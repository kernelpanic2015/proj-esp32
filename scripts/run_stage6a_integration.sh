#!/usr/bin/env bash
set -euo pipefail
OUT=${OUT:-/tmp/proj-esp32-stage6a.txt}
: > "$OUT"

echo '=== PRECHECK ===' >> "$OUT"
git status --short --branch >> "$OUT"
test -z "$(git status --porcelain)"
git fetch origin main >/dev/null
LOCAL_BEFORE=$(git rev-parse HEAD)
REMOTE_BEFORE=$(git rev-parse origin/main)
echo "LOCAL_BEFORE=$LOCAL_BEFORE" >> "$OUT"
echo "REMOTE_BEFORE=$REMOTE_BEFORE" >> "$OUT"
git pull --ff-only origin main >/dev/null

python3 scripts/stage6a_taskscheduler_integration.py >> "$OUT" 2>&1
rm -f scripts/stage6a_taskscheduler_integration.py scripts/run_stage6a_integration.sh

for env in nodemcu-32s nodemcu-32s-remote-update-test nodemcu-32s-remote-target-test; do
  ./scripts/pio run -e "$env" > "/tmp/stage6a-${env}.log" 2>&1
  echo "BUILD_OK=$env" >> "$OUT"
  grep -E 'RAM:|Flash:|SUCCESS' "/tmp/stage6a-${env}.log" | tail -n 5 >> "$OUT" || true
done

git add -A
git commit -m 'runtime: adopt TaskScheduler cooperative foundation' >/dev/null
git push origin main >/dev/null
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git ls-remote origin refs/heads/main | awk '{print $1}')
echo "LOCAL_HEAD=$LOCAL" >> "$OUT"
echo "REMOTE_HEAD=$REMOTE" >> "$OUT"
test "$LOCAL" = "$REMOTE"
test -z "$(git status --porcelain)"
echo STAGE6A_INTEGRATION_BUILD_OK >> "$OUT"
cat "$OUT"
