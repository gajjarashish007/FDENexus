#!/usr/bin/env bash
# Shared helpers for pod dashboard install/start scripts.

pod_lib_init() {
  POD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  POD_PY="${POD_PYTHON:-python3}"
  POD_PORT="${POD_PORT:-8080}"
  POD_REQUIREMENTS="${POD_ROOT}/requirements.txt"
}

pod_msg() { echo "[pod] $*"; }
pod_warn() { echo "[pod] WARNING: $*" >&2; }
pod_err() { echo "[pod] ERROR: $*" >&2; }

ensure_python3() {
  if command -v "$POD_PY" >/dev/null 2>&1; then
    pod_msg "Python: $($POD_PY --version 2>&1)"
    return 0
  fi
  pod_err "python3 not found."
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    if command -v dnf >/dev/null 2>&1; then dnf install -y python3; return 0; fi
    if command -v yum >/dev/null 2>&1; then yum install -y python3; return 0; fi
    if command -v apt-get >/dev/null 2>&1; then apt-get update -qq && apt-get install -y python3; return 0; fi
  fi
  return 1
}

ensure_pip() {
  if "$POD_PY" -m pip --version >/dev/null 2>&1; then
    return 0
  fi
  pod_msg "pip not found; installing..."
  if "$POD_PY" -m ensurepip --user >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    if command -v dnf >/dev/null 2>&1; then dnf install -y python3-pip && return 0; fi
    if command -v yum >/dev/null 2>&1; then yum install -y python3-pip && return 0; fi
    if command -v apt-get >/dev/null 2>&1; then apt-get update -qq && apt-get install -y python3-pip && return 0; fi
  fi
  return 1
}

install_system_packages() {
  [[ "${EUID:-$(id -u)}" -eq 0 ]] || return 0
  local pkgs=(python3 python3-pip curl)
  if command -v dnf >/dev/null 2>&1; then
    pod_msg "Installing system packages (dnf): ${pkgs[*]} python3-boto3"
    dnf install -y "${pkgs[@]}" python3-boto3 2>/dev/null || dnf install -y "${pkgs[@]}"
    return 0
  fi
  if command -v yum >/dev/null 2>&1; then
    pod_msg "Installing system packages (yum): ${pkgs[*]} python3-boto3"
    yum install -y "${pkgs[@]}" python3-boto3 2>/dev/null || yum install -y "${pkgs[@]}"
    return 0
  fi
  if command -v apt-get >/dev/null 2>&1; then
    pod_msg "Installing system packages (apt): ${pkgs[*]} python3-boto3"
    apt-get update -qq
    apt-get install -y "${pkgs[@]}" python3-boto3 2>/dev/null || apt-get install -y "${pkgs[@]}"
    return 0
  fi
  return 0
}

install_python_requirements() {
  ensure_pip || { pod_err "Could not install pip."; return 1; }

  if [[ -f "$POD_REQUIREMENTS" ]]; then
    pod_msg "Installing Python packages from requirements.txt ..."
    "$POD_PY" -m pip install --user -r "$POD_REQUIREMENTS"
  else
    pod_msg "Installing boto3 ..."
    "$POD_PY" -m pip install --user "boto3>=1.35.0"
  fi

  if "$POD_PY" -c "import boto3" >/dev/null 2>&1; then
    pod_msg "boto3 OK ($("$POD_PY" -c 'import boto3; print(boto3.__version__)'))"
    return 0
  fi

  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    if command -v dnf >/dev/null 2>&1; then dnf install -y python3-boto3; fi
    if command -v yum >/dev/null 2>&1; then yum install -y python3-boto3; fi
    if command -v apt-get >/dev/null 2>&1; then apt-get install -y python3-boto3; fi
  fi

  if "$POD_PY" -c "import boto3" >/dev/null 2>&1; then
    pod_msg "boto3 OK (system package)"
    return 0
  fi

  pod_err "boto3 is required for Route53 traffic migration."
  return 1
}

check_kubectl() {
  if command -v kubectl >/dev/null 2>&1; then
    pod_msg "kubectl: $(kubectl version --client --short 2>/dev/null || kubectl version --client 2>/dev/null | head -1)"
    return 0
  fi
  pod_warn "kubectl not found — cluster features (pods, nodes, deployments) will not work."
  pod_warn "Install: https://kubernetes.io/docs/tasks/tools/install-kubectl-linux/"
  return 1
}

