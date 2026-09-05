from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(f"missing {label}")
    return text.replace(old, new, 1)

p = Path("src/main.cpp")
s = p.read_text()

s = replace_once(
    s,
    "void sampleConnectivityComponent();\nvoid evaluateRuntimeSupervisor();\n",
    "void sampleConnectivityComponent();\nvoid evaluateRuntimeSupervisor();\nvoid coordinateMqttTasks();\nvoid runMqttReconnectTask();\nvoid runMqttTelemetryTask();\nString mqttRuntimeStatusJson();\n",
    "mqtt task prototypes",
)

s = replace_once(
    s,
    "Task supervisorTask(1000, TASK_FOREVER, evaluateRuntimeSupervisor,\n                    &cooperativeScheduler, false);\n",
    "Task supervisorTask(1000, TASK_FOREVER, evaluateRuntimeSupervisor,\n                    &cooperativeScheduler, false);\nTask mqttCoordinatorTask(250, TASK_FOREVER, coordinateMqttTasks,\n                         &cooperativeScheduler, false);\nTask mqttReconnectTask(ProjectConfig::MQTT_RECONNECT_INTERVAL_MS, TASK_FOREVER,\n                       runMqttReconnectTask, &cooperativeScheduler, false);\nTask mqttTelemetryTask(ProjectConfig::HEARTBEAT_INTERVAL_MS, TASK_FOREVER,\n                       runMqttTelemetryTask, &cooperativeScheduler, false);\n",
    "mqtt TaskScheduler declarations",
)

s = replace_once(
    s,
    "unsigned long lastMqttAttempt = 0;\nunsigned long lastHeartbeat = 0;\nunsigned long lastWifiRetry = 0;\n",
    "unsigned long lastWifiRetry = 0;\nuint32_t mqttReconnectAttemptCount = 0;\nuint32_t mqttReconnectSuccessCount = 0;\nuint32_t mqttTelemetryAttemptCount = 0;\nuint32_t mqttTelemetryPublishCount = 0;\nunsigned long mqttLastReconnectAttemptMs = 0;\nunsigned long mqttLastReconnectSuccessMs = 0;\nunsigned long mqttLastTelemetryAttemptMs = 0;\nunsigned long mqttLastTelemetryPublishMs = 0;\nString mqttLastReconnectResult = \"never\";\nString mqttLastTelemetryResult = \"never\";\n",
    "legacy MQTT millis state",
)

s = replace_once(
    s,
    "  lastMqttAttempt = millis();\n  String clientId = String(ProjectConfig::DEVICE_HOSTNAME) + \"-\" + deviceId;\n",
    "  String clientId = String(ProjectConfig::DEVICE_HOSTNAME) + \"-\" + deviceId;\n",
    "lastMqttAttempt assignment",
)

anchor = "bool connectMqtt() {\n"
start = s.find(anchor)
if start < 0:
    raise SystemExit("missing connectMqtt")
end_marker = "\nvoid handleWebCommand(uint8_t* data, size_t len) {"
end = s.find(end_marker, start)
if end < 0:
    raise SystemExit("missing handleWebCommand after connectMqtt")
connect_block = s[start:end]
if "void coordinateMqttTasks()" not in s:
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
    s = s[:end] + extra + s[end:]

s = replace_once(
    s,
    "  json += \"\\\"mqtt_tls\\\":\" + String(mqttTls ? \"true\" : \"false\") + \",\";\n  json += \"\\\"uptime_ms\\\":\" + String(millis()) + \",\";\n",
    "  json += \"\\\"mqtt_tls\\\":\" + String(mqttTls ? \"true\" : \"false\") + \",\";\n  json += \"\\\"mqtt_runtime\\\":\" + mqttRuntimeStatusJson() + \",\";\n  json += \"\\\"uptime_ms\\\":\" + String(millis()) + \",\";\n",
    "mqtt runtime status embedding",
)

s = replace_once(
    s,
    "  server.on(\"/api/supervisor\", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, \"application/json\", runtimeSupervisor.statusJson());\n  });\n",
    "  server.on(\"/api/supervisor\", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, \"application/json\", runtimeSupervisor.statusJson());\n  });\n\n  server.on(\"/api/mqtt/runtime\", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, \"application/json\", mqttRuntimeStatusJson());\n  });\n",
    "mqtt runtime API",
)

s = replace_once(
    s,
    "    body += \"supervisor=/api/supervisor\\n\";\n    body += \"console=/webserial\\n\";\n",
    "    body += \"supervisor=/api/supervisor\\n\";\n    body += \"mqtt_runtime=/api/mqtt/runtime\\n\";\n    body += \"console=/webserial\\n\";\n",
    "landing mqtt runtime link",
)

