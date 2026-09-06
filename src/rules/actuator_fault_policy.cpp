#include "rules/actuator_fault_policy.h"

namespace Rules {

const char* actuatorFaultPolicyName(ActuatorFaultPolicy policy) {
  switch (policy) {
    case ActuatorFaultPolicy::SafeOff: return "SAFE_OFF";
    case ActuatorFaultPolicy::SafeOn: return "SAFE_ON";
    case ActuatorFaultPolicy::KeepLastState: return "KEEP_LAST_STATE";
    case ActuatorFaultPolicy::DisableRule: return "DISABLE_RULE";
    case ActuatorFaultPolicy::AlarmOnly: return "ALARM_ONLY";
  }
  return "SAFE_OFF";
}

bool parseActuatorFaultPolicy(const String& value, ActuatorFaultPolicy& policy) {
  String normalized = value;
  normalized.trim();
  normalized.toUpperCase();
  if (normalized == "SAFE_OFF") {
    policy = ActuatorFaultPolicy::SafeOff;
    return true;
  }
  if (normalized == "SAFE_ON") {
    policy = ActuatorFaultPolicy::SafeOn;
    return true;
  }
  if (normalized == "KEEP_LAST_STATE") {
    policy = ActuatorFaultPolicy::KeepLastState;
    return true;
  }
  if (normalized == "DISABLE_RULE") {
    policy = ActuatorFaultPolicy::DisableRule;
    return true;
  }
  if (normalized == "ALARM_ONLY") {
    policy = ActuatorFaultPolicy::AlarmOnly;
    return true;
  }
  return false;
}

ActuatorFaultResolution resolveActuatorFaultPolicy(ActuatorFaultPolicy policy,
                                                   bool currentOn) {
  ActuatorFaultResolution result;
  result.desiredOn = currentOn;
  switch (policy) {
    case ActuatorFaultPolicy::SafeOff:
      result.applyDesired = true;
      result.desiredOn = false;
      break;
    case ActuatorFaultPolicy::SafeOn:
      result.applyDesired = true;
      result.desiredOn = true;
      break;
    case ActuatorFaultPolicy::KeepLastState:
      break;
    case ActuatorFaultPolicy::DisableRule:
      result.suspendRule = true;
      break;
    case ActuatorFaultPolicy::AlarmOnly:
      result.alarmOnly = true;
      break;
  }
  return result;
}

}  // namespace Rules
