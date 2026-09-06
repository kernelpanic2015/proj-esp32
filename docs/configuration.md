# Persistent configuration — Stage 7

Stage 7 introduces the configuration/control plane that local automation will consume. The invariant remains: **the cloud manages; the device controls**. Once configuration has been accepted, its execution must not depend on Wi-Fi, MQTT, HTTP or an external agent.

## Stage 7A — ConfigurationStore

`ConfigurationStore` uses a two-slot NVS transaction model in namespace `app-config`:

```text
slot0 <----> slot1
     active pointer
```

An update is committed in this order:

1. parse and validate the candidate in RAM;
2. assign the next monotonic device revision;
3. write the inactive slot;
4. read the slot back and validate it again;
5. flip the single-byte `active` pointer only after verification.

A power loss before step 5 leaves the old configuration active. The previously active slot remains available for rollback. Rollback copies the previous payload into a new monotonic revision instead of moving the revision number backwards.

Boot recovery first tries the selected slot, then the other valid slot, then creates a revision-0 default document if neither slot is usable.

Current schema 1 envelope:

```json
{
  "schema": 1,
  "revision": 0,
  "rules": [],
  "schedules": []
}
```

Store-level validation currently checks the schema/envelope, bounded array sizes, entry object shape, safe unique `id` values and optional boolean `enabled`. Rule/schedule semantics are deliberately not executed by Stage 7A; the RuleEngine and local scheduler will add semantic validation before those entries become effective.

Limits in the first implementation:

- maximum serialized configuration: 3072 bytes;
- maximum rules: 16;
- maximum schedules: 16;
- IDs: 1–48 characters, limited to alphanumeric plus `_ - . :`.

HTTP development/control surfaces:

```text
GET  /api/configuration/status
GET  /api/configuration
POST /api/configuration/apply       form field: config=<json>
POST /api/configuration/rollback
```

These routes manage a local NVS store; HTTP availability is not required for configuration execution. Authentication/network-exposure hardening remains a separate production concern.

## TaskScheduler + FSM rule for Stage 7

Configuration persistence itself is synchronous and short. Periodic rule evaluation, delayed actions, settling windows, retries and schedules will use TaskScheduler. FSMs remain owners of state/behavior. Tasks should be disabled while their work is not meaningful.

## Stage 7A physical validation

Stage 7A was proven on the physical ESP32 with the signed A/B update path:

```text
rev0 defaults
  -> apply valid config A -> rev1
  -> reject duplicate-id candidate (HTTP 400), rev1 remains active
  -> reboot -> rev1 loaded
  -> apply valid config B -> rev2
  -> rollback -> logical config A restored as monotonic rev3
  -> reboot -> rev3 loaded
  -> signed clean OTA -> 0.1.29/build30 app0 PENDING_VERIFY -> VALID
  -> rev3 still loaded
```

The active document after rollback contained `demo.rule` disabled with the first logical payload, while `previous_revision=2`. Wi-Fi, MQTT/TLS, Supervisor and EventBus remained healthy and the clean image exposed no lab-only endpoint.

### Intentional restart versus DoubleResetDetector

The proof exposed a real interaction between controlled software reboots and DRD. The project uses a 10 s double-reset detection window and a 180 s configuration portal. A second software reboot issued inside the DRD window could therefore be mistaken for human recovery intent.

Intentional firmware restarts now use `RestartService::restartNow()`. A registered hook calls `drd->stop()` before `ESP.restart()`, clearing the DRD marker only for software-controlled restart paths. Two deliberate software reboots inside the 10 s window were physically proven to return ONLINE promptly. Hardware/manual reset behavior remains unchanged and still supports double-reset recovery.


## Stage 7B — minimal local rule model

Stage 7B deliberately proves the functional boundary before adding automatic scheduling.
The first engine supports one in-memory hysteresis rule and virtual input/output components.
It does **not** load rule semantics from persisted configuration yet and it does not touch GPIO.

Flow under the controlled lab build:

```text
VirtualInputComponent
        |
        | explicit value
        v
    RuleEngine
        |
        | desired boolean state
        v
VirtualActuatorComponent
```

The demo rule follows the field pattern that motivated the architecture:

```text
value < on_below   -> desired ON
value > off_above  -> desired OFF
inside deadband    -> HOLD current state
```

Semantic validation rejects invalid IDs, non-finite thresholds and hysteresis where
`on_below >= off_above`. The engine returns a desired state only; it has no driver or
GPIO dependency. The virtual actuator owns application of that desired state.

`GET /api/rules/status` is the standard read-only observability endpoint. Controlled
write/evaluation endpoints exist only in the remote test image behind
`PROJ_RULE_ENGINE_TEST_ENDPOINTS`.

Stage 7B evaluation was intentionally explicit/manual. Stage 7C connects the same
engine to TaskScheduler + EventBus so the evaluation work task is disabled while no
rule is active and input events can force an iteration. The distinction remains
clear: Stage 7B proves rule semantics; Stage 7C proves runtime scheduling/state flow.


## Stage 7B physical validation

Stage 7B was physically proven on the ESP32 with virtual I/O and the signed A/B path. The lab image was `0.1.30-remote-test/build 31` on `app1`, reached `PENDING_VERIFY -> VALID`, and exposed the test-gated virtual rule endpoints.

Acceptance sequence:

```text
invalid: on_below=18, off_above=16 -> HTTP 400 rule_hysteresis_invalid
valid:   on_below=16, off_above=18

input 20 -> actuator OFF, HOLD
input 15 -> actuator ON,  TURN_ON
input 17 -> actuator ON,  HOLD
input 19 -> actuator OFF, TURN_OFF
input 17 -> actuator OFF, HOLD

disable rule
input 10 -> actuator remains OFF, decision DISABLED
```

The enabled sequence produced exactly five evaluations. A disabled rule did not increment that count or change the actuator. The RuleEngine only returned desired state; `VirtualActuatorComponent` owned application of that state and no GPIO was touched.

During the lab proof the component registry contained `connectivity`, `virtual.temperature`, and `virtual.heater`; Supervisor remained `RUNNING/OK` and EventBus remained `dropped=0`. The clean `0.1.31/build 32` target then installed on `app0`, reached `VALID`, returned to HTTPS-only remote-update policy, retained ConfigurationStore revision 3, restored the normal registry to only `connectivity`, and returned HTTP 404 for `/api/test/rules/status`. The standard read-only `/api/rules/status` remained available with an unconfigured engine.

Stage 7B intentionally stops at explicit/manual evaluation. Stage 7C adds and physically validates TaskScheduler + EventBus runtime wiring; Stage 7D binds persisted rule semantics to ConfigurationStore revisions.


## Stage 7C — event-driven rule runtime

Stage 7C introduces `RuleRuntime`, which connects the validated hysteresis RuleEngine to
TaskScheduler and EventBus without moving state ownership into the scheduler.

```text
VirtualInputComponent
      |
      | InputValueChanged
      v
   EventBus
      |
      v
 RuleRuntime FSM
 DISABLED <-> ARMED -> EVALUATING -> ARMED
      |
      | one-shot work request
      v
 TaskScheduler
      |
      v
 RuleEngine -> desired state -> ActuatorComponent
```

The runtime owns a single `TASK_ONCE` evaluation work task. The task stays disabled
while no active rule exists and also stays disabled while an active rule is merely
armed. An input event schedules one evaluation for the next cooperative scheduler pass;
after the callback completes, TaskScheduler disables the one-shot task again.

This deliberately separates three concepts:

- `ARMED` means a rule is eligible to react;
- `work_task_enabled=true` means an evaluation is actually pending/running;
- `DISABLED` means no active rule exists, not a fault.

Repeated requests while the work task is already enabled are coalesced instead of
creating parallel rule evaluations. `GET /api/rules/runtime` exposes FSM state,
work-task enable state, request/scheduled/coalesced/completed/rejected counters and
last request/run results.

The controlled lab build also includes a delayed virtual-input endpoint. It exists only
to prove that a locally scheduled sensor event can run while Wi-Fi and MQTT are absent;
it is removed from the clean image.


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


## Stage 7D — persisted rule activation

