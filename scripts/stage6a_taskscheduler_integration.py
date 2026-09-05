from pathlib import Path

# 1) Add TaskScheduler dependency.
p = Path('platformio.ini')
s = p.read_text()
needle = '    https://github.com/jonblack/arduino-fsm.git\n'
if 'arkhipenko/TaskScheduler' not in s:
    s = s.replace(needle, needle + '    arkhipenko/TaskScheduler@^4.0.8\n', 1)
p.write_text(s)

# 2) Introduce Stage 6 core contracts. These are deliberately small and
# allocation-light; execution cadence belongs to TaskScheduler, not Registry.
Path('include/core').mkdir(parents=True, exist_ok=True)
Path('src/core').mkdir(parents=True, exist_ok=True)

Path('include/core/component_health.h').write_text(r'''#pragma once

#include <Arduino.h>

namespace RuntimeCore {

enum class HealthState : uint8_t {
  OK,
  DEGRADED,
  FAULT,
  RECOVERING,
  DISABLED
};

struct ComponentHealth {
  HealthState state = HealthState::DISABLED;
  uint32_t lastSuccessMs = 0;
  uint32_t lastErrorMs = 0;
  uint32_t errorCount = 0;
  String faultCode;
};

const char* healthStateName(HealthState state);
String healthJson(const ComponentHealth& health);

}  // namespace RuntimeCore
''')

Path('src/core/component_health.cpp').write_text(r'''#include "core/component_health.h"

namespace RuntimeCore {

const char* healthStateName(HealthState state) {
  switch (state) {
    case HealthState::OK: return "OK";
    case HealthState::DEGRADED: return "DEGRADED";
    case HealthState::FAULT: return "FAULT";
    case HealthState::RECOVERING: return "RECOVERING";
    case HealthState::DISABLED: return "DISABLED";
  }
  return "UNKNOWN";
}

String healthJson(const ComponentHealth& health) {
  String json = "{";
  json += "\"state\":\"" + String(healthStateName(health.state)) + "\",";
  json += "\"last_success_ms\":" + String(health.lastSuccessMs) + ",";
  json += "\"last_error_ms\":" + String(health.lastErrorMs) + ",";
  json += "\"error_count\":" + String(health.errorCount) + ",";
  json += "\"fault_code\":\"" + health.faultCode + "\"";
  json += "}";
  return json;
}

}  // namespace RuntimeCore
''')

Path('include/core/component.h').write_text(r'''#pragma once

#include <Arduino.h>
#include "core/component_health.h"

namespace RuntimeCore {

// A component owns behavior/state. TaskScheduler owns when its work is due.
// FSMs inside components decide whether requested work is legal in that state.
class Component {
 public:
  virtual ~Component() = default;
  virtual const char* id() const = 0;
  virtual bool begin() = 0;
  virtual const char* stateName() const = 0;
  virtual ComponentHealth health() const = 0;
};

}  // namespace RuntimeCore
''')

Path('include/core/component_registry.h').write_text(r'''#pragma once

#include <Arduino.h>
#include "core/component.h"

namespace RuntimeCore {

class ComponentRegistry {
 public:
  static constexpr size_t MAX_COMPONENTS = 24;

  bool add(Component& component);
  bool beginAll();
  size_t size() const { return count_; }
  Component* at(size_t index) const;
  Component* find(const char* id) const;
  String statusJson() const;

 private:
  Component* components_[MAX_COMPONENTS] = {};
  size_t count_ = 0;
};

}  // namespace RuntimeCore
''')

Path('src/core/component_registry.cpp').write_text(r'''#include "core/component_registry.h"

#include <string.h>

namespace RuntimeCore {

bool ComponentRegistry::add(Component& component) {
  if (count_ >= MAX_COMPONENTS || find(component.id())) return false;
  components_[count_++] = &component;
  return true;
}

bool ComponentRegistry::beginAll() {
  bool ok = true;
  for (size_t i = 0; i < count_; ++i) {
    if (!components_[i]->begin()) ok = false;
  }
  return ok;
}

Component* ComponentRegistry::at(size_t index) const {
  return index < count_ ? components_[index] : nullptr;
}

Component* ComponentRegistry::find(const char* id) const {
  if (!id) return nullptr;
  for (size_t i = 0; i < count_; ++i) {
    if (strcmp(components_[i]->id(), id) == 0) return components_[i];
  }
  return nullptr;
}

String ComponentRegistry::statusJson() const {
  String json = "{\"count\":" + String(count_) + ",\"components\":[";
  for (size_t i = 0; i < count_; ++i) {
    if (i) json += ',';
    Component* c = components_[i];
    json += "{\"id\":\"" + String(c->id()) + "\",";
    json += "\"state\":\"" + String(c->stateName()) + "\",";
    json += "\"health\":" + healthJson(c->health()) + "}";
  }
  json += "]}";
  return json;
}

}  // namespace RuntimeCore
''')

