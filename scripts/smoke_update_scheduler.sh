#!/usr/bin/env bash
set -euo pipefail

ESP_HOST=${ESP_HOST:-proj-esp32.local}
FIXTURE_PORT=${FIXTURE_PORT:-8770}
KEYDIR=${KEYDIR:-"$HOME/.config/proj-esp32/keys"}
BASE=${BASE:-"$HOME/Downloads/proj-esp32-ota/scheduler-proof"}
TRANS="$BASE/transition"
TARGET="$BASE/target"
OUT=${OUT:-/tmp/proj-esp32-scheduler-proof.txt}
PIDFILE=/tmp/proj-esp32-scheduler-proof-server.pid
CERT="$BASE/fixture-cert.pem"
PKEY="$BASE/fixture-key.pem"

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
  for _ in $(seq 1 90); do
    sleep 1
    local v u
    v=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/version" 2>/dev/null || true)
    u=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/update/status" 2>/dev/null || true)
    if grep -q "\"version\":\"$expected_version\"" <<<"$v" && grep -q "\"build\":$expected_build" <<<"$v"; then seen_version=1; fi
    if [[ $seen_version -eq 1 ]] && grep -q "\"running_partition\":\"$expected_partition\"" <<<"$u" && grep -q '"image_state":"PENDING_VERIFY"' <<<"$u"; then seen_pending=1; fi
    if [[ $seen_version -eq 1 ]] && grep -q "\"running_partition\":\"$expected_partition\"" <<<"$u" && grep -q '"image_state":"VALID"' <<<"$u"; then seen_valid=1; break; fi
  done
  echo "TRANSITION version=$expected_version build=$expected_build partition=$expected_partition seen=$seen_version pending=$seen_pending valid=$seen_valid" >> "$OUT"
  [[ $seen_version -eq 1 && $seen_pending -eq 1 && $seen_valid -eq 1 ]]
}

wait_for_online() {
  local expected_version=$1 expected_build=$2
  for _ in $(seq 1 60); do
    sleep 1
    local v s
    v=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/version" 2>/dev/null || true)
    s=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/status" 2>/dev/null || true)
    if grep -q "\"version\":\"$expected_version\"" <<<"$v" && grep -q "\"build\":$expected_build" <<<"$v" && grep -q '"state":"ONLINE"' <<<"$s" && grep -q '"mqtt":true' <<<"$s"; then return 0; fi
  done
  return 1
}

echo '=== BASELINE ===' >> "$OUT"
V=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/version")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
P=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/policy")
echo "VERSION=$V" >> "$OUT"
echo "UPDATE=$U" >> "$OUT"
echo "STATUS=$S" >> "$OUT"
echo "POLICY=$P" >> "$OUT"
grep -q '"version":"0.1.20"' <<<"$V"
grep -q '"build":21' <<<"$V"
grep -q '"running_partition":"app1"' <<<"$U"
grep -q '"image_state":"VALID"' <<<"$U"
grep -q '"mqtt":true' <<<"$S"

echo '=== BUILD AND SIGN SCHEDULER-CAPABLE IMAGES ===' >> "$OUT"
./scripts/pio run -e nodemcu-32s-remote-update-test >/tmp/scheduler-proof-transition-build.log 2>&1
./scripts/pio run -e nodemcu-32s-remote-target-test >/tmp/scheduler-proof-target-build.log 2>&1
rm -rf "$BASE"
mkdir -p "$TRANS" "$TARGET"
python3 scripts/release_manifest.py --firmware .pio/build/nodemcu-32s-remote-update-test/firmware.bin --output "$TRANS" --model proj-esp32-35 --hardware-revision 1 --version 0.1.21-remote-test --build 22 --channel dev --private-key "$KEYDIR/update-signing-private.pem" --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
python3 scripts/release_manifest.py --firmware .pio/build/nodemcu-32s-remote-target-test/firmware.bin --output "$TARGET" --model proj-esp32-35 --hardware-revision 1 --version 0.1.22 --build 23 --channel dev --private-key "$KEYDIR/update-signing-private.pem" --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" -signature "$TRANS/manifest.sig" "$TRANS/manifest.json" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" -signature "$TARGET/manifest.sig" "$TARGET/manifest.json" >/dev/null
echo "TRANSITION_SHA=$(sha256sum "$TRANS/firmware.bin" | awk '{print $1}')" >> "$OUT"
echo "TARGET_SHA=$(sha256sum "$TARGET/firmware.bin" | awk '{print $1}')" >> "$OUT"

