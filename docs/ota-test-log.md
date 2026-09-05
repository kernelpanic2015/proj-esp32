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

### Important observation

`PENDING_VERIFY` was **not** observed. At roughly 4 seconds uptime the raw ESP-IDF image state was already `VALID`, while the application-level UpdateManager FSM was `IDLE`. This happened before the application's configured 10-second validation window could mark the image valid itself.

Therefore automatic rollback on an unvalidated/crashing first boot is **not yet proven**. Before the deliberate rollback test, inspect the exact Arduino `Update`/ESP-IDF OTA behavior and bootloader configuration used by this build so we understand why the new image is already `VALID`.