Path('include/core/event_bus.h').write_text(r'''#pragma once

#include <Arduino.h>

namespace RuntimeCore {

struct Event {
  uint16_t type = 0;
  uint32_t atMs = 0;
  int32_t value = 0;
  char source[24] = {};
};

using EventHandler = void (*)(const Event& event);

class EventBus {
 public:
  static constexpr size_t QUEUE_SIZE = 24;
  static constexpr size_t MAX_HANDLERS = 12;

  bool subscribe(EventHandler handler);
  bool post(uint16_t type, const char* source, int32_t value = 0);
  size_t process(size_t maxEvents = 8);
  size_t pending() const { return count_; }
  uint32_t dropped() const { return dropped_; }

 private:
  Event queue_[QUEUE_SIZE] = {};
  EventHandler handlers_[MAX_HANDLERS] = {};
  size_t head_ = 0;
  size_t tail_ = 0;
  size_t count_ = 0;
  size_t handlerCount_ = 0;
  uint32_t dropped_ = 0;
};

}  // namespace RuntimeCore
''')

Path('src/core/event_bus.cpp').write_text(r'''#include "core/event_bus.h"

#include <stdio.h>
#include <string.h>

namespace RuntimeCore {

bool EventBus::subscribe(EventHandler handler) {
  if (!handler || handlerCount_ >= MAX_HANDLERS) return false;
  for (size_t i = 0; i < handlerCount_; ++i) {
    if (handlers_[i] == handler) return true;
  }
  handlers_[handlerCount_++] = handler;
  return true;
}

bool EventBus::post(uint16_t type, const char* source, int32_t value) {
  if (count_ >= QUEUE_SIZE) {
    ++dropped_;
    return false;
  }

  Event& event = queue_[tail_];
  event.type = type;
  event.atMs = millis();
  event.value = value;
  snprintf(event.source, sizeof(event.source), "%s", source ? source : "");
  tail_ = (tail_ + 1) % QUEUE_SIZE;
  ++count_;
  return true;
}

size_t EventBus::process(size_t maxEvents) {
  size_t processed = 0;
  while (count_ && processed < maxEvents) {
    Event event = queue_[head_];
    head_ = (head_ + 1) % QUEUE_SIZE;
    --count_;
    for (size_t i = 0; i < handlerCount_; ++i) handlers_[i](event);
    ++processed;
  }
  return processed;
}

}  // namespace RuntimeCore
''')

# 3) Migrate the already-proven automatic update scheduler from hand-rolled
# millis polling to TaskScheduler. The low-rate policy watcher is always useful;
# the actual automatic-check task stays disabled until policy.enabled=true.
Path('include/update_scheduler.h').write_text(r'''#pragma once

#include <Arduino.h>

class AsyncWebServer;
class Scheduler;

namespace FirmwareUpdateScheduler {

// Cooperative automatic-update scheduler. TaskScheduler owns timing;
// the remote UpdateManager still owns check/apply and the scheduler remains
// check-only. Local control never depends on this service.
void begin(Scheduler& scheduler);
void setNetworkAvailable(bool available);
String statusJson();
void registerRoutes(AsyncWebServer& server);

}  // namespace FirmwareUpdateScheduler
''')

