<!-- markdownlint-disable MD041 -->

<div align="center">

# 🛩️ ESP-FC Flight Controller · YaoKun Chinese Edition

**A mini, low-cost, high-performance ESP32 flight controller for hobbyists**

[![MCU](https://img.shields.io/badge/MCU-ESP32%20%7C%20ESP32--S3%20%7C%20RP2040-purple)](https://www.espressif.com/)
[![Build](https://img.shields.io/badge/Build-PlatformIO-orange)](https://platformio.org/)
[![Config](https://img.shields.io/badge/Config-Betaflight%20v10.10%20compatible-green)](https://github.com/betaflight/betaflight-configurator)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Upstream](https://img.shields.io/badge/Upstream-rtlopez%2Fesp--fc-lightgrey)](https://github.com/rtlopez/esp-fc)
[![YaoKun](https://img.shields.io/badge/YaoKun-S3%20Hardware%20Port-c8102e)](Docs/%E8%80%80%E5%9D%A4S3%E9%80%82%E9%85%8D%E8%AF%B4%E6%98%8E.md)

[**简体中文**](README.md) · **English**

</div>

---

> 📌 **This repository is a Chinese-documented fork of [rtlopez/esp-fc](https://github.com/rtlopez/esp-fc),
> plus a YaoKun S3 hardware port.**
> The `master` branch is kept **identical to upstream** (only the directory layout changed,
> not a single line of logic). The `yaokun-organized` branch adds a **YaoKun S3 board-level
> adaptation** on top of that — see
> [YaoKun S3 Edition](#-yaokun-s3-edition-yaokun-organized-branch).
> Upstream author: [Ramon Lopez](https://github.com/rtlopez) · MIT License

## 📌 What is it

ESP-FC is an **open-source flight controller firmware for the ESP32**, designed to be
**mini, low-cost and high-performance**.

Its killer feature is **compatibility**: the firmware deliberately mimics the **Betaflight 4.2**
protocol, so you can configure it with the official
[Betaflight Configurator](https://github.com/betaflight/betaflight-configurator) GUI and analyze
blackbox logs with the official [Blackbox Log Viewer](https://blackbox.betaflight.com/) —
**if you know Betaflight, you already know how to use ESP-FC.**

> ⚠️ Bear in mind it is **not** Betaflight. There are limitations and differences in
> functionality and performance — see below.

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Multi-chip** | ESP32 / ESP32-S3 (recommended), plus ESP32-S2 / C3 / RP2040 / RP2350 / ESP8266 |
| **All ESC protocols** | PWM, Oneshot125/42, Multishot, Brushed, Dshot150/300/600 bidirectional |
| **All RC protocols** | PPM, SBUS, IBUS, CRSF (incl. ELRS) |
| **Built-in ESP-NOW RX** | ESP-NOW receiver + Wi-Fi configuration built in — no extra RX hardware |
| **Many gyros** | SPI and I2C buses: MPU6050, MPU9250, ICM20602, ICM42688, BMI160 |
| **Flight modes** | ACRO, ANGLE, AIRMODE |
| **High loop rate** | Up to **4 kHz** gyro/loop on ESP32 with an SPI gyro |
| **Blackbox** | OpenLog / OpenLager / on-board Flash |
| **MSP + CLI** | Standard MSP protocol and command-line interface |
| **In-flight PID tuning** | Adjust PID in the air without reflashing |
| **Safety** | Failsafe, buzzer, LED, voltage monitoring |
| **Betaflight-compatible** | Configurator v10.10 compatible — reuse your Betaflight tuning knowledge |

---

## 🚁 YaoKun S3 Edition (`yaokun-organized` branch)

This section is the **complete hands-on tutorial for the YaoKun S3 quadcopter hardware**:
wiring, building, flashing, ground-station configuration, and the very first test flight.
If you own a YaoKun board, **this section is all you need**.

### What was adapted

| ID   | File                                                      | Change                                                                |
|------|-----------------------------------------------------------|-----------------------------------------------------------------------|
| **Y1** | `Firmware/lib/Espfc/src/Target/TargetESP32s3YaoKun.h` (new) | YaoKun S3 board pin map, line-by-line matched to the official pin sheet |
| **Y2** | `Firmware/lib/Espfc/src/Target/Target.h`                   | +3 lines: pick the YaoKun target when `-DESPFC_TARGET_YAOKUN` is set    |
| **Y3** | `Firmware/platformio.ini`                                  | Two new build environments: `esp32s3_yaokun` / `esp32s3_yaokun_n4r2`  |
| **Y4** | Build flag `-DESPFC_DEV_PRESET_BRUSHED`                    | Force PWM output — the 8520 coreless motors are **brushed**            |

> ✅ **Zero changes to the algorithm layer.** Attitude estimation (AHRS), filters, PID,
> mixing, the MSP stack and ground-station compatibility are all kept from upstream.
> Upstream's own `[env:esp32s3]` is also **untouched**, so you can always switch and compare.

### Why this is necessary

Upstream `TargetESP32s3.h` targets a **generic S3 template board** (Lolin S3 Mini class) and all
its pin numbers are placeholders. Flashing it onto a YaoKun board gives you:

- ❌ **Not a single motor turns** — upstream drives GPIO 39/40/41/42, the YaoKun ESCs are on **6/5/15/16**
- ❌ **Buzzer runs constantly** — upstream uses GPIO39 as a motor output, but on this board **39 = buzzer**
- ❌ **IMU undetectable** — upstream SPI chip select is 8 and clock is 12; this board is **CS=17, SCK=38**
- ❌ **Battery voltage off by 2×** — upstream ADC is on GPIO1; this board is **GPIO2** with a 1:2 divider

### Complete pin map

**Motor outputs (🔴 8520 coreless brushed motors)**

| Channel            | GPIO      | Silkscreen | Position     |
|--------------------|-----------|------------|--------------|
| `ESPFC_OUTPUT_0`   | **6**     | MOT1_FR    | Front right  |
| `ESPFC_OUTPUT_1`   | **5**     | MOT2_RR    | Rear right   |
| `ESPFC_OUTPUT_2`   | **15**    | MOT3_RL    | Rear left    |
| `ESPFC_OUTPUT_3`   | **16**    | MOT4_FL    | Front left   |

**IMU (gyro/accelerometer)**

| Function        | GPIO      | Note                                                            |
|-----------------|-----------|-----------------------------------------------------------------|
| SPI_SCK         | **38**    |                                                                 |
| SPI_MOSI        | **18**    |                                                                 |
| SPI_MISO        | **21**    |                                                                 |
| **GYRO_CS**     | **17**    | 🔴 **V1 board measured value**; V2 board uses 42                |
| I2C_SCL         | **8**     | 🔴 **SCL=8 and SDA=9 — do not swap**                             |
| I2C_SDA         | **9**     | MPU6050 / BMP280 / magnetometer                                   |

**RC and serial**

| Purpose     | GPIO        | Note                                                        |
|-------------|-------------|-------------------------------------------------------------|
| SBUS input  | **1**       | Sheet pin `EXT01`; SBUS is a **single wire**                   |
| ELRS TX     | **11**      | FC → receiver                                                  |
| ELRS RX     | **12**      | Receiver → FC                                                  |
| UART0 (MSP) | **43/44**   | Primary ground-station port, 115200 8N1                        |
| USB CDC     | —           | Native S3 USB, enumerates as a virtual COM port                |

**Misc**

| Function      | GPIO  | Note                                                                       |
|---------------|-------|-----------------------------------------------------------------------------|
| VBAT sense    | **2** | 1:2 divider ⇒ `ESPFC_ADC_SCALE = 2.0f/4096` (wrong value halves the reading and silences the low-voltage alarm) |
| Buzzer        | **39**| Active buzzer                                                               |
| Blue LED      | **14**| ESP-FC drives a single LED; red 41 / green 7 unused                          |
| Button        | −1    | No dedicated button on this board — use CLI for binding                      |

> ⚠️ **ESP32-S3 forbidden pins**: GPIO26–37 are the internal Flash/PSRAM (touch them and the chip
> won't boot); GPIO0/3/45/46 are boot strapping pins; GPIO43/44 are the only MSP serial port.

### 🔴 8520 coreless = brushed motors, so BRUSHED is mandatory

This is **the one decision that makes the quad completely dead if you get it wrong**.

ESP-FC sends **DShot300** by default — a *digital* protocol that requires a decoding chip inside a
smart ESC. The 8520 coreless motor ships with a **cheap brushed ESC** (basically a switch, a diode
and a commutator) that only understands classic **PWM pulse width**. Sending it DShot is like taping
a note that says "DingDong" on a doorbell: it hears nothing, and **all four motors stay still**.

`-DESPFC_DEV_PRESET_BRUSHED` makes `ModelConfig.h` do three things:

```cpp
output.protocol = ESC_PROTOCOL_BRUSHED;   // switch protocol to PWM
output.async = true;                       // async LEDC output, no CPU cost
output.rate = 3000;                        // 3 kHz
```

We also deliberately **do not** define `ESPFC_DSHOT_TELEMETRY` in the YaoKun target —
bidirectional DShot RPM telemetry only makes sense for smart ESCs; on a PWM ESC it would just
waste a DMA channel and a UART peripheral.

### Picking the right build environment (Flash / PSRAM)

| Item                | `esp32s3_yaokun` (LCSC R8N8) ★ | `esp32s3_yaokun_n4r2` (Supermini) |
|---------------------|-------------------------------|----------------------------------|
| Flash               | 8 MB                          | 4 MB                              |
| PSRAM               | 8 MB **OPI (octal)**          | 2 MB **QIO (quad)**              |
| Partition table     | `default_8MB.csv`             | `partitions_4M_nota.csv`         |
| `memory_type`       | `qio_opi`                     | `qio`                            |

> 🔴 **Wrong choice → immediate panic with no serial output at all, and the ground station cannot
> see the board**: flashing N4R2 with R8N8 parameters overruns the 4 MB app partition and fails OPI
> init. Read the module silkscreen: `R8N8` = 8+8, `N4R2` = 4+2.

### Building

```bash
git clone https://github.com/YaoKunS/esp-fc.git
cd esp-fc
git checkout yaokun-organized
cd Firmware

pio run -e esp32s3_yaokun          # ★ build for R8N8 (common case)
pio run -e esp32s3_yaokun_n4r2     # build for N4R2
pio test -e native                 # run unit tests
```

In VS Code open `esp-fc.code-workspace` and pick `esp32s3_yaokun` in the status bar:

| Action           | Shortcut        |
|------------------|-----------------|
| Build            | `Ctrl+Alt+B`    |
| Upload           | `Ctrl+Alt+U`    |
| Serial monitor   | `Ctrl+Alt+M`    |

The toolchain is installed on first run, so **the first build takes 2–5 minutes** (44 libraries to scan).

### Flashing

**Option A — PlatformIO (recommended, auto-enters bootloader mode)**

```bash
cd Firmware
pio run -e esp32s3_yaokun -t upload --upload-port COM28
pio device monitor --port COM28
```

`use_1200bps_touch`, `wait_for_upload_port` and `require_upload_port` are already enabled, so plugging
in the board is enough — it resets itself into download mode.

**Option B — prebuilt firmware (for distributing to others)**

Firmware lives in [`Firmware/release/`](Firmware/release/) together with **bilingual SHA-256
fingerprint and flashing notes**. Use the
[ESP Tool Website](https://espressif.github.io/esptool-js/):

| File              | Flash address |
|-------------------|---------------|
| `bootloader.bin`  | `0x0`         |
| `partitions.bin`  | `0x8000`      |
| `boot_app0.bin`   | `0xE000`      |
| `firmware.bin`    | `0x10000`     |

> ⚠️ **Do not erase the whole chip.** Parameters persist in the NVS region at `0x9000`; a full-chip
> write wipes your carefully tuned PID and calibration data. Flash **by segment** as in the table above.

**Stuck in download mode after flashing?** First confirm the USB CDC COM port has appeared;
otherwise hold BOOT while resetting, or switch to UART0 (GPIO43/44).

### Initial setup (Betaflight Configurator)

1. **Connect the configurator** — UART0 (43/44) recommended; USB CDC also works
2. **Verify pins in the CLI first** — type `status` and `dump`, save the output as a baseline
3. **Set serial functions** — UART0 = MSP; if ELRS is wired to UART2 (11/12), set its protocol to **CRSF**
4. **Motor test without props** — ⚠️ **remove the propellers first**. All four motors must sound;
   if none do, check that `-DESPFC_DEV_PRESET_BRUSHED` is actually in your build flags
5. **Accelerometer calibration** — hold still ≥2 s on each of the six faces
6. **Fit the props and enable notches** — brushed motors are noisy:
   `set gyro_notch_count 3` in the CLI
7. **Configure failsafe** — pick a strategy that matches your receiver

### Bench checks (most of this needs no props at all)

- Tilt the frame left/right and forward/back — the attitude indicator must follow **in the same direction**
- Unplug the IMU — the configurator should report "sensor lost", not go silent
- Disconnect the receiver — failsafe must engage and the motors must throttle down
- The voltage reading must **match your multimeter** (this validates `ESPFC_ADC_SCALE`)

### ⚠️ Read before the first flight

**ESP-FC is attitude-stabilised + manual throttle only:**

- **It does not hover when you release the sticks** — attitude is held, but horizontal velocity carries on
- **Letting go of the throttle means losing altitude**
- No GPS / barometer / rangefinder ⇒ **no altitude hold, no position hold, no waypoints**

> For the first flight with props: **open field, prop guards, plenty of clearance, low and slow**.
> Pushing the stick forward should tilt the nose **down**. If the direction is reversed, fix the
> mixer order — **do not try to fix it with PID**.

### Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Configurator cannot see the board | Wrong env (Flash/PSRAM mismatch) | Rebuild with `_n4r2` or `esp32s3_yaokun` |
| Stuck in download mode after flashing | USB CDC COM not enumerated | Hold BOOT and reset, or use UART0 |
| No serial output at all on boot | Flash/PSRAM mismatch → panic | Check the environment table above |
| **None of the four motors turn** | **Missing `-DESPFC_DEV_PRESET_BRUSHED`** | Add it and rebuild |
| Only one motor turns | Motor order / wiring | Should be 6/5/15/16 |
| All motors turn but very weak | Voltage scale wrong → false low-voltage | Check `ESPFC_ADC_SCALE = 2.0f/4096` |
| Voltage reading is half the real value | Same as above | Same as above |
| Attitude frozen / sensor lost | IMU chip select wrong (V1=17 / V2=42) | Change `ESPFC_SPI_CS_GYRO` and rebuild |
| **Buzzer runs constantly** | **You flashed upstream's `esp32s3` build** | Flash `esp32s3_yaokun` instead |
| No SBUS signal | Receiver unpowered or no common ground | SBUS is single wire: signal to GPIO1 **plus** GND |
| ELRS receiver gives no data | Protocol not set to CRSF | Set the UART2 protocol to CRSF in the configurator |
| Violent shaking with props fitted | Motor noise into the IMU | `set gyro_notch_count 3` |
| Attitude still drifting after calibration | Calibration never captured all six faces | Redo it, holding still ≥2 s per face |

### Companion documents

- 📘 **[Full technical manual (HTML)](Docs/ESP-FC%E6%8A%80%E6%9C%AF%E8%AF%B4%E6%98%8E%E4%B9%A6.html)** — architecture, control loop, protocols, build system
- 🔧 **[YaoKun S3 adaptation notes](Docs/%E8%80%80%E5%9D%A4S3%E9%80%82%E9%85%8D%E8%AF%B4%E6%98%8E.md)** — root cause and verification for every change
- 🔧 **[Firmware fingerprint & flashing guide](Firmware/release/)** — SHA-256 checks and bilingual flashing instructions

---

## 📁 Directory layout (reorganized in this fork)

> 🔧 **Why reorganize**: upstream keeps the PlatformIO project files, docs, tests and Python
> helper scripts flat in the repo root. This fork moves **everything firmware-related under
> `Firmware/`**, containing a **complete PlatformIO project** (`platformio.ini` sits next to
> `src/`, `lib/`, `test/` and `bin/`), so **`pio run` works immediately after `cd Firmware/` —
> zero configuration changes**.

```text
esp-fc/                        # ← repo root: docs + license
├── README.md                  # Chinese readme (default)
├── README_EN.md               # This file
├── LICENSE                    # MIT License (original author)
├── AGENTS.md                  # AI-assisted development conventions
├── esp-fc.code-workspace      # VS Code workspace (points at Firmware/)
├── Firmware/                  # ★ Firmware project (complete PlatformIO project)
│   ├── platformio.ini         #   ★ Build config: 7 chip targets + native tests
│   ├── partitions_4M_nota.csv  #   Partition table
│   ├── src/                   #   Main program (main.cpp)
│   ├── lib/                   #   Core libraries
│   │   ├── Espfc/             #     Main flight logic (control, sensors, wireless)
│   │   ├── AHRS/              #     Attitude estimation
│   │   ├── EscDriver/         #     ESC protocol drivers
│   │   ├── Gps/               #     GPS support
│   │   ├── EspWire/           #     I2C wrapper
│   │   ├── MultiButton/       #     Button handling
│   │   ├── betaflight/        #     Betaflight protocol compatibility layer
│   │   └── printf/            #     Formatted output
│   ├── include/               #   Public headers
│   ├── test/                  #   Unit tests (16 suites, run under native)
│   ├── bin/                   #   Build helper Python scripts
│   ├── docker/                #   Test container
│   └── docker-compose.yml     #   Container orchestration
├── Docs/                      # ★ Documentation
│   ├── setup.md               #   ★ Setup guide (must read)
│   ├── wiring.md              #   ★ Wiring (must read)
│   ├── cli.md                 #   ★ CLI reference (must read)
│   ├── wireless.md            #   ★ Wi-Fi & ESP-NOW receiver (must read)
│   ├── connections.md         #   Connector definitions
│   ├── development.md         #   Development guide
│   └── internal/              #   Internal design docs
└── .github/workflows/         # CI: unit tests + 7-target builds + artifacts
```

**Before / after:**

| Original path | New path | Why |
|---------------|----------|-----|
| `platformio.ini`, `src/`, `lib/`, `include/`, `test/`, `bin/`, `docker/`, `docker-compose.yml`, `partitions_4M_nota.csv` | All under `Firmware/` | Merged into **one complete PlatformIO project** — internal relative paths unchanged |
| `docs/` | `Docs/` | Documentation |
| `LICENSE`, `AGENTS.md`, `esp-fc.code-workspace` | Repo root | Project-level files |

## 🚀 Quick start

### Hardware

* ESP32 or ESP32-S3 board
* MPU9250 (SPI) or MPU6050 (I2C) gyro (GY-88, GY-91, GY-521 or similar)
* PDB with 5V BEC
* Buzzer and some components (optional)

### Software

* [Betaflight Configurator](https://github.com/betaflight/betaflight-configurator/releases) **v10.10**
* [CH340 USB-serial driver](https://sparks.gogo.co.nz/ch340.html)

### Build from source

```bash
git clone https://github.com/YaoKunS/esp-fc.git
cd esp-fc
git checkout yaokun-organized   # ★ switch to the reorganized branch (master mirrors upstream)
cd Firmware                     # ← PlatformIO project root

pio run -e esp32            # Build for ESP32
pio run -e esp32s3          # Build for ESP32-S3
pio test -e native          # Run unit tests
```

> 💡 You can also open the repo-root `esp-fc.code-workspace` in VS Code (already pointed at
> `Firmware/`) and build/flash with the PlatformIO extension.

### Flashing

**Option 1 — prebuilt firmware**

1. Download the firmware from the [Releases page](https://github.com/rtlopez/esp-fc/releases)
2. Open the [ESP Tool Website](https://espressif.github.io/esptool-js/)
3. Click "Connect" and choose the device port
4. Add the firmware file and set Flash Address to `0x00`
5. Click "Program"
6. Power-cycle the board when done

<img src="Docs/images/esptool-js-flash-connect.png" alt="ESP-FC flashing">

**Option 2 — flash with PlatformIO**

```bash
cd Firmware
pio run -e esp32 --target upload
```

### Initial setup

After flashing, do these four things in order:

1. **Configure the pinout** to match your wiring — especially pin functions (see [CLI reference](Docs/cli.md))
2. **Connect Betaflight Configurator** and configure to your preferences
3. **Test motors without propellers** — ⚠️ **remove the props before powering on**
4. Have fun ;)

> [!NOTE]
> **Rule of thumb**: if you cannot change an option in Betaflight Configurator and it reverts
> after saving, the firmware **does not support** it. Follow the [setup guide](Docs/setup.md) closely.

## 🔌 Wiring diagrams

[![ESP-FC example wiring diagrams](Docs/images/espfc_wiring_combined.png)](Docs/wiring.md)

> ⚠️ **Read before soldering**: wrong wiring is the most common cause of dead chips.
> Double-check every line against the [wiring doc](Docs/wiring.md) before applying power.

## 📡 Hardware & protocol compatibility

### MCU targets

| Chip | Status |
|------|--------|
| **ESP32** | ✅ Recommended |
| **ESP32-S3** | ✅ Recommended |
| ESP32-S2 | ⚠️ Experimental |
| ESP32-C3 | ⚠️ Experimental, lacks performance, no FPU |
| RP2350 | ⚠️ Experimental, partially works |
| RP2040 | ⚠️ Experimental, lacks performance, no FPU |
| ESP8266 | ❌ Obsolete, no longer developed |

### Sensors and protocols

* **Gyros**: MPU6050, MPU6000, MPU6500, MPU9250, ICM20602, ICM42688, BMI160
* **Barometers**: BMP180, BMP280, SPL06
* **Magnetometers**: HMC5883, QMC5883, AK8963, QMC5883P
* **Receivers**: PPM, SBUS, IBUS, CRSF / ELRS
* **ESC protocols**: PWM, BRUSHED, ONESHOT125, ONESHOT42, MULTISHOT, DSHOT150, DSHOT300, DSHOT600
* **GPS**: M8, M9, F9, M10 (dual-band, constellations configurable via CLI)
* **Other**: MSP, CLI, BLACKBOX, ESPNOW

## 📚 Must-read documentation

> [!IMPORTANT]
> Before you begin, **read the following documentation carefully**.

| Document | Contents |
|----------|----------|
| [Setup guide](Docs/setup.md) | Full configuration flow — start here |
| [Wiring](Docs/wiring.md) | Pin definitions and wiring diagrams |
| [CLI reference](Docs/cli.md) | Every command-line command and parameter |
| [Wi-Fi & ESP-NOW receiver](Docs/wireless.md) | Wireless configuration |

Development: [Development guide](Docs/development.md) · [Internal design](Docs/internal/)

Need help? Join the upstream **[Discord channel](https://discord.gg/jhyPPM5UEH)**.

## 🛠️ Development environment

* Visual Studio Code
* [PlatformIO](https://platformio.org/install/ide?install=vscode) extension
* Git

Testing uses [Docker](https://www.docker.com/):

```bash
cd Firmware
docker compose run --rm native     # Run unit tests in a container
```

## 📋 Upstream roadmap

* Altitude hold
* GPS navigation
* MS5611 barometer
* Balancing robot controller

## 📜 License & credits

* **Upstream project**: ESP-FC © [Ramon Lopez](https://github.com/rtlopez) ·
  source at https://github.com/rtlopez/esp-fc
* **License**: **MIT License** (full text in [LICENSE](LICENSE), Copyright (c) 2016 rtlopez)
* **This fork**: Chinese documentation and directory reorganization only.
  **No firmware logic was modified.**
* **Fork maintained by**: YaoKunSmart · https://github.com/YaoKunS
* **Bilibili**: https://space.bilibili.com/3707011699050767

> ⚠️ When using, modifying or redistributing this project, keep the original author's
> attribution and the MIT license notice. MIT permits free use, modification and distribution
> (including commercial use), but **the copyright notice and license text must be retained**.

## 🙏 Support upstream

If you like this project and want it to keep being developed, consider supporting the author:

* BTC: `1Lopez7yPtbyjfLGe892JfheDFJMMt43tW`
* LTC: `LV3G3sJxz9AYpDMYUp8e1LCmerFYxVY3ak`

## ⚠️ Disclaimer

This project is provided "as is", without warranty of any kind. Before soldering and applying
power, please make sure to:

1. Check the [wiring doc](Docs/wiring.md) for voltage polarity and pin definitions
2. **Always remove the propellers for the first power-on** — motors can spin unexpectedly
3. Test in an open area and comply with local drone regulations

⚠️ Neither the author nor this fork is responsible for any damage, injury or loss resulting from
use of this project. **Use at your own risk!**

---

<div align="center">

**🛩️ ESP-FC** — created by [Ramon Lopez](https://github.com/rtlopez) · MIT License
· Chinese fork maintained by [YaoKunSmart](https://github.com/YaoKunS)

</div>