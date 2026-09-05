#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <WiFiManager.h>
#include <ESPmDNS.h>
#include <AsyncTCP.h>
#include <ESPAsyncWebServer.h>
#include <WebSerial.h>
#include <PubSubClient.h>
#include <Preferences.h>
#include <Fsm.h>
#include <TaskScheduler.h>

#define ESP_DRD_USE_EEPROM true
#define ESP_DRD_USE_SPIFFS false
#define DOUBLERESETDETECTOR_DEBUG false
#include <ESP_DoubleResetDetector.h>

#include "board_pins.h"
#include "project_config.h"
#include "firmware_metadata.h"
#include "update_service.h"
#include "remote_update_service.h"
#include "update_policy.h"
#include "update_scheduler.h"

enum Event : int {
  EVT_START_NETWORK = 1,
  EVT_FORCE_CONFIG,
  EVT_PORTAL_OPEN,
  EVT_CONFIG_DONE,
  EVT_WIFI_UP,
  EVT_WIFI_DOWN
};

enum class AppState {
  BOOT,
  CONFIG_PORTAL,
  WIFI_CONNECTING,
  ONLINE,
  OFFLINE
};

AsyncWebServer server(80);
WiFiClient plainNetworkClient;
WiFiClientSecure secureNetworkClient;
PubSubClient mqttClient;
WiFiManager wifiManager;
Preferences preferences;
DoubleResetDetector* drd = nullptr;
Scheduler cooperativeScheduler;

bool webStarted = false;
bool networkServicesStarted = false;
bool preferencesReady = false;
bool restartRequested = false;
unsigned long restartRequestedAt = 0;
AppState appState = AppState::BOOT;
String deviceId;
String topicState;
String topicTelemetry;
String topicEvents;
String topicCommand;
String mqttHost;
uint16_t mqttPort = 1883;
String mqttUsername;
String mqttPassword;
bool mqttTls = false;
unsigned long lastMqttAttempt = 0;
unsigned long lastHeartbeat = 0;
unsigned long lastWifiRetry = 0;

const char* stateName(AppState state) {
  switch (state) {
    case AppState::BOOT: return "BOOT";
    case AppState::CONFIG_PORTAL: return "CONFIG_PORTAL";
    case AppState::WIFI_CONNECTING: return "WIFI_CONNECTING";
    case AppState::ONLINE: return "ONLINE";
    case AppState::OFFLINE: return "OFFLINE";
  }
  return "UNKNOWN";
}

void logLine(const String& message) {
  Serial.println(message);
  if (webStarted) {
    WebSerial.println(message);
  }
}

void enterBoot() {
  appState = AppState::BOOT;
  logLine("FSM -> BOOT");
}

void enterConfigPortal() {
  appState = AppState::CONFIG_PORTAL;
  logLine("FSM -> CONFIG_PORTAL");
}

void enterWifiConnecting() {
  appState = AppState::WIFI_CONNECTING;
  logLine("FSM -> WIFI_CONNECTING");
}

void enterOnline() {
  appState = AppState::ONLINE;
  logLine("FSM -> ONLINE");
}

void enterOffline() {
  appState = AppState::OFFLINE;
  logLine("FSM -> OFFLINE");
}

State stateBoot(enterBoot, nullptr, nullptr);
State stateConfig(enterConfigPortal, nullptr, nullptr);
State stateWifi(enterWifiConnecting, nullptr, nullptr);
State stateOnline(enterOnline, nullptr, nullptr);
State stateOffline(enterOffline, nullptr, nullptr);
Fsm machine(&stateBoot);

String buildDeviceId() {
  uint64_t mac = ESP.getEfuseMac();
  char buffer[13];
  snprintf(buffer, sizeof(buffer), "%04X%08X",
           static_cast<uint16_t>(mac >> 32),
           static_cast<uint32_t>(mac));
  return String(buffer);
}

String htmlEscape(String value) {
  value.replace("&", "&amp;");
  value.replace("\"", "&quot;");
  value.replace("<", "&lt;");
  value.replace(">", "&gt;");
  return value;
}

