from pathlib import Path

# Public RemoteFirmwareUpdate trigger API.
p = Path('include/remote_update_service.h')
s = p.read_text()
s = s.replace('void begin();\nvoid registerRoutes(AsyncWebServer& server);\nString statusJson();',
'''void begin();
void registerRoutes(AsyncWebServer& server);
String statusJson();

// Transport-independent trigger API. Web, MQTT and later automatic policy
// call these same functions; none implements a separate OTA engine.
bool requestCheck(const String& manifestUrl, String& error);
bool requestApply(String& error);''')
p.write_text(s)

# Refactor Web routes to use a public trigger API while preserving the current
# mutex/StateLock synchronization model.
p = Path('src/remote_update_service.cpp')
s = p.read_text()
needle = 'void registerRoutes(AsyncWebServer& server) {'
if 'bool requestCheck(const String& requestedUrl' not in s:
    block = r'''bool requestCheck(const String& requestedUrl, String& error) {
  error = "";
  String url = requestedUrl;
  url.trim();
  if (!validManifestUrl(url)) {
    error = "manifest_url_invalid";
    return false;
  }

  {
    StateLock lock;
    if (!lock.locked()) {
      error = "state_lock_timeout";
      return false;
    }
    if (workerTask != nullptr || remoteState == RemoteState::CHECKING ||
        remoteState == RemoteState::DOWNLOADING) {
      error = "remote_update_busy";
      return false;
    }
    manifestUrl = url;
    baseUrl = "";
    lastError = "";
    remoteState = RemoteState::IDLE;
  }

  if (!startWorker(checkWorker, "ota-check", error)) {
    setFailed(error);
    return false;
  }
  return true;
}

bool requestApply(String& error) {
  error = "";
  {
    StateLock lock;
    if (!lock.locked()) {
      error = "state_lock_timeout";
      return false;
    }
    if (remoteState != RemoteState::AVAILABLE || workerTask != nullptr) {
      error = "remote_update_not_available";
      return false;
    }
  }

  if (!startWorker(applyWorker, "ota-apply", error)) {
    setFailed(error);
    return false;
  }
  return true;
}

'''
    s = s.replace(needle, block + needle, 1)

start = s.index('  server.on("/api/update/check", HTTP_POST')
end = s.index('  server.on("/api/update/apply", HTTP_POST', start)
check_route = r'''  server.on("/api/update/check", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("manifest_url", true)) {
      request->send(400, "application/json", "{\"error\":\"manifest_url_required\"}");
      return;
    }

    String error;
    if (!requestCheck(request->getParam("manifest_url", true)->value(), error)) {
      int code = 400;
      if (error == "remote_update_busy") code = 409;
      else if (error == "state_lock_timeout") code = 503;
      request->send(code, "application/json", "{\"error\":\"" + error + "\"}");
      return;
    }
    request->send(202, "application/json", statusJson());
  });

'''
s = s[:start] + check_route + s[end:]

start = s.index('  server.on("/api/update/apply", HTTP_POST')
end = s.index('\n  });\n}\n\n}  // namespace RemoteFirmwareUpdate', start) + len('\n  });')
apply_route = r'''  server.on("/api/update/apply", HTTP_POST, [](AsyncWebServerRequest* request) {
    String error;
    if (!requestApply(error)) {
      const int code = error == "state_lock_timeout" ? 503 : 409;
      request->send(code, "application/json", "{\"error\":\"" + error + "\"}");
      return;
    }
    request->send(202, "application/json", statusJson());
  });'''
s = s[:start] + apply_route + s[end:]
p.write_text(s)

# Add MQTT trigger commands and richer status observability.
p = Path('src/main.cpp')
s = p.read_text()
old = '  json += "\\\"update\\\":" + FirmwareUpdate::statusJson() + ",";\n  json += "\\\"state\\\":\\\"" + String(stateName(appState)) + "\\\",";'
new = '  json += "\\\"update\\\":" + FirmwareUpdate::statusJson() + ",";\n  json += "\\\"remote_update\\\":" + RemoteFirmwareUpdate::statusJson() + ",";\n  json += "\\\"state\\\":\\\"" + String(stateName(appState)) + "\\\",";'
s = s.replace(old, new, 1)

