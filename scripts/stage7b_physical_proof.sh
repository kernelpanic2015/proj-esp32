#!/usr/bin/env bash
set -euo pipefail

OUT="${OUT:-/tmp/proj-esp32-stage7b-proof.txt}"
: > "$OUT"
BASE_URL="http://proj-esp32.local"
KEYDIR="$HOME/.config/proj-esp32/keys"
PRIV="$KEYDIR/update-signing-private.pem"
PUB="keys/update-signing-public.pem"
ROOT="$HOME/Downloads/proj-esp32-ota/stage7b-proof"
LAB="$ROOT/lab"
TARGET="$ROOT/target"
mkdir -p "$LAB" "$TARGET"

status_get() { curl -fsS --max-time 5 "$BASE_URL/api/status"; }
rule_status_get() { curl -fsS --max-time 5 "$BASE_URL/api/rules/status"; }

install_package() {
  local dir="$1" sig code
  sig=$(base64 -w0 "$dir/manifest.sig")
  code=$(curl -sS --max-time 15 -o /tmp/stage7b-prep.json -w '%{http_code}' \
    --data-urlencode manifest@"$dir/manifest.json" \
    --data-urlencode signature="$sig" \
    "$BASE_URL/api/update/prepare")
  echo "PREPARE_HTTP=$code $(cat /tmp/stage7b-prep.json)" >> "$OUT"
  test "$code" = 200
  code=$(curl -sS --max-time 90 -o /tmp/stage7b-upload.json -w '%{http_code}' \
    -F firmware=@"$dir/firmware.bin" "$BASE_URL/api/update/upload")
  echo "UPLOAD_HTTP=$code $(cat /tmp/stage7b-upload.json)" >> "$OUT"
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

post_form() {
  local path="$1" outfile="$2"; shift 2
  curl -sS --max-time 10 -o "$outfile" -w '%{http_code}' -X POST "$@" "$BASE_URL$path"
}

echo '=== PRECHECK ===' >> "$OUT"
S=$(status_get)
echo "STATUS=$S" >> "$OUT"
echo "$S" | grep -Fq '"version":"0.1.29"'
echo "$S" | grep -Fq '"build":30'
echo "$S" | grep -Fq '"running_partition":"app0"'
echo "$S" | grep -Fq '"image_state":"VALID"'
echo "$S" | grep -Fq '"wifi":true'
echo "$S" | grep -Fq '"mqtt":true'

echo '=== SIGN STAGE7B IMAGES ===' >> "$OUT"
rm -rf "$LAB" "$TARGET"
mkdir -p "$LAB" "$TARGET"
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-update-test/firmware.bin \
  --output "$LAB" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.30-remote-test --build 31 --channel dev \
  --private-key "$PRIV" --public-key "$PUB" >/tmp/stage7b-lab-manifest.log
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-target-test/firmware.bin \
  --output "$TARGET" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.31 --build 32 --channel dev \
  --private-key "$PRIV" --public-key "$PUB" >/tmp/stage7b-target-manifest.log

echo '=== INSTALL LAB IMAGE ===' >> "$OUT"
install_package "$LAB"
wait_transition '0.1.30-remote-test' 31 app1
S=$(status_get)
RS=$(rule_status_get)
TS=$(curl -fsS --max-time 5 "$BASE_URL/api/test/rules/status")
echo "LAB_STATUS=$S" >> "$OUT"
echo "RULE_STATUS_INITIAL=$RS" >> "$OUT"
echo "TEST_STATUS_INITIAL=$TS" >> "$OUT"
echo "$RS" | grep -Fq '"configured":false'
echo "$RS" | grep -Fq '"evaluation_count":0'
echo "$TS" | grep -Fq '"state":"DISABLED"'

echo '=== INVALID RULE SEMANTICS ===' >> "$OUT"
CODE=$(post_form '/api/test/rules/configure' /tmp/stage7b-invalid.json \
  --data-urlencode on_below=18 --data-urlencode off_above=16 --data-urlencode enabled=1)
echo "INVALID_CONFIG_HTTP=$CODE $(cat /tmp/stage7b-invalid.json)" >> "$OUT"
test "$CODE" = 400
grep -Fq 'rule_hysteresis_invalid' /tmp/stage7b-invalid.json

echo '=== VALID RULE 16/18 ===' >> "$OUT"
CODE=$(post_form '/api/test/rules/configure' /tmp/stage7b-config.json \
  --data-urlencode on_below=16 --data-urlencode off_above=18 --data-urlencode enabled=1)
echo "CONFIG_HTTP=$CODE $(cat /tmp/stage7b-config.json)" >> "$OUT"
test "$CODE" = 200
grep -Fq '"configured":true' /tmp/stage7b-config.json
grep -Fq '"enabled":true' /tmp/stage7b-config.json

set_input() {
  local value="$1" out="$2"
  local code
  code=$(post_form '/api/test/rules/input' "$out" --data-urlencode "value=$value")
  echo "INPUT value=$value HTTP=$code $(cat "$out")" >> "$OUT"
  test "$code" = 200
}

evaluate_expect() {
  local expected_on="$1" expected_decision="$2" out="$3"
  local code
  code=$(post_form '/api/test/rules/evaluate' "$out")
  echo "EVALUATE expected_on=$expected_on expected_decision=$expected_decision HTTP=$code $(cat "$out")" >> "$OUT"
  test "$code" = 200
  grep -Fq "\"on\":$expected_on" "$out"
  grep -Fq "\"last_decision\":\"$expected_decision\"" "$out"
}

# Start hot: above off threshold -> actuator remains OFF.
set_input 20 /tmp/stage7b-in20.json
evaluate_expect false HOLD /tmp/stage7b-e20.json

# Below ON threshold -> ON.
set_input 15 /tmp/stage7b-in15.json
evaluate_expect true TURN_ON /tmp/stage7b-e15.json

# Deadband while ON -> hold ON.
set_input 17 /tmp/stage7b-in17a.json
evaluate_expect true HOLD /tmp/stage7b-e17a.json

# Above OFF threshold -> OFF.
set_input 19 /tmp/stage7b-in19.json
evaluate_expect false TURN_OFF /tmp/stage7b-e19.json

# Deadband while OFF -> hold OFF.
set_input 17 /tmp/stage7b-in17b.json
evaluate_expect false HOLD /tmp/stage7b-e17b.json

RS=$(rule_status_get)
echo "RULE_STATUS_AFTER_SEQUENCE=$RS" >> "$OUT"
echo "$RS" | grep -Fq '"evaluation_count":5'

echo '=== DISABLED RULE DOES NOT ACTUATE ===' >> "$OUT"
CODE=$(post_form '/api/test/rules/configure' /tmp/stage7b-disable.json \
  --data-urlencode on_below=16 --data-urlencode off_above=18 --data-urlencode enabled=0)
echo "DISABLE_HTTP=$CODE $(cat /tmp/stage7b-disable.json)" >> "$OUT"
test "$CODE" = 200
set_input 10 /tmp/stage7b-in10.json
evaluate_expect false DISABLED /tmp/stage7b-edisabled.json

SUP=$(curl -fsS --max-time 5 "$BASE_URL/api/supervisor")
C=$(curl -fsS --max-time 5 "$BASE_URL/api/components")
echo "LAB_SUPERVISOR=$SUP" >> "$OUT"
echo "LAB_COMPONENTS=$C" >> "$OUT"
echo "$SUP" | grep -Fq '"state":"RUNNING"'
echo "$C" | grep -Fq '"dropped":0'

echo '=== INSTALL CLEAN TARGET ===' >> "$OUT"
install_package "$TARGET"
wait_transition '0.1.31' 32 app0
S=$(status_get)
RS=$(rule_status_get)
CS=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration/status")
SUP=$(curl -fsS --max-time 5 "$BASE_URL/api/supervisor")
C=$(curl -fsS --max-time 5 "$BASE_URL/api/components")
CODE=$(curl -sS --max-time 5 -o /tmp/stage7b-clean-test.json -w '%{http_code}' "$BASE_URL/api/test/rules/status")
echo "FINAL_STATUS=$S" >> "$OUT"
echo "FINAL_RULE_STATUS=$RS" >> "$OUT"
echo "FINAL_CONFIG_STATUS=$CS" >> "$OUT"
echo "FINAL_SUPERVISOR=$SUP" >> "$OUT"
echo "FINAL_COMPONENTS=$C" >> "$OUT"
echo "FINAL_TEST_ENDPOINT_HTTP=$CODE" >> "$OUT"
echo "$S" | grep -Fq '"version":"0.1.31"'
echo "$S" | grep -Fq '"build":32'
echo "$S" | grep -Fq '"running_partition":"app0"'
echo "$S" | grep -Fq '"image_state":"VALID"'
echo "$S" | grep -Fq '"wifi":true'
echo "$S" | grep -Fq '"mqtt":true'
echo "$S" | grep -Fq '"http_allowed":false'
echo "$RS" | grep -Fq '"configured":false'
echo "$RS" | grep -Fq '"mode":"manual_stage7b"'
echo "$CS" | grep -Fq '"revision":3'
echo "$SUP" | grep -Fq '"state":"RUNNING"'
echo "$C" | grep -Fq '"count":1'
echo "$C" | grep -Fq '"dropped":0'
test "$CODE" = 404

echo STAGE7B_PHYSICAL_PROOF_OK >> "$OUT"
cat "$OUT"
