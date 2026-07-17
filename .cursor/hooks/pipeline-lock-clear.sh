#!/bin/bash
set -euo pipefail

cat >/dev/null

LOCK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.cursor/state"
LOCK_FILE="$LOCK_DIR/.pipeline-subagent-lock"

if [[ -f "$LOCK_FILE" ]]; then
  COUNT=$(jq -r '.count // 0' "$LOCK_FILE" 2>/dev/null || echo 0)
  COUNT=$((COUNT - 1))
  if (( COUNT <= 0 )); then
    rm -f "$LOCK_FILE"
  else
    jq --argjson c "$COUNT" '.count = $c' "$LOCK_FILE" > "$LOCK_FILE.tmp" && mv "$LOCK_FILE.tmp" "$LOCK_FILE"
  fi
fi

echo '{}'
