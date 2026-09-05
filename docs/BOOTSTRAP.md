# proj-esp32 — bootstrap / handoff

Use this file to resume the project in a new ChatGPT conversation without reconstructing the environment from memory.

## Identity

- Project: `proj-esp32`
- GitHub: `kernelpanic2015/proj-esp32`
- Notebook/device: `kpnote`
- Local path: `/home/kernelpanic/Projects/proj-esp32`
- Primary language: C++
- Build system: PlatformIO Core CLI
- Framework: Arduino core for ESP32
- PlatformIO board ID: `nodemcu-32s`
- Serial port: `/dev/ttyUSB0`

## Confirmed board

Retail board identification: NodeMCU-32S, 38 pins, ESP-WROOM-32 module, CP2102 USB/UART bridge.

Direct `esptool` probe on the connected board confirmed:

- chip: ESP32-D0WD-V3
- silicon revision: v3.0
- features: Wi-Fi + Bluetooth, dual core, 240 MHz
- crystal: 40 MHz
- flash: 4 MB
- flash voltage: 3.3 V

Linux USB/udev confirmed CP2102 (`10c4:ea60`) using the `cp210x` driver and exposing `/dev/ttyUSB0`.

## Validated execution chain

The following path has already been tested end-to-end:

`ChatGPT -> GitHub issue -> Aurora Client -> kpnote -> PlatformIO -> /dev/ttyUSB0 -> ESP32 -> serial output`

A smoke firmware was compiled, uploaded and observed emitting:

- `ESP32_SMOKE_BOOT_OK`
- `ESP32_SMOKE_HEARTBEAT_OK`

Before that smoke test the ESP32 flash was intentionally erased completely. There is no old firmware that needs to be preserved.

## Aurora control plane

Aurora jobs are submitted as strict JSON in issues in `kernelpanic2015/aurora-kpnote`, then labeled `aurora:queued`.

Canonical shape:

```json
{
  "schema": "aurora.job.v1",
  "name": "job-name",
  "cwd": "/home/kernelpanic/Projects/proj-esp32",
  "argv": ["/bin/bash", "-lc", "command"],
  "timeout_seconds": 120
}
```

Aurora Watch is read-only and may be unavailable. The Aurora Client writes the resulting local job UUID into the GitHub issue comment. The external Watch API can be consulted as:

`https://jobs.omni-one.org/api/watch/jobs/{jobId}`

When detailed stdout is needed even if Watch is unavailable, have the Aurora command post an output file back to its GitHub issue with `gh issue comment ... --body-file ...`.

## PlatformIO environment

The project keeps a dedicated PlatformIO virtual environment at `.venv-platformio/` and a stable wrapper:

```bash
./scripts/pio
```

Typical commands:

```bash
./scripts/pio run
./scripts/pio run -t upload --upload-port /dev/ttyUSB0
./scripts/pio run -t erase --upload-port /dev/ttyUSB0
./scripts/pio device list
```

For Aurora/non-interactive serial observation, use pyserial or direct serial reads. `pio device monitor` expects an interactive terminal and has failed under non-interactive Aurora jobs.

## Firmware architecture being implemented

Dependencies selected for the base firmware:

- `jonblack/arduino-fsm` — high-level device state machine
- `khoih-prog/ESP_DoubleResetDetector` — double-reset recovery trigger
- `tzapu/WiFiManager` — captive provisioning portal
- `ESP32Async/AsyncTCP`
- `ESP32Async/ESPAsyncWebServer` — asynchronous HTTP/WebSocket base
- `ayushsharma82/WebSerial` — browser console at `/webserial`
- `256dpi/arduino-mqtt` — MQTT client
- built-in mDNS and ArduinoOTA support

Initial service identity:

- hostname: `proj-esp32`
- config AP: `proj-esp32-setup`
- initial MQTT target: `kpnote.local:1883`
- MQTT root: `lab/proj-esp32`

The MQTT endpoint is intentionally just an initial default. It can later move into persisted provisioning/configuration.

## State-machine direction

High-level intended states:

`BOOT -> CONFIG_PORTAL | WIFI_CONNECTING -> ONLINE | OFFLINE`

Expected recovery path:

`double reset -> CONFIG_PORTAL`

Network/MQTT/Web/TFT callbacks should eventually produce events; the FSM should be the single owner of high-level device state.

## Hardware integration still pending

The user has a color TFT + resistive touch setup from older ESP32 work. Historical libraries likely included:

- `TFT_eSPI`
- `XPT2046_Touchscreen`
- possibly an ILI9488 / ILI9486 / ILI9341 display controller

Do not assume the display controller or TFT CS/DC/RST/touch pins until the actual module pinout is confirmed.

## GPIO rules already adopted

- logic is 3.3 V; GPIOs are not 5 V tolerant
- GPIO34, 35, 36, 39 are input-only
- GPIO6..11 are normally reserved for module flash and must not be used
- GPIO0, 2, 5, 12, 15 are boot strapping pins; use with care
- GPIO1/3 are UART0/CP2102 and should remain free while USB serial/debug is required
- default I2C: GPIO21 SDA, GPIO22 SCL
- VSPI starting point: GPIO18 SCK, GPIO19 MISO, GPIO23 MOSI

See `include/board_pins.h` and `docs/hardware.md`.

## Immediate next validation

After pulling the latest `main` onto `kpnote`:

1. build all selected dependencies together;
2. fix any Arduino-core/library compatibility issues;
3. upload the base firmware;
4. validate double-reset recovery/config portal;
5. provision Wi-Fi;
6. validate `/`, `/api/status`, `/webserial`;
7. validate MQTT publish/subscribe with the broker reachable from `kpnote`;
8. validate OTA;
9. then begin TFT/touch bring-up.
