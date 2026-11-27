#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pack_release.py —— ESP-FC耀坤版 固件打包 + 中英文指纹说明生成
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

🔴 合并单文件的另一个致命细节：bootloader 偏移按芯片而不同
----------------------------------------------------------
   经典 ESP32（火龙果 2.0 / WROOM-32）的 ROM 固定从 flash 0x1000 读
   bootloader；ESP32-S3（耀坤 S3）从 0x0 读。合并整片镜像时，
   bootloader 在镜像里的偏移必须与之一致，0x0~0x1000 之间留 0xFF：
     - hlg20：0x0=FF、0x1000=E9(bootloader)、0x8000=AA(分区表)、0x10000=E9(app)
     - s3   ：0x0=E9(bootloader)、0x8000=AA、0x10000=E9
   单文件整片镜像的**烧录**地址一律是 0x0（镜像内部偏移已摆好），
   这与「单独烧 bootloader.bin 时用 0x1000」是两件事，不要混淆。
   2026-11-27 修复：早先把两板 bootloader 都摆到 0x0，导致火龙果
   merged.bin 烧到 0x0 后物理 0x1000 处无 0xE9 镜像头、芯片不启动。
   依据：PlatformIO 自动生成的 firmware_0x00.bin 与耀坤自研飞控火龙果版
   已验证可启动的 merged.bin 均为上述布局。

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
# 🔴 v1.0.1 起 release 目录移到仓库根（与 Firmware 平级，2026-11-26 用户约定）：
#    Firmware/ 只留源码与构建产物，发布件统一放 <仓库根>/release/
RELEASE_DIR = os.path.join(REPO_DIR, "release")

# boot_app0.bin 不在 build 目录里，它由 esp32 core 提供，按需自动定位
BOOT_APP0_HINTS = [
    os.path.expanduser("~/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin"),
    os.path.expanduser("~/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0_16mb.bin"),
]

# 各段在合并单文件镜像里的偏移（ESP32 标准布局）
#
# 🔴 bootloader 偏移不是全局固定值（2026-11-27 修复单文件发布件布局）：
#    - ESP32-S3（耀坤 S3）：ROM 从 flash 0x0 读 bootloader → 镜像里摆 0x0
#    - 经典 ESP32（火龙果 2.0 / WROOM-32）：ROM 固定从 flash 0x1000 读
#      → 镜像里必须摆 0x1000，0x0~0x1000 留 0xFF 填充
#    若把经典片的 bootloader 也摆到 0x0，整片镜像烧到 0x0 后物理 0x1000
#    处不是 0xE9 镜像头，芯片上电直接不启动（串口 0 字节）。
#    依据：PlatformIO 自动生成的 firmware_0x00.bin（hlg20: 0x0=FF/0x1000=E9；
#    s3: 0x0=E9）、以及耀坤自研飞控火龙果版已验证可启动的 merged.bin 同布局。
#    下面 ("bootloader", 0x0) 只是 S3 默认值；build_context() 会按
#    BOARDS[board]["boot_addr"] 覆盖，新增板型只需在注册表里填 boot_addr。
SEGMENTS = [
    ("bootloader", 0x0),      # 默认 S3；经典 ESP32 由 build_context 覆盖成 0x1000
    ("partitions", 0x8000),
    ("boot_app0", 0xE000),
    ("firmware", 0x10000),
]

# 合并后单文件末尾追加（ESP32 标准做法）
FLASH_SECTOR_SIZE = 0x1000
ENCRYPT_KEY = b"\xff" * 16

# 🔴 发布脱敏：Arduino ESP32 core 的日志/断言宏会把 __FILE__ 编译进固件，
#    形如 C:/Users/<账号>/.platformio/packages/framework-arduinoespressif32/.../xxx.cpp
#    （本机路径 + 本机账号名，严禁出现在发布物里，2026-11-26 实扫 16 处）。
#    字符串是 NUL 结尾的，整串匹配到 NUL 为止后做等长占位替换。
LOCAL_PATH_RE = re.compile(rb'C:/Users/[^/\x00]+/\.platformio/[^\x00]+')

# ── 板型注册表（2026-11-27 火龙果适配新增）─────────────────────────────────
# 每个板型自带：Flash 容量、PSRAM 文案（中/英）、发布件命名模板、说明模板名。
# 🔴 命名口径沿 flix 仓库惯例：火龙果板发布件用 MildlySpicyDragon 前缀
#    （英文品牌名是作者的用户名，禁止意译），且不带"耀坤智联"字段——
#    品牌铁律：硬件署名 malagis，耀坤只在文档内署"固件适配"，两板品牌互不串。
# 🔴 base 里用 {ver}/{date} 占位，main() 里再填，保持与 --ver 参数联动。
# 🔴 boot_addr（2026-11-27 新增）：bootloader 在合并单文件镜像里的偏移。
#    S3 = 0x0；火龙果（经典 ESP32）= 0x1000。详见 SEGMENTS 处的说明与踩坑记录。
BOARDS = {
    "s3": {
        "boot_addr": 0x0,      # ESP32-S3：ROM 从 0x0 读 bootloader
        "flash_mb": 8,
        "psram_cn": "8MB OPI 八线 PSRAM",
        "psram_en": "8 MB OPI (octal)",
        "base": "YaoKunS_耀坤S3无人机_ESP-FC整理版_{ver}_耀坤智联_{date}",
        "tmpl_cn": "CN_TMPL",   # 既有 S3 模板，一字未改
        "tmpl_en": "EN_TMPL",
    },
    "hlg20": {
        "boot_addr": 0x1000,   # 经典 ESP32：ROM 固定从 0x1000 读 bootloader
        "flash_mb": 4,
        "psram_cn": "无 PSRAM（WROOM-32 模组）",
        "psram_en": "none (WROOM-32 module)",
        "base": "MildlySpicyDragon_火龙果2.0_ESP-FC耀坤适配版_{ver}_{date}",
        "tmpl_cn": "HLG_CN_TMPL",
        "tmpl_en": "HLG_EN_TMPL",
    },
}


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


