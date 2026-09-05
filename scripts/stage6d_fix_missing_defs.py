from pathlib import Path

p = Path('src/main.cpp')
s = p.read_text()
if '\nvoid coordinateMqttTasks() {' in s:
    print('STAGE6D_MQTT_DEFS_ALREADY_PRESENT')
    raise SystemExit(0)
marker = '\nvoid handleWebCommand(uint8_t* data, size_t len) {'
pos = s.find(marker)
if pos < 0:
    raise SystemExit('missing handleWebCommand marker')
extra = r'''

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
'''
s = s[:pos] + extra + s[pos:]
p.write_text(s)
print('STAGE6D_MQTT_DEFS_FIXED')
