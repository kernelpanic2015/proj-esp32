from pathlib import Path
import re

# Promote the physically validated clean image.
p = Path('include/firmware_identity.h')
s = p.read_text()
s = s.replace('#define PROJ_FW_VERSION "0.1.25"', '#define PROJ_FW_VERSION "0.1.29"')
s = s.replace('#define PROJ_FW_BUILD 26', '#define PROJ_FW_BUILD 30')
p.write_text(s)

# Advance controlled OTA profiles monotonically for Stage 7B work.
p = Path('platformio.ini')
s = p.read_text()
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.28\\"\n    -DPROJ_FW_BUILD=29', '-DPROJ_FW_VERSION=\\"0.1.30\\"\n    -DPROJ_FW_BUILD=31')
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.28-remote-test\\"\n    -DPROJ_FW_BUILD=29', '-DPROJ_FW_VERSION=\\"0.1.30-remote-test\\"\n    -DPROJ_FW_BUILD=31')
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.29\\"\n    -DPROJ_FW_BUILD=30', '-DPROJ_FW_VERSION=\\"0.1.31\\"\n    -DPROJ_FW_BUILD=32')
p.write_text(s)

# ROADMAP: close 7A and explicitly open 7B.
p = Path('docs/ROADMAP.md')
s = p.read_text()
s = s.replace('## Stage 7 — Persistent configuration and local rule engine [in progress — Stage 7A]',
              '## Stage 7 — Persistent configuration and local rule engine [in progress — Stage 7B]')
s = s.replace('- [ ] physically prove apply -> reboot persistence -> second apply -> rollback -> reboot persistence;',
              '- [x] physically prove apply -> reboot persistence -> second apply -> rollback -> reboot persistence;')
anchor = 'Stage 7A stores rule/schedule envelopes but does not execute them yet. Rule semantics become active only after the RuleEngine validator/evaluator is introduced.\n'
addition = '''\n**Stage 7A: VALIDATED on hardware.** The dual-slot NVS store proved valid apply, invalid-candidate rejection without active-state replacement, reboot persistence, a second valid apply, rollback with monotonic revision, persistence of the rolled-back logical document, and survival across signed A/B OTA. Clean baseline `0.1.29/build 30` is `app0/VALID`, Wi-Fi + MQTT/TLS connected, Supervisor `RUNNING/OK`, EventBus `dropped=0`.\n\nThe proof also exposed a recovery interaction: two intentional software reboots inside the 10 s DoubleResetDetector window could open the 180 s WiFiManager config portal. All intentional firmware restart paths now go through `RestartService`, which calls `drd->stop()` before `ESP.restart()`. Two software reboots inside the DRD window were then physically proven to return ONLINE promptly; manual/hardware resets still retain normal double-reset recovery behavior.\n\n**Stage 7B next:** introduce the smallest useful local rule model with virtual input/output components. Do not access GPIO from RuleEngine.\n'''
if 'Stage 7A: VALIDATED on hardware.' not in s:
    s = s.replace(anchor, anchor + addition)
p.write_text(s)

# Configuration docs: append the physical transaction proof and DRD lesson.
p = Path('docs/configuration.md')
s = p.read_text()
if '## Stage 7A physical validation' not in s:
    s += '''\n## Stage 7A physical validation\n\nStage 7A was proven on the physical ESP32 with the signed A/B update path:\n\n```text\nrev0 defaults\n  -> apply valid config A -> rev1\n  -> reject duplicate-id candidate (HTTP 400), rev1 remains active\n  -> reboot -> rev1 loaded\n  -> apply valid config B -> rev2\n  -> rollback -> logical config A restored as monotonic rev3\n  -> reboot -> rev3 loaded\n  -> signed clean OTA -> 0.1.29/build30 app0 PENDING_VERIFY -> VALID\n  -> rev3 still loaded\n```\n\nThe active document after rollback contained `demo.rule` disabled with the first logical payload, while `previous_revision=2`. Wi-Fi, MQTT/TLS, Supervisor and EventBus remained healthy and the clean image exposed no lab-only endpoint.\n\n### Intentional restart versus DoubleResetDetector\n\nThe proof exposed a real interaction between controlled software reboots and DRD. The project uses a 10 s double-reset detection window and a 180 s configuration portal. A second software reboot issued inside the DRD window could therefore be mistaken for human recovery intent.\n\nIntentional firmware restarts now use `RestartService::restartNow()`. A registered hook calls `drd->stop()` before `ESP.restart()`, clearing the DRD marker only for software-controlled restart paths. Two deliberate software reboots inside the 10 s window were physically proven to return ONLINE promptly. Hardware/manual reset behavior remains unchanged and still supports double-reset recovery.\n'''
