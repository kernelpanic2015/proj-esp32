from pathlib import Path
import re

# Promote the default identity to the image physically validated after the
# TaskScheduler migration.
p = Path('include/firmware_identity.h')
s = p.read_text()
s = s.replace('#define PROJ_FW_VERSION "0.1.14"', '#define PROJ_FW_VERSION "0.1.16"', 1)
s = s.replace('#define PROJ_FW_BUILD 15', '#define PROJ_FW_BUILD 17', 1)
p.write_text(s)

# Advance repeatable test profiles, retaining _TASK_INLINE in every child env.
p = Path('platformio.ini')
s = p.read_text()
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.15\\"\n    -DPROJ_FW_BUILD=16', '-DPROJ_FW_VERSION=\\"0.1.17\\"\n    -DPROJ_FW_BUILD=18', 1)
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.15-remote-test\\"\n    -DPROJ_FW_BUILD=16', '-DPROJ_FW_VERSION=\\"0.1.17-remote-test\\"\n    -DPROJ_FW_BUILD=18', 1)
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.16\\"\n    -DPROJ_FW_BUILD=17', '-DPROJ_FW_VERSION=\\"0.1.18\\"\n    -DPROJ_FW_BUILD=19', 1)
p.write_text(s)

# Keep the scheduler regression script reusable for the next migration step.
p = Path('scripts/smoke_update_scheduler.sh')
s = p.read_text()
s = s.replace('FIXTURE_PORT=${FIXTURE_PORT:-8769}', 'FIXTURE_PORT=${FIXTURE_PORT:-8770}', 1)
# baseline assertions are first occurrences only
s = s.replace('grep -q \'"version":"0.1.14"\' <<<"$V"', 'grep -q \'"version":"0.1.16"\' <<<"$V"', 1)
s = s.replace('grep -q \'"build":15\' <<<"$V"', 'grep -q \'"build":17\' <<<"$V"', 1)
s = s.replace('--version 0.1.15-remote-test --build 16', '--version 0.1.17-remote-test --build 18', 1)
s = s.replace('--version 0.1.16 --build 17', '--version 0.1.18 --build 19', 1)
s = s.replace("wait_for_transition '0.1.15-remote-test' 16 app0", "wait_for_transition '0.1.17-remote-test' 18 app0", 1)
s = s.replace("wait_for_online '0.1.15-remote-test' 16", "wait_for_online '0.1.17-remote-test' 18", 1)
s = s.replace('"candidate_build":17', '"candidate_build":19', 1)
s = s.replace("wait_for_transition '0.1.16' 17 app1", "wait_for_transition '0.1.18' 19 app1", 1)
# final assertions occur later
s = s.replace('grep -q \'"version":"0.1.16"\' <<<"$S"', 'grep -q \'"version":"0.1.18"\' <<<"$S"', 1)
s = s.replace('grep -q \'"build":17\' <<<"$S"', 'grep -q \'"build":19\' <<<"$S"', 1)
p.write_text(s)

# Canonical README runtime.
p = Path('docs/README.md')
s = p.read_text()
start = s.index('## Current runtime state')
end = s.index('## OTA partition layout', start)
runtime = '''## Current runtime state\n\nValidated directly on the physical device on 2026-09-05 after the Stage 6A TaskScheduler migration proof:\n\n- hostname: `proj-esp32`\n- mDNS: `proj-esp32.local`\n- device ID: `10A2CCEF49C0`\n- hardware model: `proj-esp32-35`, revision `1`\n- firmware: `0.1.16`, build `17`, channel `dev`\n- running OTA partition: `app1`\n- boot partition: `app1`\n- next update partition: `app0`\n- native image state: `VALID`\n- FSM/system: `ONLINE`\n- Wi-Fi: connected\n- MQTT: connected\n- MQTT transport: TLS\n- remote OTA policy: HTTPS-only\n- automatic update policy: disabled; manifest URL cleared after the lab proof\n\nStage 6A introduced `TaskScheduler` 4.0.8 alongside `arduino-fsm`. The automatic firmware-check path is the first real migration: a low-rate policy watcher remains scheduled, while the actual check task stays disabled until persisted policy enables it and then starts with a delayed first run. A reboot with a 60 s policy re-armed the task; without Web/MQTT `firmware.check`, the task fired at about 60.5 s, reached `AVAILABLE`, and operator apply completed `0.1.16/build 17` through `PENDING_VERIFY -> VALID`. The scheduler never auto-applied firmware.\n\nStage 6 core foundations now compile: `Component`, `ComponentHealth`, `ComponentRegistry`, and a bounded `EventBus`. Real components and the Supervisor FSM are the next incremental step.\n\n'''
s = s[:start] + runtime + s[end:]
if '- [x] TaskScheduler + arduino-fsm cooperative runtime foundation' not in s:
    anchor = '- [x] nonblocking automatic update-check scheduler proven on hardware\n'
    s = s.replace(anchor, anchor + '- [x] TaskScheduler + arduino-fsm cooperative runtime foundation; automatic scheduler migration proven on hardware\n- [x] Component / ComponentHealth / ComponentRegistry / bounded EventBus foundations compile\n- [ ] wire real components into ComponentRegistry and add Supervisor FSM\n', 1)
p.write_text(s)

