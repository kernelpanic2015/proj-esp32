#!/usr/bin/env bash
set -euo pipefail

ESP_HOST=${ESP_HOST:-proj-esp32.local}
KEYDIR=${KEYDIR:-"$HOME/.config/proj-esp32/keys"}
BASE=${BASE:-"$HOME/Downloads/proj-esp32-ota/stage6b"}
OUT=${OUT:-/tmp/proj-esp32-stage6b-proof-v2.txt}

: > "$OUT"

echo '=== CONTINUE FROM DIAGNOSED PARTIAL STAGE 6B ===' >> "$OUT"
git status --short --branch >> "$OUT"
python3 scripts/stage6b_continue.py preproof >> "$OUT"

# /api/status gained registry + EventBus metadata and is also the MQTT telemetry
# payload. Increase PubSubClient packet headroom now rather than silently losing
# telemetry as the common model grows.
python3 - <<'PY'
from pathlib import Path
p=Path('src/main.cpp')
s=p.read_text()
if 'mqttClient.setBufferSize(2048);' not in s:
    if 'mqttClient.setBufferSize(1024);' not in s:
        raise SystemExit('unexpected MQTT buffer setting')
    s=s.replace('mqttClient.setBufferSize(1024);','mqttClient.setBufferSize(2048);',1)
p.write_text(s)

p=Path('docs/architecture.md')
s=p.read_text()
needle='The same registry JSON is embedded in `/api/status`, therefore it is also present in existing MQTT status/telemetry payloads. This is the first end-to-end use of the shared health model by API and messaging surfaces.'
if needle in s and 'PubSubClient packet buffer was raised to 2048 bytes' not in s:
    s=s.replace(needle, needle+' As this enlarges the shared telemetry document, the PubSubClient packet buffer was raised to 2048 bytes to preserve headroom as more components are added.',1)
p.write_text(s)
PY

echo '=== BUILD NORMAL + SIGNED CANDIDATE ===' >> "$OUT"
./scripts/pio run -e nodemcu-32s >/tmp/stage6b-v2-normal.log 2>&1
echo BUILD_NORMAL_OK >> "$OUT"
grep -E 'RAM:|Flash:|SUCCESS' /tmp/stage6b-v2-normal.log | tail -n 6 >> "$OUT" || true
./scripts/pio run -e nodemcu-32s-signed-update-test >/tmp/stage6b-v2-candidate.log 2>&1
echo BUILD_CANDIDATE_OK >> "$OUT"
grep -E 'RAM:|Flash:|SUCCESS' /tmp/stage6b-v2-candidate.log | tail -n 6 >> "$OUT" || true

rm -rf "$BASE"
mkdir -p "$BASE"
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-signed-update-test/firmware.bin \
  --output "$BASE" \
  --model proj-esp32-35 --hardware-revision 1 \
  --version 0.1.17 --build 18 --channel dev \
  --private-key "$KEYDIR/update-signing-private.pem" \
  --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" \
  -signature "$BASE/manifest.sig" "$BASE/manifest.json" >/dev/null
echo "CANDIDATE_SHA=$(sha256sum "$BASE/firmware.bin" | awk '{print $1}')" >> "$OUT"

echo '=== BASELINE BEFORE OTA ===' >> "$OUT"
V=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/version")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
echo "VERSION=$V" >> "$OUT"
echo "UPDATE=$U" >> "$OUT"
echo "STATUS_LENGTH=${#S}" >> "$OUT"
grep -q '"version":"0.1.16"' <<<"$V"
grep -q '"build":17' <<<"$V"
grep -q '"running_partition":"app1"' <<<"$U"
grep -q '"image_state":"VALID"' <<<"$U"

echo '=== SIGNED OTA 0.1.17/18 ===' >> "$OUT"
SIG=$(base64 -w0 "$BASE/manifest.sig")
CODE=$(curl -sS --max-time 15 -o /tmp/stage6b-v2-prepare.json -w '%{http_code}' \
  --data-urlencode manifest@"$BASE/manifest.json" \
  --data-urlencode signature="$SIG" \
  "http://$ESP_HOST/api/update/prepare")
