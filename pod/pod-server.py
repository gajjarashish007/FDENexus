#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import json
import os
import re
import shutil
import threading
import time
from typing import Any, Optional
from urllib.parse import quote
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

from service_versions import (
    _is_arloxcld_url,
    _is_configured_version_url,
    _resolve_version_service_id,
    catalog_service_meta,
    fetch_version_api_detail,
    get_version_aliases,
    get_version_overrides,
    list_version_catalog_entries,
    load_catalog,
    resolve_version_environment,
)
import version_cache
from service_hide import (
    filter_services,
    is_hidden_namespace,
    load_hide_rules,
    service_name_from_pod,
    should_hide_pod,
)
from route53_traffic import fetch_traffic_migration
import pod_auth
import pod_rbac
import pod_clusters
import pod_cache
import pod_singleton
import validator_integration

_POD_DIR = os.path.dirname(os.path.abspath(__file__))

_DEFAULT_EKS_REGIONS = (
    "us-east-2",
    "us-east-1",
    "us-west-2",
    "us-west-1",
    "eu-west-1",
    "eu-west-3",
    "ap-southeast-1",
    "ap-southeast-2",
)

_DEFAULT_AWS_REGION = "us-east-2"

_ACTIVE_CLUSTER: dict[str, str] = {}
_ACTIVE_CLUSTER_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "active_cluster.json")


def _persist_active_cluster() -> None:
    if not (_ACTIVE_CLUSTER.get("name") or "").strip():
        return
    try:
        os.makedirs(os.path.dirname(_ACTIVE_CLUSTER_FILE), exist_ok=True)
        with open(_ACTIVE_CLUSTER_FILE, "w", encoding="utf-8") as fh:
            json.dump(_ACTIVE_CLUSTER, fh)
            fh.write("\n")
    except OSError:
        pass


def _load_persisted_active_cluster() -> None:
    global _ACTIVE_CLUSTER
    try:
        with open(_ACTIVE_CLUSTER_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return
        name = (data.get("name") or "").strip()
        if not name:
            return
        _ACTIVE_CLUSTER = {
            "name": name,
            "region": (data.get("region") or _DEFAULT_AWS_REGION).strip(),
            "roleArn": (data.get("roleArn") or data.get("role_arn") or "").strip(),
        }
    except (OSError, json.JSONDecodeError, TypeError):
        pass


def _ensure_active_cluster_context() -> Optional[str]:
    """Ensure kubectl points at the remembered portal cluster. Returns error text or None."""
    if not (_ACTIVE_CLUSTER.get("name") or "").strip():
        _load_persisted_active_cluster()
    name = (_ACTIVE_CLUSTER.get("name") or "").strip()
    if not name:
        return None
    region = (_ACTIVE_CLUSTER.get("region") or _DEFAULT_AWS_REGION).strip()
    role = (_ACTIVE_CLUSTER.get("roleArn") or "").strip()
    if not role:
        role = _resolve_cluster_role_arn(name)
    ctx = _current_kubectl_context()
    if _parse_cluster_from_context(ctx) == name:
        probe = _run_cmd(
            ["kubectl", "get", "namespaces", "-o", "name", "--request-timeout=5s"],
            timeout=15,
        )
        if probe.returncode == 0:
            return None
    return _switch_eks_cluster(name, region, role_arn=role or None)


def _remember_active_cluster(name: str, region: str, role_arn: str = "") -> None:
    global _ACTIVE_CLUSTER
    _ACTIVE_CLUSTER = {
        "name": (name or "").strip(),
        "region": (region or _DEFAULT_AWS_REGION).strip(),
        "roleArn": (role_arn or "").strip(),
    }
    _persist_active_cluster()


def _current_kubectl_context() -> str:
    try:
        result = _run_cmd(["kubectl", "config", "current-context"], timeout=10)
        if result.returncode == 0:
            return (result.stdout or "").strip()
    except Exception:
        pass
    return ""


def _display_cluster_name() -> str:
    parsed = _parse_cluster_from_context(_current_kubectl_context())
    if parsed and parsed != "Unknown Cluster":
        return parsed
    remembered = (_ACTIVE_CLUSTER.get("name") or "").strip()
    return remembered or "Unknown Cluster"


def _kubeconfig_path() -> str:
    return os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))


def _eks_scan_regions() -> list[str]:
    raw = os.environ.get("POD_EKS_REGIONS", "").strip()
    if raw:
        return [r.strip() for r in raw.split(",") if r.strip()]
    primary = os.environ.get("POD_AWS_REGION", _DEFAULT_AWS_REGION).strip()
    regions = list(_DEFAULT_EKS_REGIONS)
    if primary and primary not in regions:
        regions.insert(0, primary)
    elif primary:
        regions = [primary] + [r for r in regions if r != primary]
    return regions


def _cluster_prefix_filter() -> str:
    return os.environ.get("POD_EKS_CLUSTER_PREFIX", "").strip()


def _parse_cluster_from_context(context: str) -> str:
    context = (context or "").strip()
    if not context:
        return "Unknown Cluster"
    if "cluster/" in context:
        return context.split("cluster/")[-1]
    if "/" in context:
        return context.split("/")[-1]
    return context


def _region_from_context(context: str) -> str:
    context = (context or "").strip()
    parts = context.split(":")
    if len(parts) >= 4 and parts[0] == "arn" and parts[2] == "eks":
        return parts[3]
    return ""


def _html_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def _kubectl_bin() -> str:
    explicit = (os.environ.get("POD_KUBECTL") or "").strip()
    if explicit:
        return explicit
    found = shutil.which("kubectl")
    if found:
        return found
    for candidate in (
        "/usr/local/bin/kubectl",
        "/usr/bin/kubectl",
        os.path.expanduser("~/bin/kubectl"),
    ):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return "kubectl"


def _run_cmd(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["KUBECONFIG"] = _kubeconfig_path()
    path = env.get("PATH") or ""
    for extra in ("/usr/local/bin", "/usr/bin", os.path.expanduser("~/bin")):
        if extra not in path.split(":"):
            path = f"{extra}:{path}"
    env["PATH"] = path
    cmd = list(args)
    if cmd and cmd[0] == "kubectl":
        cmd[0] = _kubectl_bin()
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)


def _switch_eks_cluster(name: str, region: str, role_arn: Optional[str] = None) -> Optional[str]:
    """Point kubectl at an EKS cluster. Returns error text or None."""
    cluster_name = (name or "").strip()
    cluster_region = (region or os.environ.get("POD_AWS_REGION", _DEFAULT_AWS_REGION)).strip()
    if not cluster_name:
        return "Cluster name is required"
    kb = _kubectl_bin()
    if kb == "kubectl" and not shutil.which("kubectl"):
        return (
            "kubectl not found in PATH. Install kubectl on the pod server host "
            "(see pod/README.md) or set POD_KUBECTL to the binary path."
        )
    if kb != "kubectl" and not os.path.isfile(kb):
        return f"kubectl not found at {kb}"
    cmd = [
        'aws', 'eks', 'update-kubeconfig',
        '--name', cluster_name,
        '--region', cluster_region,
        '--alias', cluster_name,
    ]
    role = (role_arn or "").strip()
    if role:
        cmd.extend(['--role-arn', role])
    update = _run_cmd(cmd, timeout=60)
    if update.returncode != 0:
        return (update.stderr or update.stdout or "update-kubeconfig failed").strip()[:500]
    use_ctx = _run_cmd(['kubectl', 'config', 'use-context', cluster_name], timeout=15)
    if use_ctx.returncode != 0:
        return (use_ctx.stderr or use_ctx.stdout or "use-context failed").strip()[:500]
    return None


def _resolve_cluster_role_arn(name: str, role_arn_from_request: Optional[str] = None) -> str:
    role_arn = (role_arn_from_request or "").strip()
    if role_arn:
        return role_arn
    reg = pod_clusters.get_registry_cluster_by_name(name)
    if reg:
        return (reg.get("roleArn") or "").strip()
    return ""


def _use_kubectl_context(context: str) -> None:
    ctx = (context or "").strip()
    if not ctx:
        return
    try:
        _run_cmd(['kubectl', 'config', 'use-context', ctx], timeout=15)
    except Exception:
        pass


def _pod_is_running(pod: dict) -> bool:
    phase = pod.get("status", {}).get("phase", "")
    if phase != "Running":
        return False
    containers = pod.get("status", {}).get("containerStatuses", []) or []
    if not containers:
        return True
    return all(
        cs.get("ready") and "running" in (cs.get("state") or {})
        for cs in containers
    )


def _pod_is_stale(pod: dict) -> bool:
    """Pods that finished (Job/batch) or were terminated during rollout."""
    return pod.get("status", {}).get("phase", "") in ("Succeeded", "Failed")


def _pod_ready_counts(pod: dict) -> tuple[int, int]:
    container_statuses = pod.get("status", {}).get("containerStatuses", []) or []
    spec_containers = pod.get("spec", {}).get("containers", []) or []
    total = max(len(container_statuses), len(spec_containers))
    if _pod_is_stale(pod):
        return 0, total

    ready = 0
    for cs in container_statuses:
        state = cs.get("state") or {}
        if cs.get("ready") and "running" in state:
            ready += 1
    return ready, total


_WAITING_STATUS_REASONS = frozenset({
    "CrashLoopBackOff",
    "ImagePullBackOff",
    "ContainerCreating",
    "ErrImagePull",
    "PodInitializing",
    "CreateContainerConfigError",
    "CreateContainerError",
})


def _pod_display_status(pod: dict) -> str:
    """Match kubectl-style STATUS: phase first, then main-container waiting reasons."""
    phase = pod.get("status", {}).get("phase", "Unknown")
    if phase == "Succeeded":
        return "Completed"

    container_statuses = pod.get("status", {}).get("containerStatuses", []) or []
    init_statuses = pod.get("status", {}).get("initContainerStatuses", []) or []

    for cs in container_statuses:
        state = cs.get("state") or {}
        if "waiting" in state:
            reason = state["waiting"].get("reason", "")
            if reason in _WAITING_STATUS_REASONS:
                return reason
        if "terminated" in state and phase not in ("Succeeded", "Failed"):
            reason = state["terminated"].get("reason", "")
            if reason in ("CrashLoopBackOff", "Error", "OOMKilled", "Evicted"):
                return reason
            if reason == "Completed" and phase != "Running":
                return "Completed"

    if phase == "Pending" and init_statuses:
        for cs in init_statuses:
            state = cs.get("state") or {}
            if "waiting" in state:
                reason = state["waiting"].get("reason", "")
                if reason:
                    return reason

    return phase


def _pod_effective_status(pod: dict) -> str:
    return _pod_display_status(pod)


def _pod_status_class(status: str, ready_count: int, total_containers: int, phase: str = "") -> str:
    error_statuses = frozenset({
        "CrashLoopBackOff", "ImagePullBackOff", "Error", "Failed", "Terminated",
        "ErrImagePull", "Evicted", "OOMKilled",
        "CreateContainerConfigError", "CreateContainerError",
    })
    pending_statuses = frozenset({
        "Pending", "ContainerCreating", "PodInitializing",
    })

    if status == "Running" and ready_count == total_containers and total_containers > 0:
        return "status-running"
    if status in error_statuses:
        return "status-error"
    if status == "Completed" or phase == "Succeeded":
        return "status-completed"
    if phase == "Pending":
        return "status-pending"
    if status in pending_statuses:
        return "status-pending"
    # Running phase but containers not ready yet (e.g. 0/1)
    if phase == "Running" and total_containers > 0 and ready_count < total_containers:
        return "status-pending"
    # Init / scheduling / other transitional waiting reasons
    if status in _WAITING_STATUS_REASONS and status not in error_statuses:
        return "status-pending"
    return ""


def _aggregate_pod_stats(items: list) -> dict:
    """Pod counts for overview — same visibility rules as /api/pods."""
    stats = {
        "cluster_total": len(items),
        "hidden": 0,
        "visible_total": 0,
        "running": 0,
        "errors": 0,
        "pending": 0,
        "completed": 0,
        "other": 0,
    }
    for item in items:
        if should_hide_pod(item):
            stats["hidden"] += 1
            continue
        stats["visible_total"] += 1
        summary = _pod_to_summary(item)
        status_class = summary["statusClass"]
        if status_class == "status-running":
            stats["running"] += 1
        elif status_class == "status-error":
            stats["errors"] += 1
        elif status_class == "status-pending":
            stats["pending"] += 1
        elif status_class == "status-completed":
            stats["completed"] += 1
        else:
            stats["other"] += 1
    accounted = (
        stats["running"] + stats["errors"] + stats["pending"]
        + stats["completed"] + stats["other"]
    )
    stats["validated"] = accounted == stats["visible_total"]
    return stats


def _pod_restart_count(pod: dict) -> int:
    all_statuses = (pod.get("status", {}).get("containerStatuses", []) or []) + (
        pod.get("status", {}).get("initContainerStatuses", []) or []
    )
    return sum(cs.get("restartCount", 0) for cs in all_statuses)


def _pod_to_summary(pod: dict) -> dict:
    namespace = pod["metadata"]["namespace"]
    name = pod["metadata"]["name"]
    ready_count, total_containers = _pod_ready_counts(pod)
    ready = f"{ready_count}/{total_containers}" if total_containers else "0/0"
    phase = pod.get("status", {}).get("phase", "")
    actual_status = _pod_display_status(pod)
    status_class = _pod_status_class(actual_status, ready_count, total_containers, phase)
    display_status = actual_status
    if status_class == "status-pending" and actual_status == "Running":
        display_status = "Pending"
    return {
        "name": name,
        "namespace": namespace,
        "ready": ready,
        "readyCount": ready_count,
        "totalContainers": total_containers,
        "phase": phase,
        "status": display_status,
        "statusClass": status_class,
        "restarts": _pod_restart_count(pod),
        "age": pod["metadata"].get("creationTimestamp", "N/A"),
        "ip": pod.get("status", {}).get("podIP", "N/A"),
        "node": pod.get("spec", {}).get("nodeName", ""),
        "containers": [c.get("name", "") for c in pod.get("spec", {}).get("containers", []) or []],
        "labels": pod["metadata"].get("labels", {}),
    }


