#pragma once

#include <Arduino.h>
#include <Fsm.h>
#include <TaskScheduler.h>

#include "core/event_bus.h"
#include "rules/rule_engine.h"

namespace Rules {

class RuleRuntime {
 public:
  using BoolProvider = bool (*)();
  using FloatProvider = float (*)();
  using ApplyDesired = bool (*)(bool desiredOn);

  RuleRuntime(Scheduler& scheduler,
              RuntimeCore::EventBus& events,
              RuleEngine& engine,
              const char* inputSourceId,
              BoolProvider inputReady,
              FloatProvider inputValue,
              BoolProvider outputState,
              ApplyDesired applyDesired);

  bool begin();
  void refreshEligibility();
  bool requestEvaluation(const char* reason = "request");
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

  Scheduler& scheduler_;
  RuntimeCore::EventBus& events_;
  RuleEngine& engine_;
  String inputSourceId_;
  BoolProvider inputReady_;
  FloatProvider inputValue_;
  BoolProvider outputState_;
  ApplyDesired applyDesired_;

  mutable Task evaluationTask_;
  State disabledState_;
  State armedState_;
  State evaluatingState_;
  Fsm machine_;

  RuntimeState state_ = RuntimeState::Disabled;
  bool started_ = false;
  bool pending_ = false;
  uint32_t lastTransitionMs_ = 0;
  uint32_t lastRequestMs_ = 0;
  uint32_t lastRunMs_ = 0;
  uint32_t requestCount_ = 0;
  uint32_t scheduledCount_ = 0;
  uint32_t coalescedCount_ = 0;
  uint32_t completedCount_ = 0;
  uint32_t rejectedCount_ = 0;
  String lastRequestResult_ = "never";
  String lastRunResult_ = "never";
};

}  // namespace Rules
