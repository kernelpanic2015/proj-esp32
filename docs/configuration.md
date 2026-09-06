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
