#!/usr/bin/env python3
from pathlib import Path


def set_default_identity():
    p = Path("include/firmware_identity.h")
    s = p.read_text()
    if '#define PROJ_FW_VERSION "0.1.16"' in s:
        s = s.replace('#define PROJ_FW_VERSION "0.1.16"', '#define PROJ_FW_VERSION "0.1.17"', 1)
    if '#define PROJ_FW_BUILD 17' in s:
        s = s.replace('#define PROJ_FW_BUILD 17', '#define PROJ_FW_BUILD 18', 1)
    if '#define PROJ_FW_VERSION "0.1.17"' not in s or '#define PROJ_FW_BUILD 18' not in s:
        raise SystemExit("unexpected default firmware identity")
    p.write_text(s)


def advance_profiles():
    p = Path("platformio.ini")
    lines = p.read_text().splitlines()
    targets = {
        "env:nodemcu-32s-signed-update-test": ("0.1.18", 19),
        "env:nodemcu-32s-remote-update-test": ("0.1.18-remote-test", 19),
        "env:nodemcu-32s-remote-target-test": ("0.1.19", 20),
    }
    current = None
    seen = set()
    out = []
    escaped_quote = chr(92) + chr(34)
    for line in lines:
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
        if current in targets:
            version, build = targets[current]
            if "-DPROJ_FW_VERSION=" in line:
                line = f"    -DPROJ_FW_VERSION={escaped_quote}{version}{escaped_quote}"
                seen.add((current, "version"))
            elif "-DPROJ_FW_BUILD=" in line:
                line = f"    -DPROJ_FW_BUILD={build}"
                seen.add((current, "build"))
        out.append(line)
    for env in targets:
        if (env, "version") not in seen or (env, "build") not in seen:
            raise SystemExit(f"profile not updated: {env}")
    p.write_text("\n".join(out) + "\n")


def advance_scheduler_smoke():
    p = Path("scripts/smoke_update_scheduler.sh")
    s = p.read_text()
    replacements = [
        ("0.1.16", "0.1.17", 1),
        ("build\":17", "build\":18", 1),
        ("0.1.17-remote-test", "0.1.18-remote-test", 3),
        ("--build 18", "--build 19", 1),
        (" 18 app0", " 19 app1", 1),
        ("' 18", "' 19", 0),
    ]
    # Explicit targeted replacements are safer for the remaining target values.
    pairs = [
        ("--version 0.1.17-remote-test --build 18", "--version 0.1.18-remote-test --build 19"),
        ("--version 0.1.18 --build 19", "--version 0.1.19 --build 20"),
        ("wait_for_transition '0.1.17-remote-test' 18 app0", "wait_for_transition '0.1.18-remote-test' 19 app1"),
        ("wait_for_online '0.1.17-remote-test' 18", "wait_for_online '0.1.18-remote-test' 19"),
        ("\"candidate_build\":19", "\"candidate_build\":20"),
        ("wait_for_transition '0.1.18' 19 app1", "wait_for_transition '0.1.19' 20 app0"),
        ("\"version\":\"0.1.18\"", "\"version\":\"0.1.19\""),
        ("\"build\":19", "\"build\":20"),
    ]
    # Baseline first, but only its first version/build assertions.
    baseline_version = "grep -q '\"version\":\"0.1.16\"' <<<\"$V\""
    baseline_build = "grep -q '\"build\":17' <<<\"$V\""
    if baseline_version in s:
        s = s.replace(baseline_version, "grep -q '\"version\":\"0.1.17\"' <<<\"$V\"", 1)
    if baseline_build in s:
        s = s.replace(baseline_build, "grep -q '\"build\":18' <<<\"$V\"", 1)
    for old, new in pairs:
        if old in s:
            s = s.replace(old, new, 1)
        elif new not in s:
            raise SystemExit(f"scheduler smoke token missing: {old}")
    p.write_text(s)


