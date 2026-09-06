#include "schedules/local_schedule_service.h"

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
