"""Fetch service version from /internal/config for pod dashboard cards."""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_SEMVER = re.compile(r"\d+\.\d+\.\d+")
_POD_DIR = Path(__file__).resolve().parent

# Built-in fallback if service_version_overrides.json is missing on disk.
_DEFAULT_VERSION_OVERRIDES: dict[str, str] = {
    "advisor": "https://advisor.comcast.arlocloud.com/advisor/internal/config",
    "oc-accounts-service": "https://oc-accounts.comcast.arlocloud.com/oc-accounts-service/status",
    "oauth": "https://oauth.6a5cc08e4a58.arlo.com/oauth/internal/config",
    "oauth-proxy": "https://api.6a5cc08e4a58.arlo.com/oauth-proxy/internal/config",
    "oauth-proxy-staging": "https://api-staging.6a5cc08e4a58.arlo.com/oauth-proxy/internal/config",
    "broker-service": "https://broker-service.comcast.arlocloud.com/broker-service/internal/config",
    "arlosafelocations": "http://safelocations.comcast.arlocloud.com/version",
    "arloautomation-leader": "https://arloautomation-leader.comcast.arlocloud.com/automation/version",
    "hmsautomation": "https://arloautomation.comcast.arlocloud.com/automation/version",
    "backend-hmsautomation": "https://arloautomation.comcast.arlocloud.com/automation/version",
    "hmsautomation-scheduler": "https://arloautomation-scheduler.comcast.arlocloud.com/automation/version",
    "hmsautomation-job": "https://arloautomation-job.comcast.arlocloud.com/automation/version",
    "backend-hmsautomation-job": "https://arloautomation-job.comcast.arlocloud.com/automation/version",
    "arlosafeapi": "https://safeapi.comcast.arlocloud.com/version",
    "device-authentication": "https://device-authentication.comcast.arlocloud.com/device-authentication/internal/config",
    "device-location": "https://device-location.6a5cc08e4a58.arloxcld.com/device-location/internal/config",
    "directory": "https://directory.comcast.arlocloud.com/directory/internal/config",
    "discovery": "https://discovery.comcast.arlocloud.com/discovery/internal/config",
    "geolocation": "https://geolocation.comcast.arlocloud.com/geolocation/internal/config",
    "history": "https://history.comcast.arlocloud.com/history/internal/config",
    "hmsam": "https://hmsam.comcast.arlocloud.com/hmsam/version",
    "hmsapi": "https://hmsapi.comcast.arlocloud.com/hmsapi/version",
    "hmsclientauth": "https://myapi.6a5cc08e4a58.arlo.com/hmsclientauth/version",
    "hmscsapi": "https://myapi.6a5cc08e4a58.arlo.com/hmscsapi/version",
    "hmscspubsub": "https://myapi.6a5cc08e4a58.arlo.com/hmscspubsub/version",
    "hmsdeviceevent": "https://deviceapi.6a5cc08e4a58.messaging.arlo.com/hmsdeviceevent/version",
    "hmsfeeds": "https://myapi.6a5cc08e4a58.arlo.com/hmsfeeds/version",
    "hmsguard": "https://myapi.6a5cc08e4a58.arlo.com/hmsguard/version",
    "hmspubsub": "https://myapi.6a5cc08e4a58.arlo.com/hmspubsub/version",
    "nginx-deviceapi": "https://deviceapi.6a5cc08e4a58.messaging.arlo.com/hmsweb/version",
    "ngx-dvcapi": "https://deviceapi.6a5cc08e4a58.messaging.arlo.com/hmsweb/version",
    "hmsalexaapi": "https://alexaapi.comcast.arlocloud.com/hmsalexaapi/version",
    "hmsgoogleapi": "http://googleapi.comcast.arlocloud.com/hmsgoogleapi/version",
    "hmsdeviceshadow": "http://hmsdeviceshadow.comcast.arlocloud.com/hmsdeviceshadow/version",
    "hmsentityauth": "http://hmsentityauth.comcast.arlocloud.com/version",
    "hmsdevicemanagement": "http://hmsentityauth.comcast.arlocloud.com/version",
    "hmsreportingservice": "http://hmsreportingservice.comcast.arlocloud.com/version",
    "hmsvideoverification": "https://hmsvideoverification.comcast.arlocloud.com/videoverification/version",
    "hmsifttt": "http://ifttt.comcast.arlocloud.com/hmsifttt/version",
    "partnerplatform": "http://partnerplatform.comcast.arlocloud.com/partnerplatform/version",
    "partnerplatform-staging": "http://partnerplatform-staging.comcast.arlocloud.com/partnerplatform/version",
    "hmspayment": "http://paymentapi.comcast.arlocloud.com/hmspayment/version",
    "partner-notifications": "https://partner-notifications.comcast.arlocloud.com/partner-notifications/version",
    "partner-proxy": "https://partner-proxy.comcast.arlocloud.com/partner-proxy/internal/config",
    "privacy-policy": "https://policy.comcast.arlocloud.com/policy/internal/config",
    "secret-manager": "https://secret-manager.comcast.arlocloud.com/secret-manager/internal/config",
    "mqtt-auth": "https://auth.comcast.arlocloud.com/mqtt-auth/internal/config",
    "logger": "https://logger.comcast.arlocloud.com/logger/internal/config",
    "log-server": "https://deviceapi.6a5cc08e4a58.messaging.arlo.com/log-server/version",
    "messaging": "https://messaging.comcast.arlocloud.com/messaging/internal/config",
    "presence": "https://presence.6a5cc08e4a58.arloxcld.com/presence/internal/config",
    "registration": "https://registration.6a5cc08e4a58.arloxcld.com/registration/internal/config",
    "policy": "https://policy.comcast.arlocloud.com/policy/internal/config",
    "support": "https://support.comcast.arlocloud.com/support/internal/config",
    "mediamigrationscheduler": "https://mediamigrationscheduler.comcast.arlocloud.com/mediamigrationscheduler/version",
    "hmsnotification": "https://pn.comcast.arlocloud.com/hmsnotification/version",
    "hmsweb-device": "https://my.6a5cc08e4a58.arlo.com/hmsdevice/version",
    "hmsweb-media": "https://my.6a5cc08e4a58.arlo.com/hmsmedia/version",
    "hmsweb-web": "https://my.6a5cc08e4a58.arlo.com/hmsweb/version",
    "hmsdeviceauth": "https://deviceapi.6a5cc08e4a58.messaging.arlo.com/hmsdeviceauth/version",
}

