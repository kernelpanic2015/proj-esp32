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
#include "configuration_store.h"
#include "restart_service.h"
#include "core/component_registry.h"
#include "core/event_bus.h"
#include "core/runtime_events.h"
#include "core/supervisor.h"
#include "components/connectivity_component.h"
#include "rules/rule_engine.h"
#include "rules/rule_runtime.h"
#include "rules/persisted_rule_loader.h"
#include "schedules/local_schedule_service.h"
#include "components/virtual_input_component.h"
#include "components/virtual_actuator_component.h"

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
RuntimeCore::EventBus runtimeEvents;
RuntimeCore::ComponentRegistry runtimeComponents;
RuntimeCore::Supervisor runtimeSupervisor(runtimeComponents, runtimeEvents);
Rules::RuleEngine ruleEngine(runtimeEvents);
Components::VirtualInputComponent virtualTemperature(runtimeEvents, "virtual.temperature");
Components::VirtualActuatorComponent virtualHeater(runtimeEvents, "virtual.heater");
Components::VirtualActuatorComponent virtualScheduleOutput(runtimeEvents, "virtual.schedule_output");

bool ruleInputReady();
float ruleInputValue();
RuntimeCore::HealthState ruleDependencyHealth();
bool ruleOutputState();
bool ruleApplyDesired(bool desiredOn);
Rules::RuleRuntime ruleRuntime(cooperativeScheduler, runtimeEvents, ruleEngine,
                               "virtual.temperature", ruleInputReady, ruleInputValue,
                               ruleDependencyHealth, ruleOutputState, ruleApplyDesired);
Rules::PersistedRuleLoader persistedRuleLoader(ruleEngine, ruleRuntime);
bool scheduleApplyDesired(bool desiredOn);
Schedules::LocalScheduleService localScheduleService(cooperativeScheduler, scheduleApplyDesired);

bool mqttConfigured();
bool runtimeWifiConnected();
bool runtimeMqttConnected();
bool runtimeMqttConfigured();
void sampleConnectivityComponent();
void evaluateRuntimeSupervisor();
void coordinateWifiTasks();
void runWifiReconnectTask();
String wifiRuntimeStatusJson();
#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT
void runWifiTestDisconnectTask();
#endif
void coordinateMqttTasks();
void runMqttReconnectTask();
void runMqttTelemetryTask();
String mqttRuntimeStatusJson();
#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS
void runRuleTestInputTask();
#endif

Components::ConnectivityComponent connectivityComponent(
    runtimeEvents, runtimeWifiConnected, runtimeMqttConnected, runtimeMqttConfigured);
Task connectivityHealthTask(2000, TASK_FOREVER, sampleConnectivityComponent,
                            &cooperativeScheduler, false);
Task supervisorTask(1000, TASK_FOREVER, evaluateRuntimeSupervisor,
                    &cooperativeScheduler, false);
Task wifiCoordinatorTask(250, TASK_FOREVER, coordinateWifiTasks,
                         &cooperativeScheduler, false);
Task wifiReconnectTask(ProjectConfig::WIFI_RECONNECT_INTERVAL_MS, TASK_FOREVER,
                       runWifiReconnectTask, &cooperativeScheduler, false);
#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT
Task wifiTestDisconnectTask(250, TASK_ONCE, runWifiTestDisconnectTask,
                            &cooperativeScheduler, false);
#endif
Task mqttCoordinatorTask(250, TASK_FOREVER, coordinateMqttTasks,
                         &cooperativeScheduler, false);
Task mqttReconnectTask(ProjectConfig::MQTT_RECONNECT_INTERVAL_MS, TASK_FOREVER,
                       runMqttReconnectTask, &cooperativeScheduler, false);
Task mqttTelemetryTask(ProjectConfig::HEARTBEAT_INTERVAL_MS, TASK_FOREVER,
                       runMqttTelemetryTask, &cooperativeScheduler, false);
#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS
Task ruleTestInputTask(TASK_IMMEDIATE, TASK_ONCE, runRuleTestInputTask,
                       &cooperativeScheduler, false);
