from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(rel, content):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def replace_once(rel, old, new):
    p = ROOT / rel
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing patch anchor in {rel}: {old[:100]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


write("include/components/virtual_input_component.h", r'''#pragma once

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
  void disable();
  String statusJson() const;

 private:
  enum class State : uint8_t { Disabled, Ready };
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
''')

write("src/components/virtual_input_component.cpp", r'''#include "components/virtual_input_component.h"

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
''')

write("include/components/virtual_actuator_component.h", r'''#pragma once

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
''')

write("src/components/virtual_actuator_component.cpp", r'''#include "components/virtual_actuator_component.h"

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
''')

write("include/rules/rule_engine.h", r'''#pragma once

#include <Arduino.h>

#include "core/event_bus.h"

namespace Rules {

enum class RuleDecision : uint8_t {
  None = 0,
  TurnOff = 1,
  TurnOn = 2,
  Hold = 3,
  Disabled = 4
};

struct HysteresisRule {
  String id;
  bool enabled = false;
  float onBelow = 0.0f;
  float offAbove = 0.0f;
};

class RuleEngine {
 public:
  explicit RuleEngine(RuntimeCore::EventBus& events) : events_(events) {}

  bool begin();
  bool configure(const HysteresisRule& rule, String& error);
  void clear();
  bool evaluate(float inputValue, bool currentOutput,
                bool& desiredOutput, RuleDecision& decision, String& error);
  bool configured() const { return configured_; }
  bool enabled() const { return configured_ && rule_.enabled; }
  const HysteresisRule& rule() const { return rule_; }
  uint32_t evaluationCount() const { return evaluationCount_; }
  const char* lastDecisionName() const;
  String statusJson() const;

 private:
  static bool validId(const String& id);
  static const char* decisionName(RuleDecision decision);

  RuntimeCore::EventBus& events_;
  HysteresisRule rule_;
  bool configured_ = false;
  uint32_t evaluationCount_ = 0;
  uint32_t lastEvaluationMs_ = 0;
  float lastInput_ = 0.0f;
  bool lastDesired_ = false;
  RuleDecision lastDecision_ = RuleDecision::None;
  String lastError_;
};

}  // namespace Rules
''')

write("src/rules/rule_engine.cpp", r'''#include "rules/rule_engine.h"

#include <ctype.h>
#include <math.h>

#include "core/runtime_events.h"

namespace Rules {

bool RuleEngine::begin() {
  clear();
  return true;
}

bool RuleEngine::validId(const String& id) {
  if (id.length() == 0 || id.length() > 48) return false;
  for (size_t i = 0; i < id.length(); ++i) {
    const unsigned char c = static_cast<unsigned char>(id[i]);
    if (!(isalnum(c) || c == '_' || c == '-' || c == '.' || c == ':')) return false;
  }
  return true;
}

bool RuleEngine::configure(const HysteresisRule& rule, String& error) {
  error = "";
  if (!validId(rule.id)) {
    error = "rule_id_invalid";
    return false;
  }
  if (!isfinite(rule.onBelow) || !isfinite(rule.offAbove)) {
    error = "rule_threshold_invalid";
    return false;
  }
  if (!(rule.onBelow < rule.offAbove)) {
    error = "rule_hysteresis_invalid";
    return false;
  }
  rule_ = rule;
  configured_ = true;
  lastError_ = "";
  lastDecision_ = rule.enabled ? RuleDecision::None : RuleDecision::Disabled;
  return true;
}

void RuleEngine::clear() {
  rule_ = HysteresisRule{};
  configured_ = false;
  evaluationCount_ = 0;
  lastEvaluationMs_ = 0;
  lastInput_ = 0.0f;
  lastDesired_ = false;
  lastDecision_ = RuleDecision::None;
  lastError_ = "";
}

const char* RuleEngine::decisionName(RuleDecision decision) {
  switch (decision) {
    case RuleDecision::None: return "NONE";
    case RuleDecision::TurnOff: return "TURN_OFF";
    case RuleDecision::TurnOn: return "TURN_ON";
    case RuleDecision::Hold: return "HOLD";
    case RuleDecision::Disabled: return "DISABLED";
  }
  return "UNKNOWN";
}

const char* RuleEngine::lastDecisionName() const {
  return decisionName(lastDecision_);
}

bool RuleEngine::evaluate(float inputValue, bool currentOutput,
                          bool& desiredOutput, RuleDecision& decision, String& error) {
  error = "";
  desiredOutput = currentOutput;
  decision = RuleDecision::None;
  if (!configured_) {
    error = "rule_not_configured";
    lastError_ = error;
    return false;
  }
  if (!rule_.enabled) {
    decision = RuleDecision::Disabled;
    lastDecision_ = decision;
    lastError_ = "";
    return true;
  }
  if (!isfinite(inputValue)) {
    error = "rule_input_invalid";
    lastError_ = error;
    return false;
  }

  ++evaluationCount_;
  lastEvaluationMs_ = millis();
  lastInput_ = inputValue;
  if (inputValue < rule_.onBelow) {
    desiredOutput = true;
    decision = currentOutput ? RuleDecision::Hold : RuleDecision::TurnOn;
  } else if (inputValue > rule_.offAbove) {
    desiredOutput = false;
    decision = currentOutput ? RuleDecision::TurnOff : RuleDecision::Hold;
  } else {
    desiredOutput = currentOutput;
    decision = RuleDecision::Hold;
  }

  lastDesired_ = desiredOutput;
  lastDecision_ = decision;
  lastError_ = "";
  events_.post(static_cast<uint16_t>(RuntimeCore::RuntimeEventType::RuleEvaluated),
               rule_.id.c_str(), static_cast<int32_t>(decision));
  return true;
}

String RuleEngine::statusJson() const {
  String json = "{";
  json += "\"configured\":" + String(configured_ ? "true" : "false") + ",";
  json += "\"enabled\":" + String(enabled() ? "true" : "false") + ",";
  json += "\"mode\":\"manual_stage7b\",";
  json += "\"evaluation_count\":" + String(evaluationCount_) + ",";
  json += "\"last_evaluation_ms\":" + String(lastEvaluationMs_) + ",";
  json += "\"last_input\":" + String(lastInput_, 3) + ",";
  json += "\"last_desired_on\":" + String(lastDesired_ ? "true" : "false") + ",";
  json += "\"last_decision\":\"" + String(lastDecisionName()) + "\",";
  json += "\"last_error\":\"" + lastError_ + "\"";
  if (configured_) {
    json += ",\"rule\":{";
    json += "\"id\":\"" + rule_.id + "\",";
    json += "\"enabled\":" + String(rule_.enabled ? "true" : "false") + ",";
    json += "\"on_below\":" + String(rule_.onBelow, 3) + ",";
    json += "\"off_above\":" + String(rule_.offAbove, 3);
    json += "}";
  }
  json += "}";
  return json;
}

}  // namespace Rules
''')

replace_once("include/core/runtime_events.h",
'''  ComponentStateChanged = 100,\n  ComponentHealthChanged = 101,\n  SupervisorStateChanged = 102\n''',
'''  ComponentStateChanged = 100,\n  ComponentHealthChanged = 101,\n  SupervisorStateChanged = 102,\n  InputValueChanged = 200,\n  RuleEvaluated = 201\n''')

replace_once("src/main.cpp",
'''#include "components/connectivity_component.h"\n''',
'''#include "components/connectivity_component.h"\n#include "rules/rule_engine.h"\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n#include "components/virtual_input_component.h"\n#include "components/virtual_actuator_component.h"\n#endif\n''')

replace_once("src/main.cpp",
'''RuntimeCore::Supervisor runtimeSupervisor(runtimeComponents, runtimeEvents);\n''',
'''RuntimeCore::Supervisor runtimeSupervisor(runtimeComponents, runtimeEvents);\nRules::RuleEngine ruleEngine(runtimeEvents);\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\nComponents::VirtualInputComponent virtualTemperature(runtimeEvents, "virtual.temperature");\nComponents::VirtualActuatorComponent virtualHeater(runtimeEvents, "virtual.heater");\n#endif\n''')

replace_once("src/main.cpp",
'''  } else if (event.type == static_cast<uint16_t>(RuntimeCore::RuntimeEventType::SupervisorStateChanged)) {\n    logLine("EVENT supervisor_state value=" + String(event.value));\n  }\n''',
'''  } else if (event.type == static_cast<uint16_t>(RuntimeCore::RuntimeEventType::SupervisorStateChanged)) {\n    logLine("EVENT supervisor_state value=" + String(event.value));\n  } else if (event.type == static_cast<uint16_t>(RuntimeCore::RuntimeEventType::InputValueChanged)) {\n    logLine("EVENT input_value source=" + String(event.source) +\n            " milli_value=" + String(event.value));\n  } else if (event.type == static_cast<uint16_t>(RuntimeCore::RuntimeEventType::RuleEvaluated)) {\n    logLine("EVENT rule_evaluated source=" + String(event.source) +\n            " decision=" + String(event.value));\n  }\n''')

replace_once("src/main.cpp",
'''  json += "\\\"configuration\\\":" + ConfigurationStore::statusJson() + ",";\n  json += "\\\"components\\\":" + runtimeComponents.statusJson() + ",";\n''',
'''  json += "\\\"configuration\\\":" + ConfigurationStore::statusJson() + ",";\n  json += "\\\"rule_engine\\\":" + ruleEngine.statusJson() + ",";\n  json += "\\\"components\\\":" + runtimeComponents.statusJson() + ",";\n''')

replace_once("src/main.cpp",
'''    body += "configuration_status=/api/configuration/status\\n";\n    body += "components=/api/components\\n";\n''',
'''    body += "configuration_status=/api/configuration/status\\n";\n    body += "rules_status=/api/rules/status\\n";\n    body += "components=/api/components\\n";\n''')

replace_once("src/main.cpp",
'''  server.on("/api/components", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", componentsStatusJson());\n  });\n\n''',
'''  server.on("/api/components", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", componentsStatusJson());\n  });\n\n  server.on("/api/rules/status", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", ruleEngine.statusJson());\n  });\n\n''')

lab_routes = r'''#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS
  server.on("/api/test/rules/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    String json = "{\"engine\":" + ruleEngine.statusJson() +
                  ",\"input\":" + virtualTemperature.statusJson() +
                  ",\"actuator\":" + virtualHeater.statusJson() + "}";
    request->send(200, "application/json", json);
  });

  server.on("/api/test/rules/configure", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("on_below", true) || !request->hasParam("off_above", true)) {
      request->send(400, "application/json", "{\"error\":\"thresholds_required\"}");
      return;
    }
    Rules::HysteresisRule rule;
    rule.id = "demo.temperature.heater";
    rule.enabled = !request->hasParam("enabled", true) ||
                   request->getParam("enabled", true)->value() != "0";
    rule.onBelow = request->getParam("on_below", true)->value().toFloat();
    rule.offAbove = request->getParam("off_above", true)->value().toFloat();
    String error;
    if (!ruleEngine.configure(rule, error)) {
      request->send(400, "application/json", String("{\"error\":\"") + error + "\"}");
      return;
    }
    virtualHeater.enable(false);
    request->send(200, "application/json", ruleEngine.statusJson());
  });

  server.on("/api/test/rules/input", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("value", true)) {
      request->send(400, "application/json", "{\"error\":\"value_required\"}");
      return;
    }
    const float value = request->getParam("value", true)->value().toFloat();
    if (!virtualTemperature.setValue(value)) {
      request->send(400, "application/json", "{\"error\":\"value_invalid\"}");
      return;
    }
    request->send(200, "application/json", virtualTemperature.statusJson());
  });

  server.on("/api/test/rules/evaluate", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!virtualTemperature.hasValue()) {
      request->send(409, "application/json", "{\"error\":\"input_not_ready\"}");
      return;
    }
    if (!virtualHeater.enabled()) virtualHeater.enable(false);
    bool desired = virtualHeater.isOn();
    Rules::RuleDecision decision = Rules::RuleDecision::None;
    String error;
    if (!ruleEngine.evaluate(virtualTemperature.value(), virtualHeater.isOn(),
                             desired, decision, error)) {
      request->send(409, "application/json", String("{\"error\":\"") + error + "\"}");
      return;
    }
    if (decision != Rules::RuleDecision::Disabled && !virtualHeater.applyDesired(desired)) {
      request->send(500, "application/json", "{\"error\":\"actuator_rejected\"}");
      return;
    }
    String json = "{\"engine\":" + ruleEngine.statusJson() +
                  ",\"input\":" + virtualTemperature.statusJson() +
                  ",\"actuator\":" + virtualHeater.statusJson() + "}";
    request->send(200, "application/json", json);
  });

  server.on("/api/test/rules/reset", HTTP_POST, [](AsyncWebServerRequest* request) {
    ruleEngine.clear();
    virtualTemperature.disable();
    virtualHeater.disable();
    request->send(200, "application/json", "{\"reset\":true}");
  });
#endif

'''
replace_once("src/main.cpp",
'''  registerFirmwareMetadataRoutes(server);\n''', lab_routes + '''  registerFirmwareMetadataRoutes(server);\n''')

replace_once("src/main.cpp",
'''  if (!ConfigurationStore::begin()) {\n    Serial.println("CONFIGURATION_STORE_INIT_FAILED");\n  }\n\n  runtimeEvents.subscribe(handleRuntimeEvent);\n  runtimeComponents.add(connectivityComponent);\n''',
'''  if (!ConfigurationStore::begin()) {\n    Serial.println("CONFIGURATION_STORE_INIT_FAILED");\n  }\n  if (!ruleEngine.begin()) {\n    Serial.println("RULE_ENGINE_INIT_FAILED");\n  }\n\n  runtimeEvents.subscribe(handleRuntimeEvent);\n  runtimeComponents.add(connectivityComponent);\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n  runtimeComponents.add(virtualTemperature);\n  runtimeComponents.add(virtualHeater);\n#endif\n''')

replace_once("platformio.ini",
'''    -DPROJ_REMOTE_UPDATE_ALLOW_HTTP=1\n    -DPROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT=1\n''',
'''    -DPROJ_REMOTE_UPDATE_ALLOW_HTTP=1\n    -DPROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT=1\n    -DPROJ_RULE_ENGINE_TEST_ENDPOINTS=1\n''')

replace_once("docs/ROADMAP.md",
'''- [ ] `RuleEngine` with semantic rule validation and TaskScheduler-driven evaluation;\n''',
'''- [~] **Stage 7B** — minimal hysteresis `RuleEngine` + virtual input/actuator model; manual evaluation proof pending;\n- [ ] **Stage 7C** — TaskScheduler-driven/event-forced evaluation with work task disabled when no active rules;\n''')

with (ROOT / "docs/configuration.md").open("a", encoding="utf-8") as f:
    f.write(r'''

## Stage 7B — minimal local rule model

Stage 7B deliberately proves the functional boundary before adding automatic scheduling.
The first engine supports one in-memory hysteresis rule and virtual input/output components.
It does **not** load rule semantics from persisted configuration yet and it does not touch GPIO.

Flow under the controlled lab build:

```text
VirtualInputComponent
        |
        | explicit value
        v
    RuleEngine
        |
        | desired boolean state
        v
VirtualActuatorComponent
```

The demo rule follows the field pattern that motivated the architecture:

```text
value < on_below   -> desired ON
value > off_above  -> desired OFF
inside deadband    -> HOLD current state
```

Semantic validation rejects invalid IDs, non-finite thresholds and hysteresis where
`on_below >= off_above`. The engine returns a desired state only; it has no driver or
GPIO dependency. The virtual actuator owns application of that desired state.

`GET /api/rules/status` is the standard read-only observability endpoint. Controlled
write/evaluation endpoints exist only in the remote test image behind
`PROJ_RULE_ENGINE_TEST_ENDPOINTS`.

Stage 7B evaluation is intentionally explicit/manual. Stage 7C will connect the same
engine to TaskScheduler + EventBus so the evaluation work task is disabled while no
rule is active and input events can force an iteration. This keeps the distinction
clear: Stage 7B proves rule semantics; Stage 7C proves runtime scheduling/state flow.
''')

with (ROOT / "docs/architecture.md").open("a", encoding="utf-8") as f:
    f.write(r'''

## Stage 7B RuleEngine boundary

The first RuleEngine is deliberately transport- and hardware-independent. A rule
receives an input value plus current output state and returns a desired output state.
It never writes GPIO. Controlled virtual components prove the path before real sensors
or relays exist. Stage 7C will add TaskScheduler/EventBus-driven automatic evaluation;
Stage 7D will bind validated persisted rule documents to the engine lifecycle.
''')

replace_once("docs/README.md",
'''- [~] Stage 7A transactional ConfigurationStore implementation/build validation\n''',
'''- [x] Stage 7A transactional ConfigurationStore implementation + physical validation\n- [~] Stage 7B minimal RuleEngine + virtual I/O implementation; physical proof pending\n''')

replace_once("README.md",
'''**Stage 7A has started:** `ConfigurationStore` introduces versioned dual-slot NVS transactions with verified inactive-slot writes, monotonic revisions, boot fallback and rollback. Rule execution is not enabled until the RuleEngine semantic layer is added and validated.\n''',
'''**Stage 7A is validated:** `ConfigurationStore` provides versioned dual-slot NVS transactions with verified inactive-slot writes, monotonic revisions, boot fallback and rollback. **Stage 7B is in progress:** a minimal hardware-independent hysteresis RuleEngine and virtual input/actuator path are being validated before TaskScheduler-driven automatic evaluation is added in Stage 7C.\n''')

print("STAGE7B_IMPLEMENT_PATCHED")
