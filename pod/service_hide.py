"""Hide non-application service names from the All Services grid."""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path

_POD_DIR = Path(__file__).resolve().parent

_DEFAULT_EXACT = frozenset({
    "applicationautoscaling-chart",
    "argo-rollouts",
    "aws-cli",
    "aws-ebs-csi-driver",
    "aws-efs-csi-driver",
    "aws-load-balancer-controller",
    "aws-node",
    "datadog-agent",
    "eks",
    "eks-pod-identity-agent",
    "external-secrets",
    "external-secrets-cert-controller",
    "external-secrets-webhook",
    "keda-admission-webhooks",
    "keda-operator",
    "keda-operator-metrics-apiserver",
    "karpenter",
    "kubernetes-agent",
    "maxmind-pull",
    "operator",
    "prometheus",
    "splunk-otel-collector",
})
_DEFAULT_SUFFIXES = ("-chart",)
_DEFAULT_HIDDEN_NAMESPACES = frozenset({"kube-system"})


def _hide_config_path() -> Path:
    explicit = os.environ.get("POD_SERVICE_HIDE_FILE", "").strip()
    if explicit:
        return Path(explicit)
    return _POD_DIR / "data" / "service_hide_list.json"


def _parse_env_list() -> list[str]:
    raw = os.environ.get("POD_SERVICE_HIDE", "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
        except json.JSONDecodeError:
            pass
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_env_namespaces() -> list[str]:
    raw = os.environ.get("POD_HIDE_NAMESPACES", "").strip()
    if not raw:
        return []
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def load_hide_rules() -> dict[str, list[str]]:
    exact = set(_DEFAULT_EXACT)
    suffixes = list(_DEFAULT_SUFFIXES)
    prefixes: list[str] = []
    contains: list[str] = []
    patterns: list[str] = []
    hidden_namespaces = set(_DEFAULT_HIDDEN_NAMESPACES)

    path = _hide_config_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            exact.update(str(x).lower() for x in (data.get("exact") or []) if x)
            suffixes.extend(str(x) for x in (data.get("suffixes") or []) if x)
            prefixes.extend(str(x) for x in (data.get("prefixes") or []) if x)
            contains.extend(str(x) for x in (data.get("contains") or []) if x)
            hidden_namespaces.update(
                str(x).lower() for x in (data.get("hidden_namespaces") or []) if x
            )
            for item in data.get("hidden") or data.get("patterns") or []:
                if item:
                    patterns.append(str(item))
        except Exception:
            pass

    patterns.extend(_parse_env_list())
    hidden_namespaces.update(_parse_env_namespaces())

    return {
        "exact": sorted(exact),
        "suffixes": suffixes,
        "prefixes": prefixes,
        "contains": contains,
        "patterns": patterns,
        "hidden_namespaces": sorted(hidden_namespaces),
    }


def hidden_namespace_set() -> frozenset[str]:
    return frozenset(load_hide_rules().get("hidden_namespaces") or [])


def is_hidden_namespace(namespace: str) -> bool:
    return (namespace or "").strip().lower() in hidden_namespace_set()


def service_name_from_pod(pod: dict) -> str:
    labels = pod.get("metadata", {}).get("labels", {}) or {}
    for key in ("app.kubernetes.io/name", "app", "service", "k8s-app", "name"):
        value = labels.get(key)
        if value:
            return str(value)

    for owner in pod.get("metadata", {}).get("ownerReferences", []) or []:
        if owner.get("kind") == "ReplicaSet":
            rs_name = owner.get("name", "")
            parts = rs_name.rsplit("-", 1)
            if len(parts) == 2 and len(parts[1]) <= 12:
                return parts[0]

    pod_name = pod.get("metadata", {}).get("name", "unknown")
    parts = pod_name.rsplit("-", 2)
    if len(parts) >= 3:
        return parts[0]
    return pod_name


def should_hide_pod(pod: dict, rules: dict[str, list[str]] | None = None) -> bool:
    namespace = pod.get("metadata", {}).get("namespace", "default")
    if is_hidden_namespace(namespace):
        return True

    cfg = rules if rules is not None else load_hide_rules()
    service_name = service_name_from_pod(pod)
    if should_hide_service(service_name, cfg):
        return True

    pod_name = (pod.get("metadata", {}).get("name") or "").strip().lower()
    if pod_name:
        for exact in cfg.get("exact") or []:
            ex = str(exact).lower()
            if pod_name == ex or pod_name.startswith(ex + "-"):
                return True

    return False


def should_hide_service(name: str, rules: dict[str, list[str]] | None = None) -> bool:
    sid = (name or "").strip().lower()
    if not sid:
        return True

    cfg = rules if rules is not None else load_hide_rules()

    if sid in {x.lower() for x in cfg.get("exact") or []}:
        return True

    for suffix in cfg.get("suffixes") or []:
        if sid.endswith(str(suffix).lower()):
            return True

    for prefix in cfg.get("prefixes") or []:
        if sid.startswith(str(prefix).lower()):
            return True

    for needle in cfg.get("contains") or []:
        if str(needle).lower() in sid:
            return True

    for pattern in cfg.get("patterns") or []:
        if fnmatch.fnmatch(sid, str(pattern).lower()):
            return True

    return False


def filter_services(services: list[dict]) -> list[dict]:
    rules = load_hide_rules()
    hidden_ns = set(rules.get("hidden_namespaces") or [])
    out: list[dict] = []
    for svc in services:
        sid = str(svc.get("id") or svc.get("name") or "")
        if should_hide_service(sid, rules):
            continue
        namespaces = [str(n).lower() for n in (svc.get("namespaces") or [])]
        if namespaces and all(ns in hidden_ns for ns in namespaces):
            continue
        out.append(svc)
    return out
