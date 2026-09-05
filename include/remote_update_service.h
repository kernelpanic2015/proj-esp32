#pragma once

#include <Arduino.h>

class AsyncWebServer;

namespace RemoteFirmwareUpdate {

void begin();
void registerRoutes(AsyncWebServer& server);
String statusJson();

}  // namespace RemoteFirmwareUpdate
