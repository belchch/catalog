#!/bin/bash
set -euo pipefail

INPUT=$(cat)
LOCK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.cursor/state"
LOCK_FILE="$LOCK_DIR/.pipeline-subagent-lock"

if [[ ! -f "$LOCK_FILE" ]]; then
  echo '{"permission": "allow"}'
  exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.command // ""')

if echo "$COMMAND" | grep -Eq 'git[[:space:]]+(commit|push|checkout|reset|merge|rebase)\b|git[[:space:]]+branch[[:space:]]+-[dD]|gh[[:space:]]+pr[[:space:]]+(create|merge|review)\b'; then
  jq -n --arg cmd "$COMMAND" '{
    permission: "deny",
    user_message: "Заблокировано хуком pipeline-git-guard: git/gh-команды, меняющие состояние ветки/PR, разрешены только parent-оркестратору catalog-pipeline, не подагентам catalog-generator/catalog-reviewer.",
    agent_message: ("Эта команда запрещена внутри catalog-generator/catalog-reviewer (см. .cursor/hooks/pipeline-git-guard.sh): " + $cmd + ". Верни изменения/вердикт без git-операций — commit/push/checkout/PR делает parent.")
  }'
  exit 0
fi

echo '{"permission": "allow"}'
