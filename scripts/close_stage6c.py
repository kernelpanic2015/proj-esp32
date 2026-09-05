from pathlib import Path
import re


def rw(path):
    p = Path(path)
    return p, p.read_text()


def section(text, start, end, replacement):
    a = text.find(start)
    if a < 0:
        raise SystemExit(f"missing section {start}")
    b = text.find(end, a + len(start))
    if b < 0:
        raise SystemExit(f"missing next section {end}")
    return text[:a] + replacement.rstrip() + "\n\n" + text[b:]


# Canonical firmware identity: promote physically proven Stage 6C image.
p, s = rw("include/firmware_identity.h")
if '#define PROJ_FW_VERSION "0.1.17"' not in s or '#define PROJ_FW_BUILD 18' not in s:
    raise SystemExit("unexpected firmware identity baseline")
s = s.replace('#define PROJ_FW_VERSION "0.1.17"', '#define PROJ_FW_VERSION "0.1.20"', 1)
s = s.replace('#define PROJ_FW_BUILD 18', '#define PROJ_FW_BUILD 21', 1)
p.write_text(s)

# Advance repeatable OTA profiles for Stage 6D/later proofs.
p, s = rw("platformio.ini")
def set_env(text, env, version, build):
    pat = r'(\[env:' + re.escape(env) + r'\]\n)(.*?)(?=\n\[env:|\Z)'
    m = re.search(pat, text, re.S)
    if not m:
        raise SystemExit(f"missing env {env}")
    block = m.group(2)
    block, n1 = re.subn(r'-DPROJ_FW_VERSION=\\"[^\n]+?\\"', f'-DPROJ_FW_VERSION=\\"{version}\\"', block, count=1)
    block, n2 = re.subn(r'-DPROJ_FW_BUILD=\d+', f'-DPROJ_FW_BUILD={build}', block, count=1)
    if n1 != 1 or n2 != 1:
        raise SystemExit(f"missing version/build in {env}")
    return text[:m.start(2)] + block + text[m.end(2):]

s = set_env(s, "nodemcu-32s-signed-update-test", "0.1.21", 22)
s = set_env(s, "nodemcu-32s-remote-update-test", "0.1.21-remote-test", 22)
s = set_env(s, "nodemcu-32s-remote-target-test", "0.1.22", 23)
p.write_text(s)

# Roadmap: Stage 6C done, Stage 6D next.
p, s = rw("docs/ROADMAP.md")
s = s.replace("## Stage 6 — Core modular runtime [in progress]", "## Stage 6 — Core modular runtime [in progress — Stage 6C validated, Stage 6D next]", 1)
s = s.replace("- [ ] physical proof of Supervisor `RUNNING -> DEGRADED -> RUNNING` through a controlled real MQTT transport interruption;", "- [x] physical proof of Supervisor `RUNNING -> DEGRADED -> RUNNING` through a controlled real MQTT transport interruption;", 1)
s = s.replace("- [ ] migrate additional periodic/retry work to TaskScheduler where it improves consistency (MQTT reconnect, telemetry, future sensors/actuators).", "- [ ] **Stage 6D** — migrate additional periodic/retry work to TaskScheduler where it improves consistency, starting with MQTT reconnect and telemetry without changing network behavior.", 1)
rule = "Rule: drivers know hardware; components know behavior; services know communication; supervisor knows only state/health."
if "Stage 6C is physically validated" not in s:
    s = s.replace(rule, rule + "\n\nStage 6C is physically validated on `0.1.20/build 21`: a real MQTT interruption kept Wi-Fi/HTTP and the application FSM online, moved `connectivity` to `WIFI_ONLY/DEGRADED` and Supervisor to `DEGRADED`, then recovered both to `ONLINE/OK` and `RUNNING/OK`. EventBus dropped count remained zero.", 1)
p.write_text(s)

