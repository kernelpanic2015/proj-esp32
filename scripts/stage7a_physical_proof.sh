#!/usr/bin/env bash
set -euo pipefail

OUT="${OUT:-/tmp/proj-esp32-stage7a-proof.txt}"
: > "$OUT"
BASE_URL="http://proj-esp32.local"
KEYDIR="$HOME/.config/proj-esp32/keys"
PRIV="$KEYDIR/update-signing-private.pem"
PUB="keys/update-signing-public.pem"
ROOT="$HOME/Downloads/proj-esp32-ota/stage7a-proof"
LAB="$ROOT/lab"
TARGET="$ROOT/target"
mkdir -p "$LAB" "$TARGET"

echo "=== BASELINE ===" >> "$OUT"
S=$(curl -fsS --max-time 5 "$BASE_URL/api/status")
echo "STATUS=$S" >> "$OUT"
echo "$S" | grep -Fq '"version":"0.1.25"'
echo "$S" | grep -Fq '"build":26'
echo "$S" | grep -Fq '"image_state":"VALID"'

echo "=== BUILD + SIGN STAGE7A IMAGES ===" >> "$OUT"
./scripts/pio run -e nodemcu-32s-remote-update-test >/tmp/stage7a-proof-lab-build.log 2>&1
./scripts/pio run -e nodemcu-32s-remote-target-test >/tmp/stage7a-proof-target-build.log 2>&1
rm -rf "$LAB" "$TARGET"
mkdir -p "$LAB" "$TARGET"
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-update-test/firmware.bin \
  --output "$LAB" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.26-remote-test --build 27 --channel dev \
  --private-key "$PRIV" --public-key "$PUB" >/tmp/stage7a-proof-lab-manifest.log
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-target-test/firmware.bin \
  --output "$TARGET" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.27 --build 28 --channel dev \
  --private-key "$PRIV" --public-key "$PUB" >/tmp/stage7a-proof-target-manifest.log

install_package() {
  local dir="$1"
  local sig code
  sig=$(base64 -w0 "$dir/manifest.sig")
  code=$(curl -sS --max-time 15 -o /tmp/stage7a-prep.json -w '%{http_code}' \
    --data-urlencode manifest@"$dir/manifest.json" \
    --data-urlencode signature="$sig" \
    "$BASE_URL/api/update/prepare")
  echo "PREPARE_HTTP=$code $(cat /tmp/stage7a-prep.json)" >> "$OUT"
  test "$code" = 200
  code=$(curl -sS --max-time 90 -o /tmp/stage7a-upload.json -w '%{http_code}' \
    -F firmware=@"$dir/firmware.bin" "$BASE_URL/api/update/upload")
  echo "UPLOAD_HTTP=$code $(cat /tmp/stage7a-upload.json)" >> "$OUT"
  test "$code" = 200
}

wait_transition() {
  local version="$1" build="$2" partition="$3"
  local pending=0 valid=0 s
  for _ in $(seq 1 90); do
    sleep 1
    s=$(curl -fsS --max-time 1 "$BASE_URL/api/status" 2>/dev/null || true)
    if echo "$s" | grep -Fq "\"version\":\"$version\"" && echo "$s" | grep -Fq "\"build\":$build"; then
      if echo "$s" | grep -Fq '"image_state":"PENDING_VERIFY"'; then pending=1; fi
      if echo "$s" | grep -Fq '"image_state":"VALID"'; then valid=1; break; fi
    fi
  done
  echo "TRANSITION version=$version build=$build partition=$partition pending=$pending valid=$valid" >> "$OUT"
  test "$pending" -eq 1
  test "$valid" -eq 1
  echo "$s" | grep -Fq "\"running_partition\":\"$partition\""
}

reboot_lab() {
  local code
  code=$(curl -sS --max-time 5 -o /tmp/stage7a-reboot.json -w '%{http_code}' \
    -X POST --data-urlencode command=reboot "$BASE_URL/api/test/mqtt/command")
  echo "REBOOT_REQUEST_HTTP=$code $(cat /tmp/stage7a-reboot.json)" >> "$OUT"
  test "$code" = 202
  local down=0 up=0 s
  for _ in $(seq 1 15); do
    sleep 1
    if ! curl -fsS --max-time 1 "$BASE_URL/api/status" >/dev/null 2>&1; then down=1; break; fi
  done
  for _ in $(seq 1 45); do
    sleep 1
    s=$(curl -fsS --max-time 2 "$BASE_URL/api/status" 2>/dev/null || true)
    if echo "$s" | grep -Fq '"state":"ONLINE"' && echo "$s" | grep -Fq '"mqtt":true'; then up=1; break; fi
  done
  echo "REBOOT_DOWN=$down REBOOT_UP=$up" >> "$OUT"
  test "$up" -eq 1
}

echo "=== INSTALL LAB IMAGE ===" >> "$OUT"
install_package "$LAB"
wait_transition '0.1.26-remote-test' 27 app1
S=$(curl -fsS --max-time 5 "$BASE_URL/api/status")
CS=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration/status")
CFG=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration")
echo "LAB_STATUS=$S" >> "$OUT"
echo "CONFIG_STATUS_INITIAL=$CS" >> "$OUT"
echo "CONFIG_INITIAL=$CFG" >> "$OUT"
echo "$CS" | grep -Fq '"ready":true'
echo "$CS" | grep -Fq '"revision":0'
echo "$CFG" | grep -Fq '"rules":[]'
echo "$CFG" | grep -Fq '"schedules":[]'

