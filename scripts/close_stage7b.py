from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def write(rel, text):
    (ROOT / rel).write_text(text, encoding="utf-8")


def replace_once(rel, old, new):
    text = read(rel)
    if old not in text:
        raise SystemExit(f"missing anchor in {rel}: {old[:120]!r}")
    write(rel, text.replace(old, new, 1))


# Promote the already-proven clean Stage 7B target to the default identity.
replace_once("include/firmware_identity.h", '#define PROJ_FW_VERSION "0.1.29"', '#define PROJ_FW_VERSION "0.1.31"')
replace_once("include/firmware_identity.h", '#define PROJ_FW_BUILD 30', '#define PROJ_FW_BUILD 32')

# Preserve monotonic OTA ordering for the next Stage 7C proof.
replace_once("platformio.ini", '-DPROJ_FW_VERSION=\\"0.1.30\\"\n    -DPROJ_FW_BUILD=31', '-DPROJ_FW_VERSION=\\"0.1.32\\"\n    -DPROJ_FW_BUILD=33')
replace_once("platformio.ini", '-DPROJ_FW_VERSION=\\"0.1.30-remote-test\\"\n    -DPROJ_FW_BUILD=31', '-DPROJ_FW_VERSION=\\"0.1.32-remote-test\\"\n    -DPROJ_FW_BUILD=33')
replace_once("platformio.ini", '-DPROJ_FW_VERSION=\\"0.1.31\\"\n    -DPROJ_FW_BUILD=32', '-DPROJ_FW_VERSION=\\"0.1.33\\"\n    -DPROJ_FW_BUILD=34')

# ROADMAP: close 7B and point the active work at 7C.
replace_once(
    "docs/ROADMAP.md",
    '## Stage 7 — Persistent configuration and local rule engine [in progress — Stage 7B]',
    '## Stage 7 — Persistent configuration and local rule engine [in progress — Stage 7C]'
)
replace_once(
    "docs/ROADMAP.md",
    '- [~] **Stage 7B** — minimal hysteresis `RuleEngine` + virtual input/actuator model; manual evaluation proof pending;',
    '- [x] **Stage 7B** — minimal hysteresis `RuleEngine` + virtual input/actuator model; semantic and physical behavior validated;'
)
replace_once(
    "docs/ROADMAP.md",
    '**Stage 7B next:** introduce the smallest useful local rule model with virtual input/output components. Do not access GPIO from RuleEngine.\n',
    '''**Stage 7B: VALIDATED on hardware.** A controlled `0.1.30-remote-test/build 31` image proved semantic rejection of invalid hysteresis, then exercised a `16/18 C` virtual rule through `20 -> 15 -> 17 -> 19 -> 17`: OFF/HOLD, ON, HOLD-ON, OFF, HOLD-OFF. Disabling the rule prevented actuation even at an input of 10. Supervisor stayed `RUNNING/OK` and EventBus stayed `dropped=0`. Clean `0.1.31/build 32` returned to HTTPS-only operation, retained ConfigurationStore revision 3, exposed only the read-only `/api/rules/status`, and removed all RuleEngine lab endpoints.\n\n**Stage 7C next:** connect this same rule path to TaskScheduler + EventBus. The evaluation work task must remain disabled when there is no active rule, input events may force an iteration, and FSM/component ownership remains separate from scheduling.\n'''
)

