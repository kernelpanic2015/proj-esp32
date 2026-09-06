#include "rules/rule_engine.h"

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
  json += "\"mode\":\"hysteresis_v1\",";
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
