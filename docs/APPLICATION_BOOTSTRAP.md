# Application bootstrap from proj-esp32 Core

Use this template when starting a new ESP32 application derived from `kernelpanic2015/proj-esp32`.

The purpose is to keep the reusable Core stable while allowing applications to diverge in hardware, behavior, UI and domain logic.

## 1. Declare the application

Fill this block before implementation starts:

```text
Application name: <name>
Repository: <owner/repository>
Purpose: <one-sentence purpose>
Core baseline: core-v1.0.0
Core baseline commit: f2ab6e7a16e418a7f60d44b1a60ad6a6e7c37084
Application version: <application-owned version>
Target board: <board/module>
Deployment environment: <lab/home/building/vehicle/etc>
```

If a later compatible Core baseline is selected, replace both the Core baseline name and commit above.

The application version is independent from the Core version.

## 2. Read the Core contract first

Before modifying firmware, read:

1. `core-manifest.json`
2. `docs/CORE_BASELINE.md`
3. `docs/BOOTSTRAP.md`
4. `docs/architecture.md`
5. `docs/operations.md`

Do not reconstruct Stages 0-7 from conversation history unless investigating a historical regression. The repository is the source of truth.

## 3. Preserve Core invariants

Unless the application has evidence of a reusable Core defect, preserve these contracts:

- TaskScheduler owns **when** work becomes eligible;
- FSMs own **state and behavior**;
- EventBus communicates **what happened**;
- Components own subsystem behavior and health interpretation;
- Supervisor aggregates health and must not become application logic;
- RuleEngine computes desired consequences and must not access GPIO directly;
- drivers are the path to physical hardware access;
- configured local behavior should continue without cloud connectivity when technically possible;
- failures should be isolated to affected components/dependencies;
- signed A/B OTA, boot validation and rollback remain the firmware trust/update path;
- critical configuration belongs in the transactional persistence model rather than ad-hoc globals/files.

## 4. Define external hardware

Create an explicit inventory before assigning GPIOs.

```text
Device/module: <model>
Role: <sensor/actuator/display/storage/radio/etc>
Bus/interface: <I2C/SPI/UART/GPIO/ADC/PWM/etc>
Voltage: <value>
Driver/library candidate: <name/repository>
Required pins: <known or TBD>
Failure behavior: <expected safe behavior>
Core dependency: <none/component/service/rule/etc>
```

Do not lock GPIO assignments before the physical module pinout and ESP32 boot/flash/UART constraints are checked.

## 5. Maintain an application GPIO map

The application owns product GPIO assignments.

Example table:

| Function | GPIO | Direction | Boot-sensitive? | Shared bus? | Notes |
|---|---:|---|---|---|---|
| `<function>` | `<n>` | `<in/out>` | `<yes/no>` | `<bus/none>` | `<notes>` |

Keep the Core free of application-specific GPIO definitions unless they are truly board-platform requirements.

## 6. Decide module ownership

For each new capability, classify it before coding:

```text
Driver    -> talks to hardware
Component -> owns device/subsystem state + health
Service   -> reusable coordination/communication behavior
Rule      -> desired functional consequence
Application -> domain workflow and product behavior
```

If the classification is unclear, default to keeping domain behavior outside the Core.

## 7. Define health and fault behavior

Every fallible external component should declare:

- normal states;
- degraded/stale states;
- fault state;
- recovery/backoff behavior;
- last success / last error metadata where useful;
- dependent outputs;
- dependency policy where applicable.

Available validated dependency policies:

- `SAFE_OFF`
- `SAFE_ON`
- `KEEP_LAST_STATE`
- `DISABLE_RULE`
- `ALARM_ONLY`

A component fault should not stop unrelated application functions.

## 8. Define persistence and configuration

Document what the application stores and why.

Prefer:

- NVS / ConfigurationStore for critical configuration and rules;
- LittleFS only for generic internal assets/recovery when appropriate;
- SD/external storage for large application data, logs or UI assets when the application requires it.

Do not make local control depend on removable storage unless that dependency is explicit and has a safe degraded mode.

## 9. Define telemetry before field use