p.write_text(s)

# Runtime test log: record Stage 7A evidence in the existing chronological log.
p = Path('docs/runtime-test-log.md')
s = p.read_text()
if '## 2026-09-05 — Stage 7A transactional ConfigurationStore' not in s:
    s += '''\n\n## 2026-09-05 — Stage 7A transactional ConfigurationStore\n\n- Added dual-slot NVS `ConfigurationStore` with verified inactive-slot writes and a one-byte active pointer.\n- Configuration revision is device-monotonic; rollback restores previous logical content as a new revision rather than moving revision backward.\n- Valid config A became revision 1 and survived reboot.\n- A duplicate-ID candidate was rejected with `configuration_entry_id_duplicate`; active revision/content remained unchanged.\n- Valid config B became revision 2. Explicit rollback restored config A as revision 3.\n- Revision 3 persisted across reboot and across signed A/B OTA.\n- Clean target `0.1.29/build 30` completed `PENDING_VERIFY -> VALID` on `app0`; configuration remained revision 3, Wi-Fi and MQTT/TLS were connected, Supervisor was `RUNNING/OK`, and EventBus remained `dropped=0`.\n- A second controlled reboot during the original proof triggered the DRD recovery window and 180 s WiFiManager portal. This was diagnosed rather than treated as ConfigurationStore failure.\n- Added `RestartService`: intentional software reboot paths call `drd->stop()` before restart. Two deliberate software reboots inside the 10 s DRD window then recovered promptly without entering the configuration portal.\n\n**Stage 7A: VALIDATED. Stage 7B is next.**\n'''
p.write_text(s)

# Documentation index/runtime baseline.
p = Path('docs/README.md')
s = p.read_text()
s = s.replace('- [~] Stage 7A transactional ConfigurationStore implementation/build validation',
              '- [x] Stage 7A transactional ConfigurationStore: apply/reject/reboot/rollback/OTA persistence physically validated')
s = s.replace('Validated directly on the physical device on 2026-09-05 after Stage 6E closure:',
              'Validated directly on the physical device on 2026-09-05 after Stage 7A closure:')
s = s.replace('- firmware: `0.1.25`, build `26`, channel `dev`', '- firmware: `0.1.29`, build `30`, channel `dev`')
s = s.replace('Stage 6 core runtime is validated. TaskScheduler controls timing/eligibility, FSMs control state/behavior, EventBus carries transitions, components own subsystem health interpretation and Supervisor aggregates health. Further migrations remain incremental and should happen only when they improve the implementation. **Stage 7 — persistent configuration and local RuleEngine — is next.**',
              'Stage 6 core runtime is validated and Stage 7A transactional configuration is physically validated. Configuration revision 3 survived reboot, rollback and signed OTA. Intentional software restart now clears the DRD marker before reboot so it cannot masquerade as a human double-reset request. **Stage 7B — the smallest virtual-input/virtual-output local rule model — is next.**')
p.write_text(s)

# Bootstrap baseline and DRD operational rule.
p = Path('docs/BOOTSTRAP.md')
s = p.read_text()
s = s.replace('Current physical device state after Stage 6E / Stage 6 core runtime closure:',
              'Current physical device state after Stage 7A transactional configuration closure:')
s = s.replace('- firmware: `0.1.25`\n- build: `26`', '- firmware: `0.1.29`\n- build: `30`')
s = s.replace('Stage 6E physically proved a full Wi-Fi loss and recovery. The reconnect work task ran only while needed, Wi-Fi and MQTT recovered, local runtime health returned to `ONLINE/OK` and `RUNNING/OK`, and telemetry resumed. The same proof found a 2199-byte status payload exceeding the old 2048-byte MQTT buffer; the explicit 4096-byte buffer corrected the regression and >2 KiB scheduled telemetry was physically published.\n',
              'Stage 6E physically proved a full Wi-Fi loss and recovery. Stage 7A then physically proved dual-slot transactional configuration, invalid-candidate rejection, reboot persistence, monotonic rollback and persistence across signed A/B OTA. The current ConfigurationStore document is revision 3 and remains local-NVS backed.\n')
