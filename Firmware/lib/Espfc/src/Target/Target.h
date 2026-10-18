#pragma once

// 耀坤智联新增：耀坤 S3 无人机板级定义。
// 必须在 ESP32S3 之前判断 —— 该宏同时定义了 ESP32S3（芯片系列）与板级选择，
// 放在前面才能覆盖上游通用的 TargetESP32s3.h（引脚对不上耀坤 PCB）。
// 不定义 ESPFC_TARGET_YAOKUN 时行为与上游 100% 一致。
#if defined(ESPFC_TARGET_YAOKUN)
  #include "TargetESP32s3YaoKun.h"
#elif defined(ESP32C3)
#include "TargetESP32c3.h"
#elif defined(ESP32S2)
#include "TargetESP32s2.h"
#elif defined(ESP32S3)
#include "TargetESP32s3.h"
#elif defined(ESP32)
#include "TargetESP32.h"
#elif defined(ESP8266)
#include "TargetESP8266.h"
#elif defined(ARCH_RP2040)
#include "TargetRP2040.h"
#elif defined(UNIT_TEST)
#include "TargetUnitTest.h"
#else
#error "Unsupported platform!"
#endif
