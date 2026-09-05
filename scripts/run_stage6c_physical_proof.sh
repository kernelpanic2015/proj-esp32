#!/usr/bin/env bash
set -euo pipefail

ESP_HOST=${ESP_HOST:-proj-esp32.local}
KEYDIR=${KEYDIR:-"$HOME/.config/proj-esp32/keys"}
BASE=${BASE:-"$HOME/Downloads/proj-esp32-ota/stage6c-proof"}
TEST="$BASE/test"
FINAL="$BASE/final"
OUT=${OUT:-/tmp/proj-esp32-stage6c-proof.txt}

: > "$OUT"
rm -rf "$BASE"
mkdir -p "$TEST" "$FINAL"

wait_valid() {
  local expected_version=$1 expected_build=$2 expected_partition=$3
  local seen_version=0 seen_pending=0 seen_valid=0
  for _ in $(seq 1 90); do
    sleep 1
    local v u
    v=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/version" 2>/dev/null || true)
    u=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/status" 2>/dev/null || true)
    if grep -q "\"version\":\"$expected_version\"" <<<"$v" &&
       grep -q "\"build\":$expected_build" <<<"$v"; then
      seen_version=1
    fi
    if [[ $seen_version -eq 1 ]] &&
       grep -q "\"running_partition\":\"$expected_partition\"" <<<"$u" &&
       grep -q '"image_state":"PENDING_VERIFY"' <<<"$u"; then
      seen_pending=1
    fi
    if [[ $seen_version -eq 1 ]] &&
       grep -q "\"running_partition\":\"$expected_partition\"" <<<"$u" &&
       grep -q '"image_state":"VALID"' <<<"$u"; then
      seen_valid=1
      break
    fi
  done
  echo "TRANSITION version=$expected_version build=$expected_build partition=$expected_partition pending=$seen_pending valid=$seen_valid" >> "$OUT"
  [[ $seen_version -eq 1 && $seen_pending -eq 1 && $seen_valid -eq 1 ]]
}

install_signed_package() {
  local dir=$1
  local sig code
  sig=$(base64 -w0 "$dir/manifest.sig")
  code=$(curl -sS --max-time 15 -o /tmp/stage6c-prepare.json -w '%{http_code}' \
    --data-urlencode manifest@"$dir/manifest.json" \
    --data-urlencode signature="$sig" \
    "http://$ESP_HOST/api/update/prepare")
  echo "PREPARE_HTTP=$code" >> "$OUT"
  cat /tmp/stage6c-prepare.json >> "$OUT"; echo >> "$OUT"
  [[ "$code" == 200 ]]

  code=$(curl -sS --max-time 90 -o /tmp/stage6c-upload.json -w '%{http_code}' \
    -F firmware=@"$dir/firmware.bin" \
    "http://$ESP_HOST/api/update/upload")
  echo "UPLOAD_HTTP=$code" >> "$OUT"
  cat /tmp/stage6c-upload.json >> "$OUT"; echo >> "$OUT"
  [[ "$code" == 200 ]]
}

echo '=== BASELINE LAB IMAGE ===' >> "$OUT"
V=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/version")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
SUP=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/supervisor")
C=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/components")
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
echo "VERSION=$V" >> "$OUT"
echo "UPDATE=$U" >> "$OUT"
echo "SUPERVISOR=$SUP" >> "$OUT"
echo "COMPONENTS=$C" >> "$OUT"
echo "STATUS=$S" >> "$OUT"
grep -q '"version":"0.1.18-remote-test"' <<<"$V"
grep -q '"build":19' <<<"$V"
grep -q '"running_partition":"app1"' <<<"$U"
grep -q '"image_state":"VALID"' <<<"$U"
grep -q '"state":"RUNNING"' <<<"$SUP"
grep -q '"health":"OK"' <<<"$SUP"
grep -q '"mqtt":true' <<<"$S"

echo '=== BUILD + SIGN FRESH TEST IMAGE 0.1.19-remote-test/build20 ===' >> "$OUT"
./scripts/pio run -e nodemcu-32s-remote-update-test >/tmp/stage6c-proof-test-build.log 2>&1
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-update-test/firmware.bin \
  --output "$TEST" \
  --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.19-remote-test --build 20 --channel dev \
  --private-key "$KEYDIR/update-signing-private.pem" \
  --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" \
  -signature "$TEST/manifest.sig" "$TEST/manifest.json" >/dev/null
install_signed_package "$TEST"
wait_valid '0.1.19-remote-test' 20 app0

# Wait for stable healthy state and verify status embedding.
READY=0
for _ in $(seq 1 40); do
  sleep 1
  SUP=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/supervisor" 2>/dev/null || true)
  C=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/components" 2>/dev/null || true)
  S=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/status" 2>/dev/null || true)
  if grep -q '"state":"RUNNING"' <<<"$SUP" &&
     grep -q '"health":"OK"' <<<"$SUP" &&
     grep -q '"id":"connectivity"' <<<"$C" &&
     grep -q '"state":"ONLINE"' <<<"$C" &&
     grep -q '"supervisor":{"state":"RUNNING"' <<<"$S" &&
     grep -q '"mqtt":true' <<<"$S"; then
    READY=1
    break
  fi
