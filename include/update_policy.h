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

// Lock-safe runtime snapshot used by the automatic scheduler. This does not
// mutate NVS and does not depend on a wall clock.
bool automaticCheckConfig(bool& enabled, String& manifestUrl,
                          uint32_t& intervalSeconds, uint32_t& revision,
                          String& error);

// Records a compact result string after a remote check/apply attempt. This is
// persisted as part of the single NVS policy document; update frequency is low.
bool recordResult(const String& result);

}  // namespace FirmwareUpdatePolicy
