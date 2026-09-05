#include "update_policy.h"

#include "firmware_identity.h"

#include <ArduinoJson.h>
#include <ESPAsyncWebServer.h>
#include <Preferences.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <ctype.h>

namespace {

struct PolicyData {
  uint32_t schema = 1;
  uint32_t revision = 0;
  bool enabled = false;
  String manifestUrl;
  String channel = FirmwareIdentity::CHANNEL;
  uint32_t intervalSeconds = 21600;
  uint32_t lastCheckEpoch = 0;
  String lastResult = "never";
};

Preferences policyPreferences;
SemaphoreHandle_t policyMutex = nullptr;
bool policyReady = false;
PolicyData policy;

constexpr char NVS_NAMESPACE[] = "fw-update";
constexpr char NVS_POLICY_KEY[] = "policy";
constexpr uint32_t MIN_INTERVAL_SECONDS = 60;
constexpr uint32_t MAX_INTERVAL_SECONDS = 604800;
constexpr size_t MAX_POLICY_JSON_BYTES = 1024;

class PolicyLock {
 public:
  PolicyLock()
      : locked_(policyMutex &&
                xSemaphoreTake(policyMutex, pdMS_TO_TICKS(300)) == pdTRUE) {}
  ~PolicyLock() {
    if (locked_) xSemaphoreGive(policyMutex);
  }
  bool locked() const { return locked_; }

 private:
  bool locked_;
};

bool validManifestUrl(const String& url) {
  if (url.length() == 0) return true;
  if (url.length() < 16 || url.length() > 384) return false;
  if (!url.startsWith("https://") || !url.endsWith("/manifest.json")) return false;
  for (size_t i = 0; i < url.length(); ++i) {
    const unsigned char c = static_cast<unsigned char>(url[i]);
    if (c <= 0x20 || c == 0x7f || c == '"' || c == '\\') return false;
  }
  return true;
}

bool validResult(const String& value) {
  if (value.length() == 0 || value.length() > 64) return false;
  for (size_t i = 0; i < value.length(); ++i) {
    const unsigned char c = static_cast<unsigned char>(value[i]);
    if (!(isalnum(c) || c == '_' || c == '-' || c == '.' || c == ':')) {
      return false;
    }
  }
  return true;
}

bool validPolicy(const PolicyData& candidate) {
  if (candidate.schema != 1) return false;
  if (candidate.channel != FirmwareIdentity::CHANNEL) return false;
  if (candidate.intervalSeconds < MIN_INTERVAL_SECONDS ||
      candidate.intervalSeconds > MAX_INTERVAL_SECONDS) {
    return false;
  }
  if (!validManifestUrl(candidate.manifestUrl)) return false;
  if (candidate.enabled && candidate.manifestUrl.length() == 0) return false;
  if (!validResult(candidate.lastResult)) return false;
  return true;
}

String serializePolicy(const PolicyData& value) {
  StaticJsonDocument<768> document;
  document["schema"] = value.schema;
  document["revision"] = value.revision;
  document["enabled"] = value.enabled;
  document["manifest_url"] = value.manifestUrl;
  document["channel"] = value.channel;
  document["interval_seconds"] = value.intervalSeconds;
  document["last_check_epoch"] = value.lastCheckEpoch;
  document["last_result"] = value.lastResult;
  String output;
  serializeJson(document, output);
  return output;
}

bool deserializePolicy(const String& raw, PolicyData& output) {
  if (raw.length() == 0 || raw.length() > MAX_POLICY_JSON_BYTES) return false;
  StaticJsonDocument<768> document;
  if (deserializeJson(document, raw)) return false;

  if (!document["schema"].is<uint32_t>() ||
      !document["revision"].is<uint32_t>() ||
      !document["enabled"].is<bool>() ||
      !document["manifest_url"].is<const char*>() ||
      !document["channel"].is<const char*>() ||
      !document["interval_seconds"].is<uint32_t>() ||
      !document["last_check_epoch"].is<uint32_t>() ||
      !document["last_result"].is<const char*>()) {
    return false;
  }

  output.schema = document["schema"].as<uint32_t>();
  output.revision = document["revision"].as<uint32_t>();
  output.enabled = document["enabled"].as<bool>();
  output.manifestUrl = document["manifest_url"].as<const char*>();
  output.channel = document["channel"].as<const char*>();
  output.intervalSeconds = document["interval_seconds"].as<uint32_t>();
  output.lastCheckEpoch = document["last_check_epoch"].as<uint32_t>();
  output.lastResult = document["last_result"].as<const char*>();
  return validPolicy(output);
}

bool persistLocked(const PolicyData& candidate) {
  const String raw = serializePolicy(candidate);
  if (raw.length() == 0 || raw.length() > MAX_POLICY_JSON_BYTES) return false;
  if (policyPreferences.putString(NVS_POLICY_KEY, raw) != raw.length()) return false;
  policy = candidate;
  return true;
}

bool parseEnabled(String value, bool& output) {
  value.trim();
  value.toLowerCase();
  if (value == "1" || value == "true" || value == "on") {
    output = true;
    return true;
  }
  if (value == "0" || value == "false" || value == "off") {
    output = false;
    return true;
  }
  return false;
}

}  // namespace

