#include "core/component_health.h"

namespace RuntimeCore {

const char* healthStateName(HealthState state) {
  switch (state) {
    case HealthState::Ok: return "OK";
    case HealthState::Degraded: return "DEGRADED";
    case HealthState::Fault: return "FAULT";
    case HealthState::Recovering: return "RECOVERING";
    case HealthState::Disabled: return "DISABLED";
  }
  return "UNKNOWN";
}

String healthJson(const ComponentHealth& health) {
  String json = "{";
  json += "\"state\":\"" + String(healthStateName(health.state)) + "\",";
  json += "\"last_success_ms\":" + String(health.lastSuccessMs) + ",";
  json += "\"last_error_ms\":" + String(health.lastErrorMs) + ",";
  json += "\"error_count\":" + String(health.errorCount) + ",";
  json += "\"fault_code\":\"" + health.faultCode + "\"";
  json += "}";
  return json;
}

}  // namespace RuntimeCore
