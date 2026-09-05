from pathlib import Path
import re


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'missing {label}: {old!r}')
    return text.replace(old, new, 1)


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

# Promote physical clean target as canonical identity.
p = Path('include/firmware_identity.h')
s = p.read_text()
s = replace_once(s, '#define PROJ_FW_VERSION "0.1.22"', '#define PROJ_FW_VERSION "0.1.25"', 'canonical version')
s = replace_once(s, '#define PROJ_FW_BUILD 23', '#define PROJ_FW_BUILD 26', 'canonical build')
p.write_text(s)

# Advance monotonic test profiles for Stage 7 and future migration proofs.
p = Path('platformio.ini')
s = p.read_text()
s = set_env(s, 'nodemcu-32s-signed-update-test', '0.1.26', 27)
s = set_env(s, 'nodemcu-32s-remote-update-test', '0.1.26-remote-test', 27)
s = set_env(s, 'nodemcu-32s-remote-target-test', '0.1.27', 28)
p.write_text(s)

# Roadmap: Stage 6 core runtime is now validated; Stage 7 is next.
p = Path('docs/ROADMAP.md')
s = p.read_text()
s = re.sub(r'## Stage 6 — Core modular runtime \[[^\]]+\]', '## Stage 6 — Core modular runtime [validated]', s, count=1)
s = s.replace('- [~] **Stage 6E** — migrate Wi-Fi reconnect eligibility/retry cadence to TaskScheduler, keeping the reconnect work task disabled while Wi-Fi is healthy or the config portal is active.',
              '- [x] **Stage 6E** — Wi-Fi reconnect eligibility/retry cadence migrated to TaskScheduler; reconnect work remains disabled while Wi-Fi is healthy or the config portal is active; physical disconnect/recovery proven.')
if 'Stage 6E is physically validated' not in s:
    anchor = 'Stage 6C is physically validated on `0.1.20/build 21`: a real MQTT interruption kept Wi-Fi/HTTP and the application FSM online, moved `connectivity` to `WIFI_ONLY/DEGRADED` and Supervisor to `DEGRADED`, then recovered both to `ONLINE/OK` and `RUNNING/OK`. EventBus dropped count remained zero.'
    addition = '''\n\nStage 6D migrated MQTT reconnect and periodic telemetry timing to TaskScheduler. Stage 6E is physically validated on the clean `0.1.25/build 26` baseline: a controlled full Wi-Fi interruption was observed, the Wi-Fi reconnect work task became eligible only while needed, one reconnect attempt/success restored Wi-Fi and MQTT, connectivity/Supervisor returned to `ONLINE/OK` and `RUNNING/OK`, telemetry resumed, and EventBus dropped count remained zero. A status-payload growth regression discovered during the proof was corrected by making the PubSubClient buffer an explicit 4096-byte project setting.\n\nStage 6 core is therefore validated. Future subsystems should continue adopting the same TaskScheduler + FSM pattern opportunistically rather than through wholesale rewrites.'''
    if anchor in s:
        s = s.replace(anchor, anchor + addition, 1)
    else:
        s += addition
p.write_text(s)

# Runtime physical validation log.
p = Path('docs/runtime-test-log.md')
s = p.read_text()
if '### Stage 6E physical result — PASS' not in s:
    s += '''\n\n### Stage 6E physical result — PASS\n\n- Wi-Fi retry timing was removed from the main-loop `lastWifiRetry`/`millis()` path and moved to TaskScheduler with a lightweight coordinator plus a reconnect work task.\n- The reconnect task is disabled while Wi-Fi is healthy, while the config portal is active, and during the controlled lab suppression window.\n- Signed lab image `0.1.24-remote-test/build 25` reached native `PENDING_VERIFY -> VALID`.\n- A controlled full Wi-Fi disconnect made HTTP unavailable and was observed by the runtime. After the 8 s test suppression, TaskScheduler recorded one reconnect attempt and one reconnect success; the work task returned to disabled once Wi-Fi recovered.\n- MQTT then reconnected, `connectivity` returned to `ONLINE/OK`, Supervisor returned to `RUNNING/OK`, and EventBus remained `dropped=0`.\n- Scheduled MQTT telemetry resumed after recovery and published successfully.\n- During the first Stage 6E attempt, the full status document had grown to 2199 bytes while the PubSubClient buffer was 2048 bytes. The runtime correctly exposed repeated `publish_failed`; the buffer was promoted to an explicit 4096-byte project setting and the same >2 KiB status telemetry then published successfully.\n- Clean target `0.1.25/build 26` installed on `app0`, completed `PENDING_VERIFY -> VALID`, returned `ONLINE` with Wi-Fi + MQTT/TLS, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, and the lab-only Wi-Fi disconnect endpoint returned HTTP 404.\n\n**Stage 6E: VALIDATED. Stage 6 core runtime: VALIDATED. Stage 7 is next.**\n'''