def update_docs():
    p = Path("docs/README.md")
    s = p.read_text()
    s = s.replace("after the Stage 6A TaskScheduler migration proof", "after the Stage 6B ComponentRegistry physical proof")
    s = s.replace("- firmware: `0.1.16`, build `17`, channel `dev`", "- firmware: `0.1.17`, build `18`, channel `dev`")
    s = s.replace("- running OTA partition: `app1`", "- running OTA partition: `app0`")
    s = s.replace("- boot partition: `app1`", "- boot partition: `app0`")
    s = s.replace("- next update partition: `app0`", "- next update partition: `app1`")
    s = s.replace("Final `0.1.16/build 17` remained ONLINE and `VALID`.", "Final `0.1.17/build 18` remained ONLINE and `VALID`.")
    old = "Stage 6 core foundations now compile: `Component`, `ComponentHealth`, `ComponentRegistry`, and a bounded `EventBus`. Real components and the Supervisor FSM are the next incremental step."
    new = "Stage 6B now has one physically validated real component: `connectivity`. TaskScheduler samples it, transitions flow through the bounded EventBus, and the common registry is exposed by `/api/components`, `/api/status`, and existing MQTT telemetry. The Supervisor FSM is the next incremental step."
    s = s.replace(old, new)
    p.write_text(s)

    p = Path("docs/BOOTSTRAP.md")
    s = p.read_text()
    s = s.replace("Current physical device state after the Stage 6A TaskScheduler migration proof:", "Current physical device state after the Stage 6B ComponentRegistry physical proof:")
    s = s.replace("- firmware: `0.1.16`\n- build: `17`", "- firmware: `0.1.17`\n- build: `18`")
    s = s.replace("- running partition: `app1`", "- running partition: `app0`")
    s = s.replace("- boot partition: `app1`", "- boot partition: `app0`")
    s = s.replace("- next update partition: `app0`", "- next update partition: `app1`")
    s = s.replace("Final `0.1.16/build 17` remained ONLINE and `VALID`.", "Final `0.1.17/build 18` remained ONLINE and `VALID`.")
    old = "Stage 6 foundations under `include/core` / `src/core` now include `Component`, `ComponentHealth`, `ComponentRegistry`, and a bounded `EventBus`; they compile but real services/components are not yet registered."
    new = "Stage 6B physically validates the first real registered component, `connectivity`: TaskScheduler owns its sampling cadence, the component owns state/health, transitions use EventBus, and `/api/components` plus `/api/status` expose the common model."
    s = s.replace(old, new)
    p.write_text(s)

    p = Path("docs/runtime-test-log.md")
    s = p.read_text()
    marker = "### Stage 6B physical result — PASS"
    if marker not in s:
        s += """
### Stage 6B physical result — PASS

- Signed candidate `0.1.17/build 18` installed into `app0`.
- Native OTA state observed `PENDING_VERIFY -> VALID`.
- Device returned `ONLINE` with Wi-Fi and MQTT/TLS connected.
- `/api/components` reported one `connectivity` component in state `ONLINE`, health `OK`.
- The same registry is embedded in `/api/status` and therefore the existing MQTT status/telemetry model.
- EventBus reported `pending=0`, `dropped=0`.
- Normal build after integration uses about 17.0% static RAM and 69.1% of the 1728 KiB OTA slot.
- `0.1.17/build 18` is the promoted default baseline.
"""
    p.write_text(s)

    p = Path("docs/architecture.md")
    s = p.read_text()
    marker = "### Stage 6B physical proof"
    if marker not in s:
        s += """

### Stage 6B physical proof

A signed `0.1.17/build 18` image was installed on the physical ESP32 and completed `PENDING_VERIFY -> VALID` on `app0`. After network settlement, `/api/components` exposed `connectivity` as `ONLINE` / `OK`, `/api/status` embedded the same registry, MQTT/TLS was connected, and EventBus reported zero dropped events. The PubSubClient packet buffer is 2048 bytes to retain telemetry headroom as the common component model grows. This establishes the first real end-to-end component using TaskScheduler cadence + component-owned state/health + EventBus transitions + shared API/MQTT serialization.
"""
    p.write_text(s)


def cleanup_helpers():
    for name in [
        "scripts/stage6b_component_registry.py",
        "scripts/run_stage6b_component_registry.sh",
        "scripts/stage6b_continue.py",
        "scripts/run_stage6b_continue.sh",
        "scripts/finalize_stage6b.py",
    ]:
        p = Path(name)
        if p.exists():
            p.unlink()


set_default_identity()
advance_profiles()
advance_scheduler_smoke()
update_docs()
cleanup_helpers()
print("STAGE6B_FINALIZATION_FILES_OK")