void loadMqttConfig() {
  mqttHost = ProjectConfig::MQTT_HOST;
  mqttPort = ProjectConfig::MQTT_PORT;
  mqttUsername = "";
  mqttPassword = "";
  mqttTls = false;

  if (!preferencesReady) {
    return;
  }

  mqttHost = preferences.getString("mqtt_host", mqttHost);
  mqttPort = preferences.getUShort("mqtt_port", mqttPort);
  mqttUsername = preferences.getString("mqtt_user", "");
  mqttPassword = preferences.getString("mqtt_pass", "");
  mqttTls = preferences.getBool("mqtt_tls", false);
}

bool mqttConfigured() {
  return mqttHost.length() > 0 && mqttPort > 0 &&
         mqttUsername.length() > 0 && mqttPassword.length() > 0;
}

String statusJson() {
  String json = "{";
  json += "\"device\":\"" + deviceId + "\",";
  json += "\"hostname\":\"" + String(ProjectConfig::DEVICE_HOSTNAME) + "\",";
  json += "\"firmware\":" + firmwareVersionJson() + ",";
  json += "\"update\":" + FirmwareUpdate::statusJson() + ",";
  json += "\"remote_update\":" + RemoteFirmwareUpdate::statusJson() + ",";
  json += "\"update_policy\":" + FirmwareUpdatePolicy::statusJson() + ",";
  json += "\"update_scheduler\":" + FirmwareUpdateScheduler::statusJson() + ",";
  json += "\"state\":\"" + String(stateName(appState)) + "\",";
  json += "\"wifi\":" + String(WiFi.status() == WL_CONNECTED ? "true" : "false") + ",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"rssi\":" + String(WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0) + ",";
  json += "\"mqtt\":" + String(mqttClient.connected() ? "true" : "false") + ",";
  json += "\"mqtt_configured\":" + String(mqttConfigured() ? "true" : "false") + ",";
  json += "\"mqtt_tls\":" + String(mqttTls ? "true" : "false") + ",";
  json += "\"uptime_ms\":" + String(millis()) + ",";
  json += "\"free_heap\":" + String(ESP.getFreeHeap());
  json += "}";
  return json;
}

void mqttMessageReceived(char* topic, byte* payload, unsigned int length) {
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
                      RemoteFirmwareUpdate::statusJson() + ",\"update_policy\":" +
                      FirmwareUpdatePolicy::statusJson() + "}";
    mqttClient.publish(topicEvents.c_str(), response.c_str());
    return;
  }

  if (payloadString == "firmware.check") {
    String manifestUrl;
    String error;
    bool accepted = FirmwareUpdatePolicy::configuredManifestUrl(manifestUrl, error);
    if (accepted) {
      accepted = RemoteFirmwareUpdate::requestCheck(manifestUrl, error);
    }
    String response = accepted
        ? String("{\"event\":\"firmware_check_requested\",\"accepted\":true,\"source\":\"policy\"}")
        : String("{\"event\":\"firmware_check_requested\",\"accepted\":false,\"source\":\"policy\",\"error\":\"") +
              error + "\"}";
    mqttClient.publish(topicEvents.c_str(), response.c_str());
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
}

bool connectMqtt() {
  if (WiFi.status() != WL_CONNECTED || mqttClient.connected()) {
    return mqttClient.connected();
  }

  if (!mqttConfigured()) {
    logLine("MQTT not configured; open /config/mqtt");
    return false;
  }

  lastMqttAttempt = millis();
  String clientId = String(ProjectConfig::DEVICE_HOSTNAME) + "-" + deviceId;
  logLine("MQTT/PubSubClient connecting to " + mqttHost + ":" + String(mqttPort) +
          (mqttTls ? " TLS" : ""));

  if (!mqttClient.connect(clientId.c_str(), mqttUsername.c_str(), mqttPassword.c_str())) {
    logLine("MQTT/PubSubClient connection failed state=" + String(mqttClient.state()));
    return false;
  }

  mqttClient.subscribe(topicCommand.c_str());
  mqttClient.publish(topicState.c_str(), "{\"online\":true}", true);
  logLine("MQTT/PubSubClient connected; subscribed to " + topicCommand);
  return true;
}

