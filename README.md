# proj-esp32

Reusable ESP32 firmware **Core Foundation** for the user's **NodeMCU-32S / ESP-WROOM-32** board, developed in **C++ with PlatformIO** on the notebook `kpnote`.

Stages 0-7 define the validated reusable Core. Application-specific hardware and behavior should branch/fork from a validated Core baseline rather than extending one mandatory hardware roadmap. The project is designed to be driven both interactively from VS Code and remotely through the Aurora command plane.

**Current Core baseline:** `core-v1.0.0` -> firmware `0.1.41/build 42`. See [`docs/CORE_BASELINE.md`](docs/CORE_BASELINE.md).

## Current hardware

- Board family: NodeMCU-32S, 38 pins
- Module: ESP-WROOM-32
- USB/UART bridge: Silicon Labs CP2102 / CP210x
- Detected MCU: ESP32-D0WD-V3, revision 3.0
- CPU: dual core, up to 240 MHz
- Crystal: 40 MHz
- Flash detected by esptool: 4 MB, 3.3 V
- USB serial device on `kpnote`: `/dev/ttyUSB0`

## Development stack

- Language: C++
- Framework: Arduino core for ESP32
- Build/upload: PlatformIO Core CLI
- Board ID: `nodemcu-32s`
- MQTT client: `knolleary/PubSubClient` 2.8.x
- Local project path: `/home/kernelpanic/Projects/proj-esp32`
- GitHub: `kernelpanic2015/proj-esp32`

## Validated baseline — 2026-09-06

**Current physical baseline:** `0.1.41/build 42`, `app0/VALID`, application `ONLINE`, Supervisor `RUNNING/OK`, Wi-Fi + MQTT/TLS connected, EventBus `dropped=0`, ConfigurationStore revision 10, persisted rule `persisted.demo.a`, persisted schedule `persisted.demo.delay.clean`, and legacy/default actuator fault policy `SAFE_OFF`. Lab mutation endpoints are absent.

**Stage 7 is physically validated and closed (7A-7F).** Stage 7F proved `SAFE_OFF`, `SAFE_ON`, `KEEP_LAST_STATE`, `DISABLE_RULE`, and `ALARM_ONLY`, recovery for every policy, and rejection of unsupported policy without revision advance. No physical actuator GPIO was introduced.

The current firmware is online and the complete MQTT/TLS round-trip has been validated against a CloudAMQP RabbitMQ instance:

```text
notebook -> MQTT/TLS 8883 -> RabbitMQ/CloudAMQP -> ESP32
ESP32    -> MQTT/TLS 8883 -> RabbitMQ/CloudAMQP -> notebook
```

Validated runtime services:

- Wi-Fi STA and FSM `ONLINE`
- mDNS at `proj-esp32.local`
- `/`, `/api/status` and `/webserial`
- MQTT over TLS on port 8883
- authenticated RabbitMQ/CloudAMQP session visible in the broker dashboard
- subscribe on `lab/proj-esp32/<device-id>/cmd`
- publish on `state`, `events` and `telemetry`
- command `ping` round-trip with response on `events`
- telemetry heartbeat every ~10 seconds

Broker credentials and Wi-Fi credentials are persisted locally on the ESP32 and are not committed to this repository.

## Core direction

The base firmware **is the reusable edge-device runtime**. Future applications compose or extend it with:

- finite-state machine (`jonblack/arduino-fsm`)
- double-reset recovery/config mode (`ESP_DoubleResetDetector`)
- Wi-Fi provisioning portal (`WiFiManager`)
- asynchronous HTTP server
- browser WebSerial console
- MQTT/TLS client (`PubSubClient` + `WiFiClientSecure`)
- mDNS hostname
- signed A/B OTA updates
- application-specific modules such as TFT display, XPT2046 resistive touch, sensors, relays, telemetry views and MCP/AI integrations

Core `main` should evolve only through reusable fixes, hardening, compatibility work and telemetry-driven platform improvements. Applications own their own hardware-specific roadmap and versioning.

## Console workflow

```bash
cd /home/kernelpanic/Projects/proj-esp32
./scripts/pio run
./scripts/pio run -t upload --upload-port /dev/ttyUSB0
```

For non-interactive runtime capture under Aurora, prefer `scripts/capture_serial.py` instead of `pio device monitor`.

## Documentation

Start at [`docs/CORE_BASELINE.md`](docs/CORE_BASELINE.md), then [`docs/BOOTSTRAP.md`](docs/BOOTSTRAP.md). [`docs/README.md`](docs/README.md) is the complete documentation index. New application chats should identify the Core baseline they derive from before defining external hardware. MQTT/RabbitMQ validation is documented in [`docs/mqtt.md`](docs/mqtt.md).
