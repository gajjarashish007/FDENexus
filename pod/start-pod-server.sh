#!/usr/bin/env bash
# Permanent pod-server manager — the ONLY supported way to start/stop the dashboard.
#
# Usage:
#   bash start-pod-server.sh start       # start (or report already running)
#   bash start-pod-server.sh stop        # stop
#   bash start-pod-server.sh restart     # stop + start
#   bash start-pod-server.sh force-restart  # kill all + start (never skip)
#   bash start-pod-server.sh status      # health + port check
#   bash start-pod-server.sh diagnose    # full troubleshoot output
#
# Do NOT run: python3 pod-server.py  (blocked — causes port 8080 conflicts)
#
set -euo pipefail
set +H

# Bump when changing launch/auth behavior (verify on host: grep launch_pod_server start-pod-server.sh)
POD_START_SCRIPT_ID="20260928-export-launch"

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# shellcheck source=pod-lib.sh
source "$ROOT/pod-lib.sh"
pod_lib_init

PIDFILE="${POD_PIDFILE:-$ROOT/pod-server.pid}"
LOGFILE="${POD_LOGFILE:-$ROOT/pod-server.log}"
LOCKFILE="${POD_SCRIPT_LOCK:-$ROOT/.pod-server.start.lock}"
PORT="${POD_PORT:-8080}"
PY="${POD_PYTHON:-python3}"

export POD_AWS_REGION="${POD_AWS_REGION:-us-east-2}"
export POD_VERSION_ENV="${POD_VERSION_ENV:-comcast}"
export POD_VERSION_CACHE_TTL="${POD_VERSION_CACHE_TTL:-45}"
export POD_VERSION_REFRESH_SEC="${POD_VERSION_REFRESH_SEC:-45}"
export POD_PODS_CACHE_TTL="${POD_PODS_CACHE_TTL:-45}"
export POD_DEPLOYMENTS_CACHE_TTL="${POD_DEPLOYMENTS_CACHE_TTL:-90}"
export POD_NODES_CACHE_TTL="${POD_NODES_CACHE_TTL:-180}"
export POD_SERVICE_CACHE_TTL="${POD_SERVICE_CACHE_TTL:-90}"
export POD_K8S_HTML_CACHE_TTL="${POD_K8S_HTML_CACHE_TTL:-120}"
export POD_TRAFFIC_CACHE_TTL="${POD_TRAFFIC_CACHE_TTL:-300}"
export POD_CLUSTERS_CACHE_TTL="${POD_CLUSTERS_CACHE_TTL:-300}"
export POD_AUTH_USER="${POD_AUTH_USER:-admin}"
export POD_AUTH_SESSION_HOURS="${POD_AUTH_SESSION_HOURS:-24}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
export POD_MANAGED_START=1

PORTAL_ROOT="$(cd "$ROOT/.." && pwd)"
# shellcheck source=../scripts/load-portal-env.sh
source "$PORTAL_ROOT/scripts/load-portal-env.sh"
load_portal_env

if [[ -z "${POD_AUTH_PASSWORD:-}" ]]; then
  echo "WARNING: POD_AUTH_PASSWORD is not set. Set it in .pod-dashboard.env or the environment before start."
  echo "         Example: echo 'POD_AUTH_PASSWORD=YourSecurePassword' >> $ROOT/.pod-dashboard.env"
  echo "         After first successful start, password is also stored in $ROOT/data/auth.defaults"
fi
export POD_AUTH_PASSWORD="${POD_AUTH_PASSWORD:-}"
if [[ -z "${POD_AUTH_PASSWORD}" ]]; then
  unset POD_AUTH_PASSWORD 2>/dev/null || true
else
  export POD_AUTH_PASSWORD
fi

export POD_VALIDATOR_ENABLED="${POD_VALIDATOR_ENABLED:-1}"
export POD_VALIDATOR_UPSTREAM="${POD_VALIDATOR_UPSTREAM:-http://127.0.0.1:5000}"
export POD_VALIDATOR_PORT="${POD_VALIDATOR_PORT:-5000}"
export POD_VALIDATOR_PUBLIC_URL="${POD_VALIDATOR_PUBLIC_URL:-}"
export POD_VALIDATOR_AUTO_START="${POD_VALIDATOR_AUTO_START:-0}"

