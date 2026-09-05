from pathlib import Path


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"missing {label}")
    return text.replace(old, new, 1)

p = Path('include/project_config.h')
s = p.read_text()
s = replace_once(
    s,
    'constexpr uint32_t MQTT_RECONNECT_INTERVAL_MS = 5000;\nconstexpr uint32_t HEARTBEAT_INTERVAL_MS = 10000;',
    'constexpr uint32_t WIFI_RECONNECT_INTERVAL_MS = 5000;\nconstexpr uint32_t MQTT_RECONNECT_INTERVAL_MS = 5000;\nconstexpr uint32_t HEARTBEAT_INTERVAL_MS = 10000;',
    'wifi reconnect config')
p.write_text(s)

p = Path('src/main.cpp')
s = p.read_text()

s = replace_once(
    s,
    'void sampleConnectivityComponent();\nvoid evaluateRuntimeSupervisor();\nvoid coordinateMqttTasks();',
    'void sampleConnectivityComponent();\nvoid evaluateRuntimeSupervisor();\nvoid coordinateWifiTasks();\nvoid runWifiReconnectTask();\nString wifiRuntimeStatusJson();\n#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT\nvoid runWifiTestDisconnectTask();\n#endif\nvoid coordinateMqttTasks();',
    'wifi declarations')

s = replace_once(
    s,
    'Task supervisorTask(1000, TASK_FOREVER, evaluateRuntimeSupervisor,\n                    &cooperativeScheduler, false);\nTask mqttCoordinatorTask(250, TASK_FOREVER, coordinateMqttTasks,',
    'Task supervisorTask(1000, TASK_FOREVER, evaluateRuntimeSupervisor,\n                    &cooperativeScheduler, false);\nTask wifiCoordinatorTask(250, TASK_FOREVER, coordinateWifiTasks,\n                         &cooperativeScheduler, false);\nTask wifiReconnectTask(ProjectConfig::WIFI_RECONNECT_INTERVAL_MS, TASK_FOREVER,\n                       runWifiReconnectTask, &cooperativeScheduler, false);\n#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT\nTask wifiTestDisconnectTask(250, TASK_ONCE, runWifiTestDisconnectTask,\n                            &cooperativeScheduler, false);\n#endif\nTask mqttCoordinatorTask(250, TASK_FOREVER, coordinateMqttTasks,',
    'wifi tasks')

s = replace_once(
    s,
    'bool mqttTls = false;\nunsigned long lastWifiRetry = 0;\nuint32_t mqttReconnectAttemptCount = 0;',
    'bool mqttTls = false;\nuint32_t wifiReconnectAttemptCount = 0;\nuint32_t wifiReconnectSuccessCount = 0;\nuint32_t wifiDisconnectObservedCount = 0;\nunsigned long wifiLastReconnectAttemptMs = 0;\nunsigned long wifiLastReconnectSuccessMs = 0;\nunsigned long wifiLastDisconnectObservedMs = 0;\nString wifiLastReconnectResult = "never";\nbool wifiReconnectPending = false;\nbool wifiLastObservedConnected = false;\n#ifdef PROJ_OTA_TEST_MQTT_LOOPBACK_ENDPOINT\nunsigned long wifiReconnectSuppressedUntil = 0;\n#endif\nuint32_t mqttReconnectAttemptCount = 0;',
    'wifi runtime state')

s = replace_once(
    s,
    '  json += "\\\"rssi\\\":" + String(WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0) + ",";\n  json += "\\\"mqtt\\\":" + String(mqttClient.connected() ? "true" : "false") + ",";',
    '  json += "\\\"rssi\\\":" + String(WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0) + ",";\n  json += "\\\"wifi_runtime\\\":" + wifiRuntimeStatusJson() + ",";\n  json += "\\\"mqtt\\\":" + String(mqttClient.connected() ? "true" : "false") + ",";',
    'wifi status json')

marker = '\n\nbool mqttReconnectAllowedNow() {'
if marker not in s:
    raise SystemExit('missing mqtt runtime insertion marker')
wifi_impl = r'''

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
'''
s = s.replace(marker, wifi_impl + marker, 1)

s = replace_once(
    s,
    '    body += "supervisor=/api/supervisor\\n";\n    body += "mqtt_runtime=/api/mqtt/runtime\\n";',
    '    body += "supervisor=/api/supervisor\\n";\n    body += "wifi_runtime=/api/wifi/runtime\\n";\n    body += "mqtt_runtime=/api/mqtt/runtime\\n";',
    'root wifi route')

s = replace_once(
    s,
    '  server.on("/api/mqtt/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", mqttRuntimeStatusJson());\n  });',
    '  server.on("/api/wifi/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", wifiRuntimeStatusJson());\n  });\n\n  server.on("/api/mqtt/runtime", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", mqttRuntimeStatusJson());\n  });',
    'wifi runtime route')

