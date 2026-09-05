#!/usr/bin/env python3
from pathlib import Path


def write(path: str, content: str):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def replace_once(path: str, old: str, new: str):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:80]!r}")
    p.write_text(text.replace(old, new, 1))


write("include/core/runtime_events.h", r'''#pragma once

#include <stdint.h>

namespace RuntimeCore {

enum class RuntimeEventType : uint16_t {
  ComponentStateChanged = 100,
  ComponentHealthChanged = 101
};

}  // namespace RuntimeCore
''')

write("include/components/connectivity_component.h", r'''#pragma once

#include <Arduino.h>

#include "core/component.h"
#include "core/event_bus.h"

namespace Components {

class ConnectivityComponent : public RuntimeCore::Component {
 public:
  using BoolProvider = bool (*)();

  ConnectivityComponent(RuntimeCore::EventBus& events,
                        BoolProvider wifiConnected,
                        BoolProvider mqttConnected,
                        BoolProvider mqttConfigured);

  const char* id() const override { return "connectivity"; }
  bool begin() override;
  const char* stateName() const override;
  RuntimeCore::ComponentHealth health() const override { return health_; }

  // Called by TaskScheduler. The component owns state/health semantics; the
  // scheduler owns cadence.
  void sample();

 private:
  enum class State : uint8_t {
    Starting,
    Offline,
    WifiOnly,
    Online
  };

  void transitionTo(State nextState,
                    RuntimeCore::HealthState nextHealth,
                    const char* faultCode);

  RuntimeCore::EventBus& events_;
  BoolProvider wifiConnected_;
  BoolProvider mqttConnected_;
  BoolProvider mqttConfigured_;
  State state_ = State::Starting;
  RuntimeCore::ComponentHealth health_;
  bool started_ = false;
};

}  // namespace Components
''')

write("src/components/connectivity_component.cpp", r'''#include "components/connectivity_component.h"

#include "core/runtime_events.h"

namespace Components {

ConnectivityComponent::ConnectivityComponent(RuntimeCore::EventBus& events,
                                               BoolProvider wifiConnected,
                                               BoolProvider mqttConnected,
                                               BoolProvider mqttConfigured)
    : events_(events),
      wifiConnected_(wifiConnected),
      mqttConnected_(mqttConnected),
      mqttConfigured_(mqttConfigured) {}

bool ConnectivityComponent::begin() {
  started_ = true;
  state_ = State::Starting;
  health_.state = RuntimeCore::HealthState::Recovering;
  health_.faultCode = "starting";
  return wifiConnected_ && mqttConnected_ && mqttConfigured_;
}

const char* ConnectivityComponent::stateName() const {
  switch (state_) {
    case State::Starting: return "STARTING";
    case State::Offline: return "OFFLINE";
    case State::WifiOnly: return "WIFI_ONLY";
    case State::Online: return "ONLINE";
  }
  return "UNKNOWN";
}

void ConnectivityComponent::transitionTo(State nextState,
                                          RuntimeCore::HealthState nextHealth,
                                          const char* faultCode) {
  const uint32_t now = millis();
  const String nextFault = faultCode ? String(faultCode) : String();
  const bool stateChanged = nextState != state_;
  const bool healthChanged = nextHealth != health_.state || nextFault != health_.faultCode;

  if (nextHealth == RuntimeCore::HealthState::Ok) {
    health_.lastSuccessMs = now;
  } else if (healthChanged) {
    health_.lastErrorMs = now;
    ++health_.errorCount;
  }

  state_ = nextState;
  health_.state = nextHealth;
  health_.faultCode = nextFault;

  if (stateChanged) {
    events_.post(static_cast<uint16_t>(RuntimeCore::RuntimeEventType::ComponentStateChanged),
                 id(), static_cast<int32_t>(state_));
  }
  if (healthChanged) {
    events_.post(static_cast<uint16_t>(RuntimeCore::RuntimeEventType::ComponentHealthChanged),
                 id(), static_cast<int32_t>(health_.state));
  }
}

void ConnectivityComponent::sample() {
  if (!started_) return;

  const bool wifiUp = wifiConnected_ && wifiConnected_();
  if (!wifiUp) {
    transitionTo(State::Offline, RuntimeCore::HealthState::Degraded,
                 "wifi_disconnected");
    return;
  }

  const bool configured = mqttConfigured_ && mqttConfigured_();
  if (!configured) {
    transitionTo(State::WifiOnly, RuntimeCore::HealthState::Degraded,
                 "mqtt_not_configured");
    return;
  }

  const bool mqttUp = mqttConnected_ && mqttConnected_();
  if (!mqttUp) {
    transitionTo(State::WifiOnly, RuntimeCore::HealthState::Degraded,
                 "mqtt_disconnected");
    return;
  }

  transitionTo(State::Online, RuntimeCore::HealthState::Ok, "");
}

}  // namespace Components
''')