lock_holder_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -t "$LOCKFILE" 2>/dev/null | tr '\n' ' '
    return
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser "$LOCKFILE" 2>/dev/null | tr -d ' ' | tr ' ' '\n'
  fi
}

break_script_lock() {
  local pid
  echo "Clearing pod start/stop lock: $LOCKFILE"
  for pid in $(lock_holder_pids); do
    [[ -z "$pid" ]] && continue
    [[ "$pid" -eq "$$" ]] && continue
    if kill -0 "$pid" 2>/dev/null; then
      echo "  stopping PID $pid ($(ps -p "$pid" -o args= 2>/dev/null || echo unknown))"
      kill "$pid" 2>/dev/null || true
      sleep 1
      kill -9 "$pid" 2>/dev/null || true
    fi
  done
  sleep 1
  rm -f "$LOCKFILE"
}

acquire_script_lock() {
  local wait_sec="${POD_START_LOCK_WAIT_SEC:-90}"
  exec 9>"$LOCKFILE"
  if flock -w "$wait_sec" 9; then
    return 0
  fi
  echo "ERROR: Timed out after ${wait_sec}s waiting for pod start/stop lock."
  echo "  Another terminal may be running start-pod-server.sh or run-portal.sh."
  echo "  Lock file: $LOCKFILE"
  lock_holder_pids | while read -r pid; do
    [[ -n "$pid" ]] && ps -fp "$pid" 2>/dev/null || true
  done
  lsof "$LOCKFILE" 2>/dev/null || true
  echo ""
  echo "  Fix: bash $0 break-lock"
  echo "       bash $0 force-restart"
  exit 1
}

health_ok() {
  curl -sf --max-time 4 "http://127.0.0.1:${PORT}/api/health" >/dev/null 2>&1
}

_pod_login_json_body() {
  POD_AUTH_USER="${POD_AUTH_USER}" POD_AUTH_PASSWORD="${POD_AUTH_PASSWORD:-}" "$PY" -c '
import json, os
print(json.dumps({
    "username": os.environ.get("POD_AUTH_USER", ""),
    "password": os.environ.get("POD_AUTH_PASSWORD", ""),
}))
'
}

_launch_pod_server() {
  # Never use inline VAR=value prefixes here — passwords with !#$ etc break bash parsing.
  export POD_MANAGED_START=1
  export POD_AUTH_USER="${POD_AUTH_USER}"
  export POD_RBAC_DB="${POD_RBAC_DB}"
  export POD_AUTH_SESSION_HOURS="${POD_AUTH_SESSION_HOURS}"
  export POD_KUBECTL="${POD_KUBECTL:-}"
  export PATH="${PATH}"
  if [[ -n "${POD_AUTH_PASSWORD:-}" ]]; then
    export POD_AUTH_PASSWORD
  else
    unset POD_AUTH_PASSWORD 2>/dev/null || true
  fi
  nohup "$PY" "$ROOT/pod-server.py" >>"$LOGFILE" 2>&1 &
  echo $!
}

