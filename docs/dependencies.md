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

Project policy: keep the FSM dependency behind our application architecture so it can be replaced later without redesigning the firmware.

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

Version resolved: 2.0.17

Purpose: provisioning without committing SSID/password to source control. The device creates a captive configuration AP when credentials are absent or recovery mode is requested.

Recovery AP SSID: `proj-esp32-setup`.

The project uses nonblocking portal mode so the FSM and recovery logic continue running while the portal is active.

## PubSubClient

Repository: `knolleary/pubsubclient`

PlatformIO package: `knolleary/PubSubClient@^2.8`

Resolved version: 2.8.0

Purpose: MQTT publish/subscribe for device state, telemetry, events and commands.

Current validated transport combinations:

- `WiFiClient` for plain MQTT when explicitly configured
- `WiFiClientSecure` for MQTT/TLS

Current production direction uses MQTT/TLS to CloudAMQP/RabbitMQ on port 8883.

The MQTT broker host, port, username, password and TLS flag are persisted in ESP32 NVS through `/config/mqtt`; credentials are not committed.

### Why PubSubClient replaced arduino-mqtt

The first implementation used `256dpi/arduino-mqtt` 2.5.3. With the CloudAMQP RabbitMQ endpoint, TLS established successfully but the MQTT layer repeatedly failed with `err=-9 rc=6`, including after manually preconnecting the secure socket and using `skip=true`.

PubSubClient gave a deterministic broker return state. Its initial `state=4` exposed a stale/incorrect password in ESP32 NVS; after the correct password was re-saved, the ESP32 connected successfully and the complete MQTT/TLS round-trip was validated.

Project policy: PubSubClient is the validated MQTT client baseline unless a future requirement justifies another implementation.

## ESPAsyncWebServer + AsyncTCP

Organization: `ESP32Async`

Resolved versions:

- AsyncTCP 3.5.0
- ESPAsyncWebServer 3.12.0

Purpose:

- asynchronous local HTTP API
- WebSerial transport dependency
- future WebSocket/dashboard features

Current routes include:

- `/`
- `/api/status`
- `/config/mqtt`
- `/webserial` (provided by WebSerial)

## WebSerial

Repository: `ayushsharma82/WebSerial`

Resolved version: 2.1.2

Purpose: browser-accessible runtime console after Wi-Fi is connected.

Current open-source edition is AGPL-3.0. This is acceptable for the current laboratory. Before proprietary/commercial firmware distribution, review licensing requirements, obtain an appropriate commercial license, or replace it with our own WebSocket console.

## Built-in ESP32/Arduino facilities

The base firmware also uses:

- `WiFi`
- `WiFiClient`
- `WiFiClientSecure`
- `Preferences`
- `ESPmDNS`
- `ArduinoOTA`

## TLS status

Current development firmware calls `WiFiClientSecure::setInsecure()`. Traffic is encrypted, but the server certificate is not authenticated. This is acceptable only as a development baseline.

Before production use:

- install/validate the appropriate CA trust chain instead of `setInsecure()`;
- ensure device time is valid if certificate validation requires it;
- avoid pinning short-lived leaf certificates.

## Secret-handling rule

No Wi-Fi credentials, MQTT passwords, API keys, private keys or credential-bearing URLs should be committed to this repository.
