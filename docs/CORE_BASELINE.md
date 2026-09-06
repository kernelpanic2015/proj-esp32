# Core Foundation baseline

`proj-esp32` is the reusable firmware core for ESP32 applications built from this repository.

## Core Foundation v1

The Core Foundation was closed after physical validation of Stages 0 through 7.

Baseline:

- repository: `kernelpanic2015/proj-esp32`
- baseline firmware: `0.1.41/build 42`
- physical state: `app0/VALID`, application `ONLINE`
- ConfigurationStore: revision 10
- Supervisor: `RUNNING/OK`
- EventBus: `dropped=0`
- default/legacy dependency policy: `SAFE_OFF`
- source baseline name: `core-v1.0.0`

The baseline identifies a reusable source contract, not a promise that every deployment is production-hardened. Security and reliability hardening may continue in later Core releases.

## What belongs to the Core

The Core owns reusable platform behavior that should remain common across applications:

- board/runtime identity and observability;
- cooperative TaskScheduler + FSM execution model;
- Component / ComponentRegistry / ComponentHealth contracts;
- bounded EventBus;
- Supervisor health aggregation;
- Wi-Fi provisioning and recovery;
- MQTT/TLS transport and telemetry surfaces;
- signed A/B OTA, boot validation and rollback;
- transactional NVS ConfigurationStore;
- local RuleEngine / RuleRuntime;
- persisted delayed actions;
- dependency/fault policies: `SAFE_OFF`, `SAFE_ON`, `KEEP_LAST_STATE`, `DISABLE_RULE`, `ALARM_ONLY`;
- local autonomy: configured control continues without cloud connectivity;
- separation of drivers, components, services, rules and physical hardware access.

## What does not belong to the Core

Application-specific hardware and behavior must not redefine the Core unless a reusable platform defect or capability is discovered.

Examples:

- a specific sensor or relay model;
- GPIO assignments for a product;
- TFT/touch layouts;
- a particular microSD content model;
- building automation, radio, health, telemetry or industrial application logic;
- application-specific rules, screens, workflows or cloud integrations.

These belong to application repositories, forks, branches or modules built on the Core.

## Repository and versioning model

### Core repository

`main` remains the evolving Core line.

Changes to `main` should be limited to reusable platform work such as:

- bug fixes;
- security hardening;
- performance/memory improvements;
- telemetry-driven reliability fixes;
- compatibility improvements;
- reusable component contracts.

Validated Core baselines use immutable release names such as:

```text
core-v1.0.0
core-v1.0.1
core-v1.1.0
```

A published Core baseline must never be silently redefined.

### Applications

A new ESP32 application should start from a validated Core baseline, normally the newest compatible one.

Preferred models:

1. separate repository/fork derived from `core-vX.Y.Z`; or
2. application branch created from that baseline while experimentation is still local.

Applications own their own version numbers and roadmap. Their firmware version does not need to match the Core release name.

When the Core improves, an application may selectively merge/cherry-pick or rebase onto a later compatible Core release after its own regression tests.

## Telemetry feedback loop

The Core remains a maintained platform even though its foundation is closed.

Operational data may drive new Core patch/minor releases when it reveals reusable behavior:

```text
application telemetry / faults / field evidence
        -> reproduce against Core
        -> fix in Core main
        -> regression + physical validation
        -> new validated Core baseline
        -> applications adopt when appropriate
```

Application-specific behavior stays in the application unless the finding is demonstrably reusable.

## New-chat contract

A new ChatGPT conversation does not need the development history of Stages 0-7.

For Core work, read in this order:

1. `docs/CORE_BASELINE.md`
2. `docs/BOOTSTRAP.md`
3. `docs/architecture.md`
4. `docs/operations.md`
5. the specific subsystem document needed for the task.

For a new application, first state:

- application/repository name;
- Core baseline it is based on;
- target external hardware;
- application-specific requirements.

Do **not** automatically continue with RTC, TFT, touch or SD. Those are optional application/module directions, not mandatory Core stages.

## Architectural rule

The stable boundary is:

```text
Core
  -> timing/state/events/health/configuration/rules/update/connectivity
Application
  -> selected modules + domain behavior
Drivers
  -> physical devices and GPIO
```

The Core may evolve, but applications should not have to rewrite its fundamental contracts to add a new device.