ensure_kubectl() {
  pod_lib_init
  local bin="${POD_ROOT}/bin"
  mkdir -p "$bin"

  if [[ -n "${POD_KUBECTL:-}" && -x "$POD_KUBECTL" ]]; then
    export PATH="$(dirname "$POD_KUBECTL"):${PATH}"
    pod_msg "kubectl (POD_KUBECTL): $POD_KUBECTL"
    return 0
  fi

  if command -v kubectl >/dev/null 2>&1; then
    pod_msg "kubectl: $(command -v kubectl)"
    return 0
  fi

  local dest="$bin/kubectl"
  if [[ -x "$dest" ]]; then
    export POD_KUBECTL="$dest"
    export PATH="$bin:${PATH}"
    pod_msg "kubectl (bundled): $dest"
    return 0
  fi

  local arch os ver url
  arch="$(uname -m 2>/dev/null || echo amd64)"
  case "$arch" in
    x86_64|amd64) arch=amd64 ;;
    aarch64|arm64) arch=arm64 ;;
    *)
      pod_warn "Unsupported CPU arch for auto kubectl install: $arch"
      return 1
      ;;
  esac
  os=linux
  [[ "$(uname -s 2>/dev/null)" == "Darwin" ]] && os=darwin

  ver="$(curl -fsSL --connect-timeout 15 https://dl.k8s.io/release/stable.txt 2>/dev/null || echo v1.30.4)"
  url="https://dl.k8s.io/release/${ver}/bin/${os}/${arch}/kubectl"
  pod_msg "Downloading kubectl ${ver} for ${os}/${arch} ..."
  if curl -fsSL --connect-timeout 120 "$url" -o "$dest"; then
    chmod +x "$dest"
    export POD_KUBECTL="$dest"
    export PATH="$bin:${PATH}"
    pod_msg "kubectl installed: $dest"
    return 0
  fi

  pod_warn "Could not download kubectl — set POD_KUBECTL or install kubectl on PATH."
  return 1
}

check_kubeconfig() {
  export KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
  if [[ -f "$KUBECONFIG" ]]; then
    pod_msg "KUBECONFIG: $KUBECONFIG"
    if command -v kubectl >/dev/null 2>&1; then
      if ctx="$(kubectl config current-context 2>/dev/null)"; then
        pod_msg "Current context: $ctx"
      else
        pod_warn "kubectl context not set — run: aws eks update-kubeconfig --region <region> --name <cluster>"
      fi
    fi
    return 0
  fi
  pod_warn "KUBECONFIG not found at $KUBECONFIG"
  pod_warn "Run: aws eks update-kubeconfig --region us-east-2 --name <cluster-name>"
  return 1
}

check_aws_credentials() {
  if command -v aws >/dev/null 2>&1; then
    if aws sts get-caller-identity >/dev/null 2>&1; then
      pod_msg "AWS credentials OK ($(aws sts get-caller-identity --query Account --output text 2>/dev/null))"
      return 0
    fi
  fi
  if "$POD_PY" -c "
import boto3
boto3.client('sts').get_caller_identity()
" >/dev/null 2>&1; then
    pod_msg "AWS credentials OK (boto3 STS)"
    return 0
  fi
  pod_warn "AWS credentials not detected — Route53 traffic migration needs IAM access."
  pod_warn "Use EC2 instance role, or: aws configure"
  return 1
}

check_pod_files() {
  local missing=0
  for f in pod-server.py dashboard.html route53_traffic.py service_versions.py \
           data/traffic_migration_hosts.json data/service_version_catalog.json; do
    if [[ ! -f "$POD_ROOT/$f" ]]; then
      pod_warn "Missing file: $f"
      missing=1
    fi
  done
  if [[ "$missing" -eq 0 ]]; then
    pod_msg "Application files OK"
    return 0
  fi
  return 1
}

verify_python_syntax() {
  pod_msg "Checking Python syntax ..."
  local f
  for f in pod-server.py route53_traffic.py service_versions.py service_hide.py version_cache.py; do
    [[ -f "$POD_ROOT/$f" ]] || continue
    "$POD_PY" -m py_compile "$POD_ROOT/$f" || return 1
  done
  pod_msg "Python syntax OK"
  return 0
}

install_all_prerequisites() {
  pod_lib_init
  pod_msg "=== Pod Dashboard prerequisite install ==="
  ensure_python3 || return 1
  install_system_packages || true
  install_python_requirements || return 1
  verify_python_syntax || return 1
  check_pod_files || true
  check_kubectl || true
  check_kubeconfig || true
  check_aws_credentials || true
  pod_msg "=== Prerequisites complete ==="
  return 0
}