namespace FirmwareUpdatePolicy {

bool begin() {
  if (!policyMutex) policyMutex = xSemaphoreCreateMutex();
  if (!policyMutex) return false;

  PolicyLock lock;
  if (!lock.locked()) return false;

  if (!policyPreferences.begin(NVS_NAMESPACE, false)) {
    policyReady = false;
    return false;
  }

  PolicyData loaded;
  const String raw = policyPreferences.getString(NVS_POLICY_KEY, "");
  if (raw.length() == 0) {
    policy = PolicyData();
    policyReady = true;
    return true;
  }

  if (!deserializePolicy(raw, loaded)) {
    policy = PolicyData();
    policy.lastResult = "policy_invalid_defaults";
    policyReady = true;
    return true;
  }

  policy = loaded;
  policyReady = true;
  return true;
}

bool ready() {
  PolicyLock lock;
  return lock.locked() && policyReady;
}

String statusJson() {
  PolicyData snapshot;
  bool readySnapshot = false;
  {
    PolicyLock lock;
    if (lock.locked()) {
      snapshot = policy;
      readySnapshot = policyReady;
    }
  }

  StaticJsonDocument<896> document;
  document["ready"] = readySnapshot;
  document["schema"] = snapshot.schema;
  document["revision"] = snapshot.revision;
  document["enabled"] = snapshot.enabled;
  document["manifest_url"] = snapshot.manifestUrl;
  document["channel"] = snapshot.channel;
  document["interval_seconds"] = snapshot.intervalSeconds;
  document["last_check_epoch"] = snapshot.lastCheckEpoch;
  document["last_result"] = snapshot.lastResult;
  String output;
  serializeJson(document, output);
  return output;
}

bool configuredManifestUrl(String& manifestUrl, String& error) {
  manifestUrl = "";
  error = "";
  PolicyLock lock;
  if (!lock.locked() || !policyReady) {
    error = "update_policy_not_ready";
    return false;
  }
  if (policy.manifestUrl.length() == 0) {
    error = "update_policy_manifest_url_missing";
    return false;
  }
  manifestUrl = policy.manifestUrl;
  return true;
}

bool recordResult(const String& result) {
  if (!validResult(result)) return false;
  PolicyLock lock;
  if (!lock.locked() || !policyReady) return false;
  PolicyData candidate = policy;
  candidate.lastResult = result;
  return persistLocked(candidate);
}

void registerRoutes(AsyncWebServer& server) {
  server.on("/api/update/policy", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", statusJson());
  });

  server.on("/api/update/policy", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("enabled", true) ||
        !request->hasParam("manifest_url", true) ||
        !request->hasParam("interval_seconds", true)) {
      request->send(400, "application/json",
                    "{\"error\":\"policy_fields_required\"}");
      return;
    }

    bool enabled = false;
    if (!parseEnabled(request->getParam("enabled", true)->value(), enabled)) {
      request->send(400, "application/json",
                    "{\"error\":\"policy_enabled_invalid\"}");
      return;
    }

    String manifestUrl = request->getParam("manifest_url", true)->value();
    manifestUrl.trim();
    const uint32_t interval =
        static_cast<uint32_t>(request->getParam("interval_seconds", true)->value().toInt());
    String channel = FirmwareIdentity::CHANNEL;
    if (request->hasParam("channel", true)) {
      channel = request->getParam("channel", true)->value();
      channel.trim();
    }

    {
    PolicyLock lock;
    if (!lock.locked() || !policyReady) {
      request->send(503, "application/json",
                    "{\"error\":\"update_policy_not_ready\"}");
      return;
    }

    PolicyData candidate = policy;
    candidate.revision = policy.revision + 1;
    candidate.enabled = enabled;
    candidate.manifestUrl = manifestUrl;
    candidate.channel = channel;
    candidate.intervalSeconds = interval;
    candidate.lastResult = "policy_updated";

    if (!validPolicy(candidate)) {
      request->send(400, "application/json",
                    "{\"error\":\"update_policy_invalid\"}");
      return;
    }
    if (!persistLocked(candidate)) {
      request->send(500, "application/json",
                    "{\"error\":\"update_policy_persist_failed\"}");
      return;
    }

    }

    request->send(200, "application/json", statusJson());
  });
}

}  // namespace FirmwareUpdatePolicy
