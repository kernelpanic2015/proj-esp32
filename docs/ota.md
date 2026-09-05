# OTA / firmware update architecture

## Objective

`proj-esp32` must support recoverable firmware updates through one shared `UpdateManager` used by Web, MQTT, automatic checks and the LittleFS recovery interface.

## Confirmed platform capability

The current Arduino/ESP-IDF framework exposes the ESP-IDF OTA rollback APIs and is built with bootloader rollback enabled. The relevant runtime states/APIs include:

- `ESP_OTA_IMG_NEW`
- `ESP_OTA_IMG_PENDING_VERIFY`
- `esp_ota_mark_app_valid_cancel_rollback()`
- `esp_ota_mark_app_invalid_rollback_and_reboot()`

The firmware therefore uses the bootloader's A/B OTA lifecycle rather than implementing ad-hoc slot switching.

### Arduino-ESP32 validation hook

Arduino-ESP32 2.0.17 normally validates a `PENDING_VERIFY` image inside `initArduino()` before application `setup()` executes. Its weak defaults are effectively:

```cpp
verifyOta() -> true
verifyRollbackLater() -> false
```

That default behavior would bypass the project health-validation FSM. `proj-esp32` therefore provides a strong override of the weak `verifyRollbackLater()` hook returning `true`. This leaves the image in `PENDING_VERIFY` until `FirmwareUpdate::tick()` explicitly accepts or rejects it.

This behavior was verified on the physical device: version `0.1.3/build 4` remained `PENDING_VERIFY` for the local validation window and then transitioned to `VALID` under application control.

## Firmware identity

Every image carries these immutable-at-build-time fields:

- `model`
- `hardware_revision`
- semantic `version`
- monotonic integer `build`

The semantic version is for humans. Update ordering is decided by `build`.

The normal release identity has compile-time defaults, while dedicated controlled test profiles may override version/build without changing production defaults.

A future remote manifest must match both model and hardware revision before an image can be considered applicable.

## Update FSM

```text
IDLE
  -> RECEIVING
  -> FINALIZING
  -> PENDING_REBOOT
  -> reboot
  -> PENDING_VERIFY
      -> VALID
      -> ROLLBACK

Any error during receive/finalize -> FAILED -> IDLE/retry
```

The update subsystem is independent of the network FSM. A network outage does not by itself mean the new firmware is invalid.

## First-boot validation

A newly booted OTA image enters `PENDING_VERIFY`. It is marked valid only after a local validation window confirms that essential runtime functions are healthy enough to operate safely.

Initial baseline validation includes:

- critical internal configuration/NVS ready;
- no fatal boot/runtime fault reported by the update path;
- heap above the defined minimum;
- update/runtime loop continues to progress through the validation window.

As the modular Supervisor/ComponentRegistry is introduced, the validation policy will consume their local critical-health model rather than adding network requirements.

Wi-Fi, MQTT, Internet, SD and non-critical sensors must not be mandatory for validation. Those can be degraded independently.

If the local critical checks fail through the validation timeout, UpdateManager marks the candidate invalid and requests rollback/reboot. This controlled-failure path has now been proven on the physical device.

An image which crashes or repeatedly reboots before the application can explicitly reject it remains a separate later recovery test.

## Control surfaces

All update entry points call the same manager:

```text
Preact/Web ----\
LittleFS Web ---+--> UpdateManager --> inactive OTA slot
MQTT ----------/
Auto-check ----/
```

No control surface gets a separate OTA implementation.

## Web development flow

The current local Web/API upload proves partitioning, slot switching, version reporting, application-controlled validation and bootloader rollback before remote distribution/security layers are enforced on-device.

Endpoints:

- `GET /api/version`
- `GET /api/update/status`
- `GET /update`
- `POST /api/update/upload`

`/api/update/status` exposes both the application FSM state and native OTA metadata: running partition, boot partition, next update partition, raw image state and rollback capability.

The development upload endpoint is a lab feature and must not be exposed to untrusted networks.

## Signing

The production update trust model uses ECDSA P-256 signatures over SHA-256.

- private signing key: kept outside the Git repository
- public verification key: committed/embedded in firmware
- private key permissions: owner-only
- release manifest generation/signature verification already validated on the build host
- next security milestone: reject unsigned/invalid packages on the ESP32 itself before installation

Signing authenticates the image. Encryption is a separate later layer for firmware confidentiality.

## Remote distribution

Planned layout:

```text
firmware/
  <model>/
    hw<revision>/
      manifest.json
      firmware-<version>.bin.enc
      firmware-<version>.sig
```

The manifest will eventually be signed and include at least model, hardware revision, version, build, byte size, SHA-256 and download URL.

## Rollback smoke tests

Validation is staged to isolate failure modes:

1. **Healthy candidate** — prove `PENDING_VERIFY -> VALID`. **Completed** with `0.1.3/build 4`.
2. **Controlled local validation failure** — dedicated profile forces the UpdateManager health result false and requests rollback. **Completed** with `0.1.4-rollback-test/build 5`: the candidate ran in `app0/PENDING_VERIFY`, was marked invalid, and the bootloader returned to `0.1.3/build 4` in `app1/VALID`.
3. **Interrupted/crashing first boot** — still pending; only perform after the signed-update acceptance path is hardened enough to make the test worthwhile.

The controlled rollback proof also confirmed that NVS-backed Wi-Fi/MQTT configuration and unrelated local functionality survive the update/rollback cycle. Exact observations are recorded in `docs/ota-test-log.md`.
