#!/usr/bin/env bash
# FDE Nexus: launch the portal. ONE process, ONE port: the web UI at / and the API at /api.
#
#   ./start-portal.sh            local mode (default admin/admin on first run)
#   ./start-portal.sh --prod     refuses to start unless JWT_SECRET (32+ chars) and
#                                M01_ADMIN_PASSWORD are set and M01_DEMO=0
#
# Environment (all optional):
#   PORT=8077  HOST=127.0.0.1   (HOST=0.0.0.0 to reach it from other machines)
#   M01_LIVE_READS=1 (default) read real data from connected AWS accounts; changes stay simulated until --prod
#   AWS_PROFILE=<name> host credentials (or connect accounts with the "profile" method instead)
#   JWT_SECRET  M01_ADMIN_USER  M01_ADMIN_PASSWORD  M01_ADMIN_EMAIL  M01_DEMO  GITLAB_TOKEN
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOD="$ROOT/modules/m01-self-service-portal"
VENV="$MOD/.venv"
export PORT="${PORT:-${M01_PORT:-8077}}"
export M01_PORT="$PORT"
export HOST="${HOST:-127.0.0.1}"
export M01_HOST="$HOST"

if [ "${1:-}" = "--prod" ]; then
  export M01_ALLOW_INSECURE=0
  export M01_DEMO="${M01_DEMO:-0}"
  export M01_SEED_DEMO=0
else
  export M01_ALLOW_INSECURE="${M01_ALLOW_INSECURE:-1}"
fi

command -v python3 >/dev/null 2>&1 || { echo "python3 is required."; exit 1; }
for t in atmos terraform kubectl; do
  command -v "$t" >/dev/null 2>&1 || echo "Note: $t not found (some features are limited: brew install $t)."
done
[ -n "${AWS_PROFILE:-}" ] && echo "AWS_PROFILE=$AWS_PROFILE: used as the portal's host credentials."
[ -n "${GITLAB_TOKEN:-}" ] && echo "GITLAB_TOKEN is set: approved changes can open GitLab merge requests."

export M01_COMPAT_PORT="${M01_COMPAT_PORT:-5001}"   # same process; serves browsers with old cached files. 0 = off
for p in "$PORT" "$M01_COMPAT_PORT"; do
  [ "$p" = "0" ] && continue
  if lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $p is already in use (another portal running?). Stop it, or start with PORT=<port> / M01_COMPAT_PORT=0."
    exit 1
  fi
done

if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV"
fi
echo "Installing backend requirements..."
"$VENV/bin/pip" install --quiet --disable-pip-version-check -r "$MOD/requirements.txt"

echo
echo "FDE Nexus: http://$HOST:$PORT/login.html   (UI and API on port $PORT)"
echo "Login: ${M01_ADMIN_USER:-admin} (password from M01_ADMIN_PASSWORD; default 'admin' in local mode). Ctrl+C to stop."
cd "$MOD/backend"
exec "$VENV/bin/python" app.py
