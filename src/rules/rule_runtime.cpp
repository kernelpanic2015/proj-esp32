#include "rules/rule_runtime.h"

#include <string.h>

#include "core/runtime_events.h"

namespace Rules {

RuleRuntime* RuleRuntime::active_ = nullptr;

RuleRuntime::RuleRuntime(Scheduler& scheduler,
                         RuntimeCore::EventBus& events,
                         RuleEngine& engine,
                         const char* inputSourceId,
                         BoolProvider inputReady,
                         FloatProvider inputValue,
                         HealthProvider dependencyHealth,
                         BoolProvider outputState,
                         ApplyDesired applyDesired)
    : scheduler_(scheduler),
      events_(events),
      engine_(engine),
      inputSourceId_(inputSourceId ? inputSourceId : ""),
      inputReady_(inputReady),
      inputValue_(inputValue),
      dependencyHealth_(dependencyHealth),
      outputState_(outputState),
      applyDesired_(applyDesired),
      evaluationTask_(TASK_IMMEDIATE, TASK_ONCE, evaluationTaskCallback,
                      &scheduler_, false),
      disabledState_(enterDisabled, nullptr, nullptr),
      armedState_(enterArmed, nullptr, nullptr),
      evaluatingState_(enterEvaluating, nullptr, nullptr),
      machine_(&disabledState_) {
  active_ = this;
  configureTransitions();
}

void RuleRuntime::configureTransitions() {
  machine_.add_transition(&disabledState_, &armedState_, EventArm, nullptr);
  machine_.add_transition(&armedState_, &disabledState_, EventDisarm, nullptr);
  machine_.add_transition(&armedState_, &evaluatingState_, EventEvaluate, nullptr);
  machine_.add_transition(&evaluatingState_, &armedState_, EventDone, nullptr);
  machine_.add_transition(&evaluatingState_, &disabledState_, EventDisarm, nullptr);
}

bool RuleRuntime::begin() {
  if (started_) return true;
  active_ = this;
  if (!events_.subscribe(eventHandler)) {
    lastRunResult_ = "event_subscribe_failed";
    return false;
  }
  machine_.run_machine();
  started_ = true;
  refreshEligibility();
  return true;
}

void RuleRuntime::setState(RuntimeState next) {
  state_ = next;
  lastTransitionMs_ = millis();
}

void RuleRuntime::enterDisabled() {
  if (active_) active_->setState(RuntimeState::Disabled);
}

void RuleRuntime::enterArmed() {
  if (active_) active_->setState(RuntimeState::Armed);
}

void RuleRuntime::enterEvaluating() {
  if (active_) active_->setState(RuntimeState::Evaluating);
}

RuntimeCore::HealthState RuleRuntime::dependencyHealth() const {
  return dependencyHealth_ ? dependencyHealth_() : RuntimeCore::HealthState::Ok;
}

bool RuleRuntime::dependencyHealthy() const {
  return dependencyHealth() == RuntimeCore::HealthState::Ok;
}

void RuleRuntime::setFaultPolicy(ActuatorFaultPolicy policy) {
  faultPolicy_ = policy;
  refreshEligibility();
}

void RuleRuntime::refreshEligibility() {
  if (!started_) return;

  const bool dependencySuspends =
      faultPolicy_ == ActuatorFaultPolicy::DisableRule && !dependencyHealthy();

  if (!engine_.enabled() || dependencySuspends) {
    pending_ = false;
    if (evaluationTask_.isEnabled()) evaluationTask_.disable();
    if (state_ != RuntimeState::Disabled) {
      machine_.trigger(EventDisarm);
      machine_.run_machine();
    }
    if (dependencySuspends) {
      lastRequestResult_ = "dependency_fault_disable_rule";
    } else if (!engine_.configured()) {
      lastRequestResult_ = "no_active_rule";
    } else {
      lastRequestResult_ = "rule_disabled";
    }
    return;
  }

  if (state_ == RuntimeState::Disabled) {
    machine_.trigger(EventArm);
    machine_.run_machine();
  }
}

bool RuleRuntime::requestEvaluation(const char* reason) {
  ++requestCount_;
  lastRequestMs_ = millis();
  refreshEligibility();

  if (!engine_.enabled()) {
    ++rejectedCount_;
    lastRequestResult_ = "rule_disabled";
    return false;
  }

  const bool healthy = dependencyHealthy();
  if (!healthy && faultPolicy_ == ActuatorFaultPolicy::DisableRule) {
    ++rejectedCount_;
    lastRequestResult_ = "dependency_fault_disable_rule";
    return false;
  }
  if (healthy && (!inputReady_ || !inputReady_())) {
    ++rejectedCount_;
    lastRequestResult_ = "input_not_ready";
    return false;
  }
  if (state_ != RuntimeState::Armed) {
    ++rejectedCount_;
    lastRequestResult_ = "runtime_not_armed";
    return false;
  }

  if (evaluationTask_.isEnabled()) {
    pending_ = true;
    ++coalescedCount_;
    lastRequestResult_ = "coalesced";
    return true;
  }

  pending_ = true;
  if (!evaluationTask_.restart()) {
    pending_ = false;
    ++rejectedCount_;
    lastRequestResult_ = "scheduler_rejected";
    return false;
  }
  ++scheduledCount_;
  lastRequestResult_ = reason && reason[0] ? String("scheduled:") + reason : "scheduled";
  return true;
}

void RuleRuntime::eventHandler(const RuntimeCore::Event& event) {
  if (active_) active_->handleEvent(event);
}

void RuleRuntime::handleEvent(const RuntimeCore::Event& event) {
  if (inputSourceId_.length() && strcmp(event.source, inputSourceId_.c_str()) != 0) {
    return;
  }
  if (event.type == static_cast<uint16_t>(RuntimeCore::RuntimeEventType::InputValueChanged)) {
    requestEvaluation("input_event");
    return;
  }
  if (event.type == static_cast<uint16_t>(RuntimeCore::RuntimeEventType::ComponentHealthChanged)) {
    requestEvaluation("dependency_health");
  }
}

void RuleRuntime::evaluationTaskCallback() {
  if (active_) active_->executeEvaluation();
}

void RuleRuntime::executeEvaluation() {
  pending_ = false;
  if (!engine_.enabled()) {
    ++rejectedCount_;
    lastRunResult_ = "rule_disabled";
    refreshEligibility();
    return;
  }
  if (!outputState_ || !applyDesired_) {
    ++rejectedCount_;
    lastRunResult_ = "runtime_provider_unavailable";
    return;
  }

  const RuntimeCore::HealthState health = dependencyHealth();
  const bool current = outputState_();

  if (health != RuntimeCore::HealthState::Ok) {
    const ActuatorFaultResolution resolution =
        resolveActuatorFaultPolicy(faultPolicy_, current);
    ++policyActionCount_;
    lastPolicyMs_ = millis();
    lastPolicyResult_ = actuatorFaultPolicyName(faultPolicy_);

    if (resolution.suspendRule) {
      ++rejectedCount_;
      lastRunResult_ = "fault_policy:DISABLE_RULE";
      refreshEligibility();
      lastRunMs_ = millis();
      return;
    }

    machine_.trigger(EventEvaluate);
    machine_.run_machine();

    if (resolution.applyDesired) {
      if (!applyDesired_(resolution.desiredOn)) {
        ++rejectedCount_;
        lastRunResult_ = String("fault_policy_apply_failed:") +
                         actuatorFaultPolicyName(faultPolicy_);
      } else {
        lastRunResult_ = String("fault_policy:") +
                         actuatorFaultPolicyName(faultPolicy_);
      }
    } else if (resolution.alarmOnly) {
      ++alarmCount_;
      lastRunResult_ = "fault_policy:ALARM_ONLY";
    } else {
      lastRunResult_ = "fault_policy:KEEP_LAST_STATE";
    }

    lastRunMs_ = millis();
    machine_.trigger(EventDone);
    machine_.run_machine();
    return;
  }

  if (!inputReady_ || !inputReady_() || !inputValue_) {
    ++rejectedCount_;
    lastRunResult_ = "runtime_provider_unavailable";
    return;
  }

  machine_.trigger(EventEvaluate);
  machine_.run_machine();

  const float input = inputValue_();
  bool desired = current;
  RuleDecision decision = RuleDecision::None;
  String error;
  const bool evaluated = engine_.evaluate(input, current, desired, decision, error);

  if (!evaluated) {
    ++rejectedCount_;
    lastRunResult_ = error.length() ? error : "evaluation_failed";
  } else if (decision == RuleDecision::Disabled) {
    ++rejectedCount_;
    lastRunResult_ = "rule_disabled";
  } else if (!applyDesired_(desired)) {
    ++rejectedCount_;
    lastRunResult_ = "actuator_rejected";
  } else {
    ++completedCount_;
    lastRunResult_ = engine_.lastDecisionName();
  }
  lastRunMs_ = millis();

  if (engine_.enabled()) {
    machine_.trigger(EventDone);
  } else {
    machine_.trigger(EventDisarm);
  }
  machine_.run_machine();
}

const char* RuleRuntime::stateName() const {
  switch (state_) {
    case RuntimeState::Disabled: return "DISABLED";
    case RuntimeState::Armed: return "ARMED";
    case RuntimeState::Evaluating: return "EVALUATING";
  }
  return "UNKNOWN";
}

String RuleRuntime::statusJson() const {
  String json = "{";
  json += "\"state\":\"" + String(stateName()) + "\",";
  json += "\"active_rule\":" + String(engine_.enabled() ? "true" : "false") + ",";
  json += "\"input_source\":\"" + inputSourceId_ + "\",";
  json += "\"fault_policy\":\"" + String(actuatorFaultPolicyName(faultPolicy_)) + "\",";
  json += "\"dependency_health\":\"" +
          String(RuntimeCore::healthStateName(dependencyHealth())) + "\",";
  json += "\"dependency_suspended\":" +
          String((faultPolicy_ == ActuatorFaultPolicy::DisableRule && !dependencyHealthy()) ? "true" : "false") + ",";
  json += "\"work_task_enabled\":" + String(evaluationTask_.isEnabled() ? "true" : "false") + ",";
  json += "\"pending\":" + String(pending_ ? "true" : "false") + ",";
  json += "\"last_transition_ms\":" + String(lastTransitionMs_) + ",";
  json += "\"last_request_ms\":" + String(lastRequestMs_) + ",";
  json += "\"last_run_ms\":" + String(lastRunMs_) + ",";
  json += "\"last_policy_ms\":" + String(lastPolicyMs_) + ",";
  json += "\"request_count\":" + String(requestCount_) + ",";
  json += "\"scheduled_count\":" + String(scheduledCount_) + ",";
  json += "\"coalesced_count\":" + String(coalescedCount_) + ",";
  json += "\"completed_count\":" + String(completedCount_) + ",";
  json += "\"rejected_count\":" + String(rejectedCount_) + ",";
  json += "\"policy_action_count\":" + String(policyActionCount_) + ",";
  json += "\"alarm_count\":" + String(alarmCount_) + ",";
  json += "\"last_request_result\":\"" + lastRequestResult_ + "\",";
  json += "\"last_run_result\":\"" + lastRunResult_ + "\",";
  json += "\"last_policy_result\":\"" + lastPolicyResult_ + "\"";
  json += "}";
  return json;
}

}  // namespace Rules