# K8s / legacy service ids → override key (same Version API URL).
_SERVICE_VERSION_ALIASES: dict[str, str] = {
    "goog": "arlosafelocations",
    "backend-hmsautomation": "hmsautomation",
    "backend-hmsautomation-job": "hmsautomation-job",
    "hmsdeviceevents": "hmsdeviceevent",
    "device-nginx": "nginx-deviceapi",
    "ngx-dvcapi": "nginx-deviceapi",
    "privacy-policy": "policy",
    "payment": "hmspayment",
}

# Multi-key version JSON: K8s service id → key in /version response body.
_VERSION_JSON_KEY_ALIASES: dict[str, str] = {
    "hmsnotification": "hmsnotifications",
}


def _resolve_version_service_id(service_id: str) -> str:
    sid = (service_id or "").strip().lower()
    return _SERVICE_VERSION_ALIASES.get(sid, sid)


def _version_json_keys_for_service(service_id: str) -> list[str]:
    """Ordered keys to match service-specific version in multi-key JSON bodies."""
    keys: list[str] = []
    sid = _resolve_version_service_id(service_id)
    raw = (service_id or "").strip().lower()
    for k in (sid, raw):
        if k and k not in keys:
            keys.append(k)
        mapped = _VERSION_JSON_KEY_ALIASES.get(k)
        if mapped and mapped not in keys:
            keys.append(mapped)
    return keys


def _valid_version_url(url: str) -> bool:
    text = (url or "").strip()
    return bool(text) and text.upper() != "NA" and text.lower().startswith(("http://", "https://"))


def _kubeconfig_path() -> str:
    return os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))