def fix_app_image_trailer(data):
    """重算 ESP app 镜像尾部的 XOR 校验字节与 appended SHA-256（移植自 flix 打包脚本）。

    【为什么需要】bootloader 启动 app 前做两道校验：
      ① XOR 校验字节：各段段数据逐字节异或（初始 0xEF），写在最后一段之后、
         对齐到「≡15 (mod 16)」偏移处，SHA 前 1 字节；
      ② appended SHA-256：末 32 字节，覆盖镜像从 0 到校验字节（含）的全部内容。
    改了段内容（哪怕 1 字节）后两处都必须重算，否则 bootloader 报
    "Checksum failed" / 哈希不匹配而拒绝启动（flix 工程实机踩坑实证）。

    参数 data: bytes —— app 镜像原始内容（0xE9 头）
    返回 (修复后的 bytes, 是否为 app 镜像 bool)
    """
    if len(data) < 64 or data[0] != 0xE9:
        return data, False
    nseg = data[1]                       # ESP 镜像头第 2 字节 = 段数
    pos = 8 + 16                         # 8B 公共头 + 16B 扩展头（esp32 app 自 IDF v4 起都有）
    total = 0xEF                         # ESP_CHECKSUM_MAGIC
    for _ in range(nseg):
        _load, ln = struct.unpack_from("<II", data, pos)
        for b in data[pos + 8:pos + 8 + ln]:
            total ^= b
        pos += 8 + ln
    # 校验字节对齐到「下一个 ≡15 (mod 16)」的偏移（与 esptool align_file_position 一致）
    cs_off = pos + ((15 - pos % 16) % 16)
    out = bytearray(data)
    out[cs_off] = total                  # ① 重算 XOR 校验字节
    # ② 重算 appended SHA-256（覆盖 0 ~ 校验字节含），SHA 后补零保持 16 对齐
    fixed = bytes(out[:cs_off + 1]) + hashlib.sha256(bytes(out[:cs_off + 1])).digest()
    pad = (-(cs_off + 33)) % 16
    fixed += b"\x00" * pad
    return fixed, True


def sanitize_segment(path, tag):
    """读取段文件 → 替换本机路径 → 重算镜像尾部（若是 app 镜像）→ 写回原路径。

    只有真正的 ESP app 镜像（0xE9 头，即 firmware.bin）才有 appended 校验结构
    需要重算；partitions.bin / boot_app0.bin / bootloader.bin 即使被替换也无需重算
    （bootloader 镜像自带逐段校验和字段但不含路径串，实扫为 0 处）。
    返回替换处数（供日志汇报）。
    """
    with open(path, "rb") as f:
        data = f.read()
    out = bytearray(data)
    changed = 0
    for m in LOCAL_PATH_RE.finditer(data):
        full = m.group(0)
        fname = full.rsplit(b"/", 1)[-1]           # 取路径最后一段文件名
        new = b"<esp32-core>/" + fname
        if len(new) > len(full):
            new = new[:len(full)]                  # 兜底：占位串不应比原路径长
        out[m.start():m.start() + len(new)] = new
        out[m.start() + len(new):m.start() + len(full)] = b"\x00" * (len(full) - len(new))
        changed += 1
    if changed:
        data = bytes(out)
        # 改了段数据 ⇒ XOR 校验字节与 appended SHA-256 都必须重算（缺一即拒启）
        data, is_app = fix_app_image_trailer(data)
        with open(path, "wb") as f:
            f.write(data)
        log(f"  [脱敏] {tag:<12} 替换 {changed} 处本机路径"
            f"{'（已重算校验字节+SHA）' if is_app else ''}")
    return changed


def build_context(env, version, board):
    """
    收集打包需要的全部信息：产物路径、大小、哈希、镜像头、编译时间。

    board：BOARDS 注册表里本板型的条目（容量 / psram 文案按板型给，不再从 env 名猜）。
    返回一个 dict，模板直接用它填表。
    """
    bdir = os.path.join(BUILD_DIR, env)
    if not os.path.isdir(bdir):
        sys.exit(f"[pack][错误] 找不到构建目录：{bdir}\n"
                 f"        请先执行：pio run -e {env}")

    # 🔴 bootloader 偏移按板型覆盖（2026-11-27 修复，详见 SEGMENTS / BOARDS 注释）：
    #    经典 ESP32 必须把 bootloader 摆到镜像 0x1000，0x0~0x1000 保留 0xFF；
    #    S3 才是 0x0。merge_bin() 的缓冲区整体初始化为 0xFF，因此只要改地址，
    #    空隙填充自动正确，无需额外处理。ctx["segments"] 记录的地址会同步变化，
    #    说明文档里的「产物 / 烧写地址」表格也随之自动生成，不用手改模板。
    boot_addr = board["boot_addr"]
    parts = []
    for name, addr in SEGMENTS:
        if name == "bootloader":
            addr = boot_addr
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
    # 🔴 Flash 容量 / PSRAM 文案按板型给（2026-11-27 火龙果适配新增 hlg20 板型）：
    #    S3 R8N8 = 8MB + OPI PSRAM；N4R2 = 4MB + QIO PSRAM；火龙果（WROOM）= 4MB 无 PSRAM。
    #    不再从 env 名字符串猜，避免新板型漏配。
    ctx["flash_size_mb"] = board["flash_mb"]
    ctx["psram_cn"] = board["psram_cn"]
    ctx["psram_en"] = board["psram_en"]
    return ctx


# ── 指纹说明模板（中/英） ────────────────────────────────────────────────────

