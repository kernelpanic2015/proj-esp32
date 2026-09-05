#pragma once

#include <Arduino.h>

class AsyncWebServer;

String firmwareVersionJson();
void registerFirmwareMetadataRoutes(AsyncWebServer& server);