void handleWebCommand(uint8_t* data, size_t len) {
  String command;
  command.reserve(len);
  for (size_t i = 0; i < len; ++i) {
    command += static_cast<char>(data[i]);
  }
  command.trim();

  if (command == "status") {
    WebSerial.println(statusJson());
  } else if (command == "mqtt") {
    connectMqtt();
    WebSerial.println(mqttClient.connected() ? "MQTT_OK" : "MQTT_NOT_CONNECTED");
  } else if (command == "reboot") {
    WebSerial.println("REBOOTING");
    delay(100);
    ESP.restart();
  } else if (command.length()) {
    WebSerial.println("Commands: status | mqtt | reboot");
  }
}

String mqttConfigPage() {
  String page = "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>proj-esp32 MQTT</title></head><body>";
  page += "<h1>proj-esp32 MQTT</h1>";
  page += "<p>Credentials are stored only in ESP32 NVS.</p>";
  page += "<form method='post' action='/config/mqtt'>";
  page += "<label>Host <input name='host' required value='" + htmlEscape(mqttHost) + "'></label><br>";
  page += "<label>Port <input name='port' type='number' min='1' max='65535' required value='" + String(mqttPort) + "'></label><br>";
  page += "<label>Username <input name='username' required value='" + htmlEscape(mqttUsername) + "'></label><br>";
  page += "<label>Password <input name='password' type='password' placeholder='";
  page += mqttPassword.length() ? "leave blank to keep saved password" : "required on first save";
  page += "'></label><br>";
  page += "<label><input name='tls' type='checkbox' value='1'";
  if (mqttTls) page += " checked";
  page += "> TLS</label><br>";
  page += "<button type='submit'>Save and reboot</button></form>";
  page += "<p><a href='/'>Back</a> | <a href='/api/status'>Status</a></p>";
  page += "</body></html>";
  return page;
}

void startNetworkServices() {
  if (networkServicesStarted || WiFi.status() != WL_CONNECTED ||
      wifiManager.getConfigPortalActive()) {
    return;
  }

  topicState = String(ProjectConfig::MQTT_TOPIC_ROOT) + "/" + deviceId + "/state";
  topicTelemetry = String(ProjectConfig::MQTT_TOPIC_ROOT) + "/" + deviceId + "/telemetry";
  topicEvents = String(ProjectConfig::MQTT_TOPIC_ROOT) + "/" + deviceId + "/events";
  topicCommand = String(ProjectConfig::MQTT_TOPIC_ROOT) + "/" + deviceId + "/cmd";

  if (MDNS.begin(ProjectConfig::DEVICE_HOSTNAME)) {
    MDNS.addService("http", "tcp", 80);
    logLine("mDNS: http://" + String(ProjectConfig::DEVICE_HOSTNAME) + ".local");
  } else {
    logLine("mDNS start failed");
  }

  server.on("/", HTTP_GET, [](AsyncWebServerRequest* request) {
    String body = "proj-esp32\n";
    body += "state=" + String(stateName(appState)) + "\n";
    body += "status=/api/status\n";
    body += "version=/api/version\n";
    body += "update=/update\n";
    body += "remote_update_status=/api/update/remote/status\n";
    body += "update_policy=/api/update/policy\n";
    body += "update_scheduler=/api/update/scheduler\n";
    body += "console=/webserial\n";
    body += "mqtt_config=/config/mqtt\n";
    request->send(200, "text/plain", body);
  });

  server.on("/api/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", statusJson());
  });

  server.on("/config/mqtt", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "text/html", mqttConfigPage());
  });

  server.on("/config/mqtt", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!preferencesReady || !request->hasParam("host", true) ||
        !request->hasParam("port", true) || !request->hasParam("username", true)) {
      request->send(400, "text/plain", "missing required fields");
      return;
    }

    String newHost = request->getParam("host", true)->value();
    String newUser = request->getParam("username", true)->value();
    uint32_t parsedPort = request->getParam("port", true)->value().toInt();
    String newPassword = request->hasParam("password", true)
                             ? request->getParam("password", true)->value()
                             : String();
    bool newTls = request->hasParam("tls", true);

    newHost.trim();
    newUser.trim();
    if (!newHost.length() || !newUser.length() || parsedPort == 0 || parsedPort > 65535) {
      request->send(400, "text/plain", "invalid MQTT settings");
      return;
    }

    preferences.putString("mqtt_host", newHost);
    preferences.putUShort("mqtt_port", static_cast<uint16_t>(parsedPort));
    preferences.putString("mqtt_user", newUser);
    preferences.putBool("mqtt_tls", newTls);
    if (newPassword.length()) {
      preferences.putString("mqtt_pass", newPassword);
    } else if (!mqttPassword.length()) {
      request->send(400, "text/plain", "password required on first save");
      return;
    }

    request->send(200, "text/plain", "MQTT settings saved. Rebooting...\n");
    restartRequested = true;
    restartRequestedAt = millis();
  });

