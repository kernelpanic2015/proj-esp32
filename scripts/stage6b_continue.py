#!/usr/bin/env python3
from pathlib import Path
import sys


def replace_if_present(path: str, old: str, new: str):
    p = Path(path)
    text = p.read_text()
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1))


def ensure_preproof_docs():
    replace_if_present(
        "docs/README.md",
        "- [x] TaskScheduler + arduino-fsm cooperative runtime foundation; automatic scheduler migration proven on hardware\n- [x] Component / ComponentHealth / ComponentRegistry / bounded EventBus foundations compile\n- [ ] wire real components into ComponentRegistry and add Supervisor FSM\n",
        "- [x] TaskScheduler + arduino-fsm cooperative runtime foundation; automatic scheduler migration proven on hardware\n- [x] first real ComponentRegistry entry (`connectivity`) + `/api/components` shared health API implemented\n- [x] standardized ComponentHealth metadata + bounded EventBus transition routing\n- [ ] add Supervisor FSM over the common component health model\n",
    )

    replace_if_present(
        "docs/BOOTSTRAP.md",
        "1. wire the first real service components into `ComponentRegistry` and expose their common health metadata;\n2. add the Stage 6 `Supervisor` FSM and schedule it cooperatively with TaskScheduler;\n3. schedule bounded `EventBus.process()` and begin routing state-change events through it;\n4. gradually migrate eligible periodic/retry work (MQTT reconnect/telemetry and later sensors) from hand-written timing to TaskScheduler + FSM;\n5. replace development `setInsecure()` with CA validation for MQTT and remote HTTPS;\n6. harden MQTT with LWT plus reconnect backoff/jitter;\n7. continue toward ConfigurationStore/RuleEngine/local Scheduler and later DS3231/TFT/touch/microSD.\n",
        "1. add the Stage 6 `Supervisor` FSM over the validated `ComponentRegistry` / `ComponentHealth` / `EventBus` foundation;\n2. migrate MQTT reconnect/telemetry timing to TaskScheduler incrementally without changing network behavior;\n3. add more real components only when ownership boundaries are clear;\n4. replace development `setInsecure()` with CA validation for MQTT and remote HTTPS;\n5. harden MQTT with LWT plus reconnect backoff/jitter;\n6. continue toward ConfigurationStore/RuleEngine/local Scheduler and later DS3231/TFT/touch/microSD.\n",
    )

    required = [
        "include/components/connectivity_component.h",
        "src/components/connectivity_component.cpp",
        "include/core/runtime_events.h",
        "docs/runtime-test-log.md",
    ]
    for name in required:
        if not Path(name).exists():
            raise SystemExit(f"missing Stage 6B file: {name}")

    main = Path("src/main.cpp").read_text()
    for token in ["ConnectivityComponent", "/api/components", "runtimeEvents.process(8)"]:
        if token not in main:
            raise SystemExit(f"Stage 6B main.cpp token missing: {token}")

    print("STAGE6B_PREPROOF_DOCS_OK")


def update_platformio():
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
    for line in lines:
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
        if current in targets:
            version, build = targets[current]
            if "-DPROJ_FW_VERSION=" in line:
                line = f'    -DPROJ_FW_VERSION=\\"{version}\\"'
                seen.add((current, "version"))
            elif "-DPROJ_FW_BUILD=" in line:
                line = f"    -DPROJ_FW_BUILD={build}"
                seen.add((current, "build"))
        out.append(line)
    for env in targets:
        if (env, "version") not in seen or (env, "build") not in seen:
            raise SystemExit(f"failed to update {env}")
    p.write_text("\n".join(out) + "\n")


def update_smoke_scheduler():
    p = Path("scripts/smoke_update_scheduler.sh")
    s = p.read_text()
    replacements = [
        ("grep -q '\"version\":\"0.1.16\"' <<<\"$V\"", "grep -q '\"version\":\"0.1.17\"' <<<\"$V\""),
        ("grep -q '\"build\":17' <<<\"$V\"", "grep -q '\"build\":18' <<<\"$V\""),
        ("--version 0.1.17-remote-test --build 18", "--version 0.1.18-remote-test --build 19"),
        ("--version 0.1.18 --build 19", "--version 0.1.19 --build 20"),
        ("wait_for_transition '0.1.17-remote-test' 18 app0", "wait_for_transition '0.1.18-remote-test' 19 app0"),
        ("wait_for_online '0.1.17-remote-test' 18", "wait_for_online '0.1.18-remote-test' 19"),
        ("'\"candidate_build\":19'", "'\"candidate_build\":20'"),
        ("wait_for_transition '0.1.18' 19 app1", "wait_for_transition '0.1.19' 20 app1"),
        ("grep -q '\"version\":\"0.1.18\"' <<<\"$S\"", "grep -q '\"version\":\"0.1.19\"' <<<\"$S\""),
        ("grep -q '\"build\":19' <<<\"$S\"", "grep -q '\"build\":20' <<<\"$S\""),
    ]
    for old, new in replacements:
        if new in s:
            continue
        if old not in s:
            raise SystemExit(f"scheduler smoke pattern missing: {old}")
        s = s.replace(old, new, 1)
    p.write_text(s)


