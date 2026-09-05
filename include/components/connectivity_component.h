#pragma once

#include <Arduino.h>

#include "core/component.h"
#include "core/event_bus.h"

namespace Components {

class ConnectivityComponent : public RuntimeCore::Component {
 public:
  using BoolProvider = bool (*)();

  ConnectivityComponent(RuntimeCore::EventBus& events,
                        BoolProvider wifiConnected,
                        BoolProvider mqttConnected,
                        BoolProvider mqttConfigured);

  const char* id() const override { return "connectivity"; }
  bool begin() override;
  const char* stateName() const override;
  RuntimeCore::ComponentHealth health() const override { return health_; }

  // Called by TaskScheduler. The component owns state/health semantics; the
  // scheduler owns cadence.
  void sample();

 private:
  enum class State : uint8_t {
    Starting,
    Offline,
    WifiOnly,
    Online
  };

  void transitionTo(State nextState,
                    RuntimeCore::HealthState nextHealth,
                    const char* faultCode);

  RuntimeCore::EventBus& events_;
  BoolProvider wifiConnected_;
  BoolProvider mqttConnected_;
  BoolProvider mqttConfigured_;
  State state_ = State::Starting;
  RuntimeCore::ComponentHealth health_;
  bool started_ = false;
};

}  // namespace Components