main = Path("src/main.cpp").read_text()
main = main.replace('#include "update_scheduler.h"\n', '#include "update_scheduler.h"\n#include "core/component_registry.h"\n#include "core/event_bus.h"\n#include "core/runtime_events.h"\n#include "components/connectivity_component.h"\n', 1)
main = main.replace('Scheduler cooperativeScheduler;\n', '''Scheduler cooperativeScheduler;
RuntimeCore::EventBus runtimeEvents;
RuntimeCore::ComponentRegistry runtimeComponents;

bool mqttConfigured();
bool runtimeWifiConnected();
bool runtimeMqttConnected();
bool runtimeMqttConfigured();
void sampleConnectivityComponent();

Components::ConnectivityComponent connectivityComponent(
    runtimeEvents, runtimeWifiConnected, runtimeMqttConnected, runtimeMqttConfigured);
Task connectivityHealthTask(2000, TASK_FOREVER, sampleConnectivityComponent,
                            &cooperativeScheduler, false);
''', 1)
main = main.replace('void logLine(const String& message) {\n  Serial.println(message);\n  if (webStarted) {\n    WebSerial.println(message);\n  }\n}\n', '''void logLine(const String& message) {
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
  }
}
''', 1)
main = main.replace('bool mqttConfigured() {\n  return mqttHost.length() > 0 && mqttPort > 0 &&\n         mqttUsername.length() > 0 && mqttPassword.length() > 0;\n}\n\nString statusJson() {', '''bool mqttConfigured() {
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

void sampleConnectivityComponent() {
  connectivityComponent.sample();
}

String componentsStatusJson() {
  String json = "{\"registry\":" + runtimeComponents.statusJson() + ",";
  json += "\"event_bus\":{\"pending\":" + String(runtimeEvents.pending()) + ",";
  json += "\"dropped\":" + String(runtimeEvents.dropped()) + "}}";
  return json;
}

String statusJson() {''', 1)
main = main.replace('  json += "\\\"update_scheduler\\\":" + FirmwareUpdateScheduler::statusJson() + ",";\n  json += "\\\"state\\\":\\\"" + String(stateName(appState)) + "\\\",";\n', '  json += "\\\"update_scheduler\\\":" + FirmwareUpdateScheduler::statusJson() + ",";\n  json += "\\\"components\\\":" + runtimeComponents.statusJson() + ",";\n  json += "\\\"event_bus\\\":{\\\"pending\\\":" + String(runtimeEvents.pending()) + ",\\\"dropped\\\":" + String(runtimeEvents.dropped()) + "},";\n  json += "\\\"state\\\":\\\"" + String(stateName(appState)) + "\\\",";\n', 1)
main = main.replace('    body += "update_scheduler=/api/update/scheduler\\n";\n    body += "console=/webserial\\n";\n', '    body += "update_scheduler=/api/update/scheduler\\n";\n    body += "components=/api/components\\n";\n    body += "console=/webserial\\n";\n', 1)
main = main.replace('  server.on("/api/status", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", statusJson());\n  });\n\n', '  server.on("/api/status", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", statusJson());\n  });\n\n  server.on("/api/components", HTTP_GET, [](AsyncWebServerRequest* request) {\n    request->send(200, "application/json", componentsStatusJson());\n  });\n\n', 1)
main = main.replace('  preferencesReady = preferences.begin("proj-esp32", false);\n  loadMqttConfig();\n  FirmwareUpdate::begin(preferencesReady);\n', '  preferencesReady = preferences.begin("proj-esp32", false);\n  loadMqttConfig();\n\n  runtimeEvents.subscribe(handleRuntimeEvent);\n  runtimeComponents.add(connectivityComponent);\n  if (!runtimeComponents.beginAll()) {\n    Serial.println("RUNTIME_COMPONENT_INIT_DEGRADED");\n  }\n  connectivityHealthTask.enableDelayed(2000);\n\n  FirmwareUpdate::begin(preferencesReady);\n', 1)
main = main.replace('  cooperativeScheduler.execute();\n\n  const bool portalActive', '  cooperativeScheduler.execute();\n  runtimeEvents.process(8);\n\n  const bool portalActive', 1)
Path("src/main.cpp").write_text(main)

