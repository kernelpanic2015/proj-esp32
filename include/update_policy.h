#pragma once

#include <Arduino.h>
#include <stdint.h>

class AsyncWebServer;

namespace FirmwareUpdatePolicy {

bool begin();
bool ready();
String statusJson();
void registerRoutes(AsyncWebServer& server);

// Returns the configured manifest URL for a bare firmware.check request.
// A stored URL may exist while automatic updates are disabled; enabled controls
// only automatic scheduling, not an explicit operator request.
bool configuredManifestUrl(String& manifestUrl, String& error);

// Records a compact result string after a remote check/apply attempt. This is
// persisted as part of the single NVS policy document; update frequency is low.
bool recordResult(const String& result);

}  // namespace FirmwareUpdatePolicy
