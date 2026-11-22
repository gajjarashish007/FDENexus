"""kubectl runner with per-cluster isolation.

Every call is `kubectl --kubeconfig <file-for-this-cluster> [--context <ctx>] ...` with an argv list
(no shell), so two users on two clusters never share or switch a global context (the old pod
server's main bug). User-supplied names are validated before they reach kubectl, and every
positional name follows a fixed flag so it cannot be read as a flag.

Cluster sources
  eks         Amazon EKS in a connected AWS account. A kubeconfig is generated from
              eks:DescribeCluster; `aws eks get-token` runs with that account's temporary
              credentials (AssumeRole + external ID handled by M01), passed as env vars.
  kubeconfig  A context in the portal host's kubeconfig (any conformant cluster, kind, k3s...).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

KUBECTL = os.environ.get("M04_KUBECTL") or shutil.which("kubectl") or "kubectl"
AWS_CLI = shutil.which("aws")
NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")     # DNS-1123 subdomain
NS_RE = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")         # DNS-1123 label
CONTEXT_RE = re.compile(r"^[A-Za-z0-9:/@._-]{1,250}$")
KINDS = {
    "pods": "pods", "deployments": "deployments", "statefulsets": "statefulsets", "daemonsets": "daemonsets",
    "services": "services", "ingresses": "ingresses", "configmaps": "configmaps", "hpa": "horizontalpodautoscalers",
    "pvc": "persistentvolumeclaims", "cronjobs": "cronjobs", "jobs": "jobs", "nodes": "nodes", "namespaces": "namespaces",
    "events": "events", "resourcequotas": "resourcequotas", "storageclasses": "storageclasses", "pv": "persistentvolumes",
    "rolebindings": "rolebindings", "clusterrolebindings": "clusterrolebindings", "networkpolicies": "networkpolicies",
    "limitranges": "limitranges",
}
DESCRIBE_KINDS = {"pod", "deployment", "statefulset", "daemonset", "service", "ingress", "configmap", "hpa", "pvc", "node",
                  "cronjob", "job", "namespace", "rolebinding", "clusterrolebinding", "networkpolicy", "resourcequota", "limitrange",
                  "storageclass", "pv"}
CLUSTER_SCOPED = {"node", "namespace", "nodes", "namespaces", "storageclass", "storageclasses", "pv", "clusterrolebinding", "clusterrolebindings"}


class KubeError(Exception):
    pass


def check_name(value: str, what: str = "name") -> str:
    v = str(value or "")
    if not NAME_RE.match(v):
        raise KubeError(f"Invalid {what}: lowercase letters, digits, '-' and '.' only.")
    return v


def check_ns(value: str) -> str:
    v = str(value or "")
    if not NS_RE.match(v):
        raise KubeError("Invalid namespace.")
    return v


class ClusterTarget:
    """Resolved connection info for one cluster record."""

    _creds_cache: dict[str, tuple[float, dict]] = {}
    _lock = threading.Lock()

    def __init__(self, cluster: dict, account: dict | None, data_dir: Path, session_factory):
        self.c = cluster
        self.account = account
        self.data_dir = data_dir
        self.session_factory = session_factory

    # -------- credentials and kubeconfig
    def _aws_env(self) -> dict:
        if not self.account:
            raise KubeError("The AWS account for this cluster is not registered.")
        key = self.account["id"]
        with self._lock:
            hit = self._creds_cache.get(key)
            if hit and hit[0] > time.time():
                return hit[1]
        try:
            fc = self.session_factory(self.account).get_credentials().get_frozen_credentials()
        except Exception as e:  # botocore errors
            raise KubeError(f"Cannot get AWS credentials for account {key}: {str(e)[:200]}") from None
        env = {"AWS_ACCESS_KEY_ID": fc.access_key, "AWS_SECRET_ACCESS_KEY": fc.secret_key, "AWS_REGION": self.c["region"]}
        if fc.token:
            env["AWS_SESSION_TOKEN"] = fc.token
        env.pop("AWS_PROFILE", None)
        with self._lock:
            self._creds_cache[key] = (time.time() + 40 * 60, env)  # role sessions last 60 min
        return env

    def _eks_kubeconfig(self) -> Path:
        path = self.data_dir / f"{self.c['id']}.kubeconfig"
        if path.exists() and time.time() - path.stat().st_mtime < 3600:
            return path
        if not AWS_CLI:
            raise KubeError("The aws CLI is required on the portal host to authenticate to EKS (aws eks get-token).")
        try:
            eks = self.session_factory(self.account).client("eks", region_name=self.c["region"])
            d = eks.describe_cluster(name=self.c["name"])["cluster"]
        except Exception as e:
            raise KubeError(f"eks:DescribeCluster failed for {self.c['name']}: {str(e)[:200]}") from None
        if d.get("status") != "ACTIVE":
            raise KubeError(f"Cluster {self.c['name']} is {d.get('status')}.")
        cfg = {
            "apiVersion": "v1", "kind": "Config", "current-context": "eks",
            "clusters": [{"name": "eks", "cluster": {"server": d["endpoint"], "certificate-authority-data": d["certificateAuthority"]["data"]}}],
            "contexts": [{"name": "eks", "context": {"cluster": "eks", "user": "eks"}}],
            "users": [{"name": "eks", "user": {"exec": {
                "apiVersion": "client.authentication.k8s.io/v1beta1", "command": AWS_CLI, "interactiveMode": "Never",
                "args": ["--region", self.c["region"], "eks", "get-token", "--cluster-name", self.c["name"], "--output", "json"]}}}],
        }
        self.data_dir.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(cfg))
        os.chmod(tmp, 0o600)
        tmp.replace(path)
        return path

    def base_args(self) -> tuple[list[str], dict]:
        env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")} | {"NO_COLOR": "1"}
        if self.c["source"] == "eks":
            env |= self._aws_env()
            return [KUBECTL, "--kubeconfig", str(self._eks_kubeconfig())], env
        if self.c["source"] == "kubeconfig":
            ctx = self.c.get("context") or ""
            if not CONTEXT_RE.match(ctx):
                raise KubeError("Invalid kubeconfig context.")
            env |= {k: v for k, v in os.environ.items() if k.startswith("AWS_")}  # host creds for exec plugins
            return [KUBECTL, "--context", ctx], env
        raise KubeError(f"Unsupported cluster source {self.c['source']}.")

    # -------- run
    def run(self, args: list[str], timeout: int = 30, stdin: str | None = None) -> subprocess.CompletedProcess:
        base, env = self.base_args()
        cmd = base + [f"--request-timeout={min(timeout, 60)}s"] + args
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5, env=env, input=stdin)
        except subprocess.TimeoutExpired:
            raise KubeError(f"kubectl timed out after {timeout}s") from None
        except FileNotFoundError:
            raise KubeError("kubectl is not installed on the portal host (brew install kubectl / set M04_KUBECTL).") from None

    def text(self, args: list[str], timeout: int = 30) -> str:
        r = self.run(args, timeout)
        if r.returncode != 0:
            raise KubeError(_clean_err(r.stderr or r.stdout))
        return r.stdout

    def json(self, args: list[str], timeout: int = 45) -> dict:
        out = self.text(args + ["-o", "json"], timeout)
        try:
            return json.loads(out or "{}")
        except ValueError:
            raise KubeError("kubectl returned invalid JSON.") from None


def _clean_err(s: str) -> str:
    s = (s or "kubectl failed").strip()
    s = re.sub(r"(?i)(token|password|secret)[=:]\S+", r"\1=***", s)
    return s[-800:]


def kubeconfig_contexts() -> list[str]:
    try:
        r = subprocess.run([KUBECTL, "config", "get-contexts", "-o", "name"], capture_output=True, text=True, timeout=10)
        return [x.strip() for x in r.stdout.splitlines() if x.strip()] if r.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        return []
