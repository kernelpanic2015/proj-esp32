from pathlib import Path
import re


def rw(path):
    p = Path(path)
    return p, p.read_text()


def one(s, old, new, label):
    if old not in s:
        raise SystemExit(f"missing {label}")
    return s.replace(old, new, 1)


def section(s, start, end, replacement):
    a = s.find(start)
    if a < 0:
        raise SystemExit(f"missing section {start}")
    b = s.find(end, a + len(start))
    if b < 0:
        raise SystemExit(f"missing next section {end}")
    return s[:a] + replacement.rstrip() + "\n\n" + s[b:]

# Promote canonical identity to the clean image physically proven by Stage 6D.
p, s = rw('include/firmware_identity.h')
s = one(s, '#define PROJ_FW_VERSION "0.1.20"', '#define PROJ_FW_VERSION "0.1.22"', 'fw version')
s = one(s, '#define PROJ_FW_BUILD 21', '#define PROJ_FW_BUILD 23', 'fw build')
p.write_text(s)

# Advance monotonic test profiles for the next incremental runtime work.
p, s = rw('platformio.ini')
def set_env(text, env, version, build):
    pat = r'(\[env:' + re.escape(env) + r'\]\n)(.*?)(?=\n\[env:|\Z)'
    m = re.search(pat, text, re.S)
    if not m:
        raise SystemExit('missing env ' + env)
    block = m.group(2)
    block, n1 = re.subn(r'-DPROJ_FW_VERSION=\\"[^\n]+?\\"', '-DPROJ_FW_VERSION=\\"' + version + '\\"', block, count=1)
    block, n2 = re.subn(r'-DPROJ_FW_BUILD=\d+', '-DPROJ_FW_BUILD=' + str(build), block, count=1)
    if n1 != 1 or n2 != 1:
        raise SystemExit('version/build missing in ' + env)
    return text[:m.start(2)] + block + text[m.end(2):]

s = set_env(s, 'nodemcu-32s-signed-update-test', '0.1.23', 24)
s = set_env(s, 'nodemcu-32s-remote-update-test', '0.1.23-remote-test', 24)
s = set_env(s, 'nodemcu-32s-remote-target-test', '0.1.24', 25)
p.write_text(s)

# Roadmap: Stage 6D validated, next safe incremental migration stays within Stage 6.
p, s = rw('docs/ROADMAP.md')
s = s.replace('## Stage 6 — Core modular runtime [in progress — Stage 6C validated, Stage 6D next]',
              '## Stage 6 — Core modular runtime [in progress — Stage 6D validated]')
s = s.replace('- [~] **Stage 6D** — MQTT reconnect eligibility/retry cadence and periodic telemetry heartbeat migrated to TaskScheduler; physical disconnect/reconnect + telemetry proof pending.',
              '- [x] **Stage 6D** — MQTT reconnect eligibility/retry cadence and periodic telemetry heartbeat migrated to TaskScheduler and physically proven through disconnect/recovery + telemetry re-arm.')
marker = 'Stage 6C is physically validated on `0.1.20/build 21`: a real MQTT interruption kept Wi-Fi/HTTP and the application FSM online, moved `connectivity` to `WIFI_ONLY/DEGRADED` and Supervisor to `DEGRADED`, then recovered both to `ONLINE/OK` and `RUNNING/OK`. EventBus dropped count remained zero.'
replacement = marker + '\n\nStage 6D is physically validated on `0.1.22/build 23`: automatic MQTT reconnect timing and the 10 s telemetry heartbeat now belong to TaskScheduler. During a real broker disconnect, the telemetry work task disabled, connectivity/Supervisor degraded without affecting the application `ONLINE` state, the reconnect task recovered the session after eligibility returned, and telemetry re-armed with a delayed first run. The clean final image returned to HTTPS-only update policy and removed the lab endpoint.'
if 'Stage 6D is physically validated on `0.1.22/build 23`' not in s:
    s = s.replace(marker, replacement)
p.write_text(s)

