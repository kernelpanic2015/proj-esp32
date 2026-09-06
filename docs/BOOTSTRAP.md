# proj-esp32 — bootstrap / handoff

Use this file to resume the project in a new ChatGPT conversation without reconstructing the environment from memory.

## Identity

- Project: `proj-esp32`
- GitHub: `kernelpanic2015/proj-esp32`
- Repository visibility: private
- Notebook/device: `kpnote`
- Local path: `/home/kernelpanic/Projects/proj-esp32`
- Primary language: C++
- Build system: PlatformIO Core CLI
- Framework: Arduino core for ESP32
- PlatformIO board ID: `nodemcu-32s`
- Serial port: `/dev/ttyUSB0`

## Confirmed board

Retail board identification: NodeMCU-32S, 38 pins, ESP-WROOM-32 module, CP2102 USB/UART bridge.

Direct `esptool` probe confirmed:

- chip: ESP32-D0WD-V3
- silicon revision: v3.0
- Wi-Fi + Bluetooth, dual core, 240 MHz
- crystal: 40 MHz
- flash: 4 MB
- flash voltage: 3.3 V

Linux USB/udev confirmed CP2102 (`10c4:ea60`) using `cp210x` and exposing `/dev/ttyUSB0`.

## Validated execution chain

The complete development path is working:

`ChatGPT -> GitHub issue -> Aurora Client -> kpnote -> PlatformIO -> ESP32 -> HTTP/WebSerial/MQTT`

GitHub Issues in `kernelpanic2015/aurora-kpnote` are the command plane. Aurora Watch is the preferred read-only observation plane.

## Current firmware baseline — verified 2026-09-05

Current physical device state after Stage 7D persisted-rule closure:

