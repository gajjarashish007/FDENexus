#!/usr/bin/env bash
# One-click install for Pod Dashboard (EC2 / Linux).
#
# Installs Python, pip, boto3, verifies kubectl/kubeconfig/AWS, then starts the server.
#
# Usage:
#   bash install.sh              # install deps + start server
#   bash install.sh --deps-only  # install deps only, do not start
#   bash install.sh --no-start   # same as --deps-only
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=pod-lib.sh
source "$ROOT/pod-lib.sh"

START_SERVER=1
for arg in "$@"; do
  case "$arg" in
    --deps-only|--no-start) START_SERVER=0 ;;
    -h|--help)
      echo "Usage: bash install.sh [--deps-only|--no-start]"
      exit 0
      ;;
  esac
done

export POD_AWS_REGION="${POD_AWS_REGION:-us-east-2}"
export POD_VERSION_ENV="${POD_VERSION_ENV:-comcast}"
export POD_VERSION_CACHE_TTL="${POD_VERSION_CACHE_TTL:-45}"
export POD_VERSION_REFRESH_SEC="${POD_VERSION_REFRESH_SEC:-45}"
export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"

install_all_prerequisites

echo
pod_msg "Installed components:"
pod_msg "  - Python 3 + pip"
pod_msg "  - boto3 (Route53 traffic migration)"
pod_msg "  - Pod dashboard files"
echo
pod_msg "Optional (warned if missing):"
pod_msg "  - kubectl + ~/.kube/config (cluster dashboard)"
pod_msg "  - AWS credentials / IAM role (Route53 lookup)"
echo

if [[ "$START_SERVER" -eq 1 ]]; then
  pod_msg "Starting pod-server ..."
  exec bash "$ROOT/start-pod-server.sh" restart
else
  pod_msg "Done. Start manually: bash start-pod-server.sh start"
fi