done
[[ $READY -eq 1 ]]
echo "SUPERVISOR_BEFORE=$SUP" >> "$OUT"
echo "COMPONENTS_BEFORE=$C" >> "$OUT"
echo "STATUS_BEFORE=$S" >> "$OUT"

echo '=== REAL MQTT DISCONNECT / RECONNECT SUPPRESSED 8s ===' >> "$OUT"
CODE=$(curl -sS --max-time 5 -o /tmp/stage6c-disconnect.json -w '%{http_code}' \
  -X POST "http://$ESP_HOST/api/test/mqtt/disconnect")
echo "DISCONNECT_HTTP=$CODE" >> "$OUT"
cat /tmp/stage6c-disconnect.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 202 ]]

SEEN_DEGRADED=0
for _ in $(seq 1 48); do
  sleep 0.25
  SUP=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/supervisor" 2>/dev/null || true)
  C=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/components" 2>/dev/null || true)
  S=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/status" 2>/dev/null || true)
  if grep -q '"state":"DEGRADED"' <<<"$SUP" &&
     grep -q '"health":"DEGRADED"' <<<"$SUP" &&
     grep -q '"state":"WIFI_ONLY"' <<<"$C" &&
     grep -q '"fault_code":"mqtt_disconnected"' <<<"$C" &&
     grep -q '"wifi":true' <<<"$S" &&
     grep -q '"mqtt":false' <<<"$S"; then
    SEEN_DEGRADED=1
    echo "SUPERVISOR_DEGRADED=$SUP" >> "$OUT"
    echo "COMPONENTS_DEGRADED=$C" >> "$OUT"
    echo "STATUS_DEGRADED=$S" >> "$OUT"
    break
  fi
done
[[ $SEEN_DEGRADED -eq 1 ]]

SEEN_RECOVERED=0
for _ in $(seq 1 50); do
  sleep 0.5
  SUP=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/supervisor" 2>/dev/null || true)
  C=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/components" 2>/dev/null || true)
  S=$(curl -fsS --max-time 1 "http://$ESP_HOST/api/status" 2>/dev/null || true)
  if grep -q '"state":"RUNNING"' <<<"$SUP" &&
     grep -q '"health":"OK"' <<<"$SUP" &&
     grep -q '"state":"ONLINE"' <<<"$C" &&
     grep -q '"mqtt":true' <<<"$S"; then
    SEEN_RECOVERED=1
    echo "SUPERVISOR_RECOVERED=$SUP" >> "$OUT"
    echo "COMPONENTS_RECOVERED=$C" >> "$OUT"
    echo "STATUS_RECOVERED=$S" >> "$OUT"
    break
  fi
done
[[ $SEEN_RECOVERED -eq 1 ]]

echo '=== BUILD + SIGN CLEAN FINAL 0.1.20/build21 ===' >> "$OUT"
./scripts/pio run -e nodemcu-32s-remote-target-test >/tmp/stage6c-proof-final-build.log 2>&1
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-remote-target-test/firmware.bin \
  --output "$FINAL" \
  --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.20 --build 21 --channel dev \
  --private-key "$KEYDIR/update-signing-private.pem" \
  --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" \
  -signature "$FINAL/manifest.sig" "$FINAL/manifest.json" >/dev/null
install_signed_package "$FINAL"
wait_valid '0.1.20' 21 app1

sleep 4
V=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/version")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
SUP=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/supervisor")
C=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/components")
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
CODE=$(curl -sS --max-time 5 -o /tmp/stage6c-final-test-endpoint.txt -w '%{http_code}' \
  -X POST "http://$ESP_HOST/api/test/mqtt/disconnect")
echo "FINAL_VERSION=$V" >> "$OUT"
echo "FINAL_UPDATE=$U" >> "$OUT"
echo "FINAL_SUPERVISOR=$SUP" >> "$OUT"
echo "FINAL_COMPONENTS=$C" >> "$OUT"
echo "FINAL_STATUS=$S" >> "$OUT"
echo "FINAL_TEST_ENDPOINT_HTTP=$CODE" >> "$OUT"
grep -q '"version":"0.1.20"' <<<"$V"
grep -q '"build":21' <<<"$V"
grep -q '"running_partition":"app1"' <<<"$U"
grep -q '"image_state":"VALID"' <<<"$U"
grep -q '"state":"RUNNING"' <<<"$SUP"
grep -q '"health":"OK"' <<<"$SUP"
grep -q '"state":"ONLINE"' <<<"$C"
grep -q '"dropped":0' <<<"$C"
grep -q '"supervisor":{"state":"RUNNING"' <<<"$S"
grep -q '"mqtt":true' <<<"$S"
grep -q '"mqtt_tls":true' <<<"$S"
[[ "$CODE" == 404 ]]

echo STAGE6C_PHYSICAL_PROOF_OK >> "$OUT"
cat "$OUT"
