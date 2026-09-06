#include "components/virtual_input_component.h"

#include <math.h>

#include "core/runtime_events.h"

namespace Components {

VirtualInputComponent::VirtualInputComponent(RuntimeCore::EventBus& events,
                                             const char* componentId)
    : events_(events), id_(componentId ? componentId : "virtual.input") {}

bool VirtualInputComponent::begin() {
  state_ = State::Disabled;
  health_.state = RuntimeCore::HealthState::Disabled;
  health_.faultCode = "";
  hasValue_ = false;
  return true;
}

const char* VirtualInputComponent::stateName() const {
  switch (state_) {
    case State::Disabled: return "DISABLED";
    case State::Ready: return "READY";
    case State::Fault: return "FAULT";
  }
  return "UNKNOWN";
}

void VirtualInputComponent::transitionTo(State nextState,
                                         RuntimeCore::HealthState nextHealth,
                                         const char* faultCode) {
  const bool stateChanged = nextState != state_;
  const String nextFault = faultCode ? String(faultCode) : String();
  const bool healthChanged = nextHealth != health_.state || nextFault != health_.faultCode;
  const uint32_t now = millis();

  state_ = nextState;
  health_.state = nextHealth;
  health_.faultCode = nextFault;
  if (nextHealth == RuntimeCore::HealthState::Ok) {
    health_.lastSuccessMs = now;
  } else if (healthChanged && nextHealth != RuntimeCore::HealthState::Disabled) {
    health_.lastErrorMs = now;
    ++health_.errorCount;
  }

  if (stateChanged) {
    events_.post(static_cast<uint16_t>(RuntimeCore::RuntimeEventType::ComponentStateChanged),
                 id(), static_cast<int32_t>(state_));
  }
  if (healthChanged) {
    events_.post(static_cast<uint16_t>(RuntimeCore::RuntimeEventType::ComponentHealthChanged),
                 id(), static_cast<int32_t>(health_.state));
  }
}

bool VirtualInputComponent::setValue(float value) {
  if (!isfinite(value)) return false;
  value_ = value;
  hasValue_ = true;
  transitionTo(State::Ready, RuntimeCore::HealthState::Ok, "");
  const int32_t milliValue = static_cast<int32_t>(value * 1000.0f);
  events_.post(static_cast<uint16_t>(RuntimeCore::RuntimeEventType::InputValueChanged),
               id(), milliValue);
  return true;
}

bool VirtualInputComponent::injectFault(const char* faultCode) {
  String code = faultCode ? String(faultCode) : String();
  code.trim();
  if (!code.length()) code = "virtual_fault";
  transitionTo(State::Fault, RuntimeCore::HealthState::Fault, code.c_str());
  return true;
}

void VirtualInputComponent::recover() {
  if (hasValue_) {
    transitionTo(State::Ready, RuntimeCore::HealthState::Ok, "");
  } else {
    transitionTo(State::Disabled, RuntimeCore::HealthState::Disabled, "");
  }
}

void VirtualInputComponent::disable() {
  hasValue_ = false;
  transitionTo(State::Disabled, RuntimeCore::HealthState::Disabled, "");
}

String VirtualInputComponent::statusJson() const {
  String json = "{";
  json += "\"id\":\"" + id_ + "\",";
  json += "\"state\":\"" + String(stateName()) + "\",";
  json += "\"health\":" + RuntimeCore::healthJson(health_) + ",";
  json += "\"has_value\":" + String(hasValue_ ? "true" : "false") + ",";
  json += "\"value\":" + String(value_, 3);
  json += "}";
  return json;
}

}  // namespace Components