def promote():
    p = Path("include/firmware_identity.h")
    s = p.read_text()
    if '#define PROJ_FW_VERSION "0.1.17"' not in s:
        if '#define PROJ_FW_VERSION "0.1.16"' not in s:
            raise SystemExit("unexpected firmware baseline version")
        s = s.replace('#define PROJ_FW_VERSION "0.1.16"', '#define PROJ_FW_VERSION "0.1.17"', 1)
    if '#define PROJ_FW_BUILD 18' not in s:
        if '#define PROJ_FW_BUILD 17' not in s:
            raise SystemExit("unexpected firmware baseline build")
        s = s.replace('#define PROJ_FW_BUILD 17', '#define PROJ_FW_BUILD 18', 1)
    p.write_text(s)

    update_platformio()
    update_smoke_scheduler()

    p = Path("docs/README.md")
    s = p.read_text()
    s = s.replace("after the Stage 6A TaskScheduler migration proof", "after the Stage 6B ComponentRegistry physical proof")
    s = s.replace("- firmware: `0.1.16`, build `17`, channel `dev`", "- firmware: `0.1.17`, build `18`, channel `dev`")
    s = s.replace("Final `0.1.16/build 17` remained ONLINE and `VALID`.", "Final `0.1.17/build 18` remained ONLINE and `VALID`.")
    s = s.replace("Stage 6 core foundations now compile: `Component`, `ComponentHealth`, `ComponentRegistry`, and a bounded `EventBus`. Real components and the Supervisor FSM are the next incremental step.", "Stage 6B now has one real registered component: `connectivity`. Its state/health is sampled by TaskScheduler, transitions go through the bounded EventBus, and the shared registry is exposed through `/api/components`, `/api/status`, and MQTT telemetry. The Supervisor FSM is the next incremental step.")
    p.write_text(s)

    p = Path("docs/BOOTSTRAP.md")
    s = p.read_text()
    s = s.replace("Current physical device state after the Stage 6A TaskScheduler migration proof:", "Current physical device state after the Stage 6B ComponentRegistry physical proof:")
    s = s.replace("- firmware: `0.1.16`\n- build: `17`", "- firmware: `0.1.17`\n- build: `18`")
    s = s.replace("Final `0.1.16/build 17` remained ONLINE and `VALID`.", "Final `0.1.17/build 18` remained ONLINE and `VALID`.")
    s = s.replace("Stage 6 foundations under `include/core` / `src/core` now include `Component`, `ComponentHealth`, `ComponentRegistry`, and a bounded `EventBus`; they compile but real services/components are not yet registered.", "Stage 6 foundations now include a physically validated `connectivity` component registered in `ComponentRegistry`. TaskScheduler samples it every 2 s; network loss degrades health instead of stopping local control; state/health transitions use EventBus; `/api/components` and `/api/status` expose the common model.")
    p.write_text(s)

    p = Path("docs/runtime-test-log.md")
    s = p.read_text()
    marker = "### Stage 6B physical result — PASS"
    if marker not in s:
        s += """\n### Stage 6B physical result — PASS\n\n- Signed candidate `0.1.17/build 18` installed into `app0`.\n- Native OTA state observed `PENDING_VERIFY -> VALID`.\n- Device returned `ONLINE` with Wi-Fi and MQTT/TLS connected.\n- `/api/components` reported one `connectivity` component in state `ONLINE`, health `OK`.\n- The same registry is embedded in `/api/status` / MQTT telemetry.\n- EventBus `dropped=0` during the proof.\n- `0.1.17/build 18` is promoted as the normal baseline.\n"""
    p.write_text(s)

    p = Path("docs/architecture.md")
    s = p.read_text()
    marker = "### Stage 6B physical proof"
    if marker not in s:
        s += """\n\n### Stage 6B physical proof\n\nA signed `0.1.17/build 18` image was installed on the physical ESP32 and completed `PENDING_VERIFY -> VALID`. After network settlement, `/api/components` exposed the registered `connectivity` component as `ONLINE` / `OK`, the registry appeared in `/api/status`, MQTT/TLS was connected, and the EventBus reported zero dropped events. This establishes the first real end-to-end component using TaskScheduler cadence + component-owned state/health + EventBus transitions + shared API/telemetry serialization.\n"""
    p.write_text(s)

    print("STAGE6B_PROMOTION_FILES_OK")


if len(sys.argv) == 1 or sys.argv[1] == "preproof":
    ensure_preproof_docs()
elif sys.argv[1] == "promote":
    promote()
else:
    raise SystemExit("usage: stage6b_continue.py [preproof|promote]")
