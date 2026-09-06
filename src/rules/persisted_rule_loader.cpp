#include "rules/persisted_rule_loader.h"

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
