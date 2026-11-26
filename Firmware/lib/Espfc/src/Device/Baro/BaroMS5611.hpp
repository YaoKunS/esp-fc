#pragma once

/* ===========================================================================
 * BaroMS5611.hpp
 * ---------------------------------------------------------------------------
 * MS5611 高精度气压计驱动（耀坤智联新增，yaokun-organized）
 *
 * 【为什么要有这个文件】
 *   上游 esp-fc 只实现了 BMP085 / BMP280 / SPL06 三款气压计，
 *   BaroDevice.hpp 里的 BARO_MS5611 枚举只是个占位，没有任何驱动代码。
 *   MS5611 是 PXE/Pixhawk 生态里最常见的高分辨率气压计（0.1 m 分辨率），
 *   耀坤适配的 MS5611 模块走 I2C，所以补上这个驱动。
 *
 * 【硬件要点（MS5611-01BA03，I2C 模式）】
 *   - 地址：CSB 接 GND → 0x77（最常见的模块接法）；
 *           CSB 接 VDD → 0x76。两个都试，谁应答用谁。
 *   - 无寄存器概念：所有"写"都是单字节命令（复位/启动转换/PROM 读/ADC 读），
 *     所以 bus->write(addr, cmd, 0, nullptr) 就是发一条命令。
 *   - PROM：0xA0~0xAE 共 8 个 16 位字（工厂标定系数 + CRC），掉电不丢。
 *   - 转换：启动 D1(气压)/D2(温度) 转换命令后，必须等足够时间才能读 ADC。
 *     本驱动选 OSR=4096（最高过采样，噪声最小），转换时间最长 9.04ms
 *     （数据手册 Table 3），getDelay 返回 9500us 留了余量。
 *
 * 【与 BaroSensor 状态机的对接（关键，读这里才能看懂时序）】
 *   BaroSensor::read() 的状态机是：
 *     setMode(TEMP)  → 等 getDelay(TEMP)  → readTemperature()
 *     setMode(PRESS) → 等 getDelay(PRESS) → readPressure()
 *   所以：
 *     - setMode() 职责 = 发"启动转换"命令（MS5611 没有 BMP280 那种连续模式）；
 *     - readTemperature() 职责 = 读 ADC 里的 D2 并算出温度（同时缓存 dT）；
 *     - readPressure()    职责 = 读 ADC 里的 D1，用上一次缓存的 dT 算气压。
 *   这与 BMP280/SPL06 驱动"setMode 什么都不做、read 里连读带算"的写法不同，
 *   但对状态机来说行为完全兼容。
 *
 * 【补偿公式来源】
 *   TE Connectivity《MS5611-01BA03 数据手册》压力换算一节（一阶 + 二阶修正）。
 *   一阶在常温下误差 ~0.2hPa，二阶修正低温/低压下的非线性，两段都实现了。
 *   输出单位与 BMP280 驱动对齐：readTemperature() → °C；
 *   readPressure() → Pa（BaroSensor::toAltitude() 用 101325 Pa 海平面基准）。
 * =========================================================================== */

#include "Debug_Espfc.h"
#include "Device/BaroDevice.hpp"

namespace Espfc::Device::Baro {

class BaroMS5611 : public BaroDevice
{
public:
  /* PROM 标定系数（数据手册 Table 6）：
   *   w0 = 厂商/序列号 + 低 4 位是 CRC
   *   w1 = C1 压力灵敏度 sens
   *   w2 = C2 压力偏移 off
   *   w3 = C3 温度系数（sens）
   *   w4 = C4 温度系数（off）
   *   w5 = C5 参考温度 TREF
   *   w6 = C6 温度系数（TEMP）
   *   w7 = 保留（原厂一般写 0x0000） */
  struct CalibrationData
  {
    uint16_t w[8];
  };

  int begin(Hal::BusDevice* bus) final;          // 依次试 0x77 / 0x76
  int begin(Hal::BusDevice* bus, uint8_t addr) final; // 指定地址初始化

  BaroDeviceType getType() const final;          // 返回 BARO_MS5611

  float readTemperature() final;                 // °C（读 D2、算温度、缓存 dT）
  float readPressure() final;                    // Pa（读 D1、用缓存 dT 算气压）

  void setMode(BaroDeviceMode mode) final;       // 发启动转换命令
  int getDelay(BaroDeviceMode mode) const final; // 转换等待时间（微秒）

  bool testConnection() final;                   // 探测：PROM C1 合理性检查

protected:
  int writeCmd(uint8_t cmd);                     // 发单字节命令（MS5611 无寄存器）
  int readProm();                                // 读 8 个 PROM 字 + CRC 校验
  static int crc4(uint16_t n_prom[8]);           // 数据手册 AN520 的 CRC-4 算法

  CalibrationData _cal;      // PROM 标定系数
  int64_t _dt = 0;           // dT = D2 - C5*2^8（温度差分，气压补偿要用，必须缓存）
  int32_t _raw_pressure = 0; // 最近一次 D1 原始值
  int32_t _raw_temp = 0;     // 最近一次 D2 原始值
  bool _promValid = false;   // PROM 是否读到且 CRC 通过（用于自动判别数学模式）
  int8_t _mathMode = -1;     // 压力补偿模式：0=MS5611 datasheet / 1=AN520(MS5607) / -1=按CRC自动

public:
  /* ------------------------------------------------------------------
   * setMathMode：选择压力补偿公式
   *   背景：GY-63 模块上常贴 MS5607 或按 AN520 系数编码的兼容芯片，
   *   其 C1~C4 与 MS5611 datasheet 差 2 倍，用 datasheet 公式算出的气压
   *   恰好只有一半（RobTillaart/MS5611 issue#33 同款现象）。
   *   mode: -1=自动（CRC 通过→datasheet；CRC 不过→AN520）
   *          0=强制 datasheet（真品 MS5611）  1=强制 AN520（MS5607/兼容）
   * ------------------------------------------------------------------ */
  void setMathMode(int8_t mode) { _mathMode = mode; }

  /* ---- 诊断接口（临时排障用）：把内部原始值暴露给上层日志/调试通道 ----
   * 用途：气压读数异常时，上层（Hardware/BaroSensor）可打印 PROM 与 raw ADC，
   *       与数据手册公式手算对照，定位是 PROM 读错还是公式/命令错。 */
  const CalibrationData& dbgCal() const { return _cal; }
  bool dbgPromValid() const { return _promValid; }
  int32_t dbgRawD1() const { return _raw_pressure; }
  int32_t dbgRawD2() const { return _raw_temp; }
  int64_t dbgDt() const { return _dt; }
};

} // namespace Espfc::Device::Baro
