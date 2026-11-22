"""Central cache TTL configuration and shared cache helpers for pod-server."""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Optional

_CLUSTER_CACHE: dict[str, Any] = {"at": 0.0, "payload": None, "lock": threading.Lock()}
_TRAFFIC_CACHE: dict[str, dict[str, Any]] = {}
_TRAFFIC_LOCK = threading.Lock()
_HTML_CACHES: dict[str, dict[str, dict[str, Any]]] = {}
_HTML_LOCK = threading.Lock()


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.environ.get(name, str(default))))
    except (TypeError, ValueError):
        return default


def pods_ttl() -> int:
    return _int_env("POD_PODS_CACHE_TTL", 45)


def deployments_ttl() -> int:
    legacy = os.environ.get("POD_RESOURCE_CACHE_TTL")
    default = int(legacy) if legacy else 90
    return _int_env("POD_DEPLOYMENTS_CACHE_TTL", default)


def nodes_ttl() -> int:
    legacy = os.environ.get("POD_RESOURCE_CACHE_TTL")
    default = int(legacy) if legacy else 180
    return _int_env("POD_NODES_CACHE_TTL", default)


def service_pods_ttl() -> int:
    return _int_env("POD_SERVICE_CACHE_TTL", 90)


def k8s_html_ttl() -> int:
    return _int_env("POD_K8S_HTML_CACHE_TTL", 120)


def traffic_ttl() -> int:
    return _int_env("POD_TRAFFIC_CACHE_TTL", 300)


def clusters_ttl() -> int:
    return _int_env("POD_CLUSTERS_CACHE_TTL", 300)


def config_for_client() -> dict[str, int]:
    """TTL and suggested frontend refresh intervals (seconds) for the dashboard."""
    return {
        "podsTtlSec": pods_ttl(),
        "podsRefreshSec": 90,
        "deploymentsTtlSec": deployments_ttl(),
        "deploymentsRefreshSec": 180,
        "nodesTtlSec": nodes_ttl(),
        "nodesRefreshSec": 300,
        "servicePodsTtlSec": service_pods_ttl(),
        "allServicesRefreshSec": 180,
        "versionPollSec": 180,
        "k8sHtmlTtlSec": k8s_html_ttl(),
        "k8sHtmlRefreshSec": 240,
        "trafficTtlSec": traffic_ttl(),
        "trafficRefreshSec": 600,
        "clustersTtlSec": clusters_ttl(),
    }


def startup_summary() -> str:
    return (
        f"pods={pods_ttl()}s deployments={deployments_ttl()}s nodes={nodes_ttl()}s "
        f"service-pods={service_pods_ttl()}s k8s-html={k8s_html_ttl()}s "
        f"traffic={traffic_ttl()}s clusters={clusters_ttl()}s"
    )


def invalidate_html_and_meta() -> None:
    with _HTML_LOCK:
        _HTML_CACHES.clear()
    with _CLUSTER_CACHE["lock"]:
        _CLUSTER_CACHE["at"] = 0.0
        _CLUSTER_CACHE["payload"] = None
    with _TRAFFIC_LOCK:
        _TRAFFIC_CACHE.clear()


def _html_store(resource: str) -> dict[str, dict[str, Any]]:
    with _HTML_LOCK:
        if resource not in _HTML_CACHES:
            _HTML_CACHES[resource] = {}
        return _HTML_CACHES[resource]


def cached_kubectl_html(
    resource: str,
    cache_key: str,
    ttl_sec: int,
    force_refresh: bool,
    fetch_fn: Callable[[], tuple[str, Optional[str]]],
) -> tuple[str, bool, bool, int]:
    """Return (html, cached, stale, cache_age_sec)."""
    store = _html_store(resource)
    now = time.time()
    entry = store.get(cache_key)

    if not force_refresh and entry and entry.get("html") is not None:
        age = now - float(entry.get("at") or 0)
        if age < ttl_sec:
            return str(entry["html"]), True, False, int(age)
        if not entry.get("refreshing"):
            entry["refreshing"] = True

            def _background() -> None:
                try:
                    html, err = fetch_fn()
                    if not err:
                        entry["html"] = html
                        entry["error"] = None
                        entry["at"] = time.time()
                    else:
                        entry["error"] = err
                finally:
                    entry["refreshing"] = False

            threading.Thread(target=_background, daemon=True).start()
        return str(entry["html"]), True, True, int(age)

    html, err = fetch_fn()
    if err and entry and entry.get("html"):
        return str(entry["html"]), True, True, int(now - float(entry.get("at") or 0))
    store[cache_key] = {
        "html": html,
        "at": time.time(),
        "error": err,
        "refreshing": False,
    }
    return html, False, False, 0


def get_cluster_payload(ttl_sec: int, force_refresh: bool, build_fn: Callable[[], dict]) -> tuple[dict, bool, int]:
    now = time.time()
    with _CLUSTER_CACHE["lock"]:
        cached = _CLUSTER_CACHE.get("payload")
        age = now - float(_CLUSTER_CACHE.get("at") or 0)
        if not force_refresh and cached is not None and age < ttl_sec:
            return dict(cached), True, int(age)
    payload = build_fn()
    with _CLUSTER_CACHE["lock"]:
        _CLUSTER_CACHE["payload"] = payload
        _CLUSTER_CACHE["at"] = time.time()
    return payload, False, 0


def get_traffic_payload(
    cache_key: str,
    ttl_sec: int,
    force_refresh: bool,
    fetch_fn: Callable[[], dict],
) -> tuple[dict, bool, int]:
    now = time.time()
    with _TRAFFIC_LOCK:
        entry = _TRAFFIC_CACHE.get(cache_key)
        if not force_refresh and entry and now - float(entry.get("at") or 0) < ttl_sec:
            return dict(entry["payload"]), True, int(now - float(entry["at"] or 0))
    payload = fetch_fn()
    with _TRAFFIC_LOCK:
        _TRAFFIC_CACHE[cache_key] = {"payload": payload, "at": time.time()}
    return payload, False, 0
