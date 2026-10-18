<div align="center">

# 🛩️ ESP-FC 飞控 · 耀坤整理版

**ESP32 高性能飞控 —— 迷你、低成本、高性能，为业余玩家而生**

![MCU](https://img.shields.io/badge/MCU-ESP32%20%7C%20ESP32--S3%20%7C%20RP2040-purple)

![Build](https://img.shields.io/badge/Build-PlatformIO-orange)

![Config](https://img.shields.io/badge/Config-Betaflight%20v10.10%20compatible-green)

![License](https://img.shields.io/badge/License-MIT-blue.svg)

![Upstream](https://img.shields.io/badge/Upstream-rtlopez%2Fesp--fc-lightgrey)

![YaoKun](https://img.shields.io/badge/YaoKun-S3%20Hardware%20Port-c8102e)

**简体中文** · [**English**](README_EN.md)

</div>

---

> 📌 **本仓库是 [rtlopez/esp-fc](https://github.com/rtlopez/esp-fc) 的中文整理版 + 耀坤 S3 硬件适配版。**  
> `master` 分支**保持上游原样**（仅调整目录位置，未改一行代码逻辑）。  
> `yaokun-organized` 分支在整理版基础上**新增了耀坤 S3 板级适配**（详见下方 [耀坤 S3 适配版](#-耀坤-s3-适配版yaokun-organized-分支)）。  
> 上游项目与作者：[Ramon Lopez](https://github.com/rtlopez) · MIT 许可

## 📌 这是什么

ESP-FC 是一款运行在 **ESP32** 上的开源飞控固件，定位是**迷你、低成本、高性能**。

它的杀手锏是**兼容性**：固件刻意模拟了 **Betaflight 4.2** 的通信协议，  
所以你可以直接用官方 [Betaflight Configurator](https://github.com/betaflight/betaflight-configurator)  
图形界面来配置它，用官方 [Blackbox Log Viewer](https://blackbox.betaflight.com/) 分析黑匣子日志 ——  
**会玩 Betaflight 的人，零成本上手 ESP-FC。**

> ⚠️ 但请注意：它**不是** Betaflight。功能与性能上存在局限和差异，具体见下文。

## ✨ 核心特性

| 特性                | 说明                                                                 |
| ----------------- | ------------------------------------------------------------------ |
| **多芯片支持**         | ESP32 / ESP32-S3（推荐），另兼容 ESP32-S2 / C3 / RP2040 / RP2350 / ESP8266 |
| **全电调协议**         | PWM、Oneshot125/42、Multishot、Brushed、Dshot150/300/600 双向            |
| **全遥控协议**         | PPM、SBUS、IBUS、CRSF（含 ELRS）                                         |
| **ESP-NOW 接收机**   | 内置 ESP-NOW 接收 + Wi-Fi 配置，无需额外接收机硬件                                 |
| **多种陀螺仪**         | SPI / I2C 双总线，支持 MPU6050、MPU9250、ICM20602、ICM42688、BMI160          |
| **飞行模式**          | ACRO（手动）、ANGLE（自稳）、AIRMODE（空中解锁）                                   |
| **高循环频率**         | ESP32 + SPI 陀螺仪下，陀螺仪/主循环可达 **4 kHz**                               |
| **黑匣子记录**         | 支持 OpenLog / OpenLager / 内部 Flash                                  |
| **MSP + CLI**     | 标准 MSP 协议与命令行接口                                                    |
| **飞行中调参**         | PID 可在空中实时调整，不必落地重刷                                                |
| **安全保护**          | 失控保护（failsafe）、蜂鸣器、LED、电压监测                                        |
| **Betaflight 兼容** | 配置工具兼容 v10.10，现有 Betaflight 调参经验可直接套用                              |

---

## 🚁 耀坤 S3 适配版（`yaokun-organized` 分支）

这一节是**给耀坤 S3 无人机硬件的完整落地教程**：从接线、编译、烧录、地面站配置，  
到首次试飞的每一步。如果你手上是耀坤的板子，**只看这一节就够了**。

### 适配了什么

| 编号     | 文件                                                        | 改动                                                 |
| ------ | --------------------------------------------------------- | -------------------------------------------------- |
| **Y1** | `Firmware/lib/Espfc/src/Target/TargetESP32s3YaoKun.h`（新建） | 耀坤 S3 板级引脚定义，逐条对齐《耀坤S3无人机引脚定义.xlsx》                |
| **Y2** | `Firmware/lib/Espfc/src/Target/Target.h`                  | +3 行：`-DESPFC_TARGET_YAOKUN` 时选耀坤定义                |
| **Y3** | `Firmware/platformio.ini`                                 | 新增 `esp32s3_yaokun` / `esp32s3_yaokun_n4r2` 两个编译环境 |
| **Y4** | 编译宏 `-DESPFC_DEV_PRESET_BRUSHED`                          | 输出协议强制 PWM —— 8520 空心杯是**有刷**电机                    |

> ✅ **算法层 0 行改动**。姿态解算（AHRS）、滤波、PID、混控、MSP 协议栈、地面站兼容性  
> 全部原样保留上游实现。上游的 `[env:esp32s3]` 也**一行未改**，可随时切换对比。

### 为什么必须这么做

上游 `TargetESP32s3.h` 是给 **Lolin S3 Mini 一类通用模板板**写的，引脚全是占位值。  
直接烧到耀坤板上会：

- ❌ **四个电机一个都不转** —— 上游驱动 39/40/41/42，耀坤板的电调接在 **6/5/15/16**
- ❌ **蜂鸣器常鸣** —— 上游把 GPIO39 当电机脚，而耀坤板上 **39 = 蜂鸣器**
- ❌ **IMU 读不到** —— 上游 SPI 片选是 8、时钟是 12，耀坤板是 **CS=17、SCK=38**
- ❌ **电池电压读数偏差一倍** —— 上游 ADC 接 GPIO1，耀坤板是 **GPIO2** 且分压比为 1:2

### 完整引脚表

**电机输出（🔴 8520 空心杯有刷电机）**

| 通道               | GPIO   | 丝印      | 位置    |
| ---------------- | ------ | ------- | ----- |
| `ESPFC_OUTPUT_0` | **6**  | MOT1_FR | 右前 FR |
| `ESPFC_OUTPUT_1` | **5**  | MOT2_RR | 右后 RR |
| `ESPFC_OUTPUT_2` | **15** | MOT3_RL | 左后 RL |
| `ESPFC_OUTPUT_3` | **16** | MOT4_FL | 左前 FL |

**IMU（六轴）**

| 功能          | GPIO   | 说明                      |
| ----------- | ------ | ----------------------- |
| SPI_SCK     | **38** |                         |
| SPI_MOSI    | **18** |                         |
| SPI_MISO    | **21** |                         |
| **GYRO_CS** | **17** | 🔴 **V1 板实测值**；V2 板为 42 |
| I2C_SCL     | **8**  | 🔴 **SCL=8、SDA=9，别写反**  |
| I2C_SDA     | **9**  | MPU6050 / BMP280 / 磁力计  |

**遥控与串口**

| 用途         | GPIO      | 说明                        |
| ---------- | --------- | ------------------------- |
| SBUS 输入    | **1**     | xlsx `EXT01`；SBUS 是**单线** |
| ELRS TX    | **11**    | 飞控 → 接收机                  |
| ELRS RX    | **12**    | 接收机 → 飞控                  |
| UART0(MSP) | **43/44** | 地面站主串口，115200 8N1         |
| USB CDC    | —         | S3 原生 USB，枚举为虚拟 COM       |

**其它**

| 功能      | GPIO   | 说明                                                      |
| ------- | ------ | ------------------------------------------------------- |
| VBAT 采样 | **2**  | 1:2 分压 ⇒ `ESPFC_ADC_SCALE = 2.0f/4096`（填错电压显示减半、低压告警不响） |
| 蜂鸣器     | **39** | 有源蜂鸣器                                                   |
| 蓝灯      | **14** | ESP-FC 只驱动单色灯；红 41 / 绿 7 未用                             |
| 按键      | -1     | 本板无独立按键，配对用 CLI                                         |

> ⚠️ **S3 硬件禁区**：GPIO26~37 是内部 Flash/PSRAM（碰了开不了机）；  
> GPIO0/3/45/46 是启动 strapping 脚；GPIO43/44 是唯一的 MSP 串口。

### 🔴 8520 空心杯 = 有刷电机，必须开 BRUSHED

这是**唯一一个"不编译就完全飞不起来"的决定**。

ESP-FC 默认发 **DShot300**（数字协议，需要智能电调里有解码芯片）。  
8520 空心杯配的是**廉价有刷电调**，只认传统 **PWM 脉宽**。  
给它发 DShot = 给门铃贴张纸条写 "DingDong"，它毫无反应 ⇒ **四电机全停转**。

`-DESPFC_DEV_PRESET_BRUSHED` 让 `ModelConfig.h` 做三件事：

```cpp
output.protocol = ESC_PROTOCOL_BRUSHED;   // 协议换成 PWM
output.async = true;                       // 异步 LEDC 输出，不占 CPU
output.rate = 3000;                        // 3 kHz
```

同时我们在 Target 里**故意不定义** `ESPFC_DSHOT_TELEMETRY` ——  
DShot 双向回读转速只对智能电调有意义，对 PWM 电调只会白占 DMA 与串口。

### 选对编译环境（Flash / PSRAM）

| 项             | `esp32s3_yaokun`（立创 R8N8）★ | `esp32s3_yaokun_n4r2`（Supermini） |
| ------------- | -------------------------- | -------------------------------- |
| Flash         | 8 MB                       | 4 MB                             |
| PSRAM         | 8 MB **OPI（八线）**           | 2 MB **QIO（四线）**                 |
| 分区表           | `default_8MB.csv`          | `partitions_4M_nota.csv`         |
| `memory_type` | `qio_opi`                  | `qio`                            |

> 🔴 **选错直接 panic，且没有任何串口输出、地面站完全搜不到板子**：  
> N4R2 刷了 R8N8 参数 → app 超出 4MB 分区边界 + OPI 初始化失败。  
> 看模组丝印即可判断：`R8N8` = 8+8，`N4R2` = 4+2。

### 编译

```bash
git clone https://github.com/YaoKunS/esp-fc.git
cd esp-fc
git checkout yaokun-organized
cd Firmware

pio run -e esp32s3_yaokun          # ★ 编译 R8N8（常用）
pio run -e esp32s3_yaokun_n4r2     # 编译 N4R2
pio test -e native                 # 跑单元测试
```

VS Code 里打开 `esp-fc.code-workspace`，底部状态栏选 `esp32s3_yaokun`：

| 操作    | 快捷键          |
| ----- | ------------ |
| 编译    | `Ctrl+Alt+B` |
| 烧录    | `Ctrl+Alt+U` |
| 串口监视器 | `Ctrl+Alt+M` |

平台会先编译，所以**第一次编译约 2~5 分钟**（要装工具链、扫 44 个库）。

### 烧录

**方式一：PlatformIO（推荐，自动进下载模式）**

```bash
cd Firmware
pio run -e esp32s3_yaokun -t upload --upload-port COM28
pio device monitor --port COM28
```

配置里已开 `use_1200bps_touch` + `wait_for_upload_port` + `require_upload_port`，  
插上板子它会自己复位进下载模式。

**方式二：预编译固件（发给别人时用）**

固件在 [`Firmware/release/`](Firmware/release/)，含**中英文指纹与烧录说明**。  
用 [ESP Tool Website](https://espressif.github.io/esptool-js/)：

| 文件               | Flash 地址  |
| ---------------- | --------- |
| `bootloader.bin` | `0x0`     |
| `partitions.bin` | `0x8000`  |
| `boot_app0.bin`  | `0xE000`  |
| `firmware.bin`   | `0x10000` |

> ⚠️ **不要整片擦除**。参数持久化在 NVS 区（`0x9000`），整片连写会清掉你调好的  
> PID 与校准数据。按上表**分片烧录**即可。

**烧录失败停在下载模式？** 先确认 USB CDC 已枚举出 COM；  
不行就按住 BOOT 键再复位，或改用 UART0（GPIO43/44）。

### 首次配置（Betaflight Configurator）

1. **接上位机** —— 推荐 UART0（43/44）；USB CDC 也行
2. **CLI 里先确认引脚** —— 敲 `status` 和 `dump`，把输出存成文件做基线
3. **设置串口功能** —— UART0 = MSP，UART2（11/12）如接 ELRS 则协议选 **CRSF**
4. **不装桨测电机** —— ⚠️ **务必先拆掉桨叶**。四个电机必须全部响；  
   全不响 → 检查是否漏了 `-DESPFC_DEV_PRESET_BRUSHED`
5. **校准加速度计** —— 逐面静止 ≥2 秒，采满六面
6. **插桨，开陷波** —— 有刷电机噪音大，CLI 敲 `set gyro_notch_count 3`
7. **设置 failsafe** —— 按你的接收机类型配置失控保护策略

### 悬空台架检查（不装桨也能做完的大部分项）

- 手动左右/前后倾斜机身，地面站姿态仪应**同向**翻转
- 拔掉 IMU 排线 → 应报"传感器失联"而不是静默
- 断开接收机 → 应进入 failsafe，电机降油门
- 地面站电压读数应与万用表实测**一致**（验证 `ESPFC_ADC_SCALE` 填对了）

### ⚠️ 首次试飞必读

**ESP-FC 是纯姿态自稳 + 手动油门**：

- **松杆不会悬停** —— 姿态会稳平，但保持水平速度继续飘
- **松油门就掉高度**
- 无 GPS / 气压计 / 测距 ⇒ **无定高、无定点、无航点**

> 首次带桨请：**空旷场地、装保护圈、留足退让空间、低空慢速**。  
> 推杆机身应**向前倾**；方向反了要改混控顺序，**不要靠改 PID 修正**。

### 故障速查

| 现象           | 根因                                 | 处理                               |
| ------------ | ---------------------------------- | -------------------------------- |
| 地面站搜不到板子     | env 选错（Flash/PSRAM 不匹配）            | 换 `_n4r2` 或 `esp32s3_yaokun` 重烧  |
| 烧录后停在下载模式    | USB CDC 没枚举 COM                    | 按住 BOOT 复位；或改用 UART0             |
| 上电无任何串口输出    | Flash/PSRAM 参数错 → panic            | 对照上面选型表                          |
| **四个电机都不转**  | **漏 `-DESPFC_DEV_PRESET_BRUSHED`** | 加上重新编译                           |
| 只有一个电机转      | 电机顺序 / 接线错                         | 应为 6/5/15/16                     |
| 电机全转但力度极小    | 电压采样系数错 → 误判低压                     | 核对 `ESPFC_ADC_SCALE = 2.0f/4096` |
| 显示电压只有一半     | 同上                                 | 同上                               |
| 姿态不动 / 传感器失联 | IMU 片选错（V1=17 / V2=42）             | 改 `ESPFC_SPI_CS_GYRO` 重编         |
| **蜂鸣器常鸣**    | **烧的是上游 `esp32s3` 固件**             | 改烧 `esp32s3_yaokun`              |
| SBUS 无信号     | 接收机没供电 / 未共地                       | SBUS 是单线：信号到 GPIO1 + 共地          |
| ELRS 接收机无数据  | 协议没设成 CRSF                         | 地面站改 UART2 协议为 CRSF              |
| 插桨后机身剧烈抖动    | 电机噪音进 IMU                          | `set gyro_notch_count 3`         |
| 校准后姿态仍飘      | 校准没真正采到六面                          | 重跑校准，逐面静止 ≥2 秒                   |

### 配套文档

- 📘 **[技术说明书（HTML 完整版）](Docs/ESP-FC技术说明书.html)** —— 架构、控制回路、协议、构建体系全解
- 🔧 **[耀坤 S3 适配说明](Docs/耀坤S3适配说明.md)** —— 每处改动的根因与验证方法
- 🔧 **[固件指纹与烧录说明](Firmware/release/)** —— SHA-256 校验 + 中英文烧录指引


<div align="center">

**🛩️ ESP-FC** · 由 [Ramon Lopez](https://github.com/rtlopez) 倾力打造 · MIT License  
· 本中文整理版由 [耀坤智联](https://github.com/YaoKunS) 维护

</div>
