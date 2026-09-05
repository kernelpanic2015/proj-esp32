#pragma once

#include <Arduino.h>
#include <Fsm.h>

#include "core/component_registry.h"
#include "core/event_bus.h"

namespace RuntimeCore {

enum class SupervisorState : uint8_t {
  Initializing,
  Running,
  Degraded,
  Fault
};

class Supervisor {
 public:
  Supervisor(ComponentRegistry& registry, EventBus& events);

  void begin();
  void evaluate();

  SupervisorState state() const { return state_; }
  const char* stateName() const;
  HealthState healthState() const;
  String statusJson() const;

 private:
  enum EventId : int {
    EventAllHealthy = 1,
    EventDegraded,
    EventFault
  };

  static Supervisor* active_;
  static void enterInitializing();
  static void enterRunning();
  static void enterDegraded();
  static void enterFault();

  void setState(SupervisorState next);
  void configureTransitions();
  void countHealth();
  void requestState(SupervisorState desired);

  ComponentRegistry& registry_;
  EventBus& events_;
  State initializingState_;
  State runningState_;
  State degradedState_;
  State faultState_;
  Fsm machine_;

  SupervisorState state_ = SupervisorState::Initializing;
  bool started_ = false;
  uint32_t lastTransitionMs_ = 0;
  uint32_t evaluationCount_ = 0;
  uint16_t okCount_ = 0;
  uint16_t degradedCount_ = 0;
  uint16_t faultCount_ = 0;
  uint16_t recoveringCount_ = 0;
  uint16_t disabledCount_ = 0;
};

}  // namespace RuntimeCore
