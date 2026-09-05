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

Stage 7B evaluation is intentionally explicit/manual. Stage 7C will connect the same
engine to TaskScheduler + EventBus so the evaluation work task is disabled while no
rule is active and input events can force an iteration. This keeps the distinction
clear: Stage 7B proves rule semantics; Stage 7C proves runtime scheduling/state flow.
