#pragma once

#include <Arduino.h>

namespace RuntimeCore {

enum class HealthState : uint8_t {
  Ok,
  Degraded,
  Fault,
  Recovering,
  Disabled
};

struct ComponentHealth {
  HealthState state = HealthState::Disabled;
  uint32_t lastSuccessMs = 0;
  uint32_t lastErrorMs = 0;
  uint32_t errorCount = 0;
  String faultCode;
};

const char* healthStateName(HealthState state);
String healthJson(const ComponentHealth& health);

}  // namespace RuntimeCore
