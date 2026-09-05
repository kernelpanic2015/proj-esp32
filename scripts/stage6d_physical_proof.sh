#!/usr/bin/env bash
set -euo pipefail

ESP_HOST=${ESP_HOST:-proj-esp32.local}
KEYDIR=${KEYDIR:-"$HOME/.config/proj-esp32/keys"}
BASE=${BASE:-"$HOME/Downloads/proj-esp32-ota/stage6d-proof"}
LAB="$BASE/lab"
TARGET="$BASE/target"
OUT=${OUT:-/tmp/proj-esp32-stage6d-proof.txt}
: > "$OUT"

jget() {
  python3 -c "import json,sys; d=json.load(sys.stdin); print(d$1)"
}

wait_for_transition() {
  local expected_version=$1 expected_build=$2 expected_partition=$3
  local seen_version=0 seen_pending=0 seen_valid=0
  for _ in $(seq 1 90); do
    sleep 1
    local v u
    v=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/version" 2>/dev/null || true)
    u=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/update/status" 2>/dev/null || true)
    if grep -q "\"version\":\"$expected_version\"" <<<"$v" && grep -q "\"build\":$expected_build" <<<"$v"; then seen_version=1; fi
    if [[ $seen_version -eq 1 ]] && grep -q "\"running_partition\":\"$expected_partition\"" <<<"$u" && grep -q '"image_state":"PENDING_VERIFY"' <<<"$u"; then seen_pending=1; fi
    if [[ $seen_version -eq 1 ]] && grep -q "\"running_partition\":\"$expected_partition\"" <<<"$u" && grep -q '"image_state":"VALID"' <<<"$u"; then seen_valid=1; break; fi
  done
  echo "TRANSITION version=$expected_version build=$expected_build partition=$expected_partition pending=$seen_pending valid=$seen_valid" >> "$OUT"
  [[ $seen_version -eq 1 && $seen_pending -eq 1 && $seen_valid -eq 1 ]]
}

wait_for_online() {
  local expected_version=$1 expected_build=$2
  for _ in $(seq 1 60); do
    sleep 1
    local s
    s=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/status" 2>/dev/null || true)
    if grep -q "\"version\":\"$expected_version\"" <<<"$s" && \
       grep -q "\"build\":$expected_build" <<<"$s" && \
       grep -q '"state":"ONLINE"' <<<"$s" && grep -q '"mqtt":true' <<<"$s"; then
      return 0
    fi
  done
  return 1
}

signed_web_install() {
  local dir=$1
  local sig code
  sig=$(base64 -w0 "$dir/manifest.sig")
  code=$(curl -sS --max-time 15 -o /tmp/stage6d-prepare.json -w '%{http_code}' \
    --data-urlencode manifest@"$dir/manifest.json" \
    --data-urlencode signature="$sig" \
    "http://$ESP_HOST/api/update/prepare")
  echo "PREPARE_HTTP=$code $(cat /tmp/stage6d-prepare.json)" >> "$OUT"
  [[ "$code" == 200 ]]
  code=$(curl -sS --max-time 90 -o /tmp/stage6d-upload.json -w '%{http_code}' \
    -F firmware=@"$dir/firmware.bin" "http://$ESP_HOST/api/update/upload")
  echo "UPLOAD_HTTP=$code $(cat /tmp/stage6d-upload.json)" >> "$OUT"
  [[ "$code" == 200 ]]
}

echo '=== BASELINE ===' >> "$OUT"
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
echo "STATUS=$S" >> "$OUT"
grep -q '"version":"0.1.20"' <<<"$S"
grep -q '"build":21' <<<"$S"
grep -q '"running_partition":"app1"' <<<"$S"
grep -q '"image_state":"VALID"' <<<"$S"
grep -q '"mqtt":true' <<<"$S"

