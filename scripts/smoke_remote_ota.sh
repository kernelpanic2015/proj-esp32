#!/usr/bin/env bash
set -euo pipefail

BASE=${BASE:-"$HOME/Downloads/proj-esp32-ota/remote-proof"}
TRANS="$BASE/transition"
TARGET="$BASE/target"
ESP_HOST=${ESP_HOST:-proj-esp32.local}
FIXTURE_PORT=${FIXTURE_PORT:-8765}
OUT=${OUT:-/tmp/proj-esp32-remote-proof-summary.txt}
PIDFILE=/tmp/proj-esp32-remote-proof-server.pid

: > "$OUT"
rm -f "$PIDFILE"
cleanup() {
  if [[ -f "$PIDFILE" ]]; then
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
}
trap cleanup EXIT

json_get() {
  python3 -c "import json,sys; print(json.load(sys.stdin)[$1])"
}

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

echo '=== SIGNED WEB TRANSITION TO REMOTE-CAPABLE IMAGE ===' >> "$OUT"
TSIG=$(base64 -w0 "$TRANS/manifest.sig")
CODE=$(curl -sS --max-time 15 -o /tmp/proj-esp32-transition-prepare.json -w '%{http_code}' \
  --data-urlencode manifest@"$TRANS/manifest.json" \
  --data-urlencode signature="$TSIG" \
  "http://$ESP_HOST/api/update/prepare")
echo "PREPARE_HTTP=$CODE" >> "$OUT"
cat /tmp/proj-esp32-transition-prepare.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 200 ]]

CODE=$(curl -sS --max-time 90 -o /tmp/proj-esp32-transition-upload.json -w '%{http_code}' \
  -F firmware=@"$TRANS/firmware.bin" \
  "http://$ESP_HOST/api/update/upload")
echo "UPLOAD_HTTP=$CODE" >> "$OUT"
cat /tmp/proj-esp32-transition-upload.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 200 ]]
wait_for_transition '0.1.11-remote-test' 12 app0

R=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/remote/status")
echo "REMOTE_STATUS_TRANSITION=$R" >> "$OUT"
grep -q '"http_allowed":true' <<<"$R"

echo '=== LAN RELEASE FIXTURE ===' >> "$OUT"
ESPIP=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ip"])')
KPIP=$(ip route get "$ESPIP" | sed -n 's/.* src \([^ ]*\).*/\1/p' | head -n1)
[[ -n "$KPIP" ]]
echo "FIXTURE_HOST=$KPIP:$FIXTURE_PORT" >> "$OUT"
python3 -m http.server "$FIXTURE_PORT" --bind 0.0.0.0 --directory "$TARGET" >/tmp/proj-esp32-remote-fixture.log 2>&1 &
echo $! > "$PIDFILE"
sleep 1
curl -fsS --max-time 5 "http://$KPIP:$FIXTURE_PORT/manifest.json" >/dev/null
MURL="http://$KPIP:$FIXTURE_PORT/manifest.json"

echo '=== REMOTE CHECK ===' >> "$OUT"
CODE=$(curl -sS --max-time 10 -o /tmp/proj-esp32-remote-check.json -w '%{http_code}' \
  --data-urlencode manifest_url="$MURL" \
  "http://$ESP_HOST/api/update/check")
echo "CHECK_HTTP=$CODE" >> "$OUT"
cat /tmp/proj-esp32-remote-check.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 202 ]]

AVAILABLE=0
for _ in $(seq 1 30); do
  sleep 1
  R=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/remote/status" 2>/dev/null || true)
  U=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/status" 2>/dev/null || true)
  if grep -q '"state":"AVAILABLE"' <<<"$R" && grep -q '"package_prepared":true' <<<"$U" && grep -q '"candidate_build":13' <<<"$U"; then
    AVAILABLE=1
    echo "REMOTE_AVAILABLE=$R" >> "$OUT"
    echo "PREPARED=$U" >> "$OUT"
    break
  fi
done
[[ $AVAILABLE -eq 1 ]]

echo '=== REMOTE APPLY ===' >> "$OUT"
CODE=$(curl -sS --max-time 10 -o /tmp/proj-esp32-remote-apply.json -w '%{http_code}' \
  -X POST "http://$ESP_HOST/api/update/apply")
echo "APPLY_HTTP=$CODE" >> "$OUT"
cat /tmp/proj-esp32-remote-apply.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 202 ]]
wait_for_transition '0.1.12' 13 app1

echo '=== FINAL RUNTIME ===' >> "$OUT"
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
R=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/remote/status")
echo "STATUS=$S" >> "$OUT"
echo "UPDATE=$U" >> "$OUT"
echo "REMOTE_STATUS=$R" >> "$OUT"
grep -q '"state":"ONLINE"' <<<"$S"
grep -q '"wifi":true' <<<"$S"
grep -q '"mqtt":true' <<<"$S"
grep -q '"mqtt_configured":true' <<<"$S"
grep -q '"mqtt_tls":true' <<<"$S"
grep -q '"http_allowed":false' <<<"$R"

CODE=$(curl -sS --max-time 10 -o /tmp/proj-esp32-http-policy-reject.json -w '%{http_code}' \
  --data-urlencode manifest_url="$MURL" \
  "http://$ESP_HOST/api/update/check")
echo "HTTP_POLICY_REJECT_CODE=$CODE" >> "$OUT"
cat /tmp/proj-esp32-http-policy-reject.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 400 ]]

echo REMOTE_SIGNED_OTA_PROOF_OK >> "$OUT"
cat "$OUT"
