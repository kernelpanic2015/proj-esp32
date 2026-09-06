from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def write(rel, content):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')


def replace_once(rel, old, new):
    text = read(rel)
    if old not in text:
        raise SystemExit(f'missing anchor in {rel}: {old[:160]!r}')
    write(rel, text.replace(old, new, 1))


write('include/schedules/local_schedule_service.h', r'''#pragma once

#include <Arduino.h>
#include <Fsm.h>
#include <TaskScheduler.h>

namespace Schedules {

class LocalScheduleService {
 public:
  using ApplyDesired = bool (*)(bool desiredOn);

  LocalScheduleService(Scheduler& scheduler, ApplyDesired applyDesired);

  bool begin();
  bool validateDocument(const String& raw, String& error) const;
  bool activateDocument(const String& raw, uint32_t revision, String& error);

  const char* stateName() const;
  bool workTaskEnabled() const { return actionTask_.isEnabled(); }
  String statusJson() const;

 private:
  enum class ScheduleState : uint8_t {
    Disabled,
    Waiting,
    Firing,
    Completed,
    Fault
  };

  enum ScheduleEvent : int {
    EventDisable = 1,
    EventArm,
    EventFire,
    EventDone,
    EventFail
  };

  struct DelayedAction {
    String id;
    bool enabled = false;
    String target;
    bool desiredOn = false;
    uint32_t delayMs = 0;
  };

  static LocalScheduleService* active_;
  static void enterDisabled();
  static void enterWaiting();
  static void enterFiring();
  static void enterCompleted();
  static void enterFault();
  static void actionTaskCallback();

  void configureTransitions();
  void setState(ScheduleState next);
  void executeAction();
  bool parseDocument(const String& raw, DelayedAction& action, bool& found,
                     String& error) const;

  Scheduler& scheduler_;
  ApplyDesired applyDesired_;
  mutable Task actionTask_;
  State disabledState_;
  State waitingState_;
  State firingState_;
  State completedState_;
  State faultState_;
  Fsm machine_;

  ScheduleState state_ = ScheduleState::Disabled;
  DelayedAction action_;
  bool configured_ = false;
  uint32_t loadedRevision_ = 0;
  uint32_t armedCount_ = 0;
  uint32_t completedCount_ = 0;
  uint32_t failedCount_ = 0;
  uint32_t lastTransitionMs_ = 0;
  uint32_t lastArmedMs_ = 0;
  uint32_t lastCompletedMs_ = 0;
  String lastResult_ = "never";
};

}  // namespace Schedules
''')

