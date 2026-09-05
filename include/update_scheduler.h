#pragma once

#include <Arduino.h>

class AsyncWebServer;
class Scheduler;

namespace FirmwareUpdateScheduler {

// Cooperative automatic-update scheduler. TaskScheduler owns timing;
// the remote UpdateManager still owns check/apply and the scheduler remains
// check-only. Local control never depends on this service.
void begin(Scheduler& scheduler);
void setNetworkAvailable(bool available);
String statusJson();
void registerRoutes(AsyncWebServer& server);

}  // namespace FirmwareUpdateScheduler