# Bootstrap baseline and immediate direction.
p = Path('docs/BOOTSTRAP.md')
s = p.read_text()
start = s.index('## Current firmware baseline — verified 2026-09-05')
end = s.index('## Flash layout — validated', start)
baseline = '''## Current firmware baseline — verified 2026-09-05\n\nCurrent physical device state after the Stage 6A TaskScheduler migration proof:\n\n- model: `proj-esp32-35`\n- hardware revision: `1`\n- firmware: `0.1.16`\n- build: `17`\n- channel: `dev`\n- running partition: `app1`\n- boot partition: `app1`\n- next update partition: `app0`\n- native OTA image state: `VALID`\n- system/FSM: `ONLINE`\n- Wi-Fi: connected\n- MQTT/TLS: connected\n- hostname: `proj-esp32`\n- mDNS: `proj-esp32.local`\n- device ID: `10A2CCEF49C0`\n\n`arkhipenko/TaskScheduler` 4.0.8 is now adopted alongside `jonblack/arduino-fsm`. TaskScheduler owns **when work is eligible**; FSM owns **state and behavior**. Tasks are expected to remain disabled until work is meaningful, and delayed enable/restart is the preferred mechanism for warm-up, settling, retry/backoff and minimum on/off timing.\n\nThe first migrated production path is the automatic firmware check. Physical proof showed persisted policy -> delayed TaskScheduler activation -> automatic signed remote check after reboot, with no manual/MQTT check command and no automatic apply. Final `0.1.16/build 17` remained ONLINE and `VALID`.\n\nStage 6 foundations under `include/core` / `src/core` now include `Component`, `ComponentHealth`, `ComponentRegistry`, and a bounded `EventBus`; they compile but real services/components are not yet registered.\n\nLatest normal build remains within the 1728 KiB OTA slot at about 68.8% flash and 16.6% static RAM.\n\n'''
s = s[:start] + baseline + s[end:]
# Add TaskScheduler to architectural bullets if absent.
arch_anchor = '- multiple FSMs cooperate without blocking;\n'
if '- TaskScheduler owns cooperative timing/eligibility' not in s:
    s = s.replace(arch_anchor, arch_anchor + '- TaskScheduler owns cooperative timing/eligibility; FSMs own state/behavior;\n- tasks stay disabled when work is not meaningful and may be activated/restarted with delay;\n', 1)
start = s.index('## Immediate next steps')
end = s.index('## Source-of-truth invariant', start)
steps = '''## Immediate next steps\n\n1. wire the first real service components into `ComponentRegistry` and expose their common health metadata;\n2. add the Stage 6 `Supervisor` FSM and schedule it cooperatively with TaskScheduler;\n3. schedule bounded `EventBus.process()` and begin routing state-change events through it;\n4. gradually migrate eligible periodic/retry work (MQTT reconnect/telemetry and later sensors) from hand-written timing to TaskScheduler + FSM;\n5. replace development `setInsecure()` with CA validation for MQTT and remote HTTPS;\n6. harden MQTT with LWT plus reconnect backoff/jitter;\n7. continue toward ConfigurationStore/RuleEngine/local Scheduler and later DS3231/TFT/touch/microSD.\n\n'''
s = s[:start] + steps + s[end:]
p.write_text(s)

# Stage 6 roadmap: record physical proof and next substep.
p = Path('docs/ROADMAP.md')
s = p.read_text()
needle = '- [x] bounded internal event bus foundation;\n'
if '- [x] physically prove first TaskScheduler migration' not in s:
    s = s.replace(needle, needle + '- [x] physically prove first TaskScheduler migration using the automatic OTA check path;\n', 1)
p.write_text(s)

# Architecture physical evidence.
p = Path('docs/architecture.md')
s = p.read_text()
if '0.1.15-remote-test/build 16' not in s:
    s += '''\n### First physical TaskScheduler migration proof\n\nThe automatic firmware-check scheduler was migrated from hand-written `millis()` polling to TaskScheduler. A controlled `0.1.15-remote-test/build 16` image persisted an enabled 60 s policy, rebooted, re-armed the delayed task, and reached remote `AVAILABLE` at about 60.5 s without any manual or MQTT `firmware.check`. `attempt_count=1` and `accepted_count=1` were observed. Only an explicit operator apply installed `0.1.16/build 17`, which completed `PENDING_VERIFY -> VALID`. This validates the intended rule that scheduled work may stay disabled until meaningful and that automatic scheduling does not imply automatic actuation/install.\n'''
p.write_text(s)

# Record evidence in OTA test log because this migration exercised the full OTA path.
p = Path('docs/ota-test-log.md')
s = p.read_text()
if 'TaskScheduler automatic-check migration regression' not in s:
    s += '''\n## 2026-09-05 — TaskScheduler automatic-check migration regression\n\n- Baseline: `0.1.14/build 15`, `app1/VALID`, ONLINE with MQTT/TLS.\n- Stage 6A replaced the automatic update scheduler's hand-written timing with `TaskScheduler`; the actual check task remains disabled unless persisted policy enables it.\n- Installed signed transition image `0.1.15-remote-test/build 16` to `app0`; observed `PENDING_VERIFY -> VALID`.\n- Enabled a 60 s persisted HTTPS policy and rebooted. The scheduler reconstructed its delayed first run from policy revision `5`.\n- No Web/MQTT `firmware.check` was sent. At about `60546 ms`, the automatic task fired and reached `AVAILABLE` for signed candidate `0.1.16/build 17`; `attempt_count=1`, `accepted_count=1`, `last_request_result=accepted`.\n- Scheduler did not auto-apply. Explicit operator apply installed `0.1.16/build 17` to `app1`; observed `PENDING_VERIFY -> VALID`.\n- Final normal image restored HTTPS-only remote policy, remained ONLINE with Wi-Fi and MQTT/TLS, and the lab MQTT loopback endpoint returned 404.\n- The proof artifact ended `TASKSCHEDULER_AUTOMATIC_UPDATE_PROOF_OK`; a separate reconciliation job re-read the artifact and healthy physical runtime after the original wrapper reported exit code 1.\n'''
p.write_text(s)

print('STAGE6A_PROMOTION_UPDATED')
