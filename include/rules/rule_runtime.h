#pragma once

#include <Arduino.h>
#include <Fsm.h>
#include <TaskScheduler.h>

#include "core/component_health.h"
#include "core/event_bus.h"
#include "rules/actuator_fault_policy.h"
#include "rules/rule_engine.h"

namespace Rules {

class RuleRuntime {
 public:
  using BoolProvider = bool (*)();
  using FloatProvider = float (*)();
  using HealthProvider = RuntimeCore::HealthState (*)();
  using ApplyDesired = bool (*)(bool desiredOn);

  RuleRuntime(Scheduler& scheduler,
              RuntimeCore::EventBus& events,
              RuleEngine& engine,
              const char* inputSourceId,
              BoolProvider inputReady,
              FloatProvider inputValue,
              HealthProvider dependencyHealth,
              BoolProvider outputState,
              ApplyDesired applyDesired);

  bool begin();
  void refreshEligibility();
  bool requestEvaluation(const char* reason = "request");
  void setFaultPolicy(ActuatorFaultPolicy policy);
  ActuatorFaultPolicy faultPolicy() const { return faultPolicy_; }
  const char* stateName() const;
  bool workTaskEnabled() const { return evaluationTask_.isEnabled(); }
  String statusJson() const;

 private:
  enum class RuntimeState : uint8_t {
    Disabled,
    Armed,
    Evaluating
  };

  enum RuntimeEvent : int {
    EventArm = 1,
    EventDisarm,
    EventEvaluate,
    EventDone
  };

  static RuleRuntime* active_;

  static void enterDisabled();
  static void enterArmed();
  static void enterEvaluating();
  static void evaluationTaskCallback();
  static void eventHandler(const RuntimeCore::Event& event);

  void configureTransitions();
  void setState(RuntimeState next);
  void handleEvent(const RuntimeCore::Event& event);
  void executeEvaluation();
  RuntimeCore::HealthState dependencyHealth() const;
  bool dependencyHealthy() const;

  Scheduler& scheduler_;
  RuntimeCore::EventBus& events_;
  RuleEngine& engine_;
  String inputSourceId_;
  BoolProvider inputReady_;
  FloatProvider inputValue_;
  HealthProvider dependencyHealth_;
  BoolProvider outputState_;
  ApplyDesired applyDesired_;

  mutable Task evaluationTask_;
  State disabledState_;
  State armedState_;
  State evaluatingState_;
  Fsm machine_;

  RuntimeState state_ = RuntimeState::Disabled;
  ActuatorFaultPolicy faultPolicy_ = ActuatorFaultPolicy::SafeOff;
  bool started_ = false;
  bool pending_ = false;
  uint32_t lastTransitionMs_ = 0;
  uint32_t lastRequestMs_ = 0;
  uint32_t lastRunMs_ = 0;
  uint32_t lastPolicyMs_ = 0;
  uint32_t requestCount_ = 0;
  uint32_t scheduledCount_ = 0;
  uint32_t coalescedCount_ = 0;
  uint32_t completedCount_ = 0;
  uint32_t rejectedCount_ = 0;
  uint32_t policyActionCount_ = 0;
  uint32_t alarmCount_ = 0;
  String lastRequestResult_ = "never";
  String lastRunResult_ = "never";
  String lastPolicyResult_ = "never";
};

}  // namespace Rules
