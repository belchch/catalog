#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_LOG="/tmp/catalog-backend.log"
FRONTEND_LOG="/tmp/catalog-frontend.log"

kill_port() {
  local pids
  pids="$(lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    kill $pids 2>/dev/null || true
    sleep 1
    pids="$(lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      kill -9 $pids 2>/dev/null || true
    fi
  fi
}

kill_port 8000
kill_port 5173

cd "$ROOT/backend"
nohup .venv/bin/uvicorn catalog.main:app --reload --port 8000 >"$BACKEND_LOG" 2>&1 &
disown

cd "$ROOT/frontend"
nohup pnpm run dev >"$FRONTEND_LOG" 2>&1 &
disown

for _ in $(seq 1 30); do
  if curl -sf http://localhost:8000/health >/dev/null \
    && curl -sf -o /dev/null http://localhost:5173/; then
    echo "UI  http://localhost:5173"
    echo "API http://localhost:8000"
    echo "logs: $BACKEND_LOG  $FRONTEND_LOG"
    exit 0
  fi
  sleep 0.3
done

echo "не дождался готовности — смотри логи:"
echo "  $BACKEND_LOG"
echo "  $FRONTEND_LOG"
exit 1