s = replace_once(
    s,
    "  networkServicesStarted = true;\n  logLine(\"HTTP server ready: http://\" + WiFi.localIP().toString() + \"/\");\n  logLine(\"WebSerial ready: http://\" + WiFi.localIP().toString() + \"/webserial\");\n  connectMqtt();\n",
    "  networkServicesStarted = true;\n  logLine(\"HTTP server ready: http://\" + WiFi.localIP().toString() + \"/\");\n  logLine(\"WebSerial ready: http://\" + WiFi.localIP().toString() + \"/webserial\");\n  mqttCoordinatorTask.forceNextIteration();\n",
    "initial connect scheduling",
)

s = replace_once(
    s,
    "  connectivityHealthTask.enableDelayed(2000);\n  supervisorTask.enableDelayed(1000);\n",
    "  connectivityHealthTask.enableDelayed(2000);\n  supervisorTask.enableDelayed(1000);\n  mqttCoordinatorTask.enableDelayed(250);\n",
    "mqtt coordinator setup",
)

legacy = r'''  mqttClient.loop();

  bool mqttReconnectAllowed = true;
#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT
  mqttReconnectAllowed = millis() >= mqttReconnectSuppressedUntil;
#endif
  if (mqttReconnectAllowed && !mqttClient.connected() && mqttConfigured() &&
      millis() - lastMqttAttempt >= ProjectConfig::MQTT_RECONNECT_INTERVAL_MS) {
    connectMqtt();
  }

  if (mqttClient.connected() &&
      millis() - lastHeartbeat >= ProjectConfig::HEARTBEAT_INTERVAL_MS) {
    lastHeartbeat = millis();
    String telemetry = statusJson();
    mqttClient.publish(topicTelemetry.c_str(), telemetry.c_str());
  }
'''
new = r'''  // PubSubClient::loop() remains a fast cooperative service call. Stage 6D moves
  // reconnect eligibility/backoff and periodic telemetry timing to TaskScheduler.
  mqttClient.loop();
'''
s = replace_once(s, legacy, new, "legacy MQTT reconnect/heartbeat polling")

p.write_text(s)

# Documentation checkpoint before physical proof.
p = Path("docs/ROADMAP.md")
s = p.read_text()
s = s.replace(
    "- [ ] **Stage 6D** — migrate additional periodic/retry work to TaskScheduler where it improves consistency, starting with MQTT reconnect and telemetry without changing network behavior.",
    "- [~] **Stage 6D** — MQTT reconnect eligibility/retry cadence and periodic telemetry heartbeat migrated to TaskScheduler; physical disconnect/reconnect + telemetry proof pending.",
)
p.write_text(s)

p = Path("docs/architecture.md")
s = p.read_text()
if "## MQTT TaskScheduler migration (Stage 6D)" not in s:
    s += r'''

## MQTT TaskScheduler migration (Stage 6D)

Stage 6D removes the hand-written `lastMqttAttempt` and `lastHeartbeat` timers from the main loop. Three cooperative tasks now separate eligibility from work:

```text
mqttCoordinatorTask (250 ms, lightweight)
    |-- disconnected + eligible -> enable/force mqttReconnectTask
    |-- connected -> disable reconnect, delayed-enable telemetry
    `-- unavailable/portal/not configured -> disable both work tasks

mqttReconnectTask (5 s retry interval)
    `-- attempts the existing MQTT connect operation, disables itself on success

mqttTelemetryTask (10 s periodic)
    `-- publishes the existing shared status document only while connected
```

The important platform rule is preserved: work tasks remain disabled when their work is meaningless. `PubSubClient::loop()` remains a fast per-loop cooperative service call for now; Stage 6D changes timing/eligibility, not the proven transport implementation. The synchronous `PubSubClient::connect()` body is intentionally unchanged in this migration and can be hardened separately if connection latency later becomes a scheduling problem.

`GET /api/mqtt/runtime` exposes scheduler/counter state without credentials so reconnect and telemetry cadence can be physically validated.
'''
p.write_text(s)

p = Path("docs/runtime-test-log.md")
s = p.read_text()
if "## 2026-09-05 — Stage 6D MQTT scheduler migration" not in s:
    s += r'''

## 2026-09-05 — Stage 6D MQTT scheduler migration

Implementation checkpoint:

- removed main-loop `millis()` timers for MQTT reconnect and heartbeat telemetry;
- added TaskScheduler coordinator + reconnect + telemetry tasks;
- reconnect work task is disabled while connected, unconfigured, offline, in config portal, or intentionally suppressed by a test-gated proof;
- telemetry task is disabled while MQTT is disconnected and delayed by the configured heartbeat interval after connection;
- existing `PubSubClient::loop()` and connection/publish semantics remain unchanged;
- `/api/mqtt/runtime` exposes task enable state and reconnect/telemetry counters;
- physical proof pending: signed lab image, real MQTT disconnect/recovery, telemetry counter progression, clean target image.
'''
p.write_text(s)

print("STAGE6D_IMPLEMENT_PATCH_OK")
