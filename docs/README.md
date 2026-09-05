# Documentation index

This directory is the canonical handoff for `proj-esp32`.

## Read first in a new chat

1. [`BOOTSTRAP.md`](BOOTSTRAP.md) — current validated state, environment, Aurora control path and next safe actions.
2. [`hardware.md`](hardware.md) — confirmed MCU/board/flash/serial facts and GPIO constraints.
3. [`architecture.md`](architecture.md) — firmware architecture, state machine and network services.
4. [`mqtt.md`](mqtt.md) — validated RabbitMQ/CloudAMQP MQTT/TLS setup, topics and smoke-test procedure.
5. [`operations.md`](operations.md) — PlatformIO/Aurora build, upload, serial observation and Git synchronization workflow.
6. [`dependencies.md`](dependencies.md) — why each firmware dependency was chosen and replacement/licensing caveats.
7. [`references.md`](references.md) — board page, datasheet/pinout source and relevant upstream libraries/projects.

## Current milestones

- [x] CP2102 detected on Linux
- [x] ESP32 identified with esptool
- [x] full flash erase validated
- [x] PlatformIO build/upload smoke test validated
- [x] runtime heartbeat read back from ESP32 over serial
- [x] GitHub repository created and local project linked
- [x] exact PlatformIO board ID `nodemcu-32s` verified
- [x] base firmware dependencies compile together
- [x] double-reset recovery path validated with controlled first/second reset
- [x] WiFiManager config portal runs nonblocking and AP `proj-esp32-setup` is visible
- [x] Wi-Fi provisioned and STA `ONLINE` state validated
- [x] Web UI `/`, `/api/status` and `/webserial` validated over STA Wi-Fi
- [x] MQTT client migrated to `PubSubClient` 2.8.x
- [x] MQTT/TLS 8883 authenticated connection validated against CloudAMQP/RabbitMQ
- [x] broker-side MQTT connection visible in RabbitMQ dashboard
- [x] telemetry publish validated at ~10-second intervals
- [x] command subscribe and `ping` -> `events` round-trip validated end-to-end
- [ ] replace development `setInsecure()` with CA certificate validation
- [ ] add MQTT LWT/retained offline state and reconnect backoff/jitter
- [ ] OTA validated over Wi-Fi
- [ ] TFT controller and pin mapping confirmed
- [ ] XPT2046 touch validated

## Current runtime state

As validated on 2026-09-05:

- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`
- FSM: `ONLINE`
- MQTT: connected
- MQTT transport: TLS on port 8883
- broker: CloudAMQP/RabbitMQ
- root topic: `lab/proj-esp32`

The ESP32 publishes state/telemetry/events and subscribes to its command topic. Broker/Wi-Fi credentials are persisted locally and must not be committed.

## Source of truth

The local working tree is:

`/home/kernelpanic/Projects/proj-esp32`

The remote repository is:

`kernelpanic2015/proj-esp32`

Desired invariant after every validated change:

```text
local main == origin/main
```
