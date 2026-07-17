#!/bin/bash
set -euo pipefail

INPUT=$(cat)
LOCK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.cursor/state"
LOCK_FILE="$LOCK_DIR/.pipeline-subagent-lock"

mkdir -p "$LOCK_DIR"

SUBAGENT_TYPE=$(echo "$INPUT" | jq -r '.subagent_type // "unknown"')
SUBAGENT_ID=$(echo "$INPUT" | jq -r '.subagent_id // "unknown"')

COUNT=0
if [[ -f "$LOCK_FILE" ]]; then
  COUNT=$(jq -r '.count // 0' "$LOCK_FILE" 2>/dev/null || echo 0)
fi
COUNT=$((COUNT + 1))

jq -n --arg t "$SUBAGENT_TYPE" --arg id "$SUBAGENT_ID" --argjson c "$COUNT" \
  '{count: $c, last_subagent_type: $t, last_subagent_id: $id}' > "$LOCK_FILE"

echo '{"permission": "allow"}'