float ruleTestPendingInput = 0.0f;
#endif

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
uint32_t wifiReconnectAttemptCount = 0;
uint32_t wifiReconnectSuccessCount = 0;
uint32_t wifiDisconnectObservedCount = 0;
unsigned long wifiLastReconnectAttemptMs = 0;
unsigned long wifiLastReconnectSuccessMs = 0;
unsigned long wifiLastDisconnectObservedMs = 0;
String wifiLastReconnectResult = "never";
bool wifiReconnectPending = false;
bool wifiLastObservedConnected = false;
#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT
unsigned long wifiReconnectSuppressedUntil = 0;
#endif
uint32_t mqttReconnectAttemptCount = 0;
uint32_t mqttReconnectSuccessCount = 0;
uint32_t mqttTelemetryAttemptCount = 0;
uint32_t mqttTelemetryPublishCount = 0;
unsigned long mqttLastReconnectAttemptMs = 0;
unsigned long mqttLastReconnectSuccessMs = 0;
unsigned long mqttLastTelemetryAttemptMs = 0;
unsigned long mqttLastTelemetryPublishMs = 0;
String mqttLastReconnectResult = "never";
String mqttLastTelemetryResult = "never";
#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT
unsigned long mqttReconnectSuppressedUntil = 0;
#endif

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

