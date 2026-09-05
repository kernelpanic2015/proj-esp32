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
- Native raw ESP-IDF OTA state still needs to be exposed/observed explicitly in the API so that `PENDING_VERIFY -> VALID` can be proven rather than inferred.

Next action: expose raw OTA image state and boot/update partition metadata, then repeat a controlled update and deliberately test rollback.
