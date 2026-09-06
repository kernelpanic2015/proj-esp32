#!/usr/bin/env bash
set -euo pipefail

OUT="${OUT:-/tmp/proj-esp32-stage7d-proof.txt}"
: > "$OUT"
BASE_URL="http://proj-esp32.local"
KEYDIR="$HOME/.config/proj-esp32/keys"
PRIV="$KEYDIR/update-signing-private.pem"
PUB="keys/update-signing-public.pem"
ROOT="$HOME/Downloads/proj-esp32-ota/stage7d-proof"
LAB="$ROOT/lab"
TARGET="$ROOT/target"
mkdir -p "$LAB" "$TARGET"

status_get() { curl -fsS --max-time 5 "$BASE_URL/api/status"; }
config_get() { curl -fsS --max-time 5 "$BASE_URL/api/configuration"; }
config_status_get() { curl -fsS --max-time 5 "$BASE_URL/api/configuration/status"; }
rule_get() { curl -fsS --max-time 5 "$BASE_URL/api/rules/status"; }
runtime_get() { curl -fsS --max-time 5 "$BASE_URL/api/rules/runtime"; }
persisted_get() { curl -fsS --max-time 5 "$BASE_URL/api/rules/persisted"; }
test_rules_get() { curl -fsS --max-time 5 "$BASE_URL/api/test/rules/runtime"; }

install_package() {
  local dir="$1" sig code
  sig=$(base64 -w0 "$dir/manifest.sig")
  code=$(curl -sS --max-time 15 -o /tmp/stage7d-prep.json -w '%{http_code}' \
    --data-urlencode manifest@"$dir/manifest.json" \
    --data-urlencode signature="$sig" \
    "$BASE_URL/api/update/prepare")
  echo "PREPARE_HTTP=$code $(cat /tmp/stage7d-prep.json)" >> "$OUT"
  test "$code" = 200
  code=$(curl -sS --max-time 90 -o /tmp/stage7d-upload.json -w '%{http_code}' \
    -F firmware=@"$dir/firmware.bin" "$BASE_URL/api/update/upload")
  echo "UPLOAD_HTTP=$code $(cat /tmp/stage7d-upload.json)" >> "$OUT"
  test "$code" = 200
}

wait_transition() {
  local version="$1" build="$2" partition="$3"
  local pending=0 valid=0 s=""
  for _ in $(seq 1 160); do
    sleep 0.5
    s=$(curl -fsS --max-time 1 "$BASE_URL/api/status" 2>/dev/null || true)
    if echo "$s" | grep -Fq "\"version\":\"$version\"" && \
       echo "$s" | grep -Fq "\"build\":$build"; then
      echo "$s" | grep -Fq '"image_state":"PENDING_VERIFY"' && pending=1 || true
      if echo "$s" | grep -Fq '"image_state":"VALID"'; then valid=1; break; fi
    fi
  done
  echo "TRANSITION version=$version build=$build partition=$partition pending=$pending valid=$valid" >> "$OUT"
  test "$valid" -eq 1
  echo "$s" | grep -Fq "\"running_partition\":\"$partition\""
  # Pending is expected on this A/B path. Keep it explicit in evidence, but do not
  # turn an observation race into a false negative if VALID was reached before polling.
}

wait_online() {
  local version="$1" build="$2" s=""
  for _ in $(seq 1 120); do
    sleep 0.5
    s=$(curl -fsS --max-time 1 "$BASE_URL/api/status" 2>/dev/null || true)
    if echo "$s" | grep -Fq "\"version\":\"$version\"" && \
       echo "$s" | grep -Fq "\"build\":$build" && \
       echo "$s" | grep -Fq '"wifi":true'; then
      echo "$s"
      return 0
    fi
  done
  return 1
}

reboot_lab() {
  local version="$1" build="$2" code seen_down=0 s=""
  code=$(curl -sS --max-time 8 -o /tmp/stage7d-reboot.json -w '%{http_code}' \
    -X POST --data-urlencode command=reboot "$BASE_URL/api/test/mqtt/command")
  echo "REBOOT_REQUEST_HTTP=$code $(cat /tmp/stage7d-reboot.json)" >> "$OUT"
  test "$code" = 202
  for _ in $(seq 1 60); do
    sleep 0.25
    if ! curl -fsS --max-time 0.5 "$BASE_URL/api/status" >/dev/null 2>&1; then
      seen_down=1
      break
    fi
  done
  echo "REBOOT_OFFLINE_SEEN=$seen_down" >> "$OUT"
  test "$seen_down" -eq 1
  s=$(wait_online "$version" "$build")
  echo "POST_REBOOT_STATUS=$s" >> "$OUT"
}

