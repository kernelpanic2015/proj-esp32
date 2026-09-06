#include "configuration_store.h"

#include <ArduinoJson.h>
#include <ESPAsyncWebServer.h>
#include <Preferences.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <ctype.h>

namespace {

Preferences configPreferences;
SemaphoreHandle_t configMutex = nullptr;
bool configReady = false;
uint8_t activeSlot = 0;
String activeRaw;
uint32_t activeRevision = 0;
bool recoveredOnBoot = false;
String lastResult = "never";
ConfigurationStore::ValidateActiveCallback ruleValidator = nullptr;
ConfigurationStore::ActivatedCallback activatedCallback = nullptr;

constexpr char NVS_NAMESPACE[] = "app-config";
constexpr char KEY_ACTIVE[] = "active";
constexpr char KEY_SLOT0[] = "slot0";
constexpr char KEY_SLOT1[] = "slot1";
constexpr size_t JSON_CAPACITY = 4096;
constexpr size_t MAX_RULES = 16;
constexpr size_t MAX_SCHEDULES = 16;
constexpr size_t MAX_ID_LENGTH = 48;

class ConfigLock {
 public:
  ConfigLock()
      : locked_(configMutex &&
                xSemaphoreTake(configMutex, pdMS_TO_TICKS(500)) == pdTRUE) {}
  ~ConfigLock() {
    if (locked_) xSemaphoreGive(configMutex);
  }
  bool locked() const { return locked_; }

