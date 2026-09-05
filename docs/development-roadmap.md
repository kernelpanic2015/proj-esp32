# Development roadmap

This project is being built as a fault-tolerant, autonomous ESP32 edge controller rather than a monolithic sketch.

## Architectural invariants

1. **The device must keep performing configured local automation without Internet, MQTT or cloud services.**
2. **A failure in one sensor/peripheral must not stop unrelated functions.** Components fail independently and the global system may enter `DEGRADED` while healthy channels continue running.
3. **Every fallible subsystem has explicit state, health, retry/backoff and recovery policy.**
4. **Hardware-specific code is modular.** Adding or replacing a sensor should primarily add/replace one component/driver, not modify the core.
5. **The same component health model feeds TFT, Preact/Web, MQTT telemetry, logs and future AI/agent diagnostics.**
6. **Cloud manages; device controls.** MQTT/Web/API may configure, observe and trigger actions, but persisted rules/schedules execute locally.
7. **Firmware and configuration changes are transactional and recoverable.** Firmware uses OTA A/B + rollback; configuration will use validate -> persist -> apply with previous revision retained.

## Storage model

- **Firmware flash**: bootloader, NVS, OTA metadata, two application slots, LittleFS recovery, coredump.
- **NVS**: critical mutable configuration, device settings, automation/rule metadata, update state.
- **LittleFS**: small recovery UI and critical local auxiliary files. It must not be required for normal automation logic.
- **microSD (display module)**: compiled Preact application, assets, logs, historical data and non-critical bulk storage.

If the SD card is absent or damaged, sensing, rules, schedules and relay control must continue.

## Stage 0 — baseline and partition layout

- [x] Wi-Fi provisioning
- [x] HTTP status endpoint
- [x] WebSerial
- [x] MQTT/TLS through CloudAMQP/RabbitMQ
- [x] MQTT round-trip `cmd -> ESP32 -> events`
- [x] OTA A/B capability confirmed in current ESP-IDF/Arduino framework
- [x] bootloader rollback support confirmed enabled (`CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE`)
- [ ] adopt custom 4 MB partition table with larger A/B app slots and 512 KB LittleFS
- [ ] expose firmware identity and OTA state via API

Target 4 MB layout:

```text
nvs        20 KB
otadata      8 KB
app0      1728 KB
app1      1728 KB
spiffs*    512 KB
coredump    64 KB
```

`spiffs` is the partition label/subtype used by the Arduino/PlatformIO layout; the filesystem format is LittleFS.

## Stage 1 — Web OTA and version lifecycle

Goal: prove the complete A/B firmware lifecycle before adding more hardware.

- [ ] firmware identity: model, hardware revision, semantic version, monotonic build number
- [ ] `GET /api/version`
- [ ] `GET /api/update/status`
- [ ] recovery-compatible `GET /update`
- [ ] firmware upload via Web/API to inactive OTA partition
- [ ] reboot into new image
- [ ] detect `ESP_OTA_IMG_PENDING_VERIFY`
- [ ] self-test/validation window
- [ ] mark healthy image valid
- [ ] deliberately interrupt validation and verify automatic rollback

The initial Web OTA smoke test may use an unsigned development image. It is not the final security model.

## Stage 2 — firmware signing and packaging

- [ ] generate an offline/local ECDSA P-256 signing key pair
- [ ] private key stored outside the repository with restrictive permissions
- [ ] public verification key committed/embedded in firmware
- [ ] build tool emits SHA-256 + ECDSA signature
- [ ] ESP32 verifies image/package before accepting update
- [ ] add firmware encryption after signed OTA is proven reliable

Signing provides authenticity/integrity. Encryption provides confidentiality. They are separate controls and both may be used.

## Stage 3 — remote manifest and autonomous update

- [ ] public distribution structure by device model + hardware revision
- [ ] signed manifest
- [ ] monotonic build comparison
- [ ] HTTPS download
- [ ] streaming hash/signature validation
- [ ] auto-update policy stored in NVS
- [ ] channels such as `stable` / `test`
- [ ] failure telemetry and rollback reporting

The device must refuse firmware for the wrong model/hardware revision.

## Stage 4 — update triggers through all control surfaces

All triggers call the same `UpdateManager`; they do not implement separate OTA mechanisms.

- [ ] Web/Preact: check/apply/upload
- [ ] MQTT: `firmware.check`, `firmware.update`
- [ ] automatic periodic check
- [ ] local recovery UI in LittleFS

MQTT sends control intent only; firmware binaries are downloaded directly over HTTPS.

## Stage 5 — modular core and health model

Refactor the current baseline into reusable modules while preserving working behavior:

```text
core/
  EventBus
  ComponentRegistry
  Supervisor
  Health

services/
  NetworkService
  MqttService
  StorageService
  UpdateService
  WebService
  TimeService

components/
  display/
  touch/
  rtc/
  sensors/
  actuators/

drivers/
  hardware-specific implementations
```

Each component exposes a common contract such as identity, state, health and non-blocking `tick()`.

## Stage 6 — autonomous configuration, rules and scheduling

- [ ] versioned configuration schema + revision
- [ ] transactional configuration FSM
- [ ] RuleEngine
- [ ] Scheduler
- [ ] persisted rules/schedules in internal flash/NVS
- [ ] per-rule fault policy
- [ ] actuator safe states and interlocks
- [ ] DS3231-backed time when network/NTP is unavailable

Example policy: heater relay ON below 16 C, OFF above 18 C. The rule executes locally even with Wi-Fi/MQTT/Internet offline.

## Stage 7 — local UI and storage

- [ ] ILI9488 display
- [ ] touch controller confirmation/bring-up
- [ ] microSD
- [ ] Preact + Vite build served from `/www` on SD
- [ ] LittleFS recovery UI fallback
- [ ] TFT health dashboard generated from ComponentRegistry

Health visualization convention:

- OK: green + text/icon
- DEGRADED/STALE/RECOVERING: yellow + text/icon
- FAULT: red + text/icon
- DISABLED: neutral

Do not rely on color alone.

## Stage 8 — hardware expansion

Add hardware as independent modules only when a concrete feature requires it. Initial planned base hardware includes the NodeMCU-32S, ILI9488/touch/microSD display assembly and DS3231 RTC. Sensors, relays, RS-485, CAN and other modules remain later plug-in components.
