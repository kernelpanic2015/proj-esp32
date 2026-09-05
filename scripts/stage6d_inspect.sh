#!/usr/bin/env bash
set -euo pipefail
cd /home/kernelpanic/Projects/proj-esp32
printf '=== GIT ===\n'
git status --short --branch
git fetch origin main >/dev/null
printf 'LOCAL=%s\n' "$(git rev-parse HEAD)"
printf 'REMOTE=%s\n' "$(git rev-parse origin/main)"
printf '\n=== MQTT TIMING REFERENCES ===\n'
grep -nE 'lastMqttAttempt|lastHeartbeat|lastWifiRetry|connectMqtt\(|mqttClient\.loop|heartbeat|telemetry|millis\(' src/main.cpp || true
printf '\n=== MAIN LOOP / SETUP TAIL ===\n'
grep -nE '^void setup\(|^void loop\(' src/main.cpp || true
START=$(grep -n '^void setup\(' src/main.cpp | head -1 | cut -d: -f1 || true)
if [ -n "${START:-}" ]; then sed -n "${START},$ p" src/main.cpp | tail -n 260; fi
printf '\n=== DEVICE ===\n'
curl -fsS --max-time 5 http://proj-esp32.local/api/status; echo
printf 'STAGE6D_INSPECT_OK\n'