CN_TMPL = """# 耀坤S3无人机 / ESP-FC耀坤版 —— 固件指纹与烧录说明

## 一、这份固件是什么

基于开源飞控 **ESP-FC**（原作者 Ramon Lopez）的**ESP-FC耀坤版**。
在保留上游全部代码与 MIT 许可的前提下，新增了耀坤 S3 硬件的板级适配。

- **上游项目**：<https://github.com/rtlopez/esp-fc>（MIT，`(c) Ramon Lopez`）
- **本版仓库**：<https://github.com/YaoKunS/esp-fc>（分支 `yaokun-organized`）
- **硬件对应**：耀坤 S3 无人机（ESP32-S3，{flash}MB Flash + {psram}）
- **电机**：4 × **8520 空心杯有刷电机**，GPIO **6 / 5 / 15 / 16**（FR / RR / RL / FL），**PWM 输出**
- **传感器**：MPU6500（SPI，**CS=GPIO42**，v1.0.1 起默认；V1 老板=17，CLI
  `set pin_spi_cs_0 17` 可改）或 MPU6050（I2C，SDA=9 / SCL=8）
- **气压计**：v1.0.1 起内置 **MS5611 驱动**（I2C 0x76/0x77，兼容 MS5607/AN520 系
  兼容芯片自动判别；CLI `set baro_dev MS5611` 启用，`baro_math -1` 自动选补偿公式）
- **IMU 朝向**：v1.0.1 起按总线自动分档（BF 配置器实测标定）：
  I2C 6050 → CW270，SPI 6500 → CW90；`gyro_align` 显式设置优先
- **遥控**：SBUS（GPIO1）；ELRS 预留 UART2（GPIO11/12，协议需设为 CRSF）
- **地面站**：Betaflight / Cleanflight Configurator（MSP 协议 v2）
- **其它**：蜂鸣器 GPIO39、电池电压采样 GPIO2（1:2 分压）

> ★ 本固件是**纯姿态自稳 + 手动油门**：没有 GPS、测距等位置传感器（v1.0.1 起
> 可选配 MS5611 气压计，仅作高度显示与调试，**不做定高控制**）。
>
> - **松杆不会悬停** —— 姿态会稳平，但保持水平速度继续飘
> - **松油门就掉高度**
> - 首次试飞请在**空旷场地、低空、装保护圈**的前提下进行

## 二、版本与来源

| 项目 | 内容 |
| --- | --- |
| 固件版本 | **{version}**（ESP-FC耀坤版） |
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
上电后第一屏应看到多行 **IDENTITY 品牌横幅**（产品名 / 版本 V1.1 / 编译时间 /
作者 / B 站 / 立创 / 淘宝 / GitHub），与耀坤自研飞控、Flix 耀坤整理版口径一致；
接着在 CLI 里敲 `version` 确认版本、`status` 与 `dump` —— `dump` 的输出存成文件即为你的基线。

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
| 姿态不动 / 传感器失联 | IMU 片选错（默认 42，V1 板=17） | CLI `set pin_spi_cs_0 17`（或改 `ESPFC_SPI_CS_GYRO` 重编） |
| 换 IMU 后姿态错 90°/180° | NVS 固化了旧 `gyro_align` 值 | CLI `set gyro_align DEFAULT` → `save` 恢复自动分档 |
| 气压计读不到 | 模块接线松/SDA-SCL 对调拉死总线 | 逐根检查 VCC/GND/SDA(9)/SCL(8)，重插即恢复 |
| **蜂鸣器常鸣** | 烧的是上游 `esp32s3` 固件 | 改烧 `esp32s3_yaokun` |
| ELRS 接收机无数据 | 协议没设成 CRSF | 地面站改 UART2 协议 |

## 八、V1.1 主要改动

- **修复配置器保存后陀螺仪被永久关闭**：`MSP_SET_SENSOR_ALIGNMENT`(220)
  原会依据 `gyro_enable_mask` 把 `gyro_dev` 写成 `NONE`，而该掩码读回自运行时
  探测结果 —— 陀螺仪一旦暂时未识别就会读到 0，保存后固化进 NVS，之后每次开机
  都跳过探测。现改为只消费该字节、不改写 `gyro_dev`，**开机提示音、各状态音效、
  全部 LED 灯效与其余传感器配置一律不变**；如需显式关闭陀螺仪仍可用
  CLI `set gyro_dev NONE` + `save`。
- **修复蜂鸣器上电常鸣**：耀坤 S3 用高电平触发有源蜂鸣器（S8050），
  出厂默认 `pin_buzzer_invert` 由上游的反相 `1` 改为同相 `0`，上电不再持续
  鸣叫；需要响时仍由事件驱动鸣叫。**开机提示音、各状态音效与全部 LED
  灯效保持原样**，`beeperMask` 及所有音效/灯效配置未做任何改动。
- **出厂默认传感器全部 AUTO**：`gyro_dev` / `accel_dev` / `gyro_bus` /
  `baro_dev` / `baro_bus` / `mag_dev` / `mag_bus` 均为 `AUTO`，插上模块即自动
  探测，无需任何 CLI 配置。支持 BMP280 / SPL06-001 / MS5611 气压计、
  HMC5883L / QMC5883L / AK8963 磁力计、MPU6050 / MPU6500 / MPU9250 等 IMU。
- **开机 IDENTITY 品牌横幅**：上电第一屏打印多行身份串（产品名 / 版本 /
  编译时间 / 作者 / B 站 / 立创 / 淘宝 / GitHub），与耀坤自研飞控、Flix
  耀坤整理版口径一致；S3 版不含火龙果链接，两品牌独立。
- **IMU 朝向自动分档（终版）**：`gyro_align=DEFAULT` 时按总线自动选
  CW270（I2C 6050）/ CW90（SPI 6500），BF 配置器 3D 模型实测标定
  （实物抬头 3D 抬头、实物右倾 3D 右倾）；显式设置过的值优先，
  换 IMU 类型后用 `set gyro_align DEFAULT` 恢复自动。
- **MS5611 气压计驱动**：CLI `set baro_dev MS5611` 启用；`baro_math -1`（默认）
  按 CRC 自动判别 MS5611 / MS5607(AN520) 系兼容芯片的补偿公式。
- **陀螺仪 CS 默认 42（PCB V2）**：V1 老板 CLI `set pin_spi_cs_0 17` 切回。
- **发布件脱敏**：编译机路径/账号名已从固件镜像清除（app 校验已重算）。

## 九、找到我们

- B 站（哔哩哔哩）：[耀坤智联](https://space.bilibili.com/3707011699050767)
- GitHub：<https://github.com/YaoKunS>
- 淘宝店：[耀坤智联](https://shop35432590.taobao.com/)

---

本说明由 `Firmware/tools/pack_release.py` 自动生成；哈希、分段布局、镜像头与编译时间均现场
从固件镜像提取，与 bin 严格一致。发布物中**不含任何本机路径**。
"""

