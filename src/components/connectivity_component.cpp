#include "components/connectivity_component.h"

#include "core/runtime_events.h"

namespace Components {

ConnectivityComponent::ConnectivityComponent(RuntimeCore::EventBus& events,
                                               BoolProvider wifiConnected,
                                               BoolProvider mqttConnected,
                                               BoolProvider mqttConfigured)
    : events_(events),
      wifiConnected_(wifiConnected),
      mqttConnected_(mqttConnected),
      mqttConfigured_(mqttConfigured) {}

bool ConnectivityComponent::begin() {
  started_ = true;
  state_ = State::Starting;
  health_.state = RuntimeCore::HealthState::Recovering;
  health_.faultCode = "starting";
  return wifiConnected_ && mqttConnected_ && mqttConfigured_;
}

const char* ConnectivityComponent::stateName() const {
  switch (state_) {
    case State::Starting: return "STARTING";
    case State::Offline: return "OFFLINE";
    case State::WifiOnly: return "WIFI_ONLY";
    case State::Online: return "ONLINE";
  }
  return "UNKNOWN";
}

void ConnectivityComponent::transitionTo(State nextState,
                                          RuntimeCore::HealthState nextHealth,
                                          const char* faultCode) {
  const uint32_t now = millis();
  const String nextFault = faultCode ? String(faultCode) : String();
  const bool stateChanged = nextState != state_;
  const bool healthChanged = nextHealth != health_.state || nextFault != health_.faultCode;

  if (nextHealth == RuntimeCore::HealthState::Ok) {
    health_.lastSuccessMs = now;
  } else if (healthChanged) {
    health_.lastErrorMs = now;
    ++health_.errorCount;
  }

  state_ = nextState;
  health_.state = nextHealth;
  health_.faultCode = nextFault;

  if (stateChanged) {
    events_.post(static_cast<uint16_t>(RuntimeCore::RuntimeEventType::ComponentStateChanged),
                 id(), static_cast<int32_t>(state_));
  }
  if (healthChanged) {
    events_.post(static_cast<uint16_t>(RuntimeCore::RuntimeEventType::ComponentHealthChanged),
                 id(), static_cast<int32_t>(health_.state));
  }
}

void ConnectivityComponent::sample() {
  if (!started_) return;

  const bool wifiUp = wifiConnected_ && wifiConnected_();
  if (!wifiUp) {
    transitionTo(State::Offline, RuntimeCore::HealthState::Degraded,
                 "wifi_disconnected");
    return;
  }

  const bool configured = mqttConfigured_ && mqttConfigured_();
  if (!configured) {
    transitionTo(State::WifiOnly, RuntimeCore::HealthState::Degraded,
                 "mqtt_not_configured");
    return;
  }

  const bool mqttUp = mqttConnected_ && mqttConnected_();
  if (!mqttUp) {
    transitionTo(State::WifiOnly, RuntimeCore::HealthState::Degraded,
                 "mqtt_disconnected");
    return;
  }

  transitionTo(State::Online, RuntimeCore::HealthState::Ok, "");
}

}  // namespace Components
