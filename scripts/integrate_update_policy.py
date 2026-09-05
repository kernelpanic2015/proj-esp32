from pathlib import Path

# Main integration: status, routes, setup, and bare MQTT firmware.check.
p = Path('src/main.cpp')
s = p.read_text()
if '#include "update_policy.h"' not in s:
    s = s.replace('#include "remote_update_service.h"\n', '#include "remote_update_service.h"\n#include "update_policy.h"\n', 1)

s = s.replace('  json += "\\\"remote_update\\\":" + RemoteFirmwareUpdate::statusJson() + ",";\n  json += "\\\"state\\\":',
              '  json += "\\\"remote_update\\\":" + RemoteFirmwareUpdate::statusJson() + ",";\n  json += "\\\"update_policy\\\":" + FirmwareUpdatePolicy::statusJson() + ",";\n  json += "\\\"state\\\":', 1)

old_status = '''  if (payloadString == "firmware.status") {
    String response = "{\\\"event\\\":\\\"firmware_status\\\",\\\"update\\\":" +
                      FirmwareUpdate::statusJson() + ",\\\"remote_update\\\":" +
                      RemoteFirmwareUpdate::statusJson() + "}";
    mqttClient.publish(topicEvents.c_str(), response.c_str());
    return;
  }
'''
new_status = '''  if (payloadString == "firmware.status") {
    String response = "{\\\"event\\\":\\\"firmware_status\\\",\\\"update\\\":" +
                      FirmwareUpdate::statusJson() + ",\\\"remote_update\\\":" +
                      RemoteFirmwareUpdate::statusJson() + ",\\\"update_policy\\\":" +
                      FirmwareUpdatePolicy::statusJson() + "}";
    mqttClient.publish(topicEvents.c_str(), response.c_str());
    return;
  }
'''
s = s.replace(old_status, new_status, 1)

old_bare = '''  if (payloadString == "firmware.check") {
    mqttClient.publish(topicEvents.c_str(),
                       "{\\\"event\\\":\\\"firmware_check_rejected\\\",\\\"error\\\":\\\"manifest_url_required\\\"}");
    return;
  }
'''
new_bare = '''  if (payloadString == "firmware.check") {
    String manifestUrl;
    String error;
    bool accepted = FirmwareUpdatePolicy::configuredManifestUrl(manifestUrl, error);
    if (accepted) {
      accepted = RemoteFirmwareUpdate::requestCheck(manifestUrl, error);
    }
    String response = accepted
        ? String("{\\\"event\\\":\\\"firmware_check_requested\\\",\\\"accepted\\\":true,\\\"source\\\":\\\"policy\\\"}")
        : String("{\\\"event\\\":\\\"firmware_check_requested\\\",\\\"accepted\\\":false,\\\"source\\\":\\\"policy\\\",\\\"error\\\":\\\"") +
              error + "\\\"}";
    mqttClient.publish(topicEvents.c_str(), response.c_str());
    return;
  }
'''
s = s.replace(old_bare, new_bare, 1)

s = s.replace('    body += "remote_update_status=/api/update/remote/status\\n";\n',
              '    body += "remote_update_status=/api/update/remote/status\\n";\n    body += "update_policy=/api/update/policy\\n";\n', 1)
s = s.replace('  RemoteFirmwareUpdate::registerRoutes(server);\n',
              '  RemoteFirmwareUpdate::registerRoutes(server);\n  FirmwareUpdatePolicy::registerRoutes(server);\n', 1)
s = s.replace('  FirmwareUpdate::begin(preferencesReady);\n  RemoteFirmwareUpdate::begin();\n',
              '  FirmwareUpdate::begin(preferencesReady);\n  RemoteFirmwareUpdate::begin();\n  if (!FirmwareUpdatePolicy::begin()) {\n    Serial.println("UPDATE_POLICY_NVS_INIT_FAILED");\n  }\n', 1)
p.write_text(s)

# Remote update result persistence. Never hold the remote mutex during NVS I/O.
p = Path('src/remote_update_service.cpp')
s = p.read_text()
if '#include "update_policy.h"' not in s:
    s = s.replace('#include "update_service.h"\n', '#include "update_service.h"\n#include "update_policy.h"\n', 1)

old = '''void setFailed(const String& error) {
  StateLock lock;
  if (lock.locked()) {
    lastError = error;
    remoteState = RemoteState::FAILED;
    workerTask = nullptr;
  }
}
'''
new = '''void setFailed(const String& error) {
  {
    StateLock lock;
    if (lock.locked()) {
      lastError = error;
      remoteState = RemoteState::FAILED;
      workerTask = nullptr;
    }
  }
  FirmwareUpdatePolicy::recordResult(error);
}
'''
s = s.replace(old, new, 1)

success_block = '''  {
    StateLock lock;
    if (lock.locked()) {
      baseUrl = localBase;
      lastError = "";
      remoteState = RemoteState::AVAILABLE;
      workerTask = nullptr;
    }
  }
  vTaskDelete(nullptr);
'''
replacement = '''  {
    StateLock lock;
    if (lock.locked()) {
      baseUrl = localBase;
      lastError = "";
      remoteState = RemoteState::AVAILABLE;
      workerTask = nullptr;
    }
  }
  FirmwareUpdatePolicy::recordResult("available");
  vTaskDelete(nullptr);
'''
s = s.replace(success_block, replacement, 1)

s = s.replace('''  if (!FirmwareUpdate::finishPreparedInstall(error)) {
    setFailed("install_finish_" + error);
    vTaskDelete(nullptr);
    return;
  }

  finishWorker(RemoteState::IDLE);
''', '''  if (!FirmwareUpdate::finishPreparedInstall(error)) {
    setFailed("install_finish_" + error);
    vTaskDelete(nullptr);
    return;
  }

  FirmwareUpdatePolicy::recordResult("install_pending_reboot");
  finishWorker(RemoteState::IDLE);
''', 1)
p.write_text(s)

print('UPDATE_POLICY_INTEGRATED')
