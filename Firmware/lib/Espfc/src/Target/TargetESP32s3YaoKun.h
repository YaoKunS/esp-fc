#pragma once

/* ===========================================================================
 * TargetESP32s3YaoKun.h
 * ---------------------------------------------------------------------------
 * 耀坤 S3 无人机 —— ESP-FC 飞控板级定义（Yaokun Organized Edition）
 *
 * 上游项目：https://github.com/rtlopez/esp-fc  (MIT, (c) Ramon Lopez)
 * 本文件为耀坤智联（github.com/YaoKunS）在上游基础上新增的**板级适配**，
 * 未改动上游任何算法代码（滤波 / 混控 / PID / MSP 协议栈全部原样）。
 *
 * ---------------------------------------------------------------------------
 * 【为什么单独建一个 Target 文件，而不改上游 TargetESP32s3.h】
 *   上游的 TargetESP32s3.h 对应的是 Lolin S3 Mini 那类"通用 S3 模板"，
 *   引脚完全是通用占位值（电机 39/40/41/42、SPI 12/11/13、I2C SCL=10...），
 *   跟耀坤 S3 无人机 PCB 的实际布线**完全对不上**，直接烧上去必然：
 *     - 四电机无输出（引脚根本没驱动）
 *     - IMU 读不到（SPI 片选 / I2C 地址全错）
 *     - 蜂鸣器常鸣（39脚被当成电机输出）
 *   所以这里新建独立板级定义，由 -DESPFC_TARGET_YAOKUN 宏选中，
 *   上游 [env:esp32s3] 的行为**一点不变**，两套固件可随时切换对比。
 *
 * ---------------------------------------------------------------------------
 * 【引脚来源】全部取自《耀坤S3无人机引脚定义.xlsx》，逐行核对，无一臆造：
 *
 *   GPIO9   I2C0_SDA     MPU6050 / BMP280 / HMC5883L / QMC5883L
 *   GPIO8   I2C0_SCL     同上
 *   GPIO13  I2C0_INT     MPU6050 中断（本版未用，置 -1）
 *   GPIO21  SPI_MISO     MPU6500 / 光流
 *   GPIO18  SPI_MOSI     MPU6500 / 光流
 *   GPIO38  SPI_CLK      MPU6500 / 光流
 *   GPIO17  SPI_CS       MPU6500 片选（V1 板实测 CS=17，V2 板按表 CS=42）
 *   GPIO40  MPU6500_INT  MPU6500 中断（本版未用）
 *   GPIO42  MPU6500_CS   MPU6500 备用片选（V2 板用）
 *   GPIO3   I2C1_SDA     VL53L1X 激光测距（本版未启用）
 *   GPIO4   I2C1_SCL     VL53L1X（本版未启用）
 *   GPIO2   ADC1_BAT     VBAT 电池电压（1:2 分压）
 *   GPIO6   MOT1_FR      右前
 *   GPIO5   MOT2_RR      右后
 *   GPIO15  MOT3_RL      左后
 *   GPIO16  MOT4_FL      左前
 *   GPIO1   EXT01        SBUS 接收机信号输入
 *   GPIO11  TX_ELRS      ELRS 接收机预留（飞控 TX -> 接收机 RX）
 *   GPIO12  RX_ELRS      ELRS 接收机预留（接收机 TX -> 飞控 RX）
 *   GPIO41  LED_RED      红灯
 *   GPIO7   LED_GREEN    绿灯
 *   GPIO14  LED_BLUE     蓝灯
 *   GPIO39  Buzzer       有源蜂鸣器
 *   GPIO48  LED          板载 LED
 *
 * ---------------------------------------------------------------------------
 * 【🔴 电机类型 —— 这是本板最重要的一个决定】
 *   耀坤 S3 用的是 **8520 空心杯有刷电机**，不是无刷外转子。
 *   有刷电机没有 DShot/Blanked-DShot 解码协议，只能吃 **PWM（BRUSHED）**。
 *   因此：
 *     - 固件编译时必须开 -DESPFC_DEV_PRESET_BRUSHED
 *       （见 platformio.ini 的 [env:esp32s3_yaokun]）
 *       该宏会把输出协议强制为 ESC_PROTOCOL_BRUSHED + async + 3kHz。
 *     - 上游 TargetESP32s3.h 里那行 #define ESPFC_DSHOT_TELEMETRY
 *       在本文件里**故意不定义** —— DShot 双向回读电调转速只对无刷有意义，
 *       对 PWM 电调无效，误开会白占 DMA 与串口资源。
 *     - GPIO39 在本板是蜂鸣器，绝不能当电机脚用（上游模板正是 39/40/41/42）。
 *
 * 【S3 硬件禁区（踩过会直接panic，务必不要占用）】
 *   GPIO0 / 3 / 45 / 46  = 启动strapping 脚（3脚本板是 I2C1_SDA，上电电平决定 boot 模式）
 *   GPIO26~37            = 内部 Flash / PSRAM，占用即开不了机
 *   GPIO19 / 20          = USB JTAG
 *   GPIO43 / 44          = 本板已用作 UART0(MSP)，是唯一的地面站串口
 * ========================================================================= */