# Runtime physical evidence.
p, s = rw("docs/runtime-test-log.md")
if "### Stage 6C physical result — PASS" not in s:
    s += """

### Stage 6C physical result — PASS

- Signed lab image `0.1.19-remote-test/build 20` installed on `app0` and completed native `PENDING_VERIFY -> VALID`.
- Before fault injection, `/api/supervisor` reported `RUNNING/OK` and `connectivity` reported `ONLINE/OK`.
- A real MQTT disconnect was triggered while Wi-Fi and HTTP remained available; reconnect was suppressed for 8 s only in the test-gated image.
- During the interruption, `connectivity` became `WIFI_ONLY/DEGRADED` with `fault_code=mqtt_disconnected`, while the application remained `ONLINE`; Supervisor became `DEGRADED/DEGRADED`.
- After MQTT reconnect, `connectivity` returned to `ONLINE/OK` and Supervisor returned to `RUNNING/OK`.
- EventBus remained `dropped=0` throughout the proof.
- Clean target `0.1.20/build 21` installed on `app1`, completed `PENDING_VERIFY -> VALID`, returned ONLINE with Wi-Fi + MQTT/TLS, and the lab-only disconnect endpoint returned HTTP 404.
- `0.1.20/build 21` is the promoted canonical baseline.
- The proof wrapper issue was labelled failed after the script had already completed, but the captured assertions ended `STAGE6C_PHYSICAL_PROOF_OK`; closure is based on the physical assertions and final clean-device state.

**Stage 6C: VALIDATED. Stage 6D is next.**
"""
p.write_text(s)

# Documentation index/current runtime.
p, s = rw("docs/README.md")
s = s.replace("- [ ] add Supervisor FSM over the common component health model", "- [x] add Supervisor FSM over the common component health model and physically prove `RUNNING -> DEGRADED -> RUNNING`", 1)
new_runtime = """## Current runtime state

Validated directly on the physical device on 2026-09-05 after Stage 6C closure:

- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`
- hardware model: `proj-esp32-35`, revision `1`
- firmware: `0.1.20`, build `21`, channel `dev`
- running OTA partition: `app1`
- boot partition: `app1`
- next update partition: `app0`
- native image state: `VALID`
- application FSM/system: `ONLINE`
- Wi-Fi: connected
- MQTT: connected over TLS
- `connectivity`: `ONLINE/OK`
- Supervisor: `RUNNING/OK`
- EventBus: `pending=0`, `dropped=0`
- remote OTA policy: HTTPS-only
- lab-only MQTT disconnect endpoint: absent from the clean image

Stage 6A established cooperative TaskScheduler timing. Stage 6B established the component registry, shared health metadata and EventBus. Stage 6C physically proves aggregate Supervisor degradation/recovery. **Stage 6D is next: move MQTT reconnect and telemetry cadence from hand-written `millis()` timing into TaskScheduler without changing existing transport semantics.**
"""
s = section(s, "## Current runtime state", "## OTA partition layout", new_runtime)
p.write_text(s)