Path('src/update_scheduler.cpp').write_text(r'''#include "update_scheduler.h"

#include "remote_update_service.h"
#include "update_policy.h"

#include <ESPAsyncWebServer.h>
#include <TaskScheduler.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <stdint.h>

namespace {

SemaphoreHandle_t schedulerMutex = nullptr;
bool schedulerReady = false;
bool networkAvailable = false;
bool schedulerArmed = false;
bool observedEnabled = false;
uint32_t observedRevision = UINT32_MAX;
uint32_t observedIntervalSeconds = 0;
uint32_t nextDueMs = 0;
uint32_t lastAttemptMs = 0;
uint32_t lastAcceptedMs = 0;
uint32_t attemptCount = 0;
uint32_t acceptedCount = 0;
String lastRequestResult = "never";

constexpr uint32_t POLICY_WATCH_INTERVAL_MS = 1000;
constexpr uint32_t RETRY_DELAY_MS = 15000;

void policyWatchCallback();
void automaticCheckCallback();

Task policyWatchTask(POLICY_WATCH_INTERVAL_MS, TASK_FOREVER, &policyWatchCallback);
Task automaticCheckTask(60000, TASK_FOREVER, &automaticCheckCallback);

class SchedulerLock {
 public:
  SchedulerLock()
      : locked_(schedulerMutex &&
                xSemaphoreTake(schedulerMutex, pdMS_TO_TICKS(100)) == pdTRUE) {}
  ~SchedulerLock() {
    if (locked_) xSemaphoreGive(schedulerMutex);
  }
  bool locked() const { return locked_; }

 private:
  bool locked_;
};

uint32_t intervalMs(uint32_t seconds) {
  return seconds * 1000UL;
}

void disarm(const String& reason) {
  automaticCheckTask.disable();
  SchedulerLock lock;
  if (!lock.locked()) return;
  schedulerArmed = false;
  nextDueMs = 0;
  lastRequestResult = reason;
}

void applyPolicy(bool enabled, uint32_t intervalSeconds, uint32_t revision) {
  bool changed = false;
  {
    SchedulerLock lock;
    if (!lock.locked()) return;
    changed = revision != observedRevision || enabled != observedEnabled ||
              intervalSeconds != observedIntervalSeconds;
    if (!changed) return;
    observedRevision = revision;
    observedEnabled = enabled;
    observedIntervalSeconds = intervalSeconds;
  }

  if (!enabled) {
    disarm("disabled");
    return;
  }

  const uint32_t delayMs = intervalMs(intervalSeconds);
  automaticCheckTask.setInterval(delayMs);
  automaticCheckTask.restartDelayed(delayMs);

  SchedulerLock lock;
  if (!lock.locked()) return;
  schedulerArmed = true;
  nextDueMs = millis() + delayMs;
  lastRequestResult = "armed";
}

void policyWatchCallback() {
  bool enabled = false;
  String manifestUrl;
  uint32_t intervalSeconds = 0;
  uint32_t revision = 0;
  String error;
  if (!FirmwareUpdatePolicy::automaticCheckConfig(
          enabled, manifestUrl, intervalSeconds, revision, error)) {
    disarm(error.length() ? error : "policy_unavailable");
    return;
  }
  applyPolicy(enabled, intervalSeconds, revision);
}

void automaticCheckCallback() {
  bool enabled = false;
  String manifestUrl;
  uint32_t intervalSeconds = 0;
  uint32_t revision = 0;
  String policyError;
  if (!FirmwareUpdatePolicy::automaticCheckConfig(
          enabled, manifestUrl, intervalSeconds, revision, policyError)) {
    disarm(policyError.length() ? policyError : "policy_unavailable");
    return;
  }
  if (!enabled) {
    disarm("disabled");
    return;
  }

  bool haveNetwork = false;
  {
    SchedulerLock lock;
    if (!lock.locked()) return;
    haveNetwork = networkAvailable;
  }

  const uint32_t now = millis();
  const uint32_t normalIntervalMs = intervalMs(intervalSeconds);
  automaticCheckTask.setInterval(normalIntervalMs);

  if (!haveNetwork) {
    automaticCheckTask.restartDelayed(RETRY_DELAY_MS);
    SchedulerLock lock;
    if (lock.locked()) {
      nextDueMs = now + RETRY_DELAY_MS;
      lastRequestResult = "network_unavailable";
    }
    return;
  }

  {
    SchedulerLock lock;
    if (!lock.locked()) return;
    lastAttemptMs = now;
    ++attemptCount;
    nextDueMs = now + normalIntervalMs;
    lastRequestResult = "requesting";
  }

  String error;
  const bool accepted = RemoteFirmwareUpdate::requestCheck(manifestUrl, error);

  SchedulerLock lock;
  if (!lock.locked()) return;
  if (accepted) {
    lastAcceptedMs = now;
    ++acceptedCount;
    lastRequestResult = "accepted";
    return;
  }

  lastRequestResult = error.length() ? error : "request_rejected";
  if (error == "remote_update_busy" || error == "state_lock_timeout") {
    automaticCheckTask.restartDelayed(RETRY_DELAY_MS);
    nextDueMs = now + RETRY_DELAY_MS;
  }
}

}  // namespace

namespace FirmwareUpdateScheduler {

void begin(Scheduler& scheduler) {
  if (!schedulerMutex) schedulerMutex = xSemaphoreCreateMutex();
  {
    SchedulerLock lock;
    if (!lock.locked()) return;
    schedulerReady = true;
    networkAvailable = false;
    schedulerArmed = false;
    observedEnabled = false;
    observedRevision = UINT32_MAX;
    observedIntervalSeconds = 0;
    nextDueMs = 0;
    lastAttemptMs = 0;
    lastAcceptedMs = 0;
    attemptCount = 0;
    acceptedCount = 0;
    lastRequestResult = "never";
  }

  scheduler.addTask(policyWatchTask);
  scheduler.addTask(automaticCheckTask);
  automaticCheckTask.disable();
  policyWatchTask.enable();
  // Apply persisted policy immediately instead of waiting one watch interval.
  policyWatchCallback();
}

void setNetworkAvailable(bool available) {
  SchedulerLock lock;
  if (lock.locked()) networkAvailable = available;
}

String statusJson() {
  bool ready = false;
  bool armed = false;
  bool enabled = false;
  uint32_t revision = 0;
  uint32_t intervalSeconds = 0;
  uint32_t dueMs = 0;
  uint32_t attemptMs = 0;
  uint32_t acceptedMs = 0;
  uint32_t attempts = 0;
  uint32_t accepted = 0;
  String result = "lock_timeout";

  {
    SchedulerLock lock;
    if (lock.locked()) {
      ready = schedulerReady;
      armed = schedulerArmed;
      enabled = observedEnabled;
      revision = observedRevision == UINT32_MAX ? 0 : observedRevision;
      intervalSeconds = observedIntervalSeconds;
      dueMs = nextDueMs;
      attemptMs = lastAttemptMs;
      acceptedMs = lastAcceptedMs;
      attempts = attemptCount;
      accepted = acceptedCount;
      result = lastRequestResult;
    }
  }

  String json = "{";
  json += "\"ready\":" + String(ready ? "true" : "false") + ",";
  json += "\"armed\":" + String(armed ? "true" : "false") + ",";
  json += "\"enabled\":" + String(enabled ? "true" : "false") + ",";
  json += "\"policy_revision\":" + String(revision) + ",";
  json += "\"interval_seconds\":" + String(intervalSeconds) + ",";
  json += "\"next_due_ms\":" + String(dueMs) + ",";
  json += "\"last_attempt_ms\":" + String(attemptMs) + ",";
  json += "\"last_accepted_ms\":" + String(acceptedMs) + ",";
  json += "\"attempt_count\":" + String(attempts) + ",";
  json += "\"accepted_count\":" + String(accepted) + ",";
  json += "\"last_request_result\":\"" + result + "\"";
  json += "}";
  return json;
}

void registerRoutes(AsyncWebServer& server) {
  server.on("/api/update/scheduler", HTTP_GET,
            [](AsyncWebServerRequest* request) {
              request->send(200, "application/json", statusJson());
            });
}

}  // namespace FirmwareUpdateScheduler
''')