apply_config() {
  local file="$1" expected_http="$2" out="$3" code
  code=$(curl -sS --max-time 12 -o "$out" -w '%{http_code}' -X POST \
    --data-urlencode config@"$file" "$BASE_URL/api/configuration/apply")
  echo "APPLY file=$(basename "$file") HTTP=$code $(cat "$out")" >> "$OUT"
  test "$code" = "$expected_http"
}

post_input() {
  local value="$1" code
  code=$(curl -sS --max-time 8 -o /tmp/stage7d-input.json -w '%{http_code}' -X POST \
    --data-urlencode "value=$value" "$BASE_URL/api/test/rules/input")
  echo "INPUT value=$value HTTP=$code $(cat /tmp/stage7d-input.json)" >> "$OUT"
  test "$code" = 200
}

wait_decision() {
  local decision="$1" on="$2" min_completed="$3" j=""
  for _ in $(seq 1 40); do
    sleep 0.25
    j=$(test_rules_get 2>/dev/null || true)
    if echo "$j" | grep -Fq "\"last_decision\":\"$decision\"" && \
       echo "$j" | grep -Fq "\"on\":$on"; then
      local completed
      completed=$(printf '%s' "$j" | sed -n 's/.*"completed_count":\([0-9][0-9]*\).*/\1/p' | head -n1)
      if [ -n "$completed" ] && [ "$completed" -ge "$min_completed" ]; then
        echo "RULE_RESULT decision=$decision on=$on completed=$completed json=$j" >> "$OUT"
        return 0
      fi
    fi
  done
  echo "RULE_RESULT_TIMEOUT decision=$decision on=$on json=$j" >> "$OUT"
  return 1
}

cat > /tmp/stage7d-invalid.json <<'JSON'
{"schema":1,"rules":[{"id":"persisted.invalid","type":"hysteresis","enabled":true,"input":"virtual.temperature","output":"virtual.heater","on_below":18,"off_above":16}],"schedules":[]}
JSON
cat > /tmp/stage7d-a.json <<'JSON'
{"schema":1,"rules":[{"id":"persisted.demo.a","type":"hysteresis","enabled":true,"input":"virtual.temperature","output":"virtual.heater","on_below":16,"off_above":18}],"schedules":[]}
JSON
cat > /tmp/stage7d-b.json <<'JSON'
{"schema":1,"rules":[{"id":"persisted.demo.b","type":"hysteresis","enabled":true,"input":"virtual.temperature","output":"virtual.heater","on_below":14,"off_above":20}],"schedules":[]}
JSON

echo '=== PRECHECK ===' >> "$OUT"
S=$(status_get)
echo "STATUS=$S" >> "$OUT"
echo "$S" | grep -Fq '"version":"0.1.35"'
echo "$S" | grep -Fq '"build":36'
echo "$S" | grep -Fq '"running_partition":"app0"'
echo "$S" | grep -Fq '"image_state":"VALID"'
echo "$S" | grep -Fq '"wifi":true'
echo "$S" | grep -Fq '"mqtt":true'
C=$(config_status_get); echo "CONFIG_STATUS=$C" >> "$OUT"; echo "$C" | grep -Fq '"revision":3'

echo '=== SIGN IMAGES ===' >> "$OUT"
rm -rf "$LAB" "$TARGET"; mkdir -p "$LAB" "$TARGET"
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-update-test/firmware.bin \
  --output "$LAB" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.36-remote-test --build 37 --channel dev \
  --private-key "$PRIV" --public-key "$PUB" >/tmp/stage7d-lab-manifest.log
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-target-test/firmware.bin \
  --output "$TARGET" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.37 --build 38 --channel dev \
  --private-key "$PRIV" --public-key "$PUB" >/tmp/stage7d-target-manifest.log

echo '=== INSTALL LAB ===' >> "$OUT"
install_package "$LAB"
wait_transition '0.1.36-remote-test' 37 app1
S=$(wait_online '0.1.36-remote-test' 37); echo "LAB_STATUS=$S" >> "$OUT"
P=$(persisted_get); R=$(rule_get); RT=$(runtime_get); CFG=$(config_get)
echo "LEGACY_PERSISTED=$P" >> "$OUT"
echo "LEGACY_RULE=$R" >> "$OUT"
echo "LEGACY_RUNTIME=$RT" >> "$OUT"
echo "LEGACY_CONFIG=$CFG" >> "$OUT"
echo "$CFG" | grep -Fq '"revision":3'
echo "$R" | grep -Fq '"configured":false'
echo "$RT" | grep -Fq '"state":"DISABLED"'

