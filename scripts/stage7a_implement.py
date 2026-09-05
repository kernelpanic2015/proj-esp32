from pathlib import Path

HEADER = r'''#pragma once

#include <Arduino.h>

class AsyncWebServer;

namespace ConfigurationStore {

constexpr uint32_t SCHEMA_VERSION = 1;
constexpr size_t MAX_CONFIG_JSON_BYTES = 3072;

bool begin();
bool ready();
uint32_t revision();
String statusJson();
String activeJson();
bool apply(const String& candidateJson, String& error);
bool rollback(String& error);
void registerRoutes(AsyncWebServer& server);

}  // namespace ConfigurationStore
'''

SOURCE = r'''#include "configuration_store.h"

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
  return true;
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
'''

CONFIG_DOC = r'''# Persistent configuration — Stage 7

Stage 7 introduces the configuration/control plane that local automation will consume. The invariant remains: **the cloud manages; the device controls**. Once configuration has been accepted, its execution must not depend on Wi-Fi, MQTT, HTTP or an external agent.

## Stage 7A — ConfigurationStore

`ConfigurationStore` uses a two-slot NVS transaction model in namespace `app-config`:

```text
slot0 <----> slot1
     active pointer
```

An update is committed in this order:

1. parse and validate the candidate in RAM;
2. assign the next monotonic device revision;
3. write the inactive slot;
4. read the slot back and validate it again;
5. flip the single-byte `active` pointer only after verification.

A power loss before step 5 leaves the old configuration active. The previously active slot remains available for rollback. Rollback copies the previous payload into a new monotonic revision instead of moving the revision number backwards.

Boot recovery first tries the selected slot, then the other valid slot, then creates a revision-0 default document if neither slot is usable.

Current schema 1 envelope:

```json
{
  "schema": 1,
  "revision": 0,
  "rules": [],
  "schedules": []
}
```

Store-level validation currently checks the schema/envelope, bounded array sizes, entry object shape, safe unique `id` values and optional boolean `enabled`. Rule/schedule semantics are deliberately not executed by Stage 7A; the RuleEngine and local scheduler will add semantic validation before those entries become effective.

Limits in the first implementation:

- maximum serialized configuration: 3072 bytes;
- maximum rules: 16;
- maximum schedules: 16;
- IDs: 1–48 characters, limited to alphanumeric plus `_ - . :`.

HTTP development/control surfaces:

```text
GET  /api/configuration/status
GET  /api/configuration
POST /api/configuration/apply       form field: config=<json>
POST /api/configuration/rollback
```

These routes manage a local NVS store; HTTP availability is not required for configuration execution. Authentication/network-exposure hardening remains a separate production concern.

## TaskScheduler + FSM rule for Stage 7

Configuration persistence itself is synchronous and short. Periodic rule evaluation, delayed actions, settling windows, retries and schedules will use TaskScheduler. FSMs remain owners of state/behavior. Tasks should be disabled while their work is not meaningful.
'''

p = Path('include/configuration_store.h')
p.write_text(HEADER)
Path('src/configuration_store.cpp').write_text(SOURCE)
Path('docs/configuration.md').write_text(CONFIG_DOC)

# main.cpp integration
p = Path('src/main.cpp')
s = p.read_text()
s = s.replace('#include "update_scheduler.h"\n', '#include "update_scheduler.h"\n#include "configuration_store.h"\n', 1)
s = s.replace('json += "\\\"update_scheduler\\\":" + FirmwareUpdateScheduler::statusJson() + ",";\n',
              'json += "\\\"update_scheduler\\\":" + FirmwareUpdateScheduler::statusJson() + ",";\n  json += "\\\"configuration\\\":" + ConfigurationStore::statusJson() + ",";\n', 1)
s = s.replace('    body += "update_scheduler=/api/update/scheduler\\n";\n',
              '    body += "update_scheduler=/api/update/scheduler\\n";\n    body += "configuration=/api/configuration\\n";\n    body += "configuration_status=/api/configuration/status\\n";\n', 1)
s = s.replace('  FirmwareUpdateScheduler::registerRoutes(server);\n',
              '  FirmwareUpdateScheduler::registerRoutes(server);\n  ConfigurationStore::registerRoutes(server);\n', 1)
s = s.replace('  loadMqttConfig();\n\n  runtimeEvents.subscribe(handleRuntimeEvent);',
              '  loadMqttConfig();\n  if (!ConfigurationStore::begin()) {\n    Serial.println("CONFIGURATION_STORE_INIT_FAILED");\n  }\n\n  runtimeEvents.subscribe(handleRuntimeEvent);', 1)
