#include "components/virtual_actuator_component.h"

#include "core/runtime_events.h"

namespace Components {

VirtualActuatorComponent::VirtualActuatorComponent(RuntimeCore::EventBus& events,
                                                   const char* componentId)
    : events_(events), id_(componentId ? componentId : "virtual.actuator") {}

bool VirtualActuatorComponent::begin() {
  state_ = State::Disabled;
  health_.state = RuntimeCore::HealthState::Disabled;
  health_.faultCode = "";
  return true;
}

const char* VirtualActuatorComponent::stateName() const {
  switch (state_) {
    case State::Disabled: return "DISABLED";
    case State::Off: return "OFF";
    case State::On: return "ON";
  }
  return "UNKNOWN";
}

void VirtualActuatorComponent::transitionTo(State nextState,
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

void VirtualActuatorComponent::enable(bool initialOn) {
  transitionTo(initialOn ? State::On : State::Off, RuntimeCore::HealthState::Ok, "");
}

void VirtualActuatorComponent::disable() {
  transitionTo(State::Disabled, RuntimeCore::HealthState::Disabled, "");
}

bool VirtualActuatorComponent::applyDesired(bool desiredOn) {
  if (!enabled()) return false;
  transitionTo(desiredOn ? State::On : State::Off, RuntimeCore::HealthState::Ok, "");
  return true;
}

String VirtualActuatorComponent::statusJson() const {
  String json = "{";
  json += "\"id\":\"" + id_ + "\",";
  json += "\"state\":\"" + String(stateName()) + "\",";
  json += "\"health\":" + RuntimeCore::healthJson(health_) + ",";
  json += "\"enabled\":" + String(enabled() ? "true" : "false") + ",";
  json += "\"on\":" + String(isOn() ? "true" : "false");
  json += "}";
  return json;
}

}  // namespace Components