echo '=== REJECT INVALID PERSISTED RULE ===' >> "$OUT"
apply_config /tmp/stage7d-invalid.json 400 /tmp/stage7d-invalid-response.json
grep -Eq 'persisted_rule_hysteresis_invalid|rule_hysteresis_invalid' /tmp/stage7d-invalid-response.json
C=$(config_status_get); echo "AFTER_INVALID_CONFIG_STATUS=$C" >> "$OUT"; echo "$C" | grep -Fq '"revision":3'

echo '=== APPLY RULE A -> REV4 ===' >> "$OUT"
apply_config /tmp/stage7d-a.json 200 /tmp/stage7d-a-response.json
C=$(config_status_get); P=$(persisted_get); R=$(rule_get); RT=$(runtime_get)
echo "A_CONFIG_STATUS=$C" >> "$OUT"; echo "A_PERSISTED=$P" >> "$OUT"; echo "A_RULE=$R" >> "$OUT"; echo "A_RUNTIME=$RT" >> "$OUT"
echo "$C" | grep -Fq '"revision":4'
echo "$P" | grep -Fq '"loaded_revision":4'
echo "$P" | grep -Fq '"loaded_rule_id":"persisted.demo.a"'
echo "$R" | grep -Fq '"configured":true'
echo "$R" | grep -Fq '"enabled":true'
echo "$R" | grep -Fq '"on_below":16.000'
echo "$R" | grep -Fq '"off_above":18.000'
echo "$RT" | grep -Fq '"state":"ARMED"'
echo "$RT" | grep -Fq '"work_task_enabled":false'
post_input 15; wait_decision TURN_ON true 1
post_input 19; wait_decision TURN_OFF false 2

echo '=== REBOOT PROVES RULE A AUTO-LOAD ===' >> "$OUT"
reboot_lab '0.1.36-remote-test' 37
C=$(config_status_get); P=$(persisted_get); R=$(rule_get); RT=$(runtime_get)
echo "A_REBOOT_CONFIG=$C" >> "$OUT"; echo "A_REBOOT_PERSISTED=$P" >> "$OUT"; echo "A_REBOOT_RULE=$R" >> "$OUT"; echo "A_REBOOT_RUNTIME=$RT" >> "$OUT"
echo "$C" | grep -Fq '"revision":4'
echo "$P" | grep -Fq '"loaded_revision":4'
echo "$P" | grep -Fq '"loaded_rule_id":"persisted.demo.a"'
echo "$R" | grep -Fq '"configured":true'
echo "$RT" | grep -Fq '"state":"ARMED"'
echo "$RT" | grep -Fq '"work_task_enabled":false'
post_input 15; wait_decision TURN_ON true 1
post_input 19; wait_decision TURN_OFF false 2

echo '=== APPLY RULE B -> REV5 ===' >> "$OUT"
apply_config /tmp/stage7d-b.json 200 /tmp/stage7d-b-response.json
C=$(config_status_get); P=$(persisted_get); R=$(rule_get); RT=$(runtime_get)
echo "B_CONFIG_STATUS=$C" >> "$OUT"; echo "B_PERSISTED=$P" >> "$OUT"; echo "B_RULE=$R" >> "$OUT"; echo "B_RUNTIME=$RT" >> "$OUT"
echo "$C" | grep -Fq '"revision":5'
echo "$P" | grep -Fq '"loaded_revision":5'
echo "$P" | grep -Fq '"loaded_rule_id":"persisted.demo.b"'
echo "$R" | grep -Fq '"on_below":14.000'
echo "$R" | grep -Fq '"off_above":20.000'
post_input 13; wait_decision TURN_ON true 3
post_input 21; wait_decision TURN_OFF false 4