# Runtime physical result.
p, s = rw('docs/runtime-test-log.md')
s = s.replace('- physical proof pending: signed lab image, real MQTT disconnect/recovery, telemetry counter progression, clean target image.',
              '- physical proof completed: signed lab image, real MQTT disconnect/recovery, telemetry counter progression, and clean target image all passed.')
if '### Stage 6D physical result — PASS' not in s:
    s += '''\n### Stage 6D physical result — PASS\n\n- Signed lab image `0.1.21-remote-test/build 22` installed on `app0` and completed `PENDING_VERIFY -> VALID`.\n- On boot, TaskScheduler performed the initial MQTT connect (`reconnect_attempt_count=1`, `reconnect_success_count=1`) and left the reconnect task disabled while connected.\n- The telemetry task was enabled only after MQTT became connected and produced its first publish after the delayed heartbeat interval (`telemetry_publish_count=1`, `last_telemetry_result=published`).\n- A real MQTT disconnect was triggered with reconnect suppressed for 8 s only in the test image. While disconnected, the application remained `ONLINE`, `connectivity=WIFI_ONLY/DEGRADED`, Supervisor became `DEGRADED`, and the telemetry task was disabled.\n- Once reconnect became eligible, the TaskScheduler reconnect path increased the attempt/success counters, restored MQTT, returned `connectivity=ONLINE/OK` and Supervisor `RUNNING/OK`, and left the reconnect task disabled again.\n- Telemetry then re-armed with its normal delay and the publish counter advanced again.\n- Clean target `0.1.22/build 23` installed on `app1`, completed `PENDING_VERIFY -> VALID`, returned ONLINE with Wi-Fi + MQTT/TLS, and produced a scheduled telemetry publish on the clean image.\n- EventBus remained `dropped=0`; the lab-only disconnect endpoint returned HTTP 404 on the final image.\n- The first proof wrapper stopped after the degradation assertion despite the device recovering; a focused continuation repeated the real disconnect/recovery assertions and ended `STAGE6D_PHYSICAL_PROOF_OK`.\n\n**Stage 6D: VALIDATED.**\n'''
p.write_text(s)

# Architecture closure note.
p, s = rw('docs/architecture.md')
if '### Stage 6D physical proof and closure' not in s:
    s += '''\n\n### Stage 6D physical proof and closure\n\nStage 6D is physically validated. `lastMqttAttempt` and `lastHeartbeat` are gone from the main loop. A lightweight coordinator task determines eligibility; the reconnect work task is disabled while connected/unavailable and runs immediately when reconnect becomes meaningful, then repeats on the configured retry interval after failures; the telemetry work task is disabled while disconnected and uses delayed activation after connection.\n\nThe controlled proof showed `ONLINE/OK -> WIFI_ONLY/DEGRADED -> ONLINE/OK` for connectivity and `RUNNING/OK -> DEGRADED -> RUNNING/OK` for Supervisor during a real MQTT interruption, while the application FSM remained `ONLINE`. Reconnect counters advanced through the TaskScheduler path and telemetry publishing resumed after its delayed interval. The clean `0.1.22/build 23` image is the promoted baseline.\n\n`PubSubClient::loop()` intentionally remains a fast cooperative call in the main loop; Stage 6D migrated timing/eligibility without changing the proven transport implementation. Future migration should only move additional work when it improves the common TaskScheduler + FSM pattern without destabilizing local control.\n'''
p.write_text(s)

# Documentation index/current physical baseline.
p, s = rw('docs/README.md')
s = s.replace('- [ ] replace development `setInsecure()` with CA certificate validation', '- [ ] replace development `setInsecure()` with CA certificate validation')
if '- [x] MQTT reconnect + telemetry timing migrated to TaskScheduler and physically proven' not in s:
    s = s.replace('- [x] standardized ComponentHealth metadata + bounded EventBus transition routing\n',
                  '- [x] standardized ComponentHealth metadata + bounded EventBus transition routing\n- [x] MQTT reconnect + telemetry timing migrated to TaskScheduler and physically proven\n')
