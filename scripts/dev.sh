#!/usr/bin/env bash
set -euo pipefail

# Run backend (uvicorn --reload) and frontend (vite HMR) together for debugging.
# Ctrl-C stops both. Ports can be overridden: BACKEND_PORT=8001 FRONTEND_PORT=5174 make dev

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "缺少虚拟环境 .venv，请先运行: make setup" >&2
  exit 1
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "缺少前端依赖 frontend/node_modules，请先运行: make setup" >&2
  exit 1
fi

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${JWT_SECRET:?JWT_SECRET is required}"
: "${MYKB_SECRET_KEY:?MYKB_SECRET_KEY is required}"

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
KB_ROOT="${MYKB_KB_ROOT:-$HOME/.mykb/kbs}"

# Job control: each background job gets its own process group, so we can kill
# the whole tree (uvicorn reloader + worker, npm + vite) on shutdown.
set -m

cleanup() {
  trap - INT TERM EXIT
  kill -- -"$BACKEND_PID" 2>/dev/null || kill "$BACKEND_PID" 2>/dev/null || true
  kill -- -"$FRONTEND_PID" 2>/dev/null || kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo "→ backend   http://localhost:${BACKEND_PORT}  (uvicorn --reload, kb_root=${KB_ROOT})"
MYKB_KB_ROOT="$KB_ROOT" "$PY" -m uvicorn mykb.api.app:app \
  --reload --reload-dir mykb --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!

echo "→ frontend  http://localhost:${FRONTEND_PORT}  (vite HMR)"
( cd "$ROOT/frontend" && npm run dev -- --port "$FRONTEND_PORT" ) &
FRONTEND_PID=$!

echo "按 Ctrl-C 停止全部服务"
wait
