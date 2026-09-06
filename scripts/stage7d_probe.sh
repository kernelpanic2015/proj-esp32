#!/usr/bin/env bash
set -euo pipefail
BASE=http://proj-esp32.local
printf '%s\n' '=== GIT ==='
git status --short --branch
echo LOCAL_HEAD=$(git rev-parse HEAD)
git fetch origin main >/dev/null
echo REMOTE_HEAD=$(git rev-parse origin/main)
printf '%s\n' '=== DEVICE STATUS ==='
curl -fsS --max-time 5 "$BASE/api/status" || true
echo
printf '%s\n' '=== ACTIVE CONFIG ==='
curl -fsS --max-time 5 "$BASE/api/configuration" || true
echo
printf '%s\n' '=== CONFIG STATUS ==='
curl -fsS --max-time 5 "$BASE/api/configuration/status" || true
echo
printf '%s\n' '=== RULE STATUS ==='
curl -fsS --max-time 5 "$BASE/api/rules/status" || true
echo
printf '%s\n' '=== RULE RUNTIME ==='
curl -fsS --max-time 5 "$BASE/api/rules/runtime" || true
echo