# Configuration docs: record exact physical rule behavior and boundary.
config = read("docs/configuration.md")
if "## Stage 7B physical validation" not in config:
    config += '''\n\n## Stage 7B physical validation\n\nStage 7B was physically proven on the ESP32 with virtual I/O and the signed A/B path. The lab image was `0.1.30-remote-test/build 31` on `app1`, reached `PENDING_VERIFY -> VALID`, and exposed the test-gated virtual rule endpoints.\n\nAcceptance sequence:\n\n```text\ninvalid: on_below=18, off_above=16 -> HTTP 400 rule_hysteresis_invalid\nvalid:   on_below=16, off_above=18\n\ninput 20 -> actuator OFF, HOLD\ninput 15 -> actuator ON,  TURN_ON\ninput 17 -> actuator ON,  HOLD\ninput 19 -> actuator OFF, TURN_OFF\ninput 17 -> actuator OFF, HOLD\n\ndisable rule\ninput 10 -> actuator remains OFF, decision DISABLED\n```\n\nThe enabled sequence produced exactly five evaluations. A disabled rule did not increment that count or change the actuator. The RuleEngine only returned desired state; `VirtualActuatorComponent` owned application of that state and no GPIO was touched.\n\nDuring the lab proof the component registry contained `connectivity`, `virtual.temperature`, and `virtual.heater`; Supervisor remained `RUNNING/OK` and EventBus remained `dropped=0`. The clean `0.1.31/build 32` target then installed on `app0`, reached `VALID`, returned to HTTPS-only remote-update policy, retained ConfigurationStore revision 3, restored the normal registry to only `connectivity`, and returned HTTP 404 for `/api/test/rules/status`. The standard read-only `/api/rules/status` remained available with an unconfigured engine.\n\nStage 7B intentionally stops at explicit/manual evaluation. Stage 7C adds TaskScheduler + EventBus runtime wiring; Stage 7D later binds persisted rule semantics to ConfigurationStore revisions.\n'''
    write("docs/configuration.md", config)

# Runtime test log including the false wrapper label diagnosis.
runtime = read("docs/runtime-test-log.md")
if "## 2026-09-05 — Stage 7B minimal RuleEngine" not in runtime:
    runtime += '''\n\n## 2026-09-05 — Stage 7B minimal RuleEngine\n\n- Added a hardware-independent hysteresis `RuleEngine` plus `VirtualInputComponent` and `VirtualActuatorComponent`.\n- Invalid hysteresis (`on_below >= off_above`) was rejected before activation.\n- Physical sequence `20 -> 15 -> 17 -> 19 -> 17` with thresholds `16/18` proved OFF/HOLD -> ON -> HOLD-ON -> OFF -> HOLD-OFF.\n- Disabling the rule and applying input `10` produced decision `DISABLED` and left the virtual actuator OFF; the enabled evaluation count remained 5.\n- RuleEngine never accesses GPIO; it returns desired state and the actuator component owns application.\n- Lab image `0.1.30-remote-test/build 31` reached `PENDING_VERIFY -> VALID`; Supervisor remained `RUNNING/OK`, EventBus remained `dropped=0`.\n- Clean target `0.1.31/build 32` reached `PENDING_VERIFY -> VALID` on `app0`, Wi-Fi + MQTT/TLS were connected, ConfigurationStore remained revision 3, the normal registry returned to one `connectivity` component, HTTPS-only update policy was restored, and the lab RuleEngine endpoint returned HTTP 404.\n- Aurora issue #731 was labelled failed even though the proof file ended `STAGE7B_PHYSICAL_PROOF_OK`. Follow-up issue #732 inspected the wrapper and showed `RC=0`; closure is based on the explicit physical assertions, proof marker, and live clean-device state rather than the incorrect wrapper label.\n\n**Stage 7B: VALIDATED. Stage 7C is next.**\n'''
    write("docs/runtime-test-log.md", runtime)

# BOOTSTRAP: update the canonical handoff baseline and next stage.
replace_once("docs/BOOTSTRAP.md", 'Current physical device state after Stage 7A transactional configuration closure:', 'Current physical device state after Stage 7B minimal RuleEngine closure:')
replace_once("docs/BOOTSTRAP.md", '- firmware: `0.1.29`\n- build: `30`', '- firmware: `0.1.31`\n- build: `32`')
replace_once(
    "docs/BOOTSTRAP.md",
    'Stage 7B should start with virtual input/output and minimal rule semantics; do not connect RuleEngine directly to GPIO.\n',
    '''## Stage 7B RuleEngine — validated\n\n- one minimal in-memory hysteresis rule model is implemented;\n- invalid hysteresis is rejected semantically;\n- virtual temperature input and virtual heater actuator proved ON/OFF + deadband behavior;\n- disabled rule does not actuate;\n- RuleEngine produces desired state only and never touches GPIO;\n- clean firmware exposes `GET /api/rules/status`;\n- controlled write/evaluation endpoints exist only in the lab build and are absent from the clean image;\n- clean physical baseline is `0.1.31/build 32`, `app0/VALID`;\n- ConfigurationStore remains revision 3; persisted rule binding is intentionally deferred to Stage 7D.\n\n**Stage 7C next:** TaskScheduler + EventBus runtime evaluation. The evaluation work task must be disabled when no rule is active, input events may force an evaluation, and rule/actuator state ownership remains in the engine/component FSM layer.\n'''
)

