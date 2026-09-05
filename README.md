# proj-esp32

Firmware laboratory for the user's **NodeMCU-32S / ESP-WROOM-32** board, developed in **C++ with PlatformIO** on the notebook `kpnote`.

The project is designed to be driven both interactively from VS Code and remotely through the Aurora command plane.

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
- Local project path: `/home/kernelpanic/Projects/proj-esp32`
- GitHub: `kernelpanic2015/proj-esp32`

## Firmware direction

The base firmware is evolving toward a reusable edge-device runtime with:

- finite-state machine (`jonblack/arduino-fsm`)
- double-reset recovery/config mode (`ESP_DoubleResetDetector`)
- Wi-Fi provisioning portal (`WiFiManager`)
- asynchronous HTTP server
- browser WebSerial console
- MQTT client
- mDNS hostname
- OTA updates
- later: TFT display, XPT2046 resistive touch, sensors/relays, telemetry and MCP/AI integration

## Console workflow

```bash
cd /home/kernelpanic/Projects/proj-esp32
./scripts/pio run
./scripts/pio run -t upload --upload-port /dev/ttyUSB0
```

For non-interactive runtime capture under Aurora, prefer pyserial instead of `pio device monitor`.

## Documentation

Start at [`docs/README.md`](docs/README.md). New chats should read [`docs/BOOTSTRAP.md`](docs/BOOTSTRAP.md) first.