start = s.index('void mqttMessageReceived(char* topic, byte* payload, unsigned int length) {')
end = s.index('\n}\n\nbool connectMqtt()', start) + 2
handler = r'''void mqttMessageReceived(char* topic, byte* payload, unsigned int length) {
  String topicString(topic);
  String payloadString;
  payloadString.reserve(length);
  for (unsigned int i = 0; i < length; ++i) {
    payloadString += static_cast<char>(payload[i]);
  }
  payloadString.trim();

  logLine("MQTT RX " + topicString + " => " + payloadString);

  if (payloadString == "ping" || payloadString == "status") {
    String response = statusJson();
    mqttClient.publish(topicEvents.c_str(), response.c_str());
    return;
  }

  if (payloadString == "firmware.status") {
    String response = "{\"event\":\"firmware_status\",\"update\":" +
                      FirmwareUpdate::statusJson() + ",\"remote_update\":" +
                      RemoteFirmwareUpdate::statusJson() + "}";
    mqttClient.publish(topicEvents.c_str(), response.c_str());
    return;
  }

  if (payloadString == "firmware.check") {
    mqttClient.publish(topicEvents.c_str(),
                       "{\"event\":\"firmware_check_rejected\",\"error\":\"manifest_url_required\"}");
    return;
  }

  const String checkPrefix = "firmware.check ";
  if (payloadString.startsWith(checkPrefix)) {
    String manifestUrl = payloadString.substring(checkPrefix.length());
    manifestUrl.trim();
    String error;
    const bool accepted = RemoteFirmwareUpdate::requestCheck(manifestUrl, error);
    String response = accepted
        ? String("{\"event\":\"firmware_check_requested\",\"accepted\":true}")
        : String("{\"event\":\"firmware_check_requested\",\"accepted\":false,\"error\":\"") +
              error + "\"}";
    mqttClient.publish(topicEvents.c_str(), response.c_str());
    return;
  }

  if (payloadString == "firmware.update") {
    String error;
    const bool accepted = RemoteFirmwareUpdate::requestApply(error);
    String response = accepted
        ? String("{\"event\":\"firmware_update_requested\",\"accepted\":true}")
        : String("{\"event\":\"firmware_update_requested\",\"accepted\":false,\"error\":\"") +
              error + "\"}";
    mqttClient.publish(topicEvents.c_str(), response.c_str());
    return;
  }

  if (payloadString == "reboot") {
    mqttClient.publish(topicEvents.c_str(), "{\"event\":\"reboot_requested\"}");
    delay(100);
    ESP.restart();
  }
}'''
s = s[:start] + handler + s[end:]

s = s.replace('  mqttClient.setBufferSize(512);', '  mqttClient.setBufferSize(1024);', 1)

# Lab-only endpoint publishes onto the real MQTT command topic. It proves the
# broker round trip without putting broker credentials in GitHub/Aurora jobs.
marker = '  registerFirmwareMetadataRoutes(server);\n'
if 'PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT' not in s:
    test_route = r'''#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT
  server.on("/api/test/mqtt/command", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("command", true)) {
      request->send(400, "application/json", "{\"error\":\"command_required\"}");
      return;
    }
    if (!mqttClient.connected()) {
      request->send(503, "application/json", "{\"error\":\"mqtt_not_connected\"}");
      return;
    }
    String command = request->getParam("command", true)->value();
    command.trim();
    if (!command.length() || command.length() > 420) {
      request->send(400, "application/json", "{\"error\":\"command_invalid\"}");
      return;
    }
    const bool ok = mqttClient.publish(topicCommand.c_str(), command.c_str());
    request->send(ok ? 202 : 500, "application/json",
                  ok ? "{\"published\":true}" : "{\"published\":false}");
  });
#endif

'''
    s = s.replace(marker, test_route + marker, 1)
p.write_text(s)

# Enable the credential-free MQTT loopback endpoint only in the lab transition.
p = Path('platformio.ini')
s = p.read_text()
needle = '    -DPROJ_REMOTE_UPDATE_ALLOW_HTTP=1\n\n; Target image for the next repeatable remote OTA proof.'
s = s.replace(needle,
'''    -DPROJ_REMOTE_UPDATE_ALLOW_HTTP=1
    -DPROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT=1

; Target image for the next repeatable remote OTA proof.''', 1)
p.write_text(s)

print('MQTT_OTA_TRIGGER_PATCH_APPLIED')
