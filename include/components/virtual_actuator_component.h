#pragma once

#include <Arduino.h>

#include "core/component.h"
#include "core/event_bus.h"

namespace Components {

class VirtualActuatorComponent : public RuntimeCore::Component {
 public:
  VirtualActuatorComponent(RuntimeCore::EventBus& events, const char* componentId);

  const char* id() const override { return id_.c_str(); }
  bool begin() override;
  const char* stateName() const override;
  RuntimeCore::ComponentHealth health() const override { return health_; }

  void enable(bool initialOn = false);
  void disable();
  bool applyDesired(bool desiredOn);
  bool enabled() const { return state_ != State::Disabled; }
  bool isOn() const { return state_ == State::On; }
  String statusJson() const;

 private:
  enum class State : uint8_t { Disabled, Off, On };
  void transitionTo(State nextState, RuntimeCore::HealthState nextHealth,
                    const char* faultCode);

  RuntimeCore::EventBus& events_;
  String id_;
  State state_ = State::Disabled;
  RuntimeCore::ComponentHealth health_;
};

}  // namespace Components
