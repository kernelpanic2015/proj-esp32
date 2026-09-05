#pragma once

#include <Arduino.h>

class AsyncWebServer;

namespace RemoteFirmwareUpdate {

void begin();
void registerRoutes(AsyncWebServer& server);
String statusJson();

// Transport-independent trigger API. Web, MQTT and later automatic policy
// call these same functions; none implements a separate OTA engine.
bool requestCheck(const String& manifestUrl, String& error);
bool requestApply(String& error);

}  // namespace RemoteFirmwareUpdate