def _run_kubectl(args: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["KUBECONFIG"] = _kubeconfig_path()
    try:
        return subprocess.run(["kubectl", *args], capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            args=["kubectl", *args],
            returncode=124,
            stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            stderr=f"kubectl timed out after {timeout}s",
        )


def _catalog_path() -> Path | None:
    explicit = os.environ.get("POD_VERSION_CATALOG", "").strip()
    if explicit:
        path = Path(explicit)
        return path if path.is_file() else None
    for candidate in (
        _POD_DIR / "data" / "service_version_catalog.json",
        _POD_DIR.parent / "validator" / "data" / "service_version_catalog.json",
    ):
        if candidate.is_file():
            return candidate
    return None


def load_catalog() -> dict[str, Any]:
    path = _catalog_path()
    if not path:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _version_overrides() -> dict[str, str]:
    """Per-service version API URLs (defaults + env + data/service_version_overrides.json)."""
    merged = {k.lower(): v.strip() for k, v in _DEFAULT_VERSION_OVERRIDES.items() if _valid_version_url(v)}
    raw_env = os.environ.get("POD_VERSION_URLS", "").strip()
    if raw_env:
        try:
            data = json.loads(raw_env)
            if isinstance(data, dict):
                merged.update({
                    str(k).lower(): str(v).strip()
                    for k, v in data.items()
                    if _valid_version_url(str(v))
                })
        except json.JSONDecodeError:
            pass
    for candidate in (_POD_DIR / "data" / "service_version_overrides.json",):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            services = data.get("services") if isinstance(data, dict) else data
            if isinstance(services, dict):
                merged.update({
                    str(k).lower(): str(v).strip()
                    for k, v in services.items()
                    if _valid_version_url(str(v))
                })
        except Exception:
            pass
    return merged


def get_version_overrides() -> dict[str, str]:
    """Public accessor for configured version API URLs."""
    return dict(_version_overrides())


def _find_catalog_service(catalog: dict[str, Any], service_id: str) -> dict[str, Any] | None:
    sid = (service_id or "").strip().lower()
    for svc in catalog.get("services") or []:
        if str(svc.get("id", "")).lower() == sid or str(svc.get("name", "")).lower() == sid:
            return svc
    return None


def parse_version_text(raw: str, service_id: str = "") -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _SEMVER.search(text)
        if match:
            return match.group(0)
        if len(text) < 64 and not text.startswith("<"):
            return text
        return ""
    if isinstance(data, str):
        val = data.strip()
        return val if _SEMVER.search(val) else val
    if isinstance(data, dict):
        for key in (
            "version", "buildVersion", "appVersion", "release", "serviceVersion",
            "status", "message",
        ):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, (int, float)):
                return str(val)
        sid = _resolve_version_service_id(service_id)
        for candidate in _version_json_keys_for_service(service_id):
            val = data.get(candidate)
            if isinstance(val, str) and val.strip():
                return val.strip()
            if isinstance(val, (int, float)):
                return str(val)
    return ""


def _version_config_for_display(
    config: dict[str, Any] | None,
    service_id: str,
    version: str,
) -> dict[str, Any] | None:
    if not config:
        return config
    sid = _resolve_version_service_id(service_id)
    if any(key in config for key in (
        "version", "buildVersion", "appVersion", "release", "serviceVersion", "status", "message",
    )):
        return config
    for key in _version_json_keys_for_service(service_id):
        if key in config:
            return {"name": key, "version": str(config[key])}
    if sid in config:
        return {"name": sid, "version": str(config[sid])}
    if version:
        return {"name": sid or service_id, "version": version}
    return config


def _version_raw_for_display(
    body: str,
    service_id: str,
    config: dict[str, Any] | None,
) -> str:
    if config:
        return json.dumps(config, indent=2)
    parsed = _parse_config_body(body)
    if not parsed:
        return body
    sid = _resolve_version_service_id(service_id)
    for key in _version_json_keys_for_service(service_id):
        if key in parsed:
            return json.dumps({key: parsed[key]}, indent=2)
    if sid in parsed:
        return json.dumps({sid: parsed[sid]}, indent=2)
    return body