Stage 7D binds transactional ConfigurationStore revisions to RuleEngine/RuleRuntime.
New candidates are semantically validated before the inactive slot is written or the
active pointer changes. Existing Stage 7A stored documents remain boot-readable for
migration safety; unsupported legacy rule envelopes do not become executable until
replaced by a valid Stage 7D rule document.

The first executable persisted rule schema is deliberately narrow:

```json
{
  "schema": 1,
  "rules": [{
    "id": "demo.temperature.heater",
    "type": "hysteresis",
    "input": "virtual.temperature",
    "output": "virtual.heater",
    "enabled": true,
    "on_below": 16,
    "off_above": 18
  }],
  "schedules": []
}
```

Stage 7D supports zero or one executable rule. New configuration is rejected before
activation when type/binding/hysteresis semantics are unsupported. After a successful
apply or rollback commit, PersistedRuleLoader activates the committed JSON/revision
after ConfigurationStore releases its mutex and refreshes RuleRuntime eligibility.
No Wi-Fi, MQTT or cloud dependency is involved.

`GET /api/rules/persisted` exposes non-secret binding diagnostics: loaded revision,
loaded rule id and loader result. Virtual input/actuator components are present in the
clean Stage 7D runtime as software-only local bindings; mutation/test HTTP endpoints
remain lab-build-only. Real GPIO remains deferred.


## Stage 7D physical validation

Stage 7D was physically validated through the signed A/B path. The controlled `0.1.36-remote-test/build 37` image booted the existing revision 3 legacy envelope without executing it; `PersistedRuleLoader` reported `persisted_rule_type_unsupported`, RuleEngine remained unconfigured and RuleRuntime remained `DISABLED`. This proves migration safety: structurally valid legacy bytes are not silently interpreted as executable semantics.

A candidate with inverted hysteresis (`on_below=18`, `off_above=16`) returned HTTP 400 with `persisted_rule_hysteresis_invalid`; revision 3 remained active. Valid rule A (`persisted.demo.a`, 16/18) then committed as revision 4. The loader immediately reported revision 4, RuleEngine became configured/enabled, RuleRuntime became `ARMED`, and the one-shot work task remained disabled until input arrived. Inputs 15 and 19 produced `TURN_ON` and `TURN_OFF`.

An intentional reboot then loaded revision 4 automatically before network-dependent management was needed. Rule A again armed RuleRuntime and drove the virtual actuator. Rule B (`persisted.demo.b`, 14/20) committed as revision 5 and was activated immediately. Explicit ConfigurationStore rollback restored rule A as new monotonic revision 6; its 16/18 semantics were active immediately and survived another intentional reboot.

Finally clean `0.1.37/build 38` installed on `app0`, reached `PENDING_VERIFY -> VALID`, retained configuration revision 6 and automatically loaded `persisted.demo.a`. RuleRuntime is `ARMED`, but `work_task_enabled=false` and `pending=false` because the clean virtual input has no value. Supervisor is `RUNNING/OK`, EventBus is `dropped=0`, Wi-Fi + MQTT/TLS are healthy, remote update is HTTPS-only, and the Stage 7D mutation/test endpoint returns HTTP 404.

The physical proof was reconciled in Aurora issue #765 with marker `STAGE7D_PHYSICAL_PROOF_OK`. The earlier wrapper #764 reached every final assertion and installed the clean image but returned failure because a shell `pipefail`/`grep -q` assertion path was brittle against the large status payload; #765 rechecked the recorded intermediate proof plus live final state with JSON parsing and exited 0.


## Stage 7E — local delayed-action schedule

Stage 7E introduces schedule semantics **above** TaskScheduler. TaskScheduler remains a
cooperative timing primitive; `LocalScheduleService` owns the persisted meaning and its
FSM owns `DISABLED -> WAITING -> FIRING -> COMPLETED/FAULT`.

The first deliberately narrow schedule schema is:

```json
{
  "id": "demo.delay.on",
  "type": "delay_after_activation",
  "enabled": true,
  "target": "virtual.schedule_output",
  "desired_on": true,
  "delay_ms": 4000
}
```

Only zero or one schedule is supported in Stage 7E. The work task is `TASK_ONCE` and is
enabled only while a valid enabled schedule is waiting to fire. After completion it is
disabled automatically. Removing/disabling the schedule cancels pending work.

