from pathlib import Path

# Promote normal firmware identity to the physically validated image.
p = Path('include/firmware_identity.h')
s = p.read_text()
s = s.replace('#define PROJ_FW_VERSION "0.1.10"', '#define PROJ_FW_VERSION "0.1.12"', 1)
s = s.replace('#define PROJ_FW_BUILD 11', '#define PROJ_FW_BUILD 13', 1)
p.write_text(s)

# Advance reusable test profiles.
p = Path('platformio.ini')
s = p.read_text()
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.11\\"\n    -DPROJ_FW_BUILD=12',
              '-DPROJ_FW_VERSION=\\"0.1.13\\"\n    -DPROJ_FW_BUILD=14', 1)
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.11-remote-test\\"\n    -DPROJ_FW_BUILD=12',
              '-DPROJ_FW_VERSION=\\"0.1.13-remote-test\\"\n    -DPROJ_FW_BUILD=14', 1)
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.12\\"\n    -DPROJ_FW_BUILD=13',
              '-DPROJ_FW_VERSION=\\"0.1.14\\"\n    -DPROJ_FW_BUILD=15', 1)
p.write_text(s)

# docs/README.md
p = Path('docs/README.md')
s = p.read_text()
s = s.replace('- [ ] add persisted automatic update-check policy',
              '- [x] persist remote-update policy in NVS; reboot/OTA persistence and bare `firmware.check` proven\n- [ ] add nonblocking automatic update-check scheduler', 1)
start = s.index('## Current runtime state')
end = s.index('## OTA partition layout', start)
runtime = '''## Current runtime state

Validated directly on the physical device on 2026-09-05 after the persistent update-policy proof:

- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`
- hardware model: `proj-esp32-35`, revision `1`
- firmware: `0.1.12`, build `13`, channel `dev`
- running OTA partition: `app1`
- boot partition: `app1`
- next update partition: `app0`
- native image state: `VALID`
- FSM/system: `ONLINE`
- Wi-Fi: connected
- MQTT: connected
- MQTT transport: TLS
- remote OTA policy: HTTPS-only
- persisted update-policy revision: `1`

The update policy is stored transactionally in NVS. A saved HTTPS manifest URL survived an explicit reboot and a complete A/B OTA cycle. A bare MQTT `firmware.check` resolved the saved policy URL, reached `AVAILABLE`, and `firmware.update` installed `0.1.12/build 13`. `last_result` persisted as `install_pending_reboot` while the policy revision remained unchanged.

'''
s = s[:start] + runtime + s[end:]
p.write_text(s)

# docs/BOOTSTRAP.md
p = Path('docs/BOOTSTRAP.md')
s = p.read_text()
start = s.index('## Current firmware baseline — verified 2026-09-05')
end = s.index('## Flash layout — validated', start)
baseline = '''## Current firmware baseline — verified 2026-09-05

Current physical device state after the persistent signed update-policy proof:

- model: `proj-esp32-35`
- hardware revision: `1`
- firmware: `0.1.12`
- build: `13`
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

Signed Web OTA, remote check/apply and MQTT triggers share one UpdateManager path. The NVS update-policy document now provides the default manifest source for a bare `firmware.check`; the saved policy survived both a reboot and the OTA transition to `0.1.12/build 13`.

Resolved dependency baseline is unchanged. Latest normal build remains about 16.6% RAM and 68.4% of each 1728 KiB OTA slot.

'''
s = s[:start] + baseline + s[end:]
start = s.index('## Immediate next steps')
end = s.index('## Source-of-truth invariant', start)
steps = '''## Immediate next steps

1. add the nonblocking automatic-check scheduler using the persisted NVS policy, with connectivity failures treated only as degraded update service state;
2. add explicit update-policy health/last-attempt metadata without writing NVS on high-frequency runtime paths;
3. replace development `setInsecure()` with CA validation for MQTT and remote HTTPS;
4. harden MQTT with LWT and reconnect backoff/jitter;
5. continue modular runtime (`ComponentRegistry`, health model, Supervisor, local rules/scheduler);
6. mount LittleFS and add minimal recovery UI;
7. proceed to TFT/touch/microSD bring-up only after pinout confirmation.

'''
s = s[:start] + steps + s[end:]
p.write_text(s)

# docs/ROADMAP.md
p = Path('docs/ROADMAP.md')
s = p.read_text()
s = s.replace('## Stage 5 — Remote transport + MQTT triggers validated; automatic policy pending',
              '## Stage 5 — Remote transport, MQTT triggers and persisted policy validated; automatic scheduler pending', 1)
s = s.replace('Remote signed check/apply and MQTT `firmware.check` / `firmware.update` triggers have been proven on the physical ESP32. Automatic policy remains pending and must reuse that same path.',
              'Remote signed check/apply, MQTT `firmware.check` / `firmware.update`, and persistent NVS update policy have been proven on the physical ESP32. Bare `firmware.check` resolves the stored HTTPS manifest URL. Only the nonblocking automatic scheduler remains pending and must reuse that same path.', 1)
p.write_text(s)

# docs/mqtt.md
p = Path('docs/mqtt.md')
s = p.read_text()
marker = '## Next hardening work'
if '## OTA trigger commands — validated' not in s:
    note = '''## OTA trigger commands — validated

The command topic now supports `firmware.status`, `firmware.check`, `firmware.check <manifest-url>`, and `firmware.update`. A bare `firmware.check` reads the persisted NVS update policy and uses its saved HTTPS manifest URL. This was physically proven across an explicit reboot and a complete OTA to `0.1.12/build 13`; the broker remains only the trigger plane.

'''
    s = s.replace(marker, note + marker, 1)
p.write_text(s)

# docs/ota-test-log.md
p = Path('docs/ota-test-log.md')
s = p.read_text()
if 'update policy persistence and bare firmware.check proof' not in s:
    s += '''
## 2026-09-05 — update policy persistence and bare firmware.check proof

- Starting image: `0.1.10/build 11`, `app1/VALID`, ONLINE with MQTT/TLS.
- Installed signed policy-capable transition image `0.1.11-remote-test/build 12` to `app0`; observed `PENDING_VERIFY -> VALID`.
- Stored NVS policy revision `1` with HTTPS manifest URL, channel `dev`, interval 3600 s, auto-enabled `false`.
- Policy POST returned `ready=true`; a subsequent GET matched the saved document.
- Explicit reboot was triggered through the real MQTT command round trip; after reconnect, revision, URL and `policy_updated` result were unchanged.
- Bare MQTT `firmware.check` (no URL argument) resolved the saved policy URL and reached remote state `AVAILABLE`; prepared candidate was `0.1.12/build 13`.
- `last_result` changed to `available` without changing policy revision.
- MQTT `firmware.update` installed the signed target; observed `0.1.12/app1/PENDING_VERIFY -> VALID`.
- Final policy remained revision `1`, preserved the same HTTPS manifest URL, and persisted `last_result=install_pending_reboot`.
- Final runtime remained ONLINE with Wi-Fi and MQTT/TLS connected; normal image restored HTTPS-only policy and removed the lab MQTT loopback endpoint (HTTP 404).
- Aurora proof issue #644 completed successfully.

This proves NVS update-policy persistence independently across reboot and A/B OTA, and proves that `firmware.check` can use the saved policy source without transmitting a manifest URL in the MQTT command.
'''
p.write_text(s)

print('PROMOTION_FILES_UPDATED')
