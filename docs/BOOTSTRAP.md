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

Direct `esptool` probe confirmed:

- chip: ESP32-D0WD-V3
- silicon revision: v3.0
- Wi-Fi + Bluetooth, dual core, 240 MHz
- crystal: 40 MHz
- flash: 4 MB
- flash voltage: 3.3 V

Linux USB/udev confirmed CP2102 (`10c4:ea60`) using `cp210x` and exposing `/dev/ttyUSB0`.

## Validated execution chain

The complete path is working:

`ChatGPT -> GitHub issue -> Aurora Client -> kpnote -> PlatformIO -> /dev/ttyUSB0 -> ESP32 -> serial output`

The ESP32 flash was intentionally erased before the project firmware was built. No legacy firmware needs to be preserved.

## Current firmware state — validated 2026-09-05

The actual base firmware has been compiled and flashed successfully for `nodemcu-32s`.

Installed dependency set as resolved by PlatformIO:

- arduino-fsm 2.2.0
- ESP_DoubleResetDetector 1.3.2
- WiFiManager 2.0.17
- MQTT / arduino-mqtt 2.5.3
- AsyncTCP 3.5.0
- ESPAsyncWebServer 3.12.0
- WebSerial 2.1.2
- ArduinoOTA 2.0.0
- ESPmDNS 2.0.0

Last measured build footprint:

- RAM: about 53.5 KB / 327.7 KB (16.3%)
- application flash partition: about 1.01 MB / 1.31 MB (77.1%)

The default OTA-capable partition layout is still usable, but flash growth must be watched when TFT/UI libraries are added.

## Recovery and provisioning — validated

`ESP_DoubleResetDetector` is active and has been tested using controlled hardware reset pulses:

1. first reset -> normal path -> `FSM -> WIFI_CONNECTING`;
2. second reset inside the detection window -> `DOUBLE_RESET_DETECTED`;
3. double reset -> `FSM -> CONFIG_PORTAL`.

The first implementation exposed an EEPROM/NVS initialization error because the DRD object was constructed globally. This was fixed by constructing it inside `setup()` after the Arduino/ESP32 runtime initializes NVS. Current serial validation shows no NVS initialization error.

WiFiManager now runs its config portal in **nonblocking mode**, so `drd->loop()` and the FSM continue running while provisioning is open.

The ESP currently has no saved Wi-Fi credentials because flash was erased. It therefore starts the provisioning AP:

- SSID: `proj-esp32-setup`
- AP IP: `192.168.4.1`

The AP was confirmed both in ESP32 serial output and from the notebook's Wi-Fi scan at strong signal.

The last controlled test ended with the ESP in `CONFIG_PORTAL`, so it should currently be advertising `proj-esp32-setup` unless it was reset/powered off afterward.

## Serial observation rule

Do not open pyserial with default DTR/RTS states on this CP2102 board when the goal is passive monitoring: doing so can generate an unintended ESP32 reset and can accidentally look like a double reset.

Use the repository utility:

```bash
.venv-platformio/bin/python scripts/capture_serial.py --seconds 10
```

It configures DTR/RTS before opening the port so passive capture does not reset the ESP32.

## Aurora control plane

Aurora jobs are submitted as strict JSON in issues in `kernelpanic2015/aurora-kpnote`, then labeled `aurora:queued`.

```json
{
  "schema": "aurora.job.v1",
  "name": "job-name",
  "cwd": "/home/kernelpanic/Projects/proj-esp32",
  "argv": ["/bin/bash", "-lc", "command"],
  "timeout_seconds": 120
}
```

Aurora Watch is read-only and may be unavailable. Aurora writes the local job UUID into the GitHub issue comment after execution. The external read endpoint is:

`https://jobs.omni-one.org/api/watch/jobs/{jobId}`

For important diagnostics, have the Aurora job post its own captured stdout/stderr back into the issue using `gh issue comment ... --body-file ...`.

## PlatformIO environment

A dedicated PlatformIO environment lives at `.venv-platformio/`, with wrapper:

```bash
./scripts/pio
```

Common commands:

```bash
./scripts/pio run
./scripts/pio run -t upload --upload-port /dev/ttyUSB0
./scripts/pio run -t erase --upload-port /dev/ttyUSB0
./scripts/pio device list
```

## Active firmware architecture

High-level FSM:

`BOOT -> CONFIG_PORTAL | WIFI_CONNECTING -> ONLINE | OFFLINE`

Current services coded into the firmware:

- WiFiManager provisioning portal
- mDNS target hostname `proj-esp32.local`
- async HTTP server
- `/` landing endpoint
- `/api/status` JSON endpoint
- `/webserial` browser console
- ArduinoOTA
- MQTT client

Initial service identity:

- hostname: `proj-esp32`
- config AP: `proj-esp32-setup`
- initial MQTT broker target: `kpnote.local:1883`
- MQTT root: `lab/proj-esp32`

The MQTT broker target is only the first integration default and should later become provisioned/persisted configuration.

## What is implemented but not yet end-to-end validated

Because no Wi-Fi credentials are currently stored, the firmware has not yet reached STA `ONLINE` state in this build. Therefore these are compiled and flashed but still need network validation:

- `http://proj-esp32.local/`
- `/api/status`
- `/webserial`
- MQTT connect/publish/subscribe to `kpnote.local:1883`
- OTA over Wi-Fi

The next human action is to provision the ESP through `proj-esp32-setup` (preferably from a phone or another device so the `kpnote` network path to Aurora is not interrupted).

## GPIO rules already adopted

- logic is 3.3 V; GPIOs are not 5 V tolerant
- GPIO34, 35, 36, 39 are input-only
- GPIO6..11 are reserved for module flash
- GPIO0, 2, 5, 12, 15 are boot strapping pins; use with care
- GPIO1/3 are UART0/CP2102 and should remain free while USB serial/debug is required
- default I2C: GPIO21 SDA, GPIO22 SCL
- VSPI starting point: GPIO18 SCK, GPIO19 MISO, GPIO23 MOSI

See `include/board_pins.h` and `docs/hardware.md`.

## TFT/touch phase still pending

The user has an older color TFT module with resistive touch and microSD. Historical clues point to:

- `TFT_eSPI`
- `XPT2046_Touchscreen`
- likely ILI9488 / ILI9486 / ILI9341 display controller family

Do not assume the display controller or TFT CS/DC/RST/touch pins until the module is identified.

## Immediate next steps

1. provision Wi-Fi through `proj-esp32-setup`;
2. capture the assigned STA IP and confirm `ONLINE` state;
3. validate `/`, `/api/status`, and `/webserial`;
4. confirm Mosquitto/broker reachability on `kpnote` and validate MQTT publish/subscribe;
5. validate OTA;
6. then begin TFT + XPT2046 bring-up.
