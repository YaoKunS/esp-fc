> 开源飞控 ESP-FC · 耀坤 S3 硬件适配版 v1.0.1（2026-11-26）

# 耀坤S3无人机 · ESP-FC 整理版

*MSP 协议全兼容地面站　·　8520 空心杯有刷电机适配　·　Betaflight 配置器直接识别*

- 主控　**ESP32-S3**（R8N8 / N4R2）
- 内核　**ESP-FC**（(c) Ramon Lopez，MIT）
- 通信　**MSP v2 / ESP-NOW / Wi-Fi**
- 电机　**8520 空心杯有刷 · PWM**
- 地面站　**Betaflight / Cleanflight Configurator**
- 仓库　**github.com/YaoKunS/esp-fc**

## 目录

1. [项目定位](#一项目定位) —— 它是什么，与上游什么关系
2. [硬件规格](#二硬件规格) —— 模组选型与全部引脚
3. [为什么必须重做引脚](#三为什么必须重做引脚) —— 上游 S3 模板为何完全不能用
4. [8520 有刷电机适配](#四8520-空心杯电机适配) —— 🔴 本次最关键的一个决定
5. [软件架构](#五软件架构) —— 文件职责与主循环
6. [控制回路](#六控制回路) —— 串级 PID 与混控
7. [传感器链路](#七传感器链路) —— MPU6050 / MPU6500 双通路
8. [MSP 协议与地面站](#八msp-协议与地面站) —— 配置器如何识别本板
9. [安全机制](#九安全机制) —— 解锁门控与失联保护
10. [固件构建体系](#十固件构建体系) —— PlatformIO 环境与分区表
11. [编译与烧录](#十一编译与烧录) —— 从零到上电的全流程
12. [CLI 命令手册](#十二cli-命令手册) —— 串口上直接敲命令
13. [故障排查](#十三故障排查) —— 现象 → 根因 → 处理
14. [飞行能力边界](#十四飞行能力边界) —— 能做什么、不能做什么
15. [与上游差异总表](#十五与上游差异总表) —— 一行行说清改了什么

## 一、项目定位

ESP-FC 是一款运行在 **ESP32** 上的开源飞控固件，定位是**迷你、低成本、高性能**。它最大的特色是**协议兼容**：固件实现的是标准的 **Betaflight / Cleanflight MSP 协议 v2**，所以市面上的 **Betaflight Configurator** 和 **Cleanflight Configurator** 可以直接连上、直接识别、直接调参 —— 不需要专用上位机。

本仓库是 [rtlopez/esp-fc](https://github.com/rtlopez/esp-fc) 的 **耀坤整理版 + 耀坤 S3 硬件适配**。目标是让耀坤自研的 S3 四轴 （配 8520 空心杯电机）用上这套成熟的开源内核。

#### 上游原版（master）

ESP-FC 0.3.0 完整源码，一行未改。引脚定义面向 Lolin S3 Mini 等通用模板板，支持 ESP32 / S2 / S3 / C3 / ESP8266 / RP2040 / RP2350 七种平台。

#### 耀坤版（本分支）

在上游基础上**新增**独立板级定义 `TargetESP32s3YaoKun.h` 与独立编译环境 `esp32s3_yaokun`。算法层零改动。

> **✅ 正确做法**
>
> **为什么"算法层零改动"这么重要？**
> 因为飞控里最容易出事的地方不是引脚，是**姿态解算、角速度滤波、混控顺序、failsafe 判据**。这些逻辑上游已经在大量机型上验证过。**我们只换"引脚和电机协议"，把所有经过验证的数学部分原封不动留下** —— 这是本次适配风险最低的路径。

## 二、硬件规格

### 2.1 主控模组（两种，引脚相同）

| 项目 | 立创 ESP32-S3-R8N8 ★默认 | ESP32S3 Supermini N4R2 |
|---|---|---|
| Flash | **8 MB** | **4 MB** |
| PSRAM | 8 MB **OPI（八线）** | 2 MB **QIO（四线）** |
| 分区表 | `default_8MB.csv` | `partitions_4M_nota.csv` |
| `memory_type` | `qio_opi` | `qio` |
| 编译环境 | `esp32s3_yaokun` | `esp32s3_yaokun_n4r2` |

> **⛔ 危险**
>
> **🔴 选错的两种死法（都已经踩过）**
> **N4R2 刷了 R8N8 参数** → app 超出 4MB 分区边界 + OPI 初始化失败 → 芯片上电直接 `panic`，**没有任何串口输出**，地面站完全搜不到板子。
> **R8N8 刷了 N4R2 参数** → 能启动，但 PSRAM 类型填 `qio` 而实际是 OPI → 运行一段时间后随机重启。
> 看模组丝印即可判断：`R8N8` = 8+8，`N4R2` = 4+2。

### 2.2 完整引脚表（逐行取自《耀坤S3无人机引脚定义.xlsx》）

#### 电机输出

| 通道 | GPIO | PCB 丝印 | 位置 | 上游模板值 |
|---|---|---|---|---|
| `ESPFC_OUTPUT_0` | **5** | MOT2_RR | 右后 RR | 39 ❌ |
| `ESPFC_OUTPUT_1` | **6** | MOT1_FR | 右前 FR | 40 ❌ |
| `ESPFC_OUTPUT_2` | **15** | MOT3_RL | 左后 RL | 41 ❌ |
| `ESPFC_OUTPUT_3` | **16** | MOT4_FL | 左前 FL | 42 ❌ |

> **⛔ 危险**
>
> **🔴 为什么这四个数字是"要命"的**
> 上游模板把 **GPIO39 / 40 / 41 / 42** 当电机脚。而在耀坤板上：**39 = 蜂鸣器**、**41 = 红灯**、**42 = V2 板的 MPU6500 片选**。
> 不改的后果不是"电机不转"这么轻 —— 是**蜂鸣器常鸣 + IMU 片选被电平驱动乱跳**，读出来的姿态完全是噪声。

#### IMU（六轴）

| 功能 | GPIO | 说明 |
|---|---|---|
| SPI_SCK | **38** | xlsx 第 6 行；也可挂光流 |
| SPI_MOSI | **18** | xlsx 第 5 行 |
| SPI_MISO | **21** | xlsx 第 4 行 |
| **GYRO_CS** | **42** | 🔴 **v1.0.1 默认值 = PCB V2 实测**；V1 板 `set pin_spi_cs_0 17` 切回 |
| I2C_SCL | **8** | 🔴 **SCL=8、SDA=9，别写反** |
| I2C_SDA | **9** | MPU6050 / MS5611 / BMP280 / 磁力计 |
| 气压计 | −1（无内置） | v1.0.1 起支持外接 **MS5611**（I2C，与 6050 共总线） |
| MPU6500_INT | −1（未用） | GPIO40，本版未启用 |

> **💡 说明**
>
> **V1 / V2 板只差这一个引脚（`17` ↔ `42`）**
> v1.0.1 起板级默认写 **42**（PCB V2，当前出货板型）。V1 老板用 CLI `set pin_spi_cs_0 17` 一条命令切回（NVS 持久化，无需重编固件）；改 `TargetESP32s3YaoKun.h` 里 `ESPFC_SPI_CS_GYRO` 的重编路径仍保留作备选。SCK / MOSI / MISO 两版完全一致，不要去动。

#### 遥控与串口

| 用途 | GPIO | 说明 |
|---|---|---|
| SBUS 输入 | **1** | xlsx EXT01；同时设为 `ESPFC_INPUT_PIN` |
| ELRS 预留 TX | **11** | 飞控 → 接收机 |
| ELRS 预留 RX | **12** | 接收机 → 飞控 |
| UART0（MSP） | **43 / 44** | 地面站主串口，115200 8N1 |
| USB CDC | — | S3 原生 USB，枚举为虚拟 COM |

> **⚠️ 注意**
>
> **⚠️ ELRS 接收机输出的是 CRSF，不是 SBUS**
> UART2（11/12）虽然已按 xlsx 定义好，但**必须在地面站里把该串口协议改成 CRSF** 才能用。第一次上手建议直接用 SBUS 接收机（GPIO1 单线），少一个变量。

#### 其它外设

| 功能 | GPIO | 说明 |
|---|---|---|
| VBAT 采样 | **2** | 1:2 分压 ⇒ `ESPFC_ADC_SCALE = 2.0f/4096` |
| 蜂鸣器 | **39** | 有源蜂鸣器，给电即响 |
| 蓝灯 | **14** | ESP-FC 只驱动单色灯；红 41 / 绿 7 未用 |
| 板载 LED | 48 | 未驱动 |
| 按键 | −1 | 本板无独立按键，配对改用 CLI |

> **⛔ 危险**
>
> **🔴 电池电压系数填错会"咬人"**
> VBAT 经 **1:2** 分压到 GPIO2，即 `Vbat = Vadc × 2`。所以 `ESPFC_ADC_SCALE` 必须填 `2.0f / 4096`。
> 若沿用上游 ESP32S3 的 `3.3f/4096`，地面站显示的电压**只有真实值的一半**，结果是：**低压告警永远不响** —— 这比报错更危险，因为你看不出来它错了。

### 2.3 S3 硬件禁区

| 引脚 | 原因 | 本板用途 |
|---|---|---|
| **GPIO26 ~ GPIO37** | 内部 Flash / PSRAM | ❌ 绝对不能碰，占用即开不了机 |
| GPIO0 / 3 / 45 / 46 | 启动 strapping 脚（决定 boot 模式） | GPIO3 = I2C1_SDA（VL53L1X） |
| GPIO19 / 20 | USB JTAG | ❌ 不用 |
| GPIO43 / 44 | 本板唯一的 MSP 串口 | UART0 |

`TargetESP32s3YaoKun.h` 里**每一条引脚定义都写了中文注释和 xlsx 来源行号**。改之前先读注释再动手，能省掉大量"改了不生效"的排查时间。

## 三、为什么必须重做引脚

### 3.1 上游 ESP32-S3 模板是什么

ESP-FC 0.3.0 的 `Target/TargetESP32s3.h` 是给 **Lolin S3 Mini 这类通用模板板**写的。它假定的是一块"标准 S3 开发板 + 外接电调"，所有引脚都是方便记忆的占位值：

```
// 上游 TargetESP32s3.h（原样，一行未改）
#define ESPFC_INPUT_PIN 6        // ppm
#define ESPFC_OUTPUT_0 39
#define ESPFC_OUTPUT_1 40
#define ESPFC_OUTPUT_2 41
#define ESPFC_OUTPUT_3 42
#define ESPFC_SPI_0_SCK 12
#define ESPFC_SPI_0_MOSI 11
#define ESPFC_SPI_0_MISO 13
#define ESPFC_SPI_CS_GYRO 8
#define ESPFC_I2C_0_SCL 10
#define ESPFC_I2C_0_SDA 9
#define ESPFC_BUZZER_PIN 5
#define ESPFC_ADC_VBAT_PIN 1
#define ESPFC_LED_PIN -1
```

这套值跟耀坤 S3 的 PCB 布线**几乎条条对不上**。烧上去会发生什么：

> **⛔ 危险**
>

1. **四个电机一个都不转** —— 驱动 39/40/41/42，而电调接在 5/6/15/16
2. **蜂鸣器常鸣** —— GPIO39 被当成电机 PWM 输出
3. **IMU 读不到** —— SPI 片选是 8、时钟是 12，而板上是 17/38
4. **电池电压读数偏差一倍** —— ADC 接在 1 而板上是 2，且分压系数不同
5. 最糟的是 **39/40/41/42 中 GPIO42 还是 V2 板的 IMU 片选**，被高频 PWM 驱动后 IMU 数据彻底是噪声

### 3.2 我们的做法：新增，不修改

没有直接改 `TargetESP32s3.h`，而是**新建**一个文件，理由有三：

#### ① 可回归

上游 `[env:esp32s3]` 保持原样，随时能编一版做对比，定位"是我的适配错了还是上游变了"。

#### ② 可合并

将来同步上游新版本时，`TargetESP32s3.h` 大概率会被改动；我们只在自己的文件里收敛冲突。

#### ③ 可读

新人打开 `TargetESP32s3YaoKun.h`，一眼就知道这块板长什么样，不用去猜 39 是电机还是蜂鸣器。

```
// Firmware/lib/Espfc/src/Target/Target.h —— 全部改动只有这3 行
#if defined(ESPFC_TARGET_YAOKUN)          // ← 耀坤智联新增
  #include "TargetESP32s3YaoKun.h"
#elif defined(ESP32C3)
#include "TargetESP32c3.h"
...
#elif defined(ESP32S3)
#include "TargetESP32s3.h"               // ← 上游原版，保持不变
#endif
```

> **⚠️ 注意**
>
> **为什么 `ESPFC_TARGET_YAOKUN` 的判断要放在 `ESP32S3` 前面？**
> 因为该宏**同时**定义了 `ESP32S3`（芯片系列）和板级选择。如果放在后面，条件永远轮不到它，编译会静默使用上游引脚 —— 烧上去才发现问题，代价是拆桨、上电、试飞，全白费。

## 四、8520 空心杯电机适配

> **⛔ 危险**
>
> **🔴 这是本次适配唯一一个"不编译就完全飞不起来"的决定，单独一节讲。**

### 4.1 问题本质

ESP-FC 面向无刷四轴，**默认输出协议是 DShot300**。DShot 是一套**数字协议**：每帧先把线拉低再拉高，用占空比编码 0 / 1，中间还会插入 CRC。它需要**智能电调（ESC）**里有解码芯片才听得懂。

8520 空心杯电机配的是**廉价有刷电调**。所谓"电调"其实就是一个 **开关 + 二极管 + 换向器**，它只认传统的 **PWM 脉宽**（1000~2000 µs）。

类比 给门铃贴张纸条写"DingDong" 有刷电调收到 DShot 帧，理解为"有电=通"，全程无响应 → 四电机全停转

### 4.2 解法：`-DESPFC_DEV_PRESET_BRUSHED`

这个宏让 `ModelConfig.h` 在初始化时做三件事：

```
// ModelConfig.h（约 1160 行）
#ifdef ESPFC_DEV_PRESET_BRUSHED
      output.protocol = ESC_PROTOCOL_BRUSHED;   // 协议换成 PWM
      output.async = true;                       // 异步（LEDC 硬件）输出，不占 CPU
      output.rate = 3000;                        // 刷新率 3 kHz
#endif
```

同时，我们在 `TargetESP32s3YaoKun.h` 里 **故意没有**定义 `ESPFC_DSHOT_TELEMETRY` （上游 `TargetESP32s3.h` 里有那行）：

> **💡 说明**
>
> DShot 双向回读（*bidirectional DShot*）能让地面站显示实时转速，但它**只对智能电调有意义**。对 PWM 电调，它会白白占用一路 DMA 与一个串口外设，换来的功能是永远不触发的数据。

### 4.3 验证

**步骤 1 · 地面站 → 电机测试**
不装桨，接通电池，四个电机必须全部响

**步骤 2 · 只有一个响**
检查 `ESPFC_OUTPUT_0..3` 顺序与电调接线（应为 5/6/15/16）

**步骤 3 · 全都不响**
检查编译命令是否带 `-DESPFC_DEV_PRESET_BRUSHED`

## 五、软件架构

### 5.1 目录结构

```
Firmware/
├── platformio.ini                  # 编译环境（上游 + 耀坤新增两个 env）
├── partitions_4M_nota.csv          # N4R2 4MB 单分区表（无 OTA）
├── src/
│   └── main.cpp                    # 入口：初始化 + 主循环
├── lib/
│   ├── Espfc/src/
│   │   ├── Espfc.h                # 总装配
│   │   ├── Model.h/.cpp           # 设备模型（各 Device 的编排者）
│   │   ├── ModelConfig.h          # ★ 参数默认值表（引脚默认值也在这）
│   │   ├── Target/                # ★ 板级引脚定义（本适配核心）
│   │   │   ├── Target.h           # 按平台/宏分发（+3 行耀坤分支）
│   │   │   ├── TargetESP32s3.h    # 上游原版（未改）
│   │   │   └── TargetESP32s3YaoKun.h  # ★★ 新增：耀坤 S3
│   │   ├── Device/                # 各外设：IMU / MotorOutput / Receiver / Battery…
│   │   ├── Math/                  # 向量、四元数、滤波
│   │   ├── Estimator/             # 姿态解算（AHRS）
│   │   ├── Msp/                   # ★ MSP 协议栈（地面站兼容的关键）
│   │   └── Connect/               # CLI / WiFi / ESP-NOW
│   ├── EscDriver/src/             # 电机输出底层（LEDC / DShot / PWM）
│   ├── AHRS/src/                  # 姿态融合算法（Madgwick / Mahony / Kalman / RTQF）
│   ├── EspWire/src/               # 软件 I2C 实现
│   ├── Gps/src/                   # GPS 支持（未启用）
│   └── betaflight/src/            # Betaflight 兼容层（参数命名、滤波）
├── bin/                           # 打包与格式检查脚本
├── docs/                          # 上游文档
└── test/                          # PlatformIO 单元测试
```

### 5.2 主循环

ESP-FC 的主循环在 `src/main.cpp`，结构极简：

```
int main()
{
  device.initBoard();      // 按 ModelConfig 的引脚默认值初始化所有外设
  device.init();           // 加载参数（若已保存则用保存值覆盖默认值）
  while (1) {
    device.step();         // ① 读传感器 ② 姿态解算 ③ PID ④ 混控 ⑤ 输出 PWM/DSHOT
    device.await();        // FreeRTOS 让出 CPU 给 Wi-Fi / USB 任务
  }
}
```

所有实际工作都在 `Device::step()` 里串起来。S3 是双核的，`device.await()` 让出核心后，Wi-Fi / ESP-NOW / USB 任务可以在另一核上跑，这也是为什么我们的 Target 里明确**不**定义单核宏。

## 六、控制回路

ESP-FC 用的是标准的**串级 PID**，与 Betaflight 同构：

1. `陀螺仪角速度 + 加速度计` —— MPU6500(SPI) 或 MPU6050(I2C)，SPI 可到 4 kHz
2. `低通 + 陷波（可动态）` —— 有刷电机噪音大，插桨后建议开 3 组陷波
3. `AHRS 融合出四元数` —— Madgwick / Mahony / Kalman / RTQF，互补滤波类
4. `角度环 → 角速度环（串级）` —— 外环给角度目标，内环跟角速度，比单环稳得多 ★
5. `四电机分配 + 油门曲线` —— 本板为 QUAD-X（默认）
6. `PWM / DShot 帧` —— ★ 本板走 PWM(GPIO 5/6/15/16)，异步 LEDC，3 kHz ★

### 6.1 与 Betaflight 参数的对应

因为实现了 MSP 协议，配置器里调的所有 PID / 滤波 / 电机参数 **都是 Betaflight 的标准命名**，不用重新学：

| Betaflight 项 | 含义 | 本板建议初值 |
|---|---|---|
| PID Profile | 角度环/速率环 PID | 先用默认，别乱调 |
| Gyro LP Filter | 陀螺低通截止 | 默认；有刷噪音大可降到 `60 Hz` |
| Dyn Notch Count | 动态陷波组数 | **插桨后设 3** |
| Motor Min/Max | 电机端点 | 先用默认，地面站电机测试校准 |
| Motor Output | 输出协议 | 应显示 **PWM / Brushed** |

## 七、传感器链路

### 7.1 双通路设计

ESP-FC 同时支持 SPI 与 I2C 两种 IMU 总线，由 `ModelConfig` 在启动时探测。耀坤板两种都能用：

| IMU 芯片 | 总线 | SDA/SCL 或 SCK/MOSI/MISO | 片选 | 最高速率 | 朝向自动分档（v1.0.1） |
|---|---|---|---|---|---|
| MPU6500 | SPI | 38 / 18 / 21 | **42** | 4000 Hz | **CW90** |
| MPU6050 | I2C | SDA **9** / SCL **8** | — | 2000 Hz | **CW270** |

> **⚠️ 注意**
>
> **⚠️ SCL / SDA 千万别写反**
> SDA 是 **GPIO9**，SCL 是 **GPIO8**。写成 `SCL 9 / SDA 8` 的后果是 I2C 完全不通 —— 而且现象很迷惑：有时能"碰巧"读到，因为 I2C 是"时钟由主机拉低、数据由主机拉高"的单线时序，SDA/SCL 接反时 ACK 有时仍能回来。
> **同一条教训在 Flix 工程也踩过一次** —— 两个项目、两块板、同一个坑，值得单独记一笔。

### 7.2 IMU 安装朝向自动分档（v1.0.1 新增）

PCB V2 上两种 IMU 模块的插装方向都不是"零旋转"，出厂默认 `gyro_align=DEFAULT`（不旋转）会让地面站 3D 姿态错。v1.0.1 起，固件在**每次探测陀螺仪时**按总线自动分档（上表"朝向自动分档"列），BF 配置器 3D 模型实测标定：实物抬头 → 3D 抬头、实物右倾 → 3D 右倾。

> **⚠️ 注意**
>
> **🔴 插装方向是姿态反相的第一嫌疑**
> 排母 / SPI 座允许 **180° 插装**，模块插的方向一变，正确档位就跟着变。若见 pitch/roll **双双反相**（实物抬头 3D 低头、左倾 3D 右倾）= 传感器系绕 Z 轴恰差 180°，先检查模块有没有被反向插过，再谈参数。判定技巧：板子**水平静止**时加速度计 z 轴 ≈ +1g 说明芯片没装反面。

**现场试档**（不用重新编译）：`gyro_align` 每个采样周期实时读取，CLI `set gyro_align CW270` 后立即生效，BF 3D 直接可看；确认对了才 `save`。**⚠️ 任何 `save` 都会把当时的值固化进 NVS**，显式值（≠DEFAULT）会永久压制自动分档——换 IMU 类型后它会拿旧值去转新模块。恢复自动分档：`set gyro_align DEFAULT` → `save`。

**气压计（v1.0.1 新增）**：支持外接 MS5611（I2C 0x76/0x77 自动探测，OSR4096，约 51 Hz），新参数 `baro_math`：`-1` 自动按 PROM CRC-4 判别 datasheet / AN520 公式（默认）、`0` MS5611、`1` MS5607 系。🔴 市售 GY-63 模块多贴 **MS5607/AN520 系**芯片，公式用错时 **气压读数恰为真实值的一半**（约 50 kPa）——用 `-1` 自动判别即可。⚠️ 模块接线不良会拉死整条 I2C 总线（连 MPU6050 都读不到），I2C 全灭先拔外接模块。

### 7.3 常见故障：IMU 读不到

按这个顺序排查，90% 的问题在前两步：

**步骤 1 · 确认板型版本**
v1.0.1 默认 CS=`42`（PCB V2）；V1 板 `set pin_spi_cs_0 17`。改错必然读不到

**步骤 2 · 确认总线**
6500 走 SPI、6050 走 I2C。插错总线 = 完全没数据

**步骤 3 · 确认接线**
SPI 还需 MISO/MOSI/SCK/CS 四根全接；I2C 需共地

**步骤 4 · 确认滤波设置**
把 Gyro LP Filter 拉高会"看起来像没信号"，先恢复默认

## 八、MSP 协议与地面站

这是 ESP-FC 相比 Flix 那类自研飞控最大的实用优势：**用现成的 Betaflight Configurator**。

### 8.1 支持的地面站

| 地面站 | 支持 | 说明 |
|---|---|---|
| Betaflight Configurator | ✅ | 首选。参数最全，UI 最新 |
| Cleanflight Configurator | ✅ | 老牌地面站，兼容 |
| ELRS LUA 脚本 / OSD | ✅ | 需 CRFLua 飞控协议支持 |
| Betaflight 黑盒子分析 | ✅ | 需在 CLI 里开 Blackbox |

### 8.2 连接方式（三选一）

#### ① UART0（推荐）

GPIO43 = TX、GPIO44 = RX，115200 8N1。  
刷完固件第一次上电就能看到日志，最适合排查问题。

#### ② USB CDC

S3 原生 USB，Windows 会枚举出新的 COM 口。  
不依赖 USB-UART 桥芯片，二次烧录也更稳。

#### ③ Wi-Fi / ESP-NOW

连上飞控热点后可用 `wifi` 软串口下发 CLI 命令。  
适合不方便插线时看状态。

#### ④ ELRS

需把 UART2（11/12）协议设为 **CRSF**。  
走 ELRS 全双工，还有双向遥测链路。

## 九、安全机制

ESP-FC 的安全逻辑与 Betaflight 同源，耀坤板上全部生效：

| 机制 | 行为 | 本板是否生效 |
|---|---|---|
| **解锁门控** | 上电默认锁定，必须显式解锁（摇杆组合或 CLI） | ✅ |
| **接收机失联 failsafe** | 油门置零 / 缓降（可在地面站配置） | ✅ SBUS 与 CRSF 均适用 |
| **IMU 失联检测** | 读数异常时停止输出并告警 | ✅ |
| **低电压告警** | 按 `ESPFC_ADC_SCALE` 换算真实电压 | ✅ 系数正确才准（见 §2.2） |
| **油门限幅** | `desaturate()` 削顶后重新分配，保持姿态优先 | ✅ 有刷电机尤其重要 |
| **校准流程** | 加速度计 1G 校准、中位校准 | ✅ |

> **💡 说明**
>
> **关于拆桨验证校准**
> ESP-FC 的加速度计校准同样需要**把机身摆放成六面**。如果固件是"一口气跑完 48 秒、中途不等人操作"的写法，人手是跟不上的 —— 六面会采到同一个姿态，`accScale` 会塌到 1e-2 量级。
> **刷回本板前请确认你板子的 `ca` 命令是不是分段式（`ca1`~`ca6`）。**

## 十、固件构建体系

### 10.1 编译环境一览

| env 名 | 平台 | 用途 | 本整理版 |
|---|---|---|---|
| `esp32` | ESP32 | 经典 ESP32（LOLIN32） | 上游原样 |
| `esp32s3` | ESP32-S3 | 通用 S3 模板 | 上游原样（**勿烧本板**） |
| `esp32s2` | ESP32-S2 | SAOLA-1 | 上游原样 |
| `esp32c3` | ESP32-C3 | C3 开发板 | 上游原样 |
| `esp8266` | ESP8266 | D1 mini / Wemos | 上游原样 |
| `rp2040` | RP2040 | RP2040 / RP2350 | 上游原样 |
| **`esp32s3_yaokun`** | ESP32-S3 | **耀坤 S3 · R8N8** | **★ 新增** |
| **`esp32s3_yaokun_n4r2`** | ESP32-S3 | **耀坤 S3 · N4R2** | **★ 新增** |

> **⛔ 危险**
>
> **🔴 千万别烧 `esp32s3`（上游那个）到耀坤板上**
> 它会驱动 GPIO39/40/41/42 当电机 —— 其中 **39 是蜂鸣器**，你会听到**开机就一直嗡嗡响**，而且电机不动。这不是坏了，是烧错固件了。

### 10.2 耀坤 env 的关键编译宏

| 宏 | 作用 | 漏了会怎样 |
|---|---|---|
| `-DESPFC_TARGET_YAOKUN` | 选耀坤引脚定义 | 用上游引脚 → 电机不转 + 蜂鸣器常鸣 |
| `-DESPFC_DEV_PRESET_BRUSHED` | 输出协议 = PWM | 发 DShot 给有刷电调 → **四电机全停** |
| `-DESP32S3` | 芯片系列 | 找不到平台定义 |
| `-DBOARD_HAS_PSRAM` | 启用 PSRAM | 性能下降，黑盒子写入可能失败 |
| `-DARDUINO_USB_MODE=1` | USB 做 CDC | USB 口无串口，MSP 连不上 |
| `-DARDUINO_USB_CDC_ON_BOOT=1` | 上电即枚举 CDC | 同上 |

### 10.3 分区表与 Flash 参数

见 [§2.1 表格](#二硬件规格)。要点重申：

- **R8N8** → `default_8MB.csv` + `memory_type=qio_opi` + `flash_size=8MB`
- **N4R2** → `partitions_4M_nota.csv` + `memory_type=qio` + `flash_size=4MB`

> **💡 说明**
>
> **烧录时不要整片擦除**
> 参数持久化在 NVS 区（`0x9000`）。整片从 `0x0` 连写会把它一起清掉，你辛苦调好的 PID 与校准数据全丢。建议用 **分片烧录**：只写 bootloader（`0x0`）、partition table（`0x8000`）、boot_app0（`0xE000`）、app（`0x10000`）。

## 十一、编译与烧录

### 11.1 命令行（推荐，可脚本化）

```
cd Firmware

# 编译（R8N8，★常用）
pio run -e esp32s3_yaokun

# 编译 N4R2 版本
pio run -e esp32s3_yaokun_n4r2

# 烧录 + 打开串口监视器
pio run -e esp32s3_yaokun -t upload -t monitor

# 只上传（已编译过）
pio run -e esp32s3_yaokun -t upload --upload-port COM28

# 回归验证：确认上游 env 未被污染
pio run -e esp32s3
```

### 11.2 VS Code（你已装的 PlatformIO）

**步骤 1 · 打开文件夹**
VS Code → 打开文件夹 → 选 `D:\YaoKunS\Forks\esp-fc\Firmware`

**步骤 2 · 选环境**
底部状态栏 → PlatformIO 图标 → 选择 `esp32s3_yaokun`

**步骤 3 · 编译**
`Ctrl+Alt+B`（Build）

**步骤 4 · 烧录**
`Ctrl+Alt+U`（Upload）→ 会自动用 1200bps touch 让板子进下载模式

**步骤 5 · 看日志**
`Ctrl+Alt+M`（Monitor）→ 应看到 ESP-FC CLI 提示符

### 11.3 产物位置

```
.pio/build/esp32s3_yaokun/
├── bootloader.bin      # 0x0
├── partitions.bin      # 0x8000
├── boot_app0.bin       # 0xE000
├── firmware.bin        # 0x10000   ← 主程序
└── firmware.elf                ← 符号表，用于反查内存占用
```

## 十二、CLI 命令手册

ESP-FC 自带命令行接口，MSP 串口、USB CDC、Wi-Fi 软串口上都能敲。这是**不接地面站也能调试**的关键。

| 命令 | 作用 | 备注 |
|---|---|---|
| `status` | 打印状态摘要（飞行/解锁/传感器） | 最常用 |
| `dump` | 导出完整配置 | 备份 / 跨版本对比用 |
| `get <参数>` | 读单个参数 | 如 `get gyro_notch_count` |
| `set <参数> <值>` | 改单个参数 | 改完要 `save` 才生效 |
| `save` | 写入 Flash（NVS） | ⚠️ 持久化，慎用 |
| `defaults` | 恢复出厂 | ⚠️ 会清所有调参 |
| `bl` | 重启进下载模式 | 烧录失败时的救命命令 |
| `help` | 列出全部命令 |  |

> **💡 说明**
>
> `dump` 出来的文本请**存成文件**再比对。两版固件的 diff 能立刻告诉你 "是我改了参数还是环境变了"。这是排查"同一块板不同固件表现不同"的最快办法。

## 十三、故障排查

| 现象 | 最可能根因 | 处理 |
|---|---|---|
| 地面站完全搜不到板子 | env 选错，Flash/PSRAM 参数不匹配 | 换 `esp32s3_yaokun` 或 `_n4r2` 重烧 |
| 烧录后停在下载模式 | USB CDC 没枚举出 COM | 按住 BOOT 复位；或改用 UART0(43/44) |
| 上电无任何串口输出 | Flash/PSRAM 参数错 → panic | 对照 §2.1 核对 |
| 四个电机都不转 | **漏 `-DESPFC_DEV_PRESET_BRUSHED`** | 加上重新编译 |
| 只有一个电机转 | 电机顺序 / 接线错 | 核对 §2.2，应为 5/6/15/16 |
| 电机全转但力度极小 | 电压采样系数错 → 误判低压 | 核对 `ESPFC_ADC_SCALE = 2.0f/4096` |
| 显示电压只有一半 | 同上 | 同上 |
| 姿态不动 / 传感器失联 | IMU 片选错 | v1.0.1 默认 CS=42；V1 板 `set pin_spi_cs_0 17` → `save` |
| pitch/roll 双反相（抬头→低头、左倾→右倾） | 模块 180° 反插 / gyro_align 显式值残留 | 固定插装方向；`set gyro_align DEFAULT` → `save` 恢复自动分档（§7.2） |
| 换 IMU 模块后姿态错 90°/180° | NVS 固化了旧 `gyro_align` 显式值 | `set gyro_align DEFAULT` → `save` |
| 气压读数恰为一半（约 50 kPa） | GY-63 实贴 MS5607/AN520 系，公式用错 | `set baro_math -1`（CRC 自动判别）或 `1` |
| I2C 全灭（陀螺/气压全 FF） | 外接模块接线不良拉死总线 | 拔掉外接模块逐个排除；I2C 已降速 800 |
| **蜂鸣器常鸣** | **烧的是上游 esp32s3 固件** | 改烧 `esp32s3_yaokun` |
| SBUS 无信号 | 接收机没供电 / 未共地 | SBUS 是**单线**：信号线到 GPIO1 + 共地 |
| ELRS 接收机无数据 | 协议没设成 CRSF | 地面站把 UART2 协议改为 CRSF |
| 插桨后机身剧烈抖动 | 电机噪音进 IMU | CLI：`set gyro_notch_count 3` |
| 校准后姿态仍飘 | 校准没真正采到六面 | 重跑校准，逐面静止 ≥2 秒 |

## 十四、飞行能力边界

> **⛔ 危险**
>
> **★ 首次试飞前必读**

ESP-FC 是**纯姿态自稳 + 手动油门**架构。

| 能做 | 不能做 / 注意 |
|---|---|
| 姿态自稳（松杆自动回平） | **松杆不悬停** —— 姿态稳平但保持水平速度继续飘 |
| 三轴手动姿态控制 | **松油门就掉高度** |
| 接收机失联自动降油门 | 失联保护策略需在地面站确认（failsafe 模式） |
| 黑盒子记录与回放 | 无 GPS / 无地磁 / 无气压计 ⇒ **无定高、无定点、无航点** |

> **⚠️ 注意**
>
> **首次试飞建议**

1. **不装桨**先完成所有地面验证（电机顺序、IMU 方向、failsafe）
2. 装桨后**先做悬空台架测试**：低油门、用手轻扶、检查横滚/俯仰方向是否正确
3. 首次带桨飞行：**空旷场地、装保护圈、留足退让空间、低空慢速**
4. ⚠️ **横滚/俯仰方向写反是常见事故**：推杆机身应**向前倾**。方向反了请交换对应电调的 `MOT3`/`MOT4` 或调整混控顺序，**不要靠改 PID 修正**

> **💡 说明**
>
> **为什么本版不做定高？**
> 耀坤 S3 板上有 `GPIO3 / GPIO4` 的 I2C1 总线，xlsx 上标注给 VL53L1X 激光测距用，理论上可以做激光定高。但激光在 1 米以下对黑色地面和阳光环境很不稳定，且本版**未启用**该总线。等飞机基本能稳飞了再考虑，顺序不能反。

## 十五、与上游差异总表

| 编号 | 文件 | 改动 | 类型 |
|---|---|---|---|
| **Y1** | `Firmware/lib/Espfc/src/Target/TargetESP32s3YaoKun.h` | **新建**。耀坤 S3 板级引脚定义，逐条对齐 xlsx，含 8520 有刷电机适配 | 🔧 硬件适配（核心） |
| **Y2** | `Firmware/lib/Espfc/src/Target/Target.h` | **+3 行**：在最前面加 `#if defined(ESPFC_TARGET_YAOKUN)` 分支 | 🔧 硬件适配 |
| **Y3** | `Firmware/platformio.ini` | **新增两个 env**：`esp32s3_yaokun` / `esp32s3_yaokun_n4r2`（上游 env 未动） | 🔧 硬件适配 |
| **Y4** | 编译宏 `-DESPFC_DEV_PRESET_BRUSHED` | 输出协议强制 PWM（有刷电机） | 🔴 电机能否转动的关键 |
| **—** | `ESPFC_FEATURE_MASK` | 去掉 `FEATURE_DYNAMIC_FILTER`（0.3.0 已移除该掩码，改用 `gyro_notch_count` 配置项） | 🧩 版本适配 |
| **Y5** | `Device/Baro/BaroMS5611.hpp/.cpp` + 探测链接线（v1.0.1） | **新增 MS5611 气压计驱动**：I2C 自动探测、OSR4096、一阶+二阶补偿、MS5607/AN520 兼容片 CRC 自动判别（新参数 `baro_math`） | 🆕 设备驱动（v1.0.1） |
| **Y6** | `TargetESP32s3YaoKun.h` + `Hardware.cpp`（v1.0.1） | **陀螺仪 CS 默认改 42（PCB V2）**；IMU 安装朝向按总线自动分档 （I2C 6050→CW270 / SPI 6500→CW90，BF 配置器 3D 实测标定） | 🔧 板级默认值（v1.0.1） |

> **✅ 正确做法**
>
> **总结：算法层 0 行改动**
> 姿态解算（AHRS）、滤波、PID、混控、MSP 协议栈、地面站兼容性 —— **全部原样保留**。我们只改了"板级引脚"、"电机输出协议"与"设备驱动/板级默认值"这些硬件相关的事。

**耀坤S3 无人机 · ESP-FC 整理版　技术说明书　v1.0.1**  
上游项目：[rtlopez/esp-fc](https://github.com/rtlopez/esp-fc)（MIT，© Ramon Lopez）  
整理版：[github.com/YaoKunS/esp-fc](https://github.com/YaoKunS/esp-fc)　· 淘宝店铺 shop35432590.taobao.com  
v1.0：2026-10-18　·　v1.0.1：2026-11-26　·　本手册为新增内容，不替代上游任何版权声明
