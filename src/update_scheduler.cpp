#include "update_scheduler.h"

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
