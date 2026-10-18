#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pack_release.py —— ESP-FC 耀坤整理版 固件打包 + 中英文指纹说明生成
===============================================================================
用途
----
编译完成后（`pio run -e esp32s3_yaokun`），把PlatformIO 分散的4 个产物
（bootloader / partitions / boot_app0 / firmware）合并成**单文件**固件，
同时自动生成 **中英文两份指纹与烧录说明**。

为什么需要合并成单文件
----------------------
   PlatformIO 的产物是四个独立 bin，烧录时必须分别指定地址。
   合并后用户只要一个文件、地址填 0x0 即可 —— 发给别人、存档、校验都方便得多。
   （Flix / YaoKunDrone 两个工程用的是同一套做法。）

🔴 合并单文件的一个致命细节：flash-mode 必须是 DIO
--------------------------------------------------
   ESP32 bootloader 的镜像头里写死了 SPI 模式与频率。如果你用 esptool 5.x
   的 `merge-bin` 合成时把 flash-mode 填成 qio（PlatformIO 默认），
   合成出来的头部会比正确值**多 33 字节**偏移，导致芯片按错误模式读 Flash
   → 上电直接不启动 / 反复重启。
   bootloader 本来就是 DIO，所以合并时也必须写 dio。

用法
----
   python Firmware/tools/pack_release.py                 # 默认打包 R8N8 版
   python Firmware/tools/pack_release.py --env esp32s3_yaokun_n4r2
   python Firmware/tools/pack_release.py --ver v1.0 --no-merge   # 只生成说明

作者：耀坤智联 YaoKunSmart
"""

import argparse
import datetime
import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys

# ── 路径常量 ────────────────────────────────────────────────────────────────
# 本脚本放在 Firmware/tools/ 下，因此工程根是上两级
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
FIRMWARE_DIR = os.path.dirname(TOOLS_DIR)          # Firmware/
REPO_DIR = os.path.dirname(FIRMWARE_DIR)           # 仓库根
BUILD_DIR = os.path.join(FIRMWARE_DIR, ".pio", "build")
RELEASE_DIR = os.path.join(FIRMWARE_DIR, "release")

# boot_app0.bin 不在 build 目录里，它由 esp32 core 提供，按需自动定位
BOOT_APP0_HINTS = [
    os.path.expanduser("~/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin"),
    os.path.expanduser("~/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0_16mb.bin"),
]

# 各段的烧写地址（合并布局，与 ESP32 标准一致）
SEGMENTS = [
    ("bootloader", 0x0),
    ("partitions", 0x8000),
    ("boot_app0", 0xE000),
    ("firmware", 0x10000),
]

# 合并后单文件末尾追加（ESP32 标准做法）
FLASH_SECTOR_SIZE = 0x1000
ENCRYPT_KEY = b"\xff" * 16


def log(msg):
    """带前缀的进度输出，方便在打包日志里区分阶段。"""
    print(f"[pack] {msg}", flush=True)


def sha256(path):
    """算文件 SHA-256，返回 64 位小写十六进制字符串。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def human_size(n):
    """把字节数同时写成十进制和十六进制，方便核对 esptool 输出。"""
    return f"{n:,} B (0x{n:X})"


def find_boot_app0():
    """
    定位 boot_app0.bin。

    它是 Arduino ESP32 core 提供的 OTA 选择器，作用是把 otadata 指向 app0。
    缺了它芯片不会启动到 app。build 目录里没有，只能到 core 包里找。
    """
    for p in BOOT_APP0_HINTS:
        if os.path.exists(p):
            return p
    #兜底：在整个 core 包目录里搜一遍（core 版本升级会改路径）
    core = os.path.expanduser("~/.platformio/packages/framework-arduinoespressif32")
    for root, _dirs, files in os.walk(core):
        if "boot_app0.bin" in files:
            return os.path.join(root, "boot_app0.bin")
    return None


