#include <Arduino.h>
#include <WiFi.h>
#include <WiFiManager.h>
#include <ESPmDNS.h>
#include <ArduinoOTA.h>
#include <AsyncTCP.h>
#include <ESPAsyncWebServer.h>
#include <WebSerial.h>
#include <MQTT.h>
#include <Fsm.h>

#define ESP_DRD_USE_EEPROM true
#define ESP_DRD_USE_SPIFFS false
#define DOUBLERESETDETECTOR_DEBUG false
#include <ESP_DoubleResetDetector.h>

#include "board_pins.h"
#include "project_config.h"

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
WiFiClient networkClient;
MQTTClient mqttClient(512);
WiFiManager wifiManager;
DoubleResetDetector drd(ProjectConfig::DOUBLE_RESET_TIMEOUT_SECONDS,
                        ProjectConfig::DOUBLE_RESET_STORAGE_ADDRESS);

bool webStarted = false;
bool networkServicesStarted = false;
bool portalWasOpened = false;
AppState appState = AppState::BOOT;
String deviceId;
String topicState;
String topicTelemetry;
String topicEvents;
String topicCommand;
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

String statusJson() {
  String json = "{";
  json += "\"device\":\"" + deviceId + "\",";
  json += "\"hostname\":\"" + String(ProjectConfig::DEVICE_HOSTNAME) + "\",";
  json += "\"state\":\"" + String(stateName(appState)) + "\",";
  json += "\"wifi\":" + String(WiFi.status() == WL_CONNECTED ? "true" : "false") + ",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"rssi\":" + String(WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0) + ",";
  json += "\"mqtt\":" + String(mqttClient.connected() ? "true" : "false") + ",";
  json += "\"uptime_ms\":" + String(millis()) + ",";
  json += "\"free_heap\":" + String(ESP.getFreeHeap());
  json += "}";
  return json;
}

void mqttMessageReceived(String& topic, String& payload) {
  String line = "MQTT RX " + topic + " => " + payload;
  logLine(line);

  if (payload == "ping" || payload == "status") {
    mqttClient.publish(topicEvents, statusJson());
  } else if (payload == "reboot") {
    mqttClient.publish(topicEvents, "{\"event\":\"reboot_requested\"}");
    delay(100);
    ESP.restart();
  }
}

bool connectMqtt() {
  if (WiFi.status() != WL_CONNECTED || mqttClient.connected()) {
    return mqttClient.connected();
  }

  lastMqttAttempt = millis();
  String clientId = String(ProjectConfig::DEVICE_HOSTNAME) + "-" + deviceId;
  logLine("MQTT connecting to " + String(ProjectConfig::MQTT_HOST) + ":" + String(ProjectConfig::MQTT_PORT));

  if (!mqttClient.connect(clientId.c_str())) {
    logLine("MQTT connection failed");
    return false;
  }

  mqttClient.subscribe(topicCommand);
  mqttClient.publish(topicState, "{\"online\":true}", true, 0);
  logLine("MQTT connected; subscribed to " + topicCommand);
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

void startNetworkServices() {
  if (networkServicesStarted || WiFi.status() != WL_CONNECTED) {
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
    body += "console=/webserial\n";
    request->send(200, "text/plain", body);
  });

  server.on("/api/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", statusJson());
  });

  WebSerial.begin(&server);
  WebSerial.onMessage(handleWebCommand);
  server.begin();
  webStarted = true;

  ArduinoOTA.setHostname(ProjectConfig::DEVICE_HOSTNAME);
  ArduinoOTA.onStart([]() { logLine("OTA start"); });
  ArduinoOTA.onEnd([]() { logLine("OTA end"); });
  ArduinoOTA.onError([](ota_error_t error) {
    logLine("OTA error=" + String(static_cast<unsigned int>(error)));
  });
  ArduinoOTA.begin();

  mqttClient.begin(ProjectConfig::MQTT_HOST, ProjectConfig::MQTT_PORT, networkClient);
  mqttClient.onMessage(mqttMessageReceived);

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

  WiFi.mode(WIFI_STA);
  deviceId = buildDeviceId();
  logLine("device_id=" + deviceId);

  wifiManager.setConfigPortalTimeout(ProjectConfig::CONFIG_PORTAL_TIMEOUT_SECONDS);
  wifiManager.setConnectTimeout(20);
  wifiManager.setAPCallback([](WiFiManager*) {
    portalWasOpened = true;
    if (appState == AppState::WIFI_CONNECTING) {
      machine.trigger(EVT_PORTAL_OPEN);
    }
    logLine("CONFIG_PORTAL_AP=" + String(ProjectConfig::CONFIG_PORTAL_SSID));
    logLine("CONFIG_PORTAL_IP=" + WiFi.softAPIP().toString());
  });

  bool forceConfig = drd.detectDoubleReset();
  bool connected = false;

  if (forceConfig) {
    logLine("DOUBLE_RESET_DETECTED");
    machine.trigger(EVT_FORCE_CONFIG);
    connected = wifiManager.startConfigPortal(ProjectConfig::CONFIG_PORTAL_SSID);
    machine.trigger(EVT_CONFIG_DONE);
  } else {
    machine.trigger(EVT_START_NETWORK);
    connected = wifiManager.autoConnect(ProjectConfig::CONFIG_PORTAL_SSID);
    if (portalWasOpened && appState == AppState::CONFIG_PORTAL) {
      machine.trigger(EVT_CONFIG_DONE);
    }
  }

  if (connected && WiFi.status() == WL_CONNECTED) {
    logLine("WIFI_CONNECTED ssid=" + WiFi.SSID());
    logLine("WIFI_IP=" + WiFi.localIP().toString());
    machine.trigger(EVT_WIFI_UP);
    startNetworkServices();
  } else {
    logLine("WIFI_NOT_CONNECTED");
    machine.trigger(EVT_WIFI_DOWN);
  }

  Serial.println("PROJ_ESP32_SETUP_DONE");
}

void loop() {
  drd.loop();
  machine.run_machine();

  const bool wifiUp = WiFi.status() == WL_CONNECTED;

  if (!wifiUp) {
    if (appState == AppState::ONLINE) {
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
  ArduinoOTA.handle();
  WebSerial.loop();
  mqttClient.loop();

  if (!mqttClient.connected() &&
      millis() - lastMqttAttempt >= ProjectConfig::MQTT_RECONNECT_INTERVAL_MS) {
    connectMqtt();
  }

  if (mqttClient.connected() &&
      millis() - lastHeartbeat >= ProjectConfig::HEARTBEAT_INTERVAL_MS) {
    lastHeartbeat = millis();
    mqttClient.publish(topicTelemetry, statusJson());
  }

  delay(2);
}