echo '=== SIGNED WEB TRANSITION TO SCHEDULER TEST IMAGE ===' >> "$OUT"
TSIG=$(base64 -w0 "$TRANS/manifest.sig")
CODE=$(curl -sS --max-time 15 -o /tmp/scheduler-transition-prepare.json -w '%{http_code}' --data-urlencode manifest@"$TRANS/manifest.json" --data-urlencode signature="$TSIG" "http://$ESP_HOST/api/update/prepare")
echo "PREPARE_HTTP=$CODE" >> "$OUT"; cat /tmp/scheduler-transition-prepare.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 200 ]]
CODE=$(curl -sS --max-time 90 -o /tmp/scheduler-transition-upload.json -w '%{http_code}' -F firmware=@"$TRANS/firmware.bin" "http://$ESP_HOST/api/update/upload")
echo "UPLOAD_HTTP=$CODE" >> "$OUT"; cat /tmp/scheduler-transition-upload.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 200 ]]
wait_for_transition '0.1.21-remote-test' 22 app0

SCH=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/scheduler")
echo "SCHEDULER_INITIAL=$SCH" >> "$OUT"
grep -q '"ready":true' <<<"$SCH"

echo '=== HTTPS RELEASE FIXTURE ===' >> "$OUT"
ESPIP=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ip"])')
KPIP=$(ip route get "$ESPIP" | sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n1)
[[ -n "$KPIP" ]]
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$PKEY" -out "$CERT" -days 1 -subj '/CN=proj-esp32-scheduler-fixture' >/dev/null 2>&1
chmod 600 "$PKEY"
python3 -c 'import http.server,ssl,sys,os; os.chdir(sys.argv[1]); h=http.server.ThreadingHTTPServer(("0.0.0.0",int(sys.argv[2])),http.server.SimpleHTTPRequestHandler); c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); c.load_cert_chain(sys.argv[3],sys.argv[4]); h.socket=c.wrap_socket(h.socket,server_side=True); h.serve_forever()' "$TARGET" "$FIXTURE_PORT" "$CERT" "$PKEY" >/tmp/scheduler-proof-https-fixture.log 2>&1 &
echo $! > "$PIDFILE"
sleep 1
curl -kfsS --max-time 5 "https://$KPIP:$FIXTURE_PORT/manifest.json" >/dev/null
MURL="https://$KPIP:$FIXTURE_PORT/manifest.json"
echo "FIXTURE_URL=$MURL" >> "$OUT"

echo '=== ENABLE 60s AUTOMATIC CHECK POLICY ===' >> "$OUT"
CODE=$(curl -sS --max-time 10 -o /tmp/scheduler-policy-enable.json -w '%{http_code}' --data-urlencode enabled=true --data-urlencode manifest_url="$MURL" --data-urlencode interval_seconds=60 --data-urlencode channel=dev "http://$ESP_HOST/api/update/policy")
echo "POLICY_ENABLE_HTTP=$CODE" >> "$OUT"; cat /tmp/scheduler-policy-enable.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 200 ]]
P=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/policy")
SCH=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/scheduler")
echo "POLICY_ENABLED=$P" >> "$OUT"
echo "SCHEDULER_ARMED=$SCH" >> "$OUT"
grep -q '"enabled":true' <<<"$P"
grep -q '"interval_seconds":60' <<<"$P"

# Reboot proves scheduler derives its next boot-relative due time from persisted
# policy rather than from volatile state. No firmware.check command is sent.
echo '=== REBOOT WITH ENABLED POLICY ===' >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/scheduler-reboot.json -w '%{http_code}' --data-urlencode command=reboot "http://$ESP_HOST/api/test/mqtt/command")
echo "REBOOT_PUBLISH_HTTP=$CODE" >> "$OUT"; cat /tmp/scheduler-reboot.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 202 ]]
sleep 3
wait_for_online '0.1.21-remote-test' 22
P=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/policy")
SCH=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/scheduler")
echo "POLICY_AFTER_REBOOT=$P" >> "$OUT"
echo "SCHEDULER_AFTER_REBOOT=$SCH" >> "$OUT"
grep -q '"enabled":true' <<<"$P"
grep -q '"armed":true' <<<"$SCH"
grep -q '"interval_seconds":60' <<<"$SCH"