void handleRuntimeEvent(const RuntimeCore::Event& event) {
  if (event.type == static_cast<uint16_t>(RuntimeCore::RuntimeEventType::ComponentStateChanged)) {
    logLine("EVENT component_state source=" + String(event.source) +
            " value=" + String(event.value));
  } else if (event.type == static_cast<uint16_t>(RuntimeCore::RuntimeEventType::ComponentHealthChanged)) {
    logLine("EVENT component_health source=" + String(event.source) +
            " value=" + String(event.value));
  } else if (event.type == static_cast<uint16_t>(RuntimeCore::RuntimeEventType::SupervisorStateChanged)) {
    logLine("EVENT supervisor_state value=" + String(event.value));
  } else if (event.type == static_cast<uint16_t>(RuntimeCore::RuntimeEventType::InputValueChanged)) {
    logLine("EVENT input_value source=" + String(event.source) +
            " milli_value=" + String(event.value));
  } else if (event.type == static_cast<uint16_t>(RuntimeCore::RuntimeEventType::RuleEvaluated)) {
    logLine("EVENT rule_evaluated source=" + String(event.source) +
            " decision=" + String(event.value));
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

bool runtimeWifiConnected() {
  return WiFi.status() == WL_CONNECTED;
}

bool runtimeMqttConnected() {
  return mqttClient.connected();
}

bool runtimeMqttConfigured() {
  return mqttConfigured();
}

bool ruleInputReady() { return virtualTemperature.hasValue(); }
float ruleInputValue() { return virtualTemperature.value(); }
RuntimeCore::HealthState ruleDependencyHealth() {
  return virtualTemperature.health().state;
}
bool ruleOutputState() { return virtualHeater.isOn(); }
bool ruleApplyDesired(bool desiredOn) { return virtualHeater.applyDesired(desiredOn); }

bool scheduleApplyDesired(bool desiredOn) {
  return virtualScheduleOutput.applyDesired(desiredOn);
}

bool validatePersistedConfiguration(const String& raw, String& error) {
  if (!persistedRuleLoader.validateDocument(raw, error)) return false;
  if (!localScheduleService.validateDocument(raw, error)) return false;
  return true;
}

void activatePersistedConfiguration(uint32_t revision, const String& raw) {
  String error;
  if (!persistedRuleLoader.activateDocument(raw, revision, error)) {
    logLine("PERSISTED_RULE_RELOAD_FAILED " + error);
  }
  error = "";
  if (!localScheduleService.activateDocument(raw, revision, error)) {
    logLine("LOCAL_SCHEDULE_RELOAD_FAILED " + error);
  }
}

#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS
void runRuleTestInputTask() {
  virtualTemperature.setValue(ruleTestPendingInput);
}
#endif

void sampleConnectivityComponent() {
  connectivityComponent.sample();
}

void evaluateRuntimeSupervisor() {
  runtimeSupervisor.evaluate();
}

String componentsStatusJson() {
  String json;
  json.reserve(256);
  json += '{';
  json += char(34);
  json += "registry";
  json += char(34);
  json += ':';
  json += runtimeComponents.statusJson();
  json += ',';
  json += char(34);
  json += "event_bus";
  json += char(34);
  json += ':';
  json += '{';
  json += char(34);
  json += "pending";
  json += char(34);
  json += ':';
  json += String(runtimeEvents.pending());
  json += ',';
  json += char(34);
  json += "dropped";
  json += char(34);
  json += ':';
  json += String(runtimeEvents.dropped());
  json += '}';
  json += '}';
  return json;
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
  json += "\"configuration\":" + ConfigurationStore::statusJson() + ",";
  json += "\"rule_engine\":" + ruleEngine.statusJson() + ",";
  json += "\"rule_runtime\":" + ruleRuntime.statusJson() + ",";
  json += "\"persisted_rules\":" + persistedRuleLoader.statusJson() + ",";
  json += "\"local_schedule\":" + localScheduleService.statusJson() + ",";
  json += "\"components\":" + runtimeComponents.statusJson() + ",";
  json += "\"supervisor\":" + runtimeSupervisor.statusJson() + ",";
  json += "\"event_bus\":{\"pending\":" + String(runtimeEvents.pending()) + ",\"dropped\":" + String(runtimeEvents.dropped()) + "},";
  json += "\"state\":\"" + String(stateName(appState)) + "\",";
  json += "\"wifi\":" + String(WiFi.status() == WL_CONNECTED ? "true" : "false") + ",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"rssi\":" + String(WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0) + ",";
  json += "\"wifi_runtime\":" + wifiRuntimeStatusJson() + ",";
  json += "\"mqtt\":" + String(mqttClient.connected() ? "true" : "false") + ",";
  json += "\"mqtt_configured\":" + String(mqttConfigured() ? "true" : "false") + ",";
  json += "\"mqtt_tls\":" + String(mqttTls ? "true" : "false") + ",";
  json += "\"mqtt_runtime\":" + mqttRuntimeStatusJson() + ",";
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
    RestartService::restartNow();
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


bool wifiReconnectAllowedNow() {
#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT
  return static_cast<int32_t>(millis() - wifiReconnectSuppressedUntil) >= 0;
#else
  return true;
#endif
}

void runWifiReconnectTask() {
  if (wifiManager.getConfigPortalActive() || WiFi.status() == WL_CONNECTED ||
      !wifiReconnectAllowedNow()) {
    wifiLastReconnectResult = wifiManager.getConfigPortalActive() ? "portal_active" :
                              (WiFi.status() == WL_CONNECTED ? "already_connected" : "suppressed");
    wifiReconnectTask.disable();
    return;
  }

  ++wifiReconnectAttemptCount;
  wifiLastReconnectAttemptMs = millis();
  wifiReconnectPending = true;
  const bool started = WiFi.reconnect();
  wifiLastReconnectResult = started ? "reconnect_started" : "reconnect_start_failed";
}

void coordinateWifiTasks() {
  const bool portalActive = wifiManager.getConfigPortalActive();
  const bool wifiUp = WiFi.status() == WL_CONNECTED;

  if (portalActive) {
    if (wifiReconnectTask.isEnabled()) wifiReconnectTask.disable();
    wifiReconnectPending = false;
    wifiLastReconnectResult = "portal_active";
    wifiLastObservedConnected = wifiUp;
    return;
  }

  if (wifiUp) {
    if (!wifiLastObservedConnected && wifiReconnectPending) {
      ++wifiReconnectSuccessCount;
      wifiLastReconnectSuccessMs = millis();
      wifiLastReconnectResult = "connected";
    }
    wifiReconnectPending = false;
    wifiLastObservedConnected = true;
    if (wifiReconnectTask.isEnabled()) wifiReconnectTask.disable();
    if (appState == AppState::OFFLINE || appState == AppState::WIFI_CONNECTING) {
      machine.trigger(EVT_WIFI_UP);
    }
    return;
  }

  if (wifiLastObservedConnected) {
    ++wifiDisconnectObservedCount;
    wifiLastDisconnectObservedMs = millis();
  }
  wifiLastObservedConnected = false;

  if (appState == AppState::WIFI_CONNECTING || appState == AppState::ONLINE) {
    machine.trigger(EVT_WIFI_DOWN);
  }

  if (!wifiReconnectAllowedNow()) {
    if (wifiReconnectTask.isEnabled()) wifiReconnectTask.disable();
    wifiLastReconnectResult = "suppressed";
    return;
  }

  if (!wifiReconnectTask.isEnabled()) {
    wifiReconnectTask.enable();
    wifiReconnectTask.forceNextIteration();
  }
}

String wifiRuntimeStatusJson() {
  String json = "{";
  json += "\"coordinator_task_enabled\":" + String(wifiCoordinatorTask.isEnabled() ? "true" : "false") + ",";
  json += "\"reconnect_task_enabled\":" + String(wifiReconnectTask.isEnabled() ? "true" : "false") + ",";
  json += "\"reconnect_attempt_count\":" + String(wifiReconnectAttemptCount) + ",";
  json += "\"reconnect_success_count\":" + String(wifiReconnectSuccessCount) + ",";
  json += "\"disconnect_observed_count\":" + String(wifiDisconnectObservedCount) + ",";
  json += "\"last_reconnect_attempt_ms\":" + String(wifiLastReconnectAttemptMs) + ",";
  json += "\"last_reconnect_success_ms\":" + String(wifiLastReconnectSuccessMs) + ",";
  json += "\"last_disconnect_observed_ms\":" + String(wifiLastDisconnectObservedMs) + ",";
  json += "\"last_reconnect_result\":\"" + wifiLastReconnectResult + "\"";
  json += "}";
  return json;
}

#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT
void runWifiTestDisconnectTask() {
  WiFi.disconnect(false, false);
}
#endif


bool mqttReconnectAllowedNow() {
#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT
  return static_cast<int32_t>(millis() - mqttReconnectSuppressedUntil) >= 0;
#else
  return true;
#endif
}

void runMqttReconnectTask() {
  if (WiFi.status() != WL_CONNECTED || wifiManager.getConfigPortalActive() ||
      !networkServicesStarted || !mqttConfigured() || !mqttReconnectAllowedNow()) {
    mqttLastReconnectResult = "not_eligible";
    mqttReconnectTask.disable();
    return;
  }

  if (mqttClient.connected()) {
    mqttLastReconnectResult = "already_connected";
    mqttReconnectTask.disable();
    return;
  }

  ++mqttReconnectAttemptCount;
  mqttLastReconnectAttemptMs = millis();
  const bool connected = connectMqtt();
  if (connected) {
    ++mqttReconnectSuccessCount;
    mqttLastReconnectSuccessMs = millis();
    mqttLastReconnectResult = "connected";
    mqttReconnectTask.disable();
  } else {
    mqttLastReconnectResult = "failed_retry_scheduled";
  }
}

void runMqttTelemetryTask() {
  if (!mqttClient.connected()) {
    mqttLastTelemetryResult = "not_connected";
    mqttTelemetryTask.disable();
    return;
  }

  ++mqttTelemetryAttemptCount;
  mqttLastTelemetryAttemptMs = millis();
  const String telemetry = statusJson();
  const bool published = mqttClient.publish(topicTelemetry.c_str(), telemetry.c_str());
  if (published) {
    ++mqttTelemetryPublishCount;
    mqttLastTelemetryPublishMs = millis();
    mqttLastTelemetryResult = "published";
  } else {
    mqttLastTelemetryResult = "publish_failed";
  }
}

void coordinateMqttTasks() {
  const bool eligible = networkServicesStarted &&
                        WiFi.status() == WL_CONNECTED &&
                        !wifiManager.getConfigPortalActive() && mqttConfigured();

  if (!eligible) {
    if (mqttReconnectTask.isEnabled()) mqttReconnectTask.disable();
    if (mqttTelemetryTask.isEnabled()) mqttTelemetryTask.disable();
    return;
  }

  if (mqttClient.connected()) {
    if (mqttReconnectTask.isEnabled()) mqttReconnectTask.disable();
    if (!mqttTelemetryTask.isEnabled()) {
      mqttTelemetryTask.restartDelayed(ProjectConfig::HEARTBEAT_INTERVAL_MS);
    }
    return;
  }

  if (mqttTelemetryTask.isEnabled()) mqttTelemetryTask.disable();

  if (!mqttReconnectAllowedNow()) {
    if (mqttReconnectTask.isEnabled()) mqttReconnectTask.disable();
    mqttLastReconnectResult = "suppressed";
    return;
  }

  if (!mqttReconnectTask.isEnabled()) {
    mqttReconnectTask.enable();
    mqttReconnectTask.forceNextIteration();
  }
}

String mqttRuntimeStatusJson() {
  String json = "{";
  json += "\"coordinator_task_enabled\":" + String(mqttCoordinatorTask.isEnabled() ? "true" : "false") + ",";
  json += "\"reconnect_task_enabled\":" + String(mqttReconnectTask.isEnabled() ? "true" : "false") + ",";
  json += "\"telemetry_task_enabled\":" + String(mqttTelemetryTask.isEnabled() ? "true" : "false") + ",";
  json += "\"reconnect_attempt_count\":" + String(mqttReconnectAttemptCount) + ",";
  json += "\"reconnect_success_count\":" + String(mqttReconnectSuccessCount) + ",";
  json += "\"telemetry_attempt_count\":" + String(mqttTelemetryAttemptCount) + ",";
  json += "\"telemetry_publish_count\":" + String(mqttTelemetryPublishCount) + ",";
  json += "\"last_reconnect_attempt_ms\":" + String(mqttLastReconnectAttemptMs) + ",";
  json += "\"last_reconnect_success_ms\":" + String(mqttLastReconnectSuccessMs) + ",";
  json += "\"last_telemetry_attempt_ms\":" + String(mqttLastTelemetryAttemptMs) + ",";
  json += "\"last_telemetry_publish_ms\":" + String(mqttLastTelemetryPublishMs) + ",";
  json += "\"last_reconnect_result\":\"" + mqttLastReconnectResult + "\",";
  json += "\"last_telemetry_result\":\"" + mqttLastTelemetryResult + "\"";
  json += "}";
  return json;
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
    RestartService::restartNow();
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
    body += "configuration=/api/configuration\n";
    body += "configuration_status=/api/configuration/status\n";
    body += "rules_status=/api/rules/status\n";
    body += "rules_runtime=/api/rules/runtime\n";
    body += "persisted_rules=/api/rules/persisted\n";
    body += "schedule_status=/api/schedules/status\n";
    body += "components=/api/components\n";
    body += "supervisor=/api/supervisor\n";
    body += "wifi_runtime=/api/wifi/runtime\n";
    body += "mqtt_runtime=/api/mqtt/runtime\n";
    body += "console=/webserial\n";
    body += "mqtt_config=/config/mqtt\n";
    request->send(200, "text/plain", body);
  });

  server.on("/api/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", statusJson());
  });

  server.on("/api/components", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", componentsStatusJson());
  });

  server.on("/api/rules/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", ruleEngine.statusJson());
  });

  server.on("/api/rules/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", ruleRuntime.statusJson());
  });

  server.on("/api/rules/persisted", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", persistedRuleLoader.statusJson());
  });

  server.on("/api/schedules/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", localScheduleService.statusJson());
  });

  server.on("/api/supervisor", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", runtimeSupervisor.statusJson());
  });

  server.on("/api/wifi/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", wifiRuntimeStatusJson());
  });

  server.on("/api/mqtt/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {
    request->send(200, "application/json", mqttRuntimeStatusJson());
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

  server.on("/api/test/mqtt/disconnect", HTTP_POST, [](AsyncWebServerRequest* request) {
    mqttReconnectSuppressedUntil = millis() + 8000UL;
    mqttClient.disconnect();
    request->send(202, "application/json",
                  "{\"accepted\":true,\"reconnect_suppressed_ms\":8000}");
  });

  server.on("/api/test/wifi/disconnect", HTTP_POST, [](AsyncWebServerRequest* request) {
    wifiReconnectSuppressedUntil = millis() + 8000UL;
    wifiTestDisconnectTask.restartDelayed(250);
    request->send(202, "application/json",
                  "{\"accepted\":true,\"disconnect_delay_ms\":250,\"reconnect_suppressed_ms\":8000}");
  });
#endif

#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS
  server.on("/api/test/rules/status", HTTP_GET, [](AsyncWebServerRequest* request) {
    String json = "{\"engine\":" + ruleEngine.statusJson() +
                  ",\"input\":" + virtualTemperature.statusJson() +
                  ",\"actuator\":" + virtualHeater.statusJson() + "}";
    request->send(200, "application/json", json);
  });

  server.on("/api/test/rules/configure", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("on_below", true) || !request->hasParam("off_above", true)) {
      request->send(400, "application/json", "{\"error\":\"thresholds_required\"}");
      return;
    }
    Rules::HysteresisRule rule;
    rule.id = "demo.temperature.heater";
    rule.enabled = !request->hasParam("enabled", true) ||
                   request->getParam("enabled", true)->value() != "0";
    rule.onBelow = request->getParam("on_below", true)->value().toFloat();
    rule.offAbove = request->getParam("off_above", true)->value().toFloat();
    String error;
    if (!ruleEngine.configure(rule, error)) {
      request->send(400, "application/json", String("{\"error\":\"") + error + "\"}");
      return;
    }
    virtualHeater.enable(false);
    ruleRuntime.refreshEligibility();
    request->send(200, "application/json", ruleEngine.statusJson());
  });

  server.on("/api/test/rules/input", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("value", true)) {
      request->send(400, "application/json", "{\"error\":\"value_required\"}");
      return;
    }
    const float value = request->getParam("value", true)->value().toFloat();
    if (!virtualTemperature.setValue(value)) {
      request->send(400, "application/json", "{\"error\":\"value_invalid\"}");
      return;
    }
    request->send(200, "application/json", virtualTemperature.statusJson());
  });

  server.on("/api/test/rules/evaluate", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!virtualTemperature.hasValue()) {
      request->send(409, "application/json", "{\"error\":\"input_not_ready\"}");
      return;
    }
    if (!virtualHeater.enabled()) virtualHeater.enable(false);
    bool desired = virtualHeater.isOn();
    Rules::RuleDecision decision = Rules::RuleDecision::None;
    String error;
    if (!ruleEngine.evaluate(virtualTemperature.value(), virtualHeater.isOn(),
                             desired, decision, error)) {
      request->send(409, "application/json", String("{\"error\":\"") + error + "\"}");
      return;
    }
    if (decision != Rules::RuleDecision::Disabled && !virtualHeater.applyDesired(desired)) {
      request->send(500, "application/json", "{\"error\":\"actuator_rejected\"}");
      return;
    }
    String json = "{\"engine\":" + ruleEngine.statusJson() +
                  ",\"input\":" + virtualTemperature.statusJson() +
                  ",\"actuator\":" + virtualHeater.statusJson() + "}";
    request->send(200, "application/json", json);
  });

  server.on("/api/test/rules/reset", HTTP_POST, [](AsyncWebServerRequest* request) {
    ruleEngine.clear();
    ruleRuntime.setFaultPolicy(Rules::ActuatorFaultPolicy::SafeOff);
    ruleRuntime.refreshEligibility();
    virtualTemperature.disable();
    virtualHeater.disable();
    request->send(200, "application/json", "{\"reset\":true}");
  });
