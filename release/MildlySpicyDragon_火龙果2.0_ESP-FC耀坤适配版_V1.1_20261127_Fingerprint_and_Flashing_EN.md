# MildlySpicyDragon 2.0 / ESP-FC YaoKun Adapted Edition — Firmware Fingerprint & Flashing Guide

## 1. What this firmware is

Built on the open-source flight controller **ESP-FC** (by Ramon Lopez).
It keeps every line of upstream code and the MIT licence, and adds a board-level
adaptation for the **MildlySpicyDragon 2.0 flight controller**.

- **Upstream**: <https://github.com/rtlopez/esp-fc> (MIT, (c) Ramon Lopez)
- **This fork**: <https://github.com/YaoKunS/esp-fc> (branch `yaokun-organized`)
- **Hardware**: MildlySpicyDragon 2.0 flight controller (ESP32 DevKit V1 classic module,
  4 MB Flash, none (WROOM-32 module))
- **Hardware design**: **(c) MildlySpicyDragon (malagis)** — OSHWHub project page:
  <https://oshwhub.com/malagis/esp32-mini-plane>; Bilibili:
  <https://space.bilibili.com/544479100>
- **Firmware adaptation**: YaoKunSmart (YaoKunS)
- **Motors**: 4 × **8520 coreless brushed motors**, GPIO **27 / 33 / 26 / 32**
  (RR / FR / RL / FL, silkscreen M2 / M1 / M3 / M4), **PWM output**
- **Sensors**: MPU6500 (SPI, SCK18 / MOSI23 / MISO19, **CS=GPIO5**)
  or MPU6050 (I2C, SDA=21 / SCL=22, socket)
- **Barometer**: MS5611 driver included (I2C 0x76/0x77, auto-detects MS5607/AN520 clone
  parts; enable with CLI `set baro_dev MS5611`, `baro_math -1` picks the compensation
  formula automatically)
- **IMU orientation**: same PCB family and mounting direction as the YaoKun S3 —
  auto-selected per bus (calibrated against the Betaflight Configurator 3D model):
  I2C 6050 → CW270, SPI 6500 → CW90; an explicit `gyro_align` always wins
- **RC**: SBUS (GPIO4); no spare UART, no ELRS channel on this board
- **Ground station**: Betaflight / Cleanflight Configurator (MSP v2)
- **Misc**: buzzer GPIO25 (active), onboard single LED GPIO2,
  battery sense GPIO35 (100K+100K 1:2 divider, **ADC1** — works while Wi-Fi is on)

> ★ This firmware is **attitude-stabilised + manual throttle only**: no GPS or rangefinder.
> An optional MS5611 barometer is for altitude display / debugging only —
> **no altitude control**.
>
> - **It does not hover when you release the sticks** — attitude is held but horizontal
>   velocity carries on
> - **Letting go of the throttle means losing altitude**
> - Fly the first time in a **wide open area, low altitude, with prop guards**

## 2. Version and provenance

| Item | Value |
| --- | --- |
| Firmware version | **V1.1** (ESP-FC YaoKun Edition · HLG 2.0 adaptation) |
| Brand | Hardware (c) MildlySpicyDragon (malagis) · Firmware adaptation YaoKunSmart |
| Build environment | `pio run -e esp32_hlg20` |
| Build time | Nov 27 2026 21:18:55 |
| Toolchain | PlatformIO Core (espressif32 + arduino) |
| Key build flags | `-DESPFC_TARGET_HLG20` `-DESPFC_DEV_PRESET_BRUSHED` |
| Application size | 1,038,944 B (0xFDA60) |

> 🔴 **Neither macro may be removed**:
> `-DESPFC_TARGET_HLG20` selects the HLG pin map (otherwise upstream's classic-ESP32 template
> drives motors on 27/25/4/12 — where **25 is the buzzer** — and a UART steals motor pins
> 33/32; no motors turn and the buzzer screams); `-DESPFC_DEV_PRESET_BRUSHED` switches the
> output from DShot to PWM (the 8520 coreless motors are **brushed**, and a brushed ESC only
> understands PWM — otherwise all four motors stay dead).

## 3. How to flash

### Option A — single file (★ brand-new board / calibration data disposable, simplest)

```bash
esptool --chip esp32 --port COMx --baud 460800 write_flash 0x0 "MildlySpicyDragon_火龙果2.0_ESP-FC耀坤适配版_V1.1_20261127_merged.bin"
```

