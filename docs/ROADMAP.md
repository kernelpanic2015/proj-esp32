# proj-esp32 development roadmap

This roadmap turns the agreed base architecture into incremental, testable stages. The guiding rule is: **the cloud manages; the device controls**. Once configured, local automation must continue without Wi-Fi, Internet, MQTT, web UI or an external agent.

## Architectural invariants

1. **Modular components** — adding or replacing a sensor/actuator changes its driver/component module, not the core.
2. **Explicit state and health** — every fallible subsystem exposes state, health, last success, last error and fault reason.
3. **Fault isolation** — one failed sensor or cable does not stop unrelated sensors, relays or local rules.
4. **FSM-first recovery** — retries, backoff, degraded operation, recovery and safe-state behavior are explicit state transitions; blocking retry loops are forbidden.
5. **Multiple cooperative FSMs** — supervisor, network, storage, update and future component FSMs progress independently through short non-blocking `run_machine()`/`tick()` calls.
6. **Local autonomy** — rules and schedules execute locally from persisted configuration.
7. **Persistent critical state** — identity, configuration, rules, schedules and update metadata live in internal flash/NVS; the SD card is not required for core operation.
8. **Single health model** — TFT, Preact, HTTP API, MQTT telemetry and future agents consume the same component registry/health model.
9. **Safe updates** — A/B OTA, signed release metadata, compatibility checks, boot validation and rollback are core platform capabilities.
10. **No private signing keys in Git** — private update keys stay outside the repository; only public verification material may be committed.

## Storage model

- Firmware: internal flash, dual OTA slots.
- Critical mutable configuration: NVS.
- Recovery UI/minimal internal assets: LittleFS.
- Full Preact application, logs, history, large assets and application data: display microSD.

Current 4 MB flash baseline is A/B capable. The target custom layout is:

```text
nvs        20 KiB
otadata      8 KiB
app0     1728 KiB
app1     1728 KiB
littlefs  512 KiB
coredump   64 KiB
```

## Stage 0 — Baseline and observability [validated]

- ESP32 board/flash/serial identified.
- PlatformIO build/upload chain validated.
- Wi-Fi provisioning and FSM validated.
- HTTP status and WebSerial validated.
- MQTT/TLS to CloudAMQP validated.
- MQTT command -> ESP32 -> event round trip validated.
- PubSubClient selected as MQTT client.

## Stage 1 — Firmware identity, partition policy and signing foundation [validated]

Deliverables:

- custom 4 MB partition CSV with larger A/B application slots;
- explicit firmware identity: model, hardware revision, semantic version, monotonic build number and channel;
- identity/version exposed in `/api/status` and MQTT telemetry;
- local P-256 update signing keypair generated outside the repository;
- public verification key committed to the repository;
- deterministic release manifest format;
- build/release script producing firmware hash + signed manifest;
- local signature verification smoke test;
- determine whether the current Arduino/ESP32 bootloader build enables native rollback and document the result.

Acceptance criteria:

- build succeeds with the custom partition table;
- firmware fits both OTA slots with healthy headroom;
- signing private key is absent from Git and protected locally;
- a generated manifest verifies successfully against the committed public key;
- device still boots, reconnects to Wi-Fi/MQTT and reports its identity/version.

## Stage 2 — Update Manager state machine [validated]

Create a dedicated non-blocking `UpdateService`/FSM. Initial states:

```text
IDLE
CHECKING
AVAILABLE
DOWNLOADING
VERIFYING
INSTALLING
PENDING_REBOOT
PENDING_VALIDATION
VALID
FAILED
ROLLBACK
```

The update engine is transport-independent. Web, MQTT and automatic checks only request actions from this service.

Required checks before installation:

- manifest schema supported;
- model matches device model;
- hardware revision compatible;
- channel allowed;
- remote monotonic build > local build (unless an explicit development override is used);
- signed manifest valid;
- downloaded firmware SHA-256 matches signed manifest;
- image fits target OTA slot.

## Stage 3 — Web update path [validated signed package path]

Recovery/minimal web UI must provide:

- current model / hardware / firmware / build;
- `Check for update`;
- update progress/status;
- manual signed package upload for recovery;
- clear failure reason without taking unrelated services offline.

