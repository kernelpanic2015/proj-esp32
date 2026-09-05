# Documentation index

This directory is the canonical handoff for `proj-esp32`.

## Read first in a new chat

1. [`BOOTSTRAP.md`](BOOTSTRAP.md) — current validated state, environment, Aurora control path and next safe actions.
2. [`ROADMAP.md`](ROADMAP.md) — staged development plan from the current base through OTA, modular runtime, local rules, display and future sensors/actuators.
3. [`ota.md`](ota.md) — A/B firmware update architecture, rollback lifecycle and update control surfaces.
4. [`ota-test-log.md`](ota-test-log.md) — physical-device OTA validation and rollback test evidence.
5. [`hardware.md`](hardware.md) — confirmed MCU/board/flash/serial facts and GPIO constraints.
6. [`architecture.md`](architecture.md) — firmware architecture, state machine and network services.
7. [`mqtt.md`](mqtt.md) — validated RabbitMQ/CloudAMQP MQTT/TLS setup, topics and smoke-test procedure.
8. [`operations.md`](operations.md) — PlatformIO/Aurora build, upload, serial observation and Git synchronization workflow.
9. [`dependencies.md`](dependencies.md) — why each firmware dependency was chosen and replacement/licensing caveats.
10. [`references.md`](references.md) — board page, datasheet/pinout source and relevant upstream libraries/projects.

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
- [ ] add persisted automatic update-check policy
- [ ] replace development `setInsecure()` with CA certificate validation
- [ ] add MQTT LWT/retained offline state and reconnect backoff/jitter
- [ ] mount LittleFS and add recovery UI
- [ ] TFT/touch/SD pin mapping confirmed physically
- [ ] ILI9488 display bring-up
- [ ] touch controller bring-up

## Current runtime state

Validated directly on the physical device on 2026-09-05 after the MQTT-triggered remote OTA proof:

- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`
- hardware model: `proj-esp32-35`, revision `1`
- firmware: `0.1.10`, build `11`, channel `dev`
- running OTA partition: `app1`
- boot partition: `app1`
- next update partition: `app0`
- native image state: `VALID`
- FSM/system: `ONLINE`
- Wi-Fi: connected
- MQTT: connected
- MQTT transport: TLS
- remote OTA policy: HTTPS-only

MQTT now acts only as a trigger plane for the already validated signed remote UpdateManager. The physical proof published `firmware.check <manifest-url>` and `firmware.update` through the real CloudAMQP broker without exposing credentials to the job; the device fetched/verified/applied the signed package itself and reached `0.1.10/build 11` in `app1/VALID`.

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
