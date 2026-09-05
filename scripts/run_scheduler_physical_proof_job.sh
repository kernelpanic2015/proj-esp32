#!/usr/bin/env bash
set -euo pipefail
test -z "$(git status --porcelain)"
git fetch origin main >/dev/null
git pull --ff-only origin main >/dev/null
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git ls-remote origin refs/heads/main | awk '{print $1}')
test "$LOCAL" = "$REMOTE"
OUT=/tmp/proj-esp32-scheduler-proof.txt bash scripts/smoke_update_scheduler.sh >/tmp/proj-esp32-scheduler-proof-console.txt 2>&1
cat /tmp/proj-esp32-scheduler-proof.txt
