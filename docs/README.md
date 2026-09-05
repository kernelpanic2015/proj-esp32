# Documentation index

This directory is the canonical handoff for `proj-esp32`.

## Read first in a new chat

1. [`BOOTSTRAP.md`](BOOTSTRAP.md) — current validated state, environment, Aurora control path and next safe actions.
2. [`ROADMAP.md`](ROADMAP.md) — staged development plan from the current base through OTA, modular runtime, local rules, display and future sensors/actuators.
3. [`ota.md`](ota.md) — A/B firmware update architecture, rollback lifecycle and update control surfaces.
4. [`hardware.md`](hardware.md) — confirmed MCU/board/flash/serial facts and GPIO constraints.
5. [`architecture.md`](architecture.md) — firmware architecture, state machine and network services.
6. [`mqtt.md`](mqtt.md) — validated RabbitMQ/CloudAMQP MQTT/TLS setup, topics and smoke-test procedure.
7. [`operations.md`](operations.md) — PlatformIO/Aurora build, upload, serial observation and Git synchronization workflow.
8. [`dependencies.md`](dependencies.md) — why each firmware dependency was chosen and replacement/licensing caveats.
9. [`references.md`](references.md) — board page, datasheet/pinout source and relevant upstream libraries/projects.

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
- [x] 4 MB custom A/B partition layout built and flashed: 1728 KiB app0 + 1728 KiB app1 + 512 KiB LittleFS partition
- [x] bootloader rollback capability confirmed enabled in the installed ESP-IDF/Arduino framework
- [x] firmware identity endpoint `/api/version` validated on hardware
- [x] Web OTA service/FSM compiled, flashed and `/api/update/status` validated on hardware
- [x] local ECDSA P-256 firmware signing keypair generated outside Git; private key permissions set to owner-only
- [x] public update verification key committed under `keys/update-signing-public.pem`
- [x] deterministic signed manifest generation and OpenSSL verification smoke-tested
- [x] OTA candidate `0.1.1` build `2` built and signed
- [ ] perform first browser Web OTA `0.1.0 -> 0.1.1` and validate app0 -> app1 + `PENDING_VERIFY -> VALID`
- [ ] deliberately fail a candidate validation and prove bootloader rollback to last known-good image
- [ ] require signed package verification on-device before accepting firmware
- [ ] add remote signed manifest download and automatic/MQTT update triggers
- [ ] replace development `setInsecure()` with CA certificate validation
- [ ] add MQTT LWT/retained offline state and reconnect backoff/jitter
- [ ] mount LittleFS and add recovery UI
- [ ] TFT controller and pin mapping confirmed
- [ ] XPT2046 touch validated

## Current runtime state

As validated on 2026-09-05:

- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`
- firmware currently flashed: `0.1.0`, build `1`, channel `dev`
- hardware model: `proj-esp32-35`, revision `1`
- running OTA partition after serial baseline flash: `app0`
- FSM: `ONLINE`
- MQTT: connected
- MQTT transport: TLS on port 8883
- broker: CloudAMQP/RabbitMQ
- root topic: `lab/proj-esp32`

The signed `0.1.1` / build `2` candidate exists locally on `kpnote` under `/tmp/proj-esp32-release-0.1.1/` for the next Web OTA smoke test. Broker/Wi-Fi credentials and the firmware signing private key are local-only and must not be committed.

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