def _version_url(catalog: dict[str, Any], cat_svc: dict[str, Any], environment: str) -> str:
    by_env = cat_svc.get("versionUrlByEnvironment") or {}
    if environment in by_env:
        return str(by_env[environment]).strip()
    if cat_svc.get("versionUrl"):
        return str(cat_svc["versionUrl"]).strip()

    defaults = catalog.get("defaults") or {}
    template = str(defaults.get("versionPathTemplate") or "/{service}/internal/config")
    scheme = str(defaults.get("httpScheme") or "https")
    host_template = str(defaults.get("hostnameTemplate") or "{service}.{environment}.arlocloud.com")
    service_id = str(cat_svc.get("id") or "")
    host = host_template.format(service=service_id, environment=environment, env=environment)
    path = template.format(service=service_id, environment=environment, env=environment)
    return f"{scheme}://{host}{path}"


def _friendly_version_error(err: str) -> str:
    text = (err or "").strip()
    if not text:
        return "Version unavailable"
    lower = text.lower()
    if "name or service not known" in lower or "errno -2" in lower or "getaddrinfo failed" in lower or "urlopen error" in lower:
        return "In-cluster fetch failed — check kubectl exec"
    if "timed out" in lower or "timeout" in lower:
        return "Version API timed out"
    if text.startswith("HTTP "):
        return text
    if len(text) > 72:
        return text[:69] + "…"
    return text


def _http_fetch_body(url: str, timeout: float = 8.0) -> tuple[str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "EKSense-PodDashboard/1.0",
        },
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8", errors="replace"), ""
    except urllib.error.HTTPError as exc:
        return "", f"HTTP {exc.code}"
    except Exception as exc:
        return "", str(exc)[:160]


def _http_fetch_version(url: str, timeout: float = 8.0, service_id: str = "") -> tuple[str, str]:
    body, err = _http_fetch_body(url, timeout)
    if err:
        return "", err
    version = parse_version_text(body, service_id)
    if version:
        return version, ""
    return "", "No version in response"


def _is_comcast_url(url: str) -> bool:
    return ".comcast." in (url or "").lower()


def _is_configured_version_url(url: str) -> bool:
    """True when URL is an external version endpoint (not localhost/in-cluster)."""
    u = (url or "").strip().lower()
    if not u.startswith(("http://", "https://")):
        return False
    return "127.0.0.1" not in u and "localhost" not in u


def _is_arloxcld_url(url: str) -> bool:
    return ".arloxcld.com" in (url or "").lower()


def _skip_incluster_for_url(url: str) -> bool:
    """Skip kubectl exec probes only when POD_VERSION_SKIP_INCLUSTER=1."""
    return os.environ.get("POD_VERSION_SKIP_INCLUSTER", "").strip().lower() in ("1", "true", "yes")


def get_version_aliases() -> dict[str, str]:
    return dict(_SERVICE_VERSION_ALIASES)


def _allow_external_http(
    catalog: dict[str, Any],
    cluster_hint: str = "",
    *,
    prefer_http: bool = False,
    url: str = "",
) -> bool:
    if url and (_is_comcast_url(url) or _is_configured_version_url(url)):
        return True
    if prefer_http:
        return True
    if _prefer_incluster_first(catalog, cluster_hint):
        return False
    return True


def _in_cluster_paths(service_id: str, version_url: str = "") -> list[str]:
    """Local pod paths to probe; prefers path from configured Comcast URL."""
    paths: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        if path and path not in seen:
            seen.add(path)
            paths.append(path)

    url = (version_url or "").strip()
    if url:
        try:
            parsed = urlparse(url)
            req_path = (parsed.path or "").strip()
            if req_path:
                for port in (8080, 80):
                    add(f"http://127.0.0.1:{port}{req_path}")
                    add(f"http://localhost:{port}{req_path}")
        except Exception:
            pass

    sid = (service_id or "").lower()
    if "automation" in sid or "/automation/" in url.lower():
        for port in (8080, 80):
            add(f"http://127.0.0.1:{port}/automation/version")
            add(f"http://localhost:{port}/automation/version")

    for port in (8080, 80):
        add(f"http://127.0.0.1:{port}/{service_id}/internal/config")
        add(f"http://127.0.0.1:{port}/internal/config")
        add(f"http://localhost:{port}/{service_id}/internal/config")
        add(f"http://localhost:{port}/internal/config")

    return paths


