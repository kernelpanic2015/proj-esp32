#pragma once

#include <Arduino.h>

class AsyncWebServer;

namespace FirmwareUpdate {

void begin(bool criticalStorageReady);
void registerRoutes(AsyncWebServer& server);
void tick(bool criticalStorageReady);
String statusJson();

}  // namespace FirmwareUpdate
