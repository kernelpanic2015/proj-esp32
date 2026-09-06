#pragma once

#include <Arduino.h>

namespace Rules {

enum class ActuatorFaultPolicy : uint8_t {
  SafeOff,
  SafeOn,
  KeepLastState,
  DisableRule,
  AlarmOnly
};

struct ActuatorFaultResolution {
  bool applyDesired = false;
  bool desiredOn = false;
  bool suspendRule = false;
  bool alarmOnly = false;
};

const char* actuatorFaultPolicyName(ActuatorFaultPolicy policy);
bool parseActuatorFaultPolicy(const String& value, ActuatorFaultPolicy& policy);
ActuatorFaultResolution resolveActuatorFaultPolicy(ActuatorFaultPolicy policy,
                                                   bool currentOn);

}  // namespace Rules