def parse_image_header(path):
    """
    解析 ESP32 镜像头，提取 SPI 模式/频率/段数/入口点。

    头部布局（esp_image_header_t）:
      0x00 magic(1) = 0xE9
      0x01 segment_count
      0x02 spi_mode
      0x03 spi_speed_size   （高 4 位=频率，低 4 位=容量）
      0x04 entry_addr(4)
    """
    with open(path, "rb") as f:
        hdr = f.read(8)
    if len(hdr) < 8 or hdr[0] != 0xE9:
        return None
    return {
        "magic": hdr[0],
        "segments": hdr[1],
        "spi_mode": hdr[2],
        "spi_speed_size": hdr[3],
        "entry": struct.unpack("<I", hdr[4:8])[0],
    }


def merge_bin(parts, out_path):
    """
    合并成单文件：按地址顺序写入，段间空隙用 0xFF 填充。

    为什么不直接 esptool merge-bin？
       —— 因为 esptool 5.x 命令名是 `merge-bin`（不是 merge_bin），
          且**地址与文件名必须是两个独立参数**，写成 `--address` 会被静默忽略。
       这里自己实现更可控，也避免版本差异踩坑。

    ⚠️ 头部 flash-mode 会被 esptool 后续处理改写吗？
       不会 —— 我们原样拼接 bootloader 的字节，所以头部保持原样（DIO）。
       这正是我们要的。
    """
    end = max(addr + os.path.getsize(p) for p, addr in parts)
    # 末尾补到扇区边界，避免芯片按扇区读时越界
    total = ((end + FLASH_SECTOR_SIZE - 1) // FLASH_SECTOR_SIZE) * FLASH_SECTOR_SIZE
    buf = bytearray(b"\xff" * total)
    for path, addr in parts:
        with open(path, "rb") as f:
            data = f.read()
        buf[addr:addr + len(data)] = data
        log(f"  写入 0x{addr:06X} : {os.path.basename(path)} ({len(data):,} B)")
    with open(out_path, "wb") as f:
        f.write(buf)
    log(f"合并完成 → {os.path.basename(out_path)}  {human_size(len(buf))}")
    return len(buf)


def build_context(env, version):
    """
    收集打包需要的全部信息：产物路径、大小、哈希、镜像头、编译时间。

    返回一个 dict，模板直接用它填表。
    """
    bdir = os.path.join(BUILD_DIR, env)
    if not os.path.isdir(bdir):
        sys.exit(f"[pack][错误] 找不到构建目录：{bdir}\n"
                 f"        请先执行：pio run -e {env}")

    parts = []
    for name, addr in SEGMENTS:
        if name == "boot_app0":
            p = find_boot_app0()
            if p is None:
                sys.exit("[pack][错误] 找不到 boot_app0.bin（Arduino ESP32 core 未安装？）")
        else:
            p = os.path.join(bdir, f"{name}.bin")
        if not os.path.exists(p):
            sys.exit(f"[pack][错误] 缺少产物：{p}\n"
                     f"        请先完整执行：pio run -e {env}")
        parts.append((p, addr))

    ctx = {
        "env": env,
        "version": version,
        "built": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "built_en": datetime.datetime.now().strftime("%b %d %Y %H:%M:%S"),
        "date_tag": datetime.datetime.now().strftime("%Y%m%d"),
        "segments": [],
        "app_hdr": parse_image_header(parts[-1][0]),
        "boot_hdr": parse_image_header(parts[0][0]),
    }

    for path, addr in parts:
        ctx["segments"].append({
            "name": os.path.splitext(os.path.basename(path))[0],
            "path": path,
            "addr": addr,
            "size": os.path.getsize(path),
            "sha": sha256(path),
        })

    app = ctx["segments"][-1]
    ctx["app_size"] = app["size"]
    ctx["flash_size_mb"] = 8 if "n4r2" not in env else 4
    return ctx


# ── 指纹说明模板（中/英） ────────────────────────────────────────────────────

CN_TMPL = """# 耀坤S3无人机 / ESP-FC 整理版 —— 固件指纹与烧录说明

## 一、这份固件是什么

基于开源飞控 **ESP-FC**（原作者 Ramon Lopez）的**耀坤整理版**。
在保留上游全部代码与 MIT 许可的前提下，新增了耀坤 S3 硬件的板级适配。

- **上游项目**：<https://github.com/rtlopez/esp-fc>（MIT，`(c) Ramon Lopez`）
- **整理版仓库**：<https://github.com/YaoKunS/esp-fc>（分支 `yaokun-organized`）
- **硬件对应**：耀坤 S3 无人机（ESP32-S3，{flash}MB Flash + {psram}）
- **电机**：4 × **8520 空心杯有刷电机**，GPIO **6 / 5 / 15 / 16**（FR / RR / RL / FL），**PWM 输出**
- **传感器**：MPU6500（SPI，CS=GPIO17）或 MPU6050（I2C，SDA=9 / SCL=8）
- **遥控**：SBUS（GPIO1）；ELRS 预留 UART2（GPIO11/12，协议需设为 CRSF）
- **地面站**：Betaflight / Cleanflight Configurator（MSP 协议 v2）
- **其它**：蜂鸣器 GPIO39、电池电压采样 GPIO2（1:2 分压）

> ★ 本固件是**纯姿态自稳 + 手动油门**：没有 GPS、气压计、测距等位置传感器。
>
> - **松杆不会悬停** —— 姿态会稳平，但保持水平速度继续飘
> - **松油门就掉高度**
> - 首次试飞请在**空旷场地、低空、装保护圈**的前提下进行

## 二、版本与来源

| 项目 | 内容 |
| --- | --- |
| 固件版本 | **{version}**（耀坤整理版） |
| 品牌 | 耀坤智联 / YaoKunS / YaoKunSmart |
| 编译环境 | `pio run -e {env}` |
| 编译时间 | {built} |
| 工具链 | PlatformIO Core（espressif32 + arduino） |
| 关键编译宏 | `-DESPFC_TARGET_YAOKUN` `-DESPFC_DEV_PRESET_BRUSHED` |
| 应用程序大小 | {appsize} |

> 🔴 **两个宏都不能删**：
> `-DESPFC_TARGET_YAOKUN` 决定用耀坤引脚（否则用上游 39/40/41/42，电机不转、蜂鸣器常鸣）；
> `-DESPFC_DEV_PRESET_BRUSHED` 把输出从 DShot 换成 PWM
> （8520 空心杯是**有刷**电机，有刷电调只认 PWM，否则四电机全停）。

## 三、怎么烧

### 方式 A：单文件（最简单）

```bash
esptool --chip esp32s3 --port COMx --baud 921600 write_flash 0x0 "{merged}"
```

图形界面用 [ESP Tool Website](https://espressif.github.io/esptool-js/)：
连上设备 → 添加 `{merged}` → Flash Address 填 `0x0` → Program。

⚠️ 若勾选了 **DoNotChgBin**：镜像头里的 SPI 模式/频率/容量已写好，改写会破坏校验。

### 方式 B：分片（★ 已标定过的机器请用这个）

**单文件从 `0x0` 整片刷写会把 `0x9000~0xE000` 的 nvs 区清成 0xFF**，
也就是：PID、调参、加速度计标定值全部丢失。

```bash
esptool --chip esp32s3 --port COMx --baud 921600 write_flash \\\\
  0x0      "bootloader.bin" \\\\
  0x8000   "partitions.bin" \\\\
  0x10000  "firmware.bin"
```

（`boot_app0.bin` 一般不必重刷。）

## 四、怎么验证烧进去的是这一版（指纹探测）

**① 比文件哈希**（最可靠，不用上电）：

```cmd
certutil -hashfile "{merged}" SHA256
```

```bash
sha256sum "{merged}"
```

→ 应为 **{msha}**

**② 串口确认**

接 **UART0（GPIO43/44，115200 8N1）** 或 **原生 USB CDC**，115200 波特率打开。
上电后应看到 ESP-FC 的 CLI 提示符与版本横幅，
接着在 CLI 里敲 `status` 与 `dump` —— `dump` 的输出存成文件即为你的基线。

**③ 在 bin 里搜明文**（不用设备也能确认）：

- 搜 `esp-fc` → 命中（产品名串）
- 搜 `TargetESP32s3YaoKun` 一般不会进 bin（宏在编译期展开），
  改搜 `MSP` 与 `Betaflight` 相关字符串确认协议栈已编入

**④ 读 flash 里的镜像头**（只读，不改动任何东西）：

```bash
esptool --chip esp32s3 --port COMx read_flash 0x10000 0x200 app_hdr.bin
```

→ 首字节应为 `E9`（ESP 镜像魔数）。

## 五、产物与校验（SHA-256）

| 产物 | 烧写地址 | SHA-256 | 大小 |
| --- | --- | --- | --- |
{segrows}

- 合并布局：`0x0` bootloader `+ 0x8000` 分区表 `+ 0xE000` boot_app0 `+ 0x10000` 应用程序（段间填 0xFF）
- Flash 容量：**{flash}MB**（如需二次确认：`esptool image-info <bin>`）
{imghdr}

## 六、刷完必做的四件事

1. **重跑加速度计校准**（若整片刷写清空了 NVS）：逐面静止 ≥2 秒，采满六面
2. **不装桨测电机**：四个电机必须全部响；全不响 → 检查是否漏了 `-DESPFC_DEV_PRESET_BRUSHED`
3. **用万用表核对电压读数**：地面站显示应与实测一致（验证 `ESPFC_ADC_SCALE = 2.0f/4096`）
4. **插桨后开陷波**：有刷电机噪音大，CLI 敲 `set gyro_notch_count 3`

## 七、故障速查

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| 地面站搜不到板子 | env 选错（Flash/PSRAM 不匹配） | 换对应 env 重烧 |
| 烧录后停在下载模式 | USB CDC 没枚举 COM | 按住 BOOT 复位；或改用 UART0 |
| 上电无串口输出 | Flash/PSRAM 参数错 → panic | 核对模组丝印 R8N8 / N4R2 |
| **四个电机都不转** | 漏 `-DESPFC_DEV_PRESET_BRUSHED` | 加上重新编译 |
| **蜂鸣器常鸣** | 烧的是上游 `esp32s3` 固件 | 改烧 `esp32s3_yaokun` |
| 显示电压只有一半 | `ESPFC_ADC_SCALE` 填错 | 改为 `2.0f/4096` |
| 姿态不动 / 传感器失联 | IMU 片选错（V1=17 / V2=42） | 改 `ESPFC_SPI_CS_GYRO` 重编 |
| ELRS 接收机无数据 | 协议没设成 CRSF | 地面站改 UART2 协议 |

## 八、找到我们

- B 站（哔哩哔哩）：[耀坤智联](https://space.bilibili.com/3707011699050767)
- GitHub：<https://github.com/YaoKunS>
- 淘宝店：[耀坤智联](https://shop35432590.taobao.com/)

---

本说明由 `Firmware/tools/pack_release.py` 自动生成；哈希、分段布局、镜像头与编译时间均现场
从固件镜像提取，与 bin 严格一致。发布物中**不含任何本机路径**。
"""

EN_TMPL = """# YaoKun S3 Drone / ESP-FC Organized Edition — Firmware Fingerprint & Flashing Guide

## 1. What this firmware is

Built on the open-source flight controller **ESP-FC** (by Ramon Lopez).
It keeps every line of upstream code and the MIT licence, and adds a board-level
adaptation for the YaoKun S3 hardware.

- **Upstream**: <https://github.com/rtlopez/esp-fc> (MIT, (c) Ramon Lopez)
- **This fork**: <https://github.com/YaoKunS/esp-fc> (branch `yaokun-organized`)
- **Hardware**: YaoKun S3 drone (ESP32-S3, {flash} MB Flash + {psram})
- **Motors**: 4 × **8520 coreless brushed motors**, GPIO **6 / 5 / 15 / 16** (FR / RR / RL / FL), **PWM output**
- **Sensors**: MPU6500 (SPI, CS=GPIO17) or MPU6050 (I2C, SDA=9 / SCL=8)
- **RC**: SBUS (GPIO1); ELRS reserved on UART2 (GPIO11/12, protocol must be set to CRSF)
- **Ground station**: Betaflight / Cleanflight Configurator (MSP v2)
- **Misc**: buzzer GPIO39, battery sense GPIO2 (1:2 divider)

> ★ This firmware is **attitude-stabilised + manual throttle only**: no GPS, barometer or
> rangefinder.
>
> - **It does not hover when you release the sticks** — attitude is held but horizontal
>   velocity carries on
> - **Letting go of the throttle means losing altitude**
> - Fly the first time in a **wide open area, low altitude, with prop guards**

## 2. Version and provenance

| Item | Value |
| --- | --- |
| Firmware version | **{version}** (YaoKun Organized Edition) |
| Brand | YaoKunSmart / YaoKunS |
| Build environment | `pio run -e {env}` |
| Build time | {built_en} |
| Toolchain | PlatformIO Core (espressif32 + arduino) |
| Key build flags | `-DESPFC_TARGET_YAOKUN` `-DESPFC_DEV_PRESET_BRUSHED` |
| Application size | {appsize} |

> 🔴 **Neither macro may be removed**:
> `-DESPFC_TARGET_YAOKUN` selects the YaoKun pin map (otherwise upstream's 39/40/41/42 are
> used — no motors turn and the buzzer screams); `-DESPFC_DEV_PRESET_BRUSHED` switches the
> output from DShot to PWM (the 8520 coreless motors are **brushed**, and a brushed ESC only
> understands PWM — otherwise all four motors stay dead).

## 3. How to flash

### Option A — single file (simplest)

```bash
esptool --chip esp32s3 --port COMx --baud 921600 write_flash 0x0 "{merged}"
```

For a GUI use the [ESP Tool Website](https://espressif.github.io/esptool-js/):
connect → add `{merged}` → Flash Address `0x0` → Program.

⚠️ If you tick **DoNotChgBin**: the SPI mode/frequency/size are already encoded in the image
header; rewriting them breaks the checksum.

### Option B — by segment (★ use this if your board is already calibrated)

A full-chip write from `0x0` erases the NVS region `0x9000~0xE000`, which means your PID
tuning and accelerometer calibration are gone.

```bash
esptool --chip esp32s3 --port COMx --baud 921600 write_flash \\\\
  0x0      "bootloader.bin" \\\\
  0x8000   "partitions.bin" \\\\
  0x10000  "firmware.bin"
```

(`boot_app0.bin` normally does not need reflashing.)

## 4. How to verify you flashed this exact build

**① Compare the hash** (most reliable, no power needed):

```cmd
certutil -hashfile "{merged}" SHA256
```

```bash
sha256sum "{merged}"
```

→ must equal **{msha}**

**② Serial confirmation**

Attach **UART0 (GPIO43/44, 115200 8N1)** or the **native USB CDC** port and open it at
115200 baud. You should see the ESP-FC CLI banner, then type `status` and `dump` in the CLI —
save the `dump` output as your baseline.

**③ Search plaintext inside the bin** (no device needed):

- search `esp-fc` → hit (product name string)
- search for `MSP` / `Betaflight` related strings to confirm the protocol stack is linked in

**④ Read the image header from flash** (read-only, changes nothing):

```bash
esptool --chip esp32s3 --port COMx read_flash 0x10000 0x200 app_hdr.bin
```

→ the first byte must be `E9` (ESP image magic).

## 5. Artifacts and checksums (SHA-256)

| Artifact | Flash address | SHA-256 | Size |
| --- | --- | --- | --- |
{segrows}

- Merged layout: `0x0` bootloader `+ 0x8000` partitions `+ 0xE000` boot_app0 `+ 0x10000`
  application (gaps padded with 0xFF)
- Flash size: **{flash} MB** (double-check with `esptool image-info <bin>`)
{imghdr}

## 6. Four things to do after flashing

1. **Redo the accelerometer calibration** (if a full-chip write wiped NVS): hold still ≥2 s on
   each of the six faces
2. **Motor test without props**: all four motors must sound; if none do, check that
   `-DESPFC_DEV_PRESET_BRUSHED` is in your build flags
3. **Check the voltage reading against a multimeter**: the configurator value must match the
   measured value (this validates `ESPFC_ADC_SCALE = 2.0f/4096`)
4. **Enable notches once the props are on**: brushed motors are noisy — type
   `set gyro_notch_count 3` in the CLI

## 7. Troubleshooting

| Symptom | Root cause | Fix |
| --- | --- | --- |
| Configurator cannot see the board | Wrong env (Flash/PSRAM mismatch) | Rebuild with the matching env |
| Stuck in download mode after flashing | USB CDC COM not enumerated | Hold BOOT and reset, or use UART0 |
| No serial output at all on boot | Flash/PSRAM mismatch → panic | Check the module silkscreen R8N8 / N4R2 |
| **None of the four motors turn** | Missing `-DESPFC_DEV_PRESET_BRUSHED` | Add it and rebuild |
| **Buzzer runs constantly** | You flashed upstream's `esp32s3` build | Flash `esp32s3_yaokun` instead |
| Voltage reading is half the real value | Wrong `ESPFC_ADC_SCALE` | Change it to `2.0f/4096` |
| Attitude frozen / sensor lost | Wrong IMU chip select (V1=17 / V2=42) | Change `ESPFC_SPI_CS_GYRO` and rebuild |
| ELRS receiver gives no data | Protocol not set to CRSF | Set the UART2 protocol in the configurator |

## 8. Find us

- Bilibili: [YaoKunSmart](https://space.bilibili.com/3707011699050767)
- GitHub: <https://github.com/YaoKunS>
- Taobao: [YaoKunSmart](https://shop35432590.taobao.com/)

---

Auto-generated by `Firmware/tools/pack_release.py`; hashes, segment layout, image headers and
build time are extracted live from the firmware image and match the bins exactly.
The published artifacts contain **no local machine paths**.
"""


def render(tmpl, ctx, merged_name, merged_sha, merged_size):
    """
    把上下文填进模板。

    🔴 发布物绝不能出现本机绝对路径 —— 所以模板里只用文件名，
       路径信息一律在"怎么烧"小节里用相对文件名表达。
    """
    segrows = "\n".join(
        f"| `{s['name']}.bin` | `0x{s['addr']:X}` | `{s['sha']}` | {human_size(s['size'])} |"
        for s in ctx["segments"]
    )
    segrows += f"\n| **合并单文件固件** | `0x0` 整体刷 | `{merged_sha}` | {human_size(merged_size)} |"

    imghdr = ""
    if ctx["app_hdr"]:
        h = ctx["app_hdr"]
        imghdr = (f"- 应用程序镜像头：`E9 {h['segments']:02X} {h['spi_mode']:02X} {h['spi_speed_size']:02X}` "
                  f"→ SPI 模式 **{'DIO' if h['spi_mode'] == 2 else 'QIO'}**、"
                  f"段数 **{h['segments']}**、入口 **0x{h['entry']:08X}**")
    if ctx["boot_hdr"]:
        h = ctx["boot_hdr"]
        imghdr += (f"\n- bootloader 镜像头：`E9 {h['segments']:02X} {h['spi_mode']:02X} "
                   f"{h['spi_speed_size']:02X}` → SPI 模式 **{'DIO' if h['spi_mode'] == 2 else 'QIO'}**")

    psram = "8MB OPI 八线 PSRAM" if "n4r2" not in ctx["env"] else "2MB QIO 四线 PSRAM"
    psram_en = "8 MB OPI (octal)" if "n4r2" not in ctx["env"] else "2 MB QIO (quad)"

    kw = dict(ctx)
    kw.update({
        "segrows": segrows,
        "imghdr": imghdr,
        "merged": merged_name,
        "msha": merged_sha,
        "appsize": human_size(ctx["app_size"]),
        "psram": psram,
        "psram": psram,
    })
    return (tmpl
            .replace("{flash}", str(ctx["flash_size_mb"]))
            .replace("{psram}", psram_en if tmpl is EN_TMPL else psram)
            .replace("{version}", ctx["version"])
            .replace("{env}", ctx["env"])
            .replace("{built_en}", ctx["built_en"])
            .replace("{built}", ctx["built"])
            .format(**kw))


def markdown_to_text(md):
    """
    把生成的 markdown 说明转成**纯文本**版本（.txt）。

    🔴 为什么不直接手写两份模板？
        中文 md / 英文 md 是内容主体，txt 是它的纯文本投影。
        若各写一份模板，改了中文忘了改英文、或改了md忘了改 txt，
        迟早会出现"四个文件说法不一致"的尴尬。
        所以这里用**同一个渲染结果**做转换 —— 内容天然永远一致。

    转换规则：
      | 语法              | 处理                       |
      |------------------|--------------------------|
      | `# 标题`            | 标题文字 + `====` 下划线（宽度自适应）|
      | `**粗体**` / `` `代码` `` | 去掉标记，保留文字         |
      | `> 引用`            | 缩进 2 空格               |
      | 表格 `|a|b|`        | 转成按列宽对齐的等宽纯文本表格   |
      | ``` 代码块 ```      | 原样保留（去掉围栏行）           |
      | 列表 `- / 1.`       | 保留符号                  |
      | `[文字](链接)`        | `文字 (链接)`              |
      | `---` 分隔线         | `=`×72                    |
    """
    lines = md.split("\n")
    out = []
    i = 0
    n = len(lines)

    def w(s):
        """
        计算字符串的**终端显示宽度**：中文/全角字符按 2 格算。
        纯 ASCII 按 1 格。

        为什么需要它？
            表格列宽对齐靠它。如果按 len() 算，中文列会比实际窄，
            对齐全乱—— 因为终端里一个汉字占两列。
        """
        return sum(2 if ord(ch) > 0x2E80 else 1 for ch in s)

    def strip_inline(s):
        """去掉行内 markdown 标记，但保留文字内容本身。"""
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", s)   # 链接 → 文字 (url)
        s = s.replace("**", "").replace("`", "")                  # 粗体 / 行内代码
        s = s.replace("*", "")
        return s.rstrip()

    while i < n:
        line = lines[i]

        # ── 表格：检测 "| --- | --- |" 分隔行 ──────────────────────────
        if (line.lstrip().startswith("|") and i + 1 < n
                and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i + 1])):
            header = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2                      # 跳过分隔行
            rows = []
            while i < n and lines[i].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            # 计算每列最大宽度（按显示宽度算，中文算 2 格）
            ncol = max([len(header)] + [len(r) for r in rows])
            header += [""] * (ncol - len(header))
            for r in rows:
                r += [""] * (ncol - len(r))
            widths = [max(w(header[c]), max((w(r[c]) for r in rows), default=0))
                      for c in range(ncol)]
            def pad(s, width):
                return s + " " * max(0, width - w(s))
            out.append("  ".join(pad(strip_inline(header[c]), widths[c])
                                 for c in range(ncol)).rstrip())
            out.append("  ".join("-" * widths[c] for c in range(ncol)))
            for r in rows:
                out.append("  ".join(pad(strip_inline(r[c]), widths[c])
                                     for c in range(ncol)).rstrip())
            out.append("")
            continue

        # ── 标题 ──────────────────────────────────────────────────────
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            text = strip_inline(m.group(2))
            if m.group(1) == "#":
                out.append(text)
                out.append("=" * min(max(w(text), 20), 78))
            else:
                out.append("")
                out.append(text)
                out.append("-" * min(max(w(text), 12), 78))
            out.append("")
            i += 1
            continue

        # ── 代码块 ────────────────────────────────────────────────────
        if line.strip().startswith("```"):
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                out.append(lines[i])
                i += 1
            i += 1                       # 跳过收尾围栏
            out.append("")
            continue

        # ── 水平分隔线 ────────────────────────────────────────────────
        if line.strip() == "---":
            out.append("=" * 78)
            out.append("")
            i += 1
            continue

        # ── 引用块 ────────────────────────────────────────────────────
        if line.lstrip().startswith(">"):
            out.append("  " + strip_inline(line.lstrip().lstrip("> ")))
            i += 1
            continue

        out.append(strip_inline(line))
        i += 1

    # 合并连续空行，最多留 1 个
    cleaned = []
    for ln in out:
        if not ln.strip() and cleaned and not cleaned[-1].strip():
            continue
        cleaned.append(ln)
    return "\n".join(cleaned).strip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="ESP-FC 耀坤整理版 固件打包与指纹说明生成")
    ap.add_argument("--env", default="esp32s3_yaokun", help="PlatformIO 编译环境名")
    ap.add_argument("--ver", default="v1.0", help="固件版本号")
    ap.add_argument("--no-merge", action="store_true", help="只生成说明，不做合并")
    args = ap.parse_args()

    os.makedirs(RELEASE_DIR, exist_ok=True)
    log(f"环境 = {args.env}   版本 = {args.ver}")

    ctx = build_context(args.env, args.ver)
    for s in ctx["segments"]:
        log(f"  {s['name']:<12} 0x{s['addr']:06X}  {human_size(s['size'])}  {s['sha'][:16]}…")

    base = f"YaoKunS_耀坤S3无人机_ESP-FC整理版_{args.ver}_耀坤智联_{ctx['date_tag']}"

    # ── 1) 合并单文件 ──────────────────────────────────────────────────────
    if args.no_merge:
        merged_name, merged_sha, merged_size = "(未生成)", "-", 0
        log("跳过合并（--no-merge）")
    else:
        parts = [(s["path"], s["addr"]) for s in ctx["segments"]]
        merged_path = os.path.join(RELEASE_DIR, base + "_merged.bin")
        log("开始合并单文件固件")
        merged_size = merge_bin(parts, merged_path)
        merged_sha = sha256(merged_path)
        merged_name = os.path.basename(merged_path)
        log(f"SHA-256 = {merged_sha}")

    # ── 2) 生成 4 份说明：中文/英文 × markdown/纯文本 ────────────────────
    #      md 是内容主体；txt 由 markdown_to_text() 自动投影，保证两两一致。
    docs = (
        ("_指纹与烧录说明.md", "CN_TMPL", False),
        ("_指纹与烧录说明.txt", "CN_TMPL", True),
        ("_Fingerprint_and_Flashing_EN.md", "EN_TMPL", False),
        ("_Fingerprint_and_Flashing_EN.txt", "EN_TMPL", True),
    )
    for suffix, tmpl_name, as_text in docs:
        tmpl = CN_TMPL if tmpl_name == "CN_TMPL" else EN_TMPL
        out = os.path.join(RELEASE_DIR, base + suffix)
        body = render(tmpl, ctx, merged_name, merged_sha, merged_size)
        if as_text:
            body = markdown_to_text(body)
        with open(out, "w", encoding="utf-8") as f:
            f.write(body)
        log(f"说明已生成 → {os.path.basename(out)}  ({human_size(len(body.encode('utf-8')))})")

    log("全部完成。")


if __name__ == "__main__":
    main()