echo '=== BUILD + SIGN STAGE6D IMAGES ===' >> "$OUT"
./scripts/pio run -e nodemcu-32s-remote-update-test >/tmp/stage6d-lab-build.log 2>&1
./scripts/pio run -e nodemcu-32s-remote-target-test >/tmp/stage6d-target-build.log 2>&1
rm -rf "$BASE"
mkdir -p "$LAB" "$TARGET"
python3 scripts/release_manifest.py --firmware .pio/build/nodemcu-32s-remote-update-test/firmware.bin --output "$LAB" --model proj-esp32-35 --hardware-revision 1 --version 0.1.21-remote-test --build 22 --channel dev --private-key "$KEYDIR/update-signing-private.pem" --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
python3 scripts/release_manifest.py --firmware .pio/build/nodemcu-32s-remote-target-test/firmware.bin --output "$TARGET" --model proj-esp32-35 --hardware-revision 1 --version 0.1.22 --build 23 --channel dev --private-key "$KEYDIR/update-signing-private.pem" --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" -signature "$LAB/manifest.sig" "$LAB/manifest.json" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" -signature "$TARGET/manifest.sig" "$TARGET/manifest.json" >/dev/null
echo "LAB_SHA=$(sha256sum "$LAB/firmware.bin" | awk '{print $1}')" >> "$OUT"
echo "TARGET_SHA=$(sha256sum "$TARGET/firmware.bin" | awk '{print $1}')" >> "$OUT"

echo '=== INSTALL LAB IMAGE ===' >> "$OUT"
signed_web_install "$LAB"
wait_for_transition '0.1.21-remote-test' 22 app0
wait_for_online '0.1.21-remote-test' 22

R=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/mqtt/runtime")
SUP=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/supervisor")
C=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/components")
echo "MQTT_RUNTIME_INITIAL=$R" >> "$OUT"
echo "SUPERVISOR_INITIAL=$SUP" >> "$OUT"
echo "COMPONENTS_INITIAL=$C" >> "$OUT"
grep -q '"coordinator_task_enabled":true' <<<"$R"
grep -q '"reconnect_task_enabled":false' <<<"$R"
grep -q '"telemetry_task_enabled":true' <<<"$R"
grep -q '"state":"RUNNING"' <<<"$SUP"
grep -q '"dropped":0' <<<"$C"

echo '=== WAIT FOR TASKSCHEDULER TELEMETRY ===' >> "$OUT"
TELEMETRY_READY=0
for _ in $(seq 1 20); do
  sleep 1
  R=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/mqtt/runtime" 2>/dev/null || true)
  if grep -Eq '"telemetry_publish_count":[1-9][0-9]*' <<<"$R" && grep -q '"last_telemetry_result":"published"' <<<"$R"; then
    TELEMETRY_READY=1
    break
  fi
done
[[ $TELEMETRY_READY -eq 1 ]]
echo "MQTT_RUNTIME_TELEMETRY=$R" >> "$OUT"
BEFORE_RECONNECT=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["reconnect_attempt_count"])' <<<"$R")
BEFORE_TELEMETRY=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["telemetry_publish_count"])' <<<"$R")

echo '=== REAL MQTT DISCONNECT; RECONNECT SUPPRESSED 8s ===' >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/stage6d-disconnect.json -w '%{http_code}' -X POST "http://$ESP_HOST/api/test/mqtt/disconnect")
echo "DISCONNECT_HTTP=$CODE $(cat /tmp/stage6d-disconnect.json)" >> "$OUT"
[[ "$CODE" == 202 ]]

DEGRADED=0
for _ in $(seq 1 6); do
  sleep 1
  S=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/status" 2>/dev/null || true)
  R=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/mqtt/runtime" 2>/dev/null || true)
  SUP=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/supervisor" 2>/dev/null || true)
  C=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/components" 2>/dev/null || true)
  if grep -q '"mqtt":false' <<<"$S" && grep -q '"telemetry_task_enabled":false' <<<"$R" && grep -q '"state":"DEGRADED"' <<<"$SUP" && grep -q '"state":"WIFI_ONLY"' <<<"$C"; then
    DEGRADED=1
    break
  fi
done
[[ $DEGRADED -eq 1 ]]
echo "STATUS_DEGRADED=$S" >> "$OUT"
echo "MQTT_RUNTIME_DEGRADED=$R" >> "$OUT"
echo "SUPERVISOR_DEGRADED=$SUP" >> "$OUT"
echo "COMPONENTS_DEGRADED=$C" >> "$OUT"
grep -q '"dropped":0' <<<"$C"

