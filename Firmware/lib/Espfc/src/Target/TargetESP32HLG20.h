#pragma once

/* ===========================================================================
 * TargetESP32HLG20.h
 * ---------------------------------------------------------------------------
 * 微辣火龙果 2.0 飞控 —— ESP-FC 板级定义（耀坤智联适配版）
 *
 * 上游项目：https://github.com/rtlopez/esp-fc  (MIT, (c) Ramon Lopez)
 * PCB 硬件设计：(c) 微辣火龙果（malagis / MildlySpicyDragon）
 *   OSHWHub 开源页：https://oshwhub.com/malagis/esp32-mini-plane
 * 本文件为耀坤智联（github.com/YaoKunS）新增的**板级适配**，
 * 未改动上游任何算法代码（滤波 / 混控 / PID / MSP 协议栈全部原样）。
 *
 * ---------------------------------------------------------------------------
 * 【板子是什么】
 *   微辣火龙果 2.0（PCB_HLG_V2）：ESP32 DevKit V1 经典片（30 针，WROOM，
 *   4MB Flash），8520 空心杯**有刷**四轴。与耀坤 S3 无人机是**同一系列、
 *   同一套 PCB 板框外形**（2026-11-27 用户确认），IMU 安装方向完全一致。
 *
 * 【引脚来源】与以下两份已实测在飞的参考实现逐脚一致，不重新推导：
 *   - flix 耀坤整理版 board.h 的 BOARD_HLG_V2 分板
 *     （D:\YaoKunS\Forks\flix\Firmware\build\hlg\sketch\board.h）
 *   - 耀坤自研飞控 config.h 的 PCB_HLG_V2 段
 *     （D:\YaoKunS\YaoKunDrone\YaoKun_Drone\config.h）
 *
 * 【🔴 经典 ESP32 的三条铁律（与 S3 版不同，逐条都会咬人）】
 *   1. 只有 GPIO0~39：凡 S3 版用到的 40 以上编号（如 V2 板 CS=42）在经典片上
 *      一律不能出现 —— 对 42 号脚 digitalWrite 属于越界写寄存器（未定义行为）。
 *      本文件所有引脚必须 <= 39，不用的功能写 -1。
 *   2. GPIO6~11 是内部 Flash 专用，30 针 DevKit 上绝对不能当 IO 用。
 *   3. ADC2（GPIO 0/2/4/12~15/25~27）与 Wi-Fi 互斥。本固件 Wi-Fi 常开
 *      （ESP-NOW 无线 MSP），**电池 ADC 必须落在 ADC1**（32/33/34/35/36/39），
 *      否则读数恒 0 → 误判低电 → 蜂鸣器无限急鸣。本板 ADC 接 GPIO35 = ADC1_CH7，
 *      恰好合规；将来改板也绝不能把 ADC 挪到 ADC2 组的脚上。
 *
 * 【S3 版踩过、本板同样适用的坑】
 *   - 排母 / SPI 座允许 180° 插装，插装方向一变 IMU 朝向档位就跟着变
 *     （表现为 pitch/roll 双反相）。建议在模块和排母上做对位标记。
 *   - IMU 贴装方向与 S3 完全一致 ⇒ 朝向自动分档（Hardware.cpp，按总线判）
 *     原样生效：I2C 6050 → CW270，SPI 6500 → CW90。本文件不写任何方向代码。
 * ========================================================================= */

/* ---------------------------------------------------------------------------
 * 遥控输入：SBUS 单线输入（GPIO4，与 flix / 自研的 rcRxPin 一致）
 *   不接接收机时地面站仍可正常连接（MSP 走 UART0 / Wi-Fi）。
 * ------------------------------------------------------------------------ */
#define ESPFC_INPUT
#define ESPFC_INPUT_PIN 4 // SBUS in（同 flix PIN_RC_RX / 自研 kSbusPin）