#endif

#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS
  server.on("/api/test/rules/fault-policy", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("policy", true)) {
      request->send(400, "application/json", "{\"error\":\"policy_required\"}");
      return;
    }
    Rules::ActuatorFaultPolicy policy;
    if (!Rules::parseActuatorFaultPolicy(request->getParam("policy", true)->value(), policy)) {
      request->send(400, "application/json", "{\"error\":\"policy_unsupported\"}");
      return;
    }
    ruleRuntime.setFaultPolicy(policy);
    ruleRuntime.requestEvaluation("policy_test");
    request->send(200, "application/json", ruleRuntime.statusJson());
  });

  server.on("/api/test/rules/fault", HTTP_POST, [](AsyncWebServerRequest* request) {
    String code = request->hasParam("code", true)
                      ? request->getParam("code", true)->value()
                      : String("virtual_sensor_fault");
    code.trim();
    if (!code.length()) code = "virtual_sensor_fault";
    virtualTemperature.injectFault(code.c_str());
    request->send(202, "application/json", virtualTemperature.statusJson());
  });

  server.on("/api/test/rules/recover", HTTP_POST, [](AsyncWebServerRequest* request) {
    virtualTemperature.recover();
    request->send(202, "application/json", virtualTemperature.statusJson());
  });
#endif