def _node_display_status(node: dict) -> str:
    if node.get("spec", {}).get("unschedulable"):
        return "SchedulingDisabled"
    for cond in node.get("status", {}).get("conditions", []) or []:
        if cond.get("type") == "Ready":
            return "Ready" if cond.get("status") == "True" else "NotReady"
    return "Unknown"


def _node_roles(node: dict) -> str:
    labels = node.get("metadata", {}).get("labels", {}) or {}
    roles = []
    for key in labels:
        if key.startswith("node-role.kubernetes.io/"):
            roles.append(key.split("/", 1)[-1])
    return ",".join(roles) if roles else "worker"


def _node_address(node: dict, addr_type: str) -> str:
    for addr in node.get("status", {}).get("addresses", []) or []:
        if addr.get("type") == addr_type:
            return addr.get("address", "N/A")
    return "N/A"


def _node_to_summary(node: dict) -> dict:
    meta = node.get("metadata", {})
    status = _node_display_status(node)
    node_info = node.get("status", {}).get("nodeInfo", {}) or {}
    return {
        "name": meta.get("name", ""),
        "status": status,
        "roles": _node_roles(node),
        "age": meta.get("creationTimestamp", "N/A"),
        "version": node_info.get("kubeletVersion", "N/A"),
        "internalIp": _node_address(node, "InternalIP"),
        "externalIp": _node_address(node, "ExternalIP"),
        "os": node_info.get("osImage", "N/A"),
        "containerRuntime": node_info.get("containerRuntimeVersion", "N/A"),
    }


def _deployment_to_summary(item: dict) -> dict:
    meta = item.get("metadata", {})
    spec = item.get("spec", {}) or {}
    status = item.get("status", {}) or {}
    replicas = spec.get("replicas", 0) or 0
    ready = status.get("readyReplicas", 0) or 0
    return {
        "name": meta.get("name", ""),
        "namespace": meta.get("namespace", "default"),
        "ready": f"{ready}/{replicas}",
        "readyReplicas": ready,
        "replicas": replicas,
        "upToDate": status.get("updatedReplicas", 0) or 0,
        "available": status.get("availableReplicas", 0) or 0,
        "age": meta.get("creationTimestamp", "N/A"),
    }


def _aggregate_services_from_pods(pods_data: dict) -> list[dict]:
    services: dict[str, dict] = {}

    for pod in pods_data.get("items", []):
        namespace = pod.get("metadata", {}).get("namespace", "default")
        if is_hidden_namespace(namespace):
            continue
        if _pod_is_stale(pod):
            continue
        service_name = _resolve_version_service_id(service_name_from_pod(pod))
        status = _pod_effective_status(pod)

        rec = services.setdefault(
            service_name,
            {
                "id": service_name,
                "name": service_name,
                "running": 0,
                "total": 0,
                "pending": 0,
                "failed": 0,
                "namespaces": set(),
            },
        )
        rec["total"] += 1
        rec["namespaces"].add(namespace)

        if _pod_is_running(pod):
            rec["running"] += 1
        elif status in ("Pending", "ContainerCreating"):
            rec["pending"] += 1
        else:
            rec["failed"] += 1

    result: list[dict] = []
    for service_name in sorted(services):
        rec = services[service_name]
        if rec["running"] > 0 and rec["failed"] == 0:
            run_state = "deployed"
        elif rec["failed"] > 0 and rec["running"] == 0:
            run_state = "failed"
        elif rec["pending"] > 0:
            run_state = "running"
        elif rec["total"] == 0:
            run_state = "idle"
        else:
            run_state = "idle"
        result.append({
            "id": rec["id"],
            "name": rec["name"],
            "running": rec["running"],
            "total": rec["total"],
            "pending": rec["pending"],
            "failed": rec["failed"],
            "namespaces": sorted(rec["namespaces"]),
            "runState": run_state,
        })
    return result


_SERVICE_PODS_CACHE: dict = {"at": 0.0, "payload": None, "refreshing": False, "lock": threading.Lock()}

_PODS_CACHE: dict = {
    "at": 0.0,
    "cluster": "",
    "pods": None,
    "error": None,
    "refreshing": False,
    "lock": threading.Lock(),
}
_CLUSTER_PODS_STORE: dict[str, dict] = {}
_CLUSTER_PODS_LOCK = threading.Lock()
_PODS_KUBECTL_TIMEOUT = int(os.environ.get("POD_PODS_KUBECTL_TIMEOUT", "120"))

_DEPLOYMENTS_CACHE: dict = {
    "at": 0.0,
    "cluster": "",
    "items": None,
    "error": None,
    "refreshing": False,
    "lock": threading.Lock(),
}
_NODES_CACHE: dict = {
    "at": 0.0,
    "cluster": "",
    "items": None,
    "error": None,
    "refreshing": False,
    "lock": threading.Lock(),
}


def _invalidate_resource_caches() -> None:
    pod_cache.invalidate_html_and_meta()
    with _SERVICE_PODS_CACHE["lock"]:
        _SERVICE_PODS_CACHE["payload"] = None
        _SERVICE_PODS_CACHE["at"] = 0.0
        _SERVICE_PODS_CACHE["refreshing"] = False
    with _PODS_CACHE["lock"]:
        _PODS_CACHE["at"] = 0.0
        _PODS_CACHE["cluster"] = ""
        _PODS_CACHE["pods"] = None
        _PODS_CACHE["error"] = None
        _PODS_CACHE["refreshing"] = False
    with _DEPLOYMENTS_CACHE["lock"]:
        _DEPLOYMENTS_CACHE["at"] = 0.0
        _DEPLOYMENTS_CACHE["cluster"] = ""
        _DEPLOYMENTS_CACHE["items"] = None
        _DEPLOYMENTS_CACHE["error"] = None
        _DEPLOYMENTS_CACHE["refreshing"] = False
    with _NODES_CACHE["lock"]:
        _NODES_CACHE["at"] = 0.0
        _NODES_CACHE["cluster"] = ""
        _NODES_CACHE["items"] = None
        _NODES_CACHE["error"] = None
        _NODES_CACHE["refreshing"] = False
    with _CLUSTER_PODS_LOCK:
        _CLUSTER_PODS_STORE.clear()


def _fetch_all_pod_summaries(timeout: Optional[int] = None) -> tuple[list[dict], Optional[str]]:
    ctx_err = _ensure_active_cluster_context()
    if ctx_err:
        return [], ctx_err
    timeout = timeout if timeout is not None else _PODS_KUBECTL_TIMEOUT
    try:
        result = _run_cmd(['kubectl', 'get', 'pods', '--all-namespaces', '-o', 'json'], timeout=timeout)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "kubectl command failed").strip()
            return [], err
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        return [], f"Invalid kubectl JSON output: {exc}"
    except Exception as exc:
        return [], str(exc)
    pods = []
    for item in data.get('items', []):
        if should_hide_pod(item):
            continue
        pods.append(_pod_to_summary(item))
    return pods, None


def _refresh_pods_cache(cluster: str, *, timeout: Optional[int] = None) -> tuple[list[dict], Optional[str]]:
    pods, err = _fetch_all_pod_summaries(timeout=timeout)
    with _PODS_CACHE["lock"]:
        if not err:
            _PODS_CACHE["at"] = time.time()
            _PODS_CACHE["cluster"] = cluster
            _PODS_CACHE["pods"] = pods
            _PODS_CACHE["error"] = None
        else:
            _PODS_CACHE["error"] = err
        _PODS_CACHE["refreshing"] = False
    with _CLUSTER_PODS_LOCK:
        _CLUSTER_PODS_STORE[cluster] = {
            "at": time.time(),
            "pods": list(pods) if not err else None,
            "error": err,
        }
    return pods, err


def _stored_pods_for_cluster(cluster: str, *, force_refresh: bool = False) -> tuple[list[dict], Optional[str], bool, int]:
    """Return pods for cluster (kubectl context must already match). Uses per-cluster store."""
    now = time.time()
    if not force_refresh:
        with _CLUSTER_PODS_LOCK:
            entry = _CLUSTER_PODS_STORE.get(cluster)
            if entry and entry.get("pods") is not None:
                age = now - float(entry.get("at") or 0)
                if age < pod_cache.pods_ttl():
                    return list(entry["pods"]), entry.get("error"), True, int(age)
    pods, err = _refresh_pods_cache(cluster)
    return pods, err, False, 0


def _resolve_cluster_list(clusters: list) -> list[dict]:
    resolved: list[dict] = []
    if isinstance(clusters, list):
        for item in clusters:
            if not isinstance(item, dict):
                continue
            name = (item.get("name") or "").strip()
            if not name:
                continue
            region = (item.get("region") or os.environ.get("POD_AWS_REGION", _DEFAULT_AWS_REGION)).strip()
            role_arn = _resolve_cluster_role_arn(name, item.get("roleArn") or item.get("role_arn"))
            resolved.append({"name": name, "region": region, "roleArn": role_arn})
    return resolved


def _background_refresh_pods(cluster: str) -> None:
    try:
        _refresh_pods_cache(cluster)
    except Exception as exc:
        with _PODS_CACHE["lock"]:
            _PODS_CACHE["error"] = str(exc)
            _PODS_CACHE["refreshing"] = False


def _kubectl_json(args: list[str], timeout: int = 45) -> tuple[Optional[dict], Optional[str]]:
    ctx_err = _ensure_active_cluster_context()
    if ctx_err:
        return None, ctx_err
    try:
        result = _run_cmd(['kubectl'] + args, timeout=timeout)
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "kubectl command failed").strip()
            return None, err
        return json.loads(result.stdout or "{}"), None
    except json.JSONDecodeError as exc:
        return None, f"Invalid kubectl JSON output: {exc}"
    except Exception as exc:
        return None, str(exc)


def _fetch_all_deployments() -> tuple[list[dict], Optional[str]]:
    data, err = _kubectl_json(['get', 'deployments', '--all-namespaces', '-o', 'json'])
    if err:
        return [], err
    return [_deployment_to_summary(item) for item in data.get('items', [])], None


def _fetch_all_nodes() -> tuple[list[dict], Optional[str]]:
    data, err = _kubectl_json(['get', 'nodes', '-o', 'json'], timeout=45)
    if err:
        return [], err
    return [_node_to_summary(item) for item in data.get('items', [])], None


def _refresh_deployments_cache(cluster: str) -> tuple[list[dict], Optional[str]]:
    items, err = _fetch_all_deployments()
    with _DEPLOYMENTS_CACHE["lock"]:
        if not err:
            _DEPLOYMENTS_CACHE["at"] = time.time()
            _DEPLOYMENTS_CACHE["cluster"] = cluster
            _DEPLOYMENTS_CACHE["items"] = items
            _DEPLOYMENTS_CACHE["error"] = None
        else:
            _DEPLOYMENTS_CACHE["error"] = err
        _DEPLOYMENTS_CACHE["refreshing"] = False
    return items, err


def _refresh_nodes_cache(cluster: str) -> tuple[list[dict], Optional[str]]:
    items, err = _fetch_all_nodes()
    with _NODES_CACHE["lock"]:
        if not err:
            _NODES_CACHE["at"] = time.time()
            _NODES_CACHE["cluster"] = cluster
            _NODES_CACHE["items"] = items
            _NODES_CACHE["error"] = None
        else:
            _NODES_CACHE["error"] = err
        _NODES_CACHE["refreshing"] = False
    return items, err


def _background_refresh_deployments(cluster: str) -> None:
    try:
        _refresh_deployments_cache(cluster)
    except Exception as exc:
        with _DEPLOYMENTS_CACHE["lock"]:
            _DEPLOYMENTS_CACHE["error"] = str(exc)
            _DEPLOYMENTS_CACHE["refreshing"] = False


def _background_refresh_nodes(cluster: str) -> None:
    try:
        _refresh_nodes_cache(cluster)
    except Exception as exc:
        with _NODES_CACHE["lock"]:
            _NODES_CACHE["error"] = str(exc)
            _NODES_CACHE["refreshing"] = False


def _build_service_pods_payload(pods_data: dict, cluster: str) -> dict:
    services = _aggregate_services_from_pods(pods_data)
    all_count = len(services)
    services = filter_services(services)
    hidden_count = all_count - len(services)
    version_cache.enrich_service_list(services, cluster, sync_if_missing=False)
    if any(not s.get("version") and s.get("hasVersionApi") for s in services):
        ns_map = {str(s.get("id", "")).lower(): list(s.get("namespaces") or []) for s in services}
        version_cache.trigger_background_refresh(cluster, ns_map)
    running_pods = sum(s["running"] for s in services)
    total_pods = sum(s["total"] for s in services)
    return {
        "services": services,
        "summary": {
            "service_count": len(services),
            "running_pods": running_pods,
            "total_pods": total_pods,
            "hidden_service_count": hidden_count,
        },
        "cluster": cluster,
    }


def _refresh_service_pods_cache(cluster: str) -> tuple[Optional[dict], Optional[str]]:
    pods_data, pod_err = _kubectl_json(['get', 'pods', '--all-namespaces', '-o', 'json'], timeout=90)
    if pod_err:
        with _SERVICE_PODS_CACHE["lock"]:
            _SERVICE_PODS_CACHE["refreshing"] = False
        return None, pod_err
    payload = _build_service_pods_payload(pods_data, cluster)
    with _SERVICE_PODS_CACHE["lock"]:
        _SERVICE_PODS_CACHE["at"] = time.time()
        _SERVICE_PODS_CACHE["payload"] = payload
        _SERVICE_PODS_CACHE["refreshing"] = False
    return payload, None


