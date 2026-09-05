# Documentation index

This directory is the canonical handoff for `proj-esp32`.

## Read first in a new chat

1. [`BOOTSTRAP.md`](BOOTSTRAP.md) — where we are, what is connected, how Aurora controls the notebook, and the next safe actions.
2. [`hardware.md`](hardware.md) — confirmed MCU/board/flash/serial facts and GPIO constraints.
3. [`architecture.md`](architecture.md) — firmware architecture, state machine and network services.
4. [`operations.md`](operations.md) — PlatformIO/Aurora build, upload, erase and serial-observation workflow.
5. [`dependencies.md`](dependencies.md) — why each firmware dependency was chosen and the replacement/licensing caveats.
6. [`references.md`](references.md) — board page, datasheet/pinout source and relevant upstream libraries/projects.

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
- [ ] provision Wi-Fi credentials and validate STA `ONLINE` state
- [ ] Web UI `/`, `/api/status` and `/webserial` validated over STA Wi-Fi
- [ ] MQTT publish/subscribe validated against notebook broker
- [ ] OTA validated over Wi-Fi
- [ ] TFT controller and pin mapping confirmed
- [ ] XPT2046 touch validated

## Current physical state

The most recent controlled test ended in `CONFIG_PORTAL`. Unless the board has been reset or powered off since then, it should be advertising:

- SSID: `proj-esp32-setup`
- captive portal/AP IP: `192.168.4.1`

Use a phone or another client for provisioning when possible so the `kpnote` connection used by Aurora is not disrupted.

## Source of truth

The local working tree is:

`/home/kernelpanic/Projects/proj-esp32`

The remote repository is:

`kernelpanic2015/proj-esp32`

Keep the local `main` branch and GitHub `main` synchronized after validated changes.
