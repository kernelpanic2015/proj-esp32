#include "firmware_metadata.h"

#include <ESPAsyncWebServer.h>

#include "firmware_identity.h"

String firmwareVersionJson() {
  String json = "{";
  json += "\"model\":\"" + String(FirmwareIdentity::MODEL) + "\",";
  json += "\"hardware_revision\":" + String(FirmwareIdentity::HARDWARE_REVISION) + ",";
  json += "\"version\":\"" + String(FirmwareIdentity::VERSION) + "\",";
  json += "\"build\":" + String(FirmwareIdentity::BUILD) + ",";
  json += "\"channel\":\"" + String(FirmwareIdentity::CHANNEL) + "\"";
  json += "}";
  return json;
}

void registerFirmwareMetadataRoutes(AsyncWebServer& server) {
  server.on("/api/version", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", firmwareVersionJson());
  });
}