def _background_refresh_service_pods(cluster: str) -> None:
    try:
        _refresh_service_pods_cache(cluster)
    except Exception as exc:
        with _SERVICE_PODS_CACHE["lock"]:
            _SERVICE_PODS_CACHE["refreshing"] = False
            _SERVICE_PODS_CACHE["error"] = str(exc)


def _cached_resource_response(
    cache: dict,
    cluster: str,
    *,
    force_refresh: bool,
    refresh_fn,
    background_fn,
    key: str,
    ttl_sec: int,
) -> tuple[Optional[list], bool, bool, Optional[str], int]:
    now = time.time()
    with cache["lock"]:
        same_cluster = cache.get("cluster") == cluster
        cached_items = list(cache["items"]) if same_cluster and cache.get("items") else None
        cached_at = cache.get("at", 0.0) if same_cluster else 0.0
        cache_age = now - cached_at if cached_at else None

    if not force_refresh and cached_items is not None and cache_age is not None and cache_age < ttl_sec:
        return cached_items, True, False, None, int(cache_age)

    stale = (
        not force_refresh
        and cached_items is not None
        and cache_age is not None
    )
    if stale:
        with cache["lock"]:
            err_msg = cache.get("error")
            if not cache.get("refreshing"):
                cache["refreshing"] = True
                threading.Thread(target=background_fn, args=(cluster,), daemon=True).start()
        return cached_items, True, True, err_msg, int(cache_age or 0)

    items, err = refresh_fn(cluster)
    if err and cached_items is not None:
        return cached_items, True, True, err, int(cache_age or 0)
    if err:
        return [], False, False, err, 0
    return items, False, False, None, 0


def _filter_pod_summaries(
    pods: list[dict],
    namespace_filter: str = "",
    status_filter: str = "",
) -> list[dict]:
    result = []
    for summary in pods:
        if namespace_filter and summary.get("namespace") != namespace_filter:
            continue
        if status_filter and str(summary.get("status", "")).lower() != status_filter.lower():
            continue
        result.append(summary)
    return result


