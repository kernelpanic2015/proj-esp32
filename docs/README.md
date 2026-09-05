# Documentation index

This directory is the canonical handoff for `proj-esp32`.

## Read first in a new chat

1. [`BOOTSTRAP.md`](BOOTSTRAP.md) — where we are, what is connected, how Aurora controls the notebook, and the next safe actions.
2. [`hardware.md`](hardware.md) — confirmed MCU/board/flash/serial facts and GPIO constraints.
3. [`architecture.md`](architecture.md) — firmware architecture, state machine and network services.
4. [`operations.md`](operations.md) — PlatformIO/Aurora build, upload, erase and serial-observation workflow.

## Current milestones

- [x] CP2102 detected on Linux
- [x] ESP32 identified with esptool
- [x] full flash erase validated
- [x] PlatformIO build/upload smoke test validated
- [x] runtime heartbeat read back from ESP32 over serial
- [x] GitHub repository created and local project linked
- [x] exact PlatformIO board ID `nodemcu-32s` verified
- [ ] base firmware dependencies compile together
- [ ] double-reset recovery path validated
- [ ] Wi-Fi provisioning portal validated
- [ ] Web UI/WebSerial validated
- [ ] MQTT publish/subscribe validated against notebook broker
- [ ] OTA validated
- [ ] TFT controller and pin mapping confirmed
- [ ] XPT2046 touch validated

## Source of truth

The local working tree is:

`/home/kernelpanic/Projects/proj-esp32`

The remote repository is:

`kernelpanic2015/proj-esp32`

Keep the local `main` branch and GitHub `main` synchronized after validated changes.
