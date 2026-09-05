from pathlib import Path

# Promote normal firmware identity to the physically validated image.
p = Path('include/firmware_identity.h')
s = p.read_text()
s = s.replace('#define PROJ_FW_VERSION "0.1.8"', '#define PROJ_FW_VERSION "0.1.10"')
s = s.replace('#define PROJ_FW_BUILD 9', '#define PROJ_FW_BUILD 11')
p.write_text(s)

# Advance reusable test profiles one cycle.
p = Path('platformio.ini')
s = p.read_text()
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.9\\"\n    -DPROJ_FW_BUILD=10',
              '-DPROJ_FW_VERSION=\\"0.1.11\\"\n    -DPROJ_FW_BUILD=12')
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.9-remote-test\\"\n    -DPROJ_FW_BUILD=10',
              '-DPROJ_FW_VERSION=\\"0.1.11-remote-test\\"\n    -DPROJ_FW_BUILD=12')
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.10\\"\n    -DPROJ_FW_BUILD=11',
              '-DPROJ_FW_VERSION=\\"0.1.12\\"\n    -DPROJ_FW_BUILD=13')
p.write_text(s)

# Documentation index and runtime state.
p = Path('docs/README.md')
s = p.read_text()
s = s.replace('- [ ] add MQTT and automatic triggers to the validated remote update service',
              '- [x] MQTT `firmware.check <url>` / `firmware.update` triggers validated through the real broker\n- [ ] add persisted automatic update-check policy')
start = s.index('## Current runtime state')
end = s.index('## OTA partition layout', start)
runtime = '''## Current runtime state

Validated directly on the physical device on 2026-09-05 after the MQTT-triggered remote OTA proof:

- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`
- hardware model: `proj-esp32-35`, revision `1`
- firmware: `0.1.10`, build `11`, channel `dev`
- running OTA partition: `app1`
- boot partition: `app1`
- next update partition: `app0`
- native image state: `VALID`
- FSM/system: `ONLINE`
- Wi-Fi: connected
- MQTT: connected
- MQTT transport: TLS
- remote OTA policy: HTTPS-only

MQTT now acts only as a trigger plane for the already validated signed remote UpdateManager. The physical proof published `firmware.check <manifest-url>` and `firmware.update` through the real CloudAMQP broker without exposing credentials to the job; the device fetched/verified/applied the signed package itself and reached `0.1.10/build 11` in `app1/VALID`.

'''
s = s[:start] + runtime + s[end:]
p.write_text(s)

# Bootstrap baseline and immediate next steps.
p = Path('docs/BOOTSTRAP.md')
s = p.read_text()
start = s.index('## Current firmware baseline — verified 2026-09-05')
end = s.index('## Flash layout — validated', start)
baseline = '''## Current firmware baseline — verified 2026-09-05

Current physical device state after the MQTT-triggered remote OTA proof:

- model: `proj-esp32-35`
- hardware revision: `1`
- firmware: `0.1.10`
- build: `11`
- channel: `dev`
- running partition: `app1`
- boot partition: `app1`
- next update partition: `app0`
- native OTA image state: `VALID`
- system/FSM: `ONLINE`
- Wi-Fi: connected
- MQTT/TLS: connected
- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`

Validated OTA control surfaces now share one signed install engine: manual Web prepare/upload, remote HTTP API check/apply, and MQTT trigger commands. MQTT transports only the request; manifest/signature and firmware are fetched directly by the ESP32.

Resolved dependency baseline:

- arduino-fsm 2.2.0
- ESP_DoubleResetDetector 1.3.2
- WiFiManager 2.0.17
- PubSubClient 2.8.0
- AsyncTCP 3.5.0
- ESPAsyncWebServer 3.12.0
- WebSerial 2.1.2
- ArduinoJson 6.21.x
- ESPmDNS 2.0.0
- Preferences / WiFi / WiFiClientSecure / HTTPClient / Update from Arduino-ESP32

Latest normal build after MQTT-trigger integration:

- RAM: about 54.3 KiB / 320 KiB (16.6%)
- firmware: about 1.20 MiB / 1.6875 MiB application slot (about 67.9%)

'''
s = s[:start] + baseline + s[end:]
next_start = s.index('## Immediate next steps')
next_end = s.index('## Source-of-truth invariant', next_start)
next_steps = '''## Immediate next steps

1. persist remote-update policy in NVS (`enabled`, manifest URL, channel, interval, last result) so bare `firmware.check` and automatic checks share the same configured source;
2. add the nonblocking automatic-check scheduler without making local control depend on connectivity;
3. replace development `setInsecure()` with CA validation for MQTT and remote HTTPS;
4. harden MQTT with LWT and reconnect backoff/jitter;
5. continue modular runtime (`ComponentRegistry`, health model, Supervisor, local rules/scheduler);
6. mount LittleFS and add minimal recovery UI;
7. proceed to TFT/touch/microSD bring-up only after pinout confirmation.

'''
s = s[:next_start] + next_steps + s[next_end:]
p.write_text(s)

