from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def write(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def replace_once(rel, old, new):
    text = read(rel)
    if old not in text:
        raise SystemExit(f'missing anchor in {rel}: {old[:140]!r}')
    write(rel, text.replace(old, new, 1))

# Promote the physically proven clean target to the canonical source identity.
replace_once('include/firmware_identity.h', '#define PROJ_FW_VERSION "0.1.31"', '#define PROJ_FW_VERSION "0.1.37"')
replace_once('include/firmware_identity.h', '#define PROJ_FW_BUILD 32', '#define PROJ_FW_BUILD 38')

# Reserve the next monotonic identities for Stage 7E.
replace_once('platformio.ini', '-DPROJ_FW_VERSION=\\"0.1.35\\"\n    -DPROJ_FW_BUILD=36', '-DPROJ_FW_VERSION=\\"0.1.38\\"\n    -DPROJ_FW_BUILD=39')
replace_once('platformio.ini', '-DPROJ_FW_VERSION=\\"0.1.36-remote-test\\"\n    -DPROJ_FW_BUILD=37', '-DPROJ_FW_VERSION=\\"0.1.38-remote-test\\"\n    -DPROJ_FW_BUILD=39')
replace_once('platformio.ini', '-DPROJ_FW_VERSION=\\"0.1.37\\"\n    -DPROJ_FW_BUILD=38', '-DPROJ_FW_VERSION=\\"0.1.39\\"\n    -DPROJ_FW_BUILD=40')

# Roadmap closure.
replace_once('docs/ROADMAP.md',
             '- [~] **Stage 7D** — persisted rule binding to RuleEngine/RuleRuntime with boot/apply/rollback lifecycle; physical proof pending;',
             '- [x] **Stage 7D** — persisted rule binding to RuleEngine/RuleRuntime with boot/apply/rollback lifecycle physically validated;')
replace_once('docs/ROADMAP.md',
             '**Stage 7D next:** bind validated persisted rule documents and ConfigurationStore revisions to the RuleEngine/RuleRuntime lifecycle without weakening the Stage 7C rule that work tasks stay disabled until work is meaningful.\n',
             '''**Stage 7D: VALIDATED on hardware.** Legacy revision 3 remained boot-readable but non-executable. A semantically invalid hysteresis candidate was rejected without changing revision 3. Valid rule A became revision 4 and immediately armed RuleRuntime; after reboot it reloaded automatically and drove the virtual actuator. Rule B became revision 5; explicit rollback restored rule A as monotonic revision 6, and that rollback survived reboot. Clean `0.1.37/build 38` reached `app0/VALID`, retained revision 6, automatically loaded `persisted.demo.a`, left RuleRuntime `ARMED` with its work task disabled until input exists, restored HTTPS-only operation and removed lab endpoints.\n\n**Stage 7E next:** introduce the local schedule/delayed-action service above TaskScheduler, keeping persisted schedule semantics separate from the scheduler primitive and keeping inactive schedule work disabled.\n''')

# Configuration contract / physical proof.
config = read('docs/configuration.md')
if '## Stage 7D physical validation' not in config:
    config += '''\n\n## Stage 7D physical validation\n\nStage 7D was physically validated through the signed A/B path. The controlled `0.1.36-remote-test/build 37` image booted the existing revision 3 legacy envelope without executing it; `PersistedRuleLoader` reported `persisted_rule_type_unsupported`, RuleEngine remained unconfigured and RuleRuntime remained `DISABLED`. This proves migration safety: structurally valid legacy bytes are not silently interpreted as executable semantics.\n\nA candidate with inverted hysteresis (`on_below=18`, `off_above=16`) returned HTTP 400 with `persisted_rule_hysteresis_invalid`; revision 3 remained active. Valid rule A (`persisted.demo.a`, 16/18) then committed as revision 4. The loader immediately reported revision 4, RuleEngine became configured/enabled, RuleRuntime became `ARMED`, and the one-shot work task remained disabled until input arrived. Inputs 15 and 19 produced `TURN_ON` and `TURN_OFF`.\n\nAn intentional reboot then loaded revision 4 automatically before network-dependent management was needed. Rule A again armed RuleRuntime and drove the virtual actuator. Rule B (`persisted.demo.b`, 14/20) committed as revision 5 and was activated immediately. Explicit ConfigurationStore rollback restored rule A as new monotonic revision 6; its 16/18 semantics were active immediately and survived another intentional reboot.\n\nFinally clean `0.1.37/build 38` installed on `app0`, reached `PENDING_VERIFY -> VALID`, retained configuration revision 6 and automatically loaded `persisted.demo.a`. RuleRuntime is `ARMED`, but `work_task_enabled=false` and `pending=false` because the clean virtual input has no value. Supervisor is `RUNNING/OK`, EventBus is `dropped=0`, Wi-Fi + MQTT/TLS are healthy, remote update is HTTPS-only, and the Stage 7D mutation/test endpoint returns HTTP 404.\n\nThe physical proof was reconciled in Aurora issue #765 with marker `STAGE7D_PHYSICAL_PROOF_OK`. The earlier wrapper #764 reached every final assertion and installed the clean image but returned failure because a shell `pipefail`/`grep -q` assertion path was brittle against the large status payload; #765 rechecked the recorded intermediate proof plus live final state with JSON parsing and exited 0.\n'''
    write('docs/configuration.md', config)

# Runtime log.
runtime = read('docs/runtime-test-log.md')
if '## 2026-09-05 — Stage 7D persisted rule lifecycle' not in runtime:
    runtime += '''\n\n## 2026-09-05 — Stage 7D persisted rule lifecycle\n\n### Result — PASS\n\n- Added `PersistedRuleLoader` as the semantic binding layer between ConfigurationStore revisions and RuleEngine/RuleRuntime.\n- Existing revision 3 legacy envelope stayed readable but non-executable (`persisted_rule_type_unsupported`); RuleRuntime remained disabled until a valid Stage 7D rule was committed.\n- Invalid hysteresis was rejected before persistence and revision 3 remained unchanged.\n- Rule A (`persisted.demo.a`, 16/18) became revision 4, activated immediately, armed RuleRuntime and produced `15 -> TURN_ON`, `19 -> TURN_OFF`.\n- After intentional reboot, revision 4 and rule A reloaded automatically and produced the same decisions.\n- Rule B (`persisted.demo.b`, 14/20) became revision 5 and activated immediately.\n- Explicit rollback restored rule A as monotonic revision 6; rule A immediately became active again and survived a second reboot.\n- Clean target `0.1.37/build 38` installed on `app0`, reached `PENDING_VERIFY -> VALID`, retained revision 6, automatically loaded rule A, left RuleRuntime `ARMED` with `work_task_enabled=false`/`pending=false`, restored HTTPS-only update behavior, kept Supervisor `RUNNING/OK`, EventBus `dropped=0`, and removed lab endpoints (HTTP 404).\n- Aurora #765 reconciled the complete proof and ended `completed`, exit code 0, with marker `STAGE7D_PHYSICAL_PROOF_OK`.\n\n**Stage 7D: VALIDATED. Stage 7E local schedule/delayed-action service is next.**\n'''
    write('docs/runtime-test-log.md', runtime)

# Architecture closure.
arch = read('docs/architecture.md')
if '### Stage 7D physical closure' not in arch:
    arch += '''\n\n### Stage 7D physical closure\n\nThe persisted ownership boundary is now proven across apply, reboot, replacement, rollback and clean OTA. ConfigurationStore remains responsible only for durable transactional bytes/revisions. `PersistedRuleLoader` owns semantic translation/validation and activation. RuleEngine owns functional hysteresis decisions. RuleRuntime owns `DISABLED/ARMED/EVALUATING` runtime state and one-shot scheduling. VirtualActuatorComponent owns desired-state application; no GPIO is accessed.\n\nThe clean baseline intentionally keeps the persisted rule armed while its input is unavailable. This is not a polling loop: `ARMED` expresses eligibility, while the TaskScheduler work task remains disabled until an input event makes evaluation meaningful. Stage 7E extends the same distinction to persisted schedules and delayed actions.\n'''
    write('docs/architecture.md', arch)

# docs index + current state.
replace_once('docs/README.md',
             '- [~] Stage 7D persisted rule binding + boot/apply/rollback lifecycle; physical proof pending',
             '- [x] Stage 7D persisted rule binding + boot/apply/rollback lifecycle physically validated\n- [ ] Stage 7E local schedule/delayed-action service')
replace_once('docs/README.md',
             'Validated directly on the physical device on 2026-09-05 after Stage 7C closure:',
             'Validated directly on the physical device on 2026-09-05 after Stage 7D closure:')
replace_once('docs/README.md', '- firmware: `0.1.35`, build `36`, channel `dev`', '- firmware: `0.1.37`, build `38`, channel `dev`')
replace_once('docs/README.md',
             '- lab-only Wi-Fi/MQTT/rule-runtime test endpoints: absent from the clean image\n- RuleRuntime: `DISABLED`, no active rule, work task disabled in the clean image',
             '- lab-only Wi-Fi/MQTT/rule mutation endpoints: absent from the clean image\n- ConfigurationStore: revision `6`, persisted rule `persisted.demo.a`\n- RuleEngine: configured/enabled from persisted configuration\n- RuleRuntime: `ARMED`; work task disabled and no pending work until input exists')
replace_once('docs/README.md',
             'Stage 6 core runtime and Stage 7A transactional configuration are validated. **Stage 7B is physically validated:** the hardware-independent hysteresis RuleEngine correctly drove virtual desired state across ON/OFF thresholds and deadband, rejected invalid semantics, and did not actuate while disabled. **Stage 7C is now physically validated:** an EventBus input schedules exactly one TaskScheduler evaluation, the task disables again after completion, disabled rules reject work without scheduling it, and the rule path was proven to execute while Wi-Fi/MQTT were deliberately unavailable. Clean `0.1.35/build 36` exposes the read-only rule/runtime status only; lab endpoints are absent. **Stage 7D is next:** bind persisted validated rule documents/revisions to RuleEngine/RuleRuntime lifecycle.\n',
             'Stages 7A-7C remain validated. **Stage 7D is now physically validated:** persisted rule semantics activate immediately after transactional apply, reload automatically after reboot, follow monotonic ConfigurationStore rollback, and survive clean signed A/B OTA. Clean `0.1.37/build 38` holds configuration revision 6 with `persisted.demo.a` loaded; RuleRuntime is `ARMED` while its work task stays disabled until meaningful input exists. **Stage 7E is next:** local persisted schedules and delayed actions above TaskScheduler.\n')

# Bootstrap baseline and handoff.
replace_once('docs/BOOTSTRAP.md', 'Current physical device state after Stage 7B minimal RuleEngine closure:', 'Current physical device state after Stage 7D persisted-rule closure:')
replace_once('docs/BOOTSTRAP.md', '- firmware: `0.1.31`\n- build: `32`', '- firmware: `0.1.37`\n- build: `38`')
replace_once('docs/BOOTSTRAP.md',
             'Stage 6E physically proved a full Wi-Fi loss and recovery. Stage 7A then physically proved dual-slot transactional configuration, invalid-candidate rejection, reboot persistence, monotonic rollback and persistence across signed A/B OTA. The current ConfigurationStore document is revision 3 and remains local-NVS backed.\n',
             'Stage 6E physically proved full Wi-Fi loss/recovery. Stage 7A proved dual-slot transactional configuration. Stage 7B proved hysteresis semantics, Stage 7C proved event-driven local execution during a real Wi-Fi/MQTT outage, and Stage 7D now proves persisted rule activation across apply/reboot/rollback/OTA. The current ConfigurationStore document is revision 6 and remains local-NVS backed.\n')
replace_once('docs/BOOTSTRAP.md',
             '- clean physical baseline is `0.1.35/build 36`, `app0/VALID`;\n- ConfigurationStore remains revision 3; persisted rule binding is intentionally deferred to Stage 7D.\n\n**Stage 7C validated:** TaskScheduler + EventBus now drive one-shot RuleRuntime evaluation. A real Wi-Fi/MQTT outage proved a locally queued input still evaluated and actuated the virtual component; completed work returns the task to disabled, and disabled rules reject new scheduling. Clean baseline is `0.1.35/build 36`, `app0/VALID`, HTTPS-only, ConfigurationStore revision 3, RuleRuntime `DISABLED`, lab endpoints absent. **Stage 7D next:** bind persisted validated rule documents/revisions to RuleEngine/RuleRuntime lifecycle.\n',
             '- Stage 7B clean baseline was `0.1.31/build 32`; later stages supersede it.\n\n**Stage 7C validated:** TaskScheduler + EventBus drive one-shot RuleRuntime evaluation, including execution during real Wi-Fi/MQTT loss.\n\n## Stage 7D persisted rules — validated\n\n- clean physical baseline: `0.1.37/build 38`, `app0/VALID`;\n- ConfigurationStore revision: `6`;\n- active persisted rule: `persisted.demo.a`, hysteresis 16/18;\n- `PersistedRuleLoader` loads revision 6 automatically at boot;\n- RuleEngine: configured/enabled;\n- RuleRuntime: `ARMED`, work task disabled with no pending work until an input event exists;\n- invalid persisted semantics are rejected before slot/pointer activation;\n- apply activation, reboot reload, rule replacement, monotonic rollback and rollback reboot persistence are physically proven;\n- virtual bindings exist in the clean runtime, but mutation/test HTTP endpoints are absent;\n- Supervisor: `RUNNING/OK`; EventBus `dropped=0`; Wi-Fi + MQTT/TLS healthy; HTTPS-only remote update.\n\n**Stage 7E next:** local persisted schedule/delayed-action service above TaskScheduler. Keep scheduler primitives separate from schedule semantics; inactive work stays disabled.\n')

# Top-level README.
replace_once('README.md',
             '**Current physical baseline:** `0.1.35/build 36`, `app0`, native OTA `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, Wi-Fi + MQTT/TLS connected and EventBus `dropped=0`. ConfigurationStore remains revision 3; the production RuleRuntime is `DISABLED` with no active rule and Stage 7C lab endpoints are absent.\n',
             '**Current physical baseline:** `0.1.37/build 38`, `app0`, native OTA `VALID`, application `ONLINE`, Supervisor `RUNNING/OK`, Wi-Fi + MQTT/TLS connected and EventBus `dropped=0`. ConfigurationStore is revision 6 with persisted rule `persisted.demo.a`; RuleEngine is configured/enabled and RuleRuntime is `ARMED`, while its work task remains disabled until input exists. Lab mutation endpoints are absent.\n')
replace_once('README.md',
             '**Stages 7A-7C are validated:** transactional configuration, hysteresis semantics, and one-shot local RuleRuntime execution have all been physically proven. **Stage 7D is in progress:** persisted ConfigurationStore rule documents become the source of truth for RuleEngine/RuleRuntime across boot, apply and rollback; physical persistence/rollback proof is pending.\n',
             '**Stages 7A-7D are validated:** transactional configuration, hysteresis semantics, one-shot local execution and persisted rule lifecycle have all been physically proven. Apply/reboot/replacement/rollback/clean-OTA preserve the local rule source of truth. **Stage 7E is next:** persisted local schedules and delayed actions above TaskScheduler.\n')

print('STAGE7D_CLOSE_PATCHED')
