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
