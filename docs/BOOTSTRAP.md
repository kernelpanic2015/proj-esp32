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

Current physical device state after the Stage 6B ComponentRegistry physical proof:

- model: `proj-esp32-35`
- hardware revision: `1`
- firmware: `0.1.17`
- build: `18`
- channel: `dev`
- running partition: `app0`
- boot partition: `app0`
- next update partition: `app1`
- native OTA image state: `VALID`
- system/FSM: `ONLINE`
- Wi-Fi: connected
- MQTT/TLS: connected
- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`

`arkhipenko/TaskScheduler` 4.0.8 is now adopted alongside `jonblack/arduino-fsm`. TaskScheduler owns **when work is eligible**; FSM owns **state and behavior**. Tasks are expected to remain disabled until work is meaningful, and delayed enable/restart is the preferred mechanism for warm-up, settling, retry/backoff and minimum on/off timing.

The first migrated production path is the automatic firmware check. Physical proof showed persisted policy -> delayed TaskScheduler activation -> automatic signed remote check after reboot, with no manual/MQTT check command and no automatic apply. Final `0.1.17/build 18` remained ONLINE and `VALID`.

Stage 6B physically validates the first real registered component, `connectivity`: TaskScheduler owns its sampling cadence, the component owns state/health, transitions use EventBus, and `/api/components` plus `/api/status` expose the common model.

Latest normal build remains within the 1728 KiB OTA slot at about 68.8% flash and 16.6% static RAM.

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

1. add the Stage 6 `Supervisor` FSM over the validated `ComponentRegistry` / `ComponentHealth` / `EventBus` foundation;
2. migrate MQTT reconnect/telemetry timing to TaskScheduler incrementally without changing network behavior;
3. add more real components only when ownership boundaries are clear;
4. replace development `setInsecure()` with CA validation for MQTT and remote HTTPS;
5. harden MQTT with LWT plus reconnect backoff/jitter;
6. continue toward ConfigurationStore/RuleEngine/local Scheduler and later DS3231/TFT/touch/microSD.

## Source-of-truth invariant

After every validated change:

```text
/home/kernelpanic/Projects/proj-esp32 main == origin/main
```


## Stage 6C implementation checkpoint

The Supervisor FSM is implemented as a real `arduino-fsm` machine and scheduled cooperatively by TaskScheduler. It aggregates only `ComponentRegistry` health, publishes state changes through EventBus, exposes `/api/supervisor`, and is embedded in `/api/status`/MQTT telemetry. The next safe action is the controlled signed physical proof: lab test image -> real MQTT disconnect -> Supervisor `RUNNING -> DEGRADED -> RUNNING` -> clean target image with the test endpoint absent.