# 4) Wire the shared cooperative scheduler into main while deliberately leaving
# the remaining proven loop logic untouched for incremental migration.
p = Path('src/main.cpp')
s = p.read_text()
if '#include <TaskScheduler.h>' not in s:
    s = s.replace('#include <Fsm.h>\n', '#include <Fsm.h>\n#include <TaskScheduler.h>\n', 1)
if 'Scheduler cooperativeScheduler;' not in s:
    s = s.replace('DoubleResetDetector* drd = nullptr;\n', 'DoubleResetDetector* drd = nullptr;\nScheduler cooperativeScheduler;\n', 1)
s = s.replace('FirmwareUpdateScheduler::begin();', 'FirmwareUpdateScheduler::begin(cooperativeScheduler);', 1)
# Remove direct tick calls from the old hand-rolled scheduler.
s = s.replace('    FirmwareUpdateScheduler::tick(false);\n', '', 1)
s = s.replace('  FirmwareUpdateScheduler::tick(true);\n', '', 1)
# Execute cooperative tasks once per loop, with current network eligibility.
needle = '  wifiManager.process();\n  machine.run_machine();\n  FirmwareUpdate::tick(preferencesReady);\n'
replacement = ('  wifiManager.process();\n'
               '  machine.run_machine();\n'
               '  FirmwareUpdate::tick(preferencesReady);\n'
               '  FirmwareUpdateScheduler::setNetworkAvailable(\n'
               '      WiFi.status() == WL_CONNECTED && !wifiManager.getConfigPortalActive());\n'
               '  cooperativeScheduler.execute();\n')
if needle not in s:
    raise SystemExit('main loop integration anchor not found')
s = s.replace(needle, replacement, 1)
p.write_text(s)

