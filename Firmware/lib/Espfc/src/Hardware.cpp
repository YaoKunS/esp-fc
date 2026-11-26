#include "Hardware.h"
#include "Device/Baro/BaroBMP085.hpp"
#include "Device/Baro/BaroBMP280.hpp"
#include "Device/Baro/BaroMS5611.hpp" // MS5611 气压计驱动（耀坤智联新增，I2C 模式）
#include "Device/Baro/BaroSPL06.hpp"
#include "Device/BaroDevice.hpp"
#include "Device/Gyro/GyroBMI160.hpp"
#include "Device/Gyro/GyroICM20602.hpp"
#include "Device/Gyro/GyroICM42688.hpp"
#include "Device/Gyro/GyroLSM6DSO.hpp"
#include "Device/Gyro/GyroMPU6050.hpp"
#include "Device/Gyro/GyroMPU6500.hpp"
#include "Device/Gyro/GyroMPU9250.hpp"
#include "Device/GyroDevice.hpp"
#include "Device/Mag/MagAK8963.hpp"
#include "Device/Mag/MagHMC5883L.hpp"
#include "Device/Mag/MagQMC5883L.hpp"
#include "Device/Mag/MagQMC5883P.hpp"
#include "Hal/Board.hpp"
#include "Hal/Gpio.hpp"
#include "Hal/Time.hpp"
#include "Hal/Wifi.hpp"

namespace {
static Espfc::Device::BusSlave gyroSlaveBus;
static Espfc::Device::Gyro::GyroMPU6050 mpu6050;
static Espfc::Device::Gyro::GyroMPU6500 mpu6500;
static Espfc::Device::Gyro::GyroMPU9250 mpu9250;
static Espfc::Device::Gyro::GyroLSM6DSO lsm6dso;
static Espfc::Device::Gyro::GyroICM20602 icm20602;
static Espfc::Device::Gyro::GyroICM42688 icm42688;
static Espfc::Device::Gyro::GyroBMI160 bmi160;
static Espfc::Device::Mag::MagHMC5883L hmc5883l;
static Espfc::Device::Mag::MagQMC5883L qmc5883l;
static Espfc::Device::Mag::MagQMC5883P qmc5883p;
static Espfc::Device::Mag::MagAK8963 ak8963;
static Espfc::Device::Baro::BaroBMP085 bmp085;
static Espfc::Device::Baro::BaroBMP280 bmp280;
static Espfc::Device::Baro::BaroSPL06 spl06;
static Espfc::Device::Baro::BaroMS5611 ms5611; // MS5611 实例（探测顺序放最后，见 detectBaro 注释）
} // namespace

