# OTA implementation progress

Completed:

- custom 4 MB A/B partition layout;
- web upload to inactive OTA slot;
- successful `app0 -> app1` firmware transition;
- firmware model/hardware/version/build identity;
- ECDSA P-256 release signing foundation;
- signed manifest generation/verification on the build host;
- OTA update FSM;
- documentation/test log.

In progress:

- raw ESP-IDF OTA state observability;
- controlled `PENDING_VERIFY -> VALID` observation;
- automatic rollback smoke test;
- on-device signature verification;
- remote signed manifest/update trigger through MQTT and automatic checks.
