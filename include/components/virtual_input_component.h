#pragma once

#include <Arduino.h>

#include "core/component.h"
#include "core/event_bus.h"

namespace Components {

class VirtualInputComponent : public RuntimeCore::Component {
 public:
  VirtualInputComponent(RuntimeCore::EventBus& events, const char* componentId);

  const char* id() const override { return id_.c_str(); }
  bool begin() override;
  const char* stateName() const override;
  RuntimeCore::ComponentHealth health() const override { return health_; }

  bool setValue(float value);
  bool hasValue() const { return hasValue_; }
  float value() const { return value_; }
  bool injectFault(const char* faultCode = "virtual_fault");
  void recover();
  void disable();
  String statusJson() const;

 private:
  enum class State : uint8_t { Disabled, Ready, Fault };
  void transitionTo(State nextState, RuntimeCore::HealthState nextHealth,
                    const char* faultCode);

  RuntimeCore::EventBus& events_;
  String id_;
  State state_ = State::Disabled;
  RuntimeCore::ComponentHealth health_;
  bool hasValue_ = false;
  float value_ = 0.0f;
};

}  // namespace Components
