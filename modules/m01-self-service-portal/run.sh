#!/usr/bin/env bash
# Start the M01 Self-Service Portal. Creates a venv on first run.
set -euo pipefail
cd "$(dirname "$0")"

VENV=".venv"
if [ ! -d "$VENV" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r requirements.txt >/dev/null

export M01_PORT="${M01_PORT:-5001}"
echo "Starting on http://localhost:${M01_PORT}  (Ctrl+C to stop)"
python backend/app.py
