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
│   └── /webserial
├── messaging
│   └── MQTT
└── hardware (later)
    ├── TFT_eSPI
    ├── XPT2046 touch
    ├── sensors
    └── relays/actuators
```

## State machine

The first firmware base uses `jonblack/arduino-fsm` as the high-level coordinator.

Initial states:

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

A double reset inside the configured detection window requests a recovery/configuration boot. The initial implementation uses `ESP_DoubleResetDetector` behind a narrow recovery concept so that the archived dependency can later be replaced without changing the rest of the firmware.

Provisioning is provided by WiFiManager. Initial AP identity:

`proj-esp32-setup`

After provisioning, the device should normally join the saved Wi-Fi without hard-coded credentials in the repository.

## Web services

Once Wi-Fi is connected, the firmware exposes:

- `/` — human-readable device landing page
- `/api/status` — machine-readable state, IP, RSSI, uptime and MQTT status
- `/webserial` — WebSerial browser console

The intended mDNS hostname is:

`proj-esp32.local`

## MQTT

Initial broker target:

`kpnote.local:1883`

Initial topic root:

`lab/proj-esp32`

Planned topics are derived from the device identifier, for example:

```text
lab/proj-esp32/<device-id>/state
lab/proj-esp32/<device-id>/telemetry
lab/proj-esp32/<device-id>/events
lab/proj-esp32/<device-id>/cmd
```

The base firmware should publish an online/heartbeat state and subscribe to the command topic. Commands must remain intentionally small and auditable; unrestricted shell-like behavior does not belong on the ESP32.

## OTA

ArduinoOTA is intended as the first OTA mechanism. USB/CP2102 remains the recovery path.

The normal development progression becomes:

```text
first/recovery flash -> USB
normal iteration     -> OTA
runtime observation  -> WebSerial + MQTT + serial fallback
```

## Relationship to the wider lab

The longer-term device path is:

```text
AI / agent
    |
   MCP
    |
notebook device manager
    |
   MQTT
    |
  ESP32
    |
TFT / touch / sensors / relays
```

The ESP32 is the physical edge node, not the AI runtime itself.