echo '=== ROLLBACK RESTORES RULE A AS REV6 ===' >> "$OUT"
CODE=$(curl -sS --max-time 12 -o /tmp/stage7d-rollback.json -w '%{http_code}' -X POST "$BASE_URL/api/configuration/rollback")
echo "ROLLBACK_HTTP=$CODE $(cat /tmp/stage7d-rollback.json)" >> "$OUT"
test "$CODE" = 200
C=$(config_status_get); P=$(persisted_get); R=$(rule_get); RT=$(runtime_get); CFG=$(config_get)
echo "ROLLBACK_CONFIG_STATUS=$C" >> "$OUT"; echo "ROLLBACK_PERSISTED=$P" >> "$OUT"; echo "ROLLBACK_RULE=$R" >> "$OUT"; echo "ROLLBACK_RUNTIME=$RT" >> "$OUT"; echo "ROLLBACK_CONFIG=$CFG" >> "$OUT"
echo "$C" | grep -Fq '"revision":6'
echo "$P" | grep -Fq '"loaded_revision":6'
echo "$P" | grep -Fq '"loaded_rule_id":"persisted.demo.a"'
echo "$R" | grep -Fq '"on_below":16.000'
echo "$R" | grep -Fq '"off_above":18.000'
echo "$CFG" | grep -Fq '"id":"persisted.demo.a"'
post_input 15; wait_decision TURN_ON true 5
post_input 19; wait_decision TURN_OFF false 6

echo '=== REBOOT PROVES ROLLBACK PERSISTENCE ===' >> "$OUT"
reboot_lab '0.1.36-remote-test' 37
C=$(config_status_get); P=$(persisted_get); R=$(rule_get); RT=$(runtime_get)
echo "ROLLBACK_REBOOT_CONFIG=$C" >> "$OUT"; echo "ROLLBACK_REBOOT_PERSISTED=$P" >> "$OUT"; echo "ROLLBACK_REBOOT_RULE=$R" >> "$OUT"; echo "ROLLBACK_REBOOT_RUNTIME=$RT" >> "$OUT"
echo "$C" | grep -Fq '"revision":6'
echo "$P" | grep -Fq '"loaded_revision":6'
echo "$P" | grep -Fq '"loaded_rule_id":"persisted.demo.a"'
echo "$RT" | grep -Fq '"state":"ARMED"'
echo "$RT" | grep -Fq '"work_task_enabled":false'
post_input 15; wait_decision TURN_ON true 1
post_input 19; wait_decision TURN_OFF false 2

echo '=== INSTALL CLEAN TARGET ===' >> "$OUT"
install_package "$TARGET"
wait_transition '0.1.37' 38 app0
S=$(wait_online '0.1.37' 38)
C=$(config_status_get); P=$(persisted_get); R=$(rule_get); RT=$(runtime_get); SUP=$(curl -fsS --max-time 5 "$BASE_URL/api/supervisor"); COMPS=$(curl -fsS --max-time 5 "$BASE_URL/api/components")
CODE=$(curl -sS --max-time 5 -o /tmp/stage7d-clean-test.json -w '%{http_code}' "$BASE_URL/api/test/rules/runtime")
echo "FINAL_STATUS=$S" >> "$OUT"
echo "FINAL_CONFIG=$C" >> "$OUT"
echo "FINAL_PERSISTED=$P" >> "$OUT"
echo "FINAL_RULE=$R" >> "$OUT"
echo "FINAL_RUNTIME=$RT" >> "$OUT"
echo "FINAL_SUPERVISOR=$SUP" >> "$OUT"
echo "FINAL_COMPONENTS=$COMPS" >> "$OUT"
echo "FINAL_TEST_ENDPOINT_HTTP=$CODE" >> "$OUT"
echo "$S" | grep -Fq '"version":"0.1.37"'
echo "$S" | grep -Fq '"build":38'
echo "$S" | grep -Fq '"running_partition":"app0"'
echo "$S" | grep -Fq '"image_state":"VALID"'
echo "$S" | grep -Fq '"wifi":true'
echo "$S" | grep -Fq '"mqtt":true'
echo "$S" | grep -Fq '"http_allowed":false'
echo "$C" | grep -Fq '"revision":6'
echo "$P" | grep -Fq '"loaded_revision":6'
echo "$P" | grep -Fq '"loaded_rule_id":"persisted.demo.a"'
echo "$R" | grep -Fq '"configured":true'
echo "$R" | grep -Fq '"enabled":true'
echo "$RT" | grep -Fq '"state":"ARMED"'
echo "$RT" | grep -Fq '"work_task_enabled":false'
echo "$SUP" | grep -Fq '"state":"RUNNING"'
echo "$COMPS" | grep -Fq '"dropped":0'
test "$CODE" = 404

echo STAGE7D_PHYSICAL_PROOF_OK >> "$OUT"
cat "$OUT"
