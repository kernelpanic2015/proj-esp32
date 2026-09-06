#!/usr/bin/env bash
set -euo pipefail

OUT="${OUT:-/tmp/proj-esp32-stage7c-proof.txt}"
: > "$OUT"
BASE_URL="http://proj-esp32.local"
PRIV="$HOME/.config/proj-esp32/keys/update-signing-private.pem"
PUB="keys/update-signing-public.pem"
ROOT="$HOME/Downloads/proj-esp32-ota/stage7c-proof"
LAB="$ROOT/lab"
TARGET="$ROOT/target"
mkdir -p "$LAB" "$TARGET"

get_status() { curl -fsS --max-time 5 "$BASE_URL/api/status"; }
get_rule_runtime() { curl -fsS --max-time 5 "$BASE_URL/api/rules/runtime"; }
get_lab_runtime() { curl -fsS --max-time 5 "$BASE_URL/api/test/rules/runtime"; }

install_package() {
  local dir="$1" sig code
  sig=$(base64 -w0 "$dir/manifest.sig")
  code=$(curl -sS --max-time 15 -o /tmp/stage7c-prep.json -w '%{http_code}' \
    --data-urlencode manifest@"$dir/manifest.json" \
    --data-urlencode signature="$sig" \
    "$BASE_URL/api/update/prepare")
  echo "PREPARE_HTTP=$code $(cat /tmp/stage7c-prep.json)" >> "$OUT"
  test "$code" = 200
  code=$(curl -sS --max-time 90 -o /tmp/stage7c-upload.json -w '%{http_code}' \
    -F firmware=@"$dir/firmware.bin" "$BASE_URL/api/update/upload")
  echo "UPLOAD_HTTP=$code $(cat /tmp/stage7c-upload.json)" >> "$OUT"
  test "$code" = 200
}

wait_transition() {
  local version="$1" build="$2" partition="$3"
  local pending=0 valid=0 s=""
  for _ in $(seq 1 90); do
    sleep 1
    s=$(curl -fsS --max-time 1 "$BASE_URL/api/status" 2>/dev/null || true)
    if echo "$s" | grep -Fq "\"version\":\"$version\"" && \
       echo "$s" | grep -Fq "\"build\":$build"; then
      if echo "$s" | grep -Fq '"image_state":"PENDING_VERIFY"'; then pending=1; fi
      if echo "$s" | grep -Fq '"image_state":"VALID"'; then valid=1; break; fi
    fi
  done
  echo "TRANSITION version=$version build=$build partition=$partition pending=$pending valid=$valid" >> "$OUT"
  test "$pending" -eq 1
  test "$valid" -eq 1
  echo "$s" | grep -Fq "\"running_partition\":\"$partition\""
}

wait_http() {
  local s=""
  for _ in $(seq 1 40); do
    s=$(curl -fsS --max-time 1 "$BASE_URL/api/status" 2>/dev/null || true)
    if [ -n "$s" ]; then printf '%s' "$s"; return 0; fi
    sleep 1
  done
  return 1
}

post_form() {
  local path="$1" outfile="$2"; shift 2
  curl -sS --max-time 10 -o "$outfile" -w '%{http_code}' -X POST "$@" "$BASE_URL$path"
}

wait_completed() {
  local expected="$1" expected_on="$2" expected_result="$3" out="$4"
  local s=""
  for _ in $(seq 1 30); do
    s=$(get_lab_runtime 2>/dev/null || true)
    if echo "$s" | grep -Fq "\"completed_count\":$expected" && \
       echo "$s" | grep -Fq "\"on\":$expected_on" && \
       echo "$s" | grep -Fq "\"last_run_result\":\"$expected_result\""; then
      break
    fi
    sleep 0.1
  done
  printf '%s' "$s" > "$out"
  echo "RUNTIME_EXPECT completed=$expected on=$expected_on result=$expected_result $s" >> "$OUT"
  grep -Fq "\"completed_count\":$expected" "$out"
  grep -Fq "\"on\":$expected_on" "$out"
  grep -Fq "\"last_run_result\":\"$expected_result\"" "$out"
  grep -Fq '"state":"ARMED"' "$out"
  grep -Fq '"work_task_enabled":false' "$out"
}

echo '=== PRECHECK CLEAN 7B ===' >> "$OUT"
S=$(get_status)
echo "PRE_STATUS=$S" >> "$OUT"
echo "$S" | grep -Fq '"version":"0.1.31"'
echo "$S" | grep -Fq '"build":32'
echo "$S" | grep -Fq '"running_partition":"app0"'
echo "$S" | grep -Fq '"image_state":"VALID"'
echo "$S" | grep -Fq '"wifi":true'
echo "$S" | grep -Fq '"mqtt":true'

