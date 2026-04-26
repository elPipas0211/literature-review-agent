#!/usr/bin/env bash
# stop.sh — kill uvicorn (:8000) and Vite (:5173)

BACKEND_PORT=8000
FRONTEND_PORT=5173

_stop_port() {
    local port=$1
    local pids
    pids=$(lsof -ti:"$port" 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "$pids" | xargs kill 2>/dev/null || true
        echo "  Stopped process(es) on port $port."
    else
        echo "  No process on port $port."
    fi
}

echo "Stopping Literature Review Agent..."
_stop_port $BACKEND_PORT
_stop_port $FRONTEND_PORT

# Clean up PID files if they exist
rm -f .logs/backend.pid .logs/frontend.pid 2>/dev/null || true

echo "Done."
