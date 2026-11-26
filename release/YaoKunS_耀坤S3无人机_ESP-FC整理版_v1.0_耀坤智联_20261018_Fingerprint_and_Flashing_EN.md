# YaoKun S3 Drone / ESP-FC Organized Edition — Firmware Fingerprint & Flashing Guide

## 1. What this firmware is

Built on the open-source flight controller **ESP-FC** (by Ramon Lopez).
It keeps every line of upstream code and the MIT licence, and adds a board-level
adaptation for the YaoKun S3 hardware.

- **Upstream**: <https://github.com/rtlopez/esp-fc> (MIT, (c) Ramon Lopez)
- **This fork**: <https://github.com/YaoKunS/esp-fc> (branch `yaokun-organized`)
- **Hardware**: YaoKun S3 drone (ESP32-S3, 8 MB Flash + 8 MB OPI (octal))
- **Motors**: 4 × **8520 coreless brushed motors**, GPIO **6 / 5 / 15 / 16** (FR / RR / RL / FL), **PWM output**
- **Sensors**: MPU6500 (SPI, CS=GPIO17) or MPU6050 (I2C, SDA=9 / SCL=8)
- **RC**: SBUS (GPIO1); ELRS reserved on UART2 (GPIO11/12, protocol must be set to CRSF)
- **Ground station**: Betaflight / Cleanflight Configurator (MSP v2)
- **Misc**: buzzer GPIO39, battery sense GPIO2 (1:2 divider)

> ★ This firmware is **attitude-stabilised + manual throttle only**: no GPS, barometer or
> rangefinder.
>
> - **It does not hover when you release the sticks** — attitude is held but horizontal
>   velocity carries on
> - **Letting go of the throttle means losing altitude**
> - Fly the first time in a **wide open area, low altitude, with prop guards**

## 2. Version and provenance

| Item | Value |
| --- | --- |
| Firmware version | **v1.0** (YaoKun Organized Edition) |
| Brand | YaoKunSmart / YaoKunS |
| Build environment | `pio run -e esp32s3_yaokun` |
| Build time | Oct 18 2026 18:40:31 |
| Toolchain | PlatformIO Core (espressif32 + arduino) |
| Key build flags | `-DESPFC_TARGET_YAOKUN` `-DESPFC_DEV_PRESET_BRUSHED` |
| Application size | 995,360 B (0xF3020) |

> 🔴 **Neither macro may be removed**:
> `-DESPFC_TARGET_YAOKUN` selects the YaoKun pin map (otherwise upstream's 39/40/41/42 are
> used — no motors turn and the buzzer screams); `-DESPFC_DEV_PRESET_BRUSHED` switches the
> output from DShot to PWM (the 8520 coreless motors are **brushed**, and a brushed ESC only
> understands PWM — otherwise all four motors stay dead).

## 3. How to flash

### Option A — single file (simplest)

```bash
esptool --chip esp32s3 --port COMx --baud 921600 write_flash 0x0 "YaoKunS_耀坤S3无人机_ESP-FC整理版_v1.0_耀坤智联_20261018_merged.bin"
```