def _exec_version_in_pod(ns: str, pod: str, service_id: str, version_url: str = "") -> tuple[str, str]:
    paths = _in_cluster_paths(service_id, version_url)
    cmd_tpl = (
        'wget -qO- "{path}" 2>/dev/null || '
        'curl -sf "{path}" 2>/dev/null || '
        'curl -sfk "{path}" 2>/dev/null'
    )
    for path in paths:
        script = cmd_tpl.format(path=path)
        result = _run_kubectl(
            ["exec", "-n", ns, pod, "--", "sh", "-c", script],
            timeout=25,
        )
        if result.returncode != 0:
            continue
        body = (result.stdout or "").strip()
        if body and parse_version_text(body, service_id):
            return body, "in-cluster"
    return "", ""


def _discover_running_pods(service_id: str, namespaces: list[str]) -> list[tuple[str, str]]:
    sid = service_id.lower()
    prefix = f"{sid}-"
    found: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(ns: str, pod: str) -> None:
        key = (ns, pod)
        if key not in seen:
            seen.add(key)
            found.append(key)

    selectors = [
        f"app.kubernetes.io/name={service_id}",
        f"app={service_id}",
        f"name={service_id}",
    ]
    ns_filter = set(namespaces) if namespaces else None

    for selector in selectors:
        scope = ["get", "pods"]
        if ns_filter:
            for ns in ns_filter:
                result = _run_kubectl(
                    [*scope, "-n", ns, "-l", selector,
                     "--field-selector=status.phase=Running",
                     "-o", "jsonpath={.items[0].metadata.name}"],
                    timeout=6,
                )
                pod = (result.stdout or "").strip()
                if pod:
                    add(ns, pod)
        else:
            result = _run_kubectl(
                [*scope, "-A", "-l", selector,
                 "--field-selector=status.phase=Running",
                 "-o", "jsonpath={range .items[*]}{.metadata.namespace}{\"\\t\"}{.metadata.name}{\"\\n\"}{end}"],
                timeout=8,
            )
            for line in (result.stdout or "").splitlines():
                parts = line.strip().split("\t", 1)
                if len(parts) == 2:
                    add(parts[0], parts[1])

    if not found:
        ns_list = list(ns_filter) if ns_filter else []
        if not ns_list:
            ns_list = ["xcloud", "default"]
        if sid not in [n.lower() for n in ns_list]:
            ns_list = [sid, *ns_list]
        for ns in ns_list:
            result = _run_kubectl(
                [
                    "get", "pods", "-n", ns,
                    "--field-selector=status.phase=Running",
                    "-o", "jsonpath={range .items[*]}{.metadata.name}{\"\\n\"}{end}",
                ],
                timeout=6,
            )
            for pod in (result.stdout or "").splitlines():
                pod = pod.strip()
                if pod.lower().startswith(prefix) or pod.lower() == sid:
                    add(ns, pod)
                    break

    return found[:1]


def _fetch_version_for_service(
    service_id: str,
    url: str,
    namespaces: list[str],
) -> tuple[str, str, str]:
    """Returns (version, source, error). arloxcld → in-cluster first; HTTP fallback."""
    ns = list(namespaces or [])
    http_err = ""

    if url and _is_arloxcld_url(url) and not _skip_incluster_for_url(url):
        version, source = _in_cluster_fetch(service_id, ns, url)
        if version:
            return version, source, ""

    if url:
        version, http_err = _http_fetch_version(url, timeout=12.0, service_id=service_id)
        if version:
            return version, "http", ""

    if not _skip_incluster_for_url(url):
        version, source = _in_cluster_fetch(service_id, ns, url)
        if version:
            return version, source, ""

    return "", "http" if url else "in-cluster", _friendly_version_error(
        http_err or "Version API unreachable",
    )


