#!/usr/bin/env bash
# Quick diagnostic for pod-server startup issues on EC2/Linux.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PY="${POD_PYTHON:-python3}"
PORT="${POD_PORT:-8080}"
LOGFILE="${POD_LOGFILE:-$ROOT/pod-server.log}"

echo "=== Python ==="
"$PY" --version
echo ""
echo "=== Compile check ==="
"$PY" -m py_compile "$ROOT/pod-server.py" "$ROOT/pod_auth.py" "$ROOT/pod_rbac.py" && echo "OK" || { echo "FAILED"; exit 1; }
echo ""
echo "=== Import check ==="
"$PY" -c "
import importlib.util
spec = importlib.util.spec_from_file_location('pod_server', '$ROOT/pod-server.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print('import OK')
"
echo ""
echo "=== Process ==="
if [[ -f pod-server.pid ]] && kill -0 "$(cat pod-server.pid)" 2>/dev/null; then
  echo "Running pid $(cat pod-server.pid)"
else
  echo "NOT running"
fi
echo ""
echo "=== Port $PORT ==="
if command -v ss >/dev/null 2>&1; then
  ss -tlnp | grep ":${PORT} " || echo "(nothing listening)"
fi
echo ""
echo "=== Health ==="
curl -sv "http://127.0.0.1:${PORT}/api/health" 2>&1 || echo "health check failed"
echo ""
echo "=== Login page ==="
LOGIN_BODY="$(curl -s "http://127.0.0.1:${PORT}/login" 2>/dev/null || true)"
if echo "$LOGIN_BODY" | grep -q "Sign In"; then
  echo "OK — login page loads"
else
  echo "FAILED — empty or wrong response (deploy updated pod-server.py + login.html, then restart)"
  echo "Response bytes: $(echo -n "$LOGIN_BODY" | wc -c)"
fi
echo ""
echo "=== Admin create (smoke) ==="
COOKIE="$(curl -s -c - -X POST "http://127.0.0.1:${PORT}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"${POD_AUTH_USER:-admin}\",\"password\":\"${POD_AUTH_PASSWORD:-}\"}" \
  2>/dev/null | awk '/pod_session/ {print $7}')"
if [[ -n "${POD_AUTH_PASSWORD:-}" && -n "$COOKIE" ]]; then
  CREATE_CODE="$(curl -s -o /tmp/pod-admin-create.json -w '%{http_code}' -X POST "http://127.0.0.1:${PORT}/api/admin/users" \
    -H 'Content-Type: application/json' \
    -H "Cookie: pod_session=${COOKIE}" \
    -d '{"username":"_smoke_test","displayName":"Smoke","password":"smoke123","role":"user"}' 2>/dev/null || echo 000)"
  echo "HTTP $CREATE_CODE — $(cat /tmp/pod-admin-create.json 2>/dev/null || echo '{}')"
  if [[ "$CREATE_CODE" == "201" || "$CREATE_CODE" == "400" ]]; then
    echo "OK — admin POST responds (400 = user already exists)"
  else
    echo "FAILED — admin create did not return JSON (check pod-server.log)"
  fi
else
  echo "SKIP — set POD_AUTH_PASSWORD to test admin create"
fi
echo ""
echo "=== Last 25 log lines ==="
tail -25 "$LOGFILE" 2>/dev/null || echo "(no log file)"
