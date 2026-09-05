# OTA observability

The update service exposes two different concepts and they must not be conflated:

1. **UpdateManager/FSM state** — what the application-level update workflow is currently doing (`IDLE`, `RECEIVING`, `PENDING_VERIFY`, `VALID`, etc.).
2. **ESP-IDF OTA image state** — bootloader/application partition state stored in OTA metadata (`NEW`, `PENDING_VERIFY`, `VALID`, `INVALID`, `ABORTED`, `UNDEFINED`).

The API must expose both. This is necessary because after a later reboot the application update FSM may legitimately return to `IDLE` while the currently running partition remains `VALID` in ESP-IDF OTA metadata.

Useful partition metadata:

- running partition;
- configured boot partition;
- next update partition;
- raw running-image OTA state.

This observability is required before the rollback test is considered validated.
