from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')


def write(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')


def replace_once(rel, old, new):
    text = read(rel)
    if old not in text:
        raise SystemExit(f'missing anchor in {rel}: {old[:120]!r}')
    write(rel, text.replace(old, new, 1))

# Add a semantic loader that binds one persisted hysteresis rule to the validated engine/runtime.
write('include/rules/persisted_rule_loader.h', r'''#pragma once

#include <Arduino.h>

#include "rules/rule_engine.h"
#include "rules/rule_runtime.h"

namespace Rules {

class PersistedRuleLoader {
 public:
  PersistedRuleLoader(RuleEngine& engine, RuleRuntime& runtime)
      : engine_(engine), runtime_(runtime) {}

  bool begin();
  bool reload(String& error);
  uint32_t loadedRevision() const { return loadedRevision_; }
  const String& loadedRuleId() const { return loadedRuleId_; }
  const String& lastResult() const { return lastResult_; }
  String statusJson() const;

 private:
  bool parseActive(HysteresisRule& rule, bool& found, String& error);

  RuleEngine& engine_;
  RuleRuntime& runtime_;
  uint32_t loadedRevision_ = 0;
  String loadedRuleId_;
  String lastResult_ = "never";
};

}  // namespace Rules
''')

write('src/rules/persisted_rule_loader.cpp', r'''#include "rules/persisted_rule_loader.h"

#include <ArduinoJson.h>
#include <math.h>

#include "configuration_store.h"

namespace Rules {
namespace {
constexpr size_t JSON_CAPACITY = 4096;

bool parseBool(JsonVariant value, bool fallback, bool& out) {
  if (value.isNull()) {
    out = fallback;
    return true;
  }
  if (!value.is<bool>()) return false;
  out = value.as<bool>();
  return true;
}
}

bool PersistedRuleLoader::begin() {
  String error;
  return reload(error);
}

bool PersistedRuleLoader::parseActive(HysteresisRule& rule, bool& found, String& error) {
  error = "";
  found = false;
  const String raw = ConfigurationStore::activeJson();
  DynamicJsonDocument doc(JSON_CAPACITY);
  if (deserializeJson(doc, raw)) {
    error = "persisted_rule_config_json_invalid";
    return false;
  }
  if (!doc["rules"].is<JsonArray>()) {
    error = "persisted_rule_rules_missing";
    return false;
  }

  JsonArray rules = doc["rules"].as<JsonArray>();
  if (rules.size() == 0) return true;
  if (rules.size() > 1) {
    error = "persisted_rule_multiple_not_supported_stage7d";
    return false;
  }

  JsonObject object = rules[0].as<JsonObject>();
  const char* id = object["id"] | "";
  const char* type = object["type"] | "";
  const char* input = object["input"] | "";
  const char* output = object["output"] | "";
  if (String(type) != "hysteresis") {
    error = "persisted_rule_type_unsupported";
    return false;
  }
  if (String(input) != "virtual.temperature") {
    error = "persisted_rule_input_unsupported";
    return false;
  }
  if (String(output) != "virtual.heater") {
    error = "persisted_rule_output_unsupported";
    return false;
  }
  if (!object["on_below"].is<float>() && !object["on_below"].is<int>() &&
      !object["on_below"].is<long>() && !object["on_below"].is<double>()) {
    error = "persisted_rule_on_below_invalid";
    return false;
  }
  if (!object["off_above"].is<float>() && !object["off_above"].is<int>() &&
      !object["off_above"].is<long>() && !object["off_above"].is<double>()) {
    error = "persisted_rule_off_above_invalid";
    return false;
  }

  rule.id = id;
  if (!parseBool(object["enabled"], true, rule.enabled)) {
    error = "persisted_rule_enabled_invalid";
    return false;
  }
  rule.onBelow = object["on_below"].as<float>();
  rule.offAbove = object["off_above"].as<float>();
  if (!isfinite(rule.onBelow) || !isfinite(rule.offAbove)) {
    error = "persisted_rule_threshold_invalid";
    return false;
  }
  found = true;
  return true;
}

bool PersistedRuleLoader::reload(String& error) {
  error = "";
  HysteresisRule rule;
  bool found = false;
  if (!parseActive(rule, found, error)) {
    lastResult_ = error;
    return false;
  }

  if (!found) {
    engine_.clear();
    runtime_.refreshEligibility();
    loadedRevision_ = ConfigurationStore::revision();
    loadedRuleId_ = "";
    lastResult_ = "no_rules";
    return true;
  }

  String semanticError;
  if (!engine_.configure(rule, semanticError)) {
    error = semanticError.length() ? semanticError : "persisted_rule_semantic_invalid";
    lastResult_ = error;
    return false;
  }
  runtime_.refreshEligibility();
  loadedRevision_ = ConfigurationStore::revision();
  loadedRuleId_ = rule.id;
  lastResult_ = rule.enabled ? "loaded_enabled" : "loaded_disabled";
  return true;
}

String PersistedRuleLoader::statusJson() const {
  String json = "{";
  json += "\"loaded_revision\":" + String(loadedRevision_) + ",";
  json += "\"loaded_rule_id\":\"" + loadedRuleId_ + "\",";
  json += "\"last_result\":\"" + lastResult_ + "\"";
  json += "}";
  return json;
}

}  // namespace Rules
''')

# ConfigurationStore callbacks keep runtime activation inside the same successful request lifecycle.
replace_once('include/configuration_store.h',
'''bool apply(const String& candidateJson, String& error);\nbool rollback(String& error);\nvoid registerRoutes(AsyncWebServer& server);\n''',
'''bool apply(const String& candidateJson, String& error);\nbool rollback(String& error);\nusing ActivatedCallback = bool (*)(uint32_t revision, String& error);\nvoid setActivatedCallback(ActivatedCallback callback);\nvoid registerRoutes(AsyncWebServer& server);\n''')

replace_once('src/configuration_store.cpp',
'''String lastResult = "never";\n''',
'''String lastResult = "never";\nConfigurationStore::ActivatedCallback activatedCallback = nullptr;\n''')

replace_once('src/configuration_store.cpp',
'''bool rollback(String& error) {\n''',
'''void setActivatedCallback(ActivatedCallback callback) {\n  ConfigLock lock;\n  if (lock.locked()) activatedCallback = callback;\n}\n\nbool rollback(String& error) {\n''')

# Notify after the NVS pointer is committed and in-memory active snapshot has changed.
replace_once('src/configuration_store.cpp',
'''  lastResult = "applied";\n  return true;\n}\n\nvoid setActivatedCallback''',
'''  lastResult = "applied";\n  if (activatedCallback) {\n    String activationError;\n    if (!activatedCallback(activeRevision, activationError)) {\n      lastResult = activationError.length() ? String("applied_runtime_error:") + activationError\n                                            : "applied_runtime_error";\n      error = activationError.length() ? activationError : "configuration_runtime_activation_failed";\n      return false;\n    }\n  }\n  return true;\n}\n\nvoid setActivatedCallback''')

replace_once('src/configuration_store.cpp',
'''  lastResult = "rolled_back";\n  return true;\n}\n\nvoid registerRoutes''',
'''  lastResult = "rolled_back";\n  if (activatedCallback) {\n    String activationError;\n    if (!activatedCallback(activeRevision, activationError)) {\n      lastResult = activationError.length() ? String("rollback_runtime_error:") + activationError\n                                            : "rollback_runtime_error";\n      error = activationError.length() ? activationError : "configuration_runtime_activation_failed";\n      return false;\n    }\n  }\n  return true;\n}\n\nvoid registerRoutes''')

# Main integrates persisted loading in clean and lab builds. Virtual components now exist in all builds,
# but controlled write/test HTTP endpoints remain compile-gated.
replace_once('src/main.cpp',
'''#include "rules/rule_runtime.h"\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n#include "components/virtual_input_component.h"\n#include "components/virtual_actuator_component.h"\n#endif\n''',
'''#include "rules/rule_runtime.h"\n#include "rules/persisted_rule_loader.h"\n#include "components/virtual_input_component.h"\n#include "components/virtual_actuator_component.h"\n''')

replace_once('src/main.cpp',
'''Rules::RuleEngine ruleEngine(runtimeEvents);\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\nComponents::VirtualInputComponent virtualTemperature(runtimeEvents, "virtual.temperature");\nComponents::VirtualActuatorComponent virtualHeater(runtimeEvents, "virtual.heater");\n#endif\n''',
'''Rules::RuleEngine ruleEngine(runtimeEvents);\nComponents::VirtualInputComponent virtualTemperature(runtimeEvents, "virtual.temperature");\nComponents::VirtualActuatorComponent virtualHeater(runtimeEvents, "virtual.heater");\n''')

replace_once('src/main.cpp',
'''Rules::RuleRuntime ruleRuntime(cooperativeScheduler, runtimeEvents, ruleEngine,\n                               "virtual.temperature", ruleInputReady, ruleInputValue,\n                               ruleOutputState, ruleApplyDesired);\n''',
'''Rules::RuleRuntime ruleRuntime(cooperativeScheduler, runtimeEvents, ruleEngine,\n                               "virtual.temperature", ruleInputReady, ruleInputValue,\n                               ruleOutputState, ruleApplyDesired);\nRules::PersistedRuleLoader persistedRuleLoader(ruleEngine, ruleRuntime);\n''')

replace_once('src/main.cpp',
'''bool ruleInputReady() {\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n  return virtualTemperature.hasValue();\n#else\n  return false;\n#endif\n}\n\nfloat ruleInputValue() {\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n  return virtualTemperature.value();\n#else\n  return 0.0f;\n#endif\n}\n\nbool ruleOutputState() {\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n  return virtualHeater.isOn();\n#else\n  return false;\n#endif\n}\n\nbool ruleApplyDesired(bool desiredOn) {\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n  return virtualHeater.applyDesired(desiredOn);\n#else\n  (void)desiredOn;\n  return false;\n#endif\n}\n''',
'''bool ruleInputReady() { return virtualTemperature.hasValue(); }\nfloat ruleInputValue() { return virtualTemperature.value(); }\nbool ruleOutputState() { return virtualHeater.isOn(); }\nbool ruleApplyDesired(bool desiredOn) { return virtualHeater.applyDesired(desiredOn); }\n\nbool reloadPersistedRules(uint32_t revision, String& error) {\n  (void)revision;\n  return persistedRuleLoader.reload(error);\n}\n''')

replace_once('src/main.cpp',
'''  json += "\\\"rule_runtime\\\":" + ruleRuntime.statusJson() + ",";\n''',
'''  json += "\\\"rule_runtime\\\":" + ruleRuntime.statusJson() + ",";\n  json += "\\\"persisted_rules\\\":" + persistedRuleLoader.statusJson() + ",";\n''')

replace_once('src/main.cpp',
'''    body += "rules_runtime=/api/rules/runtime\\n";\n''',
'''    body += "rules_runtime=/api/rules/runtime\\n";\n    body += "persisted_rules=/api/rules/persisted\\n";\n''')

replace_once('src/main.cpp',
'''  server.on("/api/rules/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", ruleRuntime.statusJson());\n  });\n\n''',
'''  server.on("/api/rules/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", ruleRuntime.statusJson());\n  });\n\n  server.on("/api/rules/persisted", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", persistedRuleLoader.statusJson());\n  });\n\n''')

# Preserve test reset as an in-memory test action only; next persisted config reload restores truth.
# Setup order: components initialized before persisted rule is loaded so actuator can safely accept desired state.
replace_once('src/main.cpp',
'''  runtimeEvents.subscribe(handleRuntimeEvent);\n  if (!ruleRuntime.begin()) {\n    Serial.println("RULE_RUNTIME_INIT_FAILED");\n  }\n  runtimeComponents.add(connectivityComponent);\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n  runtimeComponents.add(virtualTemperature);\n  runtimeComponents.add(virtualHeater);\n#endif\n  if (!runtimeComponents.beginAll()) {\n    Serial.println("RUNTIME_COMPONENT_INIT_DEGRADED");\n  }\n''',
'''  runtimeEvents.subscribe(handleRuntimeEvent);\n  if (!ruleRuntime.begin()) {\n    Serial.println("RULE_RUNTIME_INIT_FAILED");\n  }\n  runtimeComponents.add(connectivityComponent);\n  runtimeComponents.add(virtualTemperature);\n  runtimeComponents.add(virtualHeater);\n  if (!runtimeComponents.beginAll()) {\n    Serial.println("RUNTIME_COMPONENT_INIT_DEGRADED");\n  }\n  virtualHeater.enable(false);\n  ConfigurationStore::setActivatedCallback(reloadPersistedRules);\n  String persistedRuleError;\n  if (!persistedRuleLoader.begin()) {\n    Serial.println("PERSISTED_RULE_LOAD_FAILED");\n  }\n''')

# Semantic config schema enforcement: Stage 7D supports zero or one hysteresis rule with explicit binding.
replace_once('src/configuration_store.cpp',
'''bool validateEntryArray(JsonArray array, size_t limit, String& error) {\n''',
'''bool validateRuleSemantics(JsonArray rules, String& error) {\n  if (rules.size() > 1) {\n    error = "configuration_multiple_rules_not_supported_stage7d";\n    return false;\n  }\n  if (rules.size() == 0) return true;\n  JsonObject rule = rules[0].as<JsonObject>();\n  const char* type = rule["type"] | "";\n  const char* input = rule["input"] | "";\n  const char* output = rule["output"] | "";\n  if (strcmp(type, "hysteresis") != 0) { error = "configuration_rule_type_unsupported"; return false; }\n  if (strcmp(input, "virtual.temperature") != 0) { error = "configuration_rule_input_unsupported"; return false; }\n  if (strcmp(output, "virtual.heater") != 0) { error = "configuration_rule_output_unsupported"; return false; }\n  if (!rule["on_below"].is<float>() && !rule["on_below"].is<int>() &&\n      !rule["on_below"].is<long>() && !rule["on_below"].is<double>()) {\n    error = "configuration_rule_on_below_invalid"; return false;\n  }\n  if (!rule["off_above"].is<float>() && !rule["off_above"].is<int>() &&\n      !rule["off_above"].is<long>() && !rule["off_above"].is<double>()) {\n    error = "configuration_rule_off_above_invalid"; return false;\n  }\n  const float onBelow = rule["on_below"].as<float>();\n  const float offAbove = rule["off_above"].as<float>();\n  if (!isfinite(onBelow) || !isfinite(offAbove) || !(onBelow < offAbove)) {\n    error = "configuration_rule_hysteresis_invalid"; return false;\n  }\n  return true;\n}\n\nbool validateEntryArray(JsonArray array, size_t limit, String& error) {\n''')

replace_once('src/configuration_store.cpp',
'''  if (!validateEntryArray(root["rules"].as<JsonArray>(), MAX_RULES, error)) return false;\n  if (!validateEntryArray(root["schedules"].as<JsonArray>(), MAX_SCHEDULES, error)) return false;\n  return true;\n''',
'''  if (!validateEntryArray(root["rules"].as<JsonArray>(), MAX_RULES, error)) return false;\n  if (!validateRuleSemantics(root["rules"].as<JsonArray>(), error)) return false;\n  if (!validateEntryArray(root["schedules"].as<JsonArray>(), MAX_SCHEDULES, error)) return false;\n  return true;\n''')

# math.h needed for isfinite in ConfigurationStore semantic validator.
replace_once('src/configuration_store.cpp', '#include <ctype.h>\n', '#include <ctype.h>\n#include <math.h>\n')

# Documentation in-progress checkpoint.
replace_once('docs/ROADMAP.md',
'''- [ ] local `Scheduler` for schedules/delayed actions/settling windows;\n''',
'''- [~] **Stage 7D** — persisted rule document binding to RuleEngine/RuleRuntime with revision/rollback activation; physical proof pending;\n- [ ] local `Scheduler` for schedules/delayed actions/settling windows;\n''')

config = read('docs/configuration.md')
if '## Stage 7D — persisted rule activation' not in config:
    config += r'''

## Stage 7D — persisted rule activation

Stage 7D binds the transactional ConfigurationStore revision to RuleEngine/RuleRuntime.
The active configuration is now the source of truth for rule semantics after boot,
apply and rollback.

The first persisted rule schema is intentionally narrow:

```json
{
  "schema": 1,
  "rules": [{
    "id": "demo.temperature.heater",
    "type": "hysteresis",
    "input": "virtual.temperature",
    "output": "virtual.heater",
    "enabled": true,
    "on_below": 16,
    "off_above": 18
  }],
  "schedules": []
}
```

Stage 7D supports zero or one rule. Configuration validation rejects unsupported type,
input/output binding, multiple rules and invalid hysteresis before the candidate becomes
active. A successful NVS activation invokes PersistedRuleLoader in the same request
lifecycle; rollback reloads the restored logical rule using the new monotonic revision.
The engine/runtime never depend on Wi-Fi or MQTT for this binding.

`GET /api/rules/persisted` exposes only non-secret binding diagnostics:
loaded configuration revision, loaded rule id and last loader result.

Virtual input/actuator components remain the controlled functional endpoints for this
stage; they are now present in the clean runtime because a persisted rule must have a
local input/output binding even without lab HTTP endpoints. Real hardware drivers are
still deferred.
'''
    write('docs/configuration.md', config)

arch = read('docs/architecture.md')
if '## Stage 7D persisted-rule ownership' not in arch:
    arch += r'''

## Stage 7D persisted-rule ownership

ConfigurationStore owns durable configuration and monotonic revision. PersistedRuleLoader
translates the active validated rule document into RuleEngine semantics and then asks
RuleRuntime to refresh eligibility. RuleRuntime still owns only event/scheduling runtime
state; the scheduler does not parse configuration. Apply and rollback both reload the
new active revision locally, so control-plane connectivity is irrelevant after the
configuration document has been accepted.
'''
    write('docs/architecture.md', arch)

replace_once('docs/README.md',
'''- [x] Stage 7C TaskScheduler/EventBus rule evaluation runtime physically validated\n''',
'''- [x] Stage 7C TaskScheduler/EventBus rule evaluation runtime physically validated\n- [~] Stage 7D persisted rule binding + revision/rollback activation; physical proof pending\n''')

replace_once('README.md',
'''**Stage 7A is validated:** `ConfigurationStore` provides versioned dual-slot NVS transactions with rollback. **Stage 7B is validated:** the minimal hardware-independent hysteresis RuleEngine and virtual input/output path were physically proven, including deadband and disabled-rule behavior; RuleEngine returns desired state and never accesses GPIO. **Stage 7C is validated:** TaskScheduler/EventBus-driven evaluation is one-shot/event-driven, stays disabled without meaningful work, and executed locally during real Wi-Fi/MQTT loss. **Stage 7D is next:** persisted ConfigurationStore rule documents become the source of truth for RuleEngine/RuleRuntime lifecycle and rollback.\n''',
'''**Stages 7A-7C are validated:** transactional configuration, hysteresis semantics, and one-shot local RuleRuntime execution have all been physically proven. **Stage 7D is in progress:** persisted ConfigurationStore rule documents now become the source of truth for RuleEngine/RuleRuntime lifecycle across boot, apply and rollback; physical persistence/rollback proof is pending.\n''')

print('STAGE7D_IMPLEMENT_PATCHED')
