#!/usr/bin/env bash
# FDE Nexus: launch the portal (M01 backend API + central web UI).
#
#   ./start-portal.sh            local mode (default admin/admin on first run)
#   ./start-portal.sh --prod     refuses to start unless JWT_SECRET (32+ chars) and
#                                M01_ADMIN_PASSWORD are set and M01_DEMO=0
#
# Environment (all optional): M01_PORT=5001  UI_PORT=8077  HOST=127.0.0.1
#   M01_LIVE_READS=1 (default) read real data from connected AWS accounts; changes stay simulated until --prod
#   AWS_PROFILE=<name> host credentials (or connect accounts with the "profile" method instead)
#   JWT_SECRET  M01_ADMIN_USER  M01_ADMIN_PASSWORD  M01_ADMIN_EMAIL  M01_DEMO  M01_SEED_DEMO
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MOD="$ROOT/modules/m01-self-service-portal"
VENV="$MOD/.venv"
export M01_PORT="${M01_PORT:-5001}"
UI_PORT="${UI_PORT:-8077}"
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
for t in atmos terraform; do
  command -v "$t" >/dev/null 2>&1 || echo "Note: $t not found. IaC changes still work, but Atmos validation is skipped (brew install $t)."
done
[ -n "${AWS_PROFILE:-}" ] && echo "AWS_PROFILE=$AWS_PROFILE: used as the portal's host credentials."
[ -n "${GITLAB_TOKEN:-}" ] && echo "GITLAB_TOKEN is set: approved changes can open GitLab merge requests." 

for p in "$M01_PORT" "$UI_PORT"; do
  if lsof -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $p is already in use. Set M01_PORT / UI_PORT to free ports."; exit 1
  fi
done

if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating virtual environment..."
  python3 -m venv "$VENV"
fi
echo "Installing backend requirements..."
"$VENV/bin/pip" install --quiet --disable-pip-version-check -r "$MOD/requirements.txt"

BACK_PID=""; UI_PID=""
cleanup() {
  echo; echo "Stopping portal..."
  [ -n "$UI_PID" ] && kill "$UI_PID" 2>/dev/null || true
  [ -n "$BACK_PID" ] && kill "$BACK_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

( cd "$MOD/backend" && exec "$VENV/bin/python" app.py ) &
BACK_PID=$!

# wait for the API (fails fast if preflight refused to start)
ok=0
for _ in $(seq 1 30); do
  kill -0 "$BACK_PID" 2>/dev/null || { echo "Backend exited. See the message above."; exit 1; }
  if curl -fsS "http://$HOST:$M01_PORT/api/health" >/dev/null 2>&1; then ok=1; break; fi
  sleep 0.5
done
[ "$ok" = 1 ] || { echo "Backend did not become healthy."; exit 1; }

( cd "$ROOT" && exec "$VENV/bin/python" -m http.server "$UI_PORT" --bind "$HOST" >/dev/null 2>&1 ) &
UI_PID=$!

echo
echo "FDE Nexus is running"
echo "  Portal:  http://$HOST:$UI_PORT/login.html"
echo "  API:     http://$HOST:$M01_PORT/api/health"
echo "  Login:   ${M01_ADMIN_USER:-admin} (password from M01_ADMIN_PASSWORD; default 'admin' in local mode)"
echo "Press Ctrl+C to stop."
wait
