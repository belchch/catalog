#!/bin/bash
set -euo pipefail

cat >/dev/null

LOCK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/.cursor/state"
rm -f "$LOCK_DIR/.pipeline-subagent-lock"

echo '{}'
