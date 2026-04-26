#!/usr/bin/env bash
# install.sh — set up the Literature Review Agent (Mac / Linux)
set -euo pipefail

YELLOW='\033[1;33m'; GREEN='\033[0;32m'; RED='\033[0;31m'; BOLD='\033[1m'; NC='\033[0m'
info() { echo -e "${YELLOW}▸ $*${NC}"; }
ok()   { echo -e "${GREEN}✓ $*${NC}"; }
err()  { echo -e "${RED}✗ $*${NC}"; exit 1; }

echo ""
echo -e "${BOLD}╔══════════════════════════════════════╗${NC}"
echo -e "${BOLD}║  Literature Review Agent — Install   ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════╝${NC}"
echo ""

# ── Prerequisites ──────────────────────────────────────────────────────────────
command -v conda &>/dev/null \
    || err "conda not found. Install Miniconda: https://docs.conda.io/en/latest/miniconda.html"
ok "conda $(conda --version | awk '{print $2}')"

command -v node &>/dev/null \
    || err "Node.js not found. Install v18+: https://nodejs.org"
command -v npm &>/dev/null \
    || err "npm not found. Install Node.js v18+: https://nodejs.org"
ok "Node.js $(node --version)  /  npm $(npm --version)"

# ── Conda environment ──────────────────────────────────────────────────────────
if conda env list | grep -q "^litreview "; then
    info "Updating 'litreview' conda environment..."
    conda env update -n litreview -f environment.yml --prune
else
    info "Creating 'litreview' conda environment (this may take a few minutes)..."
    conda env create -f environment.yml
fi
ok "Conda environment 'litreview' ready."

# ── Frontend dependencies ──────────────────────────────────────────────────────
info "Installing frontend dependencies..."
cd frontend && npm install && cd ..
ok "Frontend dependencies installed."

echo ""
echo -e "  ${GREEN}Installation complete!${NC}"
echo    "  Run  ./start.sh  to launch the application."
echo ""