def _in_cluster_fetch_body(
    service_id: str,
    namespaces: list[str],
    version_url: str = "",
) -> tuple[str, str, str]:
    for ns, pod in _discover_running_pods(service_id, list(namespaces or [])):
        body, source = _exec_version_in_pod(ns, pod, service_id, version_url)
        if body:
            return body, source, ""
    return "", "", "In-cluster version API unreachable"


def _in_cluster_fetch(
    service_id: str,
    namespaces: list[str],
    version_url: str = "",
) -> tuple[str, str]:
    body, source, _ = _in_cluster_fetch_body(service_id, namespaces, version_url)
    if body:
        return parse_version_text(body, service_id), source
    return "", ""


def _parse_config_body(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def resolve_version_environment(catalog: dict[str, Any], cluster_hint: str = "") -> str:
    explicit = os.environ.get("POD_VERSION_ENV", "").strip()
    if explicit:
        return explicit
    return "comcast"


def _prefer_incluster_first(catalog: dict[str, Any], cluster_hint: str = "") -> bool:
    flag = os.environ.get("POD_VERSION_INCLUSTER_FIRST", "").strip().lower()
    if flag in ("1", "true", "yes"):
        return True
    if flag in ("0", "false", "no"):
        return False
    return resolve_version_environment(catalog, cluster_hint) == "comcast"


def list_version_catalog_entries(
    catalog: dict[str, Any] | None = None,
    *,
    cluster_hint: str = "",
) -> list[dict[str, str]]:
    """All services with a version API URL (catalog + overrides)."""
    cat = catalog if catalog is not None else load_catalog()
    seen: dict[str, dict[str, str]] = {}
    for svc in cat.get("services") or []:
        sid = str(svc.get("id") or "").strip()
        if not sid:
            continue
        meta = catalog_service_meta(cat, sid, cluster_hint=cluster_hint)
        url = str(meta.get("versionUrl") or "")
        if ".partnercat." in url.lower():
            continue
        if url:
            seen[sid.lower()] = {
                "id": sid,
                "name": str(svc.get("name") or sid),
                "versionUrl": url,
            }
    for sid, url in _version_overrides().items():
        if not url:
            continue
        prev = seen.get(sid) or {}
        seen[sid] = {
            "id": prev.get("id") or sid,
            "name": prev.get("name") or sid,
            "versionUrl": url,
        }
    return list(seen.values())


def catalog_service_meta(
    catalog: dict[str, Any],
    service_id: str,
    *,
    cluster_hint: str = "",
) -> dict[str, Any]:
    sid = _resolve_version_service_id(service_id)
    overrides = _version_overrides()
    if sid in overrides:
        url = overrides[sid]
        return {"hasVersionApi": bool(url), "versionUrl": url}
    # Allow lookup by original id when alias target is configured
    orig = (service_id or "").strip().lower()
    if orig != sid and orig in overrides:
        url = overrides[orig]
        return {"hasVersionApi": bool(url), "versionUrl": url}

    cat_svc = _find_catalog_service(catalog, service_id)
    if not cat_svc:
        cat_svc = _find_catalog_service(catalog, sid)
    if not cat_svc:
        return {"hasVersionApi": False, "versionUrl": ""}
    environment = resolve_version_environment(catalog, cluster_hint)
    url = _version_url(catalog, cat_svc, environment)
    if ".partnercat." in url.lower():
        url = url.lower().replace(".partnercat.", ".comcast.")
    return {"hasVersionApi": bool(url), "versionUrl": url}


def fetch_version_api_detail(
    catalog: dict[str, Any],
    service_id: str,
    namespaces: list[str] | None = None,
    *,
    prefer_http: bool = False,
    cluster_hint: str = "",
) -> dict[str, Any]:
    base = catalog_service_meta(catalog, service_id, cluster_hint=cluster_hint)
    url = str(base.get("versionUrl") or "")
    if not base.get("hasVersionApi"):
        return {
            "ok": False,
            "serviceId": service_id,
            "version": "",
            "versionUrl": "",
            "versionSource": "",
            "versionError": "No version API configured for this service",
            "config": None,
            "raw": "",
        }

    ns_list = list(namespaces or [])
    body = ""
    source = ""
    err = ""
    use_http = _allow_external_http(catalog, cluster_hint, prefer_http=prefer_http, url=url)

    if url and _is_arloxcld_url(url) and not _skip_incluster_for_url(url):
        body, source, ic_err = _in_cluster_fetch_body(service_id, ns_list, url)
        if body:
            err = ""
        elif ic_err:
            err = ic_err

    if not body and use_http and url:
        http_body, http_err = _http_fetch_body(url, timeout=12.0)
        if http_body:
            body, source, err = http_body, "http", ""
        elif not err:
            err = _friendly_version_error(http_err)

    if not body and not _skip_incluster_for_url(url):
        body, source, ic_err = _in_cluster_fetch_body(service_id, ns_list, url)
        if body:
            err = ""
        elif ic_err and not err:
            err = ic_err

    if not body and use_http and url and not _is_configured_version_url(url):
        http_body, http_err = _http_fetch_body(url, timeout=12.0)
        if http_body:
            body, source, err = http_body, "http", ""
        else:
            err = _friendly_version_error(http_err or err)

    if not body:
        return {
            "ok": False,
            "serviceId": service_id,
            "version": "",
            "versionUrl": url,
            "versionSource": source or "in-cluster",
            "versionError": _friendly_version_error(err or "Version API unreachable"),
            "config": None,
            "raw": "",
        }

    version = parse_version_text(body, service_id)
    config = _version_config_for_display(_parse_config_body(body), service_id, version)
    raw_display = _version_raw_for_display(body, service_id, config)
    if not version and not config:
        return {
            "ok": False,
            "serviceId": service_id,
            "version": "",
            "versionUrl": url,
            "versionSource": source,
            "versionError": "No version in response",
            "config": None,
            "raw": raw_display,
        }

    return {
        "ok": True,
        "serviceId": service_id,
        "version": version,
        "versionUrl": url,
        "versionSource": source,
        "versionError": "",
        "config": config,
        "raw": raw_display,
    }


def fetch_service_version(
    catalog: dict[str, Any],
    service_id: str,
    namespaces: list[str] | None = None,
    *,
    cluster_hint: str = "",
) -> dict[str, Any]:
    base = catalog_service_meta(catalog, service_id, cluster_hint=cluster_hint)
    if not base.get("hasVersionApi"):
        return {"version": "", "versionSource": "", "versionUrl": "", "versionError": "", "hasVersionApi": False}

    url = str(base.get("versionUrl") or "")
    ns_list = list(namespaces or [])
    version, source, err = _fetch_version_for_service(service_id, url, ns_list)
    if version:
        return {**base, "version": version, "versionSource": source, "versionError": ""}

    return {
        **base,
        "version": "",
        "versionSource": source or "http",
        "versionError": err or "Version unavailable",
    }


def enrich_services_with_versions(
    services: list[dict[str, Any]],
    *,
    cluster_hint: str = "",
) -> None:
    catalog = load_catalog()
    if not catalog or not services:
        return

    overrides = _version_overrides()
    catalog_ids = {
        str(s.get("id", "")).lower()
        for s in catalog.get("services") or []
        if s.get("id")
    }
    catalog_ids.update(overrides.keys())
    targets = [svc for svc in services if str(svc.get("id", "")).lower() in catalog_ids]
    if not targets:
        return

    max_workers = min(8, max(1, len(targets)))

    def _apply(svc: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        meta = fetch_service_version(
            catalog, svc["id"], svc.get("namespaces") or [], cluster_hint=cluster_hint,
        )
        return svc["id"], meta

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [pool.submit(_apply, svc) for svc in targets]
        results = {}
        for future in as_completed(futures):
            try:
                sid, meta = future.result()
                results[sid] = meta
            except Exception as exc:
                continue

    for svc in targets:
        meta = results.get(svc["id"], {})
        if not meta.get("versionUrl"):
            meta = {**catalog_service_meta(catalog, svc["id"], cluster_hint=cluster_hint), **meta}
        svc.update(meta)