- model: `proj-esp32-35`
- hardware revision: `1`
- firmware: `0.1.37`
- build: `38`
- channel: `dev`
- running partition: `app0`
- boot partition: `app0`
- next update partition: `app1`
- native OTA image state: `VALID`
- application FSM/system: `ONLINE`
- Wi-Fi: connected
- MQTT/TLS: connected
- `connectivity`: `ONLINE/OK`
- Supervisor: `RUNNING/OK`
- EventBus dropped count: `0`
- Wi-Fi reconnect work task: disabled while healthy
- MQTT reconnect work task: disabled while connected
- MQTT telemetry task: enabled while connected
- MQTT buffer: explicit `4096` bytes
- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`

`arkhipenko/TaskScheduler` 4.0.8 runs alongside `jonblack/arduino-fsm`: TaskScheduler owns timing/eligibility; FSMs own state/behavior; components own subsystem interpretation; EventBus owns transition delivery; Supervisor aggregates registry health only.

Stage 6E physically proved full Wi-Fi loss/recovery. Stage 7A proved dual-slot transactional configuration. Stage 7B proved hysteresis semantics, Stage 7C proved event-driven local execution during a real Wi-Fi/MQTT outage, and Stage 7D now proves persisted rule activation across apply/reboot/rollback/OTA. The current ConfigurationStore document is revision 6 and remains local-NVS backed.

Normal build remains within the 1728 KiB OTA slot at roughly 17% static RAM and 70% flash usage.

## Stage 7A ConfigurationStore — validated

- NVS namespace: `app-config`;
- two verified slots plus active pointer;
- schema 1, monotonic revision;
- current proven revision: `3`;
- invalid duplicate-ID candidate rejected without changing active configuration;
- valid apply survived reboot;
- second apply + explicit rollback restored previous logical document as new revision;
- rolled-back revision survived reboot and clean signed OTA;
- clean physical baseline: `0.1.29/build 30`, `app0/VALID`.

## Stage 7B RuleEngine — validated

- one minimal in-memory hysteresis rule model is implemented;
- invalid hysteresis is rejected semantically;
- virtual temperature input and virtual heater actuator proved ON/OFF + deadband behavior;
- disabled rule does not actuate;
- RuleEngine produces desired state only and never touches GPIO;
- clean firmware exposes `GET /api/rules/status`;
- controlled write/evaluation endpoints exist only in the lab build and are absent from the clean image;
- Stage 7B clean baseline was `0.1.31/build 32`; later stages supersede it.

**Stage 7C validated:** TaskScheduler + EventBus drive one-shot RuleRuntime evaluation, including execution during real Wi-Fi/MQTT loss.

## Stage 7D persisted rules — validated

- clean physical baseline: `0.1.37/build 38`, `app0/VALID`;
- ConfigurationStore revision: `6`;
- active persisted rule: `persisted.demo.a`, hysteresis 16/18;
- `PersistedRuleLoader` loads revision 6 automatically at boot;
- RuleEngine: configured/enabled;
- RuleRuntime: `ARMED`, work task disabled with no pending work until an input event exists;
- invalid persisted semantics are rejected before slot/pointer activation;
- apply activation, reboot reload, rule replacement, monotonic rollback and rollback reboot persistence are physically proven;
- virtual bindings exist in the clean runtime, but mutation/test HTTP endpoints are absent;
- Supervisor: `RUNNING/OK`; EventBus `dropped=0`; Wi-Fi + MQTT/TLS healthy; HTTPS-only remote update.

**Stage 7E next:** local persisted schedule/delayed-action service above TaskScheduler. Keep scheduler primitives separate from schedule semantics; inactive work stays disabled.

## Flash layout — validated

`platformio.ini` uses `partitions/ota_4mb.csv` and `board_build.filesystem = littlefs`.

```text
4 MB flash
├── nvs        20 KiB
├── otadata     8 KiB
├── app0      1728 KiB
├── app1      1728 KiB
├── filesystem 512 KiB
└── coredump    64 KiB
```

The partition CSV uses the ESP32 data subtype name `spiffs` for the 512 KiB filesystem region; PlatformIO is configured to mount/build it as LittleFS.

## Recovery and provisioning — validated

`ESP_DoubleResetDetector` is active and tested using controlled hardware reset pulses:

1. first reset -> normal path -> `FSM -> WIFI_CONNECTING`;
2. second reset inside detection window -> `DOUBLE_RESET_DETECTED`;
3. double reset -> `FSM -> CONFIG_PORTAL`.

The DRD object is constructed inside `setup()` after runtime/NVS initialization; constructing it globally previously caused an EEPROM/NVS initialization error.

All intentional firmware restarts now go through `RestartService`. Its pre-restart hook calls `drd->stop()` before `ESP.restart()`, so a software-controlled reboot does not count toward human double-reset recovery. This was physically proven with two software reboots inside the 10 s DRD window. Manual/hardware reset pulses still retain the recovery behavior above.

WiFiManager runs the config portal in nonblocking mode. Recovery/config AP:

- SSID: `proj-esp32-setup`
- AP IP: `192.168.4.1`

Wi-Fi credentials are provisioned and normal boot reaches STA `ONLINE`.

## Current HTTP/Web services — validated

Validated endpoints include:

- `http://proj-esp32.local/`
- `http://proj-esp32.local/api/status`
- `http://proj-esp32.local/api/version`
- `http://proj-esp32.local/api/update/status`
- `http://proj-esp32.local/api/update/remote/status`
- `http://proj-esp32.local/update`
- `POST http://proj-esp32.local/api/update/prepare`
- `POST http://proj-esp32.local/api/update/upload`
- `POST http://proj-esp32.local/api/update/check`
- `POST http://proj-esp32.local/api/update/apply`
- `http://proj-esp32.local/webserial`
- `http://proj-esp32.local/config/mqtt`

The Web OTA upload endpoint is a development/lab interface and must not be exposed to untrusted networks.

## MQTT / RabbitMQ baseline — validated end-to-end

The device uses `PubSubClient` with `WiFiClientSecure`.

Validated behavior:

- authenticated MQTT/TLS session visible in RabbitMQ/CloudAMQP;
- subscribe on `lab/proj-esp32/<device-id>/cmd`;
- retained online state on `/state`;
- periodic `/telemetry`;
- `ping` command received on `/cmd` and response published on `/events`;
- configuration persisted in NVS and survived multiple OTA transitions plus a bootloader rollback.

