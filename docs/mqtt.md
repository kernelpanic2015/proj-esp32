# MQTT / RabbitMQ integration

## Status

Validated end-to-end on 2026-09-05.

The ESP32 maintains an authenticated MQTT/TLS connection to a CloudAMQP RabbitMQ instance and successfully exchanges commands, events and telemetry through the broker.

## Broker

- service: CloudAMQP / RabbitMQ
- hostname: `jackal.rmq.cloudamqp.com`
- plain MQTT port: `1883`
- MQTT/TLS port: `8883`
- firmware mode used for validation: TLS enabled

Do not commit the MQTT password or other credentials. The ESP32 stores MQTT configuration in NVS through the local `/config/mqtt` page.

## Firmware client

Current validated library:

- `knolleary/PubSubClient` 2.8.x

TLS transport:

- `WiFiClientSecure`

Current development configuration uses `setInsecure()`, so traffic is encrypted but the broker certificate is not authenticated. Replace this with CA validation before production use.

## Topics

Root:

```text
lab/proj-esp32
```

Per-device topics:

```text
lab/proj-esp32/<device-id>/state
lab/proj-esp32/<device-id>/telemetry
lab/proj-esp32/<device-id>/events
lab/proj-esp32/<device-id>/cmd
```

Current validated device ID:

```text
10A2CCEF49C0
```

Therefore the current command topic is:

```text
lab/proj-esp32/10A2CCEF49C0/cmd
```

## Validated behavior

The firmware:

- connects with MQTT/TLS on port 8883;
- authenticates successfully against RabbitMQ;
- subscribes to `<root>/<device-id>/cmd`;
- publishes retained `{"online":true}` on `<root>/<device-id>/state` after connection;
- publishes status telemetry about every 10 seconds;
- publishes command responses/events on `<root>/<device-id>/events`.

Validated command flow:

```text
notebook publishes "ping"
        |
        v
RabbitMQ / CloudAMQP
        |
        v
ESP32 receives on /cmd
        |
        v
ESP32 publishes status JSON on /events
        |
        v
RabbitMQ / CloudAMQP
        |
        v
notebook subscriber receives response
```

WebSerial confirmed reception with:

```text
MQTT RX lab/proj-esp32/10A2CCEF49C0/cmd => ping
```

The notebook subscriber received both periodic telemetry and the `/events` response.


## Firmware update trigger commands

Validated through the real CloudAMQP broker on 2026-09-05:

```text
firmware.status
firmware.check <https://.../manifest.json>
firmware.update
```

`firmware.check` asks the shared remote update service to fetch and verify the signed manifest. `firmware.update` is accepted only after a candidate is in `AVAILABLE` state. MQTT never transports the binary; the ESP32 downloads `firmware.bin` directly and runs the same signed SHA-256/A-B/rollback path used by Web OTA.

A plain `firmware.check` without a URL is currently rejected with `manifest_url_required`. The next milestone persists the update source/policy in NVS, after which the bare command can use the configured source.

## Reproducible notebook smoke test

Use the CloudAMQP MQTT username/password from the instance credentials. Do not paste the password into repository files.

Subscriber:

```bash
mosquitto_sub \
  -h jackal.rmq.cloudamqp.com \
  -p 8883 \
  --tls-version tlsv1.2 \
  -u '<mqtt-username>' \
  -P '<mqtt-password>' \
  -t 'lab/proj-esp32/#' \
  -v
```

Publish `ping`:

```bash
mosquitto_pub \
  -h jackal.rmq.cloudamqp.com \
  -p 8883 \
  --tls-version tlsv1.2 \
  -u '<mqtt-username>' \
  -P '<mqtt-password>' \
  -t 'lab/proj-esp32/10A2CCEF49C0/cmd' \
  -m 'ping'
```

Expected subscriber output includes:

```text
lab/proj-esp32/10A2CCEF49C0/cmd ping
lab/proj-esp32/10A2CCEF49C0/events { ... "mqtt":true ... }
```

Periodic telemetry should also appear roughly every 10 seconds.

## RabbitMQ management validation

The MQTT connection was visible in the CloudAMQP/RabbitMQ dashboard after the ESP32 authenticated successfully.

The RabbitMQ Management HTTP API is also available on the instance. A successful authenticated `whoami` request confirmed the management user independently from MQTT transport.

## Migration history

The initial firmware used `256dpi/arduino-mqtt` / lwmqtt.

Observed failure:

```text
TLS connection established
MQTT connection failed err=-9 rc=6
```

The TLS socket itself was healthy, including when it was manually preconnected before the MQTT handshake. The MQTT client was then replaced with PubSubClient.

PubSubClient initially returned:

```text
MQTT/PubSubClient connection failed state=4
```

This correctly exposed an authentication problem caused by the password stored in ESP32 NVS. Re-saving the correct password through `/config/mqtt` immediately produced a valid broker session and the end-to-end round-trip passed.

## OTA trigger commands — validated

The command topic now supports `firmware.status`, `firmware.check`, `firmware.check <manifest-url>`, and `firmware.update`. A bare `firmware.check` reads the persisted NVS update policy and uses its saved HTTPS manifest URL. This was physically proven across an explicit reboot and a complete OTA to `0.1.12/build 13`; the broker remains only the trigger plane.

## Next hardening work

- add Last Will and Testament with retained offline state;
- add exponential reconnect backoff with jitter;
- replace `setInsecure()` with CA validation;
- define topic/credential permissions so each device can publish only its own state/events/telemetry and consume only its own command topic;
- decide QoS policy per message class;
- extract MQTT logic into a dedicated nonblocking `MQTTService` while preserving the validated PubSubClient behavior.
