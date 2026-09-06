from pathlib import Path


def replace_once(path, old, new):
    p = Path(path)
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"missing expected text in {path}: {old[:120]!r}")
    p.write_text(s.replace(old, new, 1))


replace_once(
    "README.md",
    "**Current physical baseline:** `0.1.31/build 32`, `app0`, native OTA `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, Wi-Fi + MQTT/TLS connected and EventBus `dropped=0`. ConfigurationStore remains revision 3.",
    "**Current physical baseline:** `0.1.35/build 36`, `app0`, native OTA `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, Wi-Fi + MQTT/TLS connected and EventBus `dropped=0`. ConfigurationStore remains revision 3; the production RuleRuntime is `DISABLED` with no active rule and Stage 7C lab endpoints are absent."
)
replace_once(
    "README.md",
    "**Stage 7A is validated:** `ConfigurationStore` provides versioned dual-slot NVS transactions with rollback. **Stage 7B is validated:** the minimal hardware-independent hysteresis RuleEngine and virtual input/output path were physically proven, including deadband and disabled-rule behavior; RuleEngine returns desired state and never accesses GPIO. **Stage 7C is next:** TaskScheduler/EventBus-driven evaluation with work disabled when no active rule exists.",
    "**Stage 7A is validated:** `ConfigurationStore` provides versioned dual-slot NVS transactions with rollback. **Stage 7B is validated:** the minimal hardware-independent hysteresis RuleEngine and virtual input/output path were physically proven, including deadband and disabled-rule behavior; RuleEngine returns desired state and never accesses GPIO. **Stage 7C is validated:** `RuleRuntime` now connects EventBus to a one-shot TaskScheduler evaluation task; the task is disabled unless work is meaningful, and a real Wi-Fi/MQTT outage proved the local rule path still executed. **Stage 7D is next:** bind validated persisted rule documents/revisions to the engine/runtime lifecycle."
)

replace_once(
    "docs/README.md",
    "- [~] Stage 7C TaskScheduler/EventBus rule evaluation runtime next",
    "- [x] Stage 7C TaskScheduler/EventBus one-shot rule runtime physically validated, including offline execution"
)
replace_once(
    "docs/README.md",
    "Validated directly on the physical device on 2026-09-05 after Stage 7B closure:",
    "Validated directly on the physical device on 2026-09-05 after Stage 7C closure:"
)
replace_once("docs/README.md", "- firmware: `0.1.31`, build `32`, channel `dev`", "- firmware: `0.1.35`, build `36`, channel `dev`")
replace_once(
    "docs/README.md",
    "- lab-only Wi-Fi/MQTT test endpoints: absent from the clean image",
    "- lab-only Wi-Fi/MQTT/rule-runtime test endpoints: absent from the clean image\n- RuleRuntime: `DISABLED`, no active rule, work task disabled in the clean image"
)
replace_once(
    "docs/README.md",
    "Stage 6 core runtime and Stage 7A transactional configuration are validated. **Stage 7B is now physically validated:** the hardware-independent hysteresis RuleEngine correctly drove virtual desired state across ON/OFF thresholds and deadband, rejected invalid semantics, and did not actuate while disabled. The clean image exposes only read-only rule status. **Stage 7C is next:** TaskScheduler/EventBus-driven evaluation with the work task disabled when no rule is active.",
    "Stage 6 core runtime and Stage 7A transactional configuration are validated. **Stage 7B is physically validated:** the hardware-independent hysteresis RuleEngine correctly drove virtual desired state across ON/OFF thresholds and deadband, rejected invalid semantics, and did not actuate while disabled. **Stage 7C is now physically validated:** an EventBus input schedules exactly one TaskScheduler evaluation, the task disables again after completion, disabled rules reject work without scheduling it, and the rule path was proven to execute while Wi-Fi/MQTT were deliberately unavailable. Clean `0.1.35/build 36` exposes the read-only rule/runtime status only; lab endpoints are absent. **Stage 7D is next:** bind persisted validated rule documents/revisions to RuleEngine/RuleRuntime lifecycle."
)

