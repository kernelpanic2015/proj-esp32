# OTA / firmware update architecture

## Objective

`proj-esp32` must support recoverable firmware updates through one shared `UpdateManager` used by Web, MQTT, automatic checks and the LittleFS recovery interface.

## Confirmed platform capability

The current Arduino/ESP-IDF framework exposes the ESP-IDF OTA rollback APIs and is built with bootloader rollback enabled. The relevant runtime states/APIs include:

- `ESP_OTA_IMG_NEW`
- `ESP_OTA_IMG_PENDING_VERIFY`
- `esp_ota_mark_app_valid_cancel_rollback()`
- `esp_ota_mark_app_invalid_rollback_and_reboot()`

The firmware must therefore use the bootloader's A/B OTA lifecycle rather than implementing its own ad-hoc slot switching.

## Firmware identity

Every image carries these immutable-at-build-time fields:

- `model`
- `hardware_revision`
- semantic `version`
- monotonic integer `build`

The semantic version is for humans. Update ordering is decided by `build`.

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
      -> rollback on failed/interrupted validation

Any error during receive/finalize -> FAILED -> IDLE/retry
```

The update subsystem is independent of the network FSM. A network outage does not by itself mean the new firmware is invalid.

## First-boot validation

A newly booted OTA image enters `PENDING_VERIFY`. It is marked valid only after a local validation window confirms that essential runtime functions are healthy enough to operate safely.

Initial baseline validation will include conditions such as:

- application setup completed
- NVS available
- no fatal boot/runtime fault
- heap above a minimum threshold
- supervisor/runtime loop continues to make progress for the validation window

Wi-Fi, MQTT, Internet, SD and non-critical sensors must not be mandatory for validation. Those can be degraded independently.

When the future Supervisor knows a critical self-test failed, it may explicitly call rollback-and-reboot. Otherwise an image that never reaches validation remains unconfirmed and the bootloader can roll back after an interrupted/failed boot sequence.

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

The first milestone is a local Web/API upload to the inactive slot. This validates partitioning, slot switching, version reporting and rollback before remote distribution/security layers are added.

Initial endpoints:

- `GET /api/version`
- `GET /api/update/status`
- `GET /update`
- `POST /api/update/upload`

The development upload endpoint is a lab feature and must not be exposed to untrusted networks.

## Signing

The production update trust model uses ECDSA P-256 signatures over SHA-256.

- private signing key: kept outside the Git repository
- public verification key: committed/embedded in firmware
- private key permissions: owner-only
- firmware/package is rejected if signature verification fails

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

The manifest will eventually be signed as well and include at least model, hardware revision, version, build, byte size, SHA-256 and download URL.

## Rollback smoke test

A controlled test must prove all of the following:

1. device is running image A;
2. image B is uploaded to the inactive slot;
3. boot switches to B;
4. B reports `PENDING_VERIFY`;
5. a healthy B is marked `VALID`;
6. another test image is booted but deliberately not validated/interrupted;
7. bootloader returns to the last valid image;
8. NVS configuration survives the update/rollback cycle.
