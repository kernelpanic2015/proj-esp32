#include "core/supervisor.h"

#include "core/runtime_events.h"

namespace RuntimeCore {

Supervisor* Supervisor::active_ = nullptr;

Supervisor::Supervisor(ComponentRegistry& registry, EventBus& events)
    : registry_(registry),
      events_(events),
      initializingState_(enterInitializing, nullptr, nullptr),
      runningState_(enterRunning, nullptr, nullptr),
      degradedState_(enterDegraded, nullptr, nullptr),
      faultState_(enterFault, nullptr, nullptr),
      machine_(&initializingState_) {
  active_ = this;
  configureTransitions();
}

void Supervisor::configureTransitions() {
  machine_.add_transition(&initializingState_, &runningState_, EventAllHealthy, nullptr);
  machine_.add_transition(&initializingState_, &degradedState_, EventDegraded, nullptr);
  machine_.add_transition(&initializingState_, &faultState_, EventFault, nullptr);

  machine_.add_transition(&runningState_, &degradedState_, EventDegraded, nullptr);
  machine_.add_transition(&runningState_, &faultState_, EventFault, nullptr);

  machine_.add_transition(&degradedState_, &runningState_, EventAllHealthy, nullptr);
  machine_.add_transition(&degradedState_, &faultState_, EventFault, nullptr);

  machine_.add_transition(&faultState_, &runningState_, EventAllHealthy, nullptr);
  machine_.add_transition(&faultState_, &degradedState_, EventDegraded, nullptr);
}

void Supervisor::begin() {
  if (started_) return;
  started_ = true;
  machine_.run_machine();
}

void Supervisor::enterInitializing() {
  if (active_) active_->setState(SupervisorState::Initializing);
}

void Supervisor::enterRunning() {
  if (active_) active_->setState(SupervisorState::Running);
}

void Supervisor::enterDegraded() {
  if (active_) active_->setState(SupervisorState::Degraded);
}

void Supervisor::enterFault() {
  if (active_) active_->setState(SupervisorState::Fault);
}

void Supervisor::setState(SupervisorState next) {
  const bool changed = next != state_;
  state_ = next;
  if (!changed && lastTransitionMs_ != 0) return;
  lastTransitionMs_ = millis();
  events_.post(static_cast<uint16_t>(RuntimeEventType::SupervisorStateChanged),
               "supervisor", static_cast<int32_t>(state_));
}

void Supervisor::countHealth() {
  okCount_ = degradedCount_ = faultCount_ = recoveringCount_ = disabledCount_ = 0;
  for (size_t i = 0; i < registry_.size(); ++i) {
    Component* component = registry_.at(i);
    if (!component) continue;
    switch (component->health().state) {
      case HealthState::Ok: ++okCount_; break;
      case HealthState::Degraded: ++degradedCount_; break;
      case HealthState::Fault: ++faultCount_; break;
      case HealthState::Recovering: ++recoveringCount_; break;
      case HealthState::Disabled: ++disabledCount_; break;
    }
  }
}

void Supervisor::requestState(SupervisorState desired) {
  if (desired == state_) return;
  switch (desired) {
    case SupervisorState::Running:
      machine_.trigger(EventAllHealthy);
      break;
    case SupervisorState::Degraded:
      machine_.trigger(EventDegraded);
      break;
    case SupervisorState::Fault:
      machine_.trigger(EventFault);
      break;
    case SupervisorState::Initializing:
      break;
  }
}

void Supervisor::evaluate() {
  if (!started_) return;
  ++evaluationCount_;
  countHealth();

  SupervisorState desired = SupervisorState::Running;
  if (registry_.size() == 0) {
    desired = SupervisorState::Initializing;
  } else if (faultCount_ > 0) {
    desired = SupervisorState::Fault;
  } else if (degradedCount_ > 0 || recoveringCount_ > 0) {
    desired = SupervisorState::Degraded;
  }

  requestState(desired);
  machine_.run_machine();
}

const char* Supervisor::stateName() const {
  switch (state_) {
    case SupervisorState::Initializing: return "INITIALIZING";
    case SupervisorState::Running: return "RUNNING";
    case SupervisorState::Degraded: return "DEGRADED";
    case SupervisorState::Fault: return "FAULT";
  }
  return "UNKNOWN";
}

HealthState Supervisor::healthState() const {
  switch (state_) {
    case SupervisorState::Initializing: return HealthState::Recovering;
    case SupervisorState::Running: return HealthState::Ok;
    case SupervisorState::Degraded: return HealthState::Degraded;
    case SupervisorState::Fault: return HealthState::Fault;
  }
  return HealthState::Fault;
}

String Supervisor::statusJson() const {
  String json = "{";
  json += "\"state\":\"" + String(stateName()) + "\",";
  json += "\"health\":\"" + String(healthStateName(healthState())) + "\",";
  json += "\"component_count\":" + String(registry_.size()) + ",";
  json += "\"ok\":" + String(okCount_) + ",";
  json += "\"degraded\":" + String(degradedCount_) + ",";
  json += "\"fault\":" + String(faultCount_) + ",";
  json += "\"recovering\":" + String(recoveringCount_) + ",";
  json += "\"disabled\":" + String(disabledCount_) + ",";
  json += "\"last_transition_ms\":" + String(lastTransitionMs_) + ",";
  json += "\"evaluation_count\":" + String(evaluationCount_);
  json += "}";
  return json;
}

}  // namespace RuntimeCore
