#!/usr/bin/env bash
# install.sh — create .venv, install Python + frontend dependencies (macOS / Linux, no conda needed)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PY=""
for c in python3.12 python3.11 python3.13 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || { echo "ERROR: Python 3.11+ not found (https://www.python.org/downloads/)"; exit 1; }
command -v npm >/dev/null || { echo "ERROR: Node.js / npm not found (https://nodejs.org)"; exit 1; }
echo "Using $($PY --version)"

[ -x .venv/bin/python ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip -q
if [ "$(uname)" = "Darwin" ]; then
  .venv/bin/python -m pip install torch -q
else
  .venv/bin/python -m pip install torch --index-url https://download.pytorch.org/whl/cpu -q
fi
.venv/bin/python -m pip install -r requirements.txt -q
echo "[OK] Python environment ready."

(cd frontend && npm install --no-audit --no-fund)
echo "[OK] Frontend ready. Run ./start.sh (the embedding model, ~470 MB, downloads on first start)."