For a GUI use the [ESP Tool Website](https://espressif.github.io/esptool-js/):
connect → add `YaoKunS_耀坤S3无人机_ESP-FC整理版_v1.0_耀坤智联_20261018_merged.bin` → Flash Address `0x0` → Program.

⚠️ If you tick **DoNotChgBin**: the SPI mode/frequency/size are already encoded in the image
header; rewriting them breaks the checksum.

### Option B — by segment (★ use this if your board is already calibrated)

A full-chip write from `0x0` erases the NVS region `0x9000~0xE000`, which means your PID
tuning and accelerometer calibration are gone.

```bash
esptool --chip esp32s3 --port COMx --baud 921600 write_flash \\
  0x0      "bootloader.bin" \\
  0x8000   "partitions.bin" \\
  0x10000  "firmware.bin"
```

(`boot_app0.bin` normally does not need reflashing.)

## 4. How to verify you flashed this exact build

**① Compare the hash** (most reliable, no power needed):

```cmd
certutil -hashfile "YaoKunS_耀坤S3无人机_ESP-FC整理版_v1.0_耀坤智联_20261018_merged.bin" SHA256
```

```bash
sha256sum "YaoKunS_耀坤S3无人机_ESP-FC整理版_v1.0_耀坤智联_20261018_merged.bin"
```

→ must equal **98238427d80ea13678da9757fbb48d66e725cbe39e916c053878b00222fae1fe**

**② Serial confirmation**

Attach **UART0 (GPIO43/44, 115200 8N1)** or the **native USB CDC** port and open it at
115200 baud. You should see the ESP-FC CLI banner, then type `status` and `dump` in the CLI —
save the `dump` output as your baseline.

**③ Search plaintext inside the bin** (no device needed):

- search `esp-fc` → hit (product name string)
- search for `MSP` / `Betaflight` related strings to confirm the protocol stack is linked in

**④ Read the image header from flash** (read-only, changes nothing):

```bash
esptool --chip esp32s3 --port COMx read_flash 0x10000 0x200 app_hdr.bin
```

→ the first byte must be `E9` (ESP image magic).

## 5. Artifacts and checksums (SHA-256)

| Artifact | Flash address | SHA-256 | Size |
| --- | --- | --- | --- |
| `bootloader.bin` | `0x0` | `1776e4dd896a69d0a5c2e79957b0e2a88aa4129b1381d6478683515a1f6af343` | 15,104 B (0x3B00) |
| `partitions.bin` | `0x8000` | `1d9cca96de0fe07ad7fc0648b9878ddecd9ce565e38b589ad20fea698ed4c80c` | 3,072 B (0xC00) |
| `boot_app0.bin` | `0xE000` | `f94c5d786a7a8fab06ac5d10e33bf37711a6697636dc037559ea19cc410a17f0` | 8,192 B (0x2000) |
| `firmware.bin` | `0x10000` | `1482720c75b79337036bfdcbae9457dbfc4e2f99cb66c69fcf8677ae607f5954` | 995,360 B (0xF3020) |
| **合并单文件固件** | `0x0` 整体刷 | `98238427d80ea13678da9757fbb48d66e725cbe39e916c053878b00222fae1fe` | 1,064,960 B (0x104000) |

- Merged layout: `0x0` bootloader `+ 0x8000` partitions `+ 0xE000` boot_app0 `+ 0x10000`
  application (gaps padded with 0xFF)
- Flash size: **8 MB** (double-check with `esptool image-info <bin>`)
- 应用程序镜像头：`E9 05 02 3F` → SPI 模式 **DIO**、段数 **5**、入口 **0x4037D018**
- bootloader 镜像头：`E9 03 02 3F` → SPI 模式 **DIO**

## 6. Four things to do after flashing

1. **Redo the accelerometer calibration** (if a full-chip write wiped NVS): hold still ≥2 s on
   each of the six faces
2. **Motor test without props**: all four motors must sound; if none do, check that
   `-DESPFC_DEV_PRESET_BRUSHED` is in your build flags
3. **Check the voltage reading against a multimeter**: the configurator value must match the
   measured value (this validates `ESPFC_ADC_SCALE = 2.0f/4096`)
4. **Enable notches once the props are on**: brushed motors are noisy — type
   `set gyro_notch_count 3` in the CLI

## 7. Troubleshooting

| Symptom | Root cause | Fix |
| --- | --- | --- |
| Configurator cannot see the board | Wrong env (Flash/PSRAM mismatch) | Rebuild with the matching env |
| Stuck in download mode after flashing | USB CDC COM not enumerated | Hold BOOT and reset, or use UART0 |
| No serial output at all on boot | Flash/PSRAM mismatch → panic | Check the module silkscreen R8N8 / N4R2 |
| **None of the four motors turn** | Missing `-DESPFC_DEV_PRESET_BRUSHED` | Add it and rebuild |
| **Buzzer runs constantly** | You flashed upstream's `esp32s3` build | Flash `esp32s3_yaokun` instead |
| Voltage reading is half the real value | Wrong `ESPFC_ADC_SCALE` | Change it to `2.0f/4096` |
| Attitude frozen / sensor lost | Wrong IMU chip select (V1=17 / V2=42) | Change `ESPFC_SPI_CS_GYRO` and rebuild |
| ELRS receiver gives no data | Protocol not set to CRSF | Set the UART2 protocol in the configurator |

## 8. Find us

- Bilibili: [YaoKunSmart](https://space.bilibili.com/3707011699050767)
- GitHub: <https://github.com/YaoKunS>
- Taobao: [YaoKunSmart](https://shop35432590.taobao.com/)

---

Auto-generated by `Firmware/tools/pack_release.py`; hashes, segment layout, image headers and
build time are extracted live from the firmware image and match the bins exactly.
The published artifacts contain **no local machine paths**.