# docs index/current state.
replace_once("docs/README.md", '- [~] Stage 7B minimal RuleEngine + virtual I/O implementation; physical proof pending', '- [x] Stage 7B minimal RuleEngine + virtual I/O semantics physically validated\n- [~] Stage 7C TaskScheduler/EventBus rule evaluation runtime next')
replace_once("docs/README.md", 'Validated directly on the physical device on 2026-09-05 after Stage 7A closure:', 'Validated directly on the physical device on 2026-09-05 after Stage 7B closure:')
replace_once("docs/README.md", '- firmware: `0.1.29`, build `30`, channel `dev`', '- firmware: `0.1.31`, build `32`, channel `dev`')
replace_once(
    "docs/README.md",
    'Stage 6 core runtime is validated and Stage 7A transactional configuration is physically validated. Configuration revision 3 survived reboot, rollback and signed OTA. Intentional software restart now clears the DRD marker before reboot so it cannot masquerade as a human double-reset request. **Stage 7B is in progress:** the minimal hardware-independent hysteresis RuleEngine and controlled virtual input/output path are implemented for physical proof.\n',
    'Stage 6 core runtime and Stage 7A transactional configuration are validated. **Stage 7B is now physically validated:** the hardware-independent hysteresis RuleEngine correctly drove virtual desired state across ON/OFF thresholds and deadband, rejected invalid semantics, and did not actuate while disabled. The clean image exposes only read-only rule status. **Stage 7C is next:** TaskScheduler/EventBus-driven evaluation with the work task disabled when no rule is active.\n'
)

# Architecture physical closure.
arch = read("docs/architecture.md")
if "### Stage 7B physical closure" not in arch:
    arch += '''\n\n### Stage 7B physical closure\n\nThe virtual path was physically exercised on the device with thresholds 16/18. It preserved state inside the deadband, turned ON below the lower threshold, turned OFF above the upper threshold, rejected inverted thresholds, and ignored actuation when the rule was disabled. The controlled lab image registered virtual components only for the proof; the clean `0.1.31/build 32` image returned to the production registry with only `connectivity` and removed lab endpoints.\n\nThis validates the ownership boundary before scheduling is introduced: **RuleEngine decides desired functional state; Component/FSM owns behavior; Driver owns hardware.** Stage 7C now adds only the timing/event layer: TaskScheduler determines when evaluation runs and EventBus may force a pending evaluation. No Stage 7C task should stay enabled when there is no active rule.\n'''
    write("docs/architecture.md", arch)

# Top-level README baseline/current stage.
replace_once(
    "README.md",
    '**Current physical baseline:** `0.1.29/build 30`, `app0`, native OTA `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, Wi-Fi + MQTT/TLS connected and EventBus `dropped=0`. Stage 6 cooperative runtime remains validated.',
    '**Current physical baseline:** `0.1.31/build 32`, `app0`, native OTA `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, Wi-Fi + MQTT/TLS connected and EventBus `dropped=0`. ConfigurationStore remains revision 3.'
)
replace_once(
    "README.md",
    '**Stage 7A is validated:** `ConfigurationStore` provides versioned dual-slot NVS transactions with verified inactive-slot writes, monotonic revisions, boot fallback and rollback. Apply/reject/reboot/rollback/OTA persistence was physically proven. Intentional software reboots clear the DRD marker first. **Stage 7B is in progress:** a minimal hardware-independent hysteresis RuleEngine and controlled virtual input/output path are implemented for proof; RuleEngine returns desired state and never accesses GPIO.',
    '**Stage 7A is validated:** `ConfigurationStore` provides versioned dual-slot NVS transactions with rollback. **Stage 7B is validated:** the minimal hardware-independent hysteresis RuleEngine and virtual input/output path were physically proven, including deadband and disabled-rule behavior; RuleEngine returns desired state and never accesses GPIO. **Stage 7C is next:** TaskScheduler/EventBus-driven evaluation with work disabled when no active rule exists.'
)

print("STAGE7B_CLOSE_PATCHED")
