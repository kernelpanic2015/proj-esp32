#!/usr/bin/env bash
set -euo pipefail

ESP_HOST=${ESP_HOST:-proj-esp32.local}
KEYDIR=${KEYDIR:-"$HOME/.config/proj-esp32/keys"}
BASE=${BASE:-"$HOME/Downloads/proj-esp32-ota/stage6b"}
OUT=${OUT:-/tmp/proj-esp32-stage6b-proof.txt}

: > "$OUT"

echo '=== PRECHECK ===' >> "$OUT"
git status --short --branch >> "$OUT"
LOCAL_BEFORE=$(git rev-parse HEAD)
REMOTE_BEFORE=$(git ls-remote origin refs/heads/main | awk '{print $1}')
echo "LOCAL_BEFORE=$LOCAL_BEFORE" >> "$OUT"
echo "REMOTE_BEFORE=$REMOTE_BEFORE" >> "$OUT"

V=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/version")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
echo "BASELINE_VERSION=$V" >> "$OUT"
echo "BASELINE_UPDATE=$U" >> "$OUT"
echo "BASELINE_STATUS=$S" >> "$OUT"
grep -q '"version":"0.1.16"' <<<"$V"
grep -q '"build":17' <<<"$V"
grep -q '"running_partition":"app1"' <<<"$U"
grep -q '"image_state":"VALID"' <<<"$U"
grep -q '"state":"ONLINE"' <<<"$S"
grep -q '"mqtt":true' <<<"$S"

echo '=== APPLY STAGE 6B SOURCE CHANGES ===' >> "$OUT"
python3 scripts/stage6b_component_registry.py >> "$OUT"

echo '=== BUILD NORMAL + SIGNED CANDIDATE ===' >> "$OUT"
./scripts/pio run -e nodemcu-32s >/tmp/stage6b-build-normal.log 2>&1
echo BUILD_NORMAL_OK >> "$OUT"
grep -E 'RAM:|Flash:|SUCCESS' /tmp/stage6b-build-normal.log | tail -n 6 >> "$OUT" || true
./scripts/pio run -e nodemcu-32s-signed-update-test >/tmp/stage6b-build-candidate.log 2>&1
echo BUILD_CANDIDATE_OK >> "$OUT"
grep -E 'RAM:|Flash:|SUCCESS' /tmp/stage6b-build-candidate.log | tail -n 6 >> "$OUT" || true

rm -rf "$BASE"
mkdir -p "$BASE"
python3 scripts/release_manifest.py \
  --firmware .pio/build/nodemcu-32s-signed-update-test/firmware.bin \
  --output "$BASE" \
  --model proj-esp32-35 \
  --hardware-revision 1 \
  --version 0.1.17 \
  --build 18 \
  --channel dev \
  --private-key "$KEYDIR/update-signing-private.pem" \
  --public-key "$KEYDIR/update-signing-public.pem" >/dev/null
openssl dgst -sha256 -verify "$KEYDIR/update-signing-public.pem" \
  -signature "$BASE/manifest.sig" "$BASE/manifest.json" >/dev/null
echo "CANDIDATE_SHA=$(sha256sum "$BASE/firmware.bin" | awk '{print $1}')" >> "$OUT"

echo '=== SIGNED OTA TO 0.1.17/18 ===' >> "$OUT"
SIG=$(base64 -w0 "$BASE/manifest.sig")
CODE=$(curl -sS --max-time 15 -o /tmp/stage6b-prepare.json -w '%{http_code}' \
  --data-urlencode manifest@"$BASE/manifest.json" \
  --data-urlencode signature="$SIG" \
  "http://$ESP_HOST/api/update/prepare")
echo "PREPARE_HTTP=$CODE" >> "$OUT"
cat /tmp/stage6b-prepare.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 200 ]]

CODE=$(curl -sS --max-time 90 -o /tmp/stage6b-upload.json -w '%{http_code}' \
  -F firmware=@"$BASE/firmware.bin" \
  "http://$ESP_HOST/api/update/upload")
echo "UPLOAD_HTTP=$CODE" >> "$OUT"
cat /tmp/stage6b-upload.json >> "$OUT"; echo >> "$OUT"
[[ "$CODE" == 200 ]]

SEEN_VERSION=0
SEEN_PENDING=0
SEEN_VALID=0
for _ in $(seq 1 90); do
  sleep 1
  V=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/version" 2>/dev/null || true)
  U=$(curl -fsS --max-time 2 "http://$ESP_HOST/api/update/status" 2>/dev/null || true)
  if grep -q '"version":"0.1.17"' <<<"$V" && grep -q '"build":18' <<<"$V"; then
    SEEN_VERSION=1
  fi
  if [[ $SEEN_VERSION -eq 1 ]] && grep -q '"running_partition":"app0"' <<<"$U" && grep -q '"image_state":"PENDING_VERIFY"' <<<"$U"; then
    SEEN_PENDING=1
  fi
  if [[ $SEEN_VERSION -eq 1 ]] && grep -q '"running_partition":"app0"' <<<"$U" && grep -q '"image_state":"VALID"' <<<"$U"; then
    SEEN_VALID=1
    break
  fi
done
echo "TRANSITION seen_version=$SEEN_VERSION pending=$SEEN_PENDING valid=$SEEN_VALID" >> "$OUT"
[[ $SEEN_VERSION -eq 1 && $SEEN_PENDING -eq 1 && $SEEN_VALID -eq 1 ]]

# Allow network/MQTT and the 2 s connectivity task to settle after validation.
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
     grep -q '"dropped":0' <<<"$C"; then
    READY=1
    break
  fi