EN_TMPL = """# YaoKun S3 Drone / ESP-FC YaoKun Edition — Firmware Fingerprint & Flashing Guide

## 1. What this firmware is

Built on the open-source flight controller **ESP-FC** (by Ramon Lopez).
It keeps every line of upstream code and the MIT licence, and adds a board-level
adaptation for the YaoKun S3 hardware.

- **Upstream**: <https://github.com/rtlopez/esp-fc> (MIT, (c) Ramon Lopez)
- **This fork**: <https://github.com/YaoKunS/esp-fc> (branch `yaokun-organized`)
- **Hardware**: YaoKun S3 drone (ESP32-S3, {flash} MB Flash + {psram})
- **Motors**: 4 × **8520 coreless brushed motors**, GPIO **6 / 5 / 15 / 16** (FR / RR / RL / FL), **PWM output**
- **Sensors**: MPU6500 (SPI, **CS=GPIO42** default since v1.0.1; V1 boards use 17 —
  change with CLI `set pin_spi_cs_0 17`) or MPU6050 (I2C, SDA=9 / SCL=8)
- **Barometer**: MS5611 driver added in v1.0.1 (I2C 0x76/0x77, auto-detects MS5607/AN520
  clone parts; enable with CLI `set baro_dev MS5611`, `baro_math -1` picks the compensation
  formula automatically)
- **IMU orientation**: auto-selected per bus since v1.0.1 (calibrated against the
  Betaflight Configurator 3D model): I2C 6050 → CW270, SPI 6500 → CW90; an explicit
  `gyro_align` always wins
- **RC**: SBUS (GPIO1); ELRS reserved on UART2 (GPIO11/12, protocol must be set to CRSF)
- **Ground station**: Betaflight / Cleanflight Configurator (MSP v2)
- **Misc**: buzzer GPIO39, battery sense GPIO2 (1:2 divider)

> ★ This firmware is **attitude-stabilised + manual throttle only**: no GPS or rangefinder.
> An optional MS5611 barometer (v1.0.1+) is for altitude display / debugging only —
> **no altitude control**.
>
> - **It does not hover when you release the sticks** — attitude is held but horizontal
>   velocity carries on
> - **Letting go of the throttle means losing altitude**
> - Fly the first time in a **wide open area, low altitude, with prop guards**

## 2. Version and provenance

| Item | Value |
| --- | --- |
| Firmware version | **{version}** (ESP-FC YaoKun Edition) |
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
115200 baud. The first screen should show a multi-line **IDENTITY banner** (product / version
V1.1 / build time / author / Bilibili / OSHWHub / Taobao / GitHub), matching YaoKunDrone and
Flix organized editions; then type `version` to confirm, and `status` / `dump` in the CLI —
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
| Attitude frozen / sensor lost | Wrong IMU chip select (default 42, V1 boards = 17) | CLI `set pin_spi_cs_0 17` (or change `ESPFC_SPI_CS_GYRO` and rebuild) |
| Attitude off by 90°/180° after swapping IMU | NVS has a stale explicit `gyro_align` value | CLI `set gyro_align DEFAULT` → `save` to restore auto-detect |
| Barometer not found | Loose wiring or SDA/SCL swapped (pulls the whole I2C bus down) | Check VCC/GND/SDA(9)/SCL(8) one by one; re-seat to recover |
| ELRS receiver gives no data | Protocol not set to CRSF | Set the UART2 protocol in the configurator |

## 8. What's new in V1.1

- **Fixed Configurator permanently disabling the gyro after a save**:
  `MSP_SET_SENSOR_ALIGNMENT` (220) used to write `gyro_dev = NONE` from
  `gyro_enable_mask`, which is read back from runtime detection. If the gyro was
  momentarily not detected, saving in Configurator wrote 0 and persisted it to NVS,
  so every later boot skipped detection. The byte is now consumed but ignored;
  **startup beep, status beeps, LED effects and all other sensor settings are
  unchanged**. `set gyro_dev NONE` + `save` still disables it explicitly.
- **Fixed buzzer sounding continuously at power-on**: the YaoKun S3 uses an
  active-high buzzer (S8050), so `pin_buzzer_invert` now ships as `0`
  (non-inverted) instead of upstream's `1`. **The startup beep, all status
  beeps and all LED effects are unchanged** — `beeperMask` and every sound /
  light setting remain exactly as upstream.
- **All sensors default to AUTO**: `gyro_dev` / `accel_dev` / `gyro_bus` /
  `baro_dev` / `baro_bus` / `mag_dev` / `mag_bus` all ship as `AUTO` — plug in a
  module and it is detected automatically, no CLI setup required. Supports
  BMP280 / SPL06-001 / MS5611 barometers, HMC5883L / QMC5883L / AK8963 mags,
  and MPU6050 / MPU6500 / MPU9250 IMUs.
- **Boot IDENTITY banner**: a multi-line identity block prints on first screen
  (product / version / build time / author / Bilibili / OSHWHub / Taobao / GitHub),
  matching YaoKunDrone and Flix organized editions; the S3 banner carries no
  MildlySpicyDragon links — the two brands stay independent.
- **Automatic IMU orientation (final)**: while `gyro_align` is DEFAULT, the
  alignment is auto-selected per bus — CW270 (I2C 6050) / CW90 (SPI 6500) —
  calibrated against the Betaflight Configurator 3D model (nose up renders nose up,
  right roll renders right roll); explicit settings always win, restore auto mode
  with `set gyro_align DEFAULT`.
- **MS5611 barometer driver**: enable with CLI `set baro_dev MS5611`; `baro_math -1`
  (default) auto-detects the MS5611 vs MS5607(AN520) clone compensation formula via CRC.
- **Gyro CS default changed to 42 (PCB V2)**: V1 boards switch back with
  CLI `set pin_spi_cs_0 17`.
- **Release sanitisation**: build-machine paths / account names removed from the
  firmware image (app checksum recomputed).

## 9. Find us

- Bilibili: [YaoKunSmart](https://space.bilibili.com/3707011699050767)
- GitHub: <https://github.com/YaoKunS>
- Taobao: [YaoKunSmart](https://shop35432590.taobao.com/)

---

Auto-generated by `Firmware/tools/pack_release.py`; hashes, segment layout, image headers and
build time are extracted live from the firmware image and match the bins exactly.
The published artifacts contain **no local machine paths**.
"""

