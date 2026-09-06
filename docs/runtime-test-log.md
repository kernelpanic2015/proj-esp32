# Runtime / Stage 6 validation log

## 2026-09-05 — Stage 6A TaskScheduler foundation

- Added `arkhipenko/TaskScheduler` alongside `jonblack/arduino-fsm`.
- Enabled `_TASK_INLINE` for the multi-file PlatformIO firmware.
- Migrated the automatic firmware-check timer from hand-written `millis()` scheduling to TaskScheduler.
- Physical proof: an enabled 60 s policy re-armed after reboot, automatically discovered the signed target without a manual/MQTT check, and did not auto-apply it. Explicit apply completed `PENDING_VERIFY -> VALID`.
- Proven physical baseline after promotion: `0.1.16/build 17`, `app1`, `VALID`, `ONLINE`, Wi-Fi + MQTT/TLS connected.

## 2026-09-05 — Stage 6B component registry integration

Planned acceptance for this stage:

- build normal + signed candidate successfully;
- install signed `0.1.17/build 18` candidate through the existing signed Web OTA path;
- observe `PENDING_VERIFY -> VALID`;
- `/api/components` contains one registered `connectivity` component;
- online device reports connectivity state `ONLINE` and health `OK`;
- `/api/status` embeds the same registry and EventBus counters;
- EventBus dropped count remains zero during the proof;
- local `main == origin/main` after promotion.

The Aurora physical proof result is appended to this file when the stage completes.

### Stage 6B physical result — PASS

- Signed candidate `0.1.17/build 18` installed into `app0`.
- Native OTA state observed `PENDING_VERIFY -> VALID`.
- Device returned `ONLINE` with Wi-Fi and MQTT/TLS connected.
- `/api/components` reported one `connectivity` component in state `ONLINE`, health `OK`.
- The same registry is embedded in `/api/status` and therefore the existing MQTT status/telemetry model.
- EventBus reported `pending=0`, `dropped=0`.
- Normal build after integration uses about 17.0% static RAM and 69.1% of the 1728 KiB OTA slot.
- `0.1.17/build 18` is the promoted default baseline.


## 2026-09-05 — Stage 6C Supervisor FSM

Implementation/build acceptance:

- Supervisor is a dedicated `arduino-fsm` machine, not an enum-only pseudo-FSM;
- TaskScheduler evaluates it cooperatively every 1 s;
- aggregate health is derived only from `ComponentRegistry`;
- component `DEGRADED`/`RECOVERING` produces Supervisor `DEGRADED`; component `FAULT` produces Supervisor `FAULT`;
- transitions are emitted through the bounded EventBus;
- `/api/supervisor` and `/api/status.supervisor` expose the same aggregate model;
- production build and controlled Stage 6C test/final OTA profiles compile before physical proof.

Physical acceptance still pending at this checkpoint: signed OTA into the controlled test image, real MQTT disconnect with Wi-Fi/HTTP preserved, observe `RUNNING -> DEGRADED -> RUNNING`, then install the clean no-test-endpoint target image and promote it.

### Stage 6C first physical attempt — partial / corrected

- Signed `0.1.18-remote-test/build 19` installed successfully on `app1` and completed `PENDING_VERIFY -> VALID`.
- `/api/supervisor` physically reported `RUNNING/OK` with the `connectivity` component `ONLINE/OK`; EventBus remained at zero dropped events.
- The planned controlled MQTT interruption could not run because the lab-only `/api/test/mqtt/disconnect` route had not actually been inserted into `main.cpp`; the endpoint returned HTTP 404.
- No production fault occurred. The device remained `ONLINE` with MQTT/TLS connected.
- The source was corrected before retrying the degradation/recovery proof, and test build numbers were advanced so monotonic OTA ordering remains valid.


### Stage 6C physical result — PASS

- Signed lab image `0.1.19-remote-test/build 20` installed on `app0` and completed native `PENDING_VERIFY -> VALID`.
- Before fault injection, `/api/supervisor` reported `RUNNING/OK` and `connectivity` reported `ONLINE/OK`.
- A real MQTT disconnect was triggered while Wi-Fi and HTTP remained available; reconnect was suppressed for 8 s only in the test-gated image.
- During the interruption, `connectivity` became `WIFI_ONLY/DEGRADED` with `fault_code=mqtt_disconnected`, while the application remained `ONLINE`; Supervisor became `DEGRADED/DEGRADED`.
- After MQTT reconnect, `connectivity` returned to `ONLINE/OK` and Supervisor returned to `RUNNING/OK`.
- EventBus remained `dropped=0` throughout the proof.
- Clean target `0.1.20/build 21` installed on `app1`, completed `PENDING_VERIFY -> VALID`, returned ONLINE with Wi-Fi + MQTT/TLS, and the lab-only disconnect endpoint returned HTTP 404.
- `0.1.20/build 21` is the promoted canonical baseline.
- The proof wrapper issue was labelled failed after the script had already completed, but the captured assertions ended `STAGE6C_PHYSICAL_PROOF_OK`; closure is based on the physical assertions and final clean-device state.