#ifdef PROJ_RULE_ENGINE_TEST_ENDPOINTS
  server.on("/api/test/rules/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {
    String json = "{\"engine\":" + ruleEngine.statusJson() +
                  ",\"runtime\":" + ruleRuntime.statusJson() +
                  ",\"input\":" + virtualTemperature.statusJson() +
                  ",\"actuator\":" + virtualHeater.statusJson() + "}";
    request->send(200, "application/json", json);
  });

  server.on("/api/test/rules/queue-input", HTTP_POST, [](AsyncWebServerRequest* request) {
    if (!request->hasParam("value", true) || !request->hasParam("delay_ms", true)) {
      request->send(400, "application/json", "{\"error\":\"value_and_delay_required\"}");
      return;
    }
    const float value = request->getParam("value", true)->value().toFloat();
    const long parsedDelay = request->getParam("delay_ms", true)->value().toInt();
    if (parsedDelay < 0 || parsedDelay > 15000) {
      request->send(400, "application/json", "{\"error\":\"delay_out_of_range\"}");
      return;
    }
    ruleTestPendingInput = value;
    if (!ruleTestInputTask.restartDelayed(static_cast<unsigned long>(parsedDelay))) {
      request->send(500, "application/json", "{\"error\":\"scheduler_rejected\"}");
      return;
    }
    String json = "{\"accepted\":true,\"delay_ms\":" + String(parsedDelay) +
                  ",\"value\":" + String(value, 3) + "}";
    request->send(202, "application/json", json);
  });
