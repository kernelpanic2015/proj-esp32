#include "update_scheduler.h"

#include "remote_update_service.h"
#include "update_policy.h"

#include <ESPAsyncWebServer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <stdint.h>

namespace {

SemaphoreHandle_t schedulerMutex = nullptr;
bool schedulerReady = false;
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

constexpr uint32_t RETRY_DELAY_MS = 15000;

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

bool timeReached(uint32_t now, uint32_t target) {
  return static_cast<int32_t>(now - target) >= 0;
}

uint32_t intervalMs(uint32_t intervalSeconds) {
  // Policy validation currently caps this at 7 days, safely inside uint32_t ms.
  return intervalSeconds * 1000UL;
}

void applyPolicySnapshot(uint32_t now, bool enabled, uint32_t intervalSeconds,
                         uint32_t revision) {
  SchedulerLock lock;
  if (!lock.locked()) return;

  const bool changed = revision != observedRevision ||
                       enabled != observedEnabled ||
                       intervalSeconds != observedIntervalSeconds;
  if (!changed) return;

  observedRevision = revision;
  observedEnabled = enabled;
  observedIntervalSeconds = intervalSeconds;
  schedulerArmed = enabled;
  nextDueMs = enabled ? now + intervalMs(intervalSeconds) : 0;
  lastRequestResult = enabled ? "armed" : "disabled";
}

}  // namespace

namespace FirmwareUpdateScheduler {

void begin() {
  if (!schedulerMutex) schedulerMutex = xSemaphoreCreateMutex();
  SchedulerLock lock;
  if (!lock.locked()) return;

  schedulerReady = true;
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

void tick(bool networkAvailable) {
  if (!schedulerReady) return;

  bool enabled = false;
  String manifestUrl;
  uint32_t intervalSeconds = 0;
  uint32_t revision = 0;
  String policyError;
  if (!FirmwareUpdatePolicy::automaticCheckConfig(
          enabled, manifestUrl, intervalSeconds, revision, policyError)) {
    SchedulerLock lock;
    if (lock.locked()) {
      schedulerArmed = false;
      lastRequestResult = policyError.length() ? policyError : "policy_unavailable";
    }
    return;
  }

  const uint32_t now = millis();
  applyPolicySnapshot(now, enabled, intervalSeconds, revision);
  if (!enabled || !networkAvailable) return;

  bool due = false;
  {
    SchedulerLock lock;
    if (!lock.locked()) return;
    due = schedulerArmed && timeReached(now, nextDueMs);
    if (!due) return;

    // Reserve the normal next slot before leaving the lock. A transient trigger
    // rejection can shorten this to RETRY_DELAY_MS below.
    lastAttemptMs = now;
    ++attemptCount;
    nextDueMs = now + intervalMs(intervalSeconds);
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
  // A busy update service is not a policy failure. Retry soon in RAM without
  // changing policy revision or generating an NVS write.
  if (error == "remote_update_busy" || error == "state_lock_timeout") {
    nextDueMs = now + RETRY_DELAY_MS;
  }
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
