#!/usr/bin/env python3
from pathlib import Path

# Executed only after the physical proof succeeds.
# Promote the normal identity to the validated target and advance test profiles.
p = Path('include/firmware_identity.h')
s = p.read_text()
s = s.replace('#define PROJ_FW_VERSION "0.1.12"', '#define PROJ_FW_VERSION "0.1.14"', 1)
s = s.replace('#define PROJ_FW_BUILD 13', '#define PROJ_FW_BUILD 15', 1)
p.write_text(s)

p = Path('platformio.ini')
s = p.read_text()
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.13\\"\n    -DPROJ_FW_BUILD=14', '-DPROJ_FW_VERSION=\\"0.1.15\\"\n    -DPROJ_FW_BUILD=16', 1)
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.13-remote-test\\"\n    -DPROJ_FW_BUILD=14', '-DPROJ_FW_VERSION=\\"0.1.15-remote-test\\"\n    -DPROJ_FW_BUILD=16', 1)
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.14\\"\n    -DPROJ_FW_BUILD=15', '-DPROJ_FW_VERSION=\\"0.1.16\\"\n    -DPROJ_FW_BUILD=17', 1)
p.write_text(s)

# docs/README milestone and runtime baseline.
p = Path('docs/README.md')
s = p.read_text()
s = s.replace('- [ ] add nonblocking automatic update-check scheduler', '- [x] nonblocking automatic update-check scheduler proven on hardware\n- [ ] replace development `setInsecure()` with CA certificate validation', 1)
# Avoid duplicate CA line if already next item.
s = s.replace('- [ ] replace development `setInsecure()` with CA certificate validation\n- [ ] replace development `setInsecure()` with CA certificate validation', '- [ ] replace development `setInsecure()` with CA certificate validation', 1)
start = s.index('## Current runtime state')
end = s.index('## OTA partition layout', start)
runtime = '''## Current runtime state\n\nValidated directly on the physical device on 2026-09-05 after the automatic update-check scheduler proof:\n\n- hostname: `proj-esp32`\n- mDNS: `proj-esp32.local`\n- device ID: `10A2CCEF49C0`\n- hardware model: `proj-esp32-35`, revision `1`\n- firmware: `0.1.14`, build `15`, channel `dev`\n- running OTA partition: `app1`\n- boot partition: `app1`\n- next update partition: `app0`\n- native image state: `VALID`\n- FSM/system: `ONLINE`\n- Wi-Fi: connected\n- MQTT: connected\n- MQTT transport: TLS\n- remote OTA policy: HTTPS-only\n- automatic update policy currently disabled after the lab proof\n\nThe persisted policy can arm a boot-relative, nonblocking automatic check scheduler. The scheduler waits the configured interval, invokes the same signed RemoteUpdate check path without MQTT or Web input, records runtime attempt counters without high-frequency NVS writes, and never auto-applies firmware. The physical proof discovered `0.1.14/build 15` automatically after reboot; operator apply then completed `PENDING_VERIFY -> VALID`.\n\n'''
s = s[:start] + runtime + s[end:]
p.write_text(s)

