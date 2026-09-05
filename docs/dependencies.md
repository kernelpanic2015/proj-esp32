# Dependency decisions

## arduino-fsm

Repository: `jonblack/arduino-fsm`

Why selected:

- compact finite-state machine abstraction
- `on_enter`, `on_state`, `on_exit`
- event transitions
- timed transitions
- matches the user's previous development style

Caveats:

- upstream is old and its PlatformIO metadata declares AVR only
- implementation itself uses generic Arduino APIs and is small enough to validate directly on ESP32
- transition arrays are grown with dynamic allocation during setup; define the topology once at boot and do not mutate it continuously
- upstream licensing metadata/header history should be revisited before commercial distribution

Project policy: keep the FSM dependency behind our application architecture so it can be replaced with a local implementation later without redesigning the firmware.

## ESP_DoubleResetDetector

Repository: `khoih-prog/ESP_DoubleResetDetector`

Version selected: 1.3.2

Why selected:

- explicitly supports ESP32
- detects two resets in a configurable window
- natural recovery trigger for Wi-Fi/MQTT provisioning
- works with EEPROM/SPIFFS/LittleFS-backed state

Caveat: upstream repository is archived. The project uses it as a replaceable recovery implementation, not as a permanent architectural dependency.

Initial storage: ESP32 EEPROM emulation.

Initial window: 10 seconds.

## WiFiManager

Repository: `tzapu/WiFiManager`

Purpose: provisioning without committing SSID/password to source control. The device can create a captive configuration AP when credentials are absent or recovery mode is requested.

Initial AP SSID: `proj-esp32-setup`.

## ESPAsyncWebServer + AsyncTCP

Organization: `ESP32Async`

Purpose:

- asynchronous local HTTP API
- WebSerial transport dependency
- future WebSocket/dashboard features

Initial routes:

- `/`
- `/api/status`
- `/webserial` (provided by WebSerial)

## WebSerial

Repository: `ayushsharma82/WebSerial`

Purpose: browser-accessible runtime console after Wi-Fi is connected.

Current open-source edition is AGPL-3.0. This is acceptable for the current laboratory. Before a proprietary/commercial firmware distribution, either review licensing requirements, obtain an appropriate commercial license, or replace it with our own WebSocket console.

## arduino-mqtt

Repository: `256dpi/arduino-mqtt`

PlatformIO package: `256dpi/MQTT`

Purpose: MQTT publish/subscribe for state, telemetry, events and commands.

Initial broker target: `kpnote.local:1883`.

The MQTT configuration is expected to become provisioned/persisted rather than hard-coded once the first end-to-end test is complete.

## Built-in ESP32/Arduino facilities

The base firmware also uses:

- `WiFi`
- `ESPmDNS`
- `ArduinoOTA`
- `WiFiClient`

No Wi-Fi credentials, API keys or other secrets should be committed to this repository.
