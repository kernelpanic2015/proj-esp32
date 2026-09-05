# Firmware architecture

## Goals

`proj-esp32` is not intended to become a single monolithic Arduino sketch. It is the base firmware for a manageable edge device that can later expose physical I/O, TFT/touch interaction, telemetry and controlled actions to higher-level automation/AI systems.

The architectural priorities are:

- explicit device state
- recoverable provisioning
- observable runtime
- non-destructive remote management
- MQTT as device/event transport
- web UI/console for local human access
- OTA for post-bootstrap updates
- clear separation between board hardware, networking and application logic

## High-level stack

```text
ESP32 firmware
├── recovery
│   └── double-reset detector
├── state machine
│   └── arduino-fsm
├── network
│   ├── Wi-Fi
│   ├── WiFiManager provisioning portal
│   ├── mDNS
│   └── OTA
├── web
│   ├── ESPAsyncWebServer
│   ├── /api/status
│   ├── /config/mqtt
│   └── /webserial
├── messaging
│   ├── PubSubClient
│   ├── WiFiClient / WiFiClientSecure
│   └── NVS-backed broker configuration
└── hardware (later)
    ├── TFT_eSPI
    ├── XPT2046 touch
    ├── sensors
    └── relays/actuators
```

## State machine

The firmware uses `jonblack/arduino-fsm` as the high-level coordinator.

Current states:

```text
BOOT
 ├─ double reset ──> CONFIG_PORTAL
 └─ normal ────────> WIFI_CONNECTING

CONFIG_PORTAL ──> WIFI_CONNECTING

WIFI_CONNECTING
 ├─ success ───────> ONLINE
 └─ failure ───────> OFFLINE

ONLINE
 └─ Wi-Fi lost ────> OFFLINE

OFFLINE
 └─ Wi-Fi restored -> ONLINE
```

Later events should be queued rather than allowing arbitrary asynchronous callbacks to directly mutate application state.

Future states may include:

- `OTA_UPDATING`
- `SAFE_MODE`
- `ERROR`
- `DISPLAY_INIT`
- `HUMAN_CONFIRMATION`

## Recovery / provisioning

A double reset inside the configured detection window requests recovery/configuration boot. `ESP_DoubleResetDetector` is kept behind a narrow recovery concept so the archived dependency can later be replaced without changing the rest of the firmware.

Provisioning is provided by WiFiManager. Recovery AP identity:

`proj-esp32-setup`

After provisioning, the device normally joins saved Wi-Fi without hard-coded credentials in the repository.

## Web services

Once Wi-Fi is connected, the firmware exposes:

- `/` — human-readable device landing page
- `/api/status` — machine-readable state, IP, RSSI, uptime and MQTT status
- `/config/mqtt` — local broker configuration persisted to NVS
- `/webserial` — browser runtime console

mDNS hostname:

`proj-esp32.local`

## MQTT / RabbitMQ

MQTT is the device/event transport. The validated client is `PubSubClient` 2.8.x.

Current validated broker path:

```text
ESP32
  |
  | MQTT/TLS 8883
  v
CloudAMQP / RabbitMQ
  |
  +-- MQTT clients
  +-- future AMQP workers
  +-- future MCP/backend consumers
```

Validated CloudAMQP hostname:

`jackal.rmq.cloudamqp.com`

Credentials are provisioned at runtime and stored in NVS; they do not belong in source control.

Topic root:

`lab/proj-esp32`

Per-device topics:

```text
lab/proj-esp32/<device-id>/state
lab/proj-esp32/<device-id>/telemetry
lab/proj-esp32/<device-id>/events
lab/proj-esp32/<device-id>/cmd
```

Current behavior:

- subscribe to `/cmd`
- publish retained online state on `/state`
- publish heartbeat/status telemetry about every 10 seconds
- publish command responses on `/events`
- process intentionally small commands such as `ping`, `status` and `reboot`

Unrestricted shell-like behavior does not belong on the ESP32.

The end-to-end `ping` round-trip through RabbitMQ has been validated. See `mqtt.md`.

## MQTT hardening boundary

Current development TLS uses `WiFiClientSecure::setInsecure()`. This proves encrypted transport but does not authenticate the broker certificate.

Before production use, the messaging layer should add:

- CA certificate validation
- LWT retained offline state
- reconnect backoff/jitter
- explicit topic permissions per device
- QoS policy
- a dedicated nonblocking `MQTTService` extracted from `main.cpp`

The user's older `kernelpanic2015/MQTT-LIB` is useful as a design reference because it wraps PubSubClient, but its blocking reconnect loop and non-TLS `WiFiClient` implementation must not be copied unchanged.

## OTA

ArduinoOTA is the first OTA mechanism. USB/CP2102 remains the recovery path.

Normal development progression:

```text
first/recovery flash -> USB
normal iteration     -> OTA (after validation)
runtime observation  -> WebSerial + MQTT + serial fallback
```

## Relationship to the wider lab

Longer-term device path:

```text
AI / agent
    |
   MCP
    |
backend / device manager
    |
RabbitMQ
    |
 MQTT/TLS
    |
  ESP32
    |
TFT / touch / sensors / relays
```

The ESP32 is the physical edge node, not the AI runtime itself.