RECOVERED=0
for _ in $(seq 1 20); do
  sleep 1
  S=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/status" 2>/dev/null || true)
  R=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/mqtt/runtime" 2>/dev/null || true)
  SUP=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/supervisor" 2>/dev/null || true)
  C=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/components" 2>/dev/null || true)
  AFTER_RECONNECT=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("reconnect_attempt_count",0))' <<<"${R:-{}}" 2>/dev/null || echo 0)
  if grep -q '"mqtt":true' <<<"$S" && grep -q '"state":"RUNNING"' <<<"$SUP" && grep -q '"state":"ONLINE"' <<<"$C" && (( AFTER_RECONNECT > BEFORE_RECONNECT )); then
    RECOVERED=1
    break
  fi
done
[[ $RECOVERED -eq 1 ]]
echo "STATUS_RECOVERED=$S" >> "$OUT"
echo "MQTT_RUNTIME_RECOVERED=$R" >> "$OUT"
echo "SUPERVISOR_RECOVERED=$SUP" >> "$OUT"
echo "COMPONENTS_RECOVERED=$C" >> "$OUT"
grep -q '"last_reconnect_result":"connected"' <<<"$R"
grep -q '"reconnect_task_enabled":false' <<<"$R"
grep -q '"telemetry_task_enabled":true' <<<"$R"
grep -q '"dropped":0' <<<"$C"

echo '=== TELEMETRY RE-ARMS AFTER RECONNECT ===' >> "$OUT"
TELEMETRY_AFTER=0
for _ in $(seq 1 20); do
  sleep 1
  R=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/mqtt/runtime" 2>/dev/null || true)
  COUNT=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("telemetry_publish_count",0))' <<<"${R:-{}}" 2>/dev/null || echo 0)
  if (( COUNT > BEFORE_TELEMETRY )); then TELEMETRY_AFTER=1; break; fi
done
[[ $TELEMETRY_AFTER -eq 1 ]]
echo "MQTT_RUNTIME_TELEMETRY_AFTER_RECOVERY=$R" >> "$OUT"
grep -q '"last_telemetry_result":"published"' <<<"$R"

echo '=== INSTALL CLEAN TARGET ===' >> "$OUT"
signed_web_install "$TARGET"
wait_for_transition '0.1.22' 23 app1
wait_for_online '0.1.22' 23

# Allow the delayed telemetry task to fire once on the clean image.
FINAL_TELEMETRY=0
for _ in $(seq 1 20); do
  sleep 1
  R=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/mqtt/runtime" 2>/dev/null || true)
  if grep -Eq '"telemetry_publish_count":[1-9][0-9]*' <<<"$R"; then FINAL_TELEMETRY=1; break; fi
done
[[ $FINAL_TELEMETRY -eq 1 ]]

S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
SUP=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/supervisor")
C=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/components")
R=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/mqtt/runtime")
CODE=$(curl -sS --max-time 5 -o /tmp/stage6d-test-endpoint-final.json -w '%{http_code}' -X POST "http://$ESP_HOST/api/test/mqtt/disconnect")
echo "FINAL_STATUS=$S" >> "$OUT"
echo "FINAL_SUPERVISOR=$SUP" >> "$OUT"
echo "FINAL_COMPONENTS=$C" >> "$OUT"
echo "FINAL_MQTT_RUNTIME=$R" >> "$OUT"
echo "FINAL_TEST_ENDPOINT_HTTP=$CODE" >> "$OUT"
grep -q '"version":"0.1.22"' <<<"$S"
grep -q '"build":23' <<<"$S"
grep -q '"running_partition":"app1"' <<<"$S"
grep -q '"image_state":"VALID"' <<<"$S"
grep -q '"state":"ONLINE"' <<<"$S"
grep -q '"mqtt":true' <<<"$S"
grep -q '"state":"RUNNING"' <<<"$SUP"
grep -q '"health":"OK"' <<<"$SUP"
grep -q '"state":"ONLINE"' <<<"$C"
grep -q '"dropped":0' <<<"$C"
grep -q '"coordinator_task_enabled":true' <<<"$R"
grep -q '"reconnect_task_enabled":false' <<<"$R"
grep -q '"telemetry_task_enabled":true' <<<"$R"
[[ "$CODE" == 404 ]]

echo STAGE6D_PHYSICAL_PROOF_OK >> "$OUT"
cat "$OUT"
