#!/usr/bin/env bash
set -euo pipefail
BASE=http://proj-esp32.local
OUT=${OUT:-/tmp/stage7d-preflight.txt}
: > "$OUT"
{
  echo '=== GIT ==='
  git status --short --branch
  echo LOCAL_HEAD=$(git rev-parse HEAD)
  git fetch origin main >/dev/null
  echo REMOTE_HEAD=$(git rev-parse origin/main)
  echo '=== DEVICE STATUS ==='
  curl -fsS --max-time 5 "$BASE/api/status" || true
  echo
  echo '=== ACTIVE CONFIG ==='
  curl -fsS --max-time 5 "$BASE/api/configuration" || true
  echo
  echo '=== CONFIG STATUS ==='
  curl -fsS --max-time 5 "$BASE/api/configuration/status" || true
  echo
  echo '=== RULE ENGINE ==='
  curl -fsS --max-time 5 "$BASE/api/rules/status" || true
  echo
  echo '=== RULE RUNTIME ==='
  curl -fsS --max-time 5 "$BASE/api/rules/runtime" || true
  echo
} >> "$OUT"
cat "$OUT"