p.write_text(s)

# Architecture closure / pattern preservation.
p = Path('docs/architecture.md')
s = p.read_text()
if '### Stage 6E physical closure' not in s:
    s += '''\n\n### Stage 6E physical closure\n\nStage 6E removes the last hand-written periodic Wi-Fi retry timer from the main runtime path. `wifiCoordinatorTask` owns eligibility observation; `wifiReconnectTask` performs reconnect work only while disconnected and eligible. The existing application FSM remains the owner of `ONLINE/OFFLINE` state transitions. On healthy Wi-Fi the reconnect work task is disabled.\n\nPhysical proof on `0.1.24-remote-test/build 25` observed a real Wi-Fi outage, HTTP loss, scheduler-driven reconnect, MQTT recovery, component/Supervisor recovery and telemetry resumption. The clean `0.1.25/build 26` image removed the lab endpoint and remained healthy.\n\nThe Stage 6 runtime pattern is now established: **TaskScheduler owns when work is meaningful and due; FSMs own state/behavior; EventBus carries transitions; components own subsystem interpretation; Supervisor aggregates health only.** Future sensors, actuators, rule evaluation and recovery timers should adopt this pattern when introduced or when a migration materially improves the code.\n'''
p.write_text(s)

# Documentation index + current runtime.
p = Path('docs/README.md')
s = p.read_text()
if '- [x] Wi-Fi reconnect timing migrated to TaskScheduler and physically proven' not in s:
    s = s.replace('- [x] MQTT reconnect + telemetry timing migrated to TaskScheduler and physically proven',
                  '- [x] MQTT reconnect + telemetry timing migrated to TaskScheduler and physically proven\n- [x] Wi-Fi reconnect timing migrated to TaskScheduler and physically proven')
start = s.find('## Current runtime state')
end = s.find('## OTA partition layout', start)
if start < 0 or end < 0:
    raise SystemExit('docs README runtime section missing')
new_runtime = '''## Current runtime state\n\nValidated directly on the physical device on 2026-09-05 after Stage 6E closure:\n\n- hostname: `proj-esp32`\n- mDNS: `proj-esp32.local`\n- device ID: `10A2CCEF49C0`\n- hardware model: `proj-esp32-35`, revision `1`\n- firmware: `0.1.25`, build `26`, channel `dev`\n- running OTA partition: `app0`\n- boot partition: `app0`\n- next update partition: `app1`\n- native image state: `VALID`\n- application FSM/system: `ONLINE`\n- Wi-Fi: connected\n- MQTT: connected over TLS\n- `connectivity`: `ONLINE/OK`\n- Supervisor: `RUNNING/OK`\n- EventBus: `dropped=0`\n- Wi-Fi scheduler: coordinator enabled; reconnect work task disabled while healthy\n- MQTT scheduler: coordinator enabled; reconnect work task disabled while connected; telemetry task enabled\n- PubSubClient payload buffer: explicit 4096 bytes; full status telemetry >2 KiB physically proven\n- remote OTA policy: HTTPS-only\n- lab-only Wi-Fi/MQTT test endpoints: absent from the clean image\n\nStage 6 core runtime is validated. TaskScheduler controls timing/eligibility, FSMs control state/behavior, EventBus carries transitions, components own subsystem health interpretation and Supervisor aggregates health. Further migrations remain incremental and should happen only when they improve the implementation. **Stage 7 — persistent configuration and local RuleEngine — is next.**\n\n'''
s = s[:start] + new_runtime + s[end:]
p.write_text(s)

# Bootstrap current handoff and next actions.
p = Path('docs/BOOTSTRAP.md')
s = p.read_text()
start = s.find('## Current firmware baseline — verified 2026-09-05')
end = s.find('## Flash layout — validated', start)
if start < 0 or end < 0:
    raise SystemExit('bootstrap baseline section missing')
