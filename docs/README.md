# Documentation index

This directory is the canonical handoff for `proj-esp32`.

## Core baseline

**Core Foundation v1 is complete and reusable.** Stages 0-7 are the common platform baseline. Start new Core/application work at [`CORE_BASELINE.md`](CORE_BASELINE.md); `core-v1.0.0` is the first stable baseline name.

RTC/display/touch/SD and physical sensors/actuators are optional application/module directions, not mandatory continuation stages.

## Read first in a new chat

1. [`CORE_BASELINE.md`](CORE_BASELINE.md) — Core boundary, baseline/versioning model, telemetry feedback loop and rules for new applications/forks.
2. [`BOOTSTRAP.md`](BOOTSTRAP.md) — current validated state, environment, Aurora control path and safe operating facts.
3. [`ROADMAP.md`](ROADMAP.md) — historical Core stages 0-7 plus reference directions that applications may choose or ignore.
4. [`ota.md`](ota.md) — A/B firmware update architecture, rollback lifecycle and update control surfaces.
5. [`ota-test-log.md`](ota-test-log.md) — physical-device OTA validation and rollback test evidence.
6. [`hardware.md`](hardware.md) — confirmed MCU/board/flash/serial facts and GPIO constraints.
7. [`architecture.md`](architecture.md) — firmware architecture, state machine and network services.
8. [`mqtt.md`](mqtt.md) — validated RabbitMQ/CloudAMQP MQTT/TLS setup, topics and smoke-test procedure.
9. [`operations.md`](operations.md) — PlatformIO/Aurora build, upload, serial observation and Git synchronization workflow.
10. [`runtime-test-log.md`](runtime-test-log.md) — physical validation evidence for the TaskScheduler + FSM modular runtime migration.
11. [`configuration.md`](configuration.md) — Stage 7 transactional NVS configuration model and local-control contract.
12. [`dependencies.md`](dependencies.md) — why each firmware dependency was chosen and replacement/licensing caveats.
13. [`references.md`](references.md) — board page, datasheet/pinout source and relevant upstream libraries/projects.

## Current milestones

- [x] CP2102 detected on Linux
- [x] ESP32 identified with esptool
- [x] PlatformIO build/upload smoke test validated
- [x] exact PlatformIO board ID `nodemcu-32s` verified
- [x] double-reset recovery path validated
- [x] Wi-Fi provisioned and STA `ONLINE` state validated
- [x] HTTP `/api/status` and WebSerial validated
- [x] MQTT client migrated to `PubSubClient` 2.8.x
- [x] MQTT/TLS 8883 authenticated connection validated against CloudAMQP/RabbitMQ
- [x] telemetry publish and command round-trip validated
- [x] 4 MB custom A/B partition layout built and flashed: 1728 KiB app0 + 1728 KiB app1 + 512 KiB filesystem partition
- [x] bootloader rollback capability confirmed enabled in the installed ESP-IDF/Arduino framework
- [x] firmware identity endpoint `/api/version` validated on hardware
- [x] Web OTA service/FSM compiled, flashed and `/api/update/status` validated on hardware
- [x] local ECDSA P-256 firmware signing keypair generated outside Git; private key permissions owner-only
- [x] public update verification key committed under `keys/update-signing-public.pem`
- [x] deterministic signed manifest generation and OpenSSL verification smoke-tested
- [x] browser/Web OTA app0/app1 slot switching proven
- [x] Arduino weak-hook behavior identified and `verifyRollbackLater()` overridden
- [x] application-controlled `PENDING_VERIFY -> VALID` proven on hardware with `0.1.3/build 4`
- [x] controlled validation failure profile `nodemcu-32s-rollback-test` built and signed
- [x] bootloader rollback proven: `0.1.4-rollback-test/app0/PENDING_VERIFY -> 0.1.3/app1/VALID`
- [x] Wi-Fi and NVS-backed MQTT configuration proven to survive the rollback cycle
- [x] require signed package verification on-device before accepting firmware
- [x] remote signed manifest check + firmware download/apply path validated on hardware
- [x] MQTT `firmware.check <url>` / `firmware.update` triggers validated through the real broker
- [x] persist remote-update policy in NVS; reboot/OTA persistence and bare `firmware.check` proven
- [x] nonblocking automatic update-check scheduler proven on hardware
- [x] TaskScheduler + arduino-fsm cooperative runtime foundation; automatic scheduler migration proven on hardware
- [x] first real ComponentRegistry entry (`connectivity`) + `/api/components` shared health API implemented
- [x] standardized ComponentHealth metadata + bounded EventBus transition routing
- [x] MQTT reconnect + telemetry timing migrated to TaskScheduler and physically proven
- [x] Wi-Fi reconnect timing migrated to TaskScheduler and physically proven
- [x] add Supervisor FSM over the common component health model and physically prove `RUNNING -> DEGRADED -> RUNNING`
- [x] Stage 7A transactional ConfigurationStore: apply/reject/reboot/rollback/OTA persistence physically validated
- [x] Stage 7B minimal RuleEngine + virtual I/O semantics physically validated
- [x] Stage 7C TaskScheduler/EventBus one-shot rule runtime physically validated, including offline execution
- [x] Stage 7D persisted rule binding + boot/apply/rollback lifecycle physically validated
- [x] Stage 7E local persisted delayed-action service; physical offline/reboot/rollback/clean-OTA proof validated
- [x] Stage 7F all five dependency/fault policies + recovery physically validated
- [x] Stage 7 closed on clean `0.1.41/build 42`
- [x] reusable Core baseline documented for future applications/forks
- [ ] replace development `setInsecure()` with CA certificate validation
- [ ] add MQTT LWT/retained offline state and reconnect backoff/jitter
- [ ] mount LittleFS and add recovery UI
- [ ] application-specific hardware tracks as required

## Current runtime state

Validated on the physical device on 2026-09-06 after Stage 7 closure:

- firmware `0.1.41/build 42`, `app0/VALID`, `ONLINE`;
- Wi-Fi + MQTT/TLS connected; Supervisor `RUNNING/OK`; EventBus `dropped=0`;
- ConfigurationStore revision 10; rule `persisted.demo.a`; schedule `persisted.demo.delay.clean`;
- RuleRuntime `ARMED`, default/legacy `SAFE_OFF`, work task disabled while idle;
- schedule completed with work task disabled; remote OTA HTTPS-only; lab endpoints absent.

**Stage 7 is closed and physically validated (7A-7F).** This state is the first reusable Core Foundation baseline.

## OTA partition layout

```text
4 MB flash
├── nvs        20 KiB
├── otadata     8 KiB
├── app0      1728 KiB
├── app1      1728 KiB
├── filesystem 512 KiB
└── coredump    64 KiB
```

`platformio.ini` selects `board_build.filesystem = littlefs`; the partition CSV currently uses the ESP32 data subtype traditionally named `spiffs` for that filesystem region.

## Storage direction

```text
internal flash
├── firmware app0/app1
├── NVS: critical configuration/rules/update metadata
├── LittleFS: recovery UI/minimal internal assets
└── coredump

microSD
├── compiled Preact application
├── assets
├── logs/history
└── bulk application data
```

Configured local automation must remain functional without SD, Wi-Fi, Internet, MQTT or external agents.

## Source of truth

The local working tree is:

`/home/kernelpanic/Projects/proj-esp32`

The remote repository is:

`kernelpanic2015/proj-esp32`

Desired invariant after every validated change:

```text
local main == origin/main
```
