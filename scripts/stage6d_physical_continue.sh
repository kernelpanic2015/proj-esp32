#!/usr/bin/env bash
set -euo pipefail
ESP_HOST=${ESP_HOST:-proj-esp32.local}
TARGET=${TARGET:-"$HOME/Downloads/proj-esp32-ota/stage6d-proof/target"}
OUT=${OUT:-/tmp/proj-esp32-stage6d-continue.txt}
: > "$OUT"

wait_status() {
  local py=$1
  for _ in $(seq 1 30); do
    sleep 1
    S=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/status" 2>/dev/null || true)
    if python3 -c "$py" <<<"$S" 2>/dev/null; then
      echo "$S"
      return 0
    fi
  done
  return 1
}

wait_transition() {
  local version=$1 build=$2 partition=$3
  local pending=0 valid=0
  for _ in $(seq 1 90); do
    sleep 1
    U=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/status" 2>/dev/null || true)
    V=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/version" 2>/dev/null || true)
    if grep -q "\"version\":\"$version\"" <<<"$V" && grep -q "\"build\":$build" <<<"$V"; then
      if grep -q "\"running_partition\":\"$partition\"" <<<"$U" && grep -q '"image_state":"PENDING_VERIFY"' <<<"$U"; then pending=1; fi
      if grep -q "\"running_partition\":\"$partition\"" <<<"$U" && grep -q '"image_state":"VALID"' <<<"$U"; then valid=1; break; fi
    fi
  done
  echo "TRANSITION version=$version build=$build partition=$partition pending=$pending valid=$valid" >> "$OUT"
  [[ $pending -eq 1 && $valid -eq 1 ]]
}

signed_install() {
  local dir=$1 sig code
  sig=$(base64 -w0 "$dir/manifest.sig")
  code=$(curl -sS --max-time 15 -o /tmp/stage6d-cont-prepare.json -w '%{http_code}' --data-urlencode manifest@"$dir/manifest.json" --data-urlencode signature="$sig" "http://$ESP_HOST/api/update/prepare")
  echo "PREPARE_HTTP=$code $(cat /tmp/stage6d-cont-prepare.json)" >> "$OUT"
  [[ "$code" == 200 ]]
  code=$(curl -sS --max-time 90 -o /tmp/stage6d-cont-upload.json -w '%{http_code}' -F firmware=@"$dir/firmware.bin" "http://$ESP_HOST/api/update/upload")
  echo "UPLOAD_HTTP=$code $(cat /tmp/stage6d-cont-upload.json)" >> "$OUT"
  [[ "$code" == 200 ]]
}

echo '=== LAB RECOVERY BASELINE ===' >> "$OUT"
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
echo "STATUS=$S" >> "$OUT"
python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["firmware"]["version"]=="0.1.21-remote-test" and d["firmware"]["build"]==22; assert d["mqtt"] is True; assert d["supervisor"]["state"]=="RUNNING"; assert d["components"]["components"][0]["state"]=="ONLINE"' <<<"$S"
BEFORE_R=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["mqtt_runtime"]["reconnect_attempt_count"])' <<<"$S")
BEFORE_T=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["mqtt_runtime"]["telemetry_publish_count"])' <<<"$S")

echo '=== CONTROLLED DISCONNECT ===' >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/stage6d-cont-disconnect.json -w '%{http_code}' -X POST "http://$ESP_HOST/api/test/mqtt/disconnect")
echo "DISCONNECT_HTTP=$CODE $(cat /tmp/stage6d-cont-disconnect.json)" >> "$OUT"
[[ "$CODE" == 202 ]]
S=$(wait_status 'import json,sys; d=json.load(sys.stdin); assert d["mqtt"] is False; assert d["supervisor"]["state"]=="DEGRADED"; assert d["components"]["components"][0]["state"]=="WIFI_ONLY"; assert d["mqtt_runtime"]["telemetry_task_enabled"] is False')
echo "DEGRADED=$S" >> "$OUT"

S=$(wait_status "import json,sys; d=json.load(sys.stdin); assert d['mqtt'] is True; assert d['supervisor']['state']=='RUNNING'; assert d['components']['components'][0]['state']=='ONLINE'; assert d['mqtt_runtime']['reconnect_attempt_count']>$BEFORE_R; assert d['mqtt_runtime']['reconnect_success_count']>0; assert d['mqtt_runtime']['reconnect_task_enabled'] is False; assert d['mqtt_runtime']['telemetry_task_enabled'] is True")
echo "RECOVERED=$S" >> "$OUT"

S=$(wait_status "import json,sys; d=json.load(sys.stdin); assert d['mqtt_runtime']['telemetry_publish_count']>$BEFORE_T; assert d['mqtt_runtime']['last_telemetry_result']=='published'")
echo "TELEMETRY_REARMED=$S" >> "$OUT"

echo '=== CLEAN TARGET INSTALL ===' >> "$OUT"
test -s "$TARGET/firmware.bin"; test -s "$TARGET/manifest.json"; test -s "$TARGET/manifest.sig"
signed_install "$TARGET"
wait_transition 0.1.22 23 app1
S=$(wait_status 'import json,sys; d=json.load(sys.stdin); assert d["firmware"]["version"]=="0.1.22" and d["firmware"]["build"]==23; assert d["update"]["image_state"]=="VALID"; assert d["mqtt"] is True; assert d["supervisor"]["state"]=="RUNNING"; assert d["components"]["components"][0]["state"]=="ONLINE"; assert d["event_bus"]["dropped"]==0; assert d["mqtt_runtime"]["coordinator_task_enabled"] is True; assert d["mqtt_runtime"]["reconnect_task_enabled"] is False; assert d["mqtt_runtime"]["telemetry_task_enabled"] is True')
echo "FINAL_STATUS=$S" >> "$OUT"

# Prove periodic telemetry also fires on the clean image after its delayed first run.
S=$(wait_status 'import json,sys; d=json.load(sys.stdin); assert d["mqtt_runtime"]["telemetry_publish_count"]>=1; assert d["mqtt_runtime"]["last_telemetry_result"]=="published"')
echo "FINAL_TELEMETRY=$S" >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/stage6d-cont-final-test.json -w '%{http_code}' -X POST "http://$ESP_HOST/api/test/mqtt/disconnect")
echo "FINAL_TEST_ENDPOINT_HTTP=$CODE" >> "$OUT"
[[ "$CODE" == 404 ]]
echo STAGE6D_PHYSICAL_PROOF_OK >> "$OUT"
cat "$OUT"
