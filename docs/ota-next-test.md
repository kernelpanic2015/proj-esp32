# Next OTA test: raw bootloader state

The first browser OTA successfully switched execution from `app0` to `app1`, proving the write/reboot/slot-selection path.

The next controlled candidate must expose raw ESP-IDF OTA metadata in `/api/update/status` so that the lifecycle is observed directly:

```text
NEW/PENDING_VERIFY -> VALID
```

Required observations after installing the next candidate:

- firmware version/build changed;
- running partition changed;
- boot partition matches running partition after selection;
- next update partition points to the inactive slot;
- `rollback_enabled=true`;
- raw `image_state` is observed;
- UpdateManager FSM state is observed independently;
- Wi-Fi/MQTT remain healthy.

Only after this is proven should we run a deliberately failing validation image to test automatic rollback.
