#pragma once

#include <Arduino.h>

#include "rules/actuator_fault_policy.h"
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
  ActuatorFaultPolicy loadedFaultPolicy() const { return loadedFaultPolicy_; }
  const String& lastResult() const { return lastResult_; }
  String statusJson() const;

 private:
  bool parseDocument(const String& raw, HysteresisRule& rule,
                     ActuatorFaultPolicy& faultPolicy, bool& found,
                     uint32_t& revision, String& error) const;
  bool applyParsed(const HysteresisRule& rule, ActuatorFaultPolicy faultPolicy,
                   bool found, uint32_t revision, String& error);

  RuleEngine& engine_;
  RuleRuntime& runtime_;
  uint32_t loadedRevision_ = 0;
  String loadedRuleId_;
  ActuatorFaultPolicy loadedFaultPolicy_ = ActuatorFaultPolicy::SafeOff;
  String lastResult_ = "never";
};

}  // namespace Rules