CFG1='{"schema":1,"rules":[{"id":"demo.rule","enabled":false,"note":"first"}],"schedules":[]}'
CODE=$(curl -sS --max-time 10 -o /tmp/stage7a-apply1.json -w '%{http_code}' \
  -X POST --data-urlencode config="$CFG1" "$BASE_URL/api/configuration/apply")
echo "APPLY1_HTTP=$CODE $(cat /tmp/stage7a-apply1.json)" >> "$OUT"
test "$CODE" = 200
CS=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration/status")
CFG=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration")
echo "CONFIG_STATUS_AFTER_APPLY1=$CS" >> "$OUT"
echo "CONFIG_AFTER_APPLY1=$CFG" >> "$OUT"
echo "$CS" | grep -Fq '"revision":1'
echo "$CS" | grep -Fq '"rules_count":1'
echo "$CFG" | grep -Fq '"note":"first"'
echo "$CFG" | grep -Fq '"enabled":false'

BAD='{"schema":1,"rules":[{"id":"dup","enabled":true},{"id":"dup","enabled":false}],"schedules":[]}'
CODE=$(curl -sS --max-time 10 -o /tmp/stage7a-bad.json -w '%{http_code}' \
  -X POST --data-urlencode config="$BAD" "$BASE_URL/api/configuration/apply")
echo "INVALID_APPLY_HTTP=$CODE $(cat /tmp/stage7a-bad.json)" >> "$OUT"
test "$CODE" = 400
CS=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration/status")
echo "$CS" | grep -Fq '"revision":1'

echo "=== REBOOT PERSISTENCE REV1 ===" >> "$OUT"
reboot_lab
CS=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration/status")
CFG=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration")
echo "CONFIG_STATUS_AFTER_REBOOT1=$CS" >> "$OUT"
echo "CONFIG_AFTER_REBOOT1=$CFG" >> "$OUT"
echo "$CS" | grep -Fq '"revision":1'
echo "$CFG" | grep -Fq '"note":"first"'

CFG2='{"schema":1,"rules":[{"id":"demo.rule","enabled":true,"note":"second"}],"schedules":[]}'
CODE=$(curl -sS --max-time 10 -o /tmp/stage7a-apply2.json -w '%{http_code}' \
  -X POST --data-urlencode config="$CFG2" "$BASE_URL/api/configuration/apply")
echo "APPLY2_HTTP=$CODE $(cat /tmp/stage7a-apply2.json)" >> "$OUT"
test "$CODE" = 200
CS=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration/status")
CFG=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration")
echo "$CS" | grep -Fq '"revision":2'
echo "$CFG" | grep -Fq '"note":"second"'
echo "$CFG" | grep -Fq '"enabled":true'

CODE=$(curl -sS --max-time 10 -o /tmp/stage7a-rollback.json -w '%{http_code}' \
  -X POST "$BASE_URL/api/configuration/rollback")
echo "ROLLBACK_HTTP=$CODE $(cat /tmp/stage7a-rollback.json)" >> "$OUT"
test "$CODE" = 200
CS=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration/status")
CFG=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration")
echo "CONFIG_STATUS_AFTER_ROLLBACK=$CS" >> "$OUT"
echo "CONFIG_AFTER_ROLLBACK=$CFG" >> "$OUT"
echo "$CS" | grep -Fq '"revision":3'
echo "$CS" | grep -Fq '"last_result":"rolled_back"'
echo "$CFG" | grep -Fq '"note":"first"'
echo "$CFG" | grep -Fq '"enabled":false'

echo "=== REBOOT PERSISTENCE REV3 ===" >> "$OUT"
reboot_lab
CS=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration/status")
CFG=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration")
echo "CONFIG_STATUS_AFTER_REBOOT2=$CS" >> "$OUT"
echo "CONFIG_AFTER_REBOOT2=$CFG" >> "$OUT"
echo "$CS" | grep -Fq '"revision":3'
echo "$CFG" | grep -Fq '"note":"first"'

echo "=== INSTALL CLEAN TARGET ===" >> "$OUT"
install_package "$TARGET"
wait_transition '0.1.27' 28 app0
S=$(curl -fsS --max-time 5 "$BASE_URL/api/status")
CS=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration/status")
CFG=$(curl -fsS --max-time 5 "$BASE_URL/api/configuration")
SUP=$(curl -fsS --max-time 5 "$BASE_URL/api/supervisor")
C=$(curl -fsS --max-time 5 "$BASE_URL/api/components")
CODE=$(curl -sS --max-time 5 -o /tmp/stage7a-clean-test.json -w '%{http_code}' \
  -X POST "$BASE_URL/api/test/mqtt/command")
echo "FINAL_STATUS=$S" >> "$OUT"
echo "FINAL_CONFIG_STATUS=$CS" >> "$OUT"
echo "FINAL_CONFIG=$CFG" >> "$OUT"
echo "FINAL_SUPERVISOR=$SUP" >> "$OUT"
echo "FINAL_COMPONENTS=$C" >> "$OUT"
echo "FINAL_LAB_ENDPOINT_HTTP=$CODE" >> "$OUT"
echo "$S" | grep -Fq '"version":"0.1.27"'
echo "$S" | grep -Fq '"build":28'
echo "$S" | grep -Fq '"image_state":"VALID"'
echo "$S" | grep -Fq '"wifi":true'
echo "$S" | grep -Fq '"mqtt":true'
echo "$CS" | grep -Fq '"revision":3'
echo "$CFG" | grep -Fq '"note":"first"'
echo "$SUP" | grep -Fq '"state":"RUNNING"'
echo "$C" | grep -Fq '"dropped":0'
test "$CODE" = 404

echo STAGE7A_PHYSICAL_PROOF_OK >> "$OUT"
cat "$OUT"
