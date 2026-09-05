#pragma once

#include <Arduino.h>
#include <stddef.h>
#include <stdint.h>

class AsyncWebServer;

namespace FirmwareUpdate {

void begin(bool criticalStorageReady);
void registerRoutes(AsyncWebServer& server);
void tick(bool criticalStorageReady);
String statusJson();

// Shared signed-package path used by Web upload and remote transports.
// The manifest signature is verified before an install session can begin.
bool preparePackage(const String& manifestJson,
                    const String& signatureBase64,
                    String& error);
bool beginPreparedInstall(String& error);
bool writePreparedChunk(const uint8_t* data, size_t len, String& error);
bool finishPreparedInstall(String& error);

}  // namespace FirmwareUpdate