replace_once(
    "docs/ROADMAP.md",
    "## Stage 7 — Persistent configuration and local rule engine [in progress — Stage 7C]",
    "## Stage 7 — Persistent configuration and local rule engine [in progress — Stage 7D]"
)
replace_once(
    "docs/ROADMAP.md",
    "- [~] **Stage 7C** — TaskScheduler-driven/event-forced evaluation implemented; physical offline-path proof pending;\n- [ ] local `Scheduler` for schedules/delayed actions/settling windows;\n- [ ] dependency/fault policies for actuators.",
    "- [x] **Stage 7C** — TaskScheduler/EventBus-driven one-shot RuleRuntime physically validated, including real offline execution;\n- [ ] **Stage 7D** — bind validated persisted rule documents/revisions to RuleEngine/RuleRuntime lifecycle;\n- [ ] **Stage 7E** — local `Scheduler` for schedules/delayed actions/settling windows;\n- [ ] dependency/fault policies for actuators."
)
replace_once(
    "docs/ROADMAP.md",
    "**Stage 7C next:** connect this same rule path to TaskScheduler + EventBus. The evaluation work task must remain disabled when there is no active rule, input events may force an iteration, and FSM/component ownership remains separate from scheduling.\n\nA configured rule such as `heater ON below 16 C / OFF above 18 C` must continue operating with all external connectivity removed.",
    "**Stage 7C: VALIDATED on hardware.** Controlled `0.1.34-remote-test/build 35` proved the event-driven `RuleRuntime`: an input event scheduled exactly one TaskScheduler evaluation, returned the work task to disabled after completion, preserved hysteresis (`15 -> TURN_ON`, `17 -> HOLD`, `19 -> TURN_OFF`), and rejected new work after the rule was disabled. The decisive proof queued a local temperature event, deliberately removed Wi-Fi/MQTT before the event fired, confirmed HTTP became unavailable, and then observed after reconnection that the local event had still executed and turned the virtual heater ON. EventBus remained `dropped=0`. Clean `0.1.35/build 36` returned on `app0/VALID`, Wi-Fi + MQTT/TLS connected, HTTPS-only remote update restored, ConfigurationStore revision 3 preserved, production registry reduced to `connectivity`, RuleRuntime `DISABLED`, and lab endpoints returned HTTP 404.\n\n**Stage 7D next:** bind validated persisted rule documents and ConfigurationStore revisions to the RuleEngine/RuleRuntime lifecycle without weakening the Stage 7C rule that work tasks stay disabled until work is meaningful."
)

replace_once(
    "docs/configuration.md",
    "Stage 7B evaluation is intentionally explicit/manual. Stage 7C will connect the same\nengine to TaskScheduler + EventBus so the evaluation work task is disabled while no\nrule is active and input events can force an iteration. This keeps the distinction\nclear: Stage 7B proves rule semantics; Stage 7C proves runtime scheduling/state flow.",
    "Stage 7B evaluation was intentionally explicit/manual. Stage 7C connects the same\nengine to TaskScheduler + EventBus so the evaluation work task is disabled while no\nrule is active and input events can force an iteration. The distinction remains\nclear: Stage 7B proves rule semantics; Stage 7C proves runtime scheduling/state flow."
)
replace_once(
    "docs/configuration.md",
    "Stage 7B intentionally stops at explicit/manual evaluation. Stage 7C adds TaskScheduler + EventBus runtime wiring; Stage 7D later binds persisted rule semantics to ConfigurationStore revisions.",
    "Stage 7B intentionally stops at explicit/manual evaluation. Stage 7C adds and physically validates TaskScheduler + EventBus runtime wiring; Stage 7D binds persisted rule semantics to ConfigurationStore revisions."
)
p = Path("docs/configuration.md")
s = p.read_text()
if "## Stage 7C physical validation" not in s:
    s += """

## Stage 7C physical validation

Stage 7C was physically proven through the signed A/B path. Controlled
`0.1.34-remote-test/build 35` ran the virtual temperature/heater rule with
`RuleRuntime` event scheduling. A delayed local input (`15`) was queued, Wi-Fi was
deliberately disconnected before the event fired, and HTTP was confirmed unavailable.
When connectivity returned, runtime counters proved that exactly one local evaluation
had completed during the outage (`scheduled_count=1`, `completed_count=1`,
`last_run_result=TURN_ON`) and the virtual heater was ON.

The online regression then produced `17 -> HOLD` and `19 -> TURN_OFF`. Disabling the
rule left `scheduled_count` and `completed_count` unchanged while `rejected_count`
increased on a new input, proving disabled rules do not consume evaluation work.
The one-shot work task returned to disabled after every completed evaluation.

Clean `0.1.35/build 36` was installed on `app0`, reached native `VALID`, restored
HTTPS-only remote-update policy, preserved ConfigurationStore revision 3, returned the
production component registry to only `connectivity`, left RuleEngine unconfigured and
RuleRuntime `DISABLED`, and removed all Stage 7C lab endpoints (HTTP 404).

**Stage 7C: VALIDATED. Stage 7D binds persisted validated rule documents/revisions to
the RuleEngine/RuleRuntime lifecycle.**
"""
    p.write_text(s)

