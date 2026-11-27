#pragma once

// 耀坤智联新增：耀坤 S3 无人机板级定义。
// 必须在 ESP32S3 之前判断 —— 该宏同时定义了 ESP32S3（芯片系列）与板级选择，
// 放在前面才能覆盖上游通用的 TargetESP32s3.h（引脚对不上耀坤 PCB）。
// 不定义 ESPFC_TARGET_YAOKUN 时行为与上游 100% 一致。
//
// 耀坤智联新增（2026-11-27）：微辣火龙果 2.0 板级定义（ESP32 经典片）。
// 必须在 ESP32 之前判断，否则会被上游通用的 TargetESP32.h 抢走 ——
// 上游模板的电机 27/25/4/12、串口 33/32 都对不上火龙果 PCB
// （串口 33/32 正好是本板的电机脚，会被 UART 初始化抢走）。
// 硬件设计 (c) 微辣火龙果（malagis / MildlySpicyDragon）；固件适配 耀坤智联。
#if defined(ESPFC_TARGET_YAOKUN)
  #include "TargetESP32s3YaoKun.h"
#elif defined(ESPFC_TARGET_HLG20)
  #include "TargetESP32HLG20.h"
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