done
[[ $READY -eq 1 ]]

echo '=== STAGE 6B RUNTIME PROOF ===' >> "$OUT"
V=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/version")
U=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/update/status")
S=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/status")
C=$(curl -fsS --max-time 5 "http://$ESP_HOST/api/components")
echo "VERSION=$V" >> "$OUT"
echo "UPDATE=$U" >> "$OUT"
echo "COMPONENTS=$C" >> "$OUT"
echo "STATUS=$S" >> "$OUT"
grep -q '"components":{"count":1' <<<"$S"
grep -q '"event_bus":' <<<"$S"
grep -q '"dropped":0' <<<"$S"

# Promote the physically validated candidate to the default baseline and move
# test profiles forward. Keep all documentation synchronized in the same stage.
python3 - <<'PY'
from pathlib import Path

# Default firmware identity.
p = Path('include/firmware_identity.h')
s = p.read_text().replace('#define PROJ_FW_VERSION "0.1.16"', '#define PROJ_FW_VERSION "0.1.17"', 1)
s = s.replace('#define PROJ_FW_BUILD 17', '#define PROJ_FW_BUILD 18', 1)
p.write_text(s)

# Advance controlled test profiles.
p = Path('platformio.ini')
s = p.read_text()
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.17\\"\n    -DPROJ_FW_BUILD=18', '-DPROJ_FW_VERSION=\\"0.1.18\\"\n    -DPROJ_FW_BUILD=19', 1)
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.17-remote-test\\"\n    -DPROJ_FW_BUILD=18', '-DPROJ_FW_VERSION=\\"0.1.18-remote-test\\"\n    -DPROJ_FW_BUILD=19', 1)
s = s.replace('-DPROJ_FW_VERSION=\\"0.1.18\\"\n    -DPROJ_FW_BUILD=19', '-DPROJ_FW_VERSION=\\"0.1.19\\"\n    -DPROJ_FW_BUILD=20', 1)
p.write_text(s)

# Keep the repeatable remote scheduler smoke aligned with the promoted baseline.
p = Path('scripts/smoke_update_scheduler.sh')
s = p.read_text()
s = s.replace('"version":"0.1.16"', '"version":"0.1.17"', 1)
s = s.replace('"build":17', '"build":18', 1)
s = s.replace('--version 0.1.17-remote-test --build 18', '--version 0.1.18-remote-test --build 19', 1)
s = s.replace('--version 0.1.18 --build 19', '--version 0.1.19 --build 20', 1)
s = s.replace("wait_for_transition '0.1.17-remote-test' 18 app0", "wait_for_transition '0.1.18-remote-test' 19 app0", 1)
s = s.replace("wait_for_online '0.1.17-remote-test' 18", "wait_for_online '0.1.18-remote-test' 19", 1)
s = s.replace('"candidate_build":19', '"candidate_build":20', 1)
s = s.replace("wait_for_transition '0.1.18' 19 app1", "wait_for_transition '0.1.19' 20 app1", 1)
s = s.replace('"version":"0.1.18"', '"version":"0.1.19"', 1)
s = s.replace('"build":19', '"build":20', 1)
p.write_text(s)

for name in ['docs/README.md', 'docs/BOOTSTRAP.md']:
    p = Path(name)
    s = p.read_text()
    s = s.replace('firmware: `0.1.16`, build `17`, channel `dev`', 'firmware: `0.1.17`, build `18`, channel `dev`')
    s = s.replace('- firmware: `0.1.16`\n- build: `17`', '- firmware: `0.1.17`\n- build: `18`')
    s = s.replace('after the automatic update-check scheduler proof', 'after the Stage 6B ComponentRegistry physical proof')
    s = s.replace('after the automatic update scheduler proof', 'after the Stage 6B ComponentRegistry physical proof')
    p.write_text(s)

p = Path('docs/runtime-test-log.md')
s = p.read_text()
s += '''\n### Stage 6B physical result — PASS\n\n- Signed candidate `0.1.17/build 18` installed into `app0`.\n- Native OTA state observed `PENDING_VERIFY -> VALID`.\n- Device returned `ONLINE` with Wi-Fi and MQTT/TLS connected.\n- `/api/components` reported one `connectivity` component in state `ONLINE`, health `OK`.\n- The same registry is embedded in `/api/status` / MQTT telemetry.\n- EventBus `dropped=0` during the proof.\n- `0.1.17/build 18` is promoted as the normal baseline.\n'''
p.write_text(s)

p = Path('docs/architecture.md')
s = p.read_text()
s += '''\n\n### Stage 6B physical proof\n\nA signed `0.1.17/build 18` image was installed on the physical ESP32 and completed `PENDING_VERIFY -> VALID`. After network settlement, `/api/components` exposed the registered `connectivity` component as `ONLINE` / `OK`, the registry appeared in `/api/status`, MQTT/TLS was connected, and the EventBus reported zero dropped events. This establishes the first real end-to-end component using TaskScheduler cadence + component-owned state/health + EventBus transitions + shared API/telemetry serialization.\n'''
p.write_text(s)
PY

rm -f scripts/stage6b_component_registry.py scripts/run_stage6b_component_registry.sh

./scripts/pio run -e nodemcu-32s >/tmp/stage6b-promoted-normal.log 2>&1
echo '=== PROMOTED NORMAL BUILD ===' >> "$OUT"
grep -E 'RAM:|Flash:|SUCCESS' /tmp/stage6b-promoted-normal.log | tail -n 6 >> "$OUT" || true

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