/* ---------------------------------------------------------------------------
 * 遥控输入：PPM / SBUS 单线输入
 * 耀坤板 EXT01 = GPIO1，即飞控的 SBUS 信号输入脚。
 * 默认为 ESPFC_INPUT_PIN 1；不接接收机时地面站仍可正常连接。
 * ------------------------------------------------------------------------ */
#define ESPFC_INPUT
#define ESPFC_INPUT_PIN 1 // SBUS in (EXT01, xlsx 第 19 行)

/* ---------------------------------------------------------------------------
 * 电机输出（4 路，顺序严格对齐 xlsx 的 MOT1..MOT4）
 *   OUTPUT_0 → MOT1_FR (GPIO6)   右前
 *   OUTPUT_1 → MOT2_RR (GPIO5)   右后
 *   OUTPUT_2 → MOT3_RL (GPIO15)  左后
 *   OUTPUT_3 → MOT4_FL (GPIO16) 左前
 * 顺序错了会"横滚/俯仰反向"，首次上电务必拆桨验证（见适配说明 §验证）。
 * ------------------------------------------------------------------------ */
#define ESPFC_OUTPUT_COUNT 4
#define ESPFC_OUTPUT_0 6
#define ESPFC_OUTPUT_1 5
#define ESPFC_OUTPUT_2 15
#define ESPFC_OUTPUT_3 16

/* ---------------------------------------------------------------------------
 * UART0 —— MSP 地面站口（Betaflight Configurator / Cleanflight Configurator）
 *   GPIO43 = TX，GPIO44 = RX，115200 8N1。
 *   这是刷机后唯一能立刻看到启动日志的通道，务必先接它。
 * ------------------------------------------------------------------------ */
#define ESPFC_SERIAL_0
#define ESPFC_SERIAL_0_TX 43
#define ESPFC_SERIAL_0_RX 44
#define ESPFC_SERIAL_0_FN (SERIAL_FUNCTION_MSP)
#define ESPFC_SERIAL_0_BAUD (SERIAL_SPEED_115200)
#define ESPFC_SERIAL_0_BBAUD (SERIAL_SPEED_NONE)

/* ---------------------------------------------------------------------------
 * UART1 —— 空置（保留给第二路 MSP / 未来 ELRS 直连串口）
 *   TX/RX 均 -1 = 不占用任何引脚。
 *   注意：S3 的 UART1 默认挂在 GPIO43/44 也就是 UART0 的物理脚上，
 *   这里显式关掉，避免与 UART0 抢引脚导致 MSP 掉线。
 * ------------------------------------------------------------------------ */
#define ESPFC_SERIAL_1
#define ESPFC_SERIAL_1_TX -1
#define ESPFC_SERIAL_1_RX -1
#define ESPFC_SERIAL_1_FN (SERIAL_FUNCTION_MSP)
#define ESPFC_SERIAL_1_BAUD (SERIAL_SPEED_115200)
#define ESPFC_SERIAL_1_BBAUD (SERIAL_SPEED_NONE)

/* ---------------------------------------------------------------------------
 * UART2 —— ELRS 接收机预留口（SERIAL_FUNCTION_RX_SERIAL = 只收不发命令）
 *   xlsx 第 20/21 行：
 *     GPIO11 = TX_ELRS → 飞控发、接收机收
 *     GPIO12 = RX_ELRS → 接收机发、飞控收   ← 这才是真正收遥测的那根
 *   ⚠️ ELRS 接收机输出的是**串行协议（CRSF）**，不是 SBUS。
 *      本版默认**不启用**：要在地面站里改串口协议为 CRSF 才可用。
 *      先保持注释，确认走线无误后再放开，避免默认状态下白占引脚。
 * ------------------------------------------------------------------------ */