# OTA architecture MQTT milestone.
p = Path('docs/ota.md')
s = p.read_text()
if '## MQTT update triggers — validated' not in s:
    s += '''
## MQTT update triggers — validated 2026-09-05

MQTT does not carry firmware. It only requests actions from `RemoteFirmwareUpdate`, which is the same transport feeding the signed `FirmwareUpdate` engine used by Web/API.

Validated commands on the per-device `/cmd` topic:

```text
firmware.status
firmware.check <manifest-url>
firmware.update
```

Physical proof used the device's already provisioned CloudAMQP session. A lab-only local endpoint published the commands onto the real command topic so no broker password appeared in GitHub/Aurora jobs. The broker returned the messages to the subscribed ESP32 client, which reached `AVAILABLE` after `firmware.check` and then downloaded/applied `0.1.10/build 11` after `firmware.update`.

The lab loopback endpoint exists only in the controlled remote-test profile and returned HTTP 404 after booting the final normal image. The final image also returned to HTTPS-only remote-update policy.
'''
p.write_text(s)

# Physical test log.
p = Path('docs/ota-test-log.md')
s = p.read_text()
if 'MQTT-triggered remote signed OTA proof' not in s:
    s += '''
## 2026-09-05 — MQTT-triggered remote signed OTA proof

- Starting image: `0.1.8`, build `9`, `app1/VALID`, `ONLINE`, MQTT/TLS connected.
- Signed Web transition installed `0.1.9-remote-test`, build `10`, into `app0` and observed `PENDING_VERIFY -> VALID`.
- The transition profile alone enabled plain HTTP for the LAN fixture and a credential-free MQTT loopback test endpoint.
- The loopback endpoint published onto the device's real CloudAMQP `/cmd` topic using the existing broker session; no MQTT credentials were placed in the Aurora job.
- MQTT command `firmware.check http://192.168.1.115:8766/manifest.json` was delivered through the broker and caused the ESP32 remote service to reach `AVAILABLE` with candidate `0.1.10/build 11` prepared and ECDSA-verified.
- MQTT command `firmware.update` was delivered through the broker and triggered the existing remote downloader/install engine.
- Target image SHA-256: `1a4714aee70ce16f1cf4a93a12d2c3e227f6358c7d3ca4b57f8f59460fa35e7a`.
- Target boot: `0.1.10/build 11`, `app1/PENDING_VERIFY -> app1/VALID`.
- Final runtime: `ONLINE`, Wi-Fi connected, MQTT connected/configured, MQTT TLS enabled, free heap about `163 KiB`.
- Final normal image reported `http_allowed=false` and the lab-only MQTT loopback endpoint returned HTTP `404`.
- Aurora proof job UUID: `21510fa8-8260-4782-8904-906c0faf2617`, completed with exit code `0`.

This proves MQTT is a management trigger rather than an OTA transport: signed manifest verification, firmware download, SHA-256 validation, A/B install, `PENDING_VERIFY`, validation and rollback remain inside the common UpdateManager path.
'''
p.write_text(s)

# MQTT command documentation.
p = Path('docs/mqtt.md')
s = p.read_text()
if '## Firmware update trigger commands' not in s:
    insert = '''
## Firmware update trigger commands

Validated through the real CloudAMQP broker on 2026-09-05:

```text
firmware.status
firmware.check <https://.../manifest.json>
firmware.update
```

`firmware.check` asks the shared remote update service to fetch and verify the signed manifest. `firmware.update` is accepted only after a candidate is in `AVAILABLE` state. MQTT never transports the binary; the ESP32 downloads `firmware.bin` directly and runs the same signed SHA-256/A-B/rollback path used by Web OTA.

A plain `firmware.check` without a URL is currently rejected with `manifest_url_required`. The next milestone persists the update source/policy in NVS, after which the bare command can use the configured source.

'''
    s = s.replace('## Reproducible notebook smoke test\n', insert + '## Reproducible notebook smoke test\n', 1)
p.write_text(s)

# Roadmap stage 5.
p = Path('docs/ROADMAP.md')
s = p.read_text()
s = s.replace('## Stage 5 — Remote transport validated; MQTT and automatic triggers pending',
              '## Stage 5 — Remote transport + MQTT triggers validated; automatic policy pending')
s = s.replace('Remote signed check/apply has been proven on the physical ESP32. MQTT and automatic policy remain triggers only; they must reuse that path.',
              'Remote signed check/apply and MQTT `firmware.check` / `firmware.update` triggers have been proven on the physical ESP32. Automatic policy remains pending and must reuse that same path.')
p.write_text(s)

# Advance physical smoke scripts to next release cycle.
for filename in ['scripts/smoke_remote_ota.sh', 'scripts/smoke_mqtt_ota.sh']:
    p = Path(filename)
    s = p.read_text()
    s = s.replace('0.1.8', '0.1.10').replace('"build":9', '"build":11')
    s = s.replace('0.1.9-remote-test', '0.1.11-remote-test').replace(' 10 app0', ' 12 app0')
    s = s.replace('candidate_build\":11', 'candidate_build\":13')
    s = s.replace("'0.1.10' 11 app1", "'0.1.12' 13 app1")
    p.write_text(s)

print('MQTT_OTA_PROOF_PROMOTED')
