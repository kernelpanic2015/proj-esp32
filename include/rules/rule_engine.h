#pragma once

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