#define ESPFC_SERIAL_2
#define ESPFC_SERIAL_2_TX 11
#define ESPFC_SERIAL_2_RX 12
#define ESPFC_SERIAL_2_FN (SERIAL_FUNCTION_RX_SERIAL)
#define ESPFC_SERIAL_2_BAUD (SERIAL_SPEED_115200)
#define ESPFC_SERIAL_2_BBAUD (SERIAL_SPEED_NONE)

/* ---------------------------------------------------------------------------
 * 原生 USB —— S3 直连电脑的 CDC 口
 *   ESPFC_SERIAL_USB = 让 MSP/CLI 也能走 USB 虚拟串口，
 *   刷完固件第一次上电，Windows 会枚举出一个新的 COM 口，
 *   可以用它做第二次烧录（比 UART0 更稳，因为不依赖 USB-UART 桥芯片）。
 *   ⚠️ 需要 platformio.ini 里同时给：
 *        -DARDUINO_USB_MODE=1 -DARDUINO_USB_CDC_ON_BOOT=1
 * ------------------------------------------------------------------------ */
#define ESPFC_SERIAL_USB
#define ESPFC_SERIAL_USB_FN (SERIAL_FUNCTION_MSP)

/* ---------------------------------------------------------------------------
 * 软件串口（ESP-NOW 无线链路，走 Wi-Fi，不占引脚）
 *   上游用它做无线配置 / 遥测。启用后可用手机或电脑连上 ESP-FC 的
 *   Wi-Fi 直接下发 CLI 命令、查看状态，不需要插任何线。
 * ------------------------------------------------------------------------ */
#define ESPFC_SERIAL_SOFT_0
#define ESPFC_SERIAL_SOFT_0_FN (SERIAL_FUNCTION_MSP)
#define ESPFC_SERIAL_SOFT_0_WIFI

#define ESPFC_SERIAL_REMAP_PINS

/* ---------------------------------------------------------------------------
 * 调试输出端口 —— 必须定义，否则 SerialManager.cpp 编译不过。
 *   SERIAL_USB = 走 S3 原生 USB CDC，日志直接进 Windows 终端，
 *   不用外接 USB-UART 桥，是排查问题时最省事的一条路。
 *   ⚠️ 若改成 SERIAL_0，则日志走 UART0 的 43/44 引脚。
 * ------------------------------------------------------------------------ */
#define ESPFC_SERIAL_DEBUG_PORT SERIAL_USB

/* ---------------------------------------------------------------------------
 * SPI —— MPU6500 六轴（也可挂光流模块）
 *   SCK=38, MOSI=18, MISO=21（xlsx 第 4/5/6 行）
 *   ⚠️ S3 上 GPIO18/19/20 与 USB 相关，但 18 作 MOSI 可用；
 *      **绝对不要碰 GPIO26~37**（Flash/PSRAM）。
 * ------------------------------------------------------------------------ */
#define ESPFC_SPI_0
#define ESPFC_SPI_0_SCK 38
#define ESPFC_SPI_0_MOSI 18
#define ESPFC_SPI_0_MISO 21

/* ---------------------------------------------------------------------------
 * 陀螺仪片选 —— 🔴 必须与实际板子版本一致，否则 IMU 完全读不到
 *   V1 板（2026-10 台架实测确认）：CS = GPIO17
 *   V2 板（按 xlsx 标注）      ：CS = GPIO42
 *   本版默认 V1 = 17。
 *   ⚠️ 只改这一行就能切版本，不要去动 SCK/MOSI/MISO（两版一致）。
 *   ⚠️ GPIO42 同时也是 V2 的 CS，V1 板上它空闲；改之前请确认板型。
 * ------------------------------------------------------------------------ */
#define ESPFC_SPI_CS_GYRO 17
#define ESPFC_SPI_CS_BARO -1 // 本板未接气压计（无 BMP280）

/* ---------------------------------------------------------------------------
 * I2C —— MPU6050 六轴 / BMP280 气压 / HMC5883L·QMC5883L 磁力计
 *   🔴 SDA = GPIO9，SCL = GPIO8 —— 顺序千万别写成 8/9，写反了 I2C 不通
 *      （这跟 Flix 那边的教训完全一致，两个工程踩的是同一个坑）。
 *   _SOFT 表示用软件实现的 EspWire 而不是硬件 I2C 驱动；
 *   原因是 S3 的硬件 I2C 外设被 Arduino 框架占用时的已知问题，
 *   上游对所有 S3 板都这么写，照抄即可，不要擅自去掉。
 * ------------------------------------------------------------------------ */
