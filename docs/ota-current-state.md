# OTA current-state checkpoint

The first browser OTA moved the device from `app0` firmware `0.1.0/build 1` to `app1` firmware `0.1.1/build 2`.

User-observed post-update API values:

```json
{"model":"proj-esp32-35","hardware_revision":1,"version":"0.1.1","build":2,"channel":"dev"}
```

```json
{"state":"IDLE","received_bytes":0,"error":"","running_partition":"app1"}
```

This proves slot switching and execution of the new image, but does not by itself prove the raw bootloader state transition. The following release adds explicit `image_state`, `boot_partition`, `next_update_partition`, and `rollback_enabled` fields so the next test can observe the ESP-IDF OTA lifecycle directly.