echo '=== WAIT FOR AUTOMATIC CHECK; NO MANUAL/MQTT firmware.check ===' >> "$OUT"
AVAILABLE=0
for _ in $(seq 1 90); do
  sleep 1
  R=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/remote/status" 2>/dev/null || true)
  U=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/status" 2>/dev/null || true)
  SCH=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/scheduler" 2>/dev/null || true)
  if grep -q '"state":"AVAILABLE"' <<<"$R" && grep -q '"package_prepared":true' <<<"$U" && grep -q '"candidate_build":23' <<<"$U" && grep -Eq '"attempt_count":[1-9][0-9]*' <<<"$SCH" && grep -Eq '"accepted_count":[1-9][0-9]*' <<<"$SCH"; then
    AVAILABLE=1
    echo "AUTO_REMOTE_AVAILABLE=$R" >> "$OUT"
    echo "AUTO_PREPARED=$U" >> "$OUT"
    echo "AUTO_SCHEDULER=$SCH" >> "$OUT"
    break
  fi
done
[[ $AVAILABLE -eq 1 ]]
P=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/policy")
echo "POLICY_AFTER_AUTO_CHECK=$P" >> "$OUT"
grep -q '"last_result":"available"' <<<"$P"

echo '=== OPERATOR APPLY; SCHEDULER MUST NOT AUTO-APPLY ===' >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/scheduler-apply.json -w '%{http_code}' -X POST "http://$ESP_HOST/api/update/apply")
echo "APPLY_HTTP=$CODE" >> "$OUT"; cat /tmp/scheduler-apply.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 202 ]]
wait_for_transition '0.1.22' 23 app1

echo '=== DISABLE TEMPORARY FIXTURE POLICY ===' >> "$OUT"
P=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/policy")
REV=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["revision"])' <<<"$P")
CODE=$(curl -sS --max-time 10 -o /tmp/scheduler-policy-disable.json -w '%{http_code}' --data-urlencode enabled=false --data-urlencode manifest_url="$MURL" --data-urlencode interval_seconds=60 --data-urlencode channel=dev "http://$ESP_HOST/api/update/policy")
echo "POLICY_DISABLE_HTTP=$CODE" >> "$OUT"; cat /tmp/scheduler-policy-disable.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 200 ]]

# Give loop time to observe the new policy revision and disarm.
sleep 2

echo '=== FINAL RUNTIME ===' >> "$OUT"
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
P=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/policy")
R=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/remote/status")
SCH=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/scheduler")
echo "STATUS=$S" >> "$OUT"
echo "UPDATE=$U" >> "$OUT"
echo "POLICY_FINAL=$P" >> "$OUT"
echo "REMOTE_FINAL=$R" >> "$OUT"
echo "SCHEDULER_FINAL=$SCH" >> "$OUT"
grep -q '"version":"0.1.22"' <<<"$S"
grep -q '"build":23' <<<"$S"
grep -q '"state":"ONLINE"' <<<"$S"
grep -q '"wifi":true' <<<"$S"
grep -q '"mqtt":true' <<<"$S"
grep -q '"mqtt_tls":true' <<<"$S"
grep -q '"image_state":"VALID"' <<<"$U"
grep -q '"enabled":false' <<<"$P"
grep -q '"armed":false' <<<"$SCH"
grep -q '"http_allowed":false' <<<"$R"

CODE=$(curl -sS --max-time 5 -o /tmp/scheduler-loopback-final.json -w '%{http_code}' --data-urlencode command='firmware.status' "http://$ESP_HOST/api/test/mqtt/command")
echo "MQTT_LOOPBACK_FINAL_HTTP=$CODE" >> "$OUT"
[[ "$CODE" == 404 ]]

echo TASKSCHEDULER_AUTOMATIC_UPDATE_PROOF_OK >> "$OUT"
cat "$OUT"