**Stage 6C: VALIDATED. Stage 6D is next.**


## 2026-09-05 — Stage 6D MQTT scheduler migration

Implementation checkpoint:

- removed main-loop `millis()` timers for MQTT reconnect and heartbeat telemetry;
- added TaskScheduler coordinator + reconnect + telemetry tasks;
- reconnect work task is disabled while connected, unconfigured, offline, in config portal, or intentionally suppressed by a test-gated proof;
- telemetry task is disabled while MQTT is disconnected and delayed by the configured heartbeat interval after connection;
- existing `PubSubClient::loop()` and connection/publish semantics remain unchanged;
- `/api/mqtt/runtime` exposes task enable state and reconnect/telemetry counters;
- physical proof completed: signed lab image, real MQTT disconnect/recovery, telemetry counter progression, and clean target image all passed.

### Stage 6D physical result — PASS

- Signed lab image `0.1.21-remote-test/build 22` installed on `app0` and completed `PENDING_VERIFY -> VALID`.
- On boot, TaskScheduler performed the initial MQTT connect (`reconnect_attempt_count=1`, `reconnect_success_count=1`) and left the reconnect task disabled while connected.
- The telemetry task was enabled only after MQTT became connected and produced its first publish after the delayed heartbeat interval (`telemetry_publish_count=1`, `last_telemetry_result=published`).
- A real MQTT disconnect was triggered with reconnect suppressed for 8 s only in the test image. While disconnected, the application remained `ONLINE`, `connectivity=WIFI_ONLY/DEGRADED`, Supervisor became `DEGRADED`, and the telemetry task was disabled.
- Once reconnect became eligible, the TaskScheduler reconnect path increased the attempt/success counters, restored MQTT, returned `connectivity=ONLINE/OK` and Supervisor `RUNNING/OK`, and left the reconnect task disabled again.
- Telemetry then re-armed with its normal delay and the publish counter advanced again.
- Clean target `0.1.22/build 23` installed on `app1`, completed `PENDING_VERIFY -> VALID`, returned ONLINE with Wi-Fi + MQTT/TLS, and produced a scheduled telemetry publish on the clean image.
- EventBus remained `dropped=0`; the lab-only disconnect endpoint returned HTTP 404 on the final image.
- The first proof wrapper stopped after the degradation assertion despite the device recovering; a focused continuation repeated the real disconnect/recovery assertions and ended `STAGE6D_PHYSICAL_PROOF_OK`.

**Stage 6D: VALIDATED.**


## 2026-09-05 — Stage 6E Wi-Fi scheduler migration

Implementation checkpoint:

- remove `lastWifiRetry` / main-loop `millis()` retry timing;
- add TaskScheduler Wi-Fi coordinator + reconnect task;
- reconnect task disabled while Wi-Fi is healthy, config portal is active, or a controlled lab suppression is active;
- preserve existing application FSM semantics (`ONLINE <-> OFFLINE`) rather than inventing a second state owner;
- expose `/api/wifi/runtime` counters and task enable state;
- physical proof pending: signed lab image, controlled Wi-Fi disconnect, observed reconnect attempt/success, connectivity/Supervisor recovery, clean target image.


### Stage 6E first physical attempt — partial / payload budget corrected

- Signed `0.1.23-remote-test/build 24` installed and reached `PENDING_VERIFY -> VALID`.
- Controlled Wi-Fi disconnect was physically observed: HTTP became unavailable, Wi-Fi reconnect work stayed suppressed for the test window, then TaskScheduler issued one reconnect attempt and recorded one success.
- After recovery, `connectivity` returned to `ONLINE/OK`, Supervisor returned to `RUNNING/OK`, MQTT reconnected, and the Wi-Fi reconnect work task returned to disabled.
- The proof then exposed a separate telemetry budget regression: `/api/status` had grown to 2199 bytes while PubSubClient remained configured with a 2048-byte buffer, so scheduled telemetry attempts correctly ran but `publish()` returned false.
- The buffer is therefore promoted to an explicit 4096-byte project setting before repeating the telemetry and clean-target proof. This is a transport payload-budget correction, not a Wi-Fi scheduler failure.


### Stage 6E physical result — PASS

- Wi-Fi retry timing was removed from the main-loop `lastWifiRetry`/`millis()` path and moved to TaskScheduler with a lightweight coordinator plus a reconnect work task.
- The reconnect task is disabled while Wi-Fi is healthy, while the config portal is active, and during the controlled lab suppression window.
- Signed lab image `0.1.24-remote-test/build 25` reached native `PENDING_VERIFY -> VALID`.
- A controlled full Wi-Fi disconnect made HTTP unavailable and was observed by the runtime. After the 8 s test suppression, TaskScheduler recorded one reconnect attempt and one reconnect success; the work task returned to disabled once Wi-Fi recovered.
- MQTT then reconnected, `connectivity` returned to `ONLINE/OK`, Supervisor returned to `RUNNING/OK`, and EventBus remained `dropped=0`.
- Scheduled MQTT telemetry resumed after recovery and published successfully.
- During the first Stage 6E attempt, the full status document had grown to 2199 bytes while the PubSubClient buffer was 2048 bytes. The runtime correctly exposed repeated `publish_failed`; the buffer was promoted to an explicit 4096-byte project setting and the same >2 KiB status telemetry then published successfully.
- Clean target `0.1.25/build 26` installed on `app0`, completed `PENDING_VERIFY -> VALID`, returned `ONLINE` with Wi-Fi + MQTT/TLS, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, and the lab-only Wi-Fi disconnect endpoint returned HTTP 404.

