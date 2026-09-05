#!/usr/bin/env bash
set -euo pipefail

ESP_HOST=${ESP_HOST:-proj-esp32.local}
FIXTURE_PORT=${FIXTURE_PORT:-8767}
KEYDIR=${KEYDIR:-"$HOME/.config/proj-esp32/keys"}
BASE=${BASE:-"$HOME/Downloads/proj-esp32-ota/policy-proof"}
TRANS="$BASE/transition"
TARGET="$BASE/target"
OUT=${OUT:-/tmp/proj-esp32-policy-proof.txt}
PIDFILE=/tmp/proj-esp32-policy-proof-server.pid
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
  for _ in $(seq 1 80); do
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
echo "VERSION=$V" >> "$OUT"
echo "UPDATE=$U" >> "$OUT"
echo "STATUS=$S" >> "$OUT"
grep -q '"version":"0.1.10"' <<<"$V"
grep -q '"build":11' <<<"$V"
grep -q '"running_partition":"app1"' <<<"$U"
grep -q '"image_state":"VALID"' <<<"$U"
grep -q '"mqtt":true' <<<"$S"

echo '=== BUILD AND SIGN POLICY-CAPABLE IMAGES ===' >> "$OUT"
./scripts/pio run -e nodemcu-32s-remote-update-test >/tmp/policy-proof-transition-build.log 2>&1
./scripts/pio run -e nodemcu-32s-remote-target-test >/tmp/policy-proof-target-build.log 2>&1
rm -rf "$BASE"
mkdir -p "$TRANS" "$TARGET"
python3 scripts/release_manifest.py --firmware .pio/build/nodemcu-32s-remote-update-test/firmware.bin --output "$TRANS" --model proj-esp32-35 --hardware-revision 1 --version 0.1.11-remote-test --build 12 --channel dev --private-key "$KEYDIR/update-signing-private.pem" --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
python3 scripts/release_manifest.py --firmware .pio/build/nodemcu-32s-remote-target-test/firmware.bin --output "$TARGET" --model proj-esp32-35 --hardware-revision 1 --version 0.1.12 --build 13 --channel dev --private-key "$KEYDIR/update-signing-private.pem" --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" -signature "$TRANS/manifest.sig" "$TRANS/manifest.json" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" -signature "$TARGET/manifest.sig" "$TARGET/manifest.json" >/dev/null
echo "TRANSITION_SHA=$(sha256sum "$TRANS/firmware.bin" | awk '{print $1}')" >> "$OUT"
echo "TARGET_SHA=$(sha256sum "$TARGET/firmware.bin" | awk '{print $1}')" >> "$OUT"

echo '=== SIGNED WEB TRANSITION ===' >> "$OUT"
TSIG=$(base64 -w0 "$TRANS/manifest.sig")
CODE=$(curl -sS --max-time 15 -o /tmp/policy-transition-prepare.json -w '%{http_code}' --data-urlencode manifest@"$TRANS/manifest.json" --data-urlencode signature="$TSIG" "http://$ESP_HOST/api/update/prepare")
echo "PREPARE_HTTP=$CODE" >> "$OUT"; cat /tmp/policy-transition-prepare.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 200 ]]
CODE=$(curl -sS --max-time 90 -o /tmp/policy-transition-upload.json -w '%{http_code}' -F firmware=@"$TRANS/firmware.bin" "http://$ESP_HOST/api/update/upload")
echo "UPLOAD_HTTP=$CODE" >> "$OUT"; cat /tmp/policy-transition-upload.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 200 ]]
wait_for_transition '0.1.11-remote-test' 12 app0

echo '=== HTTPS RELEASE FIXTURE ===' >> "$OUT"
ESPIP=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ip"])')
KPIP=$(ip route get "$ESPIP" | sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n1)
[[ -n "$KPIP" ]]
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$PKEY" -out "$CERT" -days 1 -subj '/CN=proj-esp32-policy-fixture' >/dev/null 2>&1
chmod 600 "$PKEY"
python3 -c 'import http.server,ssl,sys,os; os.chdir(sys.argv[1]); h=http.server.ThreadingHTTPServer(("0.0.0.0",int(sys.argv[2])),http.server.SimpleHTTPRequestHandler); c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); c.load_cert_chain(sys.argv[3],sys.argv[4]); h.socket=c.wrap_socket(h.socket,server_side=True); h.serve_forever()' "$TARGET" "$FIXTURE_PORT" "$CERT" "$PKEY" >/tmp/policy-proof-https-fixture.log 2>&1 &
echo $! > "$PIDFILE"
sleep 1
curl -kfsS --max-time 5 "https://$KPIP:$FIXTURE_PORT/manifest.json" >/dev/null
MURL="https://$KPIP:$FIXTURE_PORT/manifest.json"
echo "FIXTURE_URL=$MURL" >> "$OUT"

