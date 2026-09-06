from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(rel, content):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def replace_once(rel, old, new):
    p = ROOT / rel
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing patch anchor in {rel}: {old[:160]!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


write("include/rules/rule_runtime.h", r'''#pragma once

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

  Task evaluationTask_;
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
''')

write("src/rules/rule_runtime.cpp", r'''#include "rules/rule_runtime.h"

#include <string.h>

#include "core/runtime_events.h"

namespace Rules {

RuleRuntime* RuleRuntime::active_ = nullptr;

RuleRuntime::RuleRuntime(Scheduler& scheduler,
                         RuntimeCore::EventBus& events,
                         RuleEngine& engine,
                         const char* inputSourceId,
                         BoolProvider inputReady,
                         FloatProvider inputValue,
                         BoolProvider outputState,
                         ApplyDesired applyDesired)
    : scheduler_(scheduler),
      events_(events),
      engine_(engine),
      inputSourceId_(inputSourceId ? inputSourceId : ""),
      inputReady_(inputReady),
      inputValue_(inputValue),
      outputState_(outputState),
      applyDesired_(applyDesired),
      evaluationTask_(TASK_IMMEDIATE, TASK_ONCE, evaluationTaskCallback,
                      &scheduler_, false),
      disabledState_(enterDisabled, nullptr, nullptr),
      armedState_(enterArmed, nullptr, nullptr),
      evaluatingState_(enterEvaluating, nullptr, nullptr),
      machine_(&disabledState_) {
  active_ = this;
  configureTransitions();
}

void RuleRuntime::configureTransitions() {
  machine_.add_transition(&disabledState_, &armedState_, EventArm, nullptr);
  machine_.add_transition(&armedState_, &disabledState_, EventDisarm, nullptr);
  machine_.add_transition(&armedState_, &evaluatingState_, EventEvaluate, nullptr);
  machine_.add_transition(&evaluatingState_, &armedState_, EventDone, nullptr);
  machine_.add_transition(&evaluatingState_, &disabledState_, EventDisarm, nullptr);
}

bool RuleRuntime::begin() {
  if (started_) return true;
  active_ = this;
  if (!events_.subscribe(eventHandler)) {
    lastRunResult_ = "event_subscribe_failed";
    return false;
  }
  machine_.run_machine();
  started_ = true;
  refreshEligibility();
  return true;
}

void RuleRuntime::setState(RuntimeState next) {
  state_ = next;
  lastTransitionMs_ = millis();
}

void RuleRuntime::enterDisabled() {
  if (active_) active_->setState(RuntimeState::Disabled);
}

void RuleRuntime::enterArmed() {
  if (active_) active_->setState(RuntimeState::Armed);
}

void RuleRuntime::enterEvaluating() {
  if (active_) active_->setState(RuntimeState::Evaluating);
}

void RuleRuntime::refreshEligibility() {
  if (!started_) return;

  if (!engine_.enabled()) {
    pending_ = false;
    if (evaluationTask_.isEnabled()) evaluationTask_.disable();
    if (state_ != RuntimeState::Disabled) {
      machine_.trigger(EventDisarm);
      machine_.run_machine();
    }
    if (!engine_.configured()) {
      lastRequestResult_ = "no_active_rule";
    } else {
      lastRequestResult_ = "rule_disabled";
    }
    return;
  }

  if (state_ == RuntimeState::Disabled) {
    machine_.trigger(EventArm);
    machine_.run_machine();
  }
}

bool RuleRuntime::requestEvaluation(const char* reason) {
  ++requestCount_;
  lastRequestMs_ = millis();
  refreshEligibility();

  if (!engine_.enabled()) {
    ++rejectedCount_;
    lastRequestResult_ = "rule_disabled";
    return false;
  }
  if (!inputReady_ || !inputReady_()) {
    ++rejectedCount_;
    lastRequestResult_ = "input_not_ready";
    return false;
  }
  if (state_ != RuntimeState::Armed) {
    ++rejectedCount_;
    lastRequestResult_ = "runtime_not_armed";
    return false;
  }

  if (evaluationTask_.isEnabled()) {
    pending_ = true;
    ++coalescedCount_;
    lastRequestResult_ = "coalesced";
    return true;
  }

  pending_ = true;
  if (!evaluationTask_.restart()) {
    pending_ = false;
    ++rejectedCount_;
    lastRequestResult_ = "scheduler_rejected";
    return false;
  }
  ++scheduledCount_;
  lastRequestResult_ = reason && reason[0] ? String("scheduled:") + reason : "scheduled";
  return true;
}

void RuleRuntime::eventHandler(const RuntimeCore::Event& event) {
  if (active_) active_->handleEvent(event);
}

void RuleRuntime::handleEvent(const RuntimeCore::Event& event) {
  if (event.type != static_cast<uint16_t>(RuntimeCore::RuntimeEventType::InputValueChanged)) {
    return;
  }
  if (inputSourceId_.length() && strcmp(event.source, inputSourceId_.c_str()) != 0) {
    return;
  }
  requestEvaluation("input_event");
}

void RuleRuntime::evaluationTaskCallback() {
  if (active_) active_->executeEvaluation();
}

void RuleRuntime::executeEvaluation() {
  pending_ = false;
  if (!engine_.enabled()) {
    ++rejectedCount_;
    lastRunResult_ = "rule_disabled";
    refreshEligibility();
    return;
  }
  if (!inputReady_ || !inputReady_() || !inputValue_ || !outputState_ || !applyDesired_) {
    ++rejectedCount_;
    lastRunResult_ = "runtime_provider_unavailable";
    return;
  }

  machine_.trigger(EventEvaluate);
  machine_.run_machine();

  const float input = inputValue_();
  const bool current = outputState_();
  bool desired = current;
  RuleDecision decision = RuleDecision::None;
  String error;
  const bool evaluated = engine_.evaluate(input, current, desired, decision, error);

  if (!evaluated) {
    ++rejectedCount_;
    lastRunResult_ = error.length() ? error : "evaluation_failed";
  } else if (decision == RuleDecision::Disabled) {
    ++rejectedCount_;
    lastRunResult_ = "rule_disabled";
  } else if (!applyDesired_(desired)) {
    ++rejectedCount_;
    lastRunResult_ = "actuator_rejected";
  } else {
    ++completedCount_;
    lastRunResult_ = engine_.lastDecisionName();
  }
  lastRunMs_ = millis();

  if (engine_.enabled()) {
    machine_.trigger(EventDone);
  } else {
    machine_.trigger(EventDisarm);
  }
  machine_.run_machine();
}

const char* RuleRuntime::stateName() const {
  switch (state_) {
    case RuntimeState::Disabled: return "DISABLED";
    case RuntimeState::Armed: return "ARMED";
    case RuntimeState::Evaluating: return "EVALUATING";
  }
  return "UNKNOWN";
}

String RuleRuntime::statusJson() const {
  String json = "{";
  json += "\"state\":\"" + String(stateName()) + "\",";
  json += "\"active_rule\":" + String(engine_.enabled() ? "true" : "false") + ",";
  json += "\"input_source\":\"" + inputSourceId_ + "\",";
  json += "\"work_task_enabled\":" + String(evaluationTask_.isEnabled() ? "true" : "false") + ",";
  json += "\"pending\":" + String(pending_ ? "true" : "false") + ",";
  json += "\"last_transition_ms\":" + String(lastTransitionMs_) + ",";
  json += "\"last_request_ms\":" + String(lastRequestMs_) + ",";
  json += "\"last_run_ms\":" + String(lastRunMs_) + ",";
  json += "\"request_count\":" + String(requestCount_) + ",";
  json += "\"scheduled_count\":" + String(scheduledCount_) + ",";
  json += "\"coalesced_count\":" + String(coalescedCount_) + ",";
  json += "\"completed_count\":" + String(completedCount_) + ",";
  json += "\"rejected_count\":" + String(rejectedCount_) + ",";
  json += "\"last_request_result\":\"" + lastRequestResult_ + "\",";
  json += "\"last_run_result\":\"" + lastRunResult_ + "\"";
  json += "}";
  return json;
}

}  // namespace Rules
''')

# The engine is now scheduling-independent; Stage 7C runtime owns automatic invocation.
replace_once(
    "src/rules/rule_engine.cpp",
    'json += "\\\"mode\\\":\\\"manual_stage7b\\\",";',
    'json += "\\\"mode\\\":\\\"hysteresis_v1\\\",";'
)

# Main includes and runtime providers.
replace_once(
    "src/main.cpp",
    '#include "rules/rule_engine.h"\n',
    '#include "rules/rule_engine.h"\n#include "rules/rule_runtime.h"\n'
)

replace_once(
    "src/main.cpp",
    '''Rules::RuleEngine ruleEngine(runtimeEvents);\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\nComponents::VirtualInputComponent virtualTemperature(runtimeEvents, "virtual.temperature");\nComponents::VirtualActuatorComponent virtualHeater(runtimeEvents, "virtual.heater");\n#endif\n\nbool mqttConfigured();\n''',
    '''Rules::RuleEngine ruleEngine(runtimeEvents);\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\nComponents::VirtualInputComponent virtualTemperature(runtimeEvents, "virtual.temperature");\nComponents::VirtualActuatorComponent virtualHeater(runtimeEvents, "virtual.heater");\n#endif\n\nbool ruleInputReady();\nfloat ruleInputValue();\nbool ruleOutputState();\nbool ruleApplyDesired(bool desiredOn);\nRules::RuleRuntime ruleRuntime(cooperativeScheduler, runtimeEvents, ruleEngine,\n                               "virtual.temperature", ruleInputReady, ruleInputValue,\n                               ruleOutputState, ruleApplyDesired);\n\nbool mqttConfigured();\n'''
)

replace_once(
    "src/main.cpp",
    '''void runMqttTelemetryTask();\nString mqttRuntimeStatusJson();\n''',
    '''void runMqttTelemetryTask();\nString mqttRuntimeStatusJson();\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\nvoid runRuleTestInputTask();\n#endif\n'''
)

replace_once(
    "src/main.cpp",
    '''Task mqttTelemetryTask(ProjectConfig::HEARTBEAT_INTERVAL_MS, TASK_FOREVER,\n                       runMqttTelemetryTask, &cooperativeScheduler, false);\n\nbool webStarted = false;\n''',
    '''Task mqttTelemetryTask(ProjectConfig::HEARTBEAT_INTERVAL_MS, TASK_FOREVER,\n                       runMqttTelemetryTask, &cooperativeScheduler, false);\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\nTask ruleTestInputTask(TASK_IMMEDIATE, TASK_ONCE, runRuleTestInputTask,\n                       &cooperativeScheduler, false);\nfloat ruleTestPendingInput = 0.0f;\n#endif\n\nbool webStarted = false;\n'''
)

replace_once(
    "src/main.cpp",
    '''bool runtimeMqttConfigured() {\n  return mqttConfigured();\n}\n\nvoid sampleConnectivityComponent() {\n''',
    '''bool runtimeMqttConfigured() {\n  return mqttConfigured();\n}\n\nbool ruleInputReady() {\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n  return virtualTemperature.hasValue();\n#else\n  return false;\n#endif\n}\n\nfloat ruleInputValue() {\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n  return virtualTemperature.value();\n#else\n  return 0.0f;\n#endif\n}\n\nbool ruleOutputState() {\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n  return virtualHeater.isOn();\n#else\n  return false;\n#endif\n}\n\nbool ruleApplyDesired(bool desiredOn) {\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\n  return virtualHeater.applyDesired(desiredOn);\n#else\n  (void)desiredOn;\n  return false;\n#endif\n}\n\n#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS\nvoid runRuleTestInputTask() {\n  virtualTemperature.setValue(ruleTestPendingInput);\n}\n#endif\n\nvoid sampleConnectivityComponent() {\n'''
)

replace_once(
    "src/main.cpp",
    '''  json += "\\\"rule_engine\\\":" + ruleEngine.statusJson() + ",";\n  json += "\\\"components\\\":" + runtimeComponents.statusJson() + ",";\n''',
    '''  json += "\\\"rule_engine\\\":" + ruleEngine.statusJson() + ",";\n  json += "\\\"rule_runtime\\\":" + ruleRuntime.statusJson() + ",";\n  json += "\\\"components\\\":" + runtimeComponents.statusJson() + ",";\n'''
)

# Add a standard read-only runtime endpoint while preserving Stage 7B status endpoint.
replace_once(
    "src/main.cpp",
    '''  server.on("/api/rules/status", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", ruleEngine.statusJson());\n  });\n\n''',
    '''  server.on("/api/rules/status", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", ruleEngine.statusJson());\n  });\n\n  server.on("/api/rules/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", ruleRuntime.statusJson());\n  });\n\n'''
)

replace_once(
    "src/main.cpp",
    '''    body += "rules_status=/api/rules/status\\n";\n    body += "components=/api/components\\n";\n''',
    '''    body += "rules_status=/api/rules/status\\n";\n    body += "rules_runtime=/api/rules/runtime\\n";\n    body += "components=/api/components\\n";\n'''
)

# Existing Stage 7B configure/reset paths now synchronize runtime eligibility.
replace_once(
    "src/main.cpp",
    '''    virtualHeater.enable(false);\n    request->send(200, "application/json", ruleEngine.statusJson());\n''',
    '''    virtualHeater.enable(false);\n    ruleRuntime.refreshEligibility();\n    request->send(200, "application/json", ruleEngine.statusJson());\n'''
)

replace_once(
    "src/main.cpp",
    '''    ruleEngine.clear();\n    virtualTemperature.disable();\n''',
    '''    ruleEngine.clear();\n    ruleRuntime.refreshEligibility();\n    virtualTemperature.disable();\n'''
)

# Add delayed local input injection used solely to prove rule execution during Wi-Fi/MQTT loss.
lab_routes = r'''#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS
  server.on("/api/test/rules/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {
    String json = "{\"engine\":" + ruleEngine.statusJson() +
                  ",\"runtime\":" + ruleRuntime.statusJson() +
                  ",\"input\":" + virtualTemperature.statusJson() +
                  ",\"actuator\":" + virtualHeater.statusJson() + "}";
    request->send(200, "application/json", json);
  });

  server.on("/api/test/rules/input/delayed", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("value", true) || !request->hasParam("delay_ms", true)) {
      request->send(400, "application/json", "{\"error\":\"value_and_delay_required\"}");
      return;
    }
    const float value = request->getParam("value", true)->value().toFloat();
    const long parsedDelay = request->getParam("delay_ms", true)->value().toInt();
    if (parsedDelay < 0 || parsedDelay > 15000) {
      request->send(400, "application/json", "{\"error\":\"delay_out_of_range\"}");
      return;
    }
    ruleTestPendingInput = value;
    if (!ruleTestInputTask.restartDelayed(static_cast<unsigned long>(parsedDelay))) {
      request->send(500, "application/json", "{\"error\":\"scheduler_rejected\"}");
      return;
    }
    String json = "{\"accepted\":true,\"delay_ms\":" + String(parsedDelay) +
                  ",\"value\":" + String(value, 3) + "}";
    request->send(202, "application/json", json);
  });
#endif

'''
replace_once("src/main.cpp", "  registerFirmwareMetadataRoutes(server);\n", lab_routes + "  registerFirmwareMetadataRoutes(server);\n")

replace_once(
    "src/main.cpp",
    '''  if (!ruleEngine.begin()) {\n    Serial.println("RULE_ENGINE_INIT_FAILED");\n  }\n\n  runtimeEvents.subscribe(handleRuntimeEvent);\n''',
    '''  if (!ruleEngine.begin()) {\n    Serial.println("RULE_ENGINE_INIT_FAILED");\n  }\n\n  runtimeEvents.subscribe(handleRuntimeEvent);\n  if (!ruleRuntime.begin()) {\n    Serial.println("RULE_RUNTIME_INIT_FAILED");\n  }\n'''
)

# Documentation: mark implementation checkpoint; physical validation remains pending.
replace_once(
    "docs/ROADMAP.md",
    '- [ ] **Stage 7C** — TaskScheduler-driven/event-forced evaluation with work task disabled when no active rules;',
    '- [~] **Stage 7C** — TaskScheduler-driven/event-forced evaluation implemented; physical offline-path proof pending;'
)

config = (ROOT / "docs/configuration.md").read_text(encoding="utf-8")
if "## Stage 7C — event-driven rule runtime" not in config:
    config += r'''

## Stage 7C — event-driven rule runtime

Stage 7C introduces `RuleRuntime`, which connects the validated hysteresis RuleEngine to
TaskScheduler and EventBus without moving state ownership into the scheduler.

```text
VirtualInputComponent
      |
      | InputValueChanged
      v
   EventBus
      |
      v
 RuleRuntime FSM
 DISABLED <-> ARMED -> EVALUATING -> ARMED
      |
      | one-shot work request
      v
 TaskScheduler
      |
      v
 RuleEngine -> desired state -> ActuatorComponent
```

The runtime owns a single `TASK_ONCE` evaluation work task. The task stays disabled
while no active rule exists and also stays disabled while an active rule is merely
armed. An input event schedules one evaluation for the next cooperative scheduler pass;
after the callback completes, TaskScheduler disables the one-shot task again.

This deliberately separates three concepts:

- `ARMED` means a rule is eligible to react;
- `work_task_enabled=true` means an evaluation is actually pending/running;
- `DISABLED` means no active rule exists, not a fault.

Repeated requests while the work task is already enabled are coalesced instead of
creating parallel rule evaluations. `GET /api/rules/runtime` exposes FSM state,
work-task enable state, request/scheduled/coalesced/completed/rejected counters and
last request/run results.

The controlled lab build also includes a delayed virtual-input endpoint. It exists only
to prove that a locally scheduled sensor event can run while Wi-Fi and MQTT are absent;
it is removed from the clean image.
'''
    (ROOT / "docs/configuration.md").write_text(config, encoding="utf-8")

arch = (ROOT / "docs/architecture.md").read_text(encoding="utf-8")
if "## Stage 7C RuleRuntime scheduling boundary" not in arch:
    arch += r'''

## Stage 7C RuleRuntime scheduling boundary

`RuleRuntime` is the adapter between EventBus/TaskScheduler and RuleEngine. Its FSM owns
runtime eligibility (`DISABLED`, `ARMED`, `EVALUATING`); TaskScheduler owns only when
the one-shot evaluation callback executes. RuleEngine still owns functional decision
semantics and the actuator component owns application of desired state.

A healthy armed rule therefore consumes no periodic evaluation task. Work appears only
when an input event makes evaluation meaningful. This is the same platform rule used by
sensor warm-up/retry work: tasks exist, but remain disabled until state makes them useful.
'''
    (ROOT / "docs/architecture.md").write_text(arch, encoding="utf-8")

print("STAGE7C_IMPLEMENT_PATCHED")
