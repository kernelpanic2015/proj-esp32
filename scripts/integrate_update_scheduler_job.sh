#!/usr/bin/env bash
set -euo pipefail
OUT=${OUT:-/tmp/proj-esp32-update-scheduler-build.txt}
: > "$OUT"

test -z "$(git status --porcelain)"
git fetch origin main >/dev/null
git pull --ff-only origin main >/dev/null

echo "START_HEAD=$(git rev-parse HEAD)" >> "$OUT"
python3 scripts/integrate_update_scheduler.py >> "$OUT" 2>&1
rm -f scripts/integrate_update_scheduler.py scripts/integrate_update_scheduler_job.sh

for env in nodemcu-32s nodemcu-32s-remote-update-test nodemcu-32s-remote-target-test; do
  LOG="/tmp/update-scheduler-build-$env.log"
  if ./scripts/pio run -e "$env" >"$LOG" 2>&1; then
    echo "BUILD_OK=$env" >> "$OUT"
    grep -E 'RAM:|Flash:|SUCCESS' "$LOG" | tail -n 6 >> "$OUT" || true
  else
    echo "BUILD_FAILED=$env" >> "$OUT"
    tail -n 180 "$LOG" >> "$OUT"
    exit 2
  fi
done

git add -A
git commit -m 'feat: add nonblocking automatic update check scheduler' >/dev/null
git push origin main >/dev/null
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git ls-remote origin refs/heads/main | awk '{print $1}')
echo "LOCAL_HEAD=$LOCAL" >> "$OUT"
echo "REMOTE_HEAD=$REMOTE" >> "$OUT"
test "$LOCAL" = "$REMOTE"
test -z "$(git status --porcelain)"
echo UPDATE_SCHEDULER_BUILD_OK >> "$OUT"
cat "$OUT"