# ── 火龙果 2.0 指纹说明模板（中/英，2026-11-27 新增）────────────────────────
# 🔴 为什么不复用 S3 模板：两块板芯片（S3 / 经典 ESP32）、引脚、串口、告警路径
#    全不一样，硬塞占位符会把 S3 已验证的发布说明搅乱。独立模板，互不影响。
# 🔴 品牌铁律：硬件 (c) 微辣火龙果（malagis / MildlySpicyDragon，用户名禁意译）；
#    耀坤智联只署"固件适配"，两板品牌互不串。
HLG_CN_TMPL = """# 微辣火龙果 2.0 / ESP-FC 耀坤适配版 —— 固件指纹与烧录说明

## 一、这份固件是什么

基于开源飞控 **ESP-FC**（原作者 Ramon Lopez）的**ESP-FC耀坤版**，
为**微辣火龙果 2.0 飞控**做的板级适配。

- **上游项目**：<https://github.com/rtlopez/esp-fc>（MIT，`(c) Ramon Lopez`）
- **适配版仓库**：<https://github.com/YaoKunS/esp-fc>（分支 `yaokun-organized`）
- **硬件对应**：微辣火龙果 2.0 飞控（ESP32 DevKit V1 经典片，{flash}MB Flash，{psram}）
- **硬件设计**：**(c) 微辣火龙果（malagis / MildlySpicyDragon）**
  —— 开源页：<https://oshwhub.com/malagis/esp32-mini-plane>；
  B 站：<https://space.bilibili.com/544479100>
- **固件适配**：耀坤智联（YaoKunSmart）
- **电机**：4 × **8520 空心杯有刷电机**，GPIO **27 / 33 / 26 / 32**
  （右后 RR / 右前 FR / 左后 RL / 左前 FL，对应丝印 M2 / M1 / M3 / M4），**PWM 输出**
- **传感器**：MPU6500（SPI，SCK18 / MOSI23 / MISO19，**CS=GPIO5**）
  或 MPU6050（I2C，SDA=21 / SCL=22，排母）
- **气压计**：内置 **MS5611 驱动**（I2C 0x76/0x77，兼容 MS5607/AN520 系芯片自动判别；
  CLI `set baro_dev MS5611` 启用，`baro_math -1` 自动选补偿公式）
- **IMU 朝向**：与耀坤 S3 同一系列板框、安装方向一致，按总线自动分档
  （BF 配置器实测标定）：I2C 6050 → CW270，SPI 6500 → CW90；`gyro_align` 显式设置优先
- **遥控**：SBUS（GPIO4）；本板无空闲串口，无 ELRS 通道
- **地面站**：Betaflight / Cleanflight Configurator（MSP 协议 v2）
- **其它**：蜂鸣器 GPIO25（有源）、板载单色 LED GPIO2、
  电池电压采样 GPIO35（100K+100K 1:2 分压，**ADC1**，Wi-Fi 开启时可正常读）

> ★ 本固件是**纯姿态自稳 + 手动油门**：没有 GPS、测距等位置传感器（可选配 MS5611
> 气压计，仅作高度显示与调试，**不做定高控制**）。
>
> - **松杆不会悬停** —— 姿态会稳平，但保持水平速度继续飘
> - **松油门就掉高度**
> - 首次试飞请在**空旷场地、低空、装保护圈**的前提下进行

## 二、版本与来源

| 项目 | 内容 |
| --- | --- |
| 固件版本 | **{version}**（ESP-FC耀坤版 · 火龙果 2.0 适配） |
| 品牌 | 硬件 © 微辣火龙果（malagis / MildlySpicyDragon）· 固件适配 耀坤智联 |
| 编译环境 | `pio run -e {env}` |
| 编译时间 | {built} |
| 工具链 | PlatformIO Core（espressif32 + arduino） |
| 关键编译宏 | `-DESPFC_TARGET_HLG20` `-DESPFC_DEV_PRESET_BRUSHED` |
| 应用程序大小 | {appsize} |

> 🔴 **两个宏都不能删**：
> `-DESPFC_TARGET_HLG20` 决定用火龙果引脚（否则用上游经典 ESP32 模板的
> 电机 27/25/4/12 —— 其中 **25 是蜂鸣器**、串口还会抢走 33/32 电机脚，电机不转、蜂鸣器常鸣）；
> `-DESPFC_DEV_PRESET_BRUSHED` 把输出从 DShot 换成 PWM
> （8520 空心杯是**有刷**电机，有刷电调只认 PWM，否则四电机全停）。

## 三、怎么烧

### 方式 A：单文件（★ 全新板 / 不在乎标定数据，最简单）

```bash
esptool --chip esp32 --port COMx --baud 460800 write_flash 0x0 "{merged}"
```

图形界面用 [ESP Tool Website](https://espressif.github.io/esptool-js/)：
连上设备 → 添加 `{merged}` → Flash Address 填 `0x0` → Program。

⚠️ 若勾选了 **DoNotChgBin**：镜像头里的 SPI 模式/频率/容量已写好，改写会破坏校验。

### 方式 B：分片（★ 已标定过的机器请用这个）

**单文件从 `0x0` 整片刷写会把 `0x9000~0xE000` 的 nvs 区清成 0xFF**，
也就是：PID、调参、加速度计标定值全部丢失。

```bash
esptool --chip esp32 --port COMx --baud 460800 write_flash \\\\
  0x1000   "bootloader.bin" \\\\
  0x8000   "partitions.bin" \\\\
  0x10000  "firmware.bin"
```

（`boot_app0.bin` 一般不必重刷。）

> 🔴 **别把两个地址弄混**：单文件 `merged.bin` 整片从 `0x0` 刷写即可，
> 因为镜像内部已把 bootloader 摆在 `0x1000`；只有**单独烧 bootloader.bin**
> 时才用 `0x1000`（经典 ESP32 规则，S3 才是 `0x0`）。

> 🔴 **换板型刷机必做**：如果这块板以前刷过其它板型的 ESP-FC 固件，NVS 里
> 残留的引脚值（如 S3 的 CS=42）会**覆盖**本板默认值。刷完先在 CLI 执行
> `defaults` → `save` → `reboot`，确保跑的是火龙果引脚。

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

接 **UART0（板载 CH340 USB 口，GPIO1/3，115200 8N1）**，115200 波特率打开。
上电后第一屏应看到多行 **IDENTITY 品牌横幅**：`(c) 微辣火龙果（malagis）`
硬件署名、2025 星火奖明确归微辣火龙果项目、固件适配署耀坤智联、版本 V1.1；
与耀坤自研飞控、Flix 耀坤整理版口径一致。接着在 CLI 里敲 `version` 确认版本、
`status` 与 `dump` —— `dump` 的输出存成文件即为你的基线。

**③ 在 bin 里搜明文**（不用设备也能确认）：

- 搜 `esp-fc` → 命中（产品名串）
- 搜 `MSP` 与 `Betaflight` 相关字符串确认协议栈已编入

**④ 读 flash 里的镜像头**（只读，不改动任何东西）：

```bash
esptool --chip esp32 --port COMx read_flash 0x10000 0x200 app_hdr.bin
```

→ 首字节应为 `E9`（ESP 镜像魔数）。

## 五、产物与校验（SHA-256）

| 产物 | 烧写地址 | SHA-256 | 大小 |
| --- | --- | --- | --- |
{segrows}

- 合并布局：`0x1000` bootloader（经典 ESP32；`0x0`~`0x1000` 留 0xFF） `+ 0x8000` 分区表 `+ 0xE000` boot_app0 `+ 0x10000` 应用程序（段间填 0xFF）
- Flash 容量：**{flash}MB**（如需二次确认：`esptool image-info <bin>`）
{imghdr}

## 六、刷完必做的五件事

1. **清 NVS 残留**（换板型刷机时）：CLI `defaults` → `save` → `reboot`
2. **重跑加速度计校准**（若整片刷写清空了 NVS）：逐面静止 ≥2 秒，采满六面
3. **不装桨测电机**：推油门应对角两颗同转（混控序号 ≠ 丝印 M1~M4，见故障速查）
4. **用万用表核对电压读数**：地面站显示应与实测一致（验证 `ESPFC_ADC_SCALE = 2.0f/4096`）
5. **插桨后开陷波**：有刷电机噪音大，CLI 敲 `set gyro_notch_count 3`

## 七、故障速查

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| 地面站搜不到板子 | env 选错（应烧 `esp32_hlg20`） | 换 env 重烧 |
| 上电无串口输出 | CH340 驱动没装 / UART0 接线松 | 装 CP210x/CH340 驱动，查 GPIO1/3 |
| 烧录失败 / 反复重启 | GPIO12 被拉高（光流模块 MIS 上拉） | 拔掉光流模块；长期用烧 eFuse 固定 3.3V 或加 10k 下拉 |
| **四个电机都不转** | 漏 `-DESPFC_DEV_PRESET_BRUSHED` | 加上重新编译 |
| **蜂鸣器常鸣** | 烧的是上游 `esp32` 固件（其电机表把 PWM 打到 GPIO25 蜂鸣器） | 改烧 `esp32_hlg20` |
| 推油门不是对角两颗同转 | 混控序号 ≠ 丝印 M1~M4（差一个交叉） | 按 `OUTPUT_0=27(RR) 1=33(FR) 2=26(RL) 3=32(FL)` 核对 |
| 实物抬头 3D 低头（pitch/roll 双反相） | 模块 180° 反插（排母/SPI 座允许双向插装） | 做对位标记；或 CLI `set gyro_align CW270`（6050）现场试档，注意 `exit` 会重启丢未保存值 |
| 换 IMU 后姿态错 90°/180° | NVS 固化了旧 `gyro_align` 值 | CLI `set gyro_align DEFAULT` → `save` 恢复自动分档 |
| 显示电压为零 / 只有一半 | `ESPFC_ADC_SCALE` 填错，或 ADC 被改到 ADC2 组的脚 | 保持 GPIO35（ADC1）；分压系数固定 `2.0f/4096` |
| 姿态不动 / 传感器失联 | IMU 片选 / 接线错 | SPI 6500 CS=5；I2C 6050 SDA=21 / SCL=22 |
| 气压计读不到 | 模块接线松/SDA-SCL 对调拉死总线 | 逐根检查 VCC/GND/SDA(21)/SCL(22)，重插即恢复 |

## 八、本版（V1.1）火龙果适配要点

- **修复配置器保存后陀螺仪被永久关闭**：同耀坤 S3 版，`MSP_SET_SENSOR_ALIGNMENT`(220)
  不再依据 `gyro_enable_mask` 改写 `gyro_dev`，避免陀螺仪暂时未识别时被写成
  `NONE` 并固化进 NVS、之后每次开机都不探测。**开机提示音、各状态音效、
  全部 LED 灯效与其余传感器配置一律不变**。
- **修复蜂鸣器上电常鸣**：本板 GPIO25 蜂鸣器高电平触发，出厂默认
  `pin_buzzer_invert=0`（同相），上电不再持续鸣叫；**开机提示音、各状态
  音效与全部 LED 灯效保持原样**，`beeperMask` 及音效/灯效配置未改。
- **硬件归属**：PCB 硬件设计 (c) 微辣火龙果（malagis / MildlySpicyDragon），
  2025 星火计划获奖项目属于微辣火龙果项目；耀坤智联只做 ESP-FC 固件适配
  与维护，两品牌相互独立。开机 IDENTITY 横幅按此口径署名。
- **出厂默认传感器全部 AUTO**：插上 MPU6050 / MPU6500 / MPU9250 IMU、
  HMC5883L / QMC5883L 磁力计、BMP280 / SPL06-001 / MS5611 气压计即自动
  探测，无需 CLI 配置。
- **板级适配**：`TargetESP32HLG20.h`（引脚对齐 flix / 自研的 BOARD_HLG_V2
  口径，两者逐脚一致）与编译环境 `esp32_hlg20`。
- **IMU 朝向沿用自动分档**：与耀坤 S3 同一系列板框，I2C 6050 → CW270、
  SPI 6500 → CW90 原样生效，无需 CLI 配置。
- **MS5611 气压计驱动**可用（I2C 排母）；`baro_math -1` 自动判别兼容芯片。
- **光流（PMW3901）不在本版支持范围**：ESP-FC 0.3.0 无光流设备驱动，
  GPIO12/13/14/15 仅登记未启用。
- **发布件脱敏**：编译机路径/账号名已从固件镜像清除（app 校验已重算）。

## 九、找到我们

- 硬件与原项目：B 站 [微辣火龙果](https://space.bilibili.com/544479100) ·
  OSHWHub [malagis](https://oshwhub.com/malagis/esp32-mini-plane)
- 固件适配：B 站 [耀坤智联](https://space.bilibili.com/3707011699050767) ·
  GitHub <https://github.com/YaoKunS> ·
  淘宝店 [耀坤智联](https://shop35432590.taobao.com/)

---

本说明由 `Firmware/tools/pack_release.py` 自动生成；哈希、分段布局、镜像头与编译时间均现场
从固件镜像提取，与 bin 严格一致。发布物中**不含任何本机路径**。
"""

