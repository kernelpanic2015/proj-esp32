#!/usr/bin/env bash
set -euo pipefail

ESP_HOST=${ESP_HOST:-proj-esp32.local}
FIXTURE_PORT=${FIXTURE_PORT:-8766}
KEYDIR=${KEYDIR:-"$HOME/.config/proj-esp32/keys"}
BASE=${BASE:-"$HOME/Downloads/proj-esp32-ota/mqtt-proof"}
TRANS="$BASE/transition"
TARGET="$BASE/target"
OUT=${OUT:-/tmp/proj-esp32-mqtt-ota-proof.txt}
PIDFILE=/tmp/proj-esp32-mqtt-ota-server.pid

: > "$OUT"
rm -f "$PIDFILE"
cleanup() {
  if [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
}
trap cleanup EXIT

wait_for_transition() {
  local expected_version=$1 expected_build=$2 expected_partition=$3
  local seen_version=0 seen_pending=0 seen_valid=0
  for _ in $(seq 1 75); do
    sleep 1
    local v u
    v=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/version" 2>/dev/null || true)
    u=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/update/status" 2>/dev/null || true)
    if grep -q "\"version\":\"$expected_version\"" <<<"$v" && grep -q "\"build\":$expected_build" <<<"$v"; then
      seen_version=1
    fi
    if [[ $seen_version -eq 1 ]] && grep -q "\"running_partition\":\"$expected_partition\"" <<<"$u" && grep -q '"image_state":"PENDING_VERIFY"' <<<"$u"; then
      seen_pending=1
    fi
    if [[ $seen_version -eq 1 ]] && grep -q "\"running_partition\":\"$expected_partition\"" <<<"$u" && grep -q '"image_state":"VALID"' <<<"$u"; then
      seen_valid=1
      break
    fi
  done
  echo "TRANSITION version=$expected_version build=$expected_build partition=$expected_partition seen=$seen_version pending=$seen_pending valid=$seen_valid" >> "$OUT"
  [[ $seen_version -eq 1 && $seen_pending -eq 1 && $seen_valid -eq 1 ]]
}

echo '=== BASELINE ===' >> "$OUT"
V=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/version")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
echo "VERSION=$V" >> "$OUT"
echo "UPDATE=$U" >> "$OUT"
echo "STATUS=$S" >> "$OUT"
grep -q '"version":"0.1.10"' <<<"$V"
grep -q '"build":11' <<<"$V"
grep -q '"running_partition":"app1"' <<<"$U"
grep -q '"image_state":"VALID"' <<<"$U"
grep -q '"state":"ONLINE"' <<<"$S"
grep -q '"mqtt":true' <<<"$S"

echo '=== BUILD AND SIGN ===' >> "$OUT"
./scripts/pio run -e nodemcu-32s-remote-update-test >/tmp/mqtt-proof-transition-build.log 2>&1
./scripts/pio run -e nodemcu-32s-remote-target-test >/tmp/mqtt-proof-target-build.log 2>&1
rm -rf "$BASE"
mkdir -p "$TRANS" "$TARGET"
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-update-test/firmware.bin \
  --output "$TRANS" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.11-remote-test --build 10 --channel dev \
  --private-key "$KEYDIR/update-signing-private.pem" \
  --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-target-test/firmware.bin \
  --output "$TARGET" --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.10 --build 11 --channel dev \
  --private-key "$KEYDIR/update-signing-private.pem" \
  --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" -signature "$TRANS/manifest.sig" "$TRANS/manifest.json" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" -signature "$TARGET/manifest.sig" "$TARGET/manifest.json" >/dev/null
echo "TRANSITION_SHA=$(sha256sum "$TRANS/firmware.bin" | awk '{print $1}')" >> "$OUT"
echo "TARGET_SHA=$(sha256sum "$TARGET/firmware.bin" | awk '{print $1}')" >> "$OUT"

echo '=== SIGNED WEB TRANSITION TO MQTT TEST IMAGE ===' >> "$OUT"
TSIG=$(base64 -w0 "$TRANS/manifest.sig")
CODE=$(curl -sS --max-time 15 -o /tmp/mqtt-transition-prepare.json -w '%{http_code}' \
  --data-urlencode manifest@"$TRANS/manifest.json" \
  --data-urlencode signature="$TSIG" \
  "http://$ESP_HOST/api/update/prepare")
echo "PREPARE_HTTP=$CODE" >> "$OUT"
cat /tmp/mqtt-transition-prepare.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 200 ]]
CODE=$(curl -sS --max-time 90 -o /tmp/mqtt-transition-upload.json -w '%{http_code}' \
  -F firmware=@"$TRANS/firmware.bin" \
  "http://$ESP_HOST/api/update/upload")
