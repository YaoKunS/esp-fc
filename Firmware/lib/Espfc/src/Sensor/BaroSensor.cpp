#include "Sensor/BaroSensor.hpp"
#include "Device/Baro/BaroMS5611.hpp" // 临时诊断：读 MS5611 原始 ADC 值（排障完撤）
#include "Hal/Time.hpp"

namespace Espfc::Sensor {

BaroSensor::BaroSensor(Model& model): _model(model), _state(BARO_STATE_INIT), _counter(0) {}

int BaroSensor::begin()
{
  if (!_model.baroActive() || !_model.state.baro.dev) return 0;

  _baro = _model.state.baro.dev;

  const int delay = _baro->getDelay(BARO_MODE_TEMP) + _baro->getDelay(BARO_MODE_PRESS);
  const int toGyroRate = (delay / _model.state.gyro.timer.interval) + 1; // number of gyro readings per cycle
  const int interval = _model.state.gyro.timer.interval * toGyroRate;
  const int rate = 1000000 / interval;
  _model.state.baro.rate = rate;

  const float dt = 1.0f / rate;
  const float tau = 0.8f;
  _biasAlpha = 1.0f - expf(-dt / tau);
  _model.state.baro.altitudeBiasSamples = 3 * rate;

  reload(MODEL_CHANGE_FILTER);

  _model.logger.info().log("BARO INIT").log(Device::BaroDevice::getName(_baro->getType())).logln(rate);

  _baro->setMode(BARO_MODE_TEMP);

  return 1;
}

int BaroSensor::reload(ModelChangeEvent event)
{
  switch (event)
  {
    case MODEL_CHANGE_FILTER: {
      const int rate = _model.state.baro.rate;
      const auto internalFilter = FILTER_PT1;
      const auto internalCutoff = std::max((rate + 2) / 4, 1);
      _temperatureFilter.begin(FilterConfig(internalFilter, internalCutoff), rate);
      _pressureFilter.begin(FilterConfig(internalFilter, internalCutoff), rate);
      _varioFilter.begin(FilterConfig(internalFilter, internalCutoff), rate);
      break;
    }
    default:
      break;
  }
  return 1;
}

int BaroSensor::update()
{
  int status = read();

  return status;
}

int BaroSensor::read()
{
  if (!_baro || !_model.baroActive()) return 0;

  if (_wait > micros()) return 0;

  Utils::Stats::Measure measure(_model.state.stats, COUNTER_BARO);

  // if(_model.config.debug.mode == DEBUG_BARO)
  // {
  //   _model.state.debug[0] = _state;
  // }

  switch (_state)
  {
    case BARO_STATE_INIT:
      _baro->setMode(BARO_MODE_TEMP);
      _state = BARO_STATE_TEMP_GET;
      _wait = micros() + _baro->getDelay(BARO_MODE_TEMP);
      return 0;
    case BARO_STATE_TEMP_GET:
      readTemperature();
      _baro->setMode(BARO_MODE_PRESS);
      _state = BARO_STATE_PRESS_GET;
      _wait = micros() + _baro->getDelay(BARO_MODE_PRESS);
      _counter = 1;
      return 1;
    case BARO_STATE_PRESS_GET:
      readPressure();
      updateAltitude();
      if (--_counter > 0)
      {
        _baro->setMode(BARO_MODE_PRESS);
        _state = BARO_STATE_PRESS_GET;
        _wait = micros() + _baro->getDelay(BARO_MODE_PRESS);
      }
      else
      {
        _baro->setMode(BARO_MODE_TEMP);
        _state = BARO_STATE_TEMP_GET;
        _wait = micros() + _baro->getDelay(BARO_MODE_TEMP);
      }
      return 1;
      break;
    default:
      _state = BARO_STATE_INIT;
      break;
  }

  return 0;
}

void BaroSensor::readTemperature()
{
  float temp = _model.state.baro.temperatureRaw = _baro->readTemperature();
  _model.state.baro.temperature = _temperatureFilter.update(temp);
}

void BaroSensor::readPressure()
{
  float press = _model.state.baro.pressureRaw = _baro->readPressure();
  _model.state.baro.pressure = _pressureFilter.update(press);
}

void BaroSensor::updateAltitude()
{
  auto& baro = _model.state.baro;

  baro.altitudeRaw = Utils::toAltitude(baro.pressure);
  float altitude = baro.altitudeRaw;

  if (baro.altitudeBiasSamples > 0)
  {
    baro.altitudeBiasSamples--;
    baro.altitudeBias += (altitude - baro.altitudeBias) * _biasAlpha;
  }
  else if (baro.altitudeBiasSamples == 0)
  {
    _model.logger.info().log("BARO BIAS").logln(baro.altitudeBias);
    baro.altitudeBiasSamples--;
  }

  baro.altitudeGround = altitude - baro.altitudeBias;
  baro.altitude = altitude;
  if (_first)
  {
    baro.altitudePrev = altitude;
    _first = false;
  }
  baro.vario = _varioFilter.update((altitude - baro.altitudePrev) * baro.rate);
  baro.altitudePrev = altitude;

  if (_model.config.debug.mode == DEBUG_BARO)
  {
    _model.state.debug[0] = lrintf(baro.vario * 100.0f);     // cm/s
    _model.state.debug[1] = lrintf(baro.pressureRaw * 0.1f); // hPa x 10
    //_model.state.debug[1] = lrintf(baro.pressureRaw - 100000.0f); // Pa - 100000
    _model.state.debug[2] = lrintf(baro.temperatureRaw * 100.f); // deg C x 100
    _model.state.debug[3] = lrintf(baro.altitudeGround * 100.f); // cm
    // 🔴 临时诊断（排障完撤）：把 MS5611 原始 ADC / dT / PROM 校验结果
    //    放进 debug[4..7]（空闲槽），MSP_DEBUG(254) 可远程读取。
    //    raw 右移 12 位是为了塞进 16 位槽（raw 24 位，高 12 位足够判值域与变化趋势）。
    if (_baro->getType() == BARO_MS5611) // 枚举在 Espfc 命名空间，Sensor 内可直接用
    {
      auto* ms = static_cast<Device::Baro::BaroMS5611*>(_baro);
      _model.state.debug[4] = ms->dbgRawD1() >> 12;
      _model.state.debug[5] = ms->dbgRawD2() >> 12;
      _model.state.debug[6] = (int16_t)(ms->dbgDt() & 0xFFFF);
      _model.state.debug[7] = ms->dbgPromValid() ? 1 : 0;
    }
  }
}

} // namespace Espfc::Sensor