#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT
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

  registerFirmwareMetadataRoutes(server);
  FirmwareUpdate::registerRoutes(server);
  RemoteFirmwareUpdate::registerRoutes(server);
  FirmwareUpdatePolicy::registerRoutes(server);
  FirmwareUpdateScheduler::registerRoutes(server);

  WebSerial.begin(&server);
  WebSerial.onMessage(handleWebCommand);
  server.begin();
  webStarted = true;

  if (mqttTls) {
    // Development mode: encrypted transport without CA verification.
    // Replace setInsecure() with a CA certificate before production use.
    secureNetworkClient.setInsecure();
    mqttClient.setClient(secureNetworkClient);
  } else {
    mqttClient.setClient(plainNetworkClient);
  }
  mqttClient.setServer(mqttHost.c_str(), mqttPort);
  mqttClient.setBufferSize(1024);
  mqttClient.setKeepAlive(30);
  mqttClient.setCallback(mqttMessageReceived);

  networkServicesStarted = true;
  logLine("HTTP server ready: http://" + WiFi.localIP().toString() + "/");
  logLine("WebSerial ready: http://" + WiFi.localIP().toString() + "/webserial");
  connectMqtt();
}

void configureStateMachine() {
  machine.add_transition(&stateBoot, &stateWifi, EVT_START_NETWORK, nullptr);
  machine.add_transition(&stateBoot, &stateConfig, EVT_FORCE_CONFIG, nullptr);
  machine.add_transition(&stateWifi, &stateConfig, EVT_PORTAL_OPEN, nullptr);
  machine.add_transition(&stateConfig, &stateWifi, EVT_CONFIG_DONE, nullptr);
  machine.add_transition(&stateWifi, &stateOnline, EVT_WIFI_UP, nullptr);
  machine.add_transition(&stateWifi, &stateOffline, EVT_WIFI_DOWN, nullptr);
  machine.add_transition(&stateOnline, &stateOffline, EVT_WIFI_DOWN, nullptr);
  machine.add_transition(&stateOffline, &stateOnline, EVT_WIFI_UP, nullptr);
}

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println();
  Serial.println("PROJ_ESP32_BOOT");

  configureStateMachine();
  machine.run_machine();

  preferencesReady = preferences.begin("proj-esp32", false);
  loadMqttConfig();
  FirmwareUpdate::begin(preferencesReady);
  RemoteFirmwareUpdate::begin();
  if (!FirmwareUpdatePolicy::begin()) {
    Serial.println("UPDATE_POLICY_NVS_INIT_FAILED");
  }
  FirmwareUpdateScheduler::begin(cooperativeScheduler);

  WiFi.mode(WIFI_STA);
  deviceId = buildDeviceId();
  logLine("device_id=" + deviceId);
  logLine(String("MQTT configured=") + (mqttConfigured() ? "yes" : "no"));

  // Construct DRD only after the Arduino/ESP32 runtime has initialized NVS.
  // A global constructor caused EEPROM/NVS initialization errors on this board.
  drd = new DoubleResetDetector(ProjectConfig::DOUBLE_RESET_TIMEOUT_SECONDS,
                                ProjectConfig::DOUBLE_RESET_STORAGE_ADDRESS);

  wifiManager.setConfigPortalBlocking(false);
  wifiManager.setConfigPortalTimeout(ProjectConfig::CONFIG_PORTAL_TIMEOUT_SECONDS);
  wifiManager.setConnectTimeout(20);
  wifiManager.setAPCallback([](WiFiManager*) {
    if (appState == AppState::WIFI_CONNECTING) {
      machine.trigger(EVT_PORTAL_OPEN);
    }
    logLine("CONFIG_PORTAL_AP=" + String(ProjectConfig::CONFIG_PORTAL_SSID));
    logLine("CONFIG_PORTAL_IP=" + WiFi.softAPIP().toString());
  });

  const bool forceConfig = drd->detectDoubleReset();

  if (forceConfig) {
    logLine("DOUBLE_RESET_DETECTED");
    machine.trigger(EVT_FORCE_CONFIG);
    wifiManager.startConfigPortal(ProjectConfig::CONFIG_PORTAL_SSID);
  } else {
    machine.trigger(EVT_START_NETWORK);
    if (wifiManager.autoConnect(ProjectConfig::CONFIG_PORTAL_SSID) &&
        WiFi.status() == WL_CONNECTED) {
      logLine("WIFI_CONNECTED ssid=" + WiFi.SSID());
      logLine("WIFI_IP=" + WiFi.localIP().toString());
      machine.trigger(EVT_WIFI_UP);
      startNetworkServices();
    }
  }

  if (wifiManager.getConfigPortalActive()) {
    logLine("CONFIG_PORTAL_RUNNING");
  }

  Serial.println("PROJ_ESP32_SETUP_DONE");
}