recovery_anchor = 'The DRD object is constructed inside `setup()` after runtime/NVS initialization; constructing it globally previously caused an EEPROM/NVS initialization error.\n'
recovery_add = '''\nAll intentional firmware restarts now go through `RestartService`. Its pre-restart hook calls `drd->stop()` before `ESP.restart()`, so a software-controlled reboot does not count toward human double-reset recovery. This was physically proven with two software reboots inside the 10 s DRD window. Manual/hardware reset pulses still retain the recovery behavior above.\n'''
if 'All intentional firmware restarts now go through `RestartService`' not in s:
    s = s.replace(recovery_anchor, recovery_anchor + recovery_add)
if '## Stage 7A ConfigurationStore — validated' not in s:
    insert_at = s.find('## Flash layout — validated')
    section = '''## Stage 7A ConfigurationStore — validated\n\n- NVS namespace: `app-config`;\n- two verified slots plus active pointer;\n- schema 1, monotonic revision;\n- current proven revision: `3`;\n- invalid duplicate-ID candidate rejected without changing active configuration;\n- valid apply survived reboot;\n- second apply + explicit rollback restored previous logical document as new revision;\n- rolled-back revision survived reboot and clean signed OTA;\n- clean physical baseline: `0.1.29/build 30`, `app0/VALID`.\n\nStage 7B should start with virtual input/output and minimal rule semantics; do not connect RuleEngine directly to GPIO.\n\n'''
    s = s[:insert_at] + section + s[insert_at:]
p.write_text(s)

# Architecture: document restart boundary + local configuration plane.
p = Path('docs/architecture.md')
s = p.read_text()
if '## Stage 7A — transactional local configuration' not in s:
    s += '''\n\n## Stage 7A — transactional local configuration\n\n`ConfigurationStore` is the local control-plane persistence boundary. It uses two NVS slots and activates only a candidate that has parsed, validated, persisted and read back successfully. Rule and schedule envelopes are stored here, but Stage 7A deliberately does not execute their semantics.\n\nThe physical proof established `apply -> reboot -> apply -> rollback -> reboot -> signed OTA` while preserving the selected logical document and monotonic revision. Connectivity is irrelevant to future execution: accepted local configuration remains in internal NVS.\n\n### Intentional restart boundary\n\n`RestartService` owns software-controlled restart. The service invokes a registered pre-restart hook; on this board the hook calls `DoubleResetDetector::stop()` so intentional reboot does not mimic a human double-reset. Hardware/manual resets are untouched. This keeps recovery semantics separate from update, MQTT, WebSerial and future local-control code.\n\nStage 7B builds above this store with virtual components first. RuleEngine produces desired state only; actuator/component FSMs own interlocks and eventual hardware drivers.\n'''
p.write_text(s)

# Root README concise promotion.
p = Path('README.md')
s = p.read_text()
s = s.replace('**Stage 6 core physical baseline:** `0.1.25/build 26`, `app0`, native OTA `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, Wi-Fi + MQTT/TLS connected and EventBus `dropped=0`. OTA scheduling, MQTT reconnect/telemetry and Wi-Fi reconnect timing use the shared TaskScheduler cooperative runtime; work tasks stay disabled when no meaningful work exists. Stage 7 is next.\n\n**Stage 7A has started:** `ConfigurationStore` introduces versioned dual-slot NVS transactions with verified inactive-slot writes, monotonic revisions, boot fallback and rollback. Rule execution is not enabled until the RuleEngine semantic layer is added and validated.',
              '**Current physical baseline:** `0.1.29/build 30`, `app0`, native OTA `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, Wi-Fi + MQTT/TLS connected and EventBus `dropped=0`. Stage 6 cooperative runtime remains validated.\n\n**Stage 7A is validated:** `ConfigurationStore` provides versioned dual-slot NVS transactions with verified inactive-slot writes, monotonic revisions, boot fallback and rollback. Apply/reject/reboot/rollback/OTA persistence was physically proven. Intentional software reboots clear the DRD marker first. Stage 7B now starts with virtual input/output and minimal local-rule semantics; RuleEngine does not access GPIO.')
p.write_text(s)

# Version-specific proof runners have completed their purpose; evidence lives in docs.
for path in ['scripts/stage7a_physical_proof.sh', 'scripts/stage7a_drd_physical.sh']:
    pp = Path(path)
    if pp.exists():
        pp.unlink()

print('STAGE7A_CLOSE_PATCHED')