replace_once(
    "docs/architecture.md",
    "or relays exist. Stage 7C will add TaskScheduler/EventBus-driven automatic evaluation;\nStage 7D will bind validated persisted rule documents to the engine lifecycle.",
    "or relays exist. Stage 7C adds TaskScheduler/EventBus-driven one-shot automatic evaluation;\nStage 7D will bind validated persisted rule documents to the engine lifecycle."
)
replace_once(
    "docs/architecture.md",
    "This validates the ownership boundary before scheduling is introduced: **RuleEngine decides desired functional state; Component/FSM owns behavior; Driver owns hardware.** Stage 7C now adds only the timing/event layer: TaskScheduler determines when evaluation runs and EventBus may force a pending evaluation. No Stage 7C task should stay enabled when there is no active rule.",
    "This validates the ownership boundary: **RuleEngine decides desired functional state; Component/FSM owns behavior; Driver owns hardware.** Stage 7C adds only the timing/event layer: TaskScheduler determines when evaluation runs and EventBus may request a pending evaluation. The physical offline proof confirms no Stage 7C work task needs to stay enabled while an active rule is merely armed."
)
p = Path("docs/architecture.md")
s = p.read_text()
if "### Stage 7C physical closure" not in s:
    s += """

### Stage 7C physical closure

The scheduling boundary was proven on hardware, including a real connectivity outage.
A delayed local input was queued, Wi-Fi/MQTT were removed before it fired, and HTTP
became unreachable. The input still traversed the local EventBus and RuleRuntime,
scheduled one TaskScheduler evaluation, and produced `TURN_ON`. After reconnect,
runtime counters showed one scheduled and one completed evaluation with the work task
disabled again. Subsequent `HOLD` and `TURN_OFF` decisions passed, and a disabled rule
rejected new work without scheduling an evaluation.

This confirms the platform ownership model under actual connectivity loss:

```text
connectivity failure -> Supervisor may degrade
local input          -> EventBus
EventBus             -> RuleRuntime eligibility
RuleRuntime          -> one-shot TaskScheduler work
RuleEngine           -> desired state
Actuator component   -> owns application
```

External connectivity is therefore observability/management, not a prerequisite for
the local rule-control path.
"""
    p.write_text(s)

