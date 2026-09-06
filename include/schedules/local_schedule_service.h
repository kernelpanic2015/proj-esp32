#pragma once

#include <Arduino.h>
#include <Fsm.h>
#include <TaskScheduler.h>

namespace Schedules {

class LocalScheduleService {
 public:
  using ApplyDesired = bool (*)(bool desiredOn);

  LocalScheduleService(Scheduler& scheduler, ApplyDesired applyDesired);

  bool begin();
  bool validateDocument(const String& raw, String& error) const;
  bool activateDocument(const String& raw, uint32_t revision, String& error);

  const char* stateName() const;
  bool workTaskEnabled() const { return actionTask_.isEnabled(); }
  String statusJson() const;

 private:
  enum class ScheduleState : uint8_t {
    Disabled,
    Waiting,
    Firing,
    Completed,
    Fault
  };

  enum ScheduleEvent : int {
    EventDisable = 1,
    EventArm,
    EventFire,
    EventDone,
    EventFail
  };

  struct DelayedAction {
    String id;
    bool enabled = false;
    String target;
    bool desiredOn = false;
    uint32_t delayMs = 0;
  };

  static LocalScheduleService* active_;
  static void enterDisabled();
  static void enterWaiting();
  static void enterFiring();
  static void enterCompleted();
  static void enterFault();
  static void actionTaskCallback();

  void configureTransitions();
  void setState(ScheduleState next);
  void executeAction();
  bool parseDocument(const String& raw, DelayedAction& action, bool& found,
                     String& error) const;

  Scheduler& scheduler_;
  ApplyDesired applyDesired_;
  mutable Task actionTask_;
  State disabledState_;
  State waitingState_;
  State firingState_;
  State completedState_;
  State faultState_;
  Fsm machine_;

  ScheduleState state_ = ScheduleState::Disabled;
  DelayedAction action_;
  bool configured_ = false;
  uint32_t loadedRevision_ = 0;
  uint32_t armedCount_ = 0;
  uint32_t completedCount_ = 0;
  uint32_t failedCount_ = 0;
  uint32_t lastTransitionMs_ = 0;
  uint32_t lastArmedMs_ = 0;
  uint32_t lastCompletedMs_ = 0;
  String lastResult_ = "never";
};

}  // namespace Schedules