For a GUI use the [ESP Tool Website](https://espressif.github.io/esptool-js/):
connect → add `MildlySpicyDragon_火龙果2.0_ESP-FC耀坤适配版_V1.1_20261127_merged.bin` → Flash Address `0x0` → Program.

⚠️ If you tick **DoNotChgBin**: the SPI mode/frequency/size are already encoded in the image
header; rewriting them breaks the checksum.

### Option B — by segment (★ use this if your board is already calibrated)

A full-chip write from `0x0` erases the NVS region `0x9000~0xE000`, which means your PID
tuning and accelerometer calibration are gone.

```bash
esptool --chip esp32 --port COMx --baud 460800 write_flash \\
  0x1000   "bootloader.bin" \\
  0x8000   "partitions.bin" \\
  0x10000  "firmware.bin"
```

(`boot_app0.bin` normally does not need reflashing.)

> 🔴 **Two different addresses, do not mix them up**: flash the single-file
> `merged.bin` as one image at `0x0` (the image already places the bootloader
> at `0x1000` internally). `0x1000` is only for a **standalone bootloader.bin**
> on a classic ESP32 (S3 uses `0x0`).

> 🔴 **Mandatory when switching board types**: if this board previously ran ESP-FC built for
> another board, stale NVS pin values (e.g. S3's CS=42) **override** the HLG defaults.
> After flashing run `defaults` → `save` → `reboot` in the CLI.

## 4. How to verify you flashed this exact build

**① Compare the hash** (most reliable, no power needed):

```cmd
certutil -hashfile "MildlySpicyDragon_火龙果2.0_ESP-FC耀坤适配版_V1.1_20261127_merged.bin" SHA256
```

```bash
sha256sum "MildlySpicyDragon_火龙果2.0_ESP-FC耀坤适配版_V1.1_20261127_merged.bin"
```

→ must equal **90a475dffd93e90ba6fbd2da9964b692aba7a575cf498b553fd35c9ce34201e7**

**② Serial confirmation**

Attach **UART0 (onboard CH340 USB port, GPIO1/3, 115200 8N1)** and open it at 115200 baud.
The first screen should show a multi-line **IDENTITY banner**: hardware `(c) MildlySpicyDragon
(malagis)`, the 2025 Spark Program award explicitly credited to the MildlySpicyDragon project,
firmware adaptation by YaoKunSmart, version V1.1 — matching YaoKunDrone and Flix organized
editions. Then type `version` to confirm, and `status` / `dump` in the CLI — save the `dump`
output as your baseline.

**③ Search plaintext inside the bin** (no device needed):

- search `esp-fc` → hit (product name string)
- search for `MSP` / `Betaflight` related strings to confirm the protocol stack is linked in

**④ Read the image header from flash** (read-only, changes nothing):

```bash
esptool --chip esp32 --port COMx read_flash 0x10000 0x200 app_hdr.bin
```

→ the first byte must be `E9` (ESP image magic).

## 5. Artifacts and checksums (SHA-256)

| Artifact | Flash address | SHA-256 | Size |
| --- | --- | --- | --- |
| `bootloader.bin` | `0x1000` | `7da2252586bc50961e0692b4aeef79d6569fa257466246c860965101e4165476` | 18,976 B (0x4A20) |
| `partitions.bin` | `0x8000` | `9d237d2449dfaaae40077a90f7f9f5731112bff6a30e6c7824be80d5fb039953` | 3,072 B (0xC00) |
| `boot_app0.bin` | `0xE000` | `f94c5d786a7a8fab06ac5d10e33bf37711a6697636dc037559ea19cc410a17f0` | 8,192 B (0x2000) |
| `firmware.bin` | `0x10000` | `4051097836ccc7604bc70e51895a6b2c5a93213ff1e0fc14581ce6ddb6e157dd` | 1,038,944 B (0xFDA60) |
| **合并单文件固件** | `0x0` 整体刷 | `90a475dffd93e90ba6fbd2da9964b692aba7a575cf498b553fd35c9ce34201e7` | 1,105,920 B (0x10E000) |

- Merged layout: `0x1000` bootloader (classic ESP32; 0x0-0x1000 padded with 0xFF) `+ 0x8000` partitions `+ 0xE000` boot_app0 `+ 0x10000`
  application (gaps padded with 0xFF)
- Flash size: **4 MB** (double-check with `esptool image-info <bin>`)
- 应用程序镜像头：`E9 05 02 20` → SPI 模式 **DIO**、段数 **5**、入口 **0x40088954**
- bootloader 镜像头：`E9 03 02 20` → SPI 模式 **DIO**

## 6. Five things to do after flashing

1. **Clear stale NVS** (when switching board types): CLI `defaults` → `save` → `reboot`
2. **Redo the accelerometer calibration** (if a full-chip write wiped NVS): hold still ≥2 s on
   each of the six faces
3. **Motor test without props**: throttle must spin diagonal pairs (mixer index ≠ silkscreen
   M1~M4, see troubleshooting)
4. **Check the voltage reading against a multimeter**: the configurator value must match the
   measured value (this validates `ESPFC_ADC_SCALE = 2.0f/4096`)
5. **Enable notches once the props are on**: brushed motors are noisy — type
   `set gyro_notch_count 3` in the CLI

## 7. Troubleshooting

| Symptom | Root cause | Fix |
| --- | --- | --- |
| Configurator cannot see the board | Wrong env (must be `esp32_hlg20`) | Rebuild with the matching env |
| No serial output at all on boot | CH340 driver missing / loose UART0 wiring | Install the CH340 driver, check GPIO1/3 |
| Flashing fails / boot loops | GPIO12 pulled high (optical-flow module MIS pull-up) | Unplug the flow module; permanently fix with the 3.3V eFuse or a 10k pull-down |
| **None of the four motors turn** | Missing `-DESPFC_DEV_PRESET_BRUSHED` | Add it and rebuild |
| **Buzzer runs constantly** | You flashed upstream's `esp32` build (its motor table drives PWM onto GPIO25, the buzzer) | Flash `esp32_hlg20` instead |
| Throttle does not spin diagonal pairs | Mixer index ≠ silkscreen M1~M4 (crossed by one) | Verify `OUTPUT_0=27(RR) 1=33(FR) 2=26(RL) 3=32(FL)` |
| Nose up renders nose down (pitch/roll both inverted) | Module inserted 180° flipped (sockets accept both directions) | Mark the reference orientation; or live-test with CLI `set gyro_align CW270` (6050); note that `exit` reboots and drops unsaved values |
| Attitude off by 90°/180° after swapping IMU | NVS has a stale explicit `gyro_align` value | CLI `set gyro_align DEFAULT` → `save` to restore auto-detect |
| Voltage reads zero / half the real value | Wrong `ESPFC_ADC_SCALE`, or ADC moved to an ADC2 pin | Keep GPIO35 (ADC1); divider factor fixed at `2.0f/4096` |
| Attitude frozen / sensor lost | Wrong IMU chip select / wiring | SPI 6500 CS=5; I2C 6050 SDA=21 / SCL=22 |
| Barometer not found | Loose wiring or SDA/SCL swapped (pulls the whole I2C bus down) | Check VCC/GND/SDA(21)/SCL(22) one by one; re-seat to recover |

## 8. What's new for the HLG 2.0 in V1.1

- **Fixed Configurator permanently disabling the gyro after a save**: as on the
  YaoKun S3, `MSP_SET_SENSOR_ALIGNMENT` (220) no longer rewrites `gyro_dev` from
  `gyro_enable_mask`, so a momentary detection miss can no longer persist `NONE`
  to NVS. **Startup beep, status beeps, LED effects and all other sensor
  settings are unchanged**.
- **Fixed buzzer sounding continuously at power-on**: the GPIO25 buzzer is
  active-high, so `pin_buzzer_invert` now ships as `0` (non-inverted). **Startup
  beep, all status beeps and all LED effects are unchanged**; `beeperMask` and
  every sound / light setting remain as upstream.
- **Hardware ownership**: PCB hardware design (c) MildlySpicyDragon (malagis);
  the 2025 Spark Program award belongs to the MildlySpicyDragon project.
  YaoKunSmart only maintains the ESP-FC firmware adaptation — the two brands are
  independent, as reflected in the boot IDENTITY banner.
- **All sensors default to AUTO**: plug in MPU6050 / MPU6500 / MPU9250 IMUs,
  HMC5883L / QMC5883L mags, BMP280 / SPL06-001 / MS5611 barometers and they are
  auto-detected — no CLI configuration needed.
- **Board-level adaptation**: `TargetESP32HLG20.h` (pins aligned with the
  `BOARD_HLG_V2` conventions of flix / YaoKunDrone — both match pin-for-pin) and the
  `esp32_hlg20` build environment.
- **IMU orientation reuses auto-detection**: same PCB family as the YaoKun S3 —
  CW270 (I2C 6050) / CW90 (SPI 6500) work as-is, no CLI configuration needed.
- **MS5611 barometer driver** available (I2C socket); `baro_math -1` auto-detects clones.
- **Optical flow (PMW3901) is out of scope**: ESP-FC 0.3.0 has no flow-device driver;
  GPIO12/13/14/15 are registered but unused.
- **Release sanitisation**: build-machine paths / account names removed from the
  firmware image (app checksum recomputed).

## 9. Find us

- Hardware & original project: Bilibili [MildlySpicyDragon](https://space.bilibili.com/544479100) ·
  OSHWHub [malagis](https://oshwhub.com/malagis/esp32-mini-plane)
- Firmware adaptation: Bilibili [YaoKunSmart](https://space.bilibili.com/3707011699050767) ·
  GitHub: <https://github.com/YaoKunS> ·
  Taobao: [YaoKunSmart](https://shop35432590.taobao.com/)

---

Auto-generated by `Firmware/tools/pack_release.py`; hashes, segment layout, image headers and
build time are extracted live from the firmware image and match the bins exactly.
The published artifacts contain **no local machine paths**.
