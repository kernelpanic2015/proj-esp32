# OTA test plan — 0.1.2/build 3

Purpose: observe the native ESP-IDF OTA lifecycle explicitly after the successful `0.1.1/build 2` browser update.

## Candidate requirements

- Version `0.1.2`, build `3`, channel `dev`.
- Same model/hardware revision as the device.
- `/api/update/status` exposes:
  - application update FSM state;
  - running partition;
  - boot partition;
  - next update partition;
  - raw ESP-IDF image state;
  - rollback capability flag.
- Wi-Fi/MQTT behavior otherwise unchanged.

## Success criteria

1. Device currently runs `0.1.1/build 2` from `app1`.
2. Candidate is written to `app0` through the web update path.
3. Device boots `0.1.2/build 3` from `app0`.
4. Raw OTA image state is observed as `PENDING_VERIFY` before validation, if timing allows.
5. After the local validation window, raw image state becomes `VALID` and the application FSM reports `VALID` until a later reboot.
6. MQTT and Wi-Fi remain operational.
7. No critical NVS configuration is lost.

After this passes, create a separate deliberately failing candidate to prove automatic rollback.
