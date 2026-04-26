#!/usr/bin/env bash
# start.sh — start backend (uvicorn :8000) and frontend (Vite :5173)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

BACKEND_PORT=8000
FRONTEND_PORT=5173
LOG_DIR="$SCRIPT_DIR/.logs"
mkdir -p "$LOG_DIR"

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

# ── Activate conda environment ─────────────────────────────────────────────────
echo "Activating conda environment 'litreview'..."
CONDA_BASE=$(conda info --base 2>/dev/null)
# shellcheck source=/dev/null
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate litreview

# ── Start backend ──────────────────────────────────────────────────────────────
echo "Starting backend on port $BACKEND_PORT..."
# Subshell guarantees the working directory is always the project root,
# regardless of where the caller invoked this script from.
(cd "$SCRIPT_DIR" && uvicorn backend.main:app \
    --host 127.0.0.1 \
    --port "$BACKEND_PORT") \
    > "$LOG_DIR/backend.log" 2>&1 &
echo $! > "$LOG_DIR/backend.pid"

# ── Start frontend ─────────────────────────────────────────────────────────────
echo "Starting frontend on port $FRONTEND_PORT..."
cd "$SCRIPT_DIR/frontend"
npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
echo $! > "$LOG_DIR/frontend.pid"
cd "$SCRIPT_DIR"

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