namespace Espfc {

Hardware::Hardware(Model& model): _model(model) {}

int Hardware::begin()
{
  initBus();
  detectGyro();
  detectMag();
  detectBaro();
  return 1;
}

void Hardware::onI2CError()
{
  _model.state.i2cErrorCount++;
  _model.state.i2cErrorDelta++;
}

void Hardware::initBus()
{
#if defined(ESPFC_SPI_0)
  auto* spiBus = Hal::getBusSPI(0);
  int spiResult = spiBus->begin(_model.config.pin[PIN_SPI_0_SCK], _model.config.pin[PIN_SPI_0_MOSI],
                                _model.config.pin[PIN_SPI_0_MISO]);
  if (spiResult)
  {
    _spiBus = spiBus;
  }

  {
    auto& logger = spiResult ? _model.logger.info() : _model.logger.err();
    logger.log("SPI")
        .log(_model.config.pin[PIN_SPI_0_SCK])
        .log(_model.config.pin[PIN_SPI_0_MOSI])
        .log(_model.config.pin[PIN_SPI_0_MISO])
        .logln(spiResult);
  }
#endif

#if defined(ESPFC_I2C_0)
  auto* i2cBus = Hal::getBusI2C(0);
  int i2cResult = i2cBus->begin(_model.config.pin[PIN_I2C_0_SDA], _model.config.pin[PIN_I2C_0_SCL],
                                _model.config.i2cSpeed * 1000ul);

  if (i2cResult)
  {
    _i2cBus = i2cBus;
    _i2cBus->onError = [this]() { onI2CError(); };
  }
  {
    auto& logger = i2cResult ? _model.logger.info() : _model.logger.err();
    logger.log("I2C")
        .log(_model.config.pin[PIN_I2C_0_SDA])
        .log(_model.config.pin[PIN_I2C_0_SCL])
        .log(_model.config.i2cSpeed)
        .logln(i2cResult);
  }
#endif
}

void Hardware::detectGyro()
{
  if (_model.config.gyro.dev == GYRO_NONE) return;

  Device::GyroDevice* detectedGyro = nullptr;
  bool gyroOnI2c = false; // 记录陀螺仪在哪条总线上被探测到（决定默认安装朝向档位，见函数尾）
#if defined(ESPFC_SPI_0)
  if (_spiBus && _model.config.pin[PIN_SPI_CS0] != -1)
  {
    Hal::Gpio::digitalWrite(_model.config.pin[PIN_SPI_CS0], Hal::Gpio::High);
    Hal::Gpio::pinMode(_model.config.pin[PIN_SPI_CS0], Hal::Gpio::Output);
    if (!detectedGyro && detectDevice(mpu9250, _spiBus, _model.config.pin[PIN_SPI_CS0])) detectedGyro = &mpu9250;
    if (!detectedGyro && detectDevice(mpu6500, _spiBus, _model.config.pin[PIN_SPI_CS0])) detectedGyro = &mpu6500;
    if (!detectedGyro && detectDevice(icm20602, _spiBus, _model.config.pin[PIN_SPI_CS0])) detectedGyro = &icm20602;
    if (!detectedGyro && detectDevice(icm42688, _spiBus, _model.config.pin[PIN_SPI_CS0])) detectedGyro = &icm42688;
    if (!detectedGyro && detectDevice(bmi160, _spiBus, _model.config.pin[PIN_SPI_CS0])) detectedGyro = &bmi160;
    if (!detectedGyro && detectDevice(lsm6dso, _spiBus, _model.config.pin[PIN_SPI_CS0])) detectedGyro = &lsm6dso;
    if (detectedGyro) gyroSlaveBus.begin(_spiBus, detectedGyro->getAddress());
  }
#endif
#if defined(ESPFC_I2C_0)
  if (!detectedGyro && _i2cBus && _model.config.pin[PIN_I2C_0_SDA] != -1 && _model.config.pin[PIN_I2C_0_SCL] != -1)
  {
    if (!detectedGyro && detectDevice(mpu9250, _i2cBus)) detectedGyro = &mpu9250;
    if (!detectedGyro && detectDevice(mpu6500, _i2cBus)) detectedGyro = &mpu6500;
    if (!detectedGyro && detectDevice(icm20602, _i2cBus)) detectedGyro = &icm20602;
    if (!detectedGyro && detectDevice(bmi160, _i2cBus)) detectedGyro = &bmi160;
    if (!detectedGyro && detectDevice(mpu6050, _i2cBus)) detectedGyro = &mpu6050;
    if (!detectedGyro && detectDevice(lsm6dso, _i2cBus)) detectedGyro = &lsm6dso;
    if (detectedGyro)
    {
      gyroSlaveBus.begin(_i2cBus, detectedGyro->getAddress());
      gyroOnI2c = true;
    }
  }
#endif
  if (!detectedGyro) return;

  detectedGyro->setDLPFMode(_model.config.gyro.dlpf);
  _model.state.gyro.dev = detectedGyro;
  _model.state.gyro.present = (bool)detectedGyro;
  _model.state.accel.present = _model.state.gyro.present && _model.config.accel.dev != GYRO_NONE;
  _model.state.gyro.clock = detectedGyro->getRate();

  /* ---------------------------------------------------------------------------
   * 🔴 IMU 安装朝向自动分档（v1.0.1，2026-11-26 二次修正）
   *
   * 背景：出厂 gyro_align=DEFAULT（不旋转），而本板（耀坤 S3 PCB V2）上两种
   * IMU 模块的贴装/插装方向都不是"零旋转"，BF 配置器 3D 姿态不对。
   *
   * 修正史（四版，一切以 BF 配置器实测为准）：
   *   ① 首版按 flix imuRotation 的字面值配 CW90(I2C)/CW270(SPI)——BF 实测
   *      pitch/roll 双双反向（实物抬头 3D 低头）。原因：flix 的 imuRotation
   *      是「机体→传感器」的旋转描述，换算到 ESP-FC 的「传感器→机体」向量
   *      变换时方向取反，我当时推错了方向。
   *   ② 二版改 CW270(I2C)/CW90(SPI)——6500(SPI) 实测正确 ✅。
   *   ③ 三版曾把 I2C 改 CW90——实测 6050 仍是 pitch/roll 双反相，与 ② 矛盾。
   *      复盘定论：CW270 与 CW90 相差 180°，固定模块朝向下不可能出现完全
   *      相同的症状；矛盾根源是**测试期间模块被重新插装，朝向变了**。
   *      🔴 教训：I2C 排母 / SPI 座允许 180° 插装，拔插方向一变，正确档位
   *         就跟着变。排障/标定时必须固定插装方向（建议模块与插座做对位
   *         标记），换插方向后若姿态异常，先怀疑朝向再怀疑参数。
   *   ④ 本版终版（2026-11-26，用户 BF CLI 实时切换实测确认）：6050(I2C)→
   *      **CW270**、6500(SPI)→CW90。验证方法：CLI `set gyro_align CW270`
   *      不重启即实时生效（align 每采样周期读 config），BF 3D 姿态恢复正常。
   *
   * BF 约定（MSP_ATTITUDE 直接透传 euler，yaw 取负）：pitch 正=低头、
   * roll 正=右倾。以下两档经实机验证：实物抬头 → 3D 模型抬头、
   * 实物右倾 → 3D 模型右倾。
   *
   * 生效规则：仅当 gyro_align 仍为出厂默认 DEFAULT 时自动覆盖（每次探测都执行，
   * 排母换模块立即生效）；用户 CLI `set gyro_align xxx` 或 BF 配置器显式设过
   * 的值（≠DEFAULT）永远优先，不会被覆盖。
   * ------------------------------------------------------------------------ */
  if (_model.config.gyro.align == ALIGN_DEFAULT)
  {
    _model.config.gyro.align = gyroOnI2c ? ALIGN_CW270_DEG : ALIGN_CW90_DEG;
    // 日志留痕：探测依据一目了然（CLI `logs` 可见），排障时不用猜
    auto& lg = _model.logger.info();
    lg.log("GYRO ALIGN AUTO");
    lg.logln(gyroOnI2c ? "CW270 (I2C 6050-family)" : "CW90 (SPI 6500-family)");
  }
}

void Hardware::detectMag()
{
  if (_model.config.mag.dev == MAG_NONE) return;

  Device::MagDevice* detectedMag = nullptr;
#if defined(ESPFC_I2C_0)
  if (_i2cBus && _model.config.pin[PIN_I2C_0_SDA] != -1 && _model.config.pin[PIN_I2C_0_SCL] != -1)
  {
    if (!detectedMag && detectDevice(ak8963, _i2cBus)) detectedMag = &ak8963;
    if (!detectedMag && detectDevice(hmc5883l, _i2cBus)) detectedMag = &hmc5883l;
    if (!detectedMag && detectDevice(qmc5883l, _i2cBus)) detectedMag = &qmc5883l;
    if (!detectedMag && detectDevice(qmc5883p, _i2cBus)) detectedMag = &qmc5883p;
  }
#endif
  if (gyroSlaveBus.getBus())
  {
    if (!detectedMag && detectDevice(ak8963, &gyroSlaveBus)) detectedMag = &ak8963;
    if (!detectedMag && detectDevice(hmc5883l, &gyroSlaveBus)) detectedMag = &hmc5883l;
    if (!detectedMag && detectDevice(qmc5883l, &gyroSlaveBus)) detectedMag = &qmc5883l;
    if (!detectedMag && detectDevice(qmc5883p, &gyroSlaveBus)) detectedMag = &qmc5883p;
  }
  _model.state.mag.dev = detectedMag;
  _model.state.mag.present = (bool)detectedMag;
  _model.state.mag.rate = detectedMag ? detectedMag->getRate() : 0;
}

void Hardware::detectBaro()
{
  if (_model.config.baro.dev == BARO_NONE) return;

  Device::BaroDevice* detectedBaro = nullptr;
#if defined(ESPFC_SPI_0)
  if (_spiBus && _model.config.pin[PIN_SPI_CS1] != -1)
  {
    Hal::Gpio::digitalWrite(_model.config.pin[PIN_SPI_CS1], Hal::Gpio::High);
    Hal::Gpio::pinMode(_model.config.pin[PIN_SPI_CS1], Hal::Gpio::Output);
    if (!detectedBaro && detectDevice(bmp280, _spiBus, _model.config.pin[PIN_SPI_CS1])) detectedBaro = &bmp280;
    if (!detectedBaro && detectDevice(bmp085, _spiBus, _model.config.pin[PIN_SPI_CS1])) detectedBaro = &bmp085;
    if (!detectedBaro && detectDevice(spl06, _spiBus, _model.config.pin[PIN_SPI_CS1])) detectedBaro = &spl06;
  }
#endif
#if defined(ESPFC_I2C_0)
  if (_i2cBus && _model.config.pin[PIN_I2C_0_SDA] != -1 && _model.config.pin[PIN_I2C_0_SCL] != -1)
  {
    if (!detectedBaro && detectDevice(bmp280, _i2cBus)) detectedBaro = &bmp280;
    if (!detectedBaro && detectDevice(bmp085, _i2cBus)) detectedBaro = &bmp085;
    if (!detectedBaro && detectDevice(spl06, _i2cBus)) detectedBaro = &spl06;
    // MS5611 放最后：它没有 ID 寄存器，只能靠 PROM 系数合理性判断，
    // 万一总线上同时挂着 BMP280（地址同为 0x76/0x77），让有真 ID 的芯片先被认领
    if (!detectedBaro && detectDevice(ms5611, _i2cBus)) detectedBaro = &ms5611;
    // 注入压力补偿模式（CLI baro_math：-1=按 CRC 自动 / 0=MS5611 / 1=AN520-MS5607）
    if (detectedBaro == &ms5611) ms5611.setMathMode(_model.config.baro.math);
    // 诊断信息：PROM 8 字 + CRC 校验结果打进日志（CLI `logs` 可见），
    // 用于核对 MS5611 标定系数（与数据手册 AN520 手算对照），也方便识别兼容芯片。
    if (detectedBaro == &ms5611)
    {
      const auto& cal = ms5611.dbgCal();
      auto& lg = _model.logger.info();
      lg.log("MS5611PROM");
      for (int i = 0; i < 8; i++) lg.loghex(cal.w[i]);
      lg.logln(ms5611.dbgPromValid() ? "CRC_OK" : "CRC_BAD");
    }
  }
#endif
  if (gyroSlaveBus.getBus())
  {
    if (!detectedBaro && detectDevice(bmp280, &gyroSlaveBus)) detectedBaro = &bmp280;
    if (!detectedBaro && detectDevice(bmp085, &gyroSlaveBus)) detectedBaro = &bmp085;
    if (!detectedBaro && detectDevice(spl06, &gyroSlaveBus)) detectedBaro = &spl06;
    // MS5611 同理放最后（gyroSlaveBus 也是 I2C 总线，挂在陀螺仪后面）
    if (!detectedBaro && detectDevice(ms5611, &gyroSlaveBus)) detectedBaro = &ms5611;
  }

  _model.state.baro.dev = detectedBaro;
  _model.state.baro.present = (bool)detectedBaro;
}

void Hardware::restart(const Model& model)
{
  if (model.state.mixer.escMotor) model.state.mixer.escMotor->end();
  if (model.state.mixer.escServo) model.state.mixer.escServo->end();
#ifdef ESPFC_SERIAL_SOFT_0_WIFI
  Hal::Wifi::stop();
#endif
  delay(100);
  Hal::Board::reset();
}

} // namespace Espfc