API direction:

```text
GET  /api/update/status
POST /api/update/check
POST /api/update/apply
POST /api/update/upload
```

The full Preact UI later consumes the same API from the SD card.

## Stage 4 — Boot validation and rollback [validated]

A newly installed image starts as pending validation. Validation must test local platform health, not Internet availability.

Candidate validation signals:

- firmware booted without panic/watchdog;
- NVS available;
- LittleFS available or correctly degraded;
- supervisor and core FSMs progressing;
- heap above defined floor;
- networking stack initialized (Internet/MQTT may remain degraded).

On success, mark the image valid. On failure/reboot loop, return to the last known-good image when bootloader capability permits. If native rollback is unavailable in the current framework build, implement/document the compatible fallback before calling this stage complete.

## Stage 5 — Remote transport, MQTT triggers, persisted policy and automatic scheduler [validated]

Remote signed check/apply, MQTT `firmware.check` / `firmware.update`, persistent NVS update policy, and a nonblocking automatic check scheduler have all been proven on the physical ESP32. Bare `firmware.check` resolves the stored HTTPS manifest URL, while the automatic scheduler triggers that same check path after the configured boot-relative interval. Automatic scheduling is check-only and never auto-applies firmware.

MQTT may request update actions but never transports the firmware payload.

Examples:

```text
firmware.check
firmware.update
```

The ESP32 fetches the signed manifest and firmware directly over HTTPS.

Automatic policy compares remote and local monotonic build numbers at a configured interval. A failed update does not disable normal local control.

## Stage 6 — Core modular runtime [in progress]

Introduce:

- [x] TaskScheduler cooperative runtime alongside `arduino-fsm`;
- [x] `Component` interface;
- [x] `ComponentRegistry`;
- [x] common `ComponentHealth` model;
- [x] bounded internal event bus foundation;
- [x] physically prove first TaskScheduler migration using the automatic OTA check path;
- [x] wire the first real component (`connectivity`) into the registry;
- [x] standardized component fault metadata (`ComponentHealth`);
- [x] generic registry serialization exposed at `/api/components` and embedded in `/api/status`/MQTT telemetry;
- [x] route component state/health transitions through the bounded `EventBus`;
- [ ] `Supervisor` FSM;
- [ ] migrate additional periodic/retry work to TaskScheduler where it improves consistency (MQTT reconnect, telemetry, future sensors/actuators).

Rule: drivers know hardware; components know behavior; services know communication; supervisor knows only state/health.

## Stage 7 — Persistent configuration and local rule engine

Implement versioned, validated, transactional configuration with rollback to previous configuration.

Core services:

- `ConfigurationStore`;
- `RuleEngine`;
- `Scheduler`;
- dependency/fault policies for actuators.

A configured rule such as `heater ON below 16 C / OFF above 18 C` must continue operating with all external connectivity removed.

## Stage 8 — RTC, display, touch and SD foundation

- DS3231 time service + NTP synchronization when available;
- ILI9488 TFT;
- touch controller confirmation/driver;
- microSD filesystem;
- Preact/Vite static application served from SD;
- LittleFS recovery UI remains available without SD.

## Stage 9 — Health monitor UI

The local TFT and Preact UI consume the common component registry.

Status convention:

- green: OK;
- yellow: DEGRADED / STALE / RECOVERING;
- red: FAULT;
- blue: special activity such as firmware update;
- gray: DISABLED/not configured.

Do not rely on color alone: always include icon/text/state.

The first detected component error is shown immediately, while recovery proceeds independently. Recent fault history remains visible after recovery.

## Stage 10 — Sensors and actuators as plug-in modules

Each future sensor/actuator owns its driver and internal FSM. Typical sensor states:

```text
DISABLED -> PROBING -> READY -> STALE/FAULT -> BACKOFF -> RECOVERING
```

A sensor fault can disable only dependent outputs according to an explicit policy (`SAFE_OFF`, `SAFE_ON`, `KEEP_LAST_STATE`, `DISABLE_RULE`, `ALARM_ONLY`) while unrelated channels continue normally.

This stage is intentionally open-ended: new hardware should be additive rather than a core rewrite.
