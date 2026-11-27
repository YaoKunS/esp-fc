#include "Espfc.h"
#include "Debug_Espfc.h"
#include "Hal/FastCode.hpp"
#include "Hal/Platform.hpp"
#include "Hal/Time.hpp"
#include "Identity.h"          // 开机 IDENTITY 横幅（品牌身份，见文件内注释）
#include "Stream/Printer.hpp"  // 文本输出封装（println 发 CRLF）

namespace Espfc {

/* ---------------------------------------------------------------------------
 * printIdentity() —— 开机在 MSP 地面站口打印多行 IDENTITY 品牌横幅。
 *
 * 【为什么在 SerialManager::begin() 之后调用】
 *   横幅要打到用户实际插线的 MSP 口（S3=UART0，火龙果=UART0/CH340），
 *   必须先等串口初始化完成、state.serial[i].stream 指针有效。
 *
 * 【为什么取 SERIAL_FUNCTION_MSP 的口而不是 debug 口】
 *   S3 的 debug 口是 SERIAL_USB（虚拟串口），火龙果是 UART0；
 *   两板用户看横幅的口不一致。统一取 MSP 口，才能保证 BF 配置器 /
 *   串口助手连上就能看到第一屏身份串，与自研、flix 的观感一致。
 *
 * 【为什么不写进 logger】
 *   logger 只在 ESPFC_DEBUG_SERIAL 宏打开时才输出到串口，而发布固件
 *   默认不开该宏 —— 写进 logger 会导致横幅永远不出现。
 *
 * 【串口被占用时的行为】
 *   取不到流指针就静默跳过，绝不影响飞控启动流程（横幅是观感功能，
 *   不能因为它让飞机不起飞）。
 * ------------------------------------------------------------------------ */
static void printIdentity(Stream::ReadWritable* stream)
{
  if (!stream) return;

  Stream::Printer printer(*stream);
  for (const char* const* line = ESPFC_IDENTITY_LINES; *line; ++line)
  {
    printer.println(*line);
  }
}

Espfc::Espfc()
    : _hardware{_model}, _controller{_model}, _telemetry{_model}, _input{_model, _telemetry}, _actuator{_model},
      _sensor{_model}, _mixer{_model}, _blackbox{_model}, _buzzer{_model}, _serial{_model, _telemetry}
{
}

int Espfc::load()
{
  PIN_DEBUG_INIT();
  _model.load();
  _model.state.appQueue.begin();
  return 1;
}

int Espfc::begin()
{
  _model.state.led.begin(_model.config.pin[PIN_LED_BLINK], _model.config.led.type, _model.config.led.invert);

  _serial.begin();   // requires _model.load()

  // 开机品牌横幅：取第一路 MSP 口（getSerialIndex 从 index 0 找起，
  // 两板都是 UART0 = 用户插线的地面站口），与自研/flix 第一屏口径一致。
#ifndef ESPFC_IDENTITY_DISABLED
  printIdentity(_model.getSerialStream(SERIAL_FUNCTION_MSP));
#endif

  _hardware.begin(); // requires _model.load()
  _model.begin();    // requires _hardware.begin()
  _mixer.begin();
  _sensor.begin();   // requires _hardware.begin()
  _input.begin();    // requires _serial.begin()
  _actuator.begin(); // requires _model.begin()
  _controller.begin();
  _blackbox.begin(); // requires _serial.begin(), _actuator.begin()
  _buzzer.begin();

  _model.state.buzzer.push(BUZZER_SYSTEM_INIT);

  _model.setConfigChangeListener([this](ModelChangeEvent event) {
    _serial.reload(event);
    _sensor.reload(event);
    _input.reload(event);
    _controller.reload(event);
  });

  return 1;
}

int FAST_CODE_ATTR Espfc::update(bool externalTrigger)
{
  if (externalTrigger)
  {
    _model.state.gyro.timer.update();
  }
  else
  {
    if (!_model.state.gyro.timer.check()) return 0;
  }
  Utils::Stats::Measure measure(_model.state.stats, COUNTER_CPU_0);

  if constexpr (Hal::MULTI_CORE)
  {
    _sensor.read();
    if (_model.state.input.timer.syncTo(_model.state.gyro.timer, 1u))
    {
      _input.update();
    }
    if (_model.state.actuatorTimer.check())
    {
      _actuator.update();
    }
  }
  else
  {
    _sensor.update();
    if (_model.state.loopTimer.syncTo(_model.state.gyro.timer))
    {
      _controller.update();
      if (_model.state.mixer.timer.syncTo(_model.state.loopTimer))
      {
        _mixer.update();
      }
      _blackbox.update();
      if (_model.state.input.timer.syncTo(_model.state.gyro.timer, 1u))
      {
        _input.update();
      }
      if (_model.state.actuatorTimer.check())
      {
        _actuator.update();
      }
    }
    _sensor.updateDelayed();
  }

  _serial.update();
  _buzzer.update();
  _model.state.led.update();
  _model.state.stats.update();

  return 1;
}

// other task
int FAST_CODE_ATTR Espfc::updateOther()
{
  if constexpr (Hal::MULTI_CORE)
  {
    Event e;
    if (!_model.state.appQueue.pop(e))
    {
      return 0;
    }

    Utils::Stats::Measure measure(_model.state.stats, COUNTER_CPU_1);

    switch (e.type)
    {
      case EVENT_GYRO_READ:
        _sensor.preLoop();
        _controller.update();
        // skip mixer and bb if earlier than half cycle, possible delay in previous iteration,
        // to keep space to receive dshot erpm frame, but process rest
        if (_loop_next < micros())
        {
          _loop_next = micros() + _model.state.loopTimer.interval / 2;
          _mixer.update();
          _blackbox.update();
        }
        _sensor.postLoop();
        break;
      case EVENT_ACCEL_READ:
        _sensor.fusion();
        break;
      default:
        break;
        // nothing
    }
  }

  return 1;
}

} // namespace Espfc
