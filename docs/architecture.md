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

OTA uses the project's signed A/B UpdateManager path. Unsigned ArduinoOTA was removed so there is a single firmware trust path: signed manifest verification, firmware SHA-256 verification, inactive-slot write, `PENDING_VERIFY`, application validation and bootloader rollback. USB/CP2102 remains the recovery path.

Normal development progression:

```text
first/recovery flash -> USB
normal iteration     -> signed Web/remote OTA
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


## Cooperative runtime: TaskScheduler + FSM (Stage 6A)

The project now adopts `arkhipenko/TaskScheduler` alongside `jonblack/arduino-fsm`.
Their responsibilities are intentionally different:

- **TaskScheduler = when work becomes eligible to run**;
- **FSM = current state and whether that work is legal/meaningful**;
- **EventBus = what happened**;
- **Component = who owns the behavior**;
- **Supervisor = aggregate health/recovery policy**;
- **RuleEngine = desired functional outcome**.

A task may remain disabled until work is meaningful. Delayed activation/restart is a
first-class mechanism for sensor warm-up, actuator settling, retry/backoff and
minimum on/off times. Components should prefer TaskScheduler timing primitives to
hand-rolled `millis()` polling as they are migrated.

The first migration is the automatic firmware-check scheduler. Its low-frequency
policy watcher is always enabled, while the actual remote-check task is disabled
until persisted `policy.enabled=true`; enabling the policy arms it with a delayed
first run. The OTA path remains check-only and does not auto-apply firmware.

Stage 6 core contracts now exist under `include/core` / `src/core`:
`Component`, `ComponentHealth`, `ComponentRegistry`, and a bounded `EventBus`.
The registry is discovery/health metadata, not a polling loop: execution cadence
belongs to TaskScheduler.

### First physical TaskScheduler migration proof

The automatic firmware-check scheduler was migrated from hand-written `millis()` polling to TaskScheduler. A controlled `0.1.15-remote-test/build 16` image persisted an enabled 60 s policy, rebooted, re-armed the delayed task, and reached remote `AVAILABLE` at about 60.5 s without any manual or MQTT `firmware.check`. `attempt_count=1` and `accepted_count=1` were observed. Only an explicit operator apply installed `0.1.16/build 17`, which completed `PENDING_VERIFY -> VALID`. This validates the intended rule that scheduled work may stay disabled until meaningful and that automatic scheduling does not imply automatic actuation/install.


## Component registry integration (Stage 6B)

The first concrete component is `connectivity`. It does not own network transport implementation yet; it owns the connectivity state/health interpretation that the rest of the platform can consume consistently.

TaskScheduler samples the component every 2 s. The component itself decides its state and health:

```text
STARTING -> ONLINE      health=OK
         -> WIFI_ONLY   health=DEGRADED, mqtt_not_configured|mqtt_disconnected
         -> OFFLINE     health=DEGRADED, wifi_disconnected
```

Network loss is deliberately `DEGRADED`, not a platform-wide `FAULT`, because configured local control must continue without connectivity.

State/health transitions are posted to the bounded `EventBus`; the current handler only logs them. This creates the event boundary needed for the future Supervisor without letting asynchronous callbacks directly mutate unrelated FSMs.

`GET /api/components` now exposes the registry plus EventBus counters. The same registry JSON is embedded in `/api/status`, therefore it is also present in existing MQTT status/telemetry payloads. This is the first end-to-end use of the shared health model by API and messaging surfaces. As this enlarges the shared telemetry document, the PubSubClient packet buffer was raised to 2048 bytes to preserve headroom as more components are added.


### Stage 6B physical proof

A signed `0.1.17/build 18` image was installed on the physical ESP32 and completed `PENDING_VERIFY -> VALID` on `app0`. After network settlement, `/api/components` exposed `connectivity` as `ONLINE` / `OK`, `/api/status` embedded the same registry, MQTT/TLS was connected, and EventBus reported zero dropped events. The PubSubClient packet buffer is 2048 bytes to retain telemetry headroom as the common component model grows. This establishes the first real end-to-end component using TaskScheduler cadence + component-owned state/health + EventBus transitions + shared API/MQTT serialization.


## Supervisor FSM (Stage 6C)

The Supervisor is a separate `arduino-fsm` state machine evaluated by a TaskScheduler task. It does not operate hardware and does not own network transport. It reads only the shared `ComponentRegistry` health model and derives aggregate platform health.

```text
ComponentRegistry -> Supervisor.evaluate() -> arduino-fsm
                                      |
                                      +-> RUNNING
                                      +-> DEGRADED
                                      +-> FAULT