replace_once("docs/BOOTSTRAP.md", "- clean physical baseline is `0.1.31/build 32`, `app0/VALID`;", "- clean physical baseline is `0.1.35/build 36`, `app0/VALID`;")
replace_once(
    "docs/BOOTSTRAP.md",
    "**Stage 7C next:** TaskScheduler + EventBus runtime evaluation. The evaluation work task must be disabled when no rule is active, input events may force an evaluation, and rule/actuator state ownership remains in the engine/component FSM layer.",
    "**Stage 7C validated:** TaskScheduler + EventBus now drive one-shot RuleRuntime evaluation. A real Wi-Fi/MQTT outage proved a locally queued input still evaluated and actuated the virtual component; completed work returns the task to disabled, and disabled rules reject new scheduling. Clean baseline is `0.1.35/build 36`, `app0/VALID`, HTTPS-only, ConfigurationStore revision 3, RuleRuntime `DISABLED`, lab endpoints absent. **Stage 7D next:** bind persisted validated rule documents/revisions to RuleEngine/RuleRuntime lifecycle."
)
old_steps = """## Immediate next steps

1. Continue **Stage 7A**: the dual-slot transactional `ConfigurationStore` is implemented; physically prove apply/reboot/rollback persistence before starting RuleEngine execution.
2. Introduce the first local `RuleEngine` path with TaskScheduler + FSM semantics and no dependency on Wi-Fi/MQTT/cloud.
3. Add a local scheduling abstraction for rule evaluation and delayed/settling behavior; tasks remain disabled until work is meaningful.
4. Keep the cross-cutting network-hardening backlog: replace `setInsecure()` with CA validation, then add MQTT LWT and backoff/jitter.
5. Continue opportunistic TaskScheduler + FSM migration only when touching a subsystem or when it materially reduces custom timing/recovery code.
"""
new_steps = """## Immediate next steps

1. Start **Stage 7D**: bind validated persisted rule documents and ConfigurationStore revisions to RuleEngine/RuleRuntime lifecycle.
2. Preserve the Stage 7C invariant: RuleRuntime work tasks remain disabled until an event makes evaluation meaningful; connectivity is never required for local rule execution.
3. Then add the local schedule/delayed-action layer for schedules, settling windows and future actuator timing.
4. Keep the cross-cutting network-hardening backlog: replace `setInsecure()` with CA validation, then add MQTT LWT and backoff/jitter.
5. Continue opportunistic TaskScheduler + FSM migration only when touching a subsystem or when it materially reduces custom timing/recovery code.
"""
replace_once("docs/BOOTSTRAP.md", old_steps, new_steps)
p = Path("docs/BOOTSTRAP.md")
s = p.read_text()
if "## Stage 7C closure" not in s:
    s += """

## Stage 7C closure

Stage 7C is physically validated. Controlled `0.1.34-remote-test/build 35` proved
EventBus -> RuleRuntime -> one-shot TaskScheduler -> RuleEngine execution while
Wi-Fi/MQTT were deliberately unavailable. Hysteresis, disabled-rule rejection,
Supervisor recovery and EventBus `dropped=0` were verified. Clean
`0.1.35/build 36` is running on `app0/VALID`, Wi-Fi + MQTT/TLS connected, HTTPS-only
remote update restored, ConfigurationStore revision 3 preserved, production registry
contains only `connectivity`, RuleRuntime is `DISABLED`, and Stage 7C lab endpoints are
absent.
"""
    p.write_text(s)

p = Path("docs/runtime-test-log.md")
s = p.read_text()
if "## 2026-09-05 — Stage 7C RuleRuntime physical result" not in s:
    s += """

## 2026-09-05 — Stage 7C RuleRuntime physical result

### Result — PASS

- Stage 7C introduced `RuleRuntime` as the EventBus/TaskScheduler adapter around the already validated hysteresis RuleEngine.
- Controlled lab image `0.1.34-remote-test/build 35` installed through the signed A/B OTA path and reached `PENDING_VERIFY -> VALID` on `app1`.
- With a rule armed, the evaluation task remained disabled until an input event arrived. Each input scheduled one `TASK_ONCE` evaluation and the task disabled again after completion.
- Offline proof: a local input value `15` was queued with a 3 s delay, then Wi-Fi was deliberately disconnected and reconnect suppressed long enough to confirm HTTP was unreachable. After connectivity recovered, `RuleRuntime` reported `scheduled_count=1`, `completed_count=1`, `last_run_result=TURN_ON`; the virtual heater was ON. This proves the local rule path executed while Wi-Fi/MQTT were absent.
- Online hysteresis regression passed: `17 -> HOLD` while heater remained ON, then `19 -> TURN_OFF`.
- After disabling the rule, another input increased `rejected_count` but did not increase `scheduled_count` or `completed_count`, proving disabled rules do not consume evaluation work.
- Supervisor recovered to `RUNNING/OK`; EventBus remained `dropped=0`.
- Clean target `0.1.35/build 36` installed on `app0`, reached `PENDING_VERIFY -> VALID`, returned Wi-Fi + MQTT/TLS, restored HTTPS-only remote update, preserved ConfigurationStore revision 3, reduced the production registry to only `connectivity`, left RuleEngine unconfigured and RuleRuntime `DISABLED`, and removed Stage 7C lab endpoints (HTTP 404).
- Final proof marker: `STAGE7C_PHYSICAL_PROOF_OK`.
- Canonical default firmware is promoted to `0.1.35/build 36`.

**Stage 7C: VALIDATED. Stage 7D is next: persisted rule binding to the ConfigurationStore revision lifecycle.**
"""
    p.write_text(s)

replace_once("platformio.ini", '-DPROJ_FW_VERSION=\\"0.1.34\\"', '-DPROJ_FW_VERSION=\\"0.1.35\\"')
replace_once("platformio.ini", "-DPROJ_FW_BUILD=35", "-DPROJ_FW_BUILD=36")

print("STAGE7C_DOC_PATCH_OK")
