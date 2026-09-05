# Release candidate 0.1.2/build 3

Purpose: expose native ESP-IDF OTA partition/image metadata so the A/B lifecycle can be observed directly during the next browser OTA test.

Changes relative to 0.1.1/build 2:

- `/api/update/status` adds boot partition, next update partition, raw running-image OTA state and rollback capability flag;
- no intentional change to Wi-Fi/MQTT behavior;
- candidate remains development-only and the web upload endpoint is not yet signature-enforcing on device.

This candidate is for validation of `PENDING_VERIFY -> VALID` before the deliberate rollback-failure test.