new_runtime = '''## Current runtime state\n\nValidated directly on the physical device on 2026-09-05 after Stage 6D closure:\n\n- hostname: `proj-esp32`\n- mDNS: `proj-esp32.local`\n- device ID: `10A2CCEF49C0`\n- hardware model: `proj-esp32-35`, revision `1`\n- firmware: `0.1.22`, build `23`, channel `dev`\n- running OTA partition: `app1`\n- boot partition: `app1`\n- next update partition: `app0`\n- native image state: `VALID`\n- application FSM/system: `ONLINE`\n- Wi-Fi: connected\n- MQTT: connected over TLS\n- `connectivity`: `ONLINE/OK`\n- Supervisor: `RUNNING/OK`\n- EventBus: `dropped=0`\n- MQTT scheduler: coordinator enabled, reconnect work task disabled while connected, telemetry task enabled\n- scheduled telemetry: physically proven after delayed activation\n- remote OTA policy: HTTPS-only\n- lab-only MQTT disconnect endpoint: absent from the clean image\n\nStage 6D moves automatic MQTT reconnect timing and periodic telemetry from hand-written `millis()` checks to TaskScheduler while preserving the existing PubSubClient transport behavior. Work tasks are disabled whenever their work is not meaningful. The next Stage 6 changes should remain incremental; candidates include Wi-Fi retry timing and later network hardening, but only when they fit the same TaskScheduler + FSM ownership model.\n'''
s = section(s, '## Current runtime state', '## OTA partition layout', new_runtime)
p.write_text(s)

# Bootstrap/handoff.
p, s = rw('docs/BOOTSTRAP.md')
new_base = '''## Current firmware baseline — verified 2026-09-05\n\nCurrent physical device state after Stage 6D MQTT TaskScheduler closure:\n\n- model: `proj-esp32-35`\n- hardware revision: `1`\n- firmware: `0.1.22`\n- build: `23`\n- channel: `dev`\n- running partition: `app1`\n- boot partition: `app1`\n- next update partition: `app0`\n- native OTA image state: `VALID`\n- application FSM/system: `ONLINE`\n- Wi-Fi: connected\n- MQTT/TLS: connected\n- `connectivity`: `ONLINE/OK`\n- Supervisor: `RUNNING/OK`\n- EventBus dropped count: `0`\n- hostname: `proj-esp32`\n- mDNS: `proj-esp32.local`\n- device ID: `10A2CCEF49C0`\n\n`arkhipenko/TaskScheduler` 4.0.8 runs alongside `jonblack/arduino-fsm`: TaskScheduler owns timing/eligibility, FSMs own state/behavior, components own subsystem interpretation, EventBus owns transition delivery, and Supervisor aggregates only registry health.\n\nStage 6D physically proved the MQTT scheduling migration. Reconnect timing and telemetry heartbeat no longer use `lastMqttAttempt`/`lastHeartbeat` polling in the main loop. A real disconnect disabled telemetry work, degraded connectivity/Supervisor without changing the application `ONLINE` state, then the scheduler restored MQTT and re-armed telemetry with its delayed interval. `PubSubClient::loop()` remains an intentional fast cooperative main-loop service call.\n\nNormal build remains within the 1728 KiB OTA slot at roughly 17% static RAM and 70% flash usage.\n'''
s = section(s, '## Current firmware baseline — verified 2026-09-05', '## Flash layout — validated', new_base)
new_next = '''## Immediate next steps\n\n1. Continue Stage 6 incrementally under the same TaskScheduler + FSM rule; evaluate Wi-Fi retry timing as the next migration candidate rather than rewriting stable code wholesale.\n2. Replace development `setInsecure()` with CA validation for MQTT and remote HTTPS.\n3. Add MQTT LWT/retained offline state and reconnect backoff/jitter after certificate validation design is settled.\n4. Keep network loss as `DEGRADED`, never as a prerequisite for local control.\n5. Continue toward ConfigurationStore/RuleEngine/local Scheduler, then DS3231/TFT/touch/microSD.\n'''
s = section(s, '## Immediate next steps', '## Source-of-truth invariant', new_next)
idx = s.find('## Stage 6C closure')
if idx >= 0:
    s = s[:idx].rstrip() + '''\n\n## Stage 6D closure\n\nStage 6D is validated. The physical baseline is `0.1.22/build 23` on `app1`, native image `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, `Supervisor=RUNNING/OK`, MQTT/TLS connected and EventBus `dropped=0`. Automatic MQTT reconnect timing and periodic telemetry now use TaskScheduler; their work tasks stay disabled when unnecessary. Proceed incrementally from this baseline.\n'''