**Stage 6E: VALIDATED. Stage 6 core runtime: VALIDATED. Stage 7 is next.**


## 2026-09-05 — Stage 7A transactional ConfigurationStore

- Added dual-slot NVS `ConfigurationStore` with verified inactive-slot writes and a one-byte active pointer.
- Configuration revision is device-monotonic; rollback restores previous logical content as a new revision rather than moving revision backward.
- Valid config A became revision 1 and survived reboot.
- A duplicate-ID candidate was rejected with `configuration_entry_id_duplicate`; active revision/content remained unchanged.
- Valid config B became revision 2. Explicit rollback restored config A as revision 3.
- Revision 3 persisted across reboot and across signed A/B OTA.
- Clean target `0.1.29/build 30` completed `PENDING_VERIFY -> VALID` on `app0`; configuration remained revision 3, Wi-Fi and MQTT/TLS were connected, Supervisor was `RUNNING/OK`, and EventBus remained `dropped=0`.
- A second controlled reboot during the original proof triggered the DRD recovery window and 180 s WiFiManager portal. This was diagnosed rather than treated as ConfigurationStore failure.
- Added `RestartService`: intentional software reboot paths call `drd->stop()` before restart. Two deliberate software reboots inside the 10 s DRD window then recovered promptly without entering the configuration portal.

**Stage 7A: VALIDATED. Stage 7B is next.**


## 2026-09-05 — Stage 7B minimal RuleEngine

- Added a hardware-independent hysteresis `RuleEngine` plus `VirtualInputComponent` and `VirtualActuatorComponent`.
- Invalid hysteresis (`on_below >= off_above`) was rejected before activation.
- Physical sequence `20 -> 15 -> 17 -> 19 -> 17` with thresholds `16/18` proved OFF/HOLD -> ON -> HOLD-ON -> OFF -> HOLD-OFF.
- Disabling the rule and applying input `10` produced decision `DISABLED` and left the virtual actuator OFF; the enabled evaluation count remained 5.
- RuleEngine never accesses GPIO; it returns desired state and the actuator component owns application.
- Lab image `0.1.30-remote-test/build 31` reached `PENDING_VERIFY -> VALID`; Supervisor remained `RUNNING/OK`, EventBus remained `dropped=0`.
- Clean target `0.1.31/build 32` reached `PENDING_VERIFY -> VALID` on `app0`, Wi-Fi + MQTT/TLS were connected, ConfigurationStore remained revision 3, the normal registry returned to one `connectivity` component, HTTPS-only update policy was restored, and the lab RuleEngine endpoint returned HTTP 404.
- Aurora issue #731 was labelled failed even though the proof file ended `STAGE7B_PHYSICAL_PROOF_OK`. Follow-up issue #732 inspected the wrapper and showed `RC=0`; closure is based on the explicit physical assertions, proof marker, and live clean-device state rather than the incorrect wrapper label.

**Stage 7B: VALIDATED. Stage 7C is next.**


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


## 2026-09-05 — Stage 7D persisted rule lifecycle

### Result — PASS

- Added `PersistedRuleLoader` as the semantic binding layer between ConfigurationStore revisions and RuleEngine/RuleRuntime.
- Existing revision 3 legacy envelope stayed readable but non-executable (`persisted_rule_type_unsupported`); RuleRuntime remained disabled until a valid Stage 7D rule was committed.
- Invalid hysteresis was rejected before persistence and revision 3 remained unchanged.
- Rule A (`persisted.demo.a`, 16/18) became revision 4, activated immediately, armed RuleRuntime and produced `15 -> TURN_ON`, `19 -> TURN_OFF`.
- After intentional reboot, revision 4 and rule A reloaded automatically and produced the same decisions.
- Rule B (`persisted.demo.b`, 14/20) became revision 5 and activated immediately.
- Explicit rollback restored rule A as monotonic revision 6; rule A immediately became active again and survived a second reboot.
- Clean target `0.1.37/build 38` installed on `app0`, reached `PENDING_VERIFY -> VALID`, retained revision 6, automatically loaded rule A, left RuleRuntime `ARMED` with `work_task_enabled=false`/`pending=false`, restored HTTPS-only update behavior, kept Supervisor `RUNNING/OK`, EventBus `dropped=0`, and removed lab endpoints (HTTP 404).
- Aurora #765 reconciled the complete proof and ended `completed`, exit code 0, with marker `STAGE7D_PHYSICAL_PROOF_OK`.

**Stage 7D: VALIDATED. Stage 7E local schedule/delayed-action service is next.**
