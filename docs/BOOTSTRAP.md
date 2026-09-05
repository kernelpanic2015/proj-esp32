# proj-esp32 — bootstrap / handoff

Use this file to resume the project in a new ChatGPT conversation without reconstructing the environment from memory.

## Identity

- Project: `proj-esp32`
- GitHub: `kernelpanic2015/proj-esp32`
- Repository visibility: private
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

The complete development path is working:

`ChatGPT -> GitHub issue -> Aurora Client -> kpnote -> PlatformIO -> /dev/ttyUSB0 -> ESP32 -> serial/WebSerial/MQTT output`

The ESP32 flash was intentionally erased during bootstrap; no legacy firmware needs to be preserved.

## Current firmware state — validated 2026-09-05

The current firmware has been compiled, flashed and validated online.

Resolved dependency set:

- arduino-fsm 2.2.0
- ESP_DoubleResetDetector 1.3.2
- WiFiManager 2.0.17
- PubSubClient 2.8.0
- AsyncTCP 3.5.0
- ESPAsyncWebServer 3.12.0
- WebSerial 2.1.2
- ArduinoOTA 2.0.0
- ESPmDNS 2.0.0
- Preferences / WiFi / WiFiClientSecure from Arduino-ESP32

Latest measured PubSubClient build footprint:

- RAM: 54,532 / 327,680 bytes (16.6%)
- application flash partition: 1,143,265 / 1,310,720 bytes (87.2%)

The default OTA-capable partition still fits, but flash headroom is now limited. Any TFT/UI/assets phase must watch binary growth carefully.

## Recovery and provisioning — validated

`ESP_DoubleResetDetector` is active and tested using controlled hardware reset pulses:

1. first reset -> normal path -> `FSM -> WIFI_CONNECTING`;
2. second reset inside detection window -> `DOUBLE_RESET_DETECTED`;
3. double reset -> `FSM -> CONFIG_PORTAL`.

The DRD object is constructed inside `setup()` after runtime/NVS initialization; constructing it globally previously caused an EEPROM/NVS initialization error.

WiFiManager runs the config portal in nonblocking mode. Recovery/config AP:

- SSID: `proj-esp32-setup`
- AP IP: `192.168.4.1`

Wi-Fi credentials have since been provisioned successfully. Normal boot reaches STA `ONLINE`.

## Current online services — validated

Current device identity:

- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`
- validated LAN IP during tests: `192.168.1.101`

Validated endpoints:

- `http://proj-esp32.local/`
- `http://proj-esp32.local/api/status`
- `http://proj-esp32.local/webserial`
- `http://proj-esp32.local/config/mqtt`

`/api/status` reports Wi-Fi, IP, RSSI, MQTT state, TLS flag, uptime and free heap.

## MQTT / RabbitMQ baseline — validated end-to-end

The device now uses **PubSubClient** instead of `256dpi/arduino-mqtt`.

Validated broker target:

- service: CloudAMQP / RabbitMQ
- hostname: `jackal.rmq.cloudamqp.com`
- MQTT/TLS port: `8883`
- transport: `WiFiClientSecure`
- current development TLS mode: encrypted but certificate verification disabled with `setInsecure()`

Do **not** commit the broker password, full credential URL, Wi-Fi password or other secrets. MQTT configuration is stored in ESP32 NVS through `/config/mqtt`.

Topic root:

`lab/proj-esp32`

Current device topics:

```text
lab/proj-esp32/10A2CCEF49C0/state
lab/proj-esp32/10A2CCEF49C0/telemetry
lab/proj-esp32/10A2CCEF49C0/events
lab/proj-esp32/10A2CCEF49C0/cmd
```

Validated behavior:

- authenticated MQTT/TLS session appears in RabbitMQ dashboard
- ESP32 subscribes to `/cmd`
- ESP32 publishes retained online state on `/state`
- telemetry is published about every 10 seconds
- notebook published `ping` to `/cmd`
- WebSerial showed `MQTT RX .../cmd => ping`
- ESP32 replied with status JSON on `/events`
- notebook subscriber received the `/events` response

This validates the complete cloud round-trip:

```text
notebook -> MQTT/TLS -> CloudAMQP/RabbitMQ -> ESP32
ESP32    -> MQTT/TLS -> CloudAMQP/RabbitMQ -> notebook
```

See `docs/mqtt.md` for reproducible smoke-test commands.

### MQTT migration incident worth remembering

`256dpi/arduino-mqtt`/lwmqtt repeatedly reached TLS successfully but failed the MQTT handshake with `err=-9 rc=6`. A manual preconnected `WiFiClientSecure` socket did not fix it.

The project was migrated to PubSubClient. PubSubClient initially returned `state=4` (bad credentials); re-saving the correct MQTT password in ESP32 NVS fixed authentication immediately. PubSubClient is the validated MQTT client for the current baseline.

## Serial observation rule

Do not open pyserial with default DTR/RTS states on this CP2102 board when the goal is passive monitoring; it can reset the ESP32 and interfere with double-reset detection.

Use:

```bash
.venv-platformio/bin/python scripts/capture_serial.py --seconds 10
```

The helper configures DTR/RTS before opening the port.

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

Aurora Watch is read-only. For important diagnostics, capture stdout/stderr and post the result back to the issue with `gh issue comment ... --body-file ...`.

## PlatformIO environment

Dedicated environment: `.venv-platformio/`

Wrapper:

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

Current services:

- WiFiManager provisioning portal
- mDNS `proj-esp32.local`
- async HTTP server
- `/`, `/api/status`, `/config/mqtt`
- `/webserial`
- ArduinoOTA
- Preferences/NVS MQTT configuration
- PubSubClient over WiFiClient/WiFiClientSecure

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

Historical clues for the user's TFT/touch hardware:

- `TFT_eSPI`
- `XPT2046_Touchscreen`
- likely ILI9488 / ILI9486 / ILI9341 display controller family

Do not assume display controller or TFT CS/DC/RST/touch pins until the module is identified.

## Immediate next steps

1. harden MQTT: LWT/offline retained state and reconnect backoff/jitter;
2. replace development `setInsecure()` with CA certificate validation and time synchronization if needed;
3. consider extracting MQTT behavior from `main.cpp` into a local `MQTTService` inspired by `kernelpanic2015/MQTT-LIB`, while keeping reconnect nonblocking;
4. validate OTA over Wi-Fi;
5. begin TFT + XPT2046 bring-up only after the networking baseline remains stable.