# Stage 6 roadmap progress.
replace_once("docs/ROADMAP.md",
'''- [ ] wire initial real components into the registry;
- [ ] `Supervisor` FSM;
- standardized fault metadata;
- generic serialization for API/MQTT/UI.
''',
'''- [x] wire the first real component (`connectivity`) into the registry;
- [x] standardized component fault metadata (`ComponentHealth`);
- [x] generic registry serialization exposed at `/api/components` and embedded in `/api/status`/MQTT telemetry;
- [x] route component state/health transitions through the bounded `EventBus`;
- [ ] `Supervisor` FSM;
- [ ] migrate additional periodic/retry work to TaskScheduler where it improves consistency (MQTT reconnect, telemetry, future sensors/actuators).
''')

architecture = Path("docs/architecture.md").read_text()
old_ota = '''## OTA

ArduinoOTA is the first OTA mechanism. USB/CP2102 remains the recovery path.

Normal development progression:

```text
first/recovery flash -> USB
normal iteration     -> OTA (after validation)
runtime observation  -> WebSerial + MQTT + serial fallback
```
'''
new_ota = '''## OTA

OTA uses the project's signed A/B UpdateManager path. Unsigned ArduinoOTA was removed so there is a single firmware trust path: signed manifest verification, firmware SHA-256 verification, inactive-slot write, `PENDING_VERIFY`, application validation and bootloader rollback. USB/CP2102 remains the recovery path.

Normal development progression:

```text
first/recovery flash -> USB
normal iteration     -> signed Web/remote OTA
runtime observation  -> WebSerial + MQTT + serial fallback
```
'''
if old_ota in architecture:
    architecture = architecture.replace(old_ota, new_ota, 1)
architecture += r'''

## Component registry integration (Stage 6B)

The first concrete component is `connectivity`. It does not own network transport implementation yet; it owns the connectivity state/health interpretation that the rest of the platform can consume consistently.

TaskScheduler samples the component every 2 s. The component itself decides its state and health:

```text
STARTING -> ONLINE      health=OK
         -> WIFI_ONLY   health=DEGRADED, mqtt_not_configured|mqtt_disconnected
         -> OFFLINE     health=DEGRADED, wifi_disconnected
```

Network loss is deliberately `DEGRADED`, not a platform-wide `FAULT`, because configured local control must continue without connectivity.

State/health transitions are posted to the bounded `EventBus`; the current handler only logs them. This creates the event boundary needed for the future Supervisor without letting asynchronous callbacks directly mutate unrelated FSMs.

`GET /api/components` now exposes the registry plus EventBus counters. The same registry JSON is embedded in `/api/status`, therefore it is also present in existing MQTT status/telemetry payloads. This is the first end-to-end use of the shared health model by API and messaging surfaces.
'''
Path("docs/architecture.md").write_text(architecture)

