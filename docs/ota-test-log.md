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

This test proves that the application now owns `PENDING_VERIFY -> VALID`.

## 2026-09-05 — controlled failed validation and bootloader rollback

- Source/last known good: `0.1.3`, build `4`, running `app1`, image state `VALID`.
- Controlled target: `0.1.4-rollback-test`, build `5`, PlatformIO profile `nodemcu-32s-rollback-test`.
- Candidate SHA-256 verified before upload: `7a1922b63232cf5d708473f91a4d8920244df6eba522a9ac3a7cad8666007579`.
- Transport: local Web OTA endpoint `/api/update/upload`.
- Upload wrote `1156752` bytes and selected `app0` as the boot partition.
- First reachable target sample (~2 seconds): version `0.1.4-rollback-test`, build `5`, running/boot `app0`, native image state `PENDING_VERIFY`, and `validation_test_forced_failure=true`.
- The test profile deliberately kept local health invalid until the configured validation timeout.
- The UpdateService called the ESP-IDF invalid/rollback path; the bootloader then returned to the previous valid image.
- At the first observed post-rollback sample the device was again `0.1.3`, build `4`, running/boot `app1`, next update `app0`, native image state `VALID`.
- Post-rollback runtime recovered to `ONLINE` with Wi-Fi connected and MQTT/TLS connected.
- NVS-backed configuration survived: `mqtt_configured=true` and `mqtt_tls=true`; the device retained its hostname/device identity and LAN configuration.
- Aurora proof job completed with `ROLLBACK_PROOF_OK` and exit code `0`.

This proves the full controlled lifecycle:

```text
0.1.3 build 4 / app1 / VALID
        -> Web OTA
0.1.4-rollback-test build 5 / app0 / PENDING_VERIFY
        -> forced local validation failure
        -> mark invalid + reboot
        -> bootloader rollback
0.1.3 build 4 / app1 / VALID / ONLINE
```

## 2026-09-05 — transition to signed-update verifier 0.1.5/build 6

- Source: `0.1.3`, build `4`, `app1/VALID`.
- Target: `0.1.5`, build `6`, written to `app0` through the legacy 0.1.3 upload endpoint.
- Candidate SHA-256: `f1df146d0d112926c04a525186c0326f0b51a5046487604e8256dce56da69997`.
- Host ECDSA P-256 manifest verification: `Verified OK`.
- First reachable target sample (~2 seconds): `0.1.5/build 6`, `app0/PENDING_VERIFY`.
- Around 9 seconds: `app0/VALID`.
- Runtime recovered `ONLINE` with Wi-Fi and MQTT/TLS connected.
- 0.1.5 introduced on-device signed-manifest verification, firmware SHA-256 verification and removed the unsigned ArduinoOTA bypass.

## 2026-09-05 — signed OTA negative tests and 0.1.6/build 7 positive proof

Starting baseline: `0.1.5/build 6`, `app0/VALID`.

### Unsigned upload rejection

A direct multipart upload without a prepared signed package returned HTTP `400` with:

`error = signed_package_not_prepared`

The boot partition remained `app0`; the running image remained `VALID`.

### Invalid manifest signature rejection

A one-byte modified DER signature was sent with the manifest. `/api/update/prepare` returned HTTP `400` with:

`error = package_prepare_manifest_signature_invalid`

No package was prepared and no boot partition change occurred.

### Tampered firmware rejection

A valid signed 0.1.6 manifest/signature was accepted first:

- candidate: `0.1.6`, build `7`
- size: `1161696` bytes
- expected firmware SHA-256: `e7a63a146efb543b62d64f7c02aaeb2e6f0e01b662c9b229b496999be3728aa7`

A same-size firmware copy with one modified byte was then uploaded. The ESP32 streamed the image hash, rejected it with HTTP `400` and:

`error = firmware_sha256_mismatch`

After rejection:

- running partition remained `app0`
- boot partition remained `app0`
- native image state remained `VALID`

This proves that a signed manifest cannot authorize different firmware bytes.

### Valid signed 0.1.6 installation

The valid signed package was prepared again and the original firmware uploaded:

```text
0.1.5 build 6 / app0 / VALID
        -> verify signed manifest on device
        -> verify firmware SHA-256 on device
        -> install to app1
0.1.6 build 7 / app1 / PENDING_VERIFY
        -> application health window
0.1.6 build 7 / app1 / VALID
```

Observed first reachable 0.1.6 sample at ~2 seconds in `app1/PENDING_VERIFY`; around 9 seconds the image became `VALID`.

Final runtime state:

- firmware `0.1.6`, build `7`, channel `dev`
- running/boot partition `app1`
- next update partition `app0`
- system `ONLINE`
- Wi-Fi connected
- MQTT connected over TLS
- NVS-backed MQTT configuration still present
- free heap about 173 KiB

Aurora proof job completed with `SIGNED_OTA_0_1_6_PROOF_OK` and exit code `0`.

The signed local Web OTA acceptance path is therefore physically validated. The next OTA milestone is remote signed-manifest retrieval and common Web/MQTT/automatic update triggers, while retaining the same verifier and UpdateManager.