new_base = '''## Current firmware baseline — verified 2026-09-05\n\nCurrent physical device state after Stage 6E / Stage 6 core runtime closure:\n\n- model: `proj-esp32-35`\n- hardware revision: `1`\n- firmware: `0.1.25`\n- build: `26`\n- channel: `dev`\n- running partition: `app0`\n- boot partition: `app0`\n- next update partition: `app1`\n- native OTA image state: `VALID`\n- application FSM/system: `ONLINE`\n- Wi-Fi: connected\n- MQTT/TLS: connected\n- `connectivity`: `ONLINE/OK`\n- Supervisor: `RUNNING/OK`\n- EventBus dropped count: `0`\n- Wi-Fi reconnect work task: disabled while healthy\n- MQTT reconnect work task: disabled while connected\n- MQTT telemetry task: enabled while connected\n- MQTT buffer: explicit `4096` bytes\n- hostname: `proj-esp32`\n- mDNS: `proj-esp32.local`\n- device ID: `10A2CCEF49C0`\n\n`arkhipenko/TaskScheduler` 4.0.8 runs alongside `jonblack/arduino-fsm`: TaskScheduler owns timing/eligibility; FSMs own state/behavior; components own subsystem interpretation; EventBus owns transition delivery; Supervisor aggregates registry health only.\n\nStage 6E physically proved a full Wi-Fi loss and recovery. The reconnect work task ran only while needed, Wi-Fi and MQTT recovered, local runtime health returned to `ONLINE/OK` and `RUNNING/OK`, and telemetry resumed. The same proof found a 2199-byte status payload exceeding the old 2048-byte MQTT buffer; the explicit 4096-byte buffer corrected the regression and >2 KiB scheduled telemetry was physically published.\n\nNormal build remains within the 1728 KiB OTA slot at roughly 17% static RAM and 70% flash usage.\n\n'''
s = s[:start] + new_base + s[end:]
start = s.find('## Immediate next steps')
end = s.find('## Source-of-truth invariant', start)
if start < 0 or end < 0:
    raise SystemExit('bootstrap next section missing')
new_next = '''## Immediate next steps\n\n1. Start **Stage 7** with a versioned, validated, transactional `ConfigurationStore` in NVS.\n2. Introduce the first local `RuleEngine` path with TaskScheduler + FSM semantics and no dependency on Wi-Fi/MQTT/cloud.\n3. Add a local scheduling abstraction for rule evaluation and delayed/settling behavior; tasks remain disabled until work is meaningful.\n4. Keep the cross-cutting network-hardening backlog: replace `setInsecure()` with CA validation, then add MQTT LWT and backoff/jitter.\n5. Continue opportunistic TaskScheduler + FSM migration only when touching a subsystem or when it materially reduces custom timing/recovery code.\n\n'''
s = s[:start] + new_next + s[end:]
# Replace old closure tail if present.
idx = s.find('## Stage 6D closure')
if idx >= 0:
    s = s[:idx].rstrip() + '''\n\n## Stage 6 core closure\n\nStages 6A–6E are validated. Physical baseline is `0.1.25/build 26` on `app0`, native image `VALID`, application `ONLINE`, Wi-Fi + MQTT/TLS connected, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, EventBus `dropped=0`. OTA automatic checks, MQTT reconnect/telemetry and Wi-Fi reconnect timing now use the cooperative TaskScheduler pattern where appropriate. Proceed to Stage 7; preserve this runtime ownership model for future components.\n'''
p.write_text(s)

# Root README concise promotion.
p = Path('README.md')
s = p.read_text()
pat = r'## Validated baseline — 2026-09-05\n\n(?:\*\*Stage 6D physical baseline:\*\*.*?\n\n)?(?:\*\*Stage 6C physical baseline:\*\*.*?\n\n)?'
replacement = '''## Validated baseline — 2026-09-05\n\n**Stage 6 core physical baseline:** `0.1.25/build 26`, `app0`, native OTA `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, Wi-Fi + MQTT/TLS connected and EventBus `dropped=0`. OTA scheduling, MQTT reconnect/telemetry and Wi-Fi reconnect timing use the shared TaskScheduler cooperative runtime; work tasks stay disabled when no meaningful work exists. Stage 7 is next.\n\n'''
s, n = re.subn(pat, replacement, s, count=1, flags=re.S)
if n != 1:
    raise SystemExit('root README baseline section update failed')
p.write_text(s)

# Keep repeatable update-scheduler proof aligned with new canonical baseline and next profiles.
p = Path('scripts/smoke_update_scheduler.sh')
s = p.read_text()
repls = {
    '\"version\":\"0.1.22\"': '\"version\":\"0.1.25\"',
    '\"build\":23': '\"build\":26',
    '--version 0.1.23-remote-test --build 24': '--version 0.1.26-remote-test --build 27',
    '--version 0.1.24 --build 25': '--version 0.1.27 --build 28',
    "wait_for_transition '0.1.23-remote-test' 24 app0": "wait_for_transition '0.1.26-remote-test' 27 app1",
    "wait_for_online '0.1.23-remote-test' 24": "wait_for_online '0.1.26-remote-test' 27",
    '\"candidate_build\":25': '\"candidate_build\":28',
    "wait_for_transition '0.1.24' 25 app1": "wait_for_transition '0.1.27' 28 app0",
    '\"version\":\"0.1.24\"': '\"version\":\"0.1.27\"',
    '\"build\":25': '\"build\":28',
}
for old, new in repls.items():
    s = s.replace(old, new)
p.write_text(s)

# Remove stage-specific proof runners after evidence is recorded.
for path in ['scripts/stage6e_physical_proof.sh', 'scripts/stage6e_physical_continue.sh']:
    Path(path).unlink(missing_ok=True)

print('STAGE6E_CLOSURE_PATCH_OK')
