#pragma once

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
using ValidateActiveCallback = bool (*)(const String& activeJson, String& error);
using ActivatedCallback = void (*)(uint32_t revision, const String& activeJson);
void setLifecycleCallbacks(ValidateActiveCallback validator, ActivatedCallback activated);
void registerRoutes(AsyncWebServer& server);

}  // namespace ConfigurationStore
