<!-- markdownlint-disable MD041 -->

<div align="center">

# 🛩️ ESP-FC Flight Controller · YaoKun Chinese Fork

**A mini, low-cost, high-performance ESP32 flight controller for hobbyists**

[![MCU](https://img.shields.io/badge/MCU-ESP32%20%7C%20ESP32--S3%20%7C%20RP2040-purple)](https://www.espressif.com/)
[![Build](https://img.shields.io/badge/Build-PlatformIO-orange)](https://platformio.org/)
[![Config](https://img.shields.io/badge/Config-Betaflight%20v10.10%20compatible-green)](https://github.com/betaflight/betaflight-configurator)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Upstream](https://img.shields.io/badge/Upstream-rtlopez%2Fesp--fc-lightgrey)](https://github.com/rtlopez/esp-fc)

[**简体中文**](README.md) · **English**

</div>

---

> 📌 **This repository is a Chinese-documented fork of [rtlopez/esp-fc](https://github.com/rtlopez/esp-fc).**
> The firmware source is kept **100% identical to upstream** (only the directory layout changed,
> not a single line of logic). What this fork adds: Chinese documentation and a reorganized
> directory structure.
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