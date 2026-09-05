#!/usr/bin/env bash
set -euo pipefail

OUT="${OUT:-/tmp/stage7a-drd-physical.txt}"
: > "$OUT"
BASE="http://proj-esp32.local"
KEYDIR="$HOME/.config/proj-esp32/keys"
PRIV="$KEYDIR/update-signing-private.pem"
PUB="keys/update-signing-public.pem"
ROOT="$HOME/Downloads/proj-esp32-ota/stage7a-drd-proof"
LAB="$ROOT/lab"
TARGET="$ROOT/target"
rm -rf "$ROOT"
mkdir -p "$LAB" "$TARGET"

status() { curl -fsS --max-time 5 "$BASE/api/status"; }
config_status() { curl -fsS --max-time 5 "$BASE/api/configuration/status"; }
config_json() { curl -fsS --max-time 5 "$BASE/api/configuration"; }

wait_online() {
  local max="$1" expected_version="$2" expected_build="$3" up=0 s=""
  for _ in $(seq 1 "$max"); do
    sleep 1
    s=$(curl -fsS --max-time 1 "$BASE/api/status" 2>/dev/null || true)
    if echo "$s" | grep -Fq "\"version\":\"$expected_version\"" &&
       echo "$s" | grep -Fq "\"build\":$expected_build" &&
       echo "$s" | grep -Fq '"state":"ONLINE"' &&
       echo "$s" | grep -Fq '"wifi":true' &&
       echo "$s" | grep -Fq '"mqtt":true'; then
      up=1
      break
    fi
  done
  echo "WAIT_ONLINE version=$expected_version build=$expected_build up=$up" >> "$OUT"
  test "$up" -eq 1
}

wait_transition() {
  local version="$1" build="$2" partition="$3" pending=0 valid=0 s=""
  for _ in $(seq 1 90); do
    sleep 1
    s=$(curl -fsS --max-time 1 "$BASE/api/status" 2>/dev/null || true)
    if echo "$s" | grep -Fq "\"version\":\"$version\"" && echo "$s" | grep -Fq "\"build\":$build"; then
      echo "$s" | grep -Fq '"image_state":"PENDING_VERIFY"' && pending=1 || true
      if echo "$s" | grep -Fq '"image_state":"VALID"'; then valid=1; break; fi
    fi
  done
  echo "TRANSITION version=$version build=$build partition=$partition pending=$pending valid=$valid" >> "$OUT"
  test "$pending" -eq 1
  test "$valid" -eq 1
  echo "$s" | grep -Fq "\"running_partition\":\"$partition\""
}

install_package() {
  local dir="$1" sig code
  sig=$(base64 -w0 "$dir/manifest.sig")
  code=$(curl -sS --max-time 15 -o /tmp/stage7a-drd-prep.json -w '%{http_code}' \
    --data-urlencode manifest@"$dir/manifest.json" \
    --data-urlencode signature="$sig" "$BASE/api/update/prepare")
  echo "PREPARE_HTTP=$code $(cat /tmp/stage7a-drd-prep.json)" >> "$OUT"
  test "$code" = 200
  code=$(curl -sS --max-time 90 -o /tmp/stage7a-drd-upload.json -w '%{http_code}' \
    -F firmware=@"$dir/firmware.bin" "$BASE/api/update/upload")
  echo "UPLOAD_HTTP=$code $(cat /tmp/stage7a-drd-upload.json)" >> "$OUT"
  test "$code" = 200
}

intentional_reboot() {
  local label="$1" code down=0
  code=$(curl -sS --max-time 5 -o /tmp/stage7a-drd-reboot.json -w '%{http_code}' \
    -X POST --data-urlencode command=reboot "$BASE/api/test/mqtt/command")
  echo "${label}_REQUEST_HTTP=$code $(cat /tmp/stage7a-drd-reboot.json)" >> "$OUT"
  test "$code" = 202
  for _ in $(seq 1 12); do
    sleep 1
    if ! curl -fsS --max-time 1 "$BASE/api/status" >/dev/null 2>&1; then down=1; break; fi
  done
  echo "${label}_DOWN=$down" >> "$OUT"
  wait_online 30 '0.1.28-remote-test' 29
  local cs cfg
  cs=$(config_status); cfg=$(config_json)
  echo "${label}_CONFIG_STATUS=$cs" >> "$OUT"
  echo "${label}_CONFIG=$cfg" >> "$OUT"
  echo "$cs" | grep -Fq '"revision":3'
  echo "$cfg" | grep -Fq '"note":"first"'
  echo "$cfg" | grep -Fq '"enabled":false'
}