echo '=== PERSIST POLICY ===' >> "$OUT"
CODE=$(curl -sS --max-time 10 -o /tmp/policy-post.json -w '%{http_code}' --data-urlencode enabled=false --data-urlencode manifest_url="$MURL" --data-urlencode interval_seconds=3600 --data-urlencode channel=dev "http://$ESP_HOST/api/update/policy")
echo "POLICY_POST_HTTP=$CODE" >> "$OUT"; cat /tmp/policy-post.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 200 ]]
P=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/policy")
echo "POLICY_BEFORE_REBOOT=$P" >> "$OUT"
grep -q '"ready":true' <<<"$P"
grep -q '"revision":1' <<<"$P"
grep -Fq "\"manifest_url\":\"$MURL\"" <<<"$P"
grep -q '"last_result":"policy_updated"' <<<"$P"

echo '=== REBOOT AND VERIFY NVS POLICY ===' >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/policy-reboot.json -w '%{http_code}' --data-urlencode command=reboot "http://$ESP_HOST/api/test/mqtt/command")
echo "REBOOT_PUBLISH_HTTP=$CODE" >> "$OUT"; cat /tmp/policy-reboot.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 202 ]]
sleep 3
wait_for_online '0.1.11-remote-test' 12
P=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/policy")
echo "POLICY_AFTER_REBOOT=$P" >> "$OUT"
grep -q '"revision":1' <<<"$P"
grep -Fq "\"manifest_url\":\"$MURL\"" <<<"$P"

echo '=== BARE MQTT firmware.check USES STORED POLICY URL ===' >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/policy-bare-check.json -w '%{http_code}' --data-urlencode command='firmware.check' "http://$ESP_HOST/api/test/mqtt/command")
echo "BARE_CHECK_PUBLISH_HTTP=$CODE" >> "$OUT"; cat /tmp/policy-bare-check.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 202 ]]
AVAILABLE=0
for _ in $(seq 1 35); do
  sleep 1
  R=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/remote/status" 2>/dev/null || true)
  U=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/status" 2>/dev/null || true)
  if grep -q '"state":"AVAILABLE"' <<<"$R" && grep -q '"package_prepared":true' <<<"$U" && grep -q '"candidate_build":13' <<<"$U"; then AVAILABLE=1; echo "REMOTE_AVAILABLE=$R" >> "$OUT"; echo "PREPARED=$U" >> "$OUT"; break; fi
done
[[ $AVAILABLE -eq 1 ]]
P=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/policy")
echo "POLICY_AFTER_BARE_CHECK=$P" >> "$OUT"
grep -q '"revision":1' <<<"$P"
grep -q '"last_result":"available"' <<<"$P"

echo '=== MQTT firmware.update ===' >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/policy-update.json -w '%{http_code}' --data-urlencode command='firmware.update' "http://$ESP_HOST/api/test/mqtt/command")
echo "UPDATE_PUBLISH_HTTP=$CODE" >> "$OUT"; cat /tmp/policy-update.json >> "$OUT"; echo >> "$OUT"; [[ "$CODE" == 202 ]]
wait_for_transition '0.1.12' 13 app1

echo '=== FINAL NVS + RUNTIME ===' >> "$OUT"
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
P=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/policy")
R=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/remote/status")
echo "STATUS=$S" >> "$OUT"; echo "UPDATE=$U" >> "$OUT"; echo "POLICY_FINAL=$P" >> "$OUT"; echo "REMOTE_FINAL=$R" >> "$OUT"
grep -q '"version":"0.1.12"' <<<"$S"
grep -q '"build":13' <<<"$S"
grep -q '"state":"ONLINE"' <<<"$S"
grep -q '"wifi":true' <<<"$S"
grep -q '"mqtt":true' <<<"$S"
grep -q '"mqtt_tls":true' <<<"$S"
grep -q '"image_state":"VALID"' <<<"$U"
grep -q '"revision":1' <<<"$P"
grep -Fq "\"manifest_url\":\"$MURL\"" <<<"$P"
grep -q '"last_result":"install_pending_reboot"' <<<"$P"
grep -q '"http_allowed":false' <<<"$R"
CODE=$(curl -sS --max-time 5 -o /tmp/policy-loopback-final.json -w '%{http_code}' --data-urlencode command='firmware.status' "http://$ESP_HOST/api/test/mqtt/command")
echo "MQTT_LOOPBACK_FINAL_HTTP=$CODE" >> "$OUT"
[[ "$CODE" == 404 ]]

echo UPDATE_POLICY_PERSISTENCE_AND_BARE_CHECK_PROOF_OK >> "$OUT"
cat "$OUT"