p.write_text(s)

# Root README concise baseline.
p, s = rw('README.md')
if 'Stage 6D physical baseline' not in s:
    needle = '## Validated baseline — 2026-09-05\n'
    s = s.replace(needle, needle + '\n**Stage 6D physical baseline:** `0.1.22/build 23`, `app1`, native OTA `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, `Supervisor=RUNNING/OK`, Wi-Fi + MQTT/TLS connected. MQTT reconnect and telemetry timing are now TaskScheduler-driven.\n', 1)
p.write_text(s)

# Keep automatic-update regression proof aligned with the promoted baseline and next builds.
p, s = rw('scripts/smoke_update_scheduler.sh')
repls = {
    '"version":"0.1.20"': '"version":"0.1.22"',
    '"build":21': '"build":23',
    '--version 0.1.21-remote-test --build 22': '--version 0.1.23-remote-test --build 24',
    '--version 0.1.22 --build 23': '--version 0.1.24 --build 25',
    "wait_for_transition '0.1.21-remote-test' 22 app0": "wait_for_transition '0.1.23-remote-test' 24 app0",
    "wait_for_online '0.1.21-remote-test' 22": "wait_for_online '0.1.23-remote-test' 24",
    '"candidate_build":23': '"candidate_build":25',
    "wait_for_transition '0.1.22' 23 app1": "wait_for_transition '0.1.24' 25 app1",
    '"version":"0.1.22"': '"version":"0.1.24"',
    '"build":23': '"build":25',
}
# Apply version/build baseline replacements carefully: first assertions at top need baseline,
# later final assertions need target. Use explicit known snippets where possible.
s = s.replace("grep -q '\"version\":\"0.1.20\"' <<<\"$V\"", "grep -q '\"version\":\"0.1.22\"' <<<\"$V\"")
s = s.replace("grep -q '\"build\":21' <<<\"$V\"", "grep -q '\"build\":23' <<<\"$V\"")
s = s.replace('--version 0.1.21-remote-test --build 22', '--version 0.1.23-remote-test --build 24')
s = s.replace('--version 0.1.22 --build 23', '--version 0.1.24 --build 25')
s = s.replace("wait_for_transition '0.1.21-remote-test' 22 app0", "wait_for_transition '0.1.23-remote-test' 24 app0")
s = s.replace("wait_for_online '0.1.21-remote-test' 22", "wait_for_online '0.1.23-remote-test' 24")
s = s.replace('"candidate_build":23', '"candidate_build":25')
s = s.replace("wait_for_transition '0.1.22' 23 app1", "wait_for_transition '0.1.24' 25 app1")
s = s.replace("grep -q '\"version\":\"0.1.22\"' <<<\"$S\"", "grep -q '\"version\":\"0.1.24\"' <<<\"$S\"")
s = s.replace("grep -q '\"build\":23' <<<\"$S\"", "grep -q '\"build\":25' <<<\"$S\"")
p.write_text(s)

# Stage-specific temporary proof/staging helpers are not maintained after closure.
for path in [
    'scripts/stage6d_physical_proof.sh',
    'scripts/stage6d_physical_continue.sh',
    'scripts/stage6d_notes.txt',
]:
    Path(path).unlink(missing_ok=True)

print('STAGE6D_CLOSURE_PATCH_OK')