HLG_EN_TMPL = """# MildlySpicyDragon 2.0 / ESP-FC YaoKun Adapted Edition — Firmware Fingerprint & Flashing Guide

## 1. What this firmware is

Built on the open-source flight controller **ESP-FC** (by Ramon Lopez).
It keeps every line of upstream code and the MIT licence, and adds a board-level
adaptation for the **MildlySpicyDragon 2.0 flight controller**.

- **Upstream**: <https://github.com/rtlopez/esp-fc> (MIT, (c) Ramon Lopez)
- **This fork**: <https://github.com/YaoKunS/esp-fc> (branch `yaokun-organized`)
- **Hardware**: MildlySpicyDragon 2.0 flight controller (ESP32 DevKit V1 classic module,
  {flash} MB Flash, {psram})
- **Hardware design**: **(c) MildlySpicyDragon (malagis)** — OSHWHub project page:
  <https://oshwhub.com/malagis/esp32-mini-plane>; Bilibili:
  <https://space.bilibili.com/544479100>
- **Firmware adaptation**: YaoKunSmart (YaoKunS)
- **Motors**: 4 × **8520 coreless brushed motors**, GPIO **27 / 33 / 26 / 32**
  (RR / FR / RL / FL, silkscreen M2 / M1 / M3 / M4), **PWM output**
- **Sensors**: MPU6500 (SPI, SCK18 / MOSI23 / MISO19, **CS=GPIO5**)
  or MPU6050 (I2C, SDA=21 / SCL=22, socket)
- **Barometer**: MS5611 driver included (I2C 0x76/0x77, auto-detects MS5607/AN520 clone
  parts; enable with CLI `set baro_dev MS5611`, `baro_math -1` picks the compensation
  formula automatically)
- **IMU orientation**: same PCB family and mounting direction as the YaoKun S3 —
  auto-selected per bus (calibrated against the Betaflight Configurator 3D model):
  I2C 6050 → CW270, SPI 6500 → CW90; an explicit `gyro_align` always wins
- **RC**: SBUS (GPIO4); no spare UART, no ELRS channel on this board
- **Ground station**: Betaflight / Cleanflight Configurator (MSP v2)
- **Misc**: buzzer GPIO25 (active), onboard single LED GPIO2,
  battery sense GPIO35 (100K+100K 1:2 divider, **ADC1** — works while Wi-Fi is on)

> ★ This firmware is **attitude-stabilised + manual throttle only**: no GPS or rangefinder.
> An optional MS5611 barometer is for altitude display / debugging only —
> **no altitude control**.
>
> - **It does not hover when you release the sticks** — attitude is held but horizontal
>   velocity carries on
> - **Letting go of the throttle means losing altitude**
> - Fly the first time in a **wide open area, low altitude, with prop guards**

## 2. Version and provenance

| Item | Value |
| --- | --- |
| Firmware version | **{version}** (ESP-FC YaoKun Edition · HLG 2.0 adaptation) |
| Brand | Hardware (c) MildlySpicyDragon (malagis) · Firmware adaptation YaoKunSmart |
| Build environment | `pio run -e {env}` |
| Build time | {built_en} |
| Toolchain | PlatformIO Core (espressif32 + arduino) |
| Key build flags | `-DESPFC_TARGET_HLG20` `-DESPFC_DEV_PRESET_BRUSHED` |
| Application size | {appsize} |

> 🔴 **Neither macro may be removed**:
> `-DESPFC_TARGET_HLG20` selects the HLG pin map (otherwise upstream's classic-ESP32 template
> drives motors on 27/25/4/12 — where **25 is the buzzer** — and a UART steals motor pins
> 33/32; no motors turn and the buzzer screams); `-DESPFC_DEV_PRESET_BRUSHED` switches the
> output from DShot to PWM (the 8520 coreless motors are **brushed**, and a brushed ESC only
> understands PWM — otherwise all four motors stay dead).

## 3. How to flash

### Option A — single file (★ brand-new board / calibration data disposable, simplest)

```bash
esptool --chip esp32 --port COMx --baud 460800 write_flash 0x0 "{merged}"
```

For a GUI use the [ESP Tool Website](https://espressif.github.io/esptool-js/):
connect → add `{merged}` → Flash Address `0x0` → Program.

⚠️ If you tick **DoNotChgBin**: the SPI mode/frequency/size are already encoded in the image
header; rewriting them breaks the checksum.

### Option B — by segment (★ use this if your board is already calibrated)

A full-chip write from `0x0` erases the NVS region `0x9000~0xE000`, which means your PID
tuning and accelerometer calibration are gone.

```bash
esptool --chip esp32 --port COMx --baud 460800 write_flash \\\\
  0x1000   "bootloader.bin" \\\\
  0x8000   "partitions.bin" \\\\
  0x10000  "firmware.bin"
```

(`boot_app0.bin` normally does not need reflashing.)

> 🔴 **Two different addresses, do not mix them up**: flash the single-file
> `merged.bin` as one image at `0x0` (the image already places the bootloader
> at `0x1000` internally). `0x1000` is only for a **standalone bootloader.bin**
> on a classic ESP32 (S3 uses `0x0`).

> 🔴 **Mandatory when switching board types**: if this board previously ran ESP-FC built for
> another board, stale NVS pin values (e.g. S3's CS=42) **override** the HLG defaults.
> After flashing run `defaults` → `save` → `reboot` in the CLI.

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

Attach **UART0 (onboard CH340 USB port, GPIO1/3, 115200 8N1)** and open it at 115200 baud.
The first screen should show a multi-line **IDENTITY banner**: hardware `(c) MildlySpicyDragon
(malagis)`, the 2025 Spark Program award explicitly credited to the MildlySpicyDragon project,
firmware adaptation by YaoKunSmart, version V1.1 — matching YaoKunDrone and Flix organized
editions. Then type `version` to confirm, and `status` / `dump` in the CLI — save the `dump`
output as your baseline.

**③ Search plaintext inside the bin** (no device needed):

- search `esp-fc` → hit (product name string)
- search for `MSP` / `Betaflight` related strings to confirm the protocol stack is linked in

**④ Read the image header from flash** (read-only, changes nothing):

```bash
esptool --chip esp32 --port COMx read_flash 0x10000 0x200 app_hdr.bin
```

→ the first byte must be `E9` (ESP image magic).

## 5. Artifacts and checksums (SHA-256)

| Artifact | Flash address | SHA-256 | Size |
| --- | --- | --- | --- |
{segrows}

- Merged layout: `0x1000` bootloader (classic ESP32; 0x0-0x1000 padded with 0xFF) `+ 0x8000` partitions `+ 0xE000` boot_app0 `+ 0x10000`
  application (gaps padded with 0xFF)
- Flash size: **{flash} MB** (double-check with `esptool image-info <bin>`)
{imghdr}

## 6. Five things to do after flashing

1. **Clear stale NVS** (when switching board types): CLI `defaults` → `save` → `reboot`
2. **Redo the accelerometer calibration** (if a full-chip write wiped NVS): hold still ≥2 s on
   each of the six faces
3. **Motor test without props**: throttle must spin diagonal pairs (mixer index ≠ silkscreen
   M1~M4, see troubleshooting)
4. **Check the voltage reading against a multimeter**: the configurator value must match the
   measured value (this validates `ESPFC_ADC_SCALE = 2.0f/4096`)
5. **Enable notches once the props are on**: brushed motors are noisy — type
   `set gyro_notch_count 3` in the CLI

## 7. Troubleshooting

| Symptom | Root cause | Fix |
| --- | --- | --- |
| Configurator cannot see the board | Wrong env (must be `esp32_hlg20`) | Rebuild with the matching env |
| No serial output at all on boot | CH340 driver missing / loose UART0 wiring | Install the CH340 driver, check GPIO1/3 |
| Flashing fails / boot loops | GPIO12 pulled high (optical-flow module MIS pull-up) | Unplug the flow module; permanently fix with the 3.3V eFuse or a 10k pull-down |
| **None of the four motors turn** | Missing `-DESPFC_DEV_PRESET_BRUSHED` | Add it and rebuild |
| **Buzzer runs constantly** | You flashed upstream's `esp32` build (its motor table drives PWM onto GPIO25, the buzzer) | Flash `esp32_hlg20` instead |
| Throttle does not spin diagonal pairs | Mixer index ≠ silkscreen M1~M4 (crossed by one) | Verify `OUTPUT_0=27(RR) 1=33(FR) 2=26(RL) 3=32(FL)` |
| Nose up renders nose down (pitch/roll both inverted) | Module inserted 180° flipped (sockets accept both directions) | Mark the reference orientation; or live-test with CLI `set gyro_align CW270` (6050); note that `exit` reboots and drops unsaved values |
| Attitude off by 90°/180° after swapping IMU | NVS has a stale explicit `gyro_align` value | CLI `set gyro_align DEFAULT` → `save` to restore auto-detect |
| Voltage reads zero / half the real value | Wrong `ESPFC_ADC_SCALE`, or ADC moved to an ADC2 pin | Keep GPIO35 (ADC1); divider factor fixed at `2.0f/4096` |
| Attitude frozen / sensor lost | Wrong IMU chip select / wiring | SPI 6500 CS=5; I2C 6050 SDA=21 / SCL=22 |
| Barometer not found | Loose wiring or SDA/SCL swapped (pulls the whole I2C bus down) | Check VCC/GND/SDA(21)/SCL(22) one by one; re-seat to recover |

## 8. What's new for the HLG 2.0 in V1.1

- **Fixed Configurator permanently disabling the gyro after a save**: as on the
  YaoKun S3, `MSP_SET_SENSOR_ALIGNMENT` (220) no longer rewrites `gyro_dev` from
  `gyro_enable_mask`, so a momentary detection miss can no longer persist `NONE`
  to NVS. **Startup beep, status beeps, LED effects and all other sensor
  settings are unchanged**.
- **Fixed buzzer sounding continuously at power-on**: the GPIO25 buzzer is
  active-high, so `pin_buzzer_invert` now ships as `0` (non-inverted). **Startup
  beep, all status beeps and all LED effects are unchanged**; `beeperMask` and
  every sound / light setting remain as upstream.
- **Hardware ownership**: PCB hardware design (c) MildlySpicyDragon (malagis);
  the 2025 Spark Program award belongs to the MildlySpicyDragon project.
  YaoKunSmart only maintains the ESP-FC firmware adaptation — the two brands are
  independent, as reflected in the boot IDENTITY banner.
- **All sensors default to AUTO**: plug in MPU6050 / MPU6500 / MPU9250 IMUs,
  HMC5883L / QMC5883L mags, BMP280 / SPL06-001 / MS5611 barometers and they are
  auto-detected — no CLI configuration needed.
- **Board-level adaptation**: `TargetESP32HLG20.h` (pins aligned with the
  `BOARD_HLG_V2` conventions of flix / YaoKunDrone — both match pin-for-pin) and the
  `esp32_hlg20` build environment.
- **IMU orientation reuses auto-detection**: same PCB family as the YaoKun S3 —
  CW270 (I2C 6050) / CW90 (SPI 6500) work as-is, no CLI configuration needed.
- **MS5611 barometer driver** available (I2C socket); `baro_math -1` auto-detects clones.
- **Optical flow (PMW3901) is out of scope**: ESP-FC 0.3.0 has no flow-device driver;
  GPIO12/13/14/15 are registered but unused.
- **Release sanitisation**: build-machine paths / account names removed from the
  firmware image (app checksum recomputed).

## 9. Find us

- Hardware & original project: Bilibili [MildlySpicyDragon](https://space.bilibili.com/544479100) ·
  OSHWHub [malagis](https://oshwhub.com/malagis/esp32-mini-plane)
- Firmware adaptation: Bilibili [YaoKunSmart](https://space.bilibili.com/3707011699050767) ·
  GitHub: <https://github.com/YaoKunS> ·
  Taobao: [YaoKunSmart](https://shop35432590.taobao.com/)

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

    # 🔴 psram 文案改为板型注册表给（ctx["psram_cn"/"psram_en"]），不再从 env 名猜
    psram = ctx["psram_cn"]
    psram_en = ctx["psram_en"]

    kw = dict(ctx)
    kw.update({
        "segrows": segrows,
        "imghdr": imghdr,
        "merged": merged_name,
        "msha": merged_sha,
        "appsize": human_size(ctx["app_size"]),
    })
    return (tmpl
            .replace("{flash}", str(ctx["flash_size_mb"]))
            .replace("{psram}", psram_en if tmpl is EN_TMPL or tmpl is HLG_EN_TMPL else psram)
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
    ap = argparse.ArgumentParser(description="ESP-FC耀坤版 固件打包与指纹说明生成")
    ap.add_argument("--env", default="esp32s3_yaokun", help="PlatformIO 编译环境名")
    ap.add_argument("--ver", default="V1.1", help="固件版本号（当前发布版 V1.1，2026-11-27）")
    ap.add_argument("--no-merge", action="store_true", help="只生成说明，不做合并")
    # 🔴 --board（2026-11-27 火龙果适配新增）：选择板型注册表条目。
    #    容量/PSRAM 文案/发布件命名/说明模板都按板型取，新增板型只改 BOARDS 表。
    ap.add_argument("--board", default="s3", choices=sorted(BOARDS.keys()),
                    help="板型（决定命名、容量文案与说明模板）")
    args = ap.parse_args()

    board = BOARDS[args.board]
    os.makedirs(RELEASE_DIR, exist_ok=True)
    log(f"环境 = {args.env}   板型 = {args.board}   版本 = {args.ver}")

    ctx = build_context(args.env, args.ver, board)
    for s in ctx["segments"]:
        log(f"  {s['name']:<12} 0x{s['addr']:06X}  {human_size(s['size'])}  {s['sha'][:16]}…")

    # ── 发布脱敏（2026-11-26 新增）─────────────────────────────────────────
    # Arduino core 的 __FILE__ 字符串会把 C:/Users/<账号>/.platformio/... 编进
    # firmware.bin（实扫 16 处）。只处理 BUILD_DIR 下的三个段；
    # 🔴 boot_app0.bin 位于 PlatformIO core 包目录里，绝不能写回（会污染共享安装），
    #    它是纯 OTA 数据、不含路径串，直接跳过。
    for s in ctx["segments"]:
        if s["name"] == "boot_app0" or not s["path"].startswith(BUILD_DIR):
            continue
        n = sanitize_segment(s["path"], s["name"])
        if n:
            # 段内容变了：同步刷新上下文里的哈希与大小，保证说明文档与 bin 一致
            s["sha"] = sha256(s["path"])
            s["size"] = os.path.getsize(s["path"])
    app = ctx["segments"][-1]
    ctx["app_size"] = app["size"]
    ctx["app_hdr"] = parse_image_header(app["path"])   # 镜像头信息也可能变，重取

    # 发布件命名：按板型注册表的模板填版本号与日期（命名口径见 BOARDS 注释）
    base = board["base"].format(ver=args.ver, date=ctx["date_tag"])

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
        ("_指纹与烧录说明.md", board["tmpl_cn"], False),
        ("_指纹与烧录说明.txt", board["tmpl_cn"], True),
        ("_Fingerprint_and_Flashing_EN.md", board["tmpl_en"], False),
        ("_Fingerprint_and_Flashing_EN.txt", board["tmpl_en"], True),
    )
    # 说明模板按板型选（BOARDS["tmpl_cn"/"tmpl_en"] 指向模板变量名，此处解引用）；
    # 模板注册表集中放在这里，新增板型无需再动本循环。
    TMPLS = {"CN_TMPL": CN_TMPL, "EN_TMPL": EN_TMPL,
             "HLG_CN_TMPL": HLG_CN_TMPL, "HLG_EN_TMPL": HLG_EN_TMPL}
    for suffix, tmpl_name, as_text in docs:
        tmpl = TMPLS[tmpl_name]
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