write('src/schedules/local_schedule_service.cpp', r'''#include "schedules/local_schedule_service.h"

#include <ArduinoJson.h>
#include <string.h>

namespace Schedules {
namespace {
constexpr size_t JSON_CAPACITY = 4096;
constexpr uint32_t MAX_DELAY_MS = 24UL * 60UL * 60UL * 1000UL;
constexpr size_t MAX_ID_LENGTH = 48;

bool validId(const char* value) {
  if (!value) return false;
  const size_t length = strlen(value);
  if (length == 0 || length > MAX_ID_LENGTH) return false;
  for (size_t i = 0; i < length; ++i) {
    const char c = value[i];
    const bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                    (c >= '0' && c <= '9') || c == '_' || c == '-' ||
                    c == '.' || c == ':';
    if (!ok) return false;
  }
  return true;
}
}  // namespace

LocalScheduleService* LocalScheduleService::active_ = nullptr;

LocalScheduleService::LocalScheduleService(Scheduler& scheduler, ApplyDesired applyDesired)
    : scheduler_(scheduler),
      applyDesired_(applyDesired),
      actionTask_(TASK_IMMEDIATE, TASK_ONCE, actionTaskCallback, &scheduler_, false),
      disabledState_(enterDisabled, nullptr, nullptr),
      waitingState_(enterWaiting, nullptr, nullptr),
      firingState_(enterFiring, nullptr, nullptr),
      completedState_(enterCompleted, nullptr, nullptr),
      faultState_(enterFault, nullptr, nullptr),
      machine_(&disabledState_) {
  active_ = this;
  configureTransitions();
}

void LocalScheduleService::configureTransitions() {
  machine_.add_transition(&disabledState_, &waitingState_, EventArm, nullptr);
  machine_.add_transition(&waitingState_, &disabledState_, EventDisable, nullptr);
  machine_.add_transition(&waitingState_, &firingState_, EventFire, nullptr);
  machine_.add_transition(&firingState_, &completedState_, EventDone, nullptr);
  machine_.add_transition(&firingState_, &faultState_, EventFail, nullptr);
  machine_.add_transition(&completedState_, &waitingState_, EventArm, nullptr);
  machine_.add_transition(&completedState_, &disabledState_, EventDisable, nullptr);
  machine_.add_transition(&faultState_, &waitingState_, EventArm, nullptr);
  machine_.add_transition(&faultState_, &disabledState_, EventDisable, nullptr);
}

bool LocalScheduleService::begin() {
  active_ = this;
  machine_.run_machine();
  return true;
}

void LocalScheduleService::setState(ScheduleState next) {
  state_ = next;
  lastTransitionMs_ = millis();
}

void LocalScheduleService::enterDisabled() { if (active_) active_->setState(ScheduleState::Disabled); }
void LocalScheduleService::enterWaiting() { if (active_) active_->setState(ScheduleState::Waiting); }
void LocalScheduleService::enterFiring() { if (active_) active_->setState(ScheduleState::Firing); }
void LocalScheduleService::enterCompleted() { if (active_) active_->setState(ScheduleState::Completed); }
void LocalScheduleService::enterFault() { if (active_) active_->setState(ScheduleState::Fault); }

bool LocalScheduleService::parseDocument(const String& raw, DelayedAction& action,
                                         bool& found, String& error) const {
  error = "";
  found = false;
  DynamicJsonDocument doc(JSON_CAPACITY);
  if (deserializeJson(doc, raw)) {
    error = "schedule_config_json_invalid";
    return false;
  }
  if (!doc["schedules"].is<JsonArray>()) {
    error = "schedule_array_missing";
    return false;
  }
  JsonArray schedules = doc["schedules"].as<JsonArray>();
  if (schedules.size() == 0) return true;
  if (schedules.size() > 1) {
    error = "schedule_multiple_not_supported_stage7e";
    return false;
  }

  JsonObject obj = schedules[0].as<JsonObject>();
  const char* id = obj["id"] | "";
  const char* type = obj["type"] | "";
  const char* target = obj["target"] | "";
  if (!validId(id)) { error = "schedule_id_invalid"; return false; }
  if (strcmp(type, "delay_after_activation") != 0) {
    error = "schedule_type_unsupported";
    return false;
  }
  if (strcmp(target, "virtual.schedule_output") != 0) {
    error = "schedule_target_unsupported";
    return false;
  }
  if (obj.containsKey("enabled") && !obj["enabled"].is<bool>()) {
    error = "schedule_enabled_invalid";
    return false;
  }
  if (!obj["desired_on"].is<bool>()) {
    error = "schedule_desired_on_invalid";
    return false;
  }
  if (!obj["delay_ms"].is<uint32_t>()) {
    error = "schedule_delay_invalid";
    return false;
  }
  const uint32_t delayMs = obj["delay_ms"].as<uint32_t>();
  if (delayMs > MAX_DELAY_MS) {
    error = "schedule_delay_out_of_range";
    return false;
  }

  action.id = id;
  action.enabled = obj["enabled"] | true;
  action.target = target;
  action.desiredOn = obj["desired_on"].as<bool>();
  action.delayMs = delayMs;
  found = true;
  return true;
}

bool LocalScheduleService::validateDocument(const String& raw, String& error) const {
  DelayedAction candidate;
  bool found = false;
  return parseDocument(raw, candidate, found, error);
}

bool LocalScheduleService::activateDocument(const String& raw, uint32_t revision,
                                            String& error) {
  DelayedAction candidate;
  bool found = false;
  if (!parseDocument(raw, candidate, found, error)) {
    lastResult_ = error;
    return false;
  }

  if (actionTask_.isEnabled()) actionTask_.disable();
  configured_ = found;
  loadedRevision_ = revision;
  action_ = found ? candidate : DelayedAction{};

  if (!found) {
    if (state_ != ScheduleState::Disabled) {
      machine_.trigger(EventDisable);
      machine_.run_machine();
    }
    lastResult_ = "no_schedules";
    return true;
  }

  if (!action_.enabled) {
    if (state_ != ScheduleState::Disabled) {
      machine_.trigger(EventDisable);
      machine_.run_machine();
    }
    lastResult_ = "schedule_disabled";
    return true;
  }

  if (state_ == ScheduleState::Waiting) {
    machine_.trigger(EventDisable);
    machine_.run_machine();
  }
  machine_.trigger(EventArm);
  machine_.run_machine();
  if (!actionTask_.restartDelayed(action_.delayMs)) {
    machine_.trigger(EventFire);
    machine_.run_machine();
    machine_.trigger(EventFail);
    machine_.run_machine();
    ++failedCount_;
    lastResult_ = "scheduler_rejected";
    error = lastResult_;
    return false;
  }
  ++armedCount_;
  lastArmedMs_ = millis();
  lastResult_ = "waiting";
  return true;
}

void LocalScheduleService::actionTaskCallback() {
  if (active_) active_->executeAction();
}

void LocalScheduleService::executeAction() {
  machine_.trigger(EventFire);
  machine_.run_machine();
  const bool ok = applyDesired_ && applyDesired_(action_.desiredOn);
  if (ok) {
    ++completedCount_;
    lastCompletedMs_ = millis();
    lastResult_ = "completed";
    machine_.trigger(EventDone);
  } else {
    ++failedCount_;
    lastResult_ = "target_rejected";
    machine_.trigger(EventFail);
  }
  machine_.run_machine();
}

const char* LocalScheduleService::stateName() const {
  switch (state_) {
    case ScheduleState::Disabled: return "DISABLED";
    case ScheduleState::Waiting: return "WAITING";
    case ScheduleState::Firing: return "FIRING";
    case ScheduleState::Completed: return "COMPLETED";
    case ScheduleState::Fault: return "FAULT";
  }
  return "UNKNOWN";
}

String LocalScheduleService::statusJson() const {
  String json = "{";
  json += "\"state\":\"" + String(stateName()) + "\",";
  json += "\"configured\":" + String(configured_ ? "true" : "false") + ",";
  json += "\"loaded_revision\":" + String(loadedRevision_) + ",";
  json += "\"work_task_enabled\":" + String(actionTask_.isEnabled() ? "true" : "false") + ",";
  json += "\"armed_count\":" + String(armedCount_) + ",";
  json += "\"completed_count\":" + String(completedCount_) + ",";
  json += "\"failed_count\":" + String(failedCount_) + ",";
  json += "\"last_armed_ms\":" + String(lastArmedMs_) + ",";
  json += "\"last_completed_ms\":" + String(lastCompletedMs_) + ",";
  json += "\"last_result\":\"" + lastResult_ + "\"";
  if (configured_) {
    json += ",\"schedule\":{";
    json += "\"id\":\"" + action_.id + "\",";
    json += "\"enabled\":" + String(action_.enabled ? "true" : "false") + ",";
    json += "\"type\":\"delay_after_activation\",";
    json += "\"target\":\"" + action_.target + "\",";
    json += "\"desired_on\":" + String(action_.desiredOn ? "true" : "false") + ",";
    json += "\"delay_ms\":" + String(action_.delayMs);
    json += "}";
  }
  json += "}";
  return json;
}

}  // namespace Schedules
''')

# Main integration: separate persisted semantics from TaskScheduler primitive.
replace_once('src/main.cpp',
'''#include "rules/persisted_rule_loader.h"\n#include "components/virtual_input_component.h"\n''',
'''#include "rules/persisted_rule_loader.h"\n#include "schedules/local_schedule_service.h"\n#include "components/virtual_input_component.h"\n''')

replace_once('src/main.cpp',
'''Components::VirtualActuatorComponent virtualHeater(runtimeEvents, "virtual.heater");\n''',
'''Components::VirtualActuatorComponent virtualHeater(runtimeEvents, "virtual.heater");\nComponents::VirtualActuatorComponent virtualScheduleOutput(runtimeEvents, "virtual.schedule_output");\n''')

replace_once('src/main.cpp',
'''Rules::PersistedRuleLoader persistedRuleLoader(ruleEngine, ruleRuntime);\n''',
'''Rules::PersistedRuleLoader persistedRuleLoader(ruleEngine, ruleRuntime);\nbool scheduleApplyDesired(bool desiredOn);\nSchedules::LocalScheduleService localScheduleService(cooperativeScheduler, scheduleApplyDesired);\n''')

replace_once('src/main.cpp',
'''bool validatePersistedRules(const String& raw, String& error) {\n  return persistedRuleLoader.validateDocument(raw, error);\n}\n\nvoid activatePersistedRules(uint32_t revision, const String& raw) {\n  String error;\n  if (!persistedRuleLoader.activateDocument(raw, revision, error)) {\n    logLine("PERSISTED_RULE_RELOAD_FAILED " + error);\n  }\n}\n''',
'''bool scheduleApplyDesired(bool desiredOn) {\n  return virtualScheduleOutput.applyDesired(desiredOn);\n}\n\nbool validatePersistedConfiguration(const String& raw, String& error) {\n  if (!persistedRuleLoader.validateDocument(raw, error)) return false;\n  if (!localScheduleService.validateDocument(raw, error)) return false;\n  return true;\n}\n\nvoid activatePersistedConfiguration(uint32_t revision, const String& raw) {\n  String error;\n  if (!persistedRuleLoader.activateDocument(raw, revision, error)) {\n    logLine("PERSISTED_RULE_RELOAD_FAILED " + error);\n  }\n  error = "";\n  if (!localScheduleService.activateDocument(raw, revision, error)) {\n    logLine("LOCAL_SCHEDULE_RELOAD_FAILED " + error);\n  }\n}\n''')