s = replace_once(
    s,
    '  server.on("/api/test/mqtt/disconnect", HTTP_POST, [](AsyncWebServerRequest* request) {\n    mqttReconnectSuppressedUntil = millis() + 8000UL;\n    mqttClient.disconnect();\n    request->send(202, "application/json",\n                  "{\\\"accepted\\\":true,\\\"reconnect_suppressed_ms\\\":8000}");\n  });',
    '  server.on("/api/test/mqtt/disconnect", HTTP_POST, [](AsyncWebServerRequest* request) {\n    mqttReconnectSuppressedUntil = millis() + 8000UL;\n    mqttClient.disconnect();\n    request->send(202, "application/json",\n                  "{\\\"accepted\\\":true,\\\"reconnect_suppressed_ms\\\":8000}");\n  });\n\n  server.on("/api/test/wifi/disconnect", HTTP_POST, [](AsyncWebServerRequest* request) {\n    wifiReconnectSuppressedUntil = millis() + 8000UL;\n    wifiTestDisconnectTask.restartDelayed(250);\n    request->send(202, "application/json",\n                  "{\\\"accepted\\\":true,\\\"disconnect_delay_ms\\\":250,\\\"reconnect_suppressed_ms\\\":8000}");\n  });',
    'wifi test route')

s = replace_once(
    s,
    '  supervisorTask.enableDelayed(1000);\n  mqttCoordinatorTask.enableDelayed(250);',
    '  supervisorTask.enableDelayed(1000);\n  wifiCoordinatorTask.enableDelayed(250);\n  mqttCoordinatorTask.enableDelayed(250);',
    'wifi coordinator setup')

old_loop = '''  const bool wifiUp = WiFi.status() == WL_CONNECTED;\n\n  if (!wifiUp) {\n    if (appState == AppState::WIFI_CONNECTING) {\n      machine.trigger(EVT_WIFI_DOWN);\n    } else if (appState == AppState::ONLINE) {\n      machine.trigger(EVT_WIFI_DOWN);\n    }\n\n    if (millis() - lastWifiRetry >= ProjectConfig::MQTT_RECONNECT_INTERVAL_MS) {\n      lastWifiRetry = millis();\n      WiFi.reconnect();\n    }\n    delay(5);\n    return;\n  }\n\n  if (appState == AppState::OFFLINE || appState == AppState::WIFI_CONNECTING) {\n    machine.trigger(EVT_WIFI_UP);\n  }\n\n  startNetworkServices();'''
new_loop = '''  const bool wifiUp = WiFi.status() == WL_CONNECTED;\n\n  if (!wifiUp) {\n    // Wi-Fi retry eligibility/cadence and ONLINE/OFFLINE FSM transitions are\n    // coordinated by TaskScheduler. The loop remains available to local work.\n    delay(2);\n    return;\n  }\n\n  startNetworkServices();'''
s = replace_once(s, old_loop, new_loop, 'manual wifi retry loop')

p.write_text(s)

p = Path('docs/ROADMAP.md')
s = p.read_text()
s = s.replace('## Stage 6 — Core modular runtime [in progress — Stage 6D validated]',
              '## Stage 6 — Core modular runtime [in progress — Stage 6D validated, Stage 6E in progress]')
needle = '- [x] **Stage 6D** — MQTT reconnect eligibility/retry cadence and periodic telemetry heartbeat migrated to TaskScheduler; physical disconnect/reconnect and telemetry proof complete.\n'
if needle in s and 'Stage 6E' not in s[s.find(needle):s.find(needle)+400]:
    s = s.replace(needle, needle + '- [~] **Stage 6E** — migrate Wi-Fi reconnect eligibility/retry cadence to TaskScheduler, keeping the reconnect work task disabled while Wi-Fi is healthy or the config portal is active.\n', 1)
p.write_text(s)

p = Path('docs/architecture.md')
s = p.read_text()
if '### Stage 6E Wi-Fi scheduling migration' not in s:
    s += '''\n\n### Stage 6E Wi-Fi scheduling migration\n\nWi-Fi reconnect timing is the next incremental migration to the common cooperative runtime. A lightweight coordinator observes Wi-Fi/config-portal eligibility; the actual reconnect task remains disabled while there is no meaningful work. On connection loss, the coordinator drives the existing application FSM to `OFFLINE` and enables the reconnect task; on recovery it drives `EVT_WIFI_UP` and disables reconnect work again. This removes another hand-written `millis()` retry timer without changing local-autonomy semantics.\n'''
p.write_text(s)

p = Path('docs/runtime-test-log.md')
s = p.read_text()
if '## 2026-09-05 — Stage 6E Wi-Fi scheduler migration' not in s:
    s += '''\n\n## 2026-09-05 — Stage 6E Wi-Fi scheduler migration\n\nImplementation checkpoint:\n\n- remove `lastWifiRetry` / main-loop `millis()` retry timing;\n- add TaskScheduler Wi-Fi coordinator + reconnect task;\n- reconnect task disabled while Wi-Fi is healthy, config portal is active, or a controlled lab suppression is active;\n- preserve existing application FSM semantics (`ONLINE <-> OFFLINE`) rather than inventing a second state owner;\n- expose `/api/wifi/runtime` counters and task enable state;\n- physical proof pending: signed lab image, controlled Wi-Fi disconnect, observed reconnect attempt/success, connectivity/Supervisor recovery, clean target image.\n'''
p.write_text(s)

print('STAGE6E_IMPLEMENT_PATCH_OK')