# Add a dedicated Stage 6 evidence log.
write("docs/runtime-test-log.md", r'''# Runtime / Stage 6 validation log

## 2026-09-05 — Stage 6A TaskScheduler foundation

- Added `arkhipenko/TaskScheduler` alongside `jonblack/arduino-fsm`.
- Enabled `_TASK_INLINE` for the multi-file PlatformIO firmware.
- Migrated the automatic firmware-check timer from hand-written `millis()` scheduling to TaskScheduler.
- Physical proof: an enabled 60 s policy re-armed after reboot, automatically discovered the signed target without a manual/MQTT check, and did not auto-apply it. Explicit apply completed `PENDING_VERIFY -> VALID`.
- Proven physical baseline after promotion: `0.1.16/build 17`, `app1`, `VALID`, `ONLINE`, Wi-Fi + MQTT/TLS connected.

## 2026-09-05 — Stage 6B component registry integration

Planned acceptance for this stage:

- build normal + signed candidate successfully;
- install signed `0.1.17/build 18` candidate through the existing signed Web OTA path;
- observe `PENDING_VERIFY -> VALID`;
- `/api/components` contains one registered `connectivity` component;
- online device reports connectivity state `ONLINE` and health `OK`;
- `/api/status` embeds the same registry and EventBus counters;
- EventBus dropped count remains zero during the proof;
- local `main == origin/main` after promotion.

The Aurora physical proof result is appended to this file when the stage completes.
''')

# Docs index gets the runtime proof log.
replace_once("docs/README.md",
'9. [`dependencies.md`](dependencies.md) — why each firmware dependency was chosen and replacement/licensing caveats.\n10. [`references.md`](references.md) — board page, datasheet/pinout source and relevant upstream libraries/projects.\n',
'9. [`runtime-test-log.md`](runtime-test-log.md) — physical validation evidence for the TaskScheduler + FSM modular runtime migration.\n10. [`dependencies.md`](dependencies.md) — why each firmware dependency was chosen and replacement/licensing caveats.\n11. [`references.md`](references.md) — board page, datasheet/pinout source and relevant upstream libraries/projects.\n')

# Add current Stage 6 milestone before TLS backlog.
replace_once("docs/README.md",
'- [x] nonblocking automatic update-check scheduler proven on hardware\n- [ ] replace development `setInsecure()` with CA certificate validation\n',
'- [x] nonblocking automatic update-check scheduler proven on hardware\n- [x] TaskScheduler + FSM cooperative runtime foundation adopted\n- [x] first real ComponentRegistry entry (`connectivity`) + `/api/components` shared health API implemented\n- [ ] Supervisor FSM over the common component health model\n- [ ] replace development `setInsecure()` with CA certificate validation\n')

# Bootstrap next steps reflect Stage 6B rather than starting Stage 6 from scratch.
replace_once("docs/BOOTSTRAP.md",
'''3. begin Stage 6 modular runtime (`ComponentRegistry`, common health model, EventBus and Supervisor);
4. add explicit component/update health metadata using the common model;
5. mount LittleFS and add minimal recovery UI;
6. implement local ConfigurationStore/RuleEngine/Scheduler without connectivity dependencies;
7. proceed to DS3231/TFT/touch/microSD only after physical pin mapping confirmation.
''',
'''3. continue Stage 6 modular runtime from the validated TaskScheduler + FSM foundation: add the Supervisor FSM over `ComponentRegistry`/`ComponentHealth`/`EventBus`;
4. migrate MQTT reconnect/telemetry and future component timing to TaskScheduler incrementally where it removes hand-written timing without changing behavior;
5. mount LittleFS and add minimal recovery UI;
6. implement local ConfigurationStore/RuleEngine/Scheduler without connectivity dependencies;
7. proceed to DS3231/TFT/touch/microSD only after physical pin mapping confirmation.
''')

print("STAGE6B_COMPONENT_REGISTRY_STAGED")