```

`INITIALIZING` maps to health `RECOVERING`; all enabled components healthy maps to `RUNNING/OK`; any component `DEGRADED` or `RECOVERING` maps the platform to `DEGRADED`; any component `FAULT` maps it to `FAULT`. Disabled optional components do not by themselves degrade the platform.

TaskScheduler owns the 1 s evaluation cadence. State transitions are posted to the bounded EventBus as `SupervisorStateChanged`, keeping the Supervisor observable without allowing it to reach into component internals. `/api/supervisor` exposes the aggregate state, counts per health class, transition timestamp and evaluation count. The same object is embedded into `/api/status` and therefore existing MQTT telemetry.

Stage 6C includes a lab-only MQTT disconnect endpoint in the already test-gated build profile. It suppresses MQTT reconnect briefly so the physical device can prove `RUNNING -> DEGRADED -> RUNNING` while Wi-Fi and HTTP remain available. Production/default builds do not expose this endpoint.


Stage 6C proof-note: the first signed lab image physically validated Supervisor `RUNNING/OK`, but the controlled MQTT-disconnect route was missing due to an integration patch mismatch. The proof was stopped without simulating success; the route and `/api/status.supervisor` embedding were corrected and the retry uses fresh monotonic builds.


### Stage 6C physical proof and closure

Stage 6C is physically validated. A real MQTT disconnect with Wi-Fi/HTTP preserved caused `connectivity=ONLINE/OK -> WIFI_ONLY/DEGRADED` (`mqtt_disconnected`) and Supervisor `RUNNING/OK -> DEGRADED`. After reconnect both recovered to `ONLINE/OK` and `RUNNING/OK`; EventBus dropped count stayed zero. A clean `0.1.20/build 21` image was then installed on `app1`, reached `VALID`, and did not expose the test-only disconnect endpoint.

This validates the ownership boundary: Supervisor observes aggregate health but does not own transport recovery or local functional control. Stage 6D may migrate MQTT reconnect and telemetry timing to TaskScheduler without changing this contract.


## MQTT TaskScheduler migration (Stage 6D)

Stage 6D removes the hand-written `lastMqttAttempt` and `lastHeartbeat` timers from the main loop. Three cooperative tasks now separate eligibility from work:

```text
mqttCoordinatorTask (250 ms, lightweight)
    |-- disconnected + eligible -> enable/force mqttReconnectTask
    |-- connected -> disable reconnect, delayed-enable telemetry
    `-- unavailable/portal/not configured -> disable both work tasks

mqttReconnectTask (5 s retry interval)
    `-- attempts the existing MQTT connect operation, disables itself on success

mqttTelemetryTask (10 s periodic)
    `-- publishes the existing shared status document only while connected
```

The important platform rule is preserved: work tasks remain disabled when their work is meaningless. `PubSubClient::loop()` remains a fast per-loop cooperative service call for now; Stage 6D changes timing/eligibility, not the proven transport implementation. The synchronous `PubSubClient::connect()` body is intentionally unchanged in this migration and can be hardened separately if connection latency later becomes a scheduling problem.

`GET /api/mqtt/runtime` exposes scheduler/counter state without credentials so reconnect and telemetry cadence can be physically validated.