# BOOTSTRAP baseline and next steps.
p = Path('docs/BOOTSTRAP.md')
s = p.read_text()
start = s.index('## Current firmware baseline — verified 2026-09-05')
end = s.index('## Flash layout — validated', start)
baseline = '''## Current firmware baseline — verified 2026-09-05\n\nCurrent physical device state after the automatic update scheduler proof:\n\n- model: `proj-esp32-35`\n- hardware revision: `1`\n- firmware: `0.1.14`\n- build: `15`\n- channel: `dev`\n- running partition: `app1`\n- boot partition: `app1`\n- next update partition: `app0`\n- native OTA image state: `VALID`\n- system/FSM: `ONLINE`\n- Wi-Fi: connected\n- MQTT/TLS: connected\n- hostname: `proj-esp32`\n- mDNS: `proj-esp32.local`\n- device ID: `10A2CCEF49C0`\n\nSigned Web OTA, remote check/apply, MQTT triggers, persisted NVS policy and the automatic check scheduler now share the same UpdateManager path. Automatic scheduling is check-only: it never applies a firmware image without an explicit operator/control-plane apply request. Network failure can delay or fail an update check but cannot stop local control.\n\nLatest normal build remains within the 1728 KiB OTA slot with roughly 68-70% flash occupancy and about 16-17% static RAM usage.\n\n'''
s = s[:start] + baseline + s[end:]
start = s.index('## Immediate next steps')
end = s.index('## Source-of-truth invariant', start)
steps = '''## Immediate next steps\n\n1. replace development `setInsecure()` with CA validation for MQTT and remote HTTPS;\n2. harden MQTT with LWT plus reconnect backoff/jitter;\n3. begin Stage 6 modular runtime (`ComponentRegistry`, common health model, EventBus and Supervisor);\n4. add explicit component/update health metadata using the common model;\n5. mount LittleFS and add minimal recovery UI;\n6. implement local ConfigurationStore/RuleEngine/Scheduler without connectivity dependencies;\n7. proceed to DS3231/TFT/touch/microSD only after physical pin mapping confirmation.\n\n'''
s = s[:start] + steps + s[end:]
p.write_text(s)

# ROADMAP Stage 5 -> validated.
p = Path('docs/ROADMAP.md')
s = p.read_text()
s = s.replace('## Stage 5 — Remote transport, MQTT triggers and persisted policy validated; automatic scheduler pending', '## Stage 5 — Remote transport, MQTT triggers, persisted policy and automatic scheduler [validated]', 1)
s = s.replace('Remote signed check/apply, MQTT `firmware.check` / `firmware.update`, and persistent NVS update policy have been proven on the physical ESP32. Bare `firmware.check` resolves the stored HTTPS manifest URL. Only the nonblocking automatic scheduler remains pending and must reuse that same path.', 'Remote signed check/apply, MQTT `firmware.check` / `firmware.update`, persistent NVS update policy, and a nonblocking automatic check scheduler have all been proven on the physical ESP32. Bare `firmware.check` resolves the stored HTTPS manifest URL, while the automatic scheduler triggers that same check path after the configured boot-relative interval. Automatic scheduling is check-only and never auto-applies firmware.', 1)
p.write_text(s)

# OTA test evidence.
p = Path('docs/ota-test-log.md')
s = p.read_text()
if 'automatic update-check scheduler proof' not in s:
    s += '''\n## 2026-09-05 — automatic update-check scheduler proof\n\n- Starting image: `0.1.12/build 13`, `app1/VALID`, ONLINE with MQTT/TLS.\n- Installed signed scheduler-capable transition image `0.1.13-remote-test/build 14` to `app0`; observed `PENDING_VERIFY -> VALID`.\n- Started a temporary HTTPS release fixture on `kpnote` serving signed target `0.1.14/build 15`.\n- Persisted policy with `enabled=true`, interval 60 seconds and the HTTPS manifest URL, then rebooted the ESP32.\n- After reboot the scheduler re-armed from the persisted policy using boot-relative `millis()` timing; no manual Web call and no MQTT `firmware.check` command was sent.\n- At the due time, scheduler attempt/accepted counters advanced and RemoteUpdate reached `AVAILABLE` with candidate `0.1.14/build 15`.\n- Policy `last_result` became `available`; policy revision did not change merely because a check executed.\n- The scheduler did not auto-apply. An explicit operator `POST /api/update/apply` was then issued.\n- Target image reached `0.1.14/app1/PENDING_VERIFY -> VALID`.\n- Temporary policy was disabled afterward so the dead lab fixture would not generate future checks.\n- Final image remained ONLINE with Wi-Fi and MQTT/TLS, restored HTTPS-only remote policy, and removed the lab MQTT loopback endpoint.\n\nThis closes Stage 5D: automatic checks are nonblocking, policy-driven, reboot-safe, and reuse the exact signed remote UpdateManager path without introducing an automatic apply path.\n'''
p.write_text(s)

print('SCHEDULER_PROOF_PROMOTION_UPDATED')