/* ---------------------------------------------------------------------------
 * 电机输出（8520 空心杯有刷，BRUSHED PWM 协议由 env 预设宏强制）
 *
 *   ⚠️ 注意：ESP-FC/Betaflight 的混控电机序号 ≠ 板上丝印 M1~M4！
 *   Betaflight QuadX 混控序号：1=右后(RR) 2=右前(FR) 3=左后(RL) 4=左前(FL)。
 *   板丝印是顺时针 M1 右前 / M2 右后 / M3 左后 / M4 左前（用户编号），
 *   两者差一个交叉。映射关系（flix board.h 与自研 config.h 一致）：
 *     OUTPUT_0 = 混控 1 = 右后 RR = GPIO27（丝印 M2）
 *     OUTPUT_1 = 混控 2 = 右前 FR = GPIO33（丝印 M1）
 *     OUTPUT_2 = 混控 3 = 左后 RL = GPIO26（丝印 M3）
 *     OUTPUT_3 = 混控 4 = 左前 FL = GPIO32（丝印 M4）
 *   🔴 耀坤 S3 上踩过同款坑：最初照丝印配，实机横滚/俯仰反向。
 *      首次上电仍务必拆桨做电机测试：推油门应对角两颗同转，
 *      偏航时正确的一对加速（见 Docs/火龙果2.0适配说明.md §验证）。
 *
 *   🔴 必须凑满 8 路（4~7 写 -1）：经典 ESP32 的 ESC 驱动走 RMT 外设，
 *      ESC_CHANNEL_COUNT = RMT_CHANNEL_MAX = 8，ModelConfig.h 里有
 *      static_assert 强制 OUTPUT_COUNT 与之一致 —— 只写 4 路直接编译失败。
 *      （上游 TargetESP32.h 同样是 8 路，4~7 置 -1。）
 * ------------------------------------------------------------------------ */
#define ESPFC_OUTPUT_COUNT 8
#define ESPFC_OUTPUT_0 27 // RR（丝印 M2）
#define ESPFC_OUTPUT_1 33 // FR（丝印 M1）
#define ESPFC_OUTPUT_2 26 // RL（丝印 M3）
#define ESPFC_OUTPUT_3 32 // FL（丝印 M4）
#define ESPFC_OUTPUT_4 -1 // 本板只有 4 路电机；RMT 剩余通道无硬件对应
#define ESPFC_OUTPUT_5 -1
#define ESPFC_OUTPUT_6 -1
#define ESPFC_OUTPUT_7 -1

/* ---------------------------------------------------------------------------
 * UART0 —— MSP 地面站口（DevKit 板载 CH340 USB 转串口），115200 8N1。
 *   GPIO1 = TX，GPIO3 = RX。经典 ESP32 的 U0 默认就接在板载 USB 桥上，
 *   刷机后唯一能立刻看到启动日志的通道，务必先接它。
 *   ⚠️ GPIO3 同时是 strapping 脚（U0RX），这是 DevKit 的固有接法，不用处理。
 * ------------------------------------------------------------------------ */
#define ESPFC_SERIAL_0
#define ESPFC_SERIAL_0_TX 1
#define ESPFC_SERIAL_0_RX 3
#define ESPFC_SERIAL_0_FN (SERIAL_FUNCTION_MSP)
#define ESPFC_SERIAL_0_BAUD (SERIAL_SPEED_115200)
#define ESPFC_SERIAL_0_BBAUD (SERIAL_SPEED_NONE)

/* ---------------------------------------------------------------------------
 * UART1 / UART2 —— 🔴 必须显式关掉，上游经典 ESP32 模板的默认值会打死电机：
 *   上游 TargetESP32.h 把 SERIAL_1 配在 TX33/RX32 —— 正好是本板的右前/左前
 *   电机脚！串口一初始化就把电机脚抢走，PWM 输出全废。
 *   SERIAL_2 配在 17/16 —— 是 I2C1 预留（VL53L1X），WROVER 模组上还会撞 PSRAM。
 *   本板没有空闲串口给 ELRS（flix/自研同样置 -1），全部显式 -1。
 * ------------------------------------------------------------------------ */
#define ESPFC_SERIAL_1
#define ESPFC_SERIAL_1_TX -1
#define ESPFC_SERIAL_1_RX -1
#define ESPFC_SERIAL_1_FN (SERIAL_FUNCTION_MSP)
#define ESPFC_SERIAL_1_BAUD (SERIAL_SPEED_115200)
#define ESPFC_SERIAL_1_BBAUD (SERIAL_SPEED_NONE)