is_running() {
  if [[ ! -f "$PIDFILE" ]]; then
    return 1
  fi
  local pid
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

port_in_use() {
  if command -v ss >/dev/null 2>&1; then
    ss -tlnH 2>/dev/null | grep -qE ":${PORT}([[:space:]]|$)" && return 0
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser "${PORT}/tcp" >/dev/null 2>&1 && return 0
  fi
  return 1
}

port_listener_pids() {
  local pid pids=""
  if command -v fuser >/dev/null 2>&1; then
    for pid in $(fuser "${PORT}/tcp" 2>/dev/null || true); do
      [[ "$pid" =~ ^[0-9]+$ ]] && pids="$pids $pid"
    done
  fi
  if command -v ss >/dev/null 2>&1; then
    for pid in $(ss -tlnp 2>/dev/null | grep -E ":${PORT}([[:space:]]|$)" | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p'); do
      pids="$pids $pid"
    done
  fi
  for pid in $(pgrep -f "pod-server\\.py" 2>/dev/null || true); do
    pids="$pids $pid"
  done
  echo "$pids" | tr ' ' '\n' | grep -E '^[0-9]+$' | sort -u | tr '\n' ' '
}

stop_systemd_service() {
  if command -v systemctl >/dev/null 2>&1 && systemctl is-active pod-server >/dev/null 2>&1; then
    echo "Stopping systemd pod-server ..."
    systemctl stop pod-server 2>/dev/null || true
    sleep 2
  fi
}

kill_all_pod_servers() {
  local pid
  stop_systemd_service
  echo "Stopping all pod-server processes ..."
  if [[ -f "$PIDFILE" ]]; then
    pid="$(cat "$PIDFILE" 2>/dev/null || true)"
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
    sleep 1
    [[ -n "$pid" ]] && kill -9 "$pid" 2>/dev/null || true
    rm -f "$PIDFILE"
  fi
  pkill -f "[p]od-server\\.py" 2>/dev/null || true
  sleep 1
  pkill -9 -f "[p]od-server\\.py" 2>/dev/null || true
  for pid in $(port_listener_pids); do
    [[ -n "$pid" ]] && kill -9 "$pid" 2>/dev/null || true
  done
  if command -v fuser >/dev/null 2>&1; then
    fuser -k -KILL "${PORT}/tcp" 2>/dev/null || true
  fi
  rm -f "$ROOT/pod-server.lock"
  sleep 1
}

wait_port_free() {
  local i
  for i in $(seq 1 25); do
    port_in_use || return 0
    sleep 1
  done
  return 1
}

show_port_holders() {
  echo "--- port $PORT ---"
  ss -tlnp 2>/dev/null | grep -E ":${PORT}([[:space:]]|$)" || true
  ps aux 2>/dev/null | grep -E '[p]od-server\.py' || true
}

adopt_if_healthy() {
  local pid
  health_ok || return 1
  if ! curl -sf -X POST "http://127.0.0.1:${PORT}/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "$(_pod_login_json_body)" \
    | grep -q '"ok"'; then
    echo "WARNING: Server on port $PORT is healthy but login failed — forcing restart to repair auth."
    return 1
  fi
  pid="$(port_listener_pids | awk '{print $1}')"
  [[ -n "$pid" ]] || return 1
  echo "$pid" >"$PIDFILE"
  echo "============================================"
  echo "  pod-server ALREADY RUNNING (healthy)"
  echo "  pid:       $pid"
  echo "  port:      $PORT"
  echo "  login:     http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT}/login"
  echo "  dashboard: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT}/dashboard.html"
  echo "============================================"
  echo "No restart needed. To force restart: bash $0 force-restart"
  return 0
}

ensure_rbac_data_dir() {
  local rbac_dir="${POD_RBAC_DIR:-$ROOT/data}"
  mkdir -p "$rbac_dir"
  if ! touch "$rbac_dir/.write_test" 2>/dev/null; then
    rbac_dir="${HOME}/.pod-dashboard"
    mkdir -p "$rbac_dir"
  else
    rm -f "$rbac_dir/.write_test"
  fi
  export POD_RBAC_DB="${POD_RBAC_DB:-$rbac_dir/rbac.db}"
  chmod u+rwx "$rbac_dir" 2>/dev/null || true
  echo "  rbac db: $POD_RBAC_DB"
}

reset_admin_password() {
  ensure_python3 || exit 1
  ensure_rbac_data_dir
  echo "Resetting admin password for: ${POD_AUTH_USER:-admin}"
  export POD_MANAGED_START=1
  export POD_RBAC_DB="${POD_RBAC_DB}"
  export POD_AUTH_USER="${POD_AUTH_USER}"
  if [[ -n "${POD_AUTH_PASSWORD:-}" ]]; then
    export POD_AUTH_PASSWORD
  else
    unset POD_AUTH_PASSWORD 2>/dev/null || true
  fi
  "$PY" -c "
import pod_rbac
pod_rbac.load_auth_environment()
pod_rbac.init_db()
pod_rbac.persist_auth_defaults()
pod_rbac.sync_admin_password_from_env()
print('Password synced. Database:', pod_rbac.db_path())
"
}

start_server() {
  local force="${1:-0}"
  acquire_script_lock

  ensure_python3 || exit 1
  ensure_rbac_data_dir
  reset_admin_password

  if [[ "$force" == "1" ]]; then
    echo "Force restart — stopping every pod-server instance on port $PORT ..."
    kill_all_pod_servers
    if ! wait_port_free; then
      echo "ERROR: port $PORT still in use after force kill:"
      show_port_holders
      exit 1
    fi
  elif adopt_if_healthy; then
    exit 0
  fi

  echo "Starting pod-server (port $PORT) ..."
  if [[ "$force" != "1" ]] && port_in_use; then
    kill_all_pod_servers
    wait_port_free || { show_port_holders; exit 1; }
  fi
  if [[ "${POD_FAST_START:-0}" == "1" ]]; then
    "$PY" -c "import boto3" 2>/dev/null || install_python_requirements || exit 1
  else
    install_python_requirements || exit 1
  fi
  ensure_kubectl || pod_warn "Starting without kubectl — EKS views will show Not connected until kubectl is available."
  "$PY" -m py_compile "$ROOT/pod-server.py" "$ROOT/pod_auth.py" "$ROOT/pod_rbac.py" "$ROOT/pod_singleton.py" "$ROOT/pod_clusters.py" "$ROOT/pod_cache.py"

  echo "  auth: enabled (user: ${POD_AUTH_USER})"
  echo "  log:  $LOGFILE"
  echo "  script: start-pod-server.sh ${POD_START_SCRIPT_ID}"

  local new_pid
  new_pid="$(_launch_pod_server)" || exit 1
  echo "$new_pid" >"$PIDFILE"

  local i
  for i in $(seq 1 45); do
    if health_ok; then
      echo ""
      echo "============================================"
      echo "  pod-server STARTED OK"
      echo "  pid:       $new_pid"
      echo "  port:      $PORT"
      echo "  health:    $(curl -sf "http://127.0.0.1:${PORT}/api/health" 2>/dev/null || echo '{}')"
      if curl -sf -X POST "http://127.0.0.1:${PORT}/api/auth/login" \
        -H 'Content-Type: application/json' \
        -d "$(_pod_login_json_body)" \
        | grep -q '"ok"'; then
        echo "  login:     OK (admin credentials verified)"
      else
        echo "  login:     FAILED — run: bash $0 reset-admin-password"
      fi
      echo "  url:       http://$(hostname -I 2>/dev/null | awk '{print $1}'):${PORT}/login"
      echo "============================================"
      exit 0
    fi
    if ! kill -0 "$new_pid" 2>/dev/null; then
      echo "ERROR: pod-server process exited during startup."
      tail -25 "$LOGFILE" 2>/dev/null || true
      rm -f "$PIDFILE"
      exit 1
    fi
    sleep 1
  done

  echo "ERROR: pod-server started but health check timed out."
  tail -25 "$LOGFILE" 2>/dev/null || true
  show_port_holders
  exit 1
}

stop_server() {
  acquire_script_lock
  kill_all_pod_servers
  wait_port_free || true
  echo "pod-server stopped."
}

status_server() {
  echo "=== pod-server status ==="
  echo "port $PORT: $(port_in_use && echo IN_USE || echo free)"
  [[ -f "$PIDFILE" ]] && echo "pid file: $(cat "$PIDFILE") $(is_running && echo alive || echo stale)"
  if health_ok; then
    echo "health: OK — $(curl -sf "http://127.0.0.1:${PORT}/api/health" 2>/dev/null)"
    echo "login:  http://127.0.0.1:${PORT}/login"
    exit 0
  fi
  echo "health: NOT OK"
  show_port_holders
  tail -10 "$LOGFILE" 2>/dev/null || true
  exit 1
}

diagnose_server() {
  echo "=== diagnose ==="
  echo "user: $(whoami)  dir: $ROOT"
  status_server || true
  echo ""
  echo "Fix: bash $0 force-restart"
}

install_deps() {
  install_all_prerequisites
}

case "${1:-start}" in
  start)   start_server 0 ;;
  stop)    stop_server ;;
  restart|force-restart)
    echo "=== FORCE RESTART pod-server ==="
    break_script_lock
    stop_server
    start_server 1
    ;;
  break-lock)
    break_script_lock
    echo "Lock cleared. Run: bash $0 start"
    ;;
  kill-port) acquire_script_lock; kill_all_pod_servers; wait_port_free && echo "Port $PORT is free" ;;
  reset-admin-password) reset_admin_password ;;
  status)  status_server ;;
  diagnose) diagnose_server ;;
  install-deps) install_deps ;;
  *)
    echo "Usage: $0 {start|stop|restart|force-restart|break-lock|status|diagnose|kill-port|reset-admin-password}"
    exit 1
    ;;
esac