echo '=== SIGN STAGE7C IMAGES ===' >> "$OUT"
rm -rf "$LAB" "$TARGET"
mkdir -p "$LAB" "$TARGET"
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-update-test/firmware.bin \
  --output "$LAB" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.32-remote-test --build 33 --channel dev \
  --private-key "$PRIV" --public-key "$PUB" >/tmp/stage7c-lab-manifest.log
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-target-test/firmware.bin \
  --output "$TARGET" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.33 --build 34 --channel dev \
  --private-key "$PRIV" --public-key "$PUB" >/tmp/stage7c-target-manifest.log

echo '=== INSTALL LAB 7C ===' >> "$OUT"
install_package "$LAB"
wait_transition '0.1.32-remote-test' 33 app1
S=$(get_status)
R=$(get_rule_runtime)
T=$(get_lab_runtime)
echo "LAB_STATUS=$S" >> "$OUT"
echo "LAB_RULE_RUNTIME=$R" >> "$OUT"
echo "LAB_TEST_RUNTIME=$T" >> "$OUT"
echo "$S" | grep -Fq '"http_allowed":true'
echo "$R" | grep -Fq '"state":"DISABLED"'
echo "$R" | grep -Fq '"active_rule":false'
echo "$R" | grep -Fq '"work_task_enabled":false'
echo "$R" | grep -Fq '"scheduled_count":0'

echo '=== CONFIGURE ACTIVE 16/18 ===' >> "$OUT"
CODE=$(post_form '/api/test/rules/configure' /tmp/stage7c-config.json \
  --data-urlencode on_below=16 --data-urlencode off_above=18 --data-urlencode enabled=1)
echo "CONFIG_HTTP=$CODE $(cat /tmp/stage7c-config.json)" >> "$OUT"
test "$CODE" = 200
R=$(get_rule_runtime)
echo "ARMED_RUNTIME=$R" >> "$OUT"
echo "$R" | grep -Fq '"state":"ARMED"'
echo "$R" | grep -Fq '"active_rule":true'
echo "$R" | grep -Fq '"work_task_enabled":false'
echo "$R" | grep -Fq '"completed_count":0'

echo '=== OFFLINE LOCAL EVENT PROOF ===' >> "$OUT"
CODE=$(post_form '/api/test/rules/input/delayed' /tmp/stage7c-delayed.json \
  --data-urlencode value=15 --data-urlencode delay_ms=3000)
echo "DELAYED_INPUT_HTTP=$CODE $(cat /tmp/stage7c-delayed.json)" >> "$OUT"
test "$CODE" = 202
CODE=$(curl -sS --max-time 5 -o /tmp/stage7c-wifi-disc.json -w '%{http_code}' -X POST \
  "$BASE_URL/api/test/wifi/disconnect")
echo "WIFI_DISCONNECT_HTTP=$CODE $(cat /tmp/stage7c-wifi-disc.json)" >> "$OUT"
test "$CODE" = 202
sleep 2
if curl -fsS --max-time 1 "$BASE_URL/api/status" >/dev/null 2>&1; then
  echo 'WARNING_HTTP_STILL_REACHABLE_AT_2S' >> "$OUT"
else
  echo 'HTTP_UNAVAILABLE_DURING_WIFI_LOSS=1' >> "$OUT"
fi
S=$(wait_http)
echo "RECOVERED_STATUS=$S" >> "$OUT"
echo "$S" | grep -Fq '"wifi":true'
echo "$S" | grep -Fq '"mqtt":true'
echo "$S" | grep -Eq '"disconnect_observed_count":[1-9][0-9]*'
echo "$S" | grep -Eq '"reconnect_success_count":[1-9][0-9]*'
T=$(get_lab_runtime)
echo "POST_OFFLINE_RULE=$T" >> "$OUT"
echo "$T" | grep -Fq '"value":15.000'
echo "$T" | grep -Fq '"on":true'
echo "$T" | grep -Fq '"state":"ARMED"'
echo "$T" | grep -Fq '"work_task_enabled":false'
echo "$T" | grep -Fq '"scheduled_count":1'
echo "$T" | grep -Fq '"completed_count":1'
echo "$T" | grep -Fq '"last_run_result":"TURN_ON"'