This stage intentionally uses **relative runtime time**, not wall-clock time. Without a
validated RTC, a persisted delay starts again when its configuration is activated at
boot/apply/rollback. Calendar/cron semantics remain deferred until the DS3231 time
foundation in Stage 8. This avoids pretending that `millis()` is durable civil time.

The first target is a dedicated software-only `virtual.schedule_output`; no GPIO is
touched. `GET /api/schedules/status` exposes state, loaded revision, task enable state,
counters and the active schedule. ConfigurationStore semantic validation invokes both
the persisted-rule and persisted-schedule validators before committing a candidate.

## Stage 7E physical validation

Stage 7E was physically validated through the signed A/B path. Controlled
`0.1.38-remote-test/build 39` first loaded the existing revision 6 document with no
schedule. A candidate bound to unsupported target `gpio.1` returned HTTP 400
(`schedule_target_unsupported`) and revision 6 remained active.

Schedule A (`persisted.demo.delay.a`, desired ON, 6000 ms) committed as revision 7
and entered `WAITING` with its one-shot task enabled. Wi-Fi was then deliberately
disconnected with reconnect suppressed for the lab window. The schedule completed at
about 19.0 s after boot, while Wi-Fi reconnect succeeded only at about 22.0 s, proving
the action executed locally before connectivity returned. The task disabled after
completion and `virtual.schedule_output` was ON.

Schedule B (`persisted.demo.delay.b`, desired OFF, 15000 ms) became revision 8.
After an intentional reboot, ConfigurationStore loaded revision 8 and
LocalScheduleService automatically re-armed from boot/activation, remained `WAITING`,
then completed after the relative delay with the virtual output OFF. Explicit rollback
restored schedule A as monotonic revision 9, re-armed it immediately and completed
again.

A clean-persist schedule (`persisted.demo.delay.clean`, desired ON, 15000 ms) became
revision 10 before signed OTA to clean `0.1.39/build 40`. The clean image reached
`app0/PENDING_VERIFY -> VALID`, retained revision 10, loaded both the persisted rule
and schedule automatically, completed the delayed action, and returned its work task
to disabled. HTTPS-only remote update was restored, Wi-Fi + MQTT/TLS were healthy,
Supervisor was `RUNNING/OK`, EventBus remained `dropped=0`, and lab endpoints returned
HTTP 404.

The original physical wrapper (#775) returned exit code 1 after printing the complete
`STAGE7E_PHYSICAL_PROOF_OK` record. A separate read-only reconciliation (#777)
finished `aurora:completed`, exit code 0, checked the recorded proof plus live device
state, found no proof-console errors, and produced
`STAGE7E_PHYSICAL_RECONCILED_OK`. No OTA or configuration mutation was repeated during
reconciliation.

`ConfigurationStore` lifecycle callbacks now run after the store mutex is released,
so rule/schedule activation cannot deadlock by being called while `ConfigLock` is
held. The callback contract is still `void`; current semantic validation makes all
supported activations deterministic, but a future fallible activation subsystem
should use an explicit result/compensation contract rather than pretending the
post-commit callback itself is transactional.

**Stage 7E: VALIDATED.**


## Stage 7F — persisted actuator fault policy

A persisted hysteresis rule may include an optional `fault_policy`. Supported values are:

- `SAFE_OFF` — force the dependent output OFF while the input dependency is not healthy;
- `SAFE_ON` — force the dependent output ON;
- `KEEP_LAST_STATE` — freeze the current output state and do not evaluate stale input;
- `DISABLE_RULE` — suspend RuleRuntime while the dependency is unhealthy and automatically re-arm after recovery;
- `ALARM_ONLY` — record the policy action/alarm without changing the output.

Legacy Stage 7D/7E documents that omit `fault_policy` remain valid and resolve to the conservative `SAFE_OFF` default. Invalid policy names are rejected by persisted semantic validation before ConfigurationStore advances the active slot/revision.

The policy guard consumes component health; it never accesses GPIO. RuleEngine still computes desired state only from valid input, RuleRuntime coordinates dependency policy and evaluation, and the actuator component/driver remains the only future path to physical hardware.
