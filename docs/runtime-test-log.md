# Runtime / Stage 6 validation log

## 2026-09-05 — Stage 6A TaskScheduler foundation

- Added `arkhipenko/TaskScheduler` alongside `jonblack/arduino-fsm`.
- Enabled `_TASK_INLINE` for the multi-file PlatformIO firmware.
- Migrated the automatic firmware-check timer from hand-written `millis()` scheduling to TaskScheduler.
- Physical proof: an enabled 60 s policy re-armed after reboot, automatically discovered the signed target without a manual/MQTT check, and did not auto-apply it. Explicit apply completed `PENDING_VERIFY -> VALID`.
- Proven physical baseline after promotion: `0.1.16/build 17`, `app1`, `VALID`, `ONLINE`, Wi-Fi + MQTT/TLS connected.

## 2026-09-05 — Stage 6B component registry integration

Planned acceptance for this stage:

- build normal + signed candidate successfully;
- install signed `0.1.17/build 18` candidate through the existing signed Web OTA path;
- observe `PENDING_VERIFY -> VALID`;
- `/api/components` contains one registered `connectivity` component;
- online device reports connectivity state `ONLINE` and health `OK`;
- `/api/status` embeds the same registry and EventBus counters;
- EventBus dropped count remains zero during the proof;
- local `main == origin/main` after promotion.

The Aurora physical proof result is appended to this file when the stage completes.

### Stage 6B physical result — PASS

- Signed candidate `0.1.17/build 18` installed into `app0`.
- Native OTA state observed `PENDING_VERIFY -> VALID`.
- Device returned `ONLINE` with Wi-Fi and MQTT/TLS connected.
- `/api/components` reported one `connectivity` component in state `ONLINE`, health `OK`.
- The same registry is embedded in `/api/status` and therefore the existing MQTT status/telemetry model.
- EventBus reported `pending=0`, `dropped=0`.
- Normal build after integration uses about 17.0% static RAM and 69.1% of the 1728 KiB OTA slot.
- `0.1.17/build 18` is the promoted default baseline.