Each application should decide what operational evidence it needs to improve both itself and the Core.

Suggested reusable telemetry categories:

- firmware/application uptime;
- reboot/reset reason;
- free/minimum heap;
- Supervisor transitions;
- component state/health transitions;
- EventBus dropped count;
- Wi-Fi reconnect attempts/successes;
- MQTT reconnect attempts/successes;
- OTA check/install/rollback outcomes;
- configuration apply/reject/rollback counts;
- rule/schedule execution/fault-policy counters.

Application-specific telemetry may be added separately.

Do not send credentials, tokens, private keys or sensitive application data as generic Core telemetry.

## 10. Define update/versioning policy

Each application owns its own firmware version and release cadence.

Record in the application repository:

```text
application_version: <version>
core_baseline: <core-vX.Y.Z>
core_commit: <sha>
```

When adopting a newer Core baseline:

1. review Core changes;
2. merge/cherry-pick/rebase using the application's chosen strategy;
3. run application regression tests;
4. physically validate safety-critical hardware behavior;
5. only then publish a new application release.

Do not silently change the Core baseline of a released application.

## 11. Core upstream rule

When field use reveals a problem, classify it:

### Keep in the application

The finding is specific to:

- one sensor/actuator model;
- one GPIO layout;
- one domain workflow;
- one UI;
- one deployment-specific integration.

### Propose back to Core

The finding affects reusable platform behavior such as:

- scheduler/runtime behavior;
- FSM/component contracts;
- Supervisor/health semantics;
- EventBus reliability;
- OTA/update safety;
- ConfigurationStore behavior;
- generic RuleRuntime/fault-policy semantics;
- Wi-Fi/MQTT reliability;
- memory/performance;
- generic telemetry/observability;
- security hardening.

Upstream flow:

```text
application evidence
    -> reproduce against Core
    -> fix Core main
    -> Core regression + physical validation
    -> publish new Core baseline
    -> application adopts deliberately
```

Do not patch the Core differently in many applications when the same reusable bug can be fixed once upstream.

## 12. Minimum validation gates for a new application

Before considering the application baseline stable, verify at least:

- Core baseline/ref recorded;
- local Git tree clean and synchronized;
- normal PlatformIO build succeeds;
- firmware fits OTA partition with headroom;
- boot reaches expected application state;
- `/api/version` and `/api/status` remain coherent;
- Supervisor and component health are sane;
- EventBus does not unexpectedly drop events;
- application hardware can fail/recover without unrelated subsystem failure;
- selected safe-state/fault policies behave as documented;
- local operation still behaves correctly during connectivity loss where applicable;
- signed OTA update path still works after application integration;
- application-specific telemetry is observable;
- secrets remain outside Git.

Add application-specific physical acceptance tests on top of these gates.

## 13. Recommended repository layout

An application may retain the Core layout and add explicit application areas, for example:

```text
src/
├── core/             # inherited/reusable Core
├── components/       # generic + application components
├── drivers/          # physical device drivers
├── rules/            # generic runtime + application rule binding
├── app/              # application/domain orchestration
└── main.cpp

docs/
├── APPLICATION.md
├── HARDWARE.md
├── TEST_PLAN.md
└── ...
```

The exact layout may evolve, but application/domain code should remain distinguishable from reusable Core code.

## 14. New-chat starter

A new ChatGPT/agent conversation can begin with:

```text
Use kernelpanic2015/proj-esp32 as the Core reference.
Read core-manifest.json, docs/CORE_BASELINE.md and docs/APPLICATION_BOOTSTRAP.md first.

Application: <name>
Repository: <repository>
Core baseline: <core-vX.Y.Z>
Core commit: <sha>
External hardware: <list>
Goal: <goal>

Preserve the Core contracts unless evidence shows a reusable Core change is required. Keep application-specific hardware and behavior outside Core main.
```

Then inspect the application's own repository/documentation before planning implementation.

## 15. First application rule

The first task in a derived project is **not** automatically RTC, TFT, touch, SD, sensors or relays.

The first task is to declare the application boundary, hardware inventory, safety behavior and validation plan. The hardware roadmap follows from the application goal.