# 5) Advance the existing physical scheduler smoke script to the next candidate
# pair so the TaskScheduler migration gets the same real-device proof.
p = Path('scripts/smoke_update_scheduler.sh')
s = p.read_text()
s = s.replace('FIXTURE_PORT=${FIXTURE_PORT:-8768}', 'FIXTURE_PORT=${FIXTURE_PORT:-8769}', 1)
s = s.replace('"version":"0.1.12"', '"version":"0.1.14"', 1)
s = s.replace('"build":13', '"build":15', 1)
s = s.replace('--version 0.1.13-remote-test --build 14', '--version 0.1.15-remote-test --build 16', 1)
s = s.replace('--version 0.1.14 --build 15', '--version 0.1.16 --build 17', 1)
s = s.replace("wait_for_transition '0.1.13-remote-test' 14 app0", "wait_for_transition '0.1.15-remote-test' 16 app0", 1)
s = s.replace("wait_for_online '0.1.13-remote-test' 14", "wait_for_online '0.1.15-remote-test' 16", 1)
s = s.replace('"candidate_build":15', '"candidate_build":17', 1)
s = s.replace("wait_for_transition '0.1.14' 15 app1", "wait_for_transition '0.1.16' 17 app1", 1)
# final assertions (later occurrences)
s = s.replace('"version":"0.1.14"', '"version":"0.1.16"')
s = s.replace('"build":15', '"build":17')
s = s.replace('AUTOMATIC_UPDATE_CHECK_SCHEDULER_PROOF_OK', 'TASKSCHEDULER_AUTOMATIC_UPDATE_PROOF_OK', 1)
p.write_text(s)

# 6) Record Stage 6A architecture direction.
p = Path('docs/architecture.md')
s = p.read_text()
section = r'''

## Cooperative runtime: TaskScheduler + FSM (Stage 6A)

The project now adopts `arkhipenko/TaskScheduler` alongside `jonblack/arduino-fsm`.
Their responsibilities are intentionally different:

- **TaskScheduler = when work becomes eligible to run**;
- **FSM = current state and whether that work is legal/meaningful**;
- **EventBus = what happened**;
- **Component = who owns the behavior**;
- **Supervisor = aggregate health/recovery policy**;
- **RuleEngine = desired functional outcome**.

A task may remain disabled until work is meaningful. Delayed activation/restart is a
first-class mechanism for sensor warm-up, actuator settling, retry/backoff and
minimum on/off times. Components should prefer TaskScheduler timing primitives to
hand-rolled `millis()` polling as they are migrated.

The first migration is the automatic firmware-check scheduler. Its low-frequency
policy watcher is always enabled, while the actual remote-check task is disabled
until persisted `policy.enabled=true`; enabling the policy arms it with a delayed
first run. The OTA path remains check-only and does not auto-apply firmware.

Stage 6 core contracts now exist under `include/core` / `src/core`:
`Component`, `ComponentHealth`, `ComponentRegistry`, and a bounded `EventBus`.
The registry is discovery/health metadata, not a polling loop: execution cadence
belongs to TaskScheduler.
'''
if '## Cooperative runtime: TaskScheduler + FSM (Stage 6A)' not in s:
    s += section
p.write_text(s)

p = Path('docs/ROADMAP.md')
s = p.read_text()
s = s.replace('## Stage 6 — Core modular runtime', '## Stage 6 — Core modular runtime [in progress]', 1)
s = s.replace('Introduce:\n\n- `Component` interface;', 'Introduce:\n\n- [x] TaskScheduler cooperative runtime alongside `arduino-fsm`;\n- [x] `Component` interface;', 1)
s = s.replace('- `ComponentRegistry`;\n- common `ComponentHealth` model;\n- internal event bus;\n- `Supervisor` FSM;', '- [x] `ComponentRegistry`;\n- [x] common `ComponentHealth` model;\n- [x] bounded internal event bus foundation;\n- [ ] wire initial real components into the registry;\n- [ ] `Supervisor` FSM;', 1)
p.write_text(s)

p = Path('docs/dependencies.md')
s = p.read_text()
if 'TaskScheduler' not in s:
    s += r'''

## TaskScheduler

- Upstream: `arkhipenko/TaskScheduler`
- Baseline: 4.0.8
- Role: cooperative timing/execution eligibility for component work.
- Kept alongside `arduino-fsm`: TaskScheduler decides **when**; FSM decides
  **state/behavior**. Tasks should be disabled when no work is meaningful and
  use delayed enable/restart for warm-up, settling, retry and backoff.
- This does not make blocking callbacks safe. Every cooperative callback must
  return quickly; genuinely blocking/heavy work remains a candidate for a
  FreeRTOS worker that reports completion through events.
'''
p.write_text(s)

print('STAGE6A_TASKSCHEDULER_STAGED')