#define ESPFC_SERIAL_2
#define ESPFC_SERIAL_2_TX -1
#define ESPFC_SERIAL_2_RX -1
#define ESPFC_SERIAL_2_FN (SERIAL_FUNCTION_RX_SERIAL)
#define ESPFC_SERIAL_2_BAUD (SERIAL_SPEED_115200)
#define ESPFC_SERIAL_2_BBAUD (SERIAL_SPEED_NONE)

/* ---------------------------------------------------------------------------
 * 经典 ESP32 **没有原生 USB CDC**（S3 才有），绝不定义 ESPFC_SERIAL_USB，
 * 否则编译报错/运行异常。调试日志走 UART0（板载 CH340，插 USB 就能看）。
 * ------------------------------------------------------------------------ */
#define ESPFC_SERIAL_DEBUG_PORT SERIAL_UART_0

/* ---------------------------------------------------------------------------
 * 软件串口（ESP-NOW 无线链路，走 Wi-Fi，不占引脚）
 *   与 S3 版体验一致：手机/电脑连上 ESP-FC 的 Wi-Fi 即可下发 CLI、看状态。
 *   ⚠️ 正因为 Wi-Fi 常开，上面的 ADC 必须用 ADC1 的 GPIO35（见文件头铁律 3）。
 * ------------------------------------------------------------------------ */
#define ESPFC_SERIAL_SOFT_0
#define ESPFC_SERIAL_SOFT_0_FN (SERIAL_FUNCTION_MSP)
#define ESPFC_SERIAL_SOFT_0_WIFI

#define ESPFC_SERIAL_REMAP_PINS

/* ---------------------------------------------------------------------------
 * SPI —— MPU6500 六轴（VSPI 默认脚，与 flix/自研/上游模板三方一致，不用改）
 *   ⚠️ ESP-Drone 的命名是 MOS/MIS：SDI=MOSI=23，SDO=MISO=19，别搞反。
 * ------------------------------------------------------------------------ */
#define ESPFC_SPI_0
#define ESPFC_SPI_0_SCK 18
#define ESPFC_SPI_0_MOSI 23
#define ESPFC_SPI_0_MISO 19

/* ---------------------------------------------------------------------------
 * 陀螺仪片选 GPIO5（NCS，内部上拉即可；strapping 高=正常启动，无冲突）。
 *   本板只有一个 SPI 从设备，无候选片选。
 *   🔴 绝不能沿用 S3 V2 板的 42：经典 ESP32 只有 GPIO0~39，对 42 写寄存器
 *      属于越界访问（见文件头铁律 1）。
 *   气压计走 I2C（见下），无 SPI 气压计片选。
 * ------------------------------------------------------------------------ */
#define ESPFC_SPI_CS_GYRO 5
#define ESPFC_SPI_CS_BARO -1

/* ---------------------------------------------------------------------------
 * I2C0 —— MPU6050 / MS5611 / BMP280 / HMC5883L·QMC5883L 排母
 *   SCL=22、SDA=21（经典片 I2C0 默认脚，与 ESP-Drone 官方引脚一致）。
 *   _SOFT 用软件实现的 EspWire 而不是硬件 I2C 驱动 —— 上游对所有 ESP32/S3
 *   板都这么写（硬件 I2C 外设与 Arduino 框架的已知冲突），照抄不要去掉。
 * ------------------------------------------------------------------------ */
#define ESPFC_I2C_0
#define ESPFC_I2C_0_SCL 22
#define ESPFC_I2C_0_SDA 21
#define ESPFC_I2C_0_SOFT

/* ---------------------------------------------------------------------------
 * 蜂鸣器（GPIO25，有源：给电就响）。ESP-FC 用它做上电/解锁/低电告警提示音。
 *   GPIO25 是 ADC2 组的脚，但只作**输出**，不碰 ADC，无 Wi-Fi 冲突。
 * ------------------------------------------------------------------------ */
#define ESPFC_BUZZER_PIN 25