Current development TLS mode is encrypted but certificate verification is disabled with `setInsecure()`. Replacing this with proper CA validation is still pending.

Do not commit broker passwords, Wi-Fi passwords or other secrets.

## OTA A/B — validated through rollback

The project uses native ESP-IDF/bootloader A/B OTA semantics, not custom slot switching.

### Important Arduino-ESP32 hook

Arduino-ESP32 2.0.17 provides weak hooks `verifyOta()` and `verifyRollbackLater()`. The framework default would validate a `PENDING_VERIFY` image during `initArduino()` before application `setup()`.

The project therefore contains:

```cpp
extern "C" bool verifyRollbackLater() {
    return true;
}
```

in `src/ota_hooks.cpp`. Do not remove this without redesigning the OTA validation lifecycle.

### Healthy validation proof

Physical-device test proved:

```text
0.1.2 / app0 / VALID
        -> OTA
0.1.3 / app1 / PENDING_VERIFY
        -> application health window
0.1.3 / app1 / VALID
```

`PENDING_VERIFY` was observable for several seconds before the application called `esp_ota_mark_app_valid_cancel_rollback()`.

### Controlled rollback proof

A dedicated PlatformIO profile exists:

`nodemcu-32s-rollback-test`

It builds approximately:

- version: `0.1.4-rollback-test`
- build: `5`
- compile flag: `PROJ_OTA_TEST_FORCE_VALIDATION_FAILURE=1`

Physical-device test proved:

```text
0.1.3 build 4 / app1 / VALID
        -> Web OTA to app0
0.1.4-rollback-test build 5 / app0 / PENDING_VERIFY
        -> forced local validation failure
        -> esp_ota_mark_app_invalid_rollback_and_reboot()
        -> bootloader rollback
0.1.3 build 4 / app1 / VALID / ONLINE
```

After rollback, Wi-Fi and MQTT/TLS reconnected and NVS-backed MQTT configuration remained present. See `docs/ota-test-log.md` for the exact evidence.

## Firmware signing and remote OTA — validated

A local ECDSA P-256 signing keypair exists on `kpnote` outside the Git repository.

Rules and verified behavior:

- private key stays outside Git and has owner-only permissions;
- public key is committed under `keys/update-signing-public.pem`;
- `scripts/release_manifest.py` creates a deterministic manifest and signature;
- the ESP32 verifies the ECDSA signature before preparing an update;
- unsigned packages and invalid signatures are rejected;
- the streamed firmware SHA-256 must match the signed manifest before `Update.end()` accepts the image;
- Web upload and remote download share the same signed-package install path;
- remote `check` fetches `manifest.json` + `manifest.sig`, then `apply` downloads `firmware.bin`;
- default builds accept only HTTPS remote manifest URLs;
- a lab-only build flag can enable HTTP for controlled LAN tests;
- the first remote OTA proof completed `0.1.7-remote-test/app0/VALID -> 0.1.8/app1/PENDING_VERIFY -> VALID`;
- after the proof the final `0.1.8` image rejected the same HTTP manifest URL, confirming return to HTTPS-only policy.

Transport CA validation is still pending. Update authenticity is already protected independently by the signed manifest and signed firmware hash.

## Serial observation rule

Do not open pyserial with default DTR/RTS states on this CP2102 board when the goal is passive monitoring; it can reset the ESP32 and interfere with double-reset detection.

Use:

```bash
.venv-platformio/bin/python scripts/capture_serial.py --seconds 10
```

## Aurora control plane

Create strict JSON issues in `kernelpanic2015/aurora-kpnote` with label `aurora:queued`:

```json
{
  "schema": "aurora.job.v1",
  "name": "job-name",
  "cwd": "/home/kernelpanic/Projects/proj-esp32",
  "argv": ["/bin/bash", "-lc", "command"],
  "timeout_seconds": 120
}
```

Do not treat Issue creation as execution success. Wait for the real Aurora job UUID and observe it through Aurora Watch until `completed` or `failed`.