class PodManagementHandler(BaseHTTPRequestHandler):
    def handle_one_request(self):
        """Ignore client disconnects during auto-refresh (BrokenPipeError)."""
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _write_body(self, data: bytes) -> None:
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        # Suppress noisy logs when the browser cancels in-flight refresh requests.
        if args and isinstance(args[-1], str) and "Broken pipe" in str(args[-1]):
            return
        super().log_message(format, *args)

    def _path_only(self) -> str:
        return self.path.split('?', 1)[0]

    def _parse_cookies(self) -> dict[str, str]:
        raw = self.headers.get('Cookie', '')
        cookies: dict[str, str] = {}
        for part in raw.split(';'):
            part = part.strip()
            if '=' in part:
                key, value = part.split('=', 1)
                cookies[key.strip()] = value.strip()
        return cookies

    def _session_token(self) -> Optional[str]:
        return self._parse_cookies().get(pod_auth.SESSION_COOKIE)

    def _current_user(self) -> Optional[dict]:
        if not pod_auth.is_enabled():
            return {
                "id": 0,
                "username": "local",
                "displayName": "local",
                "role": pod_rbac.ROLE_SUPER_ADMIN,
            }
        return pod_auth.validate_session(self._session_token())

    def _audit_activity(
        self,
        action: str,
        details: Optional[dict] = None,
        *,
        target: str = "",
        actor: Optional[dict] = None,
    ) -> None:
        user = actor if actor is not None else self._current_user()
        if not user:
            return
        payload = dict(details or {})
        payload.setdefault("path", self._path_only())
        payload.setdefault("method", self.command or "")
        if self.client_address:
            payload.setdefault("ip", self.client_address[0])
        pod_rbac.log_activity(user, action, payload, target=target)

    def _require_permission(self, method: Optional[str] = None, path: Optional[str] = None) -> bool:
        if not pod_auth.is_enabled():
            return True
        req_method = (method or self.command or "GET").upper()
        req_path = path or self._path_only()
        if pod_auth.is_public_path(req_method, req_path):
            return True
        resolved = pod_rbac.resolve_route_permission(req_method, req_path)
        if resolved is None:
            return True
        user = self._current_user()
        if not user:
            self._send_json(401, {'error': 'Unauthorized', 'login': '/login'})
            return False
        module, action = resolved
        if pod_rbac.user_has_permission(user, module, action):
            return True
        self._send_json(403, {
            "error": "Forbidden",
            "module": module,
            "action": action,
            "message": f"You do not have {action} access to {module}",
        })
        return False

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self._write_body(body)

    def _redirect(self, location: str, status: int = 302) -> None:
        self.send_response(status)
        self.send_header('Location', location)
        self.end_headers()

    def _cookie_suffix(self) -> str:
        proto = (self.headers.get("X-Forwarded-Proto") or self.headers.get("X-Forwarded-Ssl") or "").lower()
        if proto in ("https", "on"):
            return "; Secure"
        return ""

    def _set_session_cookie(self, token: str) -> None:
        max_age = pod_auth.session_ttl_sec()
        self.send_header(
            'Set-Cookie',
            f'{pod_auth.SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={max_age}{self._cookie_suffix()}',
        )

    def _clear_session_cookie(self) -> None:
        self.send_header(
            'Set-Cookie',
            f'{pod_auth.SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0{self._cookie_suffix()}',
        )

    def _require_auth(self, method: Optional[str] = None) -> bool:
        if not pod_auth.is_enabled():
            return True
        path = self._path_only()
        req_method = (method or self.command or 'GET').upper()
        if pod_auth.is_public_path(req_method, path):
            return True
        if self._current_user():
            return True
        if path.startswith('/api/') or req_method == 'POST':
            self._send_json(401, {'error': 'Unauthorized', 'login': '/login'})
            return False
        next_path = self.path if self.path.startswith('/') else f'/{self.path}'
        self._redirect(f'/login?next={quote(next_path, safe="")}')
        return False

    def do_GET(self):
        try:
            self._do_GET_impl()
        except Exception:
            import traceback
            traceback.print_exc()
            try:
                self._send_json(500, {'error': 'Internal server error'})
            except Exception:
                pass

    def _do_GET_impl(self) -> None:
        if not self._require_auth('GET'):
            return
        if not self._require_permission('GET'):
            return
        path_only = self._path_only()
        if path_only in ('/login', '/login.html'):
            self.serve_file('login.html', 'text/html')
            return
        if path_only == '/api/health':
            self._send_json(200, {
                'ok': True,
                'auth': pod_auth.is_enabled(),
                'authUser': pod_auth.configured_username(),
                'rbacDb': str(pod_rbac.db_path()),
                'build': 'auth-fix-2026-08-14b',
            })
            return
        if path_only == '/api/auth/me':
            self.handle_auth_me()
            return
        if self.path == '/' or path_only == '/dashboard.html':
            self.serve_file('dashboard.html', 'text/html')
        elif self.path == '/portal':
            self.serve_file('pod-management.html', 'text/html')
        elif self.path == '/terminal':
            self.serve_file('terminal-gui.html', 'text/html')
        elif path_only == '/api/pods':
            self.handle_api_pods()
        elif path_only == '/api/pods/multi-cluster':
            self._send_json(405, {'error': 'Use POST for multi-cluster pod query'})
        elif path_only == '/api/nodes':
            self.handle_api_nodes()
        elif path_only == '/api/deployments':
            self.handle_api_deployments()
        elif path_only == '/api/search':
            self.handle_api_search()
        elif self.path == '/pods':
            self.handle_list_pods()
        elif self.path == '/namespaces':
            self.handle_list_namespaces()
        elif self.path == '/nodes':
            self.handle_list_nodes()
        elif self.path == '/cluster-name':
            self.handle_cluster_name()
        elif self.path == '/api/clusters':
            self.handle_list_clusters()
        elif path_only == '/api/cache/config':
            self.handle_cache_config()
        elif path_only == '/api/validator/config':
            self.handle_validator_config()
        elif path_only == '/api/validator/health':
            self.handle_validator_health()
        elif self.path == '/api/status':
            self.handle_cluster_status()
        elif self.path.split('?', 1)[0] == '/api/service-pods':
            self.handle_service_pods()
        elif self.path.split('?', 1)[0] == '/api/version-catalog':
            self.handle_version_catalog()
        elif self.path == '/api/version-config':
            self.handle_version_config()
        elif self.path.split('?', 1)[0] == '/api/service-hide-list':
            self.handle_service_hide_list()
        elif self.path.startswith('/api/service-version/'):
            self.handle_service_version()
        elif self.path.split('?', 1)[0] == '/api/traffic-migration':
            self.handle_traffic_migration()
        elif path_only == '/data/traffic_migration_hosts.json':
            self.serve_file('data/traffic_migration_hosts.json', 'application/json')
        elif path_only == '/pod-base.js':
            self.serve_file('pod-base.js', 'application/javascript')
        elif self.path == '/kubectl-version':
            self.handle_kubectl_version()
        elif self.path.startswith('/exec?'):
            self.handle_exec_get()
        elif self.path.startswith('/troubleshoot?'):
            self.handle_troubleshoot_get()
        elif path_only.startswith('/api/admin/'):
            self.handle_admin_api('GET')
        else:
            self.send_response(404)
            self.end_headers()
    
    def do_POST(self):
        try:
            self._do_POST_impl()
        except Exception:
            import traceback
            traceback.print_exc()
            try:
                self._send_json(500, {'error': 'Internal server error'})
            except Exception:
                pass

    def do_DELETE(self):
        try:
            self._do_DELETE_impl()
        except Exception:
            import traceback
            traceback.print_exc()
            try:
                self._send_json(500, {'error': 'Internal server error'})
            except Exception:
                pass

    def _do_DELETE_impl(self) -> None:
        if not self._require_auth('DELETE'):
            return
        if not self._require_permission('DELETE'):
            return
        path_only = self._path_only()
        if path_only.startswith('/api/admin/'):
            self.handle_admin_api('DELETE')
            return
        self.send_response(404)
        self.end_headers()

    def _do_POST_impl(self) -> None:
        path_only = self._path_only()
        if path_only == '/api/auth/login':
            content_length = int(self.headers.get('Content-Length', 0) or 0)
            post_data = self.rfile.read(content_length) if content_length else b'{}'
            data = json.loads(post_data.decode('utf-8') or '{}')
            self.handle_auth_login(data)
            return
        if path_only == '/api/auth/logout':
            self.handle_auth_logout()
            return
        if not self._require_auth('POST'):
            return
        if not self._require_permission('POST'):
            return

        content_length = int(self.headers.get('Content-Length', 0) or 0)
        post_data = self.rfile.read(content_length) if content_length else b'{}'
        data = json.loads(post_data.decode('utf-8') or '{}')

        if self.path == '/cleanup':
            self.handle_cleanup(data)
        elif self.path == '/describe':
            self.handle_describe(data)
        elif self.path == '/logs':
            self.handle_logs(data)
        elif self.path == '/delete':
            self.handle_delete(data)
        elif self.path == '/services':
            self.handle_list_services(data)
        elif self.path == '/ingress':
            self.handle_list_ingress(data)
        elif self.path == '/describe-svc':
            self.handle_describe_svc(data)
        elif self.path == '/describe-ingress':
            self.handle_describe_ingress(data)
        elif self.path == '/configmaps':
            self.handle_list_configmaps(data)
        elif self.path == '/kubectl-exec':
            self.handle_kubectl_exec(data)
        elif self.path == '/execute':
            self.handle_execute(data)
        elif self.path == '/hpa':
            self.handle_list_hpa(data)
        elif self.path == '/deployments':
            self.handle_list_deployments(data)
        elif self.path == '/describe-node':
            self.handle_describe_node(data)
        elif self.path == '/describe-deployment':
            self.handle_describe_deployment(data)
        elif self.path == '/describe-configmap':
            self.handle_describe_configmap(data)
        elif self.path == '/deployment-yaml':
            self.handle_deployment_yaml(data)
        elif self.path == '/rollout-restart-deployment':
            self.handle_rollout_restart_deployment(data)
        elif self._path_only() == '/rollout-restart-deployments':
            self.handle_rollout_restart_deployments(data)
        elif self.path == '/exec':
            self.handle_exec_pod(data)
        elif self.path == '/terminal-session':
            self.handle_terminal_session(data)
        elif self.path == '/api/clusters/switch':
            self.handle_switch_cluster(data)
        elif self._path_only() == '/api/pods/multi-cluster':
            self.handle_api_pods_multi_cluster(data)
        elif self._path_only().startswith('/api/admin/'):
            self.handle_admin_api('POST', data)
        else:
            self.send_response(404)
            self.end_headers()

    def serve_file(self, filename, content_type):
        path = filename if os.path.isabs(filename) else os.path.join(_POD_DIR, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                body = f.read().encode()
                self.send_response(200)
                self.send_header('Content-type', content_type)
                self.send_header('Content-Length', str(len(body)))
                if filename.endswith('.html'):
                    self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                    self.send_header('Pragma', 'no-cache')
                self.end_headers()
                self._write_body(body)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def handle_auth_login(self, data: dict) -> None:
        if not pod_auth.is_enabled():
            self._send_json(503, {'error': 'Authentication is not configured on this server'})
            return
        token, err = pod_auth.login(
            str(data.get('username') or ''),
            str(data.get('password') or ''),
        )
        if err:
            self._send_json(401, {'error': err})
            pod_rbac.log_activity(
                {"username": str(data.get('username') or ''), "role": "unknown"},
                "auth.login_failed",
                {"reason": err},
            )
            return
        user = pod_auth.validate_session(token) or {}
        self._audit_activity("auth.login", {"role": user.get("role")}, actor=user)
        body = json.dumps({
            'ok': True,
            'username': user.get('username') or str(data.get('username') or ''),
            'role': user.get('role') or '',
        }).encode()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self._set_session_cookie(token)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self._write_body(body)

    def handle_auth_logout(self) -> None:
        user = self._current_user()
        self._audit_activity(
            "auth.logout",
            {"username": (user or {}).get("username")},
            actor=user,
        )
        pod_auth.logout(self._session_token())
        body = json.dumps({'ok': True}).encode()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self._clear_session_cookie()
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self._write_body(body)

    def handle_auth_me(self) -> None:
        token = self._session_token()
        user = pod_auth.validate_session(token)
        if not user:
            self._send_json(401, {'authenticated': False, 'login': '/login'})
            return
        if token:
            pod_auth.touch_session(token)
        payload = {
            'authenticated': True,
            'userId': user.get('id'),
            'username': user.get('username'),
            'displayName': user.get('displayName') or user.get('username'),
            'role': user.get('role'),
            'authEnabled': pod_auth.is_enabled(),
        }
        if pod_auth.is_enabled() and user.get('id'):
            try:
                payload['permissions'] = pod_rbac.permissions_for_client(user)
            except Exception as exc:
                print(f"[auth] permissions lookup failed: {exc}", flush=True)
                payload['permissions'] = {
                    'role': user.get('role'),
                    'modules': {},
                    'canManageUsers': user.get('role') != pod_rbac.ROLE_USER,
                }
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        if token:
            self._set_session_cookie(token)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self._write_body(body)

    def handle_admin_api(self, method: str, data: Optional[dict] = None) -> None:
        user = self._current_user()
        if not user:
            self._send_json(401, {'error': 'Unauthorized'})
            return
        path = self._path_only()
        sub = path[len('/api/admin/'):].strip('/')
        parts = [p for p in sub.split('/') if p]

        if method == 'GET':
            if sub == 'modules' or sub == '':
                self._send_json(200, {'modules': pod_rbac.MODULES, 'actions': list(pod_rbac.ACTIONS)})
                return
            if sub == 'audit':
                limit = 100
                action_filter = ''
                actor_filter = ''
                if '?' in self.path:
                    from urllib.parse import parse_qs
                    qs = parse_qs(self.path.split('?', 1)[1])
                    try:
                        limit = int((qs.get('limit') or ['100'])[0])
                    except ValueError:
                        limit = 100
                    action_filter = (qs.get('action') or [''])[0]
                    actor_filter = (qs.get('actor') or [''])[0]
                self._send_json(200, {
                    'logs': pod_rbac.list_audit_logs(
                        limit,
                        action_prefix=action_filter,
                        actor=actor_filter,
                    ),
                })
                return
            if parts[:1] == ['users']:
                if len(parts) == 1:
                    search = ''
                    if '?' in self.path:
                        from urllib.parse import parse_qs
                        qs = parse_qs(self.path.split('?', 1)[1])
                        search = (qs.get('search') or [''])[0]
                    users = pod_rbac.list_users(search)
                    self._send_json(200, {'users': users, 'count': len(users)})
                    return
                if len(parts) == 2 and parts[1].isdigit():
                    u = pod_rbac.get_user_by_id(int(parts[1]))
                    if not u:
                        self._send_json(404, {'error': 'User not found'})
                        return
                    self._send_json(200, {'user': u})
                    return
                if len(parts) == 3 and parts[1].isdigit() and parts[2] == 'permissions':
                    uid = int(parts[1])
                    try:
                        u = pod_rbac.get_user_by_id(uid)
                        if not u:
                            self._send_json(404, {'error': 'User not found'})
                            return
                        self._send_json(200, {
                            'user': u,
                            'permissions': pod_rbac.get_user_permissions(uid),
                            'modules': pod_rbac.MODULES,
                            'editable': u.get('role') != pod_rbac.ROLE_SUPER_ADMIN,
                        })
                    except Exception as exc:
                        import traceback
                        traceback.print_exc()
                        self._send_json(500, {'error': f'Failed to load permissions: {exc}'})
                    return
            if parts[:1] == ['clusters']:
                if len(parts) == 1:
                    clusters = pod_clusters.list_registry_clusters(include_disabled=True)
                    self._send_json(200, {'clusters': clusters, 'count': len(clusters)})
                    return
                if len(parts) == 2 and parts[1].isdigit():
                    cluster = pod_clusters.get_registry_cluster(int(parts[1]))
                    if not cluster:
                        self._send_json(404, {'error': 'Cluster not found'})
                        return
                    self._send_json(200, {'cluster': cluster})
                    return
            self._send_json(404, {'error': 'Not found'})
            return

        data = data or {}
        if method == 'DELETE':
            if len(parts) == 2 and parts[0] == 'users' and parts[1].isdigit():
                uid = int(parts[1])
                ok, err = pod_rbac.delete_user(uid, actor=user)
                if err:
                    self._send_json(400, {'error': err})
                    return
                self._send_json(200, {'ok': True})
                return
            if len(parts) == 2 and parts[0] == 'clusters' and parts[1].isdigit():
                ok, err = pod_clusters.delete_registry_cluster(int(parts[1]), actor=user)
                if err:
                    self._send_json(400, {'error': err})
                    return
                pod_cache.invalidate_html_and_meta()
                self._send_json(200, {'ok': True})
                return
            self._send_json(404, {'error': 'Not found'})
            return
        if parts[:1] == ['clusters']:
            if len(parts) == 1:
                created, err = pod_clusters.add_registry_cluster(
                    name=str(data.get('name') or ''),
                    region=str(data.get('region') or 'us-east-2'),
                    label=str(data.get('label') or data.get('displayName') or ''),
                    notes=str(data.get('notes') or ''),
                    role_arn=str(data.get('roleArn') or data.get('role_arn') or ''),
                    enabled=bool(data.get('enabled', True)),
                    actor=user,
                )
                if err:
                    self._send_json(400, {'error': err})
                    return
                pod_cache.invalidate_html_and_meta()
                self._send_json(201, {'cluster': created})
                return
            if len(parts) == 2 and parts[1].isdigit():
                role_arn = None
                if 'roleArn' in data or 'role_arn' in data:
                    role_arn = str(data.get('roleArn') or data.get('role_arn') or '')
                updated, err = pod_clusters.update_registry_cluster(
                    int(parts[1]),
                    name=data.get('name'),
                    region=data.get('region'),
                    label=data.get('label') if 'label' in data else data.get('displayName'),
                    notes=data.get('notes'),
                    role_arn=role_arn,
                    enabled=data.get('enabled') if 'enabled' in data else None,
                    actor=user,
                )
                if err:
                    self._send_json(400, {'error': err})
                    return
                pod_cache.invalidate_html_and_meta()
                self._send_json(200, {'cluster': updated})
                return
        if parts[:1] == ['users']:
            if len(parts) == 1:
                created, err = pod_rbac.create_user(
                    username=str(data.get('username') or ''),
                    password=str(data.get('password') or ''),
                    display_name=str(data.get('displayName') or data.get('display_name') or ''),
                    role=str(data.get('role') or pod_rbac.ROLE_USER),
                    actor=user,
                )
                if err:
                    self._send_json(400, {'error': err})
                    return
                self._send_json(201, {'user': created})
                return
            if len(parts) == 2 and parts[1].isdigit():
                uid = int(parts[1])
                updated, err = pod_rbac.update_user(
                    uid,
                    display_name=data.get('displayName') if 'displayName' in data else data.get('display_name'),
                    role=data.get('role'),
                    active=data.get('active') if 'active' in data else None,
                    password=data.get('password') or None,
                    actor=user,
                )
                if err:
                    self._send_json(400, {'error': err})
                    return
                self._send_json(200, {'user': updated})
                return
            if len(parts) == 3 and parts[1].isdigit() and parts[2] == 'permissions':
                uid = int(parts[1])
                perms = data.get('permissions') or {}
                ok, err = pod_rbac.set_user_permissions(uid, perms, actor=user)
                if err:
                    self._send_json(400, {'error': err})
                    return
                self._send_json(200, {'ok': True, 'permissions': pod_rbac.get_user_permissions(uid)})
                return
            if len(parts) == 3 and parts[1].isdigit() and parts[2] == 'reset-permissions':
                uid = int(parts[1])
                ok, err = pod_rbac.reset_user_permissions(uid, actor=user)
                if err:
                    self._send_json(400, {'error': err})
                    return
                self._send_json(200, {'ok': True, 'permissions': pod_rbac.get_user_permissions(uid)})
                return
        self._send_json(404, {'error': 'Not found'})

    def kubectl_cmd(self, args, timeout: int = 30):
        ctx_err = _ensure_active_cluster_context()
        if ctx_err:
            return f"Error: {ctx_err}"
        try:
            result = _run_cmd(['kubectl'] + args, timeout=timeout)
            if result.returncode == 0:
                return result.stdout
            err = (result.stderr or result.stdout or "kubectl command failed").strip()
            return f"Error: {err}"
        except Exception as e:
            return f"Error: {str(e)}"

    def _kubectl_json(self, args, timeout: int = 45):
        return _kubectl_json(args, timeout=timeout)

    def _current_context(self) -> str:
        try:
            result = _run_cmd(['kubectl', 'config', 'current-context'], timeout=10)
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _list_aws_eks_clusters(self) -> list[dict]:
        prefix = _cluster_prefix_filter()
        clusters: list[dict] = []
        seen: set[tuple[str, str]] = set()
        errors: list[str] = []

        for region in _eks_scan_regions():
            try:
                result = _run_cmd(
                    ['aws', 'eks', 'list-clusters', '--region', region, '--output', 'json'],
                    timeout=45,
                )
                if result.returncode != 0:
                    err = (result.stderr or result.stdout or "list-clusters failed").strip()
                    errors.append(f"{region}: {err[:160]}")
                    continue
                names = json.loads(result.stdout or "{}").get("clusters", [])
                for name in names:
                    if prefix and not name.startswith(prefix):
                        continue
                    key = (region, name)
                    if key in seen:
                        continue
                    seen.add(key)
                    clusters.append({"name": name, "region": region, "source": "aws"})
            except Exception as exc:
                errors.append(f"{region}: {exc}")
                continue

        clusters.sort(key=lambda c: (c.get("region") or "", c.get("name") or ""))
        return clusters, errors

    def _list_kubectl_clusters(self) -> list[dict]:
        prefix = _cluster_prefix_filter()
        clusters: list[dict] = []
        try:
            result = _run_cmd(['kubectl', 'config', 'get-contexts', '-o', 'name'], timeout=15)
            if result.returncode != 0:
                return clusters
            for ctx in result.stdout.strip().splitlines():
                ctx = ctx.strip()
                if not ctx:
                    continue
                name = _parse_cluster_from_context(ctx)
                if prefix and not name.startswith(prefix):
                    continue
                region = _region_from_context(ctx) or os.environ.get("POD_AWS_REGION", _DEFAULT_AWS_REGION)
                clusters.append({"name": name, "region": region, "source": "kubeconfig", "context": ctx})
        except Exception:
            pass
        return clusters

    def handle_list_clusters(self):
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        force_refresh = (qs.get("refresh", [""])[0] or "").strip().lower() in ("1", "true", "yes")
        current_ctx = self._current_context()
        current_name = _parse_cluster_from_context(current_ctx)

        def _build_payload() -> dict:
            aws_clusters, aws_errors = self._list_aws_eks_clusters()
            merged: dict[str, dict] = {}
            for item in pod_clusters.list_registry_clusters():
                merged[item["name"]] = {**item, "source": "registry"}
            for item in aws_clusters:
                if item["name"] not in merged:
                    merged[item["name"]] = item
                else:
                    merged[item["name"]].setdefault("discoveredRegion", item.get("region"))
            for item in self._list_kubectl_clusters():
                merged.setdefault(item["name"], item)

            clusters = sorted(merged.values(), key=lambda c: (c.get("region") or "", c.get("name") or ""))
            payload = {
                "clusters": clusters,
                "current": current_name,
                "current_context": current_ctx,
                "regions_scanned": _eks_scan_regions(),
            }
            if aws_errors and not clusters:
                payload["error"] = aws_errors[0]
                payload["errors"] = aws_errors[:5]
            return payload

        payload, cached, cache_age = pod_cache.get_cluster_payload(
            pod_cache.clusters_ttl(),
            force_refresh,
            _build_payload,
        )
        payload = json.loads(json.dumps(payload))
        for cluster in payload.get("clusters") or []:
            cluster["current"] = cluster.get("name") == current_name
        payload["current"] = current_name
        payload["current_context"] = current_ctx
        payload["cached"] = cached
        payload["cacheAgeSec"] = cache_age

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def handle_cache_config(self) -> None:
        cfg = pod_cache.config_for_client()
        cfg["versionCacheTtlSec"] = version_cache.cache_ttl_sec()
        cfg["versionCacheRefreshSec"] = version_cache.cache_refresh_sec()
        self._send_json(200, cfg)

    def handle_validator_config(self) -> None:
        host = self.headers.get("Host", "")
        scheme = validator_integration.guess_request_scheme(
            {k: v for k, v in self.headers.items()}
        )
        self._send_json(200, validator_integration.client_config(host, scheme))

    def handle_validator_health(self) -> None:
        self._send_json(200, validator_integration.check_upstream())

    def handle_switch_cluster(self, data):
        name = (data.get("name") or "").strip()
        region = (data.get("region") or os.environ.get("POD_AWS_REGION", _DEFAULT_AWS_REGION)).strip()
        if not name:
            self.send_response(400)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": "Cluster name is required"}).encode())
            return

        role_arn = _resolve_cluster_role_arn(
            name,
            data.get("roleArn") or data.get("role_arn"),
        )

        try:
            err = _switch_eks_cluster(name, region, role_arn=role_arn or None)
            if err:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": err}).encode())
                return

            _remember_active_cluster(name, region, role_arn or "")
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "cluster": name,
                "region": region,
                "roleArn": role_arn or None,
                "context": self._current_context(),
            }).encode())
            _invalidate_resource_caches()
            self._audit_activity("cluster.switch", {
                "cluster": name,
                "region": region,
                "hasRoleArn": bool(role_arn),
            })
        except Exception as exc:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode())

    def handle_cluster_status(self):
        cluster = _display_cluster_name()
        region = (_ACTIVE_CLUSTER.get("region") or os.environ.get("POD_AWS_REGION", _DEFAULT_AWS_REGION)).strip()
        pods_data, pod_err = self._kubectl_json(['get', 'pods', '--all-namespaces', '-o', 'json'])
        nodes_data, node_err = self._kubectl_json(['get', 'nodes', '-o', 'json'], timeout=20)

        items = pods_data.get("items", []) if pods_data else []
        pod_stats = _aggregate_pod_stats(items) if pods_data else {}
        node_count = len(nodes_data.get("items", [])) if nodes_data else 0
        connected = pods_data is not None
        error = pod_err or node_err or ""

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self._write_body(json.dumps({
            "connected": connected,
            "cluster": cluster,
            "region": region,
            "context": self._current_context(),
            "pod_count": pod_stats.get("visible_total", len(items)),
            "cluster_pod_count": pod_stats.get("cluster_total", len(items)),
            "pod_stats": pod_stats,
            "node_count": node_count,
            "error": error,
        }).encode())

    def handle_service_pods(self):
        from urllib.parse import parse_qs, urlparse

        qs = parse_qs(urlparse(self.path).query)
        force_refresh = (qs.get("refresh", ["0"])[0] or "").strip().lower() in ("1", "true", "yes")
        now = time.time()
        cluster = _parse_cluster_from_context(self._current_context())
        ttl = pod_cache.service_pods_ttl()

        with _SERVICE_PODS_CACHE["lock"]:
            cached = _SERVICE_PODS_CACHE.get("payload")
            cached_at = float(_SERVICE_PODS_CACHE.get("at") or 0.0)
            refreshing = bool(_SERVICE_PODS_CACHE.get("refreshing"))
            cache_age = now - cached_at if cached_at else None

        def _send_payload(payload: dict, *, cached: bool, stale: bool, age: int) -> None:
            body_payload = json.loads(json.dumps(payload))
            body_payload["cached"] = cached
            body_payload["stale"] = stale
            body_payload["cacheAgeSec"] = age
            body = json.dumps(body_payload).encode()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('X-Cache', 'HIT' if cached and not stale else ('STALE' if stale else 'MISS'))
            self.end_headers()
            self._write_body(body)

        if not force_refresh and cached and cache_age is not None and cache_age < ttl:
            _send_payload(cached, cached=True, stale=False, age=int(cache_age))
            return

        if not force_refresh and cached and cache_age is not None and not refreshing:
            with _SERVICE_PODS_CACHE["lock"]:
                _SERVICE_PODS_CACHE["refreshing"] = True
            threading.Thread(target=_background_refresh_service_pods, args=(cluster,), daemon=True).start()
            _send_payload(cached, cached=True, stale=True, age=int(cache_age))
            return

        try:
            payload, err = _refresh_service_pods_cache(cluster)
            if err and cached:
                _send_payload(cached, cached=True, stale=True, age=int(cache_age or 0))
                return
            if err:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self._write_body(json.dumps({
                    "error": err,
                    "services": [],
                    "summary": {"service_count": 0, "running_pods": 0, "total_pods": 0},
                    "connected": False,
                }).encode())
                return
            _send_payload(payload or {"services": [], "summary": {}, "cluster": cluster}, cached=False, stale=False, age=0)
        except Exception as exc:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self._write_body(json.dumps({
                "error": str(exc),
                "services": [],
                "summary": {"service_count": 0, "running_pods": 0, "total_pods": 0},
            }).encode())

    def handle_service_hide_list(self):
        rules = load_hide_rules()
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self._write_body(json.dumps({"rules": rules}).encode())

    def handle_version_catalog(self):
        catalog = load_catalog()
        cluster = _parse_cluster_from_context(self._current_context())
        services = list_version_catalog_entries(catalog, cluster_hint=cluster)
        environment = resolve_version_environment(catalog, cluster)
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self._write_body(json.dumps({
            "environment": environment,
            "services": services,
        }).encode())

    def handle_version_config(self):
        """Return configured version API URLs (defaults + overrides file + env)."""
        overrides = get_version_overrides()
        services = [
            {"id": sid, "name": sid, "versionUrl": url, "hasVersionApi": bool(url)}
            for sid, url in sorted(overrides.items())
        ]
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self._write_body(json.dumps({
            "environment": os.environ.get("POD_VERSION_ENV", "comcast"),
            "aliases": get_version_aliases(),
            "services": services,
        }).encode())

    def handle_service_version(self):
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(self.path)
        service_id = parsed.path.split('/api/service-version/', 1)[-1].strip('/')
        params = parse_qs(parsed.query or "")
        prefer_http = params.get("http", ["0"])[0] in ("1", "true", "yes")

        if not service_id:
            self.send_response(400)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self._write_body(json.dumps({"ok": False, "error": "Service id required"}).encode())
            return

        configured_url = ""
        try:
            cluster = _parse_cluster_from_context(self._current_context())
            catalog = load_catalog()
            meta = catalog_service_meta(catalog, service_id, cluster_hint=cluster)
            configured_url = str(meta.get("versionUrl") or "")

            namespaces: list[str] = []
            sid_lower = service_id.lower()
            resolved = _resolve_version_service_id(sid_lower)
            pods_data, _ = self._kubectl_json(['get', 'pods', '--all-namespaces', '-o', 'json'], timeout=60)
            if pods_data:
                for pod in pods_data.get("items", []):
                    pod_svc = service_name_from_pod(pod).lower()
                    if pod_svc in (sid_lower, resolved):
                        ns = pod.get("metadata", {}).get("namespace")
                        if ns and ns not in namespaces:
                            namespaces.append(ns)

            force = params.get("force", ["0"])[0] in ("1", "true", "yes")
            payload = version_cache.get_or_fetch(
                service_id,
                cluster,
                namespaces,
                force=force,
                prefer_http=prefer_http or bool(
                    configured_url
                    and _is_configured_version_url(configured_url)
                    and not _is_arloxcld_url(configured_url)
                ),
            )
            if not payload.get("versionUrl") and configured_url:
                payload["versionUrl"] = configured_url
                payload["hasVersionApi"] = True
            err = str(payload.get("versionError") or "")
            if configured_url and "not configured" in err.lower():
                payload = version_cache.fetch_and_store(
                    service_id,
                    cluster,
                    namespaces,
                    prefer_http=True,
                )
                payload.setdefault("serviceId", service_id)
            elif not payload.get("versionUrl"):
                payload["versionUrl"] = configured_url
            payload.setdefault("serviceId", service_id)
            payload.setdefault("ok", bool(payload.get("version")))
        except Exception as exc:
            payload = {
                "ok": False,
                "serviceId": service_id,
                "version": "",
                "versionUrl": configured_url,
                "versionError": str(exc)[:160],
            }

        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self._write_body(json.dumps(payload).encode())

    def handle_api_pods(self):
        """JSON pod list for dashboard and terminal GUI (cached)."""
        from urllib.parse import parse_qs, urlparse

        try:
            qs = parse_qs(urlparse(self.path).query)
            namespace_filter = (qs.get("namespace", [""])[0] or "").strip()
            status_filter = (qs.get("status", [""])[0] or "").strip()
            force_refresh = (qs.get("refresh", ["0"])[0] or "").strip() in ("1", "true", "yes")

            cluster = _parse_cluster_from_context(self._current_context())
            now = time.time()
            with _PODS_CACHE["lock"]:
                same_cluster = _PODS_CACHE.get("cluster") == cluster
                cached_pods = list(_PODS_CACHE["pods"]) if same_cluster and _PODS_CACHE.get("pods") else None
                cached_at = _PODS_CACHE.get("at", 0.0) if same_cluster else 0.0
                cache_age = now - cached_at if cached_at else None
                refreshing = bool(_PODS_CACHE.get("refreshing"))

            def _respond(pods: list[dict], *, cached: bool, stale: bool = False, warning: str = "") -> None:
                filtered = _filter_pod_summaries(pods, namespace_filter, status_filter)
                region = _region_from_context(self._current_context()) or os.environ.get("POD_AWS_REGION", _DEFAULT_AWS_REGION)
                stamped = [{**p, "cluster": cluster} for p in filtered]
                payload = {
                    "pods": stamped,
                    "count": len(stamped),
                    "cluster": cluster,
                    "region": region,
                    "cached": cached,
                    "cacheAgeSec": int(cache_age) if cache_age is not None else 0,
                }
                if stale:
                    payload["stale"] = True
                if warning:
                    payload["warning"] = warning
                self._send_json(200, payload)

            if not force_refresh and cached_pods is not None and cache_age is not None and cache_age < pod_cache.pods_ttl():
                _respond(cached_pods, cached=True)
                return

            if (
                not force_refresh
                and cached_pods is not None
                and cache_age is not None
                and not refreshing
            ):
                with _PODS_CACHE["lock"]:
                    _PODS_CACHE["refreshing"] = True
                threading.Thread(target=_background_refresh_pods, args=(cluster,), daemon=True).start()
                _respond(cached_pods, cached=True, stale=True)
                return

            pods, err = _refresh_pods_cache(cluster)
            if err and cached_pods is not None:
                _respond(cached_pods, cached=True, stale=True, warning=err)
                return
            if err:
                self._send_json(200, {"error": err, "pods": [], "connected": False})
                return
            _respond(pods, cached=False)
        except Exception as e:
            self._send_json(500, {"error": str(e), "pods": []})

    def handle_api_pods_multi_cluster(self, data: dict) -> None:
        """Fetch and merge pods from multiple EKS clusters."""
        force_refresh = bool(data.get("refresh"))
        resolved = _resolve_cluster_list(data.get("clusters") or [])
        if not resolved:
            cluster = _parse_cluster_from_context(self._current_context())
            region = _region_from_context(self._current_context()) or os.environ.get("POD_AWS_REGION", _DEFAULT_AWS_REGION)
            role_arn = _resolve_cluster_role_arn(cluster)
            resolved = [{"name": cluster, "region": region, "roleArn": role_arn}]

        namespace_filter = (data.get("namespace") or "").strip()
        status_filter = (data.get("status") or "").strip()
        orig_ctx = self._current_context()
        merged: list[dict] = []
        cluster_results: list[dict] = []
        any_cached = False
        max_age = 0
        warnings: list[str] = []

        try:
            for item in resolved:
                name = item["name"]
                region = item["region"]
                role_arn = item.get("roleArn") or ""
                err = _switch_eks_cluster(name, region, role_arn=role_arn or None)
                if err:
                    cluster_results.append({
                        "cluster": name,
                        "region": region,
                        "ok": False,
                        "count": 0,
                        "error": err,
                    })
                    warnings.append(f"{name}: {err}")
                    continue
                pods, fetch_err, cached, cache_age = _stored_pods_for_cluster(name, force_refresh=force_refresh)
                if fetch_err:
                    cluster_results.append({
                        "cluster": name,
                        "region": region,
                        "ok": False,
                        "count": 0,
                        "error": fetch_err,
                    })
                    warnings.append(f"{name}: {fetch_err}")
                    continue
                if cached:
                    any_cached = True
                    max_age = max(max_age, cache_age)
                stamped = [{**p, "cluster": name, "region": region} for p in (pods or [])]
                filtered = _filter_pod_summaries(stamped, namespace_filter, status_filter)
                merged.extend(filtered)
                cluster_results.append({
                    "cluster": name,
                    "region": region,
                    "ok": True,
                    "count": len(filtered),
                    "cached": cached,
                    "cacheAgeSec": cache_age,
                })
        finally:
            _use_kubectl_context(orig_ctx)

        payload = {
            "pods": merged,
            "count": len(merged),
            "multiCluster": len(resolved) > 1,
            "clusters": [r["cluster"] for r in cluster_results if r.get("ok")],
            "clusterResults": cluster_results,
            "cached": any_cached,
            "cacheAgeSec": max_age,
        }
        if warnings:
            payload["warning"] = "; ".join(warnings[:3])
        self._send_json(200, payload)

    def handle_api_nodes(self):
        from urllib.parse import parse_qs, urlparse

        try:
            qs = parse_qs(urlparse(self.path).query)
            force_refresh = (qs.get("refresh", [""])[0] or "").strip().lower() in ("1", "true", "yes")
            cluster = _parse_cluster_from_context(self._current_context())
            items, cached, stale, warning, cache_age = _cached_resource_response(
                _NODES_CACHE,
                cluster,
                force_refresh=force_refresh,
                refresh_fn=_refresh_nodes_cache,
                background_fn=_background_refresh_nodes,
                key="nodes",
                ttl_sec=pod_cache.nodes_ttl(),
            )
            if warning and not items:
                self._send_json(503, {"error": warning, "nodes": []})
                return
            self._send_json(200, {
                "nodes": items or [],
                "count": len(items or []),
                "cluster": cluster,
                "cached": cached,
                "stale": stale,
                "cacheAgeSec": cache_age,
                "warning": warning or "",
            })
        except Exception as e:
            self._send_json(500, {"error": str(e), "nodes": []})

    def handle_api_deployments(self):
        from urllib.parse import parse_qs, urlparse

        try:
            qs = parse_qs(urlparse(self.path).query)
            namespace_filter = (qs.get("namespace", [""])[0] or "").strip()
            force_refresh = (qs.get("refresh", [""])[0] or "").strip().lower() in ("1", "true", "yes")
            cluster = _parse_cluster_from_context(self._current_context())
            items, cached, stale, warning, cache_age = _cached_resource_response(
                _DEPLOYMENTS_CACHE,
                cluster,
                force_refresh=force_refresh,
                refresh_fn=_refresh_deployments_cache,
                background_fn=_background_refresh_deployments,
                key="deployments",
                ttl_sec=pod_cache.deployments_ttl(),
            )
            if warning and not items:
                self._send_json(503, {"error": warning, "deployments": []})
                return
            deployments = []
            for summary in items or []:
                if namespace_filter and summary["namespace"] != namespace_filter:
                    continue
                deployments.append(summary)
            self._send_json(200, {
                "deployments": deployments,
                "count": len(deployments),
                "cluster": cluster,
                "cached": cached,
                "stale": stale,
                "cacheAgeSec": cache_age,
                "warning": warning or "",
            })
        except Exception as e:
            self._send_json(500, {"error": str(e), "deployments": []})

    def handle_api_search(self):
        from urllib.parse import parse_qs, urlparse

        try:
            qs = parse_qs(urlparse(self.path).query)
            query = (qs.get("q", [""])[0] or "").strip().lower()
            limit = 30
            try:
                limit = min(100, max(5, int((qs.get("limit", ["30"])[0] or "30"))))
            except ValueError:
                limit = 30
            if len(query) < 2:
                self._send_json(200, {"query": query, "results": []})
                return

            cluster = _parse_cluster_from_context(self._current_context())
            results: list[dict] = []

            with _PODS_CACHE["lock"]:
                pods = list(_PODS_CACHE.get("pods") or []) if _PODS_CACHE.get("cluster") == cluster else []
            for pod in pods:
                hay = f"{pod.get('namespace','')} {pod.get('name','')} {pod.get('ip','')} {pod.get('node','')}".lower()
                if query in hay:
                    results.append({
                        "type": "pod",
                        "section": "pods",
                        "label": f"{pod.get('namespace')}/{pod.get('name')}",
                        "meta": pod.get("status") or "",
                    })
                if len(results) >= limit:
                    break

            if len(results) < limit:
                with _DEPLOYMENTS_CACHE["lock"]:
                    deployments = list(_DEPLOYMENTS_CACHE.get("items") or []) if _DEPLOYMENTS_CACHE.get("cluster") == cluster else []
                for dep in deployments:
                    hay = f"{dep.get('namespace','')} {dep.get('name','')}".lower()
                    if query in hay:
                        results.append({
                            "type": "deployment",
                            "section": "deployments",
                            "label": f"{dep.get('namespace')}/{dep.get('name')}",
                            "meta": dep.get("ready") or "",
                        })
                    if len(results) >= limit:
                        break

            self._send_json(200, {"query": query, "cluster": cluster, "results": results[:limit]})
        except Exception as e:
            self._send_json(500, {"error": str(e), "results": []})

    def handle_traffic_migration(self):
        from urllib.parse import parse_qs, urlparse

        try:
            qs = parse_qs(urlparse(self.path).query)
            hostname = (qs.get("hostname", [""])[0] or "").strip()
            list_only = (qs.get("list", [""])[0] or "").strip().lower() in ("1", "true", "yes")
            audit = (qs.get("audit", [""])[0] or "").strip().lower() in ("1", "true", "yes")
            force_refresh = (qs.get("refresh", [""])[0] or "").strip().lower() in ("1", "true", "yes")
            cache_key = f"{hostname}|{int(list_only)}|{int(audit)}"

            def _fetch() -> dict:
                return fetch_traffic_migration(hostname, list_only=list_only, audit=audit)

            payload, cached, cache_age = pod_cache.get_traffic_payload(
                cache_key,
                pod_cache.traffic_ttl(),
                force_refresh,
                _fetch,
            )
            payload["cached"] = cached
            payload["cacheAgeSec"] = cache_age
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e), "hosts": [], "count": 0}).encode())

    def _build_pod_rows_html(self, pods_data: dict) -> str:
        html = (
            '<table class="table table-sm table-hover table-striped align-middle mb-0">'
            '<thead class="table-light"><tr>'
        )
        headers = ['NAMESPACE', 'NAME', 'READY', 'STATUS', 'RESTARTS', 'AGE', 'IP', 'ACTIONS']
        html += ''.join(f'<th scope="col">{h}</th>' for h in headers) + '</tr></thead><tbody>'

        for pod in pods_data.get('items', []):
            if should_hide_pod(pod):
                continue
            summary = _pod_to_summary(pod)
            namespace = summary["namespace"]
            name = summary["name"]
            pod_key = f"{namespace}/{name}"
            safe_key = _html_escape(pod_key).replace("'", "\\'")
            status_class = summary["statusClass"]

            html += f'<tr class="pod-row {status_class}" data-pod-key="{_html_escape(pod_key)}" style="cursor:pointer">'
            html += f'<td><span class="text-success fw-semibold">{_html_escape(namespace)}</span></td>'
            html += f'<td><span class="text-primary fw-semibold">{_html_escape(name)}</span></td>'
            html += f'<td>{summary["ready"]}</td>'
            html += f'<td class="{status_class}">{_html_escape(summary["status"])}</td>'
            html += f'<td>{summary["restarts"]}</td>'
            html += f'<td title="{_html_escape(summary["age"])}">{_html_escape(summary["age"])}</td>'
            html += f'<td><code class="small">{_html_escape(summary["ip"])}</code></td>'
            html += (
                f'<td class="text-nowrap">'
                f'<button type="button" class="btn btn-3d btn-3d-primary btn-sm pod-describe-btn" '
                f'data-pod-key="{_html_escape(pod_key)}" '
                f'onclick="event.stopPropagation(); selectPodByKey(\'{safe_key}\')">'
                f'<i class="bi bi-card-text"></i> Describe</button></td>'
            )
            html += '</tr>'

        html += '</tbody></table>'
        return html

    def handle_list_pods(self):
        pods_data, err = self._kubectl_json(['get', 'pods', '--all-namespaces', '-o', 'json'])
        if err:
            html = (
                f'<p class="kubectl-error"><strong>Cannot list pods.</strong> '
                f'{_html_escape(err)}</p>'
                f'<p>Select an EKS cluster from the sidebar dropdown, or run '
                f'<code>aws eks update-kubeconfig --region us-east-2 --name &lt;cluster&gt;</code>.</p>'
            )
        else:
            items = pods_data.get('items', [])
            visible = [p for p in items if not should_hide_pod(p)]
            if not visible:
                html = '<p>No application pods found (infrastructure pods are excluded).</p>'
            else:
                html = self._build_pod_rows_html(pods_data)

        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self._write_body(html.encode())

    def handle_list_namespaces(self):
        output = self.kubectl_cmd(['get', 'namespaces', '-o', 'name'])
        if output.startswith('Error'):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.send_header('X-Kubectl-Error', output[7:200] if len(output) > 7 else 'kubectl failed')
            self.end_headers()
            self.wfile.write(b'default')
            return
        namespaces = [
            ns.replace('namespace/', '')
            for ns in output.strip().split('\n')
            if ns and not is_hidden_namespace(ns.replace('namespace/', ''))
        ]

        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(', '.join(namespaces).encode())

    def handle_list_nodes(self):
        output = self.kubectl_cmd(['get', 'nodes', '-o', 'wide'])
        if output.startswith('Error'):
            html = f'<p class="kubectl-error">{_html_escape(output)}</p>'
        else:
            html = self.format_table(output)
        
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self._write_body(html.encode())

    def handle_exec_get(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        pod = params.get('pod', [''])[0]
        namespace = params.get('namespace', ['default'])[0]
        
        exec_cmd = f"kubectl exec -it {pod} -n {namespace} -- /bin/bash"
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(exec_cmd.encode())

    def handle_kubectl_version(self):
        try:
            result = _run_cmd(['kubectl', 'version', '--client'], timeout=10)
            if result.returncode == 0:
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(result.stdout.encode())
            else:
                self.send_response(500)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'kubectl not available')
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f'Error: {str(e)}'.encode())

    def handle_kubectl_exec(self, data):
        try:
            pod = data.get('pod', '')
            namespace = data.get('namespace', 'default')
            command = data.get('command', '')

            if not pod or not command:
                self.send_response(400)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(b'Pod name and command are required')
                return

            result = _run_cmd(
                ['kubectl', 'exec', '-n', namespace, pod, '--', 'sh', '-c', command],
                timeout=30,
            )

            self.send_response(200 if result.returncode == 0 else 500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()

            output = result.stdout if result.stdout else result.stderr
            self.wfile.write(output.encode())

        except subprocess.TimeoutExpired:
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Command timeout')
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(f'Error: {str(e)}'.encode())

    def handle_execute(self, data):
        # Host shell execution is intentionally disabled — use /kubectl-exec for pod commands.
        self._send_json(403, {
            'error': 'Host command execution is disabled. Use kubectl-exec for in-pod commands.',
        })

    def handle_cluster_name(self):
        cluster_name = _display_cluster_name()
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(cluster_name.encode())

    def handle_troubleshoot_get(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        
        pod = params.get('pod', [''])[0]
        namespace = params.get('namespace', ['default'])[0]
        
        troubleshoot_cmd = f"kubectl exec -it {pod} -n {namespace} -- bash -c 'apt update && apt install -y telnet && bash'"
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(troubleshoot_cmd.encode())

    def handle_cleanup(self, data):
        env = os.environ.copy()
        env['DRY_RUN'] = 'true' if data.get('dryRun') else 'false'
        
        try:
            result = subprocess.run(['bash', 'pods.sh'], capture_output=True, text=True, env=env)
            output = result.stdout + result.stderr
        except Exception as e:
            output = f"Error running cleanup: {str(e)}"
        self._audit_activity("cleanup.run", {"dryRun": bool(data.get('dryRun')), "ok": "Error" not in output[:80]})
        _invalidate_resource_caches()
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

    def handle_describe(self, data):
        pod = data.get('pod')
        namespace = data.get('namespace', 'default')
        cluster_name = (data.get('cluster') or '').strip()
        region = (data.get('region') or os.environ.get('POD_AWS_REGION', _DEFAULT_AWS_REGION)).strip()
        role_arn = _resolve_cluster_role_arn(cluster_name, data.get('roleArn') or data.get('role_arn'))
        orig_ctx = self._current_context()
        try:
            if cluster_name:
                err = _switch_eks_cluster(cluster_name, region, role_arn=role_arn or None)
                if err:
                    self.send_response(500)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(f"Error: {err}".encode())
                    return
            output = self.kubectl_cmd(['describe', 'pod', pod, '-n', namespace])
        finally:
            if cluster_name:
                _use_kubectl_context(orig_ctx)
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

    def handle_logs(self, data):
        pod = data.get('pod')
        namespace = data.get('namespace', 'default')
        cluster_name = (data.get('cluster') or '').strip()
        region = (data.get('region') or os.environ.get('POD_AWS_REGION', _DEFAULT_AWS_REGION)).strip()
        role_arn = _resolve_cluster_role_arn(cluster_name, data.get('roleArn') or data.get('role_arn'))
        orig_ctx = self._current_context()
        try:
            if cluster_name:
                err = _switch_eks_cluster(cluster_name, region, role_arn=role_arn or None)
                if err:
                    self.send_response(500)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(f"Error: {err}".encode())
                    return
            output = self.kubectl_cmd(['logs', pod, '-n', namespace, '--tail=100'])
        finally:
            if cluster_name:
                _use_kubectl_context(orig_ctx)
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

    def handle_delete(self, data):
        pod = data.get('pod')
        namespace = data.get('namespace', 'default')
        cluster_name = (data.get('cluster') or '').strip()
        region = (data.get('region') or os.environ.get('POD_AWS_REGION', _DEFAULT_AWS_REGION)).strip()
        role_arn = _resolve_cluster_role_arn(cluster_name, data.get('roleArn') or data.get('role_arn'))
        orig_ctx = self._current_context()
        try:
            if cluster_name:
                err = _switch_eks_cluster(cluster_name, region, role_arn=role_arn or None)
                if err:
                    self.send_response(500)
                    self.send_header('Content-type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(f"Error: {err}".encode())
                    return
            output = self.kubectl_cmd(['delete', 'pod', pod, '-n', namespace])
        finally:
            if cluster_name:
                _use_kubectl_context(orig_ctx)
                _invalidate_resource_caches()
        ok = not str(output).startswith('Error')
        self._audit_activity(
            "pod.delete",
            {"pod": pod, "namespace": namespace, "cluster": cluster_name or None, "ok": ok},
            target=f"{cluster_name + ':' if cluster_name else ''}{namespace}/{pod}",
        )
        if not cluster_name:
            _invalidate_resource_caches()
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

    def _cached_kubectl_resource_html(
        self,
        resource: str,
        data: dict,
        kubectl_args: list[str],
        *,
        table_kind: str = "",
        namespace_for_table: str = "default",
    ) -> str:
        namespace = data.get("namespace") or ""
        force_refresh = str(data.get("refresh", "")).lower() in ("1", "true", "yes")
        cluster = _parse_cluster_from_context(self._current_context())
        cache_key = f"{cluster}:{namespace or '*'}"

        def fetch() -> tuple[str, Optional[str]]:
            output = self.kubectl_cmd(kubectl_args)
            if output.startswith("Error"):
                return f'<p class="kubectl-error">{_html_escape(output)}</p>', output
            if table_kind == "svc":
                html = self.format_table(output, "svc")
            elif table_kind == "ingress":
                html = self.format_table(output, "ingress")
            elif table_kind == "configmap":
                html = self.format_table(output, "configmap", namespace or namespace_for_table)
            else:
                html = self.format_table(output)
            return html, None

        html, _, _, _ = pod_cache.cached_kubectl_html(
            resource,
            cache_key,
            pod_cache.k8s_html_ttl(),
            force_refresh,
            fetch,
        )
        return html

    def handle_list_services(self, data):
        namespace = data.get('namespace')
        if namespace:
            kubectl_args = ['get', 'svc', '-n', namespace, '-o', 'wide']
        else:
            kubectl_args = ['get', 'svc', '--all-namespaces', '-o', 'wide']
        html = self._cached_kubectl_resource_html("services", data, kubectl_args, table_kind="svc")
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self._write_body(html.encode())

    def handle_list_ingress(self, data):
        namespace = data.get('namespace')
        if namespace:
            kubectl_args = ['get', 'ingress', '-n', namespace, '-o', 'wide']
        else:
            kubectl_args = ['get', 'ingress', '--all-namespaces', '-o', 'wide']
        html = self._cached_kubectl_resource_html("ingress", data, kubectl_args, table_kind="ingress")
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self._write_body(html.encode())

    def handle_describe_svc(self, data):
        name = data.get('name')
        namespace = data.get('namespace', 'default')
        output = self.kubectl_cmd(['describe', 'svc', name, '-n', namespace])
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

    def handle_describe_ingress(self, data):
        name = data.get('name')
        namespace = data.get('namespace', 'default')
        output = self.kubectl_cmd(['describe', 'ingress', name, '-n', namespace])
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

    def handle_list_configmaps(self, data):
        namespace = data.get('namespace')
        if namespace:
            kubectl_args = ['get', 'configmaps', '-n', namespace, '-o', 'wide']
        else:
            kubectl_args = ['get', 'configmaps', '--all-namespaces', '-o', 'wide']
        html = self._cached_kubectl_resource_html(
            "configmaps", data, kubectl_args, table_kind="configmap", namespace_for_table="default",
        )
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self._write_body(html.encode())

    def handle_list_hpa(self, data):
        namespace = data.get('namespace')
        if namespace:
            kubectl_args = ['get', 'hpa', '-n', namespace, '-o', 'wide']
        else:
            kubectl_args = ['get', 'hpa', '--all-namespaces', '-o', 'wide']
        html = self._cached_kubectl_resource_html("hpa", data, kubectl_args)
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self._write_body(html.encode())

    def handle_list_deployments(self, data):
        namespace = data.get('namespace')
        if namespace:
            output = self.kubectl_cmd(['get', 'deployments', '-n', namespace, '-o', 'wide'])
        else:
            output = self.kubectl_cmd(['get', 'deployments', '--all-namespaces', '-o', 'wide'])

        if output.startswith('Error'):
            html = f'<p class="kubectl-error">{_html_escape(output)}</p>'
        else:
            html = self.format_table(output)
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self._write_body(html.encode())

    def handle_describe_node(self, data):
        node = data.get('node') or data.get('name')
        if not node:
            self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Node name is required')
            return
        output = self.kubectl_cmd(['describe', 'node', node])
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

    def handle_describe_deployment(self, data):
        name = data.get('deployment') or data.get('name')
        namespace = data.get('namespace', 'default')
        if not name:
            self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Deployment name is required')
            return
        output = self.kubectl_cmd(['describe', 'deployment', name, '-n', namespace])
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

    def handle_deployment_yaml(self, data):
        name = data.get('deployment') or data.get('name')
        namespace = data.get('namespace', 'default')
        if not name:
            self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'Deployment name is required')
            return
        output = self.kubectl_cmd(['get', 'deployment', name, '-n', namespace, '-o', 'yaml'])
        if output.startswith('Error'):
            self.send_response(500)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(output.encode())
            return
        self.send_response(200)
        self.send_header('Content-type', 'text/yaml')
        self.end_headers()
        self.wfile.write(output.encode())

    def _resolve_restart_clusters(self, data: dict) -> list[dict]:
        clusters = data.get('clusters') or []
        resolved: list[dict] = []
        if isinstance(clusters, list):
            for item in clusters:
                if not isinstance(item, dict):
                    continue
                name = (item.get('name') or '').strip()
                if not name:
                    continue
                region = (item.get('region') or os.environ.get('POD_AWS_REGION', _DEFAULT_AWS_REGION)).strip()
                role_arn = _resolve_cluster_role_arn(
                    name,
                    item.get('roleArn') or item.get('role_arn'),
                )
                resolved.append({
                    'name': name,
                    'region': region,
                    'roleArn': role_arn,
                })
        if resolved:
            return resolved
        current_ctx = self._current_context()
        current_name = _parse_cluster_from_context(current_ctx)
        region = _region_from_context(current_ctx) or os.environ.get('POD_AWS_REGION', _DEFAULT_AWS_REGION)
        role_arn = _resolve_cluster_role_arn(current_name)
        return [{'name': current_name, 'region': region, 'roleArn': role_arn}]

    @staticmethod
    def _kubectl_command_failed(output: str) -> bool:
        text = str(output or '').strip()
        lower = text.lower()
        return lower.startswith('error') or '\nerror:' in lower

    @staticmethod
    def _is_not_found_error(output: str, kind: str, name: str) -> bool:
        lower = str(output or '').lower()
        if 'notfound' in lower or 'not found' in lower:
            return True
        resource = f'{kind}s.apps "{name}"'
        return resource in lower

    def _rollout_status_wait(
        self,
        workload_kind: str,
        name: str,
        namespace: str,
        timeout_sec: int = 180,
    ) -> tuple[bool, str]:
        timeout = max(10, min(int(timeout_sec or 180), 600))
        out = self.kubectl_cmd([
            'rollout', 'status', f'{workload_kind}/{name}', '-n', namespace, f'--timeout={timeout}s',
        ])
        ok = not self._kubectl_command_failed(out) and 'successfully rolled out' in str(out).lower()
        return ok, str(out)[:500]

    def _restart_k8s_workload(
        self,
        name: str,
        namespace: str,
        wait: bool = False,
        wait_timeout_sec: int = 180,
    ) -> tuple[bool, str, str, Optional[bool], str]:
        """
        Restart a workload by name.
        Try deployment first, then fallback to statefulset if deployment is not found.
        """
        dep_output = self.kubectl_cmd(['rollout', 'restart', 'deployment', name, '-n', namespace])
        if not self._kubectl_command_failed(dep_output):
            wait_ok, wait_out = (None, '')
            if wait:
                wait_ok, wait_out = self._rollout_status_wait('deployment', name, namespace, wait_timeout_sec)
            return (wait_ok is not False), str(dep_output)[:500], 'deployment', wait_ok, wait_out

        if not self._is_not_found_error(dep_output, 'deployment', name):
            return False, str(dep_output)[:500], 'deployment', None, ''

        sts_output = self.kubectl_cmd(['rollout', 'restart', 'statefulset', name, '-n', namespace])
        if not self._kubectl_command_failed(sts_output):
            wait_ok, wait_out = (None, '')
            if wait:
                wait_ok, wait_out = self._rollout_status_wait('statefulset', name, namespace, wait_timeout_sec)
            return (wait_ok is not False), str(sts_output)[:500], 'statefulset', wait_ok, wait_out
        return False, str(sts_output)[:500], 'statefulset', None, ''

    def _rollout_restart_on_cluster(
        self,
        name: str,
        namespace: str,
        cluster_name: str,
        region: str,
        role_arn: str = "",
        wait: bool = False,
        wait_timeout_sec: int = 180,
    ) -> tuple[bool, str, str, Optional[bool], str]:
        err = _switch_eks_cluster(cluster_name, region, role_arn=role_arn or None)
        if err:
            return False, err, 'deployment', None, ''
        ok, output, kind, wait_ok, wait_output = self._restart_k8s_workload(
            name, namespace, wait=wait, wait_timeout_sec=wait_timeout_sec,
        )
        return ok, output, kind, wait_ok, wait_output

    def handle_rollout_restart_deployment(self, data):
        items = data.get('deployments')
        if isinstance(items, list) and len(items) > 1:
            self.handle_rollout_restart_deployments(data)
            return
        if isinstance(items, list) and len(items) == 1:
            data = {**data, **items[0]}

        name = (data.get('deployment') or data.get('name') or '').strip()
        namespace = (data.get('namespace') or 'default').strip()
        wait = bool(data.get('waitForRollout', True))
        try:
            wait_timeout_sec = int(data.get('rolloutTimeoutSec') or 180)
        except Exception:
            wait_timeout_sec = 180
        if not name:
            self._send_json(400, {'ok': False, 'error': 'deployment name is required'})
            return

        clusters = self._resolve_restart_clusters(data)
        orig_ctx = self._current_context()
        results: list[dict] = []
        try:
            for cluster in clusters:
                cluster_name = cluster['name']
                region = cluster['region']
                role_arn = cluster.get('roleArn') or ''
                ok, output, kind, wait_ok, wait_output = self._rollout_restart_on_cluster(
                    name, namespace, cluster_name, region, role_arn=role_arn,
                    wait=wait, wait_timeout_sec=wait_timeout_sec,
                )
                results.append({
                    'deployment': name,
                    'namespace': namespace,
                    'cluster': cluster_name,
                    'region': region,
                    'kind': kind,
                    'waitEnabled': wait,
                    'rolloutReady': wait_ok,
                    'rolloutStatus': wait_output,
                    'ok': ok,
                    'output': output,
                })
                self._audit_activity(
                    "deployment.restart",
                    {
                        "deployment": name,
                        "namespace": namespace,
                        "cluster": cluster_name,
                        "region": region,
                        "ok": ok,
                    },
                    target=f"{cluster_name}:{namespace}/{name}",
                )
        finally:
            _use_kubectl_context(orig_ctx)
            _invalidate_resource_caches()

        ok_count = sum(1 for r in results if r.get('ok'))
        if len(results) > 1:
            self._audit_activity(
                "deployment.restart_multi_cluster",
                {
                    "deployment": name,
                    "namespace": namespace,
                    "clusters": [r['cluster'] for r in results],
                    "ok": ok_count,
                    "failed": len(results) - ok_count,
                },
                target=f"{namespace}/{name}",
            )

        if len(results) == 1:
            r = results[0]
            self._send_json(200, {
                'ok': r['ok'],
                'output': r['output'],
                'kind': r.get('kind') or 'deployment',
                'waitEnabled': r.get('waitEnabled'),
                'rolloutReady': r.get('rolloutReady'),
                'rolloutStatus': r.get('rolloutStatus', ''),
                'deployment': name,
                'namespace': namespace,
                'cluster': r['cluster'],
                'region': r['region'],
            })
            return

        self._send_json(200, {
            'ok': ok_count == len(results),
            'deployment': name,
            'namespace': namespace,
            'total': len(results),
            'okCount': ok_count,
            'failedCount': len(results) - ok_count,
            'results': results,
        })

    def handle_rollout_restart_deployments(self, data):
        raw_items = data.get('deployments') or []
        if not raw_items:
            self._send_json(400, {'ok': False, 'error': 'deployments list is required'})
            return
        wait = bool(data.get('waitForRollout', True))
        try:
            wait_timeout_sec = int(data.get('rolloutTimeoutSec') or 180)
        except Exception:
            wait_timeout_sec = 180

        clusters = self._resolve_restart_clusters(data)
        orig_ctx = self._current_context()
        results: list[dict] = []
        try:
            for cluster in clusters:
                cluster_name = cluster['name']
                region = cluster['region']
                role_arn = cluster.get('roleArn') or ''
                err = _switch_eks_cluster(cluster_name, region, role_arn=role_arn or None)
                if err:
                    for item in raw_items:
                        name = (item.get('deployment') or item.get('name') or '').strip()
                        namespace = (item.get('namespace') or 'default').strip()
                        results.append({
                            'deployment': name,
                            'namespace': namespace,
                            'cluster': cluster_name,
                            'region': region,
                            'ok': False,
                            'output': err,
                        })
                    continue
                for item in raw_items:
                    name = (item.get('deployment') or item.get('name') or '').strip()
                    namespace = (item.get('namespace') or 'default').strip()
                    if not name:
                        results.append({
                            'deployment': '',
                            'namespace': namespace,
                            'cluster': cluster_name,
                            'region': region,
                            'ok': False,
                            'output': 'deployment name is required',
                        })
                        continue
                    ok, output, workload_kind, wait_ok, wait_out = self._restart_k8s_workload(
                        name, namespace, wait=wait, wait_timeout_sec=wait_timeout_sec,
                    )
                    results.append({
                        'deployment': name,
                        'namespace': namespace,
                        'cluster': cluster_name,
                        'region': region,
                        'kind': workload_kind,
                        'waitEnabled': wait,
                        'rolloutReady': wait_ok,
                        'rolloutStatus': wait_out,
                        'ok': ok,
                        'output': str(output)[:500],
                    })
                    self._audit_activity(
                        "deployment.restart",
                        {
                            "deployment": name,
                            "namespace": namespace,
                            "cluster": cluster_name,
                            "region": region,
                            "ok": ok,
                            "batch": True,
                        },
                        target=f"{cluster_name}:{namespace}/{name}",
                    )
        finally:
            _use_kubectl_context(orig_ctx)
            _invalidate_resource_caches()

        ok_count = sum(1 for r in results if r.get('ok'))
        cluster_names = sorted({r.get('cluster') for r in results if r.get('cluster')})
        self._audit_activity(
            "deployment.restart_batch",
            {
                "total": len(results),
                "ok": ok_count,
                "failed": len(results) - ok_count,
                "clusters": cluster_names,
                "deployments": [f"{r['cluster']}:{r['namespace']}/{r['deployment']}" for r in results[:100]],
            },
        )
        self._send_json(200, {
            'ok': ok_count == len(results),
            'total': len(results),
            'okCount': ok_count,
            'failedCount': len(results) - ok_count,
            'clusters': cluster_names,
            'results': results,
        })

    def handle_describe_configmap(self, data):
        name = data.get('name') or data.get('configmap')
        namespace = data.get('namespace', 'default')
        if not name:
            self.send_response(400)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'ConfigMap name is required')
            return
        output = self.kubectl_cmd(['describe', 'configmap', name, '-n', namespace])
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

    def handle_terminal_session(self, data):
        pod = data.get('pod')
        namespace = data.get('namespace', 'default')
        container = data.get('container')
        command = data.get('command', '')
        
        print(f"Terminal session: pod={pod}, ns={namespace}, cmd='{command}'")
        
        if not pod:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Pod name required')
            return
        
        try:
            cmd = ['kubectl', 'exec', pod, '-n', namespace]
            if container:
                cmd.extend(['-c', container])

            if command.strip():
                cmd.extend(['--', 'bash', '-c', f'cd /; {command}; echo "COMMAND_DONE"'])
                print(f"Executing: {' '.join(cmd)}")
            else:
                cmd.extend(['--', 'bash', '-c', 'pwd; echo "Connected to $(hostname)"'])

            result = _run_cmd(cmd, timeout=10)
            print(f"Command result: returncode={result.returncode}")
            print(f"Stdout: {result.stdout}")
            print(f"Stderr: {result.stderr}")
            
            if result.returncode == 0:
                output = result.stdout
                if command.strip():
                    # Remove the COMMAND_DONE marker
                    output = output.replace('COMMAND_DONE\n', '').replace('COMMAND_DONE', '')
                    output += '\n$ '
                else:
                    output += '\n$ '
            else:
                output = f"Error: {result.stderr}\n$ "
                
        except subprocess.TimeoutExpired:
            output = "Command timed out\n$ "
            print("Command timed out")
        except Exception as e:
            output = f"Error: {str(e)}\n$ "
            print(f"Exception: {e}")
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

    def handle_exec_pod(self, data):
        pod = data.get('pod')
        namespace = data.get('namespace', 'default')
        command = (data.get('command') or '').strip()
        container = data.get('container')
        try:
            timeout_sec = int(data.get('timeoutSec') or 45)
        except Exception:
            timeout_sec = 45
        
        if not pod or not command:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Pod name and command required')
            return
        
        try:
            # Fast validation: return clear error when pod is wrong/old.
            exists = _run_cmd(['kubectl', 'get', 'pod', pod, '-n', namespace, '-o', 'name'], timeout=12)
            if exists.returncode != 0:
                msg = (exists.stderr or exists.stdout or '').strip() or f'pod/{pod} not found'
                self._audit_activity(
                    "terminal.exec",
                    {
                        "pod": pod,
                        "namespace": namespace,
                        "ok": False,
                        "reason": "pod not found in namespace",
                    },
                    target=f"{namespace}/{pod}",
                )
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(f"Error: pod not found in namespace: {msg}".encode())
                return

            # Keep interactive troubleshooting responsive for network calls.
            safe_command = command
            if command.startswith('curl') and '--max-time' not in command:
                safe_command = command.replace('curl', 'curl --connect-timeout 5 --max-time 15', 1)

            cmd = ['kubectl', 'exec', pod, '-n', namespace]
            if container:
                cmd.extend(['-c', container])
            cmd.extend(['--', 'sh', '-c', safe_command])
            timeout_sec = max(10, min(timeout_sec, 120))
            # Retry once for transient timeout/network reset.
            attempt_errors: list[str] = []
            result = None
            for attempt in range(2):
                try:
                    result = _run_cmd(cmd, timeout=timeout_sec)
                    break
                except subprocess.TimeoutExpired:
                    attempt_errors.append('timeout')
                    if attempt == 0:
                        continue
                    raise
                except Exception as e:
                    msg = str(e)
                    attempt_errors.append(msg)
                    if attempt == 0 and any(t in msg.lower() for t in ('connection reset', 'i/o timeout', 'temporarily unavailable')):
                        continue
                    raise
            
            output = ((result.stdout or '') if result else '').strip()
            stderr = ((result.stderr or '') if result else '').strip()
            if stderr:
                output += (('\n' if output else '') + f"STDERR:\n{stderr}")
            if result and result.returncode != 0:
                output += f"\nExit code: {result.returncode}"
                likely = ''
                low = stderr.lower()
                if 'not found' in low:
                    likely = 'Likely cause: command binary is missing in the container.'
                elif 'permission denied' in low:
                    likely = 'Likely cause: permission denied inside the container.'
                elif 'timed out' in low or 'timeout' in low:
                    likely = 'Likely cause: upstream network call timed out.'
                elif 'connection refused' in low:
                    likely = 'Likely cause: target service/port is not listening.'
                if likely:
                    output += f"\n{likely}"
            if not output:
                output = "(No output)"

            masked = re.sub(r'(?i)(password|passwd|token|secret|apikey|api_key)\s*[=:]\s*\S+', r'\1=***', command)
            self._audit_activity(
                "terminal.exec",
                {
                    "pod": pod,
                    "namespace": namespace,
                    "ok": bool(result and result.returncode == 0),
                    "command": masked[:240],
                },
                target=f"{namespace}/{pod}",
            )
                
        except subprocess.TimeoutExpired:
            output = f"Command timed out after {timeout_sec} seconds. Try a lighter command or add curl --max-time 10"
        except Exception as e:
            output = f"Error executing command: {str(e)}"
        
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(output.encode())

    def format_table(self, output, resource_type="", default_namespace="default"):
        describe_fn_map = {
            'svc': 'describeSvc',
            'ingress': 'describeIngress',
            'configmap': 'describeConfigMap',
        }
        lines = output.strip().split('\n')
        if len(lines) > 1:
            headers = lines[0].split()
            html = (
                '<table class="table table-sm table-hover table-striped align-middle mb-0 resource-table">'
                '<thead class="table-light"><tr>'
                + ''.join(f'<th scope="col">{_html_escape(h)}</th>' for h in headers)
            )
            if resource_type:
                html += '<th scope="col">Actions</th>'
            html += '</tr></thead><tbody>'

            all_namespaces = len(headers) > 1 and headers[0].upper() == 'NAMESPACE'

            for line in lines[1:]:
                cols = line.split()
                if not cols:
                    continue
                namespace = cols[0] if all_namespaces else default_namespace
                name = cols[1] if all_namespaces else cols[0]
                row_key = f"{namespace}/{name}" if all_namespaces else name
                html += f'<tr class="resource-row" data-resource-key="{_html_escape(row_key)}" role="button" tabindex="0">'
                html += ''.join(f'<td>{_html_escape(c)}</td>' for c in cols)
                if resource_type:
                    safe_name = _html_escape(name).replace("'", "\\'")
                    safe_ns = _html_escape(namespace).replace("'", "\\'")
                    fn = describe_fn_map.get(resource_type, f'describe{resource_type.title()}')
                    html += (
                        f'<td class="text-nowrap">'
                        f'<button type="button" class="btn btn-3d btn-3d-primary btn-sm" '
                        f'onclick="event.stopPropagation(); {fn}(\'{safe_name}\', \'{safe_ns}\')">'
                        f'<i class="bi bi-card-text"></i> Describe</button></td>'
                    )
                html += '</tr>'
            html += '</tbody></table>'
        else:
            html = '<p class="text-muted mb-0 px-2 py-3">No resources found</p>'
        return html


def _port_available(port: int) -> bool:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(('0.0.0.0', port))
        return True
    except OSError:
        return False


def _describe_port_holders(port: int) -> str:
    lines: list[str] = []
    for cmd in (
        ['ss', '-tlnp'],
        ['fuser', '-v', f'{port}/tcp'],
    ):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            output = ((result.stdout or '') + (result.stderr or '')).strip()
            if output and str(port) in output:
                lines.append(f"$ {' '.join(cmd)}\n{output}")
        except Exception:
            continue
    if not lines:
        return f"(run as root: ss -tlnp | grep :{port})"
    return '\n\n'.join(lines)


def _exit_port_in_use(port: int) -> None:
    import sys
    print(f"\nERROR: Port {port} is already in use — cannot start pod-server.", flush=True)
    print('--- What is using the port? ---', flush=True)
    print(_describe_port_holders(port), flush=True)
    print(
        '\nFix:\n'
        f'  cd {_POD_DIR}\n'
        '  bash start-pod-server.sh kill-port\n'
        '  bash start-pod-server.sh restart\n'
        '\nIf systemd is installed:\n'
        '  systemctl stop pod-server 2>/dev/null || true\n'
        '\nDo NOT run: python3 pod-server.py  (use start-pod-server.sh instead)\n',
        flush=True,
    )
    sys.exit(1)


if __name__ == '__main__':
    import sys
    if os.environ.get('POD_MANAGED_START') != '1':
        print(
            'ERROR: Do not run pod-server.py directly — it causes port conflicts.\n'
            f'  cd {_POD_DIR}\n'
            '  bash start-pod-server.sh start      # start in background\n'
            '  bash start-pod-server.sh status     # check status\n'
            '  bash start-pod-server.sh restart    # restart\n',
            flush=True,
        )
        sys.exit(1)

    pod_rbac.load_auth_environment()

    port = int(os.environ.get('POD_PORT', '8080'))

    pod_singleton.acquire()
    if not _port_available(port):
        _exit_port_in_use(port)

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True
        allow_reuse_address = False

    try:
        server = ThreadedHTTPServer(('0.0.0.0', port), PodManagementHandler)
    except OSError as exc:
        if getattr(exc, 'errno', None) == 98:
            _exit_port_in_use(port)
        raise
    server.allow_reuse_address = False
    print(f"[startup] bound to port {port} (pid {os.getpid()})", flush=True)

    try:
        os.environ.setdefault("POD_VERSION_ENV", "comcast")
        os.environ.setdefault("POD_VERSION_CACHE_TTL", "45")
        os.environ.setdefault("POD_VERSION_REFRESH_SEC", "45")

        def _boot_cluster() -> str:
            try:
                result = _run_cmd(["kubectl", "config", "current-context"], timeout=15)
                return _parse_cluster_from_context((result.stdout or "").strip())
            except Exception:
                return ""

        version_cache.init_db()
        pod_rbac.init_db()
        pod_rbac.ensure_session_schema()
        pod_rbac.persist_auth_defaults()
        if pod_rbac.sync_admin_password_from_env():
            pass  # logged inside sync_admin_password_from_env
        elif not (os.environ.get("POD_AUTH_PASSWORD") or "").strip():
            print("[auth] WARNING: POD_AUTH_PASSWORD not set — admin password will not be reset on restart", flush=True)
        _load_persisted_active_cluster()
        cluster_boot_err = _ensure_active_cluster_context()
        if cluster_boot_err:
            print(f"[cluster] kubectl not ready yet: {cluster_boot_err[:240]}", flush=True)
        elif (_ACTIVE_CLUSTER.get("name") or "").strip():
            print(
                f"[cluster] kubectl context: {_ACTIVE_CLUSTER['name']} "
                f"({_ACTIVE_CLUSTER.get('region') or _DEFAULT_AWS_REGION})",
                flush=True,
            )
        boot_cluster = _display_cluster_name()
        for sid, url in get_version_overrides().items():
            print(f"[version_api] configured: {sid} -> {url}")
        try:
            n = version_cache.refresh_all(boot_cluster)
            print(f"[version_cache] initial refresh: {n} service(s) for cluster {boot_cluster or 'default'}")
        except Exception as exc:
            print(f"[version_cache] initial refresh skipped: {exc}")
        version_cache.start_background_refresh(_boot_cluster)

        auth_msg = pod_auth.startup_message()
        if auth_msg:
            print(f"[auth] {auth_msg}")
        print(f"[rbac] database: {pod_rbac.db_path()}")
        print(f"Pod Management Portal running at http://0.0.0.0:{port}")
        if pod_auth.is_enabled():
            print(f"Login page: http://0.0.0.0:{port}/login")
        print(f"Version API environment: {os.environ.get('POD_VERSION_ENV', 'comcast')}")
        print(f"Version cache: refresh every {version_cache.cache_refresh_sec()}s, TTL {version_cache.cache_ttl_sec()}s")
        print(f"Resource cache TTLs: {pod_cache.startup_summary()}")
        print(f"Pods kubectl timeout: {_PODS_KUBECTL_TIMEOUT}s")
        if validator_integration.enabled():
            vcfg = validator_integration.client_config()
            vhealth = validator_integration.check_upstream()
            print(
                f"[validator] upstream={vcfg['upstream']} ok={vhealth.get('ok')} "
                f"public={vcfg['iframeUrl']}",
                flush=True,
            )
            if validator_integration.auto_start() and not vhealth.get("ok"):
                started = validator_integration.try_start_validator(_POD_DIR)
                print(f"[validator] auto-start: {started}", flush=True)
        else:
            print("[validator] embed disabled (POD_VALIDATOR_ENABLED=0)", flush=True)

        def _warm_caches() -> None:
            try:
                cluster = _boot_cluster() or "default"
                _refresh_pods_cache(cluster)
                print(f"[pods_cache] warmed for cluster {cluster}", flush=True)
                _refresh_deployments_cache(cluster)
                print(f"[deployments_cache] warmed for cluster {cluster}", flush=True)
                _refresh_nodes_cache(cluster)
                print(f"[nodes_cache] warmed for cluster {cluster}", flush=True)
            except Exception as exc:
                print(f"[cache] warm skipped: {exc}", flush=True)

        threading.Thread(target=_warm_caches, daemon=True).start()
        server.serve_forever()
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
