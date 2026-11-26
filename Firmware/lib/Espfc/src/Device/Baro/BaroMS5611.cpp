/* ===========================================================================
 * BaroMS5611.cpp —— MS5611 气压计驱动实现（耀坤智联新增）
 * ---------------------------------------------------------------------------
 * 协议细节全部来自 MS5611-01BA03 数据手册：
 *   - 命令表（Table 5）：
 *       0x1E 复位（耗时最长 2.8ms，这里等 10ms 留足余量）
 *       0xA0+i*2 读 PROM 第 i 个字（16 位，大端）
 *       0x40+OSR<<2 启动 D1（气压）转换；0x50+OSR<<2 启动 D2（温度）转换
 *       0x00 读 ADC 结果（3 字节，大端：高 8 位 | 中 8 位 | 低 8 位）
 *   - OSR=4096 时 D1/D2 转换最长 9.04ms（Table 3）→ getDelay 返回 9500us。
 *
 * 🔴 踩坑预警：MS5611 是"命令式"器件，没有寄存器映射。
 *    如果把命令字节当"寄存器地址"后跟数据写（像 BMP280 那样 write(addr,reg,1,&val)），
 *    多出来的数据字节会被芯片当成新命令，行为错乱。
 *    所以所有命令一律 writeCmd()：bus->write(addr, cmd, 0, nullptr) 只发一个字节。
 * =========================================================================== */

#include "BaroMS5611.hpp"
#include "Hal/Time.hpp" // delay()：复位后的等待用（与 BaroSPL06.cpp 同款做法，不直接用 Arduino API 保持 HAL 层一致）