#endif

  registerFirmwareMetadataRoutes(server);
  FirmwareUpdate::registerRoutes(server);
  RemoteFirmwareUpdate::registerRoutes(server);
  FirmwareUpdatePolicy::registerRoutes(server);
  FirmwareUpdateScheduler::registerRoutes(server);
  ConfigurationStore::registerRoutes(server);

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
  mqttClient.setBufferSize(ProjectConfig::MQTT_BUFFER_SIZE);
  mqttClient.setKeepAlive(30);
  mqttClient.setCallback(mqttMessageReceived);

  networkServicesStarted = true;
  logLine("HTTP server ready: http://" + WiFi.localIP().toString() + "/");
  logLine("WebSerial ready: http://" + WiFi.localIP().toString() + "/webserial");
  mqttCoordinatorTask.forceNextIteration();
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
  if (!ConfigurationStore::begin()) {
    Serial.println("CONFIGURATION_STORE_INIT_FAILED");
  }
  if (!ruleEngine.begin()) {
    Serial.println("RULE_ENGINE_INIT_FAILED");
  }

  runtimeEvents.subscribe(handleRuntimeEvent);
  if (!ruleRuntime.begin()) {
    Serial.println("RULE_RUNTIME_INIT_FAILED");
  }
  runtimeComponents.add(connectivityComponent);
  runtimeComponents.add(virtualTemperature);
  runtimeComponents.add(virtualHeater);
  runtimeComponents.add(virtualScheduleOutput);
  if (!runtimeComponents.beginAll()) {
    Serial.println("RUNTIME_COMPONENT_INIT_DEGRADED");
  }
  virtualHeater.enable(false);
  virtualScheduleOutput.enable(false);
  localScheduleService.begin();
  ConfigurationStore::setLifecycleCallbacks(validatePersistedConfiguration, activatePersistedConfiguration);
  String localActivationError;
  const String activeConfiguration = ConfigurationStore::activeJson();
  if (!persistedRuleLoader.activateDocument(activeConfiguration, ConfigurationStore::revision(), localActivationError)) {
    Serial.println("PERSISTED_RULE_LOAD_FAILED");
  }
  localActivationError = "";
  if (!localScheduleService.activateDocument(activeConfiguration, ConfigurationStore::revision(), localActivationError)) {
    Serial.println("LOCAL_SCHEDULE_LOAD_FAILED");
  }
  runtimeSupervisor.begin();
  connectivityHealthTask.enableDelayed(2000);
  supervisorTask.enableDelayed(1000);
  wifiCoordinatorTask.enableDelayed(250);
  mqttCoordinatorTask.enableDelayed(250);

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
  RestartService::setBeforeRestartHook([]() {
    if (drd) drd->stop();
  });

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
    RestartService::restartNow();
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
  runtimeEvents.process(8);

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
    // Wi-Fi retry eligibility/cadence and ONLINE/OFFLINE FSM transitions are
    // coordinated by TaskScheduler. The loop remains available to local work.
    delay(2);
    return;
  }

  startNetworkServices();
  WebSerial.loop();
  // PubSubClient::loop() remains a fast cooperative service call. Stage 6D moves
  // reconnect eligibility/backoff and periodic telemetry timing to TaskScheduler.
  mqttClient.loop();

  delay(2);
}
