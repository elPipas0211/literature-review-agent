#!/usr/bin/env bash
# start.sh — bootstrap if needed, then start backend (:8000) and frontend (:5173)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BACKEND_PORT=8000
FRONTEND_PORT=5173
LOG_DIR="$SCRIPT_DIR/.logs"
mkdir -p "$LOG_DIR"

# ── Bootstrap ──────────────────────────────────────────────────────────────────
[ -x .venv/bin/python ] || ./install.sh
[ -d frontend/node_modules ] || (cd frontend && npm install --no-audit --no-fund)

# ── Kill any process already on these ports ────────────────────────────────────
_stop_port() {
    local port=$1
    local pids
    pids=$(lsof -ti:"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill 2>/dev/null || true
        sleep 0.4
        echo "  Stopped existing process on port $port."
    fi
}

echo "Checking ports..."
_stop_port $BACKEND_PORT
_stop_port $FRONTEND_PORT

# ── Start backend ──────────────────────────────────────────────────────────────
echo "Starting backend on port $BACKEND_PORT..."
(cd "$SCRIPT_DIR" && .venv/bin/python -m uvicorn backend.main:app \
    --host 127.0.0.1 \
    --port "$BACKEND_PORT") \
    > "$LOG_DIR/backend.log" 2>&1 &
echo $! > "$LOG_DIR/backend.pid"

# ── Start frontend ─────────────────────────────────────────────────────────────
echo "Starting frontend on port $FRONTEND_PORT..."
(cd "$SCRIPT_DIR/frontend" && npm run dev) > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$LOG_DIR/frontend.pid"

sleep 2

echo ""
echo "╔═══════════════════════════════════════════╗"
echo "║   Literature Review Agent is running       ║"
echo "╠═══════════════════════════════════════════╣"
echo "║  Frontend  →  http://localhost:$FRONTEND_PORT      ║"
echo "║  API docs  →  http://localhost:$BACKEND_PORT/docs  ║"
echo "╚═══════════════════════════════════════════╝"
echo ""
echo "Logs : $LOG_DIR/"
echo "Stop : ./stop.sh"
echo ""
