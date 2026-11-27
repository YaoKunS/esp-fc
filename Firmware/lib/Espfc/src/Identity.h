#pragma once

/* ===========================================================================
 * Identity.h —— ESP-FC 耀坤整理版开机 IDENTITY 横幅（品牌身份唯一数据源）
 * ---------------------------------------------------------------------------
 * 【为什么要单独建这个文件】
 *   上游 ESP-FC 开机没有任何主动品牌输出，只有 CLI `version` 命令打印
 *   `ESPF <target> <version> <rev> <date> <time> api= ...` 这类技术串，
 *   现场无法一眼认出"这是哪条产品线、硬件归谁、固件归谁"。
 *   耀坤自研飞控（YaoKun_Drone/config.h 的 FK_ID_*）和 flix 耀坤整理版
 *   （i18n.h 的 TXT_IDENTITY）都在开机主动打印 IDENTITY 横幅，本文件把
 *   同一套语义搬到 ESP-FC，三款固件的第一屏口径完全一致。
 *
 * 【品牌铁律（🔴 改文案前必读，与自研 config.h 第 34-44 行同源）】
 *   1. 两块板品牌互相独立，耀坤智联只是"替微辣火龙果作者做固件适配维护"，
 *      不是火龙果本人，更不能暗示耀坤拥有火龙果硬件或获奖：
 *        · 火龙果版：硬件署名 (c) 微辣火龙果（malagis / MildlySpicyDragon），
 *          2025 星火奖必须明写是"微辣火龙果项目"的奖，固件适配才署耀坤；
 *        · S3 版：严禁出现任何火龙果的立创开源页 / B 站链接（下面 S3 分支
 *          故意不定义那些宏，编译期就钉死，不靠人记）。
 *   2. 火龙果英文名固定写 MildlySpicyDragon（作者用户名），禁止意译。
 *   3. 版本号全工程只允许 platform.h 的 ESPFC_VERSION 一处数据源，
 *      横幅用 STR() 把它字符串化，发新版本只改那一处即可联动。
 *
 * 【为什么用宏数组而不是运行时拼字符串】
 *   横幅内容全部是编译期常量，直接进 .rodata，不占堆、不引入格式化开销；
 *   开机时遍历打印即可，也方便发布说明里的"指纹"逐行对照。
 * ========================================================================= */

#include <platform.h>  // STR() / ESPFC_VERSION（版本唯一数据源）

#define IDENTITY_SEP "IDENTITY: ============================================"

/* ---------------------------------------------------------------------------
 * 编译期版本号：来自 platform.h 的 ESPFC_VERSION（如 v1.1）。
 * 注意 ESPFC_VERSION 必须是【不带引号的裸 token】，否则 STR() 会把引号也编进去。
 * ------------------------------------------------------------------------ */
#define IDENTITY_VERSION STR(ESPFC_VERSION)

#if defined(ESPFC_TARGET_HLG20)
  /* ========================= 微辣火龙果 2.0 版 ========================= */
  // 产品名：保留作者品牌在前，括号里说明是耀坤固件适配版，避免品牌混淆。
  #define IDENTITY_NAME   "IDENTITY:   微辣火龙果 2.0 飞控（ESP-FC 耀坤适配版） MildlySpicyDragon"
  #define IDENTITY_AUTHOR "IDENTITY:   Author  : 硬件设计 微辣火龙果（malagis）· 固件适配 耀坤智联"
  // 🔴 星火奖归属：2025 鼓励奖属于微辣火龙果项目（malagis），不是耀坤的。
  //    用户明确要求写上，但必须把获奖主体钉死在"微辣火龙果项目"上。
  #define IDENTITY_AWARD  "IDENTITY:   Award   : 2025星火计划获奖项目 —— 微辣火龙果（malagis），非耀坤"
  #define IDENTITY_BILI   "IDENTITY:   BiliBili : 微辣火龙果  https://space.bilibili.com/544479100"
  #define IDENTITY_OSH    "IDENTITY:   OSHWHub  : 微辣火龙果  https://oshwhub.com/malagis/esp32-mini-plane"
  // 固件仓库行指向 ESP-FC 适配仓库（不是 flix / 自研飞控仓库，三个产品互相独立）。
  #define IDENTITY_GITHUB "IDENTITY:   GitHub   : https://github.com/YaoKunS/esp-fc (yaokun-organized)"

#elif defined(ESPFC_TARGET_YAOKUN)
  /* ========================= 耀坤 S3 版 ========================= */
  #define IDENTITY_NAME   "IDENTITY:   YaoKunS   耀坤S3无人机 | ESP-FC 耀坤整理版"
  #define IDENTITY_AUTHOR "IDENTITY:   Author  : 耀坤智联 YaoKunSmart"
  // S3 版【没有】IDENTITY_AWARD / IDENTITY_BILI / IDENTITY_OSH 的火龙果版本：
  // 编译期就不定义这些宏，S3 横幅里绝不可能出现火龙果链接或奖项。
  #define IDENTITY_BILI   "IDENTITY:   BiliBili : 耀坤智联  https://space.bilibili.com/3707011699050767/"
  #define IDENTITY_OSH    "IDENTITY:   OSHWHub  : 耀坤无人机  https://oshwhub.com/lindahe/"
  #define IDENTITY_GITHUB "IDENTITY:   GitHub   : https://github.com/YaoKunS/esp-fc (yaokun-organized)"

#else
  /* ========================= 上游通用板（行为不变） ========================= */
  // 非耀坤板型不打印品牌横幅：避免把耀坤署名烧进上游原版固件。
  #define ESPFC_IDENTITY_DISABLED
#endif

#ifndef ESPFC_IDENTITY_DISABLED

/* 版本行：编译期拼接，发版只改 platform.h 的 ESPFC_VERSION 一处。 */
#define IDENTITY_VERSION_LINE "IDENTITY:   Version  : " IDENTITY_VERSION
/* 编译时间行：__DATE__/__TIME__ 精确对应本机这一次编译，排障时可核对固件新旧。 */
#define IDENTITY_BUILT_LINE   "IDENTITY:   Built   : " __DATE__ " " __TIME__
/* 淘宝店与固件仓库两板共用，放在最后两行，属于耀坤的署名。 */
#define IDENTITY_TAOBAO       "IDENTITY:   Taobao   : 耀坤智联  https://shop35432590.taobao.com/"

/* 横幅行表（以 nullptr 结尾）：顺序与自研 IDENTITY 块一致，方便逐行对照。 */
static const char* const ESPFC_IDENTITY_LINES[] = {
  IDENTITY_SEP,
  IDENTITY_NAME,
  IDENTITY_VERSION_LINE,
  IDENTITY_BUILT_LINE,
#ifdef IDENTITY_AWARD
  IDENTITY_AWARD,
#endif
  IDENTITY_AUTHOR,
  IDENTITY_BILI,
  IDENTITY_OSH,
  IDENTITY_TAOBAO,
  IDENTITY_GITHUB,
  IDENTITY_SEP,
  nullptr
};

#endif