echo "PREPARE_HTTP=$CODE" >> "$OUT"
cat /tmp/stage6b-v2-prepare.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 200 ]]
CODE=$(curl -sS --max-time 90 -o /tmp/stage6b-v2-upload.json -w '%{http_code}' \
  -F firmware=@"$BASE/firmware.bin" \
  "http://$ESP_HOST/api/update/upload")
echo "UPLOAD_HTTP=$CODE" >> "$OUT"
cat /tmp/stage6b-v2-upload.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 200 ]]

SEEN_VERSION=0; SEEN_PENDING=0; SEEN_VALID=0
for _ in $(seq 1 90); do
  sleep 1
  V=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/version" 2>/dev/null || true)
  U=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/status" 2>/dev/null || true)
  if grep -q '"version":"0.1.17"' <<<"$V" && grep -q '"build":18' <<<"$V"; then SEEN_VERSION=1; fi
  if [[ $SEEN_VERSION -eq 1 ]] && grep -q '"running_partition":"app0"' <<<"$U" && grep -q '"image_state":"PENDING_VERIFY"' <<<"$U"; then SEEN_PENDING=1; fi
  if [[ $SEEN_VERSION -eq 1 ]] && grep -q '"running_partition":"app0"' <<<"$U" && grep -q '"image_state":"VALID"' <<<"$U"; then SEEN_VALID=1; break; fi
done
echo "TRANSITION seen_version=$SEEN_VERSION pending=$SEEN_PENDING valid=$SEEN_VALID" >> "$OUT"
[[ $SEEN_VERSION -eq 1 && $SEEN_PENDING -eq 1 && $SEEN_VALID -eq 1 ]]

READY=0
for _ in $(seq 1 45); do
  sleep 1
  S=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/status" 2>/dev/null || true)
  C=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/components" 2>/dev/null || true)
  if grep -q '"state":"ONLINE"' <<<"$S" && \
     grep -q '"mqtt":true' <<<"$S" && \
     grep -q '"count":1' <<<"$C" && \
     grep -q '"id":"connectivity"' <<<"$C" && \
     grep -q '"state":"ONLINE"' <<<"$C" && \
     grep -q '"health":{"state":"OK"' <<<"$C" && \
     grep -q '"dropped":0' <<<"$C"; then READY=1; break; fi
done
[[ $READY -eq 1 ]]

echo '=== PHYSICAL COMPONENT PROOF ===' >> "$OUT"
V=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/version")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
C=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/components")
echo "VERSION=$V" >> "$OUT"
echo "UPDATE=$U" >> "$OUT"
echo "COMPONENTS=$C" >> "$OUT"
echo "STATUS_LENGTH=${#S}" >> "$OUT"
echo "STATUS=$S" >> "$OUT"
grep -q '"components":{"count":1' <<<"$S"
grep -q '"event_bus":' <<<"$S"
grep -q '"dropped":0' <<<"$S"

python3 scripts/stage6b_continue.py promote >> "$OUT"
rm -f \
  scripts/stage6b_component_registry.py \
  scripts/run_stage6b_component_registry.sh \
  scripts/stage6b_continue.py \
  scripts/run_stage6b_continue.sh

./scripts/pio run -e nodemcu-32s >/tmp/stage6b-v2-promoted.log 2>&1
echo '=== PROMOTED NORMAL BUILD ===' >> "$OUT"
grep -E 'RAM:|Flash:|SUCCESS' /tmp/stage6b-v2-promoted.log | tail -n 6 >> "$OUT" || true

git add -A
git commit -m 'runtime: register first TaskScheduler component' >/dev/null
git push origin main >/dev/null
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git ls-remote origin refs/heads/main | awk '{print $1}')
echo "LOCAL_HEAD=$LOCAL" >> "$OUT"
echo "REMOTE_HEAD=$REMOTE" >> "$OUT"
[[ "$LOCAL" == "$REMOTE" ]]
[[ -z "$(git status --porcelain)" ]]
echo STAGE6B_COMPONENT_REGISTRY_PROOF_OK >> "$OUT"
cat "$OUT"