replace_once('src/main.cpp',
'''  json += "\\\"persisted_rules\\\":" + persistedRuleLoader.statusJson() + ",";\n''',
'''  json += "\\\"persisted_rules\\\":" + persistedRuleLoader.statusJson() + ",";\n  json += "\\\"local_schedule\\\":" + localScheduleService.statusJson() + ",";\n''')

replace_once('src/main.cpp',
'''    body += "persisted_rules=/api/rules/persisted\\n";\n''',
'''    body += "persisted_rules=/api/rules/persisted\\n";\n    body += "schedule_status=/api/schedules/status\\n";\n''')

replace_once('src/main.cpp',
'''  server.on("/api/rules/persisted", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", persistedRuleLoader.statusJson());\n  });\n\n''',
'''  server.on("/api/rules/persisted", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", persistedRuleLoader.statusJson());\n  });\n\n  server.on("/api/schedules/status", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", localScheduleService.statusJson());\n  });\n\n''')

replace_once('src/main.cpp',
'''  runtimeComponents.add(connectivityComponent);\n  runtimeComponents.add(virtualTemperature);\n  runtimeComponents.add(virtualHeater);\n  if (!runtimeComponents.beginAll()) {\n''',
'''  runtimeComponents.add(connectivityComponent);\n  runtimeComponents.add(virtualTemperature);\n  runtimeComponents.add(virtualHeater);\n  runtimeComponents.add(virtualScheduleOutput);\n  if (!runtimeComponents.beginAll()) {\n''')

