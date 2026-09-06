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
  bool validateDocument(const String& raw, String& error) const;
  bool activateDocument(const String& raw, uint32_t revision, String& error);
  uint32_t loadedRevision() const { return loadedRevision_; }
  const String& loadedRuleId() const { return loadedRuleId_; }
  const String& lastResult() const { return lastResult_; }
  String statusJson() const;

 private:
  bool parseDocument(const String& raw, HysteresisRule& rule, bool& found,
                     uint32_t& revision, String& error) const;
  bool applyParsed(const HysteresisRule& rule, bool found, uint32_t revision,
                   String& error);

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
#include <ctype.h>
#include <math.h>

#include "configuration_store.h"

namespace Rules {
namespace {
constexpr size_t JSON_CAPACITY = 4096;

bool supportedNumber(JsonVariant value) {
  return value.is<float>() || value.is<double>() || value.is<int>() ||
         value.is<long>() || value.is<unsigned int>() || value.is<unsigned long>();
}
}

bool PersistedRuleLoader::parseDocument(const String& raw, HysteresisRule& rule,
                                        bool& found, uint32_t& revision,
                                        String& error) const {
  error = "";
  found = false;
  revision = 0;
  DynamicJsonDocument doc(JSON_CAPACITY);
  if (deserializeJson(doc, raw)) {
    error = "persisted_rule_config_json_invalid";
    return false;
  }
  if (!doc["revision"].is<uint32_t>() || !doc["rules"].is<JsonArray>()) {
    error = "persisted_rule_document_invalid";
    return false;
  }
  revision = doc["revision"].as<uint32_t>();
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
  if (!supportedNumber(object["on_below"])) {
    error = "persisted_rule_on_below_invalid";
    return false;
  }
  if (!supportedNumber(object["off_above"])) {
    error = "persisted_rule_off_above_invalid";
    return false;
  }
  if (object.containsKey("enabled") && !object["enabled"].is<bool>()) {
    error = "persisted_rule_enabled_invalid";
    return false;
  }

  rule.id = id;
  rule.enabled = object["enabled"] | true;
  rule.onBelow = object["on_below"].as<float>();
  rule.offAbove = object["off_above"].as<float>();
  if (!isfinite(rule.onBelow) || !isfinite(rule.offAbove) ||
      !(rule.onBelow < rule.offAbove)) {
    error = "persisted_rule_hysteresis_invalid";
    return false;
  }
  if (rule.id.length() == 0 || rule.id.length() > 48) {
    error = "rule_id_invalid";
    return false;
  }
  for (size_t i = 0; i < rule.id.length(); ++i) {
    const unsigned char c = static_cast<unsigned char>(rule.id[i]);
    if (!(isalnum(c) || c == '_' || c == '-' || c == '.' || c == ':')) {
      error = "rule_id_invalid";
      return false;
    }
  }

  found = true;
  return true;
}

bool PersistedRuleLoader::validateDocument(const String& raw, String& error) const {
  HysteresisRule rule;
  bool found = false;
  uint32_t revision = 0;
  return parseDocument(raw, rule, found, revision, error);
}

bool PersistedRuleLoader::applyParsed(const HysteresisRule& rule, bool found,
                                      uint32_t revision, String& error) {
  error = "";
  if (!found) {
    engine_.clear();
    runtime_.refreshEligibility();
    loadedRevision_ = revision;
    loadedRuleId_ = "";
    lastResult_ = "no_rules";
    return true;
  }

  if (!engine_.configure(rule, error)) {
    lastResult_ = error.length() ? error : "persisted_rule_semantic_invalid";
    return false;
  }
  runtime_.refreshEligibility();
  loadedRevision_ = revision;
  loadedRuleId_ = rule.id;
  lastResult_ = rule.enabled ? "loaded_enabled" : "loaded_disabled";
  return true;
}

bool PersistedRuleLoader::activateDocument(const String& raw, uint32_t revision,
                                           String& error) {
  HysteresisRule rule;
  bool found = false;
  uint32_t parsedRevision = 0;
  if (!parseDocument(raw, rule, found, parsedRevision, error)) {
    loadedRevision_ = revision;
    lastResult_ = error;
    return false;
  }
  if (parsedRevision != revision) {
    error = "persisted_rule_revision_mismatch";
    loadedRevision_ = revision;
    lastResult_ = error;
    return false;
  }
  return applyParsed(rule, found, revision, error);
}

bool PersistedRuleLoader::reload(String& error) {
  const String raw = ConfigurationStore::activeJson();
  const uint32_t revision = ConfigurationStore::revision();
  return activateDocument(raw, revision, error);
}

bool PersistedRuleLoader::begin() {
  String error;
  return reload(error);
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

replace_once('include/configuration_store.h',
'''bool apply(const String& candidateJson, String& error);\nbool rollback(String& error);\nvoid registerRoutes(AsyncWebServer& server);\n''',
'''bool apply(const String& candidateJson, String& error);\nbool rollback(String& error);\nusing ValidateActiveCallback = bool (*)(const String& activeJson, String& error);\nusing ActivatedCallback = void (*)(uint32_t revision, const String& activeJson);\nvoid setRuleLifecycleCallbacks(ValidateActiveCallback validator, ActivatedCallback activated);\nvoid registerRoutes(AsyncWebServer& server);\n''')

replace_once('src/configuration_store.cpp',
'''String lastResult = "never";\n''',
'''String lastResult = "never";\nConfigurationStore::ValidateActiveCallback ruleValidator = nullptr;\nConfigurationStore::ActivatedCallback activatedCallback = nullptr;\n''')

replace_once('src/configuration_store.cpp',
'''  const uint8_t nextSlot = activeSlot == 0 ? 1 : 0;\n  String verified;\n''',
'''  if (ruleValidator) {\n    String semanticError;\n    if (!ruleValidator(canonical, semanticError)) {\n      error = semanticError.length() ? semanticError : "configuration_rule_semantic_invalid";\n      return false;\n    }\n  }\n\n  const uint8_t nextSlot = activeSlot == 0 ? 1 : 0;\n  String verified;\n''')

replace_once('src/configuration_store.cpp',
'''  lastResult = "applied";\n  return true;\n}\n\nbool rollback''',
'''  lastResult = "applied";\n  if (activatedCallback) activatedCallback(activeRevision, activeRaw);\n  return true;\n}\n\nvoid setRuleLifecycleCallbacks(ValidateActiveCallback validator, ActivatedCallback activated) {\n  ConfigLock lock;\n  if (!lock.locked()) return;\n  ruleValidator = validator;\n  activatedCallback = activated;\n}\n\nbool rollback''')

replace_once('src/configuration_store.cpp',
'''  String verified;\n  if (!persistSlotVerified(previousSlot, rollbackRaw, nextRevision, verified, error)) return false;\n''',
'''  if (ruleValidator) {\n    String semanticError;\n    if (!ruleValidator(rollbackRaw, semanticError)) {\n      error = semanticError.length() ? semanticError : "configuration_rule_semantic_invalid";\n      return false;\n    }\n  }\n\n  String verified;\n  if (!persistSlotVerified(previousSlot, rollbackRaw, nextRevision, verified, error)) return false;\n''')

replace_once('src/configuration_store.cpp',
'''  lastResult = "rolled_back";\n  return true;\n}\n\nvoid registerRoutes''',
'''  lastResult = "rolled_back";\n  if (activatedCallback) activatedCallback(activeRevision, activeRaw);\n  return true;\n}\n\nvoid registerRoutes''')

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
'''bool ruleInputReady() { return virtualTemperature.hasValue(); }\nfloat ruleInputValue() { return virtualTemperature.value(); }\nbool ruleOutputState() { return virtualHeater.isOn(); }\nbool ruleApplyDesired(bool desiredOn) { return virtualHeater.applyDesired(desiredOn); }\n\nbool validatePersistedRules(const String& raw, String& error) {\n  return persistedRuleLoader.validateDocument(raw, error);\n}\n\nvoid activatePersistedRules(uint32_t revision, const String& raw) {\n  String error;\n  if (!persistedRuleLoader.activateDocument(raw, revision, error)) {\n    logLine("PERSISTED_RULE_RELOAD_FAILED " + error);\n  }\n}\n''')

replace_once('src/main.cpp',
'''  json += "\\\"rule_runtime\\\":" + ruleRuntime.statusJson() + ",";\n''',
'''  json += "\\\"rule_runtime\\\":" + ruleRuntime.statusJson() + ",";\n  json += "\\\"persisted_rules\\\":" + persistedRuleLoader.statusJson() + ",";\n''')

replace_once('src/main.cpp',
'''    body += "rules_runtime=/api/rules/runtime\\n";\n''',
'''    body += "rules_runtime=/api/rules/runtime\\n";\n    body += "persisted_rules=/api/rules/persisted\\n";\n''')

replace_once('src/main.cpp',
'''  server.on("/api/rules/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", ruleRuntime.statusJson());\n  });\n\n''',
'''  server.on("/api/rules/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", ruleRuntime.statusJson());\n  });\n\n  server.on("/api/rules/persisted", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", persistedRuleLoader.statusJson());\n  });\n\n''')

replace_once('src/main.cpp',
'''  runtimeEvents.subscribe(handleRuntimeEvent);\n  if (!ruleRuntime.begin()) {\n    Serial.println("RULE_RUNTIME_INIT_FAILED");\n  }\n  runtimeComponents.add(connectivityComponent);\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n  runtimeComponents.add(virtualTemperature);\n  runtimeComponents.add(virtualHeater);\n#endif\n  if (!runtimeComponents.beginAll()) {\n    Serial.println("RUNTIME_COMPONENT_INIT_DEGRADED");\n  }\n''',
'''  runtimeEvents.subscribe(handleRuntimeEvent);\n  if (!ruleRuntime.begin()) {\n    Serial.println("RULE_RUNTIME_INIT_FAILED");\n  }\n  runtimeComponents.add(connectivityComponent);\n  runtimeComponents.add(virtualTemperature);\n  runtimeComponents.add(virtualHeater);\n  if (!runtimeComponents.beginAll()) {\n    Serial.println("RUNTIME_COMPONENT_INIT_DEGRADED");\n  }\n  virtualHeater.enable(false);\n  ConfigurationStore::setRuleLifecycleCallbacks(validatePersistedRules, activatePersistedRules);\n  if (!persistedRuleLoader.begin()) {\n    Serial.println("PERSISTED_RULE_LOAD_FAILED");\n  }\n''')

replace_once('docs/ROADMAP.md',
'''- [ ] local `Scheduler` for schedules/delayed actions/settling windows;\n''',
'''- [~] **Stage 7D** — persisted rule binding to RuleEngine/RuleRuntime with boot/apply/rollback lifecycle; physical proof pending;\n- [ ] local `Scheduler` for schedules/delayed actions/settling windows;\n''')

config = read('docs/configuration.md')
if '## Stage 7D — persisted rule activation' not in config:
    config += r'''

## Stage 7D — persisted rule activation

Stage 7D binds transactional ConfigurationStore revisions to RuleEngine/RuleRuntime.
New candidates are semantically validated before the inactive slot is written or the
active pointer changes. Existing Stage 7A stored documents remain boot-readable for
migration safety; unsupported legacy rule envelopes do not become executable until
replaced by a valid Stage 7D rule document.

The first executable persisted rule schema is deliberately narrow:

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

Stage 7D supports zero or one executable rule. New configuration is rejected before
activation when type/binding/hysteresis semantics are unsupported. After a successful
apply or rollback commit, PersistedRuleLoader activates the committed JSON/revision
without re-entering the ConfigurationStore mutex and refreshes RuleRuntime eligibility.
No Wi-Fi, MQTT or cloud dependency is involved.

`GET /api/rules/persisted` exposes non-secret binding diagnostics: loaded revision,
loaded rule id and loader result. Virtual input/actuator components are present in the
clean Stage 7D runtime as software-only local bindings; mutation/test HTTP endpoints
remain lab-build-only. Real GPIO remains deferred.
'''
    write('docs/configuration.md', config)

arch = read('docs/architecture.md')
if '## Stage 7D persisted-rule ownership' not in arch:
    arch += r'''

## Stage 7D persisted-rule ownership

ConfigurationStore owns durable bytes and monotonic revision. PersistedRuleLoader owns
translation of a validated active rule document into RuleEngine semantics and asks
RuleRuntime to refresh eligibility. RuleRuntime still owns FSM/event/scheduler state;
TaskScheduler never parses configuration. Apply and rollback activate the newly committed
revision locally, preserving the rule that cloud/network manages but local firmware controls.
'''
    write('docs/architecture.md', arch)

replace_once('docs/README.md',
'''- [x] Stage 7C TaskScheduler/EventBus rule evaluation runtime physically validated\n''',
'''- [x] Stage 7C TaskScheduler/EventBus rule evaluation runtime physically validated\n- [~] Stage 7D persisted rule binding + revision/rollback lifecycle; physical proof pending\n''')

replace_once('README.md',
'''**Stage 7A is validated:** `ConfigurationStore` provides versioned dual-slot NVS transactions with rollback. **Stage 7B is validated:** the minimal hardware-independent hysteresis RuleEngine and virtual input/output path were physically proven, including deadband and disabled-rule behavior; RuleEngine returns desired state and never accesses GPIO. **Stage 7C is validated:** TaskScheduler/EventBus-driven evaluation is one-shot/event-driven, stays disabled without meaningful work, and executed locally during real Wi-Fi/MQTT loss. **Stage 7D is next:** persisted ConfigurationStore rule documents become the source of truth for RuleEngine/RuleRuntime lifecycle and rollback.\n''',
'''**Stages 7A-7C are validated:** transactional configuration, hysteresis semantics, and one-shot local RuleRuntime execution have all been physically proven. **Stage 7D is in progress:** persisted ConfigurationStore rule documents become the source of truth for RuleEngine/RuleRuntime across boot, apply and rollback; physical persistence/rollback proof is pending.\n''')

print('STAGE7D_IMPLEMENT_PATCHED')