namespace Espfc::Device::Baro {

/* ------------------------------------------------------------------
 * I2C 地址与命令常量（数据手册 §5.2：CSB=GND→0x77，CSB=VDD→0x76）
 * 市售 GY-63/GY-65 模块 CSB 都拉低，默认 0x77，故先试 0x77。
 * ------------------------------------------------------------------ */
static const uint8_t MS5611_ADDR_FIRST  = 0x77;
static const uint8_t MS5611_ADDR_SECOND = 0x76;

static const uint8_t MS5611_CMD_RESET     = 0x1E; // 复位，随后要等 ≥2.8ms
static const uint8_t MS5611_CMD_ADC_READ  = 0x00; // 读 ADC（3 字节结果）
static const uint8_t MS5611_CMD_PROM_BASE = 0xA0; // PROM 读命令基址，0xA0+i*2

/* 启动转换命令 = 基址 + 过采样率档位 << 1
 * 🔴 手册 Table 5 的命令是每档 +2，不是 +2 的幂！
 *    D1: 0x40/0x42/0x44/0x46/0x48（256/512/1024/2048/4096 次）
 *    D2: 0x50/0x52/0x54/0x56/0x58
 *    🔴 踩坑记录：最初写成 档位<<2，结果 D1 4096 档发成了 0x50 ——
 *       那其实是"D2 温度转换"命令，温度 ADC 被当成气压算，
 *       实测气压虚高 4.6%（101.3→106.2 kPa）且随温度同步漂移。
 *       修正为 <<1 后气压回到真实值。 */
static const uint8_t MS5611_CMD_CONV_D1 = 0x40; // D1 = 数字气压（+档位*2）
static const uint8_t MS5611_CMD_CONV_D2 = 0x50; // D2 = 数字温度（+档位*2）
static const uint8_t MS5611_OSR_SHIFT   = 4 << 1; // 档位 4 = OSR 4096 → D1=0x48 / D2=0x58

/* ------------------------------------------------------------------
 * begin(bus)：不带地址的探测入口，先试 0x77（最常见模块接法）再试 0x76
 * 返回：1 = 某个地址上探测成功；0 = 两个地址都没应答/校验不过
 * ------------------------------------------------------------------ */
int BaroMS5611::begin(Hal::BusDevice* bus)
{
  return begin(bus, MS5611_ADDR_FIRST) ? 1 : begin(bus, MS5611_ADDR_SECOND) ? 1 : 0;
}

/* ------------------------------------------------------------------
 * begin(bus, addr)：在指定地址上初始化
 * 流程：探测 → 复位 → 读 PROM（标定系数 + CRC 校验）
 * 返回：1 = 成功；0 = 探测失败
 * 注意：探测失败直接返回 0，不发复位 —— 避免总线上挂着别的
 *       器件时把别人当 MS5611 乱敲命令（探测放在最前面就是为这个）。
 * ------------------------------------------------------------------ */
int BaroMS5611::begin(Hal::BusDevice* bus, uint8_t addr)
{
  setBus(bus, addr);

  if (!testConnection()) return 0;

  // 复位后内部标定系数会重新从 PROM 加载，这是手册要求的上电序列
  writeCmd(MS5611_CMD_RESET);
  delay(10); // 手册要求 ≥2.8ms，取 10ms 留足余量（慢一步不影响探测吞吐）

  _promValid = (readProm() == 1);
  return 1;
}

BaroDeviceType BaroMS5611::getType() const
{
  return BARO_MS5611;
}

/* ------------------------------------------------------------------
 * setMode：发"启动转换"命令（对接 BaroSensor 状态机的等待-读取节奏）
 *   BARO_MODE_TEMP → 启动 D2（温度）转换
 *   BARO_MODE_PRESS→ 启动 D1（气压）转换
 * 写失败静默返回：BaroSensor 下一轮读 ADC 会读到旧值/0，不会崩；
 * 总线断线属于硬件问题，靠 state.i2cErrorCount 统计即可。
 * ------------------------------------------------------------------ */
void BaroMS5611::setMode(BaroDeviceMode mode)
{
  switch (mode)
  {
    case BARO_MODE_TEMP:
      writeCmd(MS5611_CMD_CONV_D2 | MS5611_OSR_SHIFT);
      break;
    default:
      writeCmd(MS5611_CMD_CONV_D1 | MS5611_OSR_SHIFT);
      break;
  }
}

/* ------------------------------------------------------------------
 * getDelay：转换等待时间（微秒，BaroSensor 用 micros() 比较）
 * OSR=4096 手册标称最长 9.04ms → 9500us 留余量。
 * 温度/气压同过采样，等待时间相同。
 * ------------------------------------------------------------------ */
int BaroMS5611::getDelay(BaroDeviceMode mode) const
{
  (void)mode;
  return 9500;
}

/* ------------------------------------------------------------------
 * readTemperature：读 ADC 里的 D2，计算温度（°C）并缓存 dT
 * 返回：摄氏度；总线异常时返回 0（与 BMP280 驱动行为一致）
 *
 * 一阶公式（手册）：
 *   dT   = D2 - C5 * 2^8
 *   TEMP = 2000 + dT * C6 / 2^23     （单位 0.01°C，即"厘度"）
 * dT 必须缓存成成员变量：readPressure() 算气压要用它，
 * 而 BaroSensor 状态机是"读温度→读气压"交替调用，正好接得上。
 * ------------------------------------------------------------------ */
float BaroMS5611::readTemperature()
{
  // 读 3 字节 ADC：bus->read() 先发命令字节再读，对 MS5611 恰好等价于
  // "发 0x00 读结果命令 → 读 3 字节" 的手册时序
  uint8_t buf[3] = {};
  if (_bus->read(_addr, MS5611_CMD_ADC_READ, 3, buf) != 3) return 0.0f;
  _raw_temp = (buf[0] << 16) | (buf[1] << 8) | buf[2];
  _raw_temp &= 0x00FFFFFF; // ADC 固定 24 位，防符号位以外的高位脏数据

  // int64 全程运算：dT*2^23 量级会溢出 32 位（手册明确警告）
  _dt = (int64_t)_raw_temp - ((int64_t)_cal.w[5] << 8);
  int64_t temp = 2000 + ((_dt * (int64_t)_cal.w[6]) >> 23); // 0.01°C

  return (float)temp / 100.0f;
}

/* ------------------------------------------------------------------
 * readPressure：读 ADC 里的 D1，用最近缓存的 dT 计算气压（Pa）
 * 返回：帕斯卡；总线异常时返回 0
 *
 * 两种压力系数编码（🔴 这是 GY-63 模块的深坑，务必读这段）：
 *   MS5611 原装芯片按 datasheet 公式标定（mode 0）。
 *   市面大量模块（含本块 GY-63）贴的是 MS5607 / 按 AN520 应用笔记
 *   系数编码的兼容芯片（mode 1），C1~C4 与 datasheet 差 2 倍——
 *   拿错公式算出的气压恰好只有一半（实测 50.8 kPa vs 101.8 kPa）。
 *   温度系数 C5/C6 两种芯片相同，所以温度总是准的。
 *   参考实现：RobTillaart/MS5611 库 initConstants(mathMode)，issue#33。
 *   模式选择见函数内注释（_mathMode，CLI baro_math 可手动覆盖）。
 *
 * datasheet 一阶公式（mode 0）：
 *   off  = C2*2^16 + (C4*dT)/2^7
 *   sens = C1*2^15 + (C3*dT)/2^8
 *   P    = (D1*sens/2^21 - off) / 2^15   （单位 Pa）
 * AN520/MS5607 版（mode 1）：off/sens 各项移位量全部 +1（等效 ×2）。
 *
 * 二阶修正（手册，温度 < 20°C 时启用；<-15°C 再加一项）：
 *   低温下 sens/off 对温度呈非线性，不修正冬季室外会漂好几个 hPa，
 *   对定高而言就是十几米的假高度变化，必须做。
 * ------------------------------------------------------------------ */
float BaroMS5611::readPressure()
{
  uint8_t buf[3] = {};
  if (_bus->read(_addr, MS5611_CMD_ADC_READ, 3, buf) != 3) return 0.0f;
  _raw_pressure = (buf[0] << 16) | (buf[1] << 8) | buf[2];
  _raw_pressure &= 0x00FFFFFF;

  // 先按一阶公式重算当前温度（厘度），二阶修正要用它
  int64_t temp = 2000 + ((_dt * (int64_t)_cal.w[6]) >> 23);

  // ---- 压力补偿模式：自动判别只做一次，结论存回 _mathMode ----
  // 判据：用（修复后的）正确 CRC-4 算法校验 PROM。
  //   通过 → PROM 按官方规范烧写 → datasheet 公式（mode 0）；
  //   不通过 → 兼容芯片/AN520 系数 → AN520 公式（mode 1）。
  // 真品 MS5607（CRC 会通过）会被误判成 mode0，此时用 CLI baro_math 1 手动指定。
  int8_t mode = _mathMode;
  if (mode < 0) mode = _promValid ? 0 : 1;

  // off/sens：64 位运算防溢出；移位量随模式切换（AN520 版全部大 1 位，见函数头注释）
  int64_t off, sens;
  if (mode == 1)
  {
    off  = ((int64_t)_cal.w[2] << 17) + (((int64_t)_cal.w[4] * _dt) >> 6);
    sens = ((int64_t)_cal.w[1] << 16) + (((int64_t)_cal.w[3] * _dt) >> 7);
  }
  else
  {
    off  = ((int64_t)_cal.w[2] << 16) + (((int64_t)_cal.w[4] * _dt) >> 7);
    sens = ((int64_t)_cal.w[1] << 15) + (((int64_t)_cal.w[3] * _dt) >> 8);
  }

  // ---- 二阶修正（手册补偿表 + iNav 同款实现）----
  int64_t t2 = 0, off2 = 0, sens2 = 0;
  if (temp < 2000) // 温度低于 20°C（temp 单位是 0.01°C）
  {
    t2    = (3 * _dt * _dt) >> 33;  // 3*dT²/2^33
    int64_t tl = temp - 2000;       // 与 20°C 的差（负数，平方后无符号问题）
    off2  = (61 * tl * tl) >> 4;    // 61*(T-2000)²/2^4
    sens2 = (29 * tl * tl) >> 4;    // 29*(T-2000)²/2^4
    if (temp < -1500) // 温度低于 -15°C，再补一项更陡的非线性
    {
      int64_t tl2 = temp + 1500;
      off2  += 17 * tl2 * tl2;
      sens2 += 7 * tl2 * tl2;
    }
  }
  temp  -= t2;   // 修正后的温度（厘度）
  off   -= off2;
  sens  -= sens2;

  // 气压：Pa。P = ((D1*sens)/2^21 - off) / 2^15。
  // 🔴 括号必须显式写：C++ 里 ">> 21 - off" 会被解析成 ">> (21-off)"，
  //    加法优先级高于移位，少一对括号结果全错（本工程已在此留注释防回归）。
  int64_t p = ((((int64_t)_raw_pressure * sens) >> 21) - off) >> 15;

  return (float)p;
}

/* ------------------------------------------------------------------
 * testConnection：探测芯片是否在线
 * 判据：读 PROM 第 1 字（C1 压力灵敏度），必须是合理的非零值。
 *   - 真芯片 C1 恒在 10000~65000 区间（几十 kPa 量程的标定系数）；
 *   - 总线上没这颗芯片 → 读回 0 或 0xFFFF（NACK/超时）→ 判失败；
 *   - 比起 CRC 校验更宽容：个别兼容芯片 CRC 位不规范但系数完全可用。
 * 顺带把 C1 低 8 位存进 chipId，devinfo 命令可用来区分模块个体。
 * ------------------------------------------------------------------ */
bool BaroMS5611::testConnection()
{
  uint8_t buf[2] = {};
  // 读 PROM 字 1（C1）：bus->read 先发 0xA2 命令再读 2 字节
  if (_bus->read(_addr, MS5611_CMD_PROM_BASE | 0x02, 2, buf) != 2) return false;
  uint16_t c1 = ((uint16_t)buf[0] << 8) | buf[1];
  if (c1 == 0x0000 || c1 == 0xFFFF) return false; // 无应答 / 总线悬空

  setChipId((uint8_t)(c1 & 0xFF));
  return true;
}

/* ------------------------------------------------------------------
 * readProm：读 8 个 PROM 字，做 CRC-4 校验
 * 返回：1 = CRC 通过；0 = CRC 不通过（芯片仍可用，只是存疑）
 * CRC 只作为诊断信息（_promValid），不拦截初始化 —— 参见 testConnection 注释。
 * ------------------------------------------------------------------ */
int BaroMS5611::readProm()
{
  for (int i = 0; i < 8; i++)
  {
    uint8_t buf[2] = {};
    if (_bus->read(_addr, MS5611_CMD_PROM_BASE | (i * 2), 2, buf) != 2) return 0;
    _cal.w[i] = ((uint16_t)buf[0] << 8) | buf[1];
  }

  // CRC-4 校验（AN520）：副本上算，别动 _cal 原始数据
  uint16_t prom[8];
  for (int i = 0; i < 8; i++) prom[i] = _cal.w[i];
  int crc = crc4(prom);
  int stored = _cal.w[0] & 0x0F; // CRC 存在字 0 的低 4 位

  return (crc == stored) ? 1 : 0;
}

/* ------------------------------------------------------------------
 * crc4：MS5611 PROM 的 CRC-4 校验算法（TE 应用笔记 AN520 原样实现）
 * 参数 n_prom：8 个 16 位字的副本（调用方负责拷贝）
 * 返回：计算出的 CRC（应与 PROM 字 0 低 4 位相等）
 * 算法说明：逐字节异或进 16 位余数寄存器，多项式 0x3000（即 x^12+x^11+x^3+1），
 * 最后取余数高 4 位。
 * ------------------------------------------------------------------ */
int BaroMS5611::crc4(uint16_t n_prom[8])
{
  uint16_t n_rem = 0x0000;

  n_prom[0] &= 0x0FFF; // 参与计算时把 CRC 位清零
  n_prom[7] = 0x0000;  // AN520 约定：字 7 固定按 0 参与（原厂也写 0）

  for (int i = 0; i < 16; i++) // 16 个字节（8 字 × 2）
  {
    // 🔴 踩坑修复：必须先按 uint16_t 取高字节再截 8 位。
    //    最初写成 (uint8_t)(n_prom[i>>1]) >> 8 —— C 的强转先于移位，
    //    uint8_t 截断后 >>8 恒为 0，CRC 只算了一半数据位，
    //    兼容芯片的坏 PROM 也能"通过"校验（假阳性），排障差点被误导。
    if (i % 2 == 0) n_rem ^= 0x00FF & ((uint16_t)(n_prom[i >> 1]) >> 8); // 偶数次取高字节
    else            n_rem ^= 0x00FF & ((uint16_t)(n_prom[i >> 1]));      // 奇数次取低字节

    for (uint8_t j = 8; j > 0; j--) // 逐位移位做多项式除法
    {
      if (n_rem & 0x8000) n_rem = (n_rem << 1) ^ 0x3000;
      else                n_rem = (n_rem << 1);
    }
  }
  return (0x000F & (n_rem >> 12));
}

/* ------------------------------------------------------------------
 * writeCmd：发单字节命令
 * MS5611 无寄存器映射，"寄存器地址"位置放命令字节、长度 0 即可
 * （BusI2C::write 的实现是 beginTransmission + write(regAddr) + endTransmission）。
 * 返回：1 = ACK；0 = NACK/超时
 * ------------------------------------------------------------------ */
int BaroMS5611::writeCmd(uint8_t cmd)
{
  return _bus->write(_addr, cmd, 0, nullptr) ? 1 : 0;
}

} // namespace Espfc::Device::Baro