/*
 * 【蜂鸣器极性 —— 只修上电常鸣，不动任何音效/灯效】
 *   火龙果 2.0 有源蜂鸣器同 S3 板：高电平触发（给 High 响、给 Low 不响）。
 *   ESP-FC 上游 BuzzerConfig.inverted 默认 true（为低电平触发板设计），
 *   会让 Buzzer::begin() 上电写 High → 蜂鸣器持续常鸣。
 *   覆盖为 0（同相）：begin() 上电写 Low，只把"不响的静止电平"摆正；
 *   需要响时写 High，上方 GPIO25 说明里的上电/解锁/低电告警等**所有音效
 *   照常播放**。
 * 🔴 beeperMask 及全部状态音效、LED 灯效保持上游原样，一字不改。
 *   本默认值即用户手动 `set pin_buzzer_invert 0` 实测效果的固化。
 */
#define ESPFC_BUZZER_INVERTED 0

/* ---------------------------------------------------------------------------
 * 按键 —— 本板没有独立功能按键。GPIO0 虽是 DevKit 的 BOOT 键，
 *   但它兼 strapping（低=下载模式），固件里当按键用容易误触发下载，
 *   参考实现也都未启用 ⇒ 置 -1，配对/校准改用 CLI 或地面站命令。
 * ------------------------------------------------------------------------ */
#define ESPFC_BUTTON_PIN -1

/* ---------------------------------------------------------------------------
 * 板载 LED（GPIO2，唯一一颗单色灯，拉电流接法：GPIO2 → 限流电阻 → LED → GND）
 *   ESP-FC 只驱动单色 LED，正好匹配。GPIO2 兼 strapping（低=下载模式），
 *   拉电流接法在复位期间呈高阻，不影响 boot。
 * ------------------------------------------------------------------------ */
#define ESPFC_LED_PIN 2

/* ---------------------------------------------------------------------------
 * 电池电压采样（GPIO35 = ADC1_CH7）
 *   ⚠️ 分压系数是**硬件决定的**：100K+100K 等值分压，Vpin = Vbat/2，
 *      Vbat = Vpin × 2 ⇒ ESPFC_ADC_SCALE = 2.0/4096（12 位 ADC 0~4095）。
 *      与 flix（kVbattDividerRatio 2.0）和自研（kVbattDividerRatio 2.0f）一致。
 *      填错后果：电压成倍偏差，低压告警永不响或一上电就响。
 *   🔴 GPIO34~39 是 input-only（无输出驱动、无内部上/下拉）。ESP-FC 的 ADC
 *      只调 analogRead(pin)、不做 pinMode，对仅输入脚安全；但也正因如此，
 *      这个脚永远不能挪作输出用。
 * ------------------------------------------------------------------------ */
#define ESPFC_ADC_VBAT
#define ESPFC_ADC_VBAT_PIN 35
#define ESPFC_ADC_SCALE (2.0f / 4096)

/* ---------------------------------------------------------------------------
 * 功能掩码（0.3.0 版）：FEATURE_RX_SERIAL → 启用串行接收机（SBUS / CRSF 等）
 *   ⚠️ 0.2.x 的 FEATURE_DYNAMIC_FILTER 在 0.3.0 已被移除（改成了
 *      gyro_notch_count 配置参数），拼进掩码会直接编译报错。
 *   ⚠️ 8520 有刷电机照样需要滤波：电机噪声一样会灌进 IMU。插桨后若地面站
 *      显示噪音大，CLI `set gyro_notch_count 3` 加陷波。
 * ------------------------------------------------------------------------ */
#define ESPFC_FEATURE_MASK (FEATURE_RX_SERIAL)

/* ---------------------------------------------------------------------------
 * IMU 采样率上限（Hz）：I2C 最高 2000（总线带宽限制），SPI 最高 4000。
 *   与上游经典 ESP32 模板一致。噪声大时可在地面站把 gyro 采样率降一档。
 * ------------------------------------------------------------------------ */
#define ESPFC_GYRO_I2C_RATE_MAX 2000
#define ESPFC_GYRO_SPI_RATE_MAX 4000

/* ---------------------------------------------------------------------------
 * 经典 ESP32 也是双核：姿态解算跑核心 1，Wi-Fi/ESP-NOW 跑核心 0。
 *   与 S3 版保持一致。若强制单核（-DESPFC_SINGLE_CORE）无线会掉帧。
 * ------------------------------------------------------------------------ */
#define ESPFC_MULTI_CORE