echo "UPLOAD_HTTP=$CODE" >> "$OUT"
cat /tmp/mqtt-transition-upload.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 200 ]]
wait_for_transition '0.1.11-remote-test' 12 app0

R=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/remote/status")
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
echo "REMOTE_STATUS_TRANSITION=$R" >> "$OUT"
echo "STATUS_TRANSITION=$S" >> "$OUT"
grep -q '"http_allowed":true' <<<"$R"
grep -q '"mqtt":true' <<<"$S"

# The lab endpoint publishes to the device's real MQTT command topic using the
# already-provisioned broker session, so no broker secret appears in this test.
TEST_CODE=$(curl -sS --max-time 5 -o /tmp/mqtt-loopback-present.json -w '%{http_code}' \
  --data-urlencode command='firmware.status' \
  "http://$ESP_HOST/api/test/mqtt/command")
echo "MQTT_LOOPBACK_ENDPOINT_HTTP=$TEST_CODE" >> "$OUT"
cat /tmp/mqtt-loopback-present.json >> "$OUT"; echo >> "$OUT"
[[ "$TEST_CODE" == 202 ]]

echo '=== LAN SIGNED RELEASE FIXTURE ===' >> "$OUT"
ESPIP=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ip"])')
KPIP=$(ip route get "$ESPIP" | sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n1)
[[ -n "$KPIP" ]]
echo "FIXTURE_HOST=$KPIP:$FIXTURE_PORT" >> "$OUT"
python3 -m http.server "$FIXTURE_PORT" --bind 0.0.0.0 --directory "$TARGET" >/tmp/mqtt-ota-fixture.log 2>&1 &
echo $! > "$PIDFILE"
sleep 1
curl -fsS --max-time 5 "http://$KPIP:$FIXTURE_PORT/manifest.json" >/dev/null
MURL="http://$KPIP:$FIXTURE_PORT/manifest.json"

echo '=== MQTT firmware.check ROUND TRIP ===' >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/mqtt-check-publish.json -w '%{http_code}' \
  --data-urlencode command="firmware.check $MURL" \
  "http://$ESP_HOST/api/test/mqtt/command")
echo "MQTT_CHECK_PUBLISH_HTTP=$CODE" >> "$OUT"
cat /tmp/mqtt-check-publish.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 202 ]]

AVAILABLE=0
for _ in $(seq 1 30); do
  sleep 1
  R=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/remote/status" 2>/dev/null || true)
  U=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/status" 2>/dev/null || true)
  if grep -q '"state":"AVAILABLE"' <<<"$R" && grep -q '"package_prepared":true' <<<"$U" && grep -q '"candidate_build":13' <<<"$U"; then
    AVAILABLE=1
    echo "MQTT_REMOTE_AVAILABLE=$R" >> "$OUT"
    echo "MQTT_PREPARED=$U" >> "$OUT"
    break
  fi
done
[[ $AVAILABLE -eq 1 ]]

echo '=== MQTT firmware.update ROUND TRIP ===' >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/mqtt-update-publish.json -w '%{http_code}' \
  --data-urlencode command='firmware.update' \
  "http://$ESP_HOST/api/test/mqtt/command")
echo "MQTT_UPDATE_PUBLISH_HTTP=$CODE" >> "$OUT"
cat /tmp/mqtt-update-publish.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 202 ]]
wait_for_transition '0.1.12' 13 app1

echo '=== FINAL RUNTIME ===' >> "$OUT"
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
R=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/remote/status")
echo "STATUS=$S" >> "$OUT"
echo "UPDATE=$U" >> "$OUT"
echo "REMOTE_STATUS=$R" >> "$OUT"
grep -q '"version":"0.1.10"' <<<"$S"
grep -q '"build":11' <<<"$S"
grep -q '"state":"ONLINE"' <<<"$S"
grep -q '"wifi":true' <<<"$S"
grep -q '"mqtt":true' <<<"$S"
grep -q '"mqtt_configured":true' <<<"$S"
grep -q '"mqtt_tls":true' <<<"$S"
grep -q '"image_state":"VALID"' <<<"$U"
grep -q '"http_allowed":false' <<<"$R"

# Test-only MQTT loopback control surface must disappear in the normal image.
CODE=$(curl -sS --max-time 5 -o /tmp/mqtt-loopback-final.json -w '%{http_code}' \
  --data-urlencode command='firmware.status' \
  "http://$ESP_HOST/api/test/mqtt/command")
echo "MQTT_LOOPBACK_FINAL_HTTP=$CODE" >> "$OUT"
[[ "$CODE" == 404 ]]

echo MQTT_TRIGGERED_REMOTE_OTA_PROOF_OK >> "$OUT"
cat "$OUT"
