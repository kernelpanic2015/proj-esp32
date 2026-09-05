#!/usr/bin/env bash
set -euo pipefail

ESP_HOST=${ESP_HOST:-proj-esp32.local}
KEYDIR=${KEYDIR:-"$HOME/.config/proj-esp32/keys"}
BASE=${BASE:-"$HOME/Downloads/proj-esp32-ota/stage6e-proof-fixed"}
LAB="$BASE/lab"
TARGET="$BASE/target"
OUT=${OUT:-/tmp/proj-esp32-stage6e-continue.txt}
: > "$OUT"

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

install_signed_web() {
  local dir=$1 sig code
  sig=$(base64 -w0 "$dir/manifest.sig")
  code=$(curl -sS --max-time 15 -o /tmp/stage6e-cont-prepare.json -w '%{http_code}' --data-urlencode manifest@"$dir/manifest.json" --data-urlencode signature="$sig" "http://$ESP_HOST/api/update/prepare")
  echo "PREPARE_HTTP=$code $(cat /tmp/stage6e-cont-prepare.json)" >> "$OUT"
  [[ "$code" == 200 ]]
  code=$(curl -sS --max-time 90 -o /tmp/stage6e-cont-upload.json -w '%{http_code}' -F firmware=@"$dir/firmware.bin" "http://$ESP_HOST/api/update/upload")
  echo "UPLOAD_HTTP=$code $(cat /tmp/stage6e-cont-upload.json)" >> "$OUT"
  [[ "$code" == 200 ]]
}

echo '=== CURRENT LAB BASELINE ===' >> "$OUT"
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
echo "STATUS=$S" >> "$OUT"
grep -q '"version":"0.1.23-remote-test"' <<<"$S"
grep -q '"build":24' <<<"$S"
grep -q '"running_partition":"app0"' <<<"$S"
grep -q '"image_state":"VALID"' <<<"$S"

echo '=== BUILD + SIGN FIXED IMAGES ===' >> "$OUT"
./scripts/pio run -e nodemcu-32s-remote-update-test >/tmp/stage6e-cont-lab-build.log 2>&1
./scripts/pio run -e nodemcu-32s-remote-target-test >/tmp/stage6e-cont-target-build.log 2>&1
rm -rf "$BASE"; mkdir -p "$LAB" "$TARGET"
python3 scripts/release_manifest.py --firmware .pio/build/nodemcu-32s-remote-update-test/firmware.bin --output "$LAB" --model proj-esp32-35 --hardware-revision 1 --version 0.1.24-remote-test --build 25 --channel dev --private-key "$KEYDIR/update-signing-private.pem" --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
python3 scripts/release_manifest.py --firmware .pio/build/nodemcu-32s-remote-target-test/firmware.bin --output "$TARGET" --model proj-esp32-35 --hardware-revision 1 --version 0.1.25 --build 26 --channel dev --private-key "$KEYDIR/update-signing-private.pem" --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" -signature "$LAB/manifest.sig" "$LAB/manifest.json" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" -signature "$TARGET/manifest.sig" "$TARGET/manifest.json" >/dev/null

echo '=== INSTALL FIXED LAB IMAGE ===' >> "$OUT"
install_signed_web "$LAB"
wait_for_transition '0.1.24-remote-test' 25 app1
sleep 2
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
W=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/wifi/runtime")
M=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/mqtt/runtime")
echo "FIXED_LAB_STATUS=$S" >> "$OUT"
echo "WIFI_INITIAL=$W" >> "$OUT"
echo "MQTT_INITIAL=$M" >> "$OUT"
STATUS_BYTES=$(printf '%s' "$S" | wc -c)
echo "STATUS_BYTES=$STATUS_BYTES" >> "$OUT"
(( STATUS_BYTES > 2048 ))

# Prove the enlarged buffer restored scheduled full-status telemetry before fault injection.
TELEMETRY_BASE=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["telemetry_publish_count"])' <<<"$M")
PRE_PUBLISH_OK=0
for _ in $(seq 1 20); do
  sleep 1
  M=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/mqtt/runtime" 2>/dev/null || true)
  N=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("telemetry_publish_count",0))' <<<"${M:-{}}" 2>/dev/null || echo 0)
  if (( N > TELEMETRY_BASE )); then PRE_PUBLISH_OK=1; break; fi
done
echo "MQTT_PRE_DISCONNECT=$M" >> "$OUT"
[[ $PRE_PUBLISH_OK -eq 1 ]]
grep -q '"last_telemetry_result":"published"' <<<"$M"

PRE_W=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/wifi/runtime")
PRE_A=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["reconnect_attempt_count"])' <<<"$PRE_W")
PRE_OK=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["reconnect_success_count"])' <<<"$PRE_W")
PRE_D=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["disconnect_observed_count"])' <<<"$PRE_W")
PRE_T=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["telemetry_publish_count"])' <<<"$M")