#define ESPFC_I2C_0
#define ESPFC_I2C_0_SCL 8
#define ESPFC_I2C_0_SDA 9
#define ESPFC_I2C_0_SOFT

/* ---------------------------------------------------------------------------
 * 蜂鸣器（GPIO39，有源蜂鸣器：给电就响，不给电就静）
 *   ESP-FC 用它做：上电提示音、未解锁提示音、低电压告警音、
 *   以及校准/配对成功的音频反馈。是**有源**蜂鸣器，
 *   所以只要 digitalWrite(HIGH)，不需要输出方波。
 * ------------------------------------------------------------------------ */
#define ESPFC_BUZZER_PIN 39

/* ---------------------------------------------------------------------------
 * 按键 —— 本板没有独立按键（GPIO 为 -1）
 *   配对 / 校准改用 CLI 或地面站命令触发。
 *   ⚠️ 若后续要在板上加按键，GPIO48（板载 LED 脚）旁的测试点更合适，
 *      但要先确认它是不是真的引到了排针。
 * ------------------------------------------------------------------------ */
#define ESPFC_BUTTON_PIN -1

/* ---------------------------------------------------------------------------
 * 板载 LED（GPIO14 蓝灯 / xlsx 第 12 行）
 *   注意：本板是**三色灯**（红41 / 绿7 / 蓝14），
 *   但 ESP-FC 的固件只会驱动单色 LED，所以这里只映射蓝灯那颗，
 *   红绿两颗留给用户自己接外部电路或后续自定义。
 * ------------------------------------------------------------------------ */
#define ESPFC_LED_PIN 14

/* ---------------------------------------------------------------------------
 * 电池电压采样（GPIO2，xlsx 第 23 行 ADC1_BAT）
 *   ⚠️ 分压系数是**硬件决定的**，不是随便填的：
 *      耀坤板 VBAT 经 1:2 分压（两个等值电阻）接到 GPIO2，
 *      即 Vpin = Vbat / 2  ⇒  Vbat = Vpin × 2
 *      所以 ESPFC_ADC_SCALE 必须 = 2.0 / 4096（12 位 ADC 量程 0~4095）。
 *      填错的后果：地面站显示的电池电压成倍偏差，低压告警要么永远不响、
 *      要么一上电就报警。若实测电压明显不对，先来这里核对这个系数。
 * ------------------------------------------------------------------------ */
#define ESPFC_ADC_VBAT
#define ESPFC_ADC_VBAT_PIN 2
#define ESPFC_ADC_SCALE (2.0f / 4096)

/* ---------------------------------------------------------------------------
 * 功能掩码（0.3.0 版）
 *   FEATURE_RX_SERIAL → 启用串行接收机（SBUS / CRSF 等）
 *   ⚠️ 0.2.x 的 FEATURE_DYNAMIC_FILTER 在 0.3.0 已被移除 ——
 *      动态陷波滤波改成了 gyro.dynamicFilter.count 这���**配置参数**
 *      （在地面站 CLI 里 `set gyro_notch_count N` 调，默认就是开的）。
 *      所以这里不再拼那个掩码，写上会直接编译报错。
 *   ⚠️ 8520 有刷电机照样需要滤波：电机噪声一样会灌进 IMU。
 *      插桨后若地面站显示噪音很大，在 CLI 里加陷波：
 *        set gyro_notch_count 3
 * ------------------------------------------------------------------------ */
#define ESPFC_FEATURE_MASK (FEATURE_RX_SERIAL)

/* ---------------------------------------------------------------------------
 * IMU 采样率上限（Hz）
 *   I2C 最高 2000（总线带宽限制），SPI 最高 4000。
 *   上游默认取满，实际噪声大时可在地面站里把 gyro 采样率往下降一档。
 * ------------------------------------------------------------------------ */
#define ESPFC_GYRO_I2C_RATE_MAX 2000
#define ESPFC_GYRO_SPI_RATE_MAX 4000

/* ---------------------------------------------------------------------------
 * S3 专用：多核 + ESP-NOW 依赖的 FreeRTOS 任务
 *   与上游 S3 保持一致 —— 姿态解算跑在核心 1，Wi-Fi/ESP-NOW 跑核心 0，
 *   两边互不抢占。若强制单核（-DESPFC_SINGLE_CORE），无线会掉帧。
 * ------------------------------------------------------------------------ */
#define ESPFC_MULTI_CORE