 private:
  bool locked_;
};

const char* slotKey(uint8_t slot) {
  return slot == 0 ? KEY_SLOT0 : KEY_SLOT1;
}

bool validId(const char* value) {
  if (!value) return false;
  const size_t length = strlen(value);
  if (length == 0 || length > MAX_ID_LENGTH) return false;
  for (size_t i = 0; i < length; ++i) {
    const unsigned char c = static_cast<unsigned char>(value[i]);
    if (!(isalnum(c) || c == '_' || c == '-' || c == '.' || c == ':')) return false;
  }
  return true;
}

bool validateEntryArray(JsonArray array, size_t limit, String& error) {
  if (array.size() > limit) {
    error = "configuration_entry_limit";
    return false;
  }

  for (size_t i = 0; i < array.size(); ++i) {
    JsonVariant entry = array[i];
    if (!entry.is<JsonObject>()) {
      error = "configuration_entry_not_object";
      return false;
    }
    JsonObject object = entry.as<JsonObject>();
    if (!object["id"].is<const char*>() || !validId(object["id"].as<const char*>())) {
      error = "configuration_entry_id_invalid";
      return false;
    }
    if (object.containsKey("enabled") && !object["enabled"].is<bool>()) {
      error = "configuration_entry_enabled_invalid";
      return false;
    }
    for (size_t j = 0; j < i; ++j) {
      const char* previous = array[j]["id"] | "";
      if (strcmp(previous, object["id"].as<const char*>()) == 0) {
        error = "configuration_entry_id_duplicate";
        return false;
      }
    }
  }
  return true;
}

bool validateDocument(DynamicJsonDocument& document, bool requireRevision, String& error) {
  error = "";
  if (!document.is<JsonObject>()) {
    error = "configuration_root_invalid";
    return false;
  }

  JsonObject root = document.as<JsonObject>();
  if (!root["schema"].is<uint32_t>() ||
      root["schema"].as<uint32_t>() != ConfigurationStore::SCHEMA_VERSION) {
    error = "configuration_schema_unsupported";
    return false;
  }
  if (requireRevision && !root["revision"].is<uint32_t>()) {
    error = "configuration_revision_missing";
    return false;
  }
  if (!root["rules"].is<JsonArray>() || !root["schedules"].is<JsonArray>()) {
    error = "configuration_arrays_required";
    return false;
  }
  if (!validateEntryArray(root["rules"].as<JsonArray>(), MAX_RULES, error)) return false;
  if (!validateEntryArray(root["schedules"].as<JsonArray>(), MAX_SCHEDULES, error)) return false;
  return true;
}

bool parseStored(const String& raw, DynamicJsonDocument& document,
                 uint32_t& revisionOut, String& error) {
  revisionOut = 0;
  if (raw.length() == 0 || raw.length() > ConfigurationStore::MAX_CONFIG_JSON_BYTES) {
    error = "configuration_size_invalid";
    return false;
  }
  document.clear();
  const DeserializationError jsonError = deserializeJson(document, raw);
  if (jsonError) {
    error = "configuration_json_invalid";
    return false;
  }
  if (!validateDocument(document, true, error)) return false;
  revisionOut = document["revision"].as<uint32_t>();
  return true;
}

bool canonicalizeCandidate(const String& raw, uint32_t revisionValue,
                           String& canonical, String& error) {
  if (raw.length() == 0 || raw.length() > ConfigurationStore::MAX_CONFIG_JSON_BYTES) {
    error = "configuration_size_invalid";
    return false;
  }

  DynamicJsonDocument document(JSON_CAPACITY);
  const DeserializationError jsonError = deserializeJson(document, raw);
  if (jsonError) {
    error = "configuration_json_invalid";
    return false;
  }
  if (!validateDocument(document, false, error)) return false;

  document["schema"] = ConfigurationStore::SCHEMA_VERSION;
  document["revision"] = revisionValue;
  canonical = "";
  serializeJson(document, canonical);
  if (canonical.length() == 0 || canonical.length() > ConfigurationStore::MAX_CONFIG_JSON_BYTES) {
    error = "configuration_size_invalid";
    return false;
  }
  return true;
}

String defaultConfiguration() {
  StaticJsonDocument<192> document;
  document["schema"] = ConfigurationStore::SCHEMA_VERSION;
  document["revision"] = 0;
  document.createNestedArray("rules");
  document.createNestedArray("schedules");
  String raw;
  serializeJson(document, raw);
  return raw;
}

bool loadSlot(uint8_t slot, String& rawOut, uint32_t& revisionOut) {
  rawOut = configPreferences.getString(slotKey(slot), "");
  DynamicJsonDocument document(JSON_CAPACITY);
  String error;
  return parseStored(rawOut, document, revisionOut, error);
}

bool persistSlotVerified(uint8_t slot, const String& raw, uint32_t expectedRevision,
                         String& verifiedRaw, String& error) {
  if (configPreferences.putString(slotKey(slot), raw) != raw.length()) {
    error = "configuration_slot_write_failed";
    return false;
  }

  uint32_t readRevision = 0;
  if (!loadSlot(slot, verifiedRaw, readRevision) || readRevision != expectedRevision) {
    error = "configuration_slot_verify_failed";
    return false;
  }
  return true;
}

void countsFromRaw(const String& raw, size_t& rules, size_t& schedules) {
  rules = 0;
  schedules = 0;
  DynamicJsonDocument document(JSON_CAPACITY);
  if (deserializeJson(document, raw)) return;
  if (document["rules"].is<JsonArray>()) rules = document["rules"].as<JsonArray>().size();
  if (document["schedules"].is<JsonArray>()) schedules = document["schedules"].as<JsonArray>().size();
}

}  // namespace