echo '=== ONLINE EVENT/HYSTERESIS REGRESSION ===' >> "$OUT"
CODE=$(post_form '/api/test/rules/input' /tmp/stage7c-in17.json --data-urlencode value=17)
test "$CODE" = 200
wait_completed 2 true HOLD /tmp/stage7c-e17.json
CODE=$(post_form '/api/test/rules/input' /tmp/stage7c-in19.json --data-urlencode value=19)
test "$CODE" = 200
wait_completed 3 false TURN_OFF /tmp/stage7c-e19.json

echo '=== DISABLE RULE / TASK MUST STAY OFF ===' >> "$OUT"
CODE=$(post_form '/api/test/rules/configure' /tmp/stage7c-disable.json \
  --data-urlencode on_below=16 --data-urlencode off_above=18 --data-urlencode enabled=0)
echo "DISABLE_HTTP=$CODE $(cat /tmp/stage7c-disable.json)" >> "$OUT"
test "$CODE" = 200
R=$(get_rule_runtime)
echo "DISABLED_RUNTIME=$R" >> "$OUT"
echo "$R" | grep -Fq '"state":"DISABLED"'
echo "$R" | grep -Fq '"active_rule":false'
echo "$R" | grep -Fq '"work_task_enabled":false'
CODE=$(post_form '/api/test/rules/input' /tmp/stage7c-in10.json --data-urlencode value=10)
test "$CODE" = 200
sleep 0.4
R=$(get_rule_runtime)
echo "DISABLED_AFTER_INPUT=$R" >> "$OUT"
echo "$R" | grep -Fq '"state":"DISABLED"'
echo "$R" | grep -Fq '"work_task_enabled":false'
echo "$R" | grep -Fq '"scheduled_count":3'
echo "$R" | grep -Fq '"completed_count":3'
echo "$R" | grep -Eq '"rejected_count":[1-9][0-9]*'

SUP=$(curl -fsS --max-time 5 "$BASE_URL/api/supervisor")
COMPS=$(curl -fsS --max-time 5 "$BASE_URL/api/components")
echo "LAB_SUPERVISOR=$SUP" >> "$OUT"
echo "LAB_COMPONENTS=$COMPS" >> "$OUT"
echo "$SUP" | grep -Fq '"state":"RUNNING"'
echo "$COMPS" | grep -Fq '"dropped":0'

echo '=== INSTALL CLEAN TARGET 7C ===' >> "$OUT"
install_package "$TARGET"
wait_transition '0.1.33' 34 app0
S=$(get_status)
R=$(get_rule_runtime)
E=$(curl -fsS --max-time 5 "$BASE_URL/api/rules/status")
C=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration/status")
SUP=$(curl -fsS --max-time 5 "$BASE_URL/api/supervisor")
COMPS=$(curl -fsS --max-time 5 "$BASE_URL/api/components")
CODE=$(curl -sS --max-time 5 -o /tmp/stage7c-clean-lab.json -w '%{http_code}' "$BASE_URL/api/test/rules/runtime")
echo "FINAL_STATUS=$S" >> "$OUT"
echo "FINAL_RUNTIME=$R" >> "$OUT"
echo "FINAL_ENGINE=$E" >> "$OUT"
echo "FINAL_CONFIG=$C" >> "$OUT"
echo "FINAL_SUPERVISOR=$SUP" >> "$OUT"
echo "FINAL_COMPONENTS=$COMPS" >> "$OUT"
echo "FINAL_LAB_ENDPOINT_HTTP=$CODE" >> "$OUT"
echo "$S" | grep -Fq '"version":"0.1.33"'
echo "$S" | grep -Fq '"build":34'
echo "$S" | grep -Fq '"running_partition":"app0"'
echo "$S" | grep -Fq '"image_state":"VALID"'
echo "$S" | grep -Fq '"wifi":true'
echo "$S" | grep -Fq '"mqtt":true'
echo "$S" | grep -Fq '"http_allowed":false'
echo "$R" | grep -Fq '"state":"DISABLED"'
echo "$R" | grep -Fq '"active_rule":false'
echo "$R" | grep -Fq '"work_task_enabled":false'
echo "$E" | grep -Fq '"configured":false'
echo "$E" | grep -Fq '"mode":"hysteresis_v1"'
echo "$C" | grep -Fq '"revision":3'
echo "$SUP" | grep -Fq '"state":"RUNNING"'
echo "$COMPS" | grep -Fq '"count":1'
echo "$COMPS" | grep -Fq '"dropped":0'
test "$CODE" = 404

echo STAGE7C_PHYSICAL_PROOF_OK >> "$OUT"
cat "$OUT"