p.write_text(s)

# ROADMAP Stage 7 start
p = Path('docs/ROADMAP.md')
s = p.read_text()
s = s.replace('## Stage 7 — Persistent configuration and local rule engine\n\nImplement versioned, validated, transactional configuration with rollback to previous configuration.\n\nCore services:\n\n- `ConfigurationStore`;\n- `RuleEngine`;\n- `Scheduler`;\n- dependency/fault policies for actuators.\n',
'''## Stage 7 — Persistent configuration and local rule engine [in progress — Stage 7A]\n\nImplement versioned, validated, transactional configuration with rollback to previous configuration.\n\nCore services:\n\n- [x] **Stage 7A foundation** — dual-slot transactional NVS `ConfigurationStore`, monotonic revision, verified inactive-slot write, boot fallback and rollback API;\n- [ ] physically prove apply -> reboot persistence -> second apply -> rollback -> reboot persistence;\n- [ ] `RuleEngine` with semantic rule validation and TaskScheduler-driven evaluation;\n- [ ] local `Scheduler` for schedules/delayed actions/settling windows;\n- [ ] dependency/fault policies for actuators.\n\nStage 7A stores rule/schedule envelopes but does not execute them yet. Rule semantics become active only after the RuleEngine validator/evaluator is introduced.\n''', 1)
p.write_text(s)

# docs index
p = Path('docs/README.md')
s = p.read_text()
s = s.replace('10. [`dependencies.md`](dependencies.md)', '10. [`configuration.md`](configuration.md) — Stage 7 transactional NVS configuration model and local-control contract.\n11. [`dependencies.md`](dependencies.md)', 1)
s = s.replace('11. [`references.md`](references.md)', '12. [`references.md`](references.md)', 1)
if '- [~] Stage 7A transactional ConfigurationStore implementation/build validation' not in s:
    marker = '- [x] add Supervisor FSM over the common component health model and physically prove `RUNNING -> DEGRADED -> RUNNING`\n'
    s = s.replace(marker, marker + '- [~] Stage 7A transactional ConfigurationStore implementation/build validation\n', 1)
p.write_text(s)

# architecture
p = Path('docs/architecture.md')
s = p.read_text()
if '### Stage 7A configuration transaction boundary' not in s:
    s += r'''

### Stage 7A configuration transaction boundary

`ConfigurationStore` is the durable boundary for local automation configuration. It uses two NVS slots plus a one-byte active pointer. A candidate is validated, written to the inactive slot, read back, validated again and only then activated. The old slot remains the rollback source. Rollback creates a new monotonic revision containing the previous payload.

The store is intentionally not the RuleEngine. Stage 7A only guarantees persistence, structural validation, revisioning and recovery. RuleEngine/Scheduler will consume snapshots and add semantic validation/execution under the established TaskScheduler + FSM ownership model.
'''
p.write_text(s)

# bootstrap / README concise next state
p = Path('docs/BOOTSTRAP.md')
s = p.read_text()
s = s.replace('1. Start **Stage 7** with a versioned, validated, transactional `ConfigurationStore` in NVS.\n',
              '1. Continue **Stage 7A**: the dual-slot transactional `ConfigurationStore` is implemented; physically prove apply/reboot/rollback persistence before starting RuleEngine execution.\n', 1)
p.write_text(s)

p = Path('README.md')
s = p.read_text()
if 'Stage 7A has started' not in s:
    anchor = '**Stage 6 core physical baseline:** `0.1.25/build 26`, `app0`, native OTA `VALID`, application `ONLINE`, `connectivity=ONLINE/OK`, Supervisor `RUNNING/OK`, Wi-Fi + MQTT/TLS connected and EventBus `dropped=0`. OTA scheduling, MQTT reconnect/telemetry and Wi-Fi reconnect timing use the shared TaskScheduler cooperative runtime; work tasks stay disabled when no meaningful work exists. Stage 7 is next.'
    replacement = anchor + '\n\n**Stage 7A has started:** `ConfigurationStore` introduces versioned dual-slot NVS transactions with verified inactive-slot writes, monotonic revisions, boot fallback and rollback. Rule execution is not enabled until the RuleEngine semantic layer is added and validated.'
    s = s.replace(anchor, replacement, 1)
p.write_text(s)

print('STAGE7A_IMPLEMENT_PATCH_OK')