echo '=== BASELINE ===' >> "$OUT"
S=$(status); CS=$(config_status); CFG=$(config_json)
echo "STATUS=$S" >> "$OUT"
echo "CONFIG_STATUS=$CS" >> "$OUT"
echo "CONFIG=$CFG" >> "$OUT"
echo "$S" | grep -Fq '"version":"0.1.27"'
echo "$S" | grep -Fq '"build":28'
echo "$S" | grep -Fq '"image_state":"VALID"'
echo "$CS" | grep -Fq '"revision":3'

test -r "$PRIV"
test -r "$PUB"
./scripts/pio run -e nodemcu-32s-remote-update-test >/tmp/stage7a-drd-lab-build.log 2>&1
./scripts/pio run -e nodemcu-32s-remote-target-test >/tmp/stage7a-drd-target-build.log 2>&1
python3 scripts/release_manifest.py --firmware .pio/build/nodemcu-32s-remote-update-test/firmware.bin \
  --output "$LAB" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.28-remote-test --build 29 --channel dev \
  --private-key "$PRIV" --public-key "$PUB" >/tmp/stage7a-drd-lab-manifest.log
python3 scripts/release_manifest.py --firmware .pio/build/nodemcu-32s-remote-target-test/firmware.bin \
  --output "$TARGET" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.29 --build 30 --channel dev \
  --private-key "$PRIV" --public-key "$PUB" >/tmp/stage7a-drd-target-manifest.log

echo '=== INSTALL DRD-HARDENED LAB IMAGE ===' >> "$OUT"
install_package "$LAB"
wait_transition '0.1.28-remote-test' 29 app1
wait_online 30 '0.1.28-remote-test' 29

echo '=== INTENTIONAL REBOOT 1 ===' >> "$OUT"
intentional_reboot REBOOT1
# Deliberately request the second software reboot well inside the 10 s DRD
# window. restart_service must call drd->stop() first, so this must not open
# the 180 s configuration portal.
sleep 2
echo '=== INTENTIONAL REBOOT 2 WITHIN DRD WINDOW ===' >> "$OUT"
intentional_reboot REBOOT2

S=$(status); SUP=$(curl -fsS --max-time 5 "$BASE/api/supervisor"); C=$(curl -fsS --max-time 5 "$BASE/api/components")
echo "AFTER_DOUBLE_SOFTWARE_REBOOT=$S" >> "$OUT"
echo "SUPERVISOR=$SUP" >> "$OUT"
echo "COMPONENTS=$C" >> "$OUT"
echo "$SUP" | grep -Fq '"state":"RUNNING"'
echo "$C" | grep -Fq '"dropped":0'

echo '=== INSTALL CLEAN TARGET ===' >> "$OUT"
install_package "$TARGET"
wait_transition '0.1.29' 30 app0
wait_online 30 '0.1.29' 30
S=$(status); CS=$(config_status); CFG=$(config_json); SUP=$(curl -fsS --max-time 5 "$BASE/api/supervisor"); C=$(curl -fsS --max-time 5 "$BASE/api/components")
CODE=$(curl -sS --max-time 5 -o /tmp/stage7a-drd-clean-lab.json -w '%{http_code}' -X POST "$BASE/api/test/mqtt/command")
echo "FINAL_STATUS=$S" >> "$OUT"
echo "FINAL_CONFIG_STATUS=$CS" >> "$OUT"
echo "FINAL_CONFIG=$CFG" >> "$OUT"
echo "FINAL_SUPERVISOR=$SUP" >> "$OUT"
echo "FINAL_COMPONENTS=$C" >> "$OUT"
echo "FINAL_LAB_ENDPOINT_HTTP=$CODE" >> "$OUT"
echo "$S" | grep -Fq '"running_partition":"app0"'
echo "$S" | grep -Fq '"image_state":"VALID"'
echo "$CS" | grep -Fq '"revision":3'
echo "$CFG" | grep -Fq '"note":"first"'
echo "$CFG" | grep -Fq '"enabled":false'
echo "$SUP" | grep -Fq '"state":"RUNNING"'
echo "$C" | grep -Fq '"dropped":0'
test "$CODE" = 404

echo STAGE7A_DRD_PHYSICAL_PROOF_OK >> "$OUT"
cat "$OUT"