echo '=== CONTROLLED WI-FI DISCONNECT ===' >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/stage6e-cont-disconnect.json -w '%{http_code}' -X POST "http://$ESP_HOST/api/test/wifi/disconnect")
echo "DISCONNECT_HTTP=$CODE $(cat /tmp/stage6e-cont-disconnect.json)" >> "$OUT"
[[ "$CODE" == 202 ]]
OFFLINE=0
for _ in $(seq 1 12); do
  sleep 1
  if ! curl -fsS --max-time 1 "http://$ESP_HOST/api/status" >/dev/null 2>&1; then OFFLINE=1; break; fi
done
echo "HTTP_OFFLINE_SEEN=$OFFLINE" >> "$OUT"
[[ $OFFLINE -eq 1 ]]

RECOVERED=0
for _ in $(seq 1 45); do
  sleep 1
  S=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/status" 2>/dev/null || true)
  if grep -q '"version":"0.1.24-remote-test"' <<<"$S" && grep -q '"state":"ONLINE"' <<<"$S" && grep -q '"wifi":true' <<<"$S" && grep -q '"mqtt":true' <<<"$S"; then RECOVERED=1; break; fi
done
[[ $RECOVERED -eq 1 ]]
W=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/wifi/runtime")
SUP=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/supervisor")
C=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/components")
echo "RECOVERED_STATUS=$S" >> "$OUT"
echo "WIFI_RECOVERED=$W" >> "$OUT"
echo "SUPERVISOR_RECOVERED=$SUP" >> "$OUT"
echo "COMPONENTS_RECOVERED=$C" >> "$OUT"
A=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["reconnect_attempt_count"])' <<<"$W")
OK=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["reconnect_success_count"])' <<<"$W")
D=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["disconnect_observed_count"])' <<<"$W")
(( A > PRE_A && OK > PRE_OK && D > PRE_D ))
grep -q '"reconnect_task_enabled":false' <<<"$W"
grep -q '"last_reconnect_result":"connected"' <<<"$W"
grep -q '"state":"RUNNING"' <<<"$SUP"
grep -q '"health":"OK"' <<<"$SUP"
grep -q '"state":"ONLINE"' <<<"$C"
grep -q '"dropped":0' <<<"$C"

POST_PUBLISH_OK=0
for _ in $(seq 1 25); do
  sleep 1
  M=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/mqtt/runtime" 2>/dev/null || true)
  N=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("telemetry_publish_count",0))' <<<"${M:-{}}" 2>/dev/null || echo 0)
  if (( N > PRE_T )); then POST_PUBLISH_OK=1; break; fi
done
echo "MQTT_AFTER_RECOVERY=$M" >> "$OUT"
[[ $POST_PUBLISH_OK -eq 1 ]]
grep -q '"last_telemetry_result":"published"' <<<"$M"

echo '=== INSTALL CLEAN TARGET ===' >> "$OUT"
install_signed_web "$TARGET"
wait_for_transition '0.1.25' 26 app0
sleep 2
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
W=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/wifi/runtime")
M=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/mqtt/runtime")
SUP=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/supervisor")
C=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/components")
CODE=$(curl -sS --max-time 5 -o /tmp/stage6e-cont-final-endpoint.json -w '%{http_code}' -X POST "http://$ESP_HOST/api/test/wifi/disconnect")
echo "FINAL_STATUS=$S" >> "$OUT"
echo "FINAL_WIFI=$W" >> "$OUT"
echo "FINAL_MQTT=$M" >> "$OUT"
echo "FINAL_SUPERVISOR=$SUP" >> "$OUT"
echo "FINAL_COMPONENTS=$C" >> "$OUT"
echo "FINAL_TEST_ENDPOINT_HTTP=$CODE" >> "$OUT"
grep -q '"version":"0.1.25"' <<<"$S"
grep -q '"build":26' <<<"$S"
grep -q '"running_partition":"app0"' <<<"$S"
grep -q '"image_state":"VALID"' <<<"$S"
grep -q '"state":"ONLINE"' <<<"$S"
grep -q '"wifi":true' <<<"$S"
grep -q '"mqtt":true' <<<"$S"
grep -q '"coordinator_task_enabled":true' <<<"$W"
grep -q '"reconnect_task_enabled":false' <<<"$W"
grep -q '"telemetry_task_enabled":true' <<<"$M"
grep -q '"state":"RUNNING"' <<<"$SUP"
grep -q '"state":"ONLINE"' <<<"$C"
grep -q '"dropped":0' <<<"$C"
[[ "$CODE" == 404 ]]

echo STAGE6E_PHYSICAL_PROOF_OK >> "$OUT"
cat "$OUT"
