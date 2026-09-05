# OTA validation log

This file records controlled firmware lifecycle tests performed on the physical ESP32.

## Test protocol

For each OTA test record:

- source version/build and running partition;
- target version/build;
- update transport;
- target partition;
- first-boot OTA image state;
- validation result;
- Wi-Fi/MQTT/runtime health after boot;
- rollback result when intentionally tested;
- NVS persistence across update/rollback.

The device must never depend on Internet or MQTT to decide whether a newly booted image is locally healthy.

## 2026-09-05 — 0.1.0/build 1 -> 0.1.1/build 2

- Source: `0.1.0`, build `1`, `app0`.
- Target: `0.1.1`, build `2`.
- Transport: local browser upload through `/update` / `/api/update/upload`.
- Target boot observed by user: `0.1.1`, build `2`, running partition `app1`.
- Initial post-test API sample supplied by user: update service `IDLE`, `received_bytes=0`, no error, running partition `app1`.
- This proved the web write/reboot/slot-selection path, but raw bootloader state was not yet exposed.

## 2026-09-05 — 0.1.1/build 2 -> 0.1.2/build 3

- Source: `0.1.1`, build `2`, running `app1`.
- Target: `0.1.2`, build `3`, written through the same web OTA endpoint.
- Upload response: `PENDING_REBOOT`, `received_bytes=1156816`.
- New image was reachable after about 3 seconds and ran from `app0`.
- Boot partition: `app0`.
- Next update partition: `app1`.
- Raw image state observed on the first successful HTTP sample: `VALID`.
- Compiled rollback flag reported `rollback_enabled=true`.
- Runtime remained healthy: system `ONLINE`, Wi-Fi connected, MQTT connected/TLS, free heap about 169 KiB.
- NVS-backed MQTT configuration survived the OTA transition.

### Root cause of immediate VALID state

Arduino-ESP32 2.0.17 defines weak hooks `verifyRollbackLater()` and `verifyOta()`. Their defaults are respectively `false` and `true`, so `initArduino()` automatically marks a `PENDING_VERIFY` image valid before application `setup()` runs.

`proj-esp32` now overrides the weak `verifyRollbackLater()` hook and returns `true`. This defers validation to `FirmwareUpdate::tick()` so the project FSM owns the health window and rollback decision.

## 2026-09-05 — 0.1.2/build 3 -> 0.1.3/build 4

- Source: `0.1.2`, build `3`, running `app0`, image state `VALID`.
- Target: `0.1.3`, build `4`, written to `app1`.
- Upload response: `PENDING_REBOOT`, `received_bytes=1156816`.
- At the first reachable sample (~2 seconds), both the application UpdateManager and raw ESP-IDF state were `PENDING_VERIFY`.
- `PENDING_VERIFY` remained visible through successive observations.
- Around the configured local validation window, both states transitioned to `VALID`.
- Final partition state: running `app1`, boot `app1`, next update `app0`, rollback enabled.
- Runtime remained `ONLINE`; Wi-Fi and MQTT/TLS remained connected; free heap remained about 168 KiB.
- NVS-backed MQTT configuration survived again.

This test proves that the application now owns `PENDING_VERIFY -> VALID`. The next test is a deliberately failed local validation that must return to the last known-good image without affecting persistent configuration.
