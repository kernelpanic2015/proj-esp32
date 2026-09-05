# Operations

## Local working tree

```bash
cd /home/kernelpanic/Projects/proj-esp32
```

The project uses a dedicated PlatformIO virtual environment and wrapper:

```bash
./scripts/pio
```

## PlatformIO

Build:

```bash
./scripts/pio run
```

Upload over CP2102:

```bash
./scripts/pio run -t upload --upload-port /dev/ttyUSB0
```

Erase flash intentionally:

```bash
./scripts/pio run -t erase --upload-port /dev/ttyUSB0
```

List devices:

```bash
./scripts/pio device list
```

## Serial observation

Interactive human use can use PlatformIO's monitor:

```bash
./scripts/pio device monitor -p /dev/ttyUSB0 -b 115200
```

For Aurora jobs this is not the preferred path because the PlatformIO monitor expects an interactive terminal.

Use the repository helper for deterministic passive capture:

```bash
.venv-platformio/bin/python scripts/capture_serial.py --seconds 10
```

Important: on this CP2102 board, opening pyserial with default DTR/RTS states can reset the ESP32 and interfere with double-reset detection. The helper configures DTR/RTS before opening the port.

## Runtime checks

Status endpoint:

```bash
curl -fsS http://proj-esp32.local/api/status
```

Expected healthy baseline includes:

```json
{
  "state": "ONLINE",
  "wifi": true,
  "mqtt": true,
  "mqtt_configured": true,
  "mqtt_tls": true
}
```

Web console:

`http://proj-esp32.local/webserial`

MQTT configuration page:

`http://proj-esp32.local/config/mqtt`

Broker/Wi-Fi credentials must never be committed or printed into persistent automation logs unnecessarily.

## MQTT / CloudAMQP smoke test

The validated broker uses MQTT/TLS on port 8883. Keep credentials outside the repository.

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

Success criteria:

1. RabbitMQ dashboard shows the ESP32 MQTT connection;
2. WebSerial prints `MQTT RX .../cmd => ping`;
3. subscriber sees the `/cmd` message;
4. subscriber receives a status JSON response on `/events`;
5. telemetry continues at roughly 10-second intervals.

See `mqtt.md` for the complete validated integration record.

## Aurora jobs

Commands to the notebook are submitted through issues in `kernelpanic2015/aurora-kpnote`.

Issue body must be strict `aurora.job.v1` JSON; do not wrap it in Markdown fences.

Example:

```json
{
  "schema": "aurora.job.v1",
  "name": "build-proj-esp32",
  "cwd": "/home/kernelpanic/Projects/proj-esp32",
  "argv": [
    "/bin/bash",
    "-lc",
    "./scripts/pio run"
  ],
  "timeout_seconds": 600
}
```

Add label:

`aurora:queued`

The Aurora Client updates the issue and posts a local job UUID after execution. Aurora Watch is read-only.

For important diagnostics, make the job capture stdout/stderr into a file and post that file to the issue with GitHub CLI. Do not put broker passwords or other secrets into the issue body.

## Git workflow

Canonical remote:

`https://github.com/kernelpanic2015/proj-esp32.git`

Desired invariant:

```text
local main == origin/main
```

Before builds driven from changes made directly on GitHub:

```bash
git pull --ff-only origin main
```

After validated local modifications:

```bash
git add ...
git commit -m '...'
git push origin main
```

Do not commit `.pio/`, `.venv-platformio/`, Wi-Fi credentials, MQTT credentials or local secret/config files.

Useful synchronization check:

```bash
git fetch origin main
git status --short --branch
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
```

## Safe iteration order

For changes that can affect boot/networking/messaging:

1. synchronize source;
2. compile;
3. inspect warnings/errors and flash/RAM footprint;
4. upload;
5. capture serial boot;
6. validate `/api/status` and WebSerial;
7. validate broker connection and MQTT round-trip if messaging changed;
8. commit/push local corrections;
9. verify `local main == origin/main`.

USB remains the recovery path even after OTA is enabled.
