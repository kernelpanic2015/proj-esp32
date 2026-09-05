#pragma once

#include <Arduino.h>

class AsyncWebServer;

namespace FirmwareUpdateScheduler {

// Boot-relative, nonblocking scheduler for automatic update checks.
// It never auto-applies firmware and never gates local device control.
void begin();
void tick(bool networkAvailable);
String statusJson();
void registerRoutes(AsyncWebServer& server);

}  // namespace FirmwareUpdateScheduler