namespace ConfigurationStore {

bool begin() {
  if (!configMutex) configMutex = xSemaphoreCreateMutex();
  if (!configMutex) return false;

  ConfigLock lock;
  if (!lock.locked()) return false;
  if (!configPreferences.begin(NVS_NAMESPACE, false)) {
    configReady = false;
    lastResult = "nvs_open_failed";
    return false;
  }

  const uint8_t requestedSlot = configPreferences.getUChar(KEY_ACTIVE, 0);
  String raw;
  uint32_t revisionValue = 0;
  if (requestedSlot <= 1 && loadSlot(requestedSlot, raw, revisionValue)) {
    activeSlot = requestedSlot;
    activeRaw = raw;
    activeRevision = revisionValue;
    configReady = true;
    recoveredOnBoot = false;
    lastResult = "loaded";
    return true;
  }

  const uint8_t fallbackSlot = requestedSlot == 0 ? 1 : 0;
  if (loadSlot(fallbackSlot, raw, revisionValue)) {
    if (configPreferences.putUChar(KEY_ACTIVE, fallbackSlot) != 1) {
      configReady = false;
      lastResult = "recovery_pointer_write_failed";
      return false;
    }
    activeSlot = fallbackSlot;
    activeRaw = raw;
    activeRevision = revisionValue;
    configReady = true;
    recoveredOnBoot = true;
    lastResult = "recovered_previous_slot";
    return true;
  }

  const String defaults = defaultConfiguration();
  String verified;
  String error;
  if (!persistSlotVerified(0, defaults, 0, verified, error) ||
      configPreferences.putUChar(KEY_ACTIVE, 0) != 1) {
    configReady = false;
    lastResult = error.length() ? error : "default_pointer_write_failed";
    return false;
  }
  configPreferences.remove(KEY_SLOT1);
  activeSlot = 0;
  activeRaw = verified;
  activeRevision = 0;
  configReady = true;
  recoveredOnBoot = false;
  lastResult = "defaults_created";
  return true;
}

bool ready() {
  ConfigLock lock;
  return lock.locked() && configReady;
}

uint32_t revision() {
  ConfigLock lock;
  return lock.locked() && configReady ? activeRevision : 0;
}

String activeJson() {
  ConfigLock lock;
  if (!lock.locked() || !configReady) return "{}";
  return activeRaw;
}

String statusJson() {
  bool readySnapshot = false;
  uint8_t slotSnapshot = 0;
  uint32_t revisionSnapshot = 0;
  uint32_t previousRevision = 0;
  bool recoveredSnapshot = false;
  String resultSnapshot = "not_ready";
  String rawSnapshot;

  {
    ConfigLock lock;
    if (lock.locked()) {
      readySnapshot = configReady;
      slotSnapshot = activeSlot;
      revisionSnapshot = activeRevision;
      recoveredSnapshot = recoveredOnBoot;
      resultSnapshot = lastResult;
      rawSnapshot = activeRaw;
      if (configReady) {
        String previousRaw;
        uint32_t candidateRevision = 0;
        if (loadSlot(activeSlot == 0 ? 1 : 0, previousRaw, candidateRevision)) {
          previousRevision = candidateRevision;
        }
      }
    }
  }

  size_t ruleCount = 0;
  size_t scheduleCount = 0;
  countsFromRaw(rawSnapshot, ruleCount, scheduleCount);

  StaticJsonDocument<512> document;
  document["ready"] = readySnapshot;
  document["schema"] = SCHEMA_VERSION;
  document["revision"] = revisionSnapshot;
  document["active_slot"] = slotSnapshot;
  document["previous_revision"] = previousRevision;
  document["recovered_on_boot"] = recoveredSnapshot;
  document["rules_count"] = ruleCount;
  document["schedules_count"] = scheduleCount;
  document["max_json_bytes"] = MAX_CONFIG_JSON_BYTES;
  document["last_result"] = resultSnapshot;
  String output;
  serializeJson(document, output);
  return output;
}

bool apply(const String& candidateJson, String& error) {
  error = "";
  ConfigLock lock;
  if (!lock.locked() || !configReady) {
    error = "configuration_not_ready";
    return false;
  }
  if (activeRevision == UINT32_MAX) {
    error = "configuration_revision_exhausted";
    return false;
  }

  const uint32_t nextRevision = activeRevision + 1;
  String canonical;
  if (!canonicalizeCandidate(candidateJson, nextRevision, canonical, error)) return false;

  if (ruleValidator) {
    String semanticError;
    if (!ruleValidator(canonical, semanticError)) {
      error = semanticError.length() ? semanticError : "configuration_rule_semantic_invalid";
      return false;
    }
  }

  const uint8_t nextSlot = activeSlot == 0 ? 1 : 0;
  String verified;
  if (!persistSlotVerified(nextSlot, canonical, nextRevision, verified, error)) return false;

  if (configPreferences.putUChar(KEY_ACTIVE, nextSlot) != 1) {
    error = "configuration_pointer_write_failed";
    return false;
  }

  activeSlot = nextSlot;
  activeRaw = verified;
  activeRevision = nextRevision;
  recoveredOnBoot = false;
  lastResult = "applied";
  if (activatedCallback) activatedCallback(activeRevision, activeRaw);
  return true;
}

void setLifecycleCallbacks(ValidateActiveCallback validator, ActivatedCallback activated) {
  ConfigLock lock;
  if (!lock.locked()) return;
  ruleValidator = validator;
  activatedCallback = activated;
}

bool rollback(String& error) {
  error = "";
  ConfigLock lock;
  if (!lock.locked() || !configReady) {
    error = "configuration_not_ready";
    return false;
  }
  if (activeRevision == UINT32_MAX) {
    error = "configuration_revision_exhausted";
    return false;
  }

  const uint8_t previousSlot = activeSlot == 0 ? 1 : 0;
  String previousRaw;
  uint32_t previousRevision = 0;
  if (!loadSlot(previousSlot, previousRaw, previousRevision)) {
    error = "configuration_previous_missing";
    return false;
  }

  DynamicJsonDocument document(JSON_CAPACITY);
  String parseError;
  if (deserializeJson(document, previousRaw) ||
      !validateDocument(document, true, parseError)) {
    error = parseError.length() ? parseError : "configuration_previous_invalid";
    return false;
  }

  const uint32_t nextRevision = activeRevision + 1;
  document["revision"] = nextRevision;
  String rollbackRaw;
  serializeJson(document, rollbackRaw);
  if (rollbackRaw.length() == 0 || rollbackRaw.length() > MAX_CONFIG_JSON_BYTES) {
    error = "configuration_size_invalid";
    return false;
  }

  if (ruleValidator) {
    String semanticError;
    if (!ruleValidator(rollbackRaw, semanticError)) {
      error = semanticError.length() ? semanticError : "configuration_rule_semantic_invalid";
      return false;
    }
  }

  String verified;
  if (!persistSlotVerified(previousSlot, rollbackRaw, nextRevision, verified, error)) return false;
  if (configPreferences.putUChar(KEY_ACTIVE, previousSlot) != 1) {
    error = "configuration_pointer_write_failed";
    return false;
  }

  activeSlot = previousSlot;
  activeRaw = verified;
  activeRevision = nextRevision;
  recoveredOnBoot = false;
  lastResult = "rolled_back";
  if (activatedCallback) activatedCallback(activeRevision, activeRaw);
  return true;
}

void registerRoutes(AsyncWebServer& server) {
  server.on("/api/configuration/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", statusJson());
  });

  server.on("/api/configuration", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", activeJson());
  });

  server.on("/api/configuration/apply", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("config", true)) {
      request->send(400, "application/json", "{\"error\":\"configuration_required\"}");
      return;
    }
    String error;
    if (!apply(request->getParam("config", true)->value(), error)) {
      request->send(400, "application/json",
                    String("{\"error\":\"") + error + "\"}");
      return;
    }
    request->send(200, "application/json", statusJson());
  });

  server.on("/api/configuration/rollback", HTTP_POST, [](AsyncWebServerRequest* request) {
    String error;
    if (!rollback(error)) {
      request->send(400, "application/json",
                    String("{\"error\":\"") + error + "\"}");
      return;
    }
    request->send(200, "application/json", statusJson());
  });
}

}  // namespace ConfigurationStore