void loop() {
  if (restartRequested && millis() - restartRequestedAt > 750) {
    ESP.restart();
  }

  if (drd) {
    drd->loop();
  }

  wifiManager.process();
  machine.run_machine();
  FirmwareUpdate::tick(preferencesReady);
  FirmwareUpdateScheduler::setNetworkAvailable(
      WiFi.status() == WL_CONNECTED && !wifiManager.getConfigPortalActive());
  cooperativeScheduler.execute();

  const bool portalActive = wifiManager.getConfigPortalActive();

  if (portalActive) {
    if (appState == AppState::WIFI_CONNECTING) {
      machine.trigger(EVT_PORTAL_OPEN);
    }
    delay(2);
    return;
  }

  if (appState == AppState::CONFIG_PORTAL) {
    machine.trigger(EVT_CONFIG_DONE);
  }

  const bool wifiUp = WiFi.status() == WL_CONNECTED;

  if (!wifiUp) {
    if (appState == AppState::WIFI_CONNECTING) {
      machine.trigger(EVT_WIFI_DOWN);
    } else if (appState == AppState::ONLINE) {
      machine.trigger(EVT_WIFI_DOWN);
    }

    if (millis() - lastWifiRetry >= ProjectConfig::MQTT_RECONNECT_INTERVAL_MS) {
      lastWifiRetry = millis();
      WiFi.reconnect();
    }
    delay(5);
    return;
  }

  if (appState == AppState::OFFLINE || appState == AppState::WIFI_CONNECTING) {
    machine.trigger(EVT_WIFI_UP);
  }

  startNetworkServices();
  WebSerial.loop();
  mqttClient.loop();

  if (!mqttClient.connected() && mqttConfigured() &&
      millis() - lastMqttAttempt >= ProjectConfig::MQTT_RECONNECT_INTERVAL_MS) {
    connectMqtt();
  }

  if (mqttClient.connected() &&
      millis() - lastHeartbeat >= ProjectConfig::HEARTBEAT_INTERVAL_MS) {
    lastHeartbeat = millis();
    String telemetry = statusJson();
    mqttClient.publish(topicTelemetry.c_str(), telemetry.c_str());
  }

  delay(2);
}