# Bootstrap current source of truth and next action.
p, s = rw("docs/BOOTSTRAP.md")
new_base = """## Current firmware baseline — verified 2026-09-05

Current physical device state after Stage 6C Supervisor FSM closure:

- model: `proj-esp32-35`
- hardware revision: `1`
- firmware: `0.1.20`
- build: `21`
- channel: `dev`
- running partition: `app1`
- boot partition: `app1`
- next update partition: `app0`
- native OTA image state: `VALID`
- application FSM/system: `ONLINE`
- Wi-Fi: connected
- MQTT/TLS: connected
- `connectivity`: `ONLINE/OK`
- Supervisor: `RUNNING/OK`
- EventBus dropped count: `0`
- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`

TaskScheduler owns timing/eligibility; FSMs own state/behavior; components own subsystem interpretation; EventBus owns transition delivery; Supervisor aggregates only registry health. Stage 6C proved a real MQTT loss can degrade connectivity/Supervisor without taking local application control offline, then recover automatically. The clean `0.1.20/build 21` image removed the test endpoint and remained `VALID`.

Normal build remains within the 1728 KiB OTA slot with roughly 17% static RAM and 69% flash usage.
"""
s = section(s, "## Current firmware baseline — verified 2026-09-05", "## Flash layout — validated", new_base)
new_next = """## Immediate next steps

1. **Stage 6D:** migrate MQTT reconnect timing to TaskScheduler with explicit retry/backoff eligibility while preserving current connection behavior and local autonomy.
2. Migrate periodic MQTT telemetry heartbeat timing to TaskScheduler and prove no regression in broker round-trip/status payloads.
3. Keep network loss as `DEGRADED`, never as a prerequisite for local control.
4. Replace development `setInsecure()` with CA validation for MQTT and remote HTTPS.
5. Add MQTT LWT/retained offline state and reconnect backoff/jitter after the scheduler migration is stable.
6. Continue toward ConfigurationStore/RuleEngine/local Scheduler, then DS3231/TFT/touch/microSD.
"""
s = section(s, "## Immediate next steps", "## Source-of-truth invariant", new_next)
idx = s.find("## Stage 6C implementation checkpoint")
if idx >= 0:
    s = s[:idx].rstrip() + """

## Stage 6C closure

Stage 6C is validated. The physical baseline is `0.1.20/build 21` on `app1`, native image `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, `Supervisor=RUNNING/OK`, MQTT/TLS connected and EventBus `dropped=0`. The controlled proof observed `RUNNING -> DEGRADED -> RUNNING` during a real MQTT interruption while Wi-Fi/HTTP remained available. Proceed with Stage 6D; do not repeat Stage 6C unless the shared health/Supervisor contract changes.
"""
p.write_text(s)

# Architecture closure.
p, s = rw("docs/architecture.md")
if "### Stage 6C physical proof and closure" not in s:
    s += """

### Stage 6C physical proof and closure

Stage 6C is physically validated. A real MQTT disconnect with Wi-Fi/HTTP preserved caused `connectivity=ONLINE/OK -> WIFI_ONLY/DEGRADED` (`mqtt_disconnected`) and Supervisor `RUNNING/OK -> DEGRADED`. After reconnect both recovered to `ONLINE/OK` and `RUNNING/OK`; EventBus dropped count stayed zero. A clean `0.1.20/build 21` image was then installed on `app1`, reached `VALID`, and did not expose the test-only disconnect endpoint.

This validates the ownership boundary: Supervisor observes aggregate health but does not own transport recovery or local functional control. Stage 6D may migrate MQTT reconnect and telemetry timing to TaskScheduler without changing this contract.
"""
p.write_text(s)

# Root README concise baseline.
p, s = rw("README.md")
needle = "## Validated baseline — 2026-09-05\n"
if "Stage 6C physical baseline" not in s:
    s = s.replace(needle, needle + "\n**Stage 6C physical baseline:** `0.1.20/build 21`, `app1`, native OTA `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, `Supervisor=RUNNING/OK`, Wi-Fi + MQTT/TLS connected, EventBus `dropped=0`. Stage 6D is next.\n", 1)
p.write_text(s)

# Align repeatable scheduler proof with new baseline/test builds.
p, s = rw("scripts/smoke_update_scheduler.sh")
for old, new in [
    ('"version":"0.1.17"', '"version":"0.1.20"'),
    ('"build":18', '"build":21'),
    ('--version 0.1.18-remote-test --build 19', '--version 0.1.21-remote-test --build 22'),
    ('--version 0.1.19 --build 20', '--version 0.1.22 --build 23'),
    ("wait_for_transition '0.1.18-remote-test' 19 app1", "wait_for_transition '0.1.21-remote-test' 22 app0"),
    ("wait_for_online '0.1.18-remote-test' 19", "wait_for_online '0.1.21-remote-test' 22"),
    ('"candidate_build":20', '"candidate_build":23'),
    ("wait_for_transition '0.1.19' 20 app0", "wait_for_transition '0.1.22' 23 app1"),
    ('"version":"0.1.19"', '"version":"0.1.22"'),
    ('"build":20', '"build":23'),
]:
    s = s.replace(old, new)
p.write_text(s)

# Remove Stage 6C-only proof runner from maintained tree.
Path("scripts/run_stage6c_physical_proof.sh").unlink(missing_ok=True)
print("STAGE6C_CLOSURE_PATCH_OK")
