# 耀坤S3无人机 / ESP-FC 整理版 —— 固件指纹与烧录说明

## 一、这份固件是什么

基于开源飞控 **ESP-FC**（原作者 Ramon Lopez）的**耀坤整理版**。
在保留上游全部代码与 MIT 许可的前提下，新增了耀坤 S3 硬件的板级适配。

- **上游项目**：<https://github.com/rtlopez/esp-fc>（MIT，`(c) Ramon Lopez`）
- **整理版仓库**：<https://github.com/YaoKunS/esp-fc>（分支 `yaokun-organized`）
- **硬件对应**：耀坤 S3 无人机（ESP32-S3，8MB Flash + 8MB OPI 八线 PSRAM）
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
| 固件版本 | **v1.0**（耀坤整理版） |
| 品牌 | 耀坤智联 / YaoKunS / YaoKunSmart |
| 编译环境 | `pio run -e esp32s3_yaokun` |
| 编译时间 | 2026-10-18 18:40:31 |
| 工具链 | PlatformIO Core（espressif32 + arduino） |
| 关键编译宏 | `-DESPFC_TARGET_YAOKUN` `-DESPFC_DEV_PRESET_BRUSHED` |
| 应用程序大小 | 995,360 B (0xF3020) |

> 🔴 **两个宏都不能删**：
> `-DESPFC_TARGET_YAOKUN` 决定用耀坤引脚（否则用上游 39/40/41/42，电机不转、蜂鸣器常鸣）；
> `-DESPFC_DEV_PRESET_BRUSHED` 把输出从 DShot 换成 PWM
> （8520 空心杯是**有刷**电机，有刷电调只认 PWM，否则四电机全停）。

## 三、怎么烧

### 方式 A：单文件（最简单）

```bash
esptool --chip esp32s3 --port COMx --baud 921600 write_flash 0x0 "YaoKunS_耀坤S3无人机_ESP-FC整理版_v1.0_耀坤智联_20261018_merged.bin"
```

图形界面用 [ESP Tool Website](https://espressif.github.io/esptool-js/)：
连上设备 → 添加 `YaoKunS_耀坤S3无人机_ESP-FC整理版_v1.0_耀坤智联_20261018_merged.bin` → Flash Address 填 `0x0` → Program。

⚠️ 若勾选了 **DoNotChgBin**：镜像头里的 SPI 模式/频率/容量已写好，改写会破坏校验。

### 方式 B：分片（★ 已标定过的机器请用这个）

**单文件从 `0x0` 整片刷写会把 `0x9000~0xE000` 的 nvs 区清成 0xFF**，
也就是：PID、调参、加速度计标定值全部丢失。

```bash
esptool --chip esp32s3 --port COMx --baud 921600 write_flash \\
  0x0      "bootloader.bin" \\
  0x8000   "partitions.bin" \\
  0x10000  "firmware.bin"
```

（`boot_app0.bin` 一般不必重刷。）

## 四、怎么验证烧进去的是这一版（指纹探测）

**① 比文件哈希**（最可靠，不用上电）：

```cmd
certutil -hashfile "YaoKunS_耀坤S3无人机_ESP-FC整理版_v1.0_耀坤智联_20261018_merged.bin" SHA256
```

```bash
sha256sum "YaoKunS_耀坤S3无人机_ESP-FC整理版_v1.0_耀坤智联_20261018_merged.bin"
```

→ 应为 **98238427d80ea13678da9757fbb48d66e725cbe39e916c053878b00222fae1fe**

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
| `bootloader.bin` | `0x0` | `1776e4dd896a69d0a5c2e79957b0e2a88aa4129b1381d6478683515a1f6af343` | 15,104 B (0x3B00) |
| `partitions.bin` | `0x8000` | `1d9cca96de0fe07ad7fc0648b9878ddecd9ce565e38b589ad20fea698ed4c80c` | 3,072 B (0xC00) |
| `boot_app0.bin` | `0xE000` | `f94c5d786a7a8fab06ac5d10e33bf37711a6697636dc037559ea19cc410a17f0` | 8,192 B (0x2000) |
| `firmware.bin` | `0x10000` | `1482720c75b79337036bfdcbae9457dbfc4e2f99cb66c69fcf8677ae607f5954` | 995,360 B (0xF3020) |
| **合并单文件固件** | `0x0` 整体刷 | `98238427d80ea13678da9757fbb48d66e725cbe39e916c053878b00222fae1fe` | 1,064,960 B (0x104000) |

- 合并布局：`0x0` bootloader `+ 0x8000` 分区表 `+ 0xE000` boot_app0 `+ 0x10000` 应用程序（段间填 0xFF）
- Flash 容量：**8MB**（如需二次确认：`esptool image-info <bin>`）
- 应用程序镜像头：`E9 05 02 3F` → SPI 模式 **DIO**、段数 **5**、入口 **0x4037D018**
- bootloader 镜像头：`E9 03 02 3F` → SPI 模式 **DIO**

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