replace_once('src/main.cpp',
'''  virtualHeater.enable(false);\n  ConfigurationStore::setRuleLifecycleCallbacks(validatePersistedRules, activatePersistedRules);\n  if (!persistedRuleLoader.begin()) {\n    Serial.println("PERSISTED_RULE_LOAD_FAILED");\n  }\n''',
'''  virtualHeater.enable(false);\n  virtualScheduleOutput.enable(false);\n  localScheduleService.begin();\n  ConfigurationStore::setRuleLifecycleCallbacks(validatePersistedConfiguration, activatePersistedConfiguration);\n  String localActivationError;\n  const String activeConfiguration = ConfigurationStore::activeJson();\n  if (!persistedRuleLoader.activateDocument(activeConfiguration, ConfigurationStore::revision(), localActivationError)) {\n    Serial.println("PERSISTED_RULE_LOAD_FAILED");\n  }\n  localActivationError = "";\n  if (!localScheduleService.activateDocument(activeConfiguration, ConfigurationStore::revision(), localActivationError)) {\n    Serial.println("LOCAL_SCHEDULE_LOAD_FAILED");\n  }\n''')

# Rename the generic lifecycle API now that both rules and schedules use it.
replace_once('include/configuration_store.h',
'''void setRuleLifecycleCallbacks(ValidateActiveCallback validator, ActivatedCallback activated);\n''',
'''void setLifecycleCallbacks(ValidateActiveCallback validator, ActivatedCallback activated);\n''')
replace_once('src/configuration_store.cpp',
'''void setRuleLifecycleCallbacks(ValidateActiveCallback validator, ActivatedCallback activated) {\n''',
'''void setLifecycleCallbacks(ValidateActiveCallback validator, ActivatedCallback activated) {\n''')
replace_once('src/main.cpp', 'ConfigurationStore::setRuleLifecycleCallbacks(', 'ConfigurationStore::setLifecycleCallbacks(')

# Documentation: mark Stage 7E implementation in progress and define the no-RTC contract.
replace_once('docs/ROADMAP.md',
             '- [ ] **Stage 7E** — local `Scheduler` for schedules/delayed actions/settling windows;',
             '- [~] **Stage 7E** — local persisted delayed-action service above TaskScheduler; physical offline/reboot proof pending;')

config = read('docs/configuration.md')
if '## Stage 7E — local delayed-action schedule' not in config:
    config += r'''

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
'''
    write('docs/configuration.md', config)

arch = read('docs/architecture.md')
if '## Stage 7E local schedule boundary' not in arch:
    arch += r'''

## Stage 7E local schedule boundary

`LocalScheduleService` translates persisted schedule semantics into one-shot
TaskScheduler work. The schedule FSM owns meaning/state; TaskScheduler owns only when
the due callback runs; the target component owns application of desired state. A
waiting schedule has one enabled delayed task, a completed/disabled schedule has no
work task, and network state is not part of eligibility.

Until DS3231 is validated, Stage 7E uses relative `delay_after_activation` semantics.
Reboot intentionally re-arms the relative delay from boot-time activation. Wall-clock
schedules are a Stage 8 time-service concern, not something synthesized from uptime.
'''
    write('docs/architecture.md', arch)

replace_once('docs/README.md',
             '- [ ] Stage 7E local schedule/delayed-action service',
             '- [~] Stage 7E local persisted delayed-action service; physical offline/reboot proof pending')

replace_once('README.md',
             '**Stages 7A-7D are validated:** transactional configuration, hysteresis semantics, one-shot local execution and persisted rule lifecycle have all been physically proven. Apply/reboot/replacement/rollback/clean-OTA preserve the local rule source of truth. **Stage 7E is next:** persisted local schedules and delayed actions above TaskScheduler.\n',
             '**Stages 7A-7D are validated. Stage 7E is in progress:** a persisted relative delayed-action service now sits above TaskScheduler. Its FSM owns schedule meaning/state, TaskScheduler owns only due-time execution, and the work task is disabled except while a valid action is waiting. Wall-clock schedules remain deferred until the DS3231 time foundation.\n')

print('STAGE7E_IMPLEMENT_PATCHED')