Public Watch fallback, when needed:

```text
https://jobs.dellasale.com/api/watch/jobs
https://jobs.dellasale.com/api/watch/jobs/{jobId}
https://jobs.dellasale.com/api/watch/jobs/{jobId}/events
```

The `jobId` is the Aurora UUID, not the GitHub Issue number.

## PlatformIO environment

Dedicated environment: `.venv-platformio/`

Wrapper:

```bash
./scripts/pio
```

Common commands:

```bash
./scripts/pio run
./scripts/pio run -e nodemcu-32s-rollback-test
./scripts/pio run -t upload --upload-port /dev/ttyUSB0
./scripts/pio device list
```

Do not erase flash unless explicitly required.

## GPIO rules already adopted

- logic is 3.3 V; GPIOs are not 5 V tolerant
- GPIO34, 35, 36, 39 are input-only
- GPIO6..11 are reserved for module flash
- GPIO0, 2, 5, 12, 15 are boot strapping pins; use with care
- GPIO1/3 are UART0/CP2102 and should remain free while USB serial/debug is required
- default I2C: GPIO21 SDA, GPIO22 SCL
- VSPI starting point: GPIO18 SCK, GPIO19 MISO, GPIO23 MOSI

Do not lock TFT/touch/SD chip-select or other display GPIOs until the physical module pinout is confirmed.

## Architectural direction

The firmware base must remain autonomous and fault-tolerant:

- network/cloud manage and observe; local firmware controls;
- configured rules/schedules must continue without Internet or MQTT;
- sensor/actuator failures are isolated by component rather than stopping the whole device;
- multiple FSMs cooperate without blocking;
- TaskScheduler owns cooperative timing/eligibility; FSMs own state/behavior;
- tasks stay disabled when work is not meaningful and may be activated/restarted with delay;
- future components expose standard state/health metadata to TFT, Preact, MQTT and APIs;
- internal flash holds firmware A/B, NVS and LittleFS recovery assets;
- microSD will hold the compiled Preact frontend, logs, data and larger UI assets.

## Immediate next steps

1. Start **Stage 7D**: bind validated persisted rule documents and ConfigurationStore revisions to RuleEngine/RuleRuntime lifecycle.
2. Preserve the Stage 7C invariant: RuleRuntime work tasks remain disabled until an event makes evaluation meaningful; connectivity is never required for local rule execution.
3. Then add the local schedule/delayed-action layer for schedules, settling windows and future actuator timing.
4. Keep the cross-cutting network-hardening backlog: replace `setInsecure()` with CA validation, then add MQTT LWT and backoff/jitter.
5. Continue opportunistic TaskScheduler + FSM migration only when touching a subsystem or when it materially reduces custom timing/recovery code.

## Source-of-truth invariant

After every validated change:

```text
/home/kernelpanic/Projects/proj-esp32 main == origin/main
```

## Stage 6 core closure

Stages 6A–6E are validated. Physical baseline is `0.1.25/build 26` on `app0`, native image `VALID`, application `ONLINE`, Wi-Fi + MQTT/TLS connected, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, EventBus `dropped=0`. OTA automatic checks, MQTT reconnect/telemetry and Wi-Fi reconnect timing now use the cooperative TaskScheduler pattern where appropriate. Proceed to Stage 7; preserve this runtime ownership model for future components.


## Stage 7C closure

Stage 7C is physically validated. Controlled `0.1.34-remote-test/build 35` proved
EventBus -> RuleRuntime -> one-shot TaskScheduler -> RuleEngine execution while
Wi-Fi/MQTT were deliberately unavailable. Hysteresis, disabled-rule rejection,
Supervisor recovery and EventBus `dropped=0` were verified. Clean
`0.1.35/build 36` is running on `app0/VALID`, Wi-Fi + MQTT/TLS connected, HTTPS-only
remote update restored, ConfigurationStore revision 3 preserved, production registry
contains only `connectivity`, RuleRuntime is `DISABLED`, and Stage 7C lab endpoints are
absent.
