"""AI Infrastructure Validator — config and health for Pod dashboard embed."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def upstream_base() -> str:
    raw = (os.environ.get("POD_VALIDATOR_UPSTREAM") or "http://127.0.0.1:5000").strip()
    return raw.rstrip("/")


def public_base(host_header: str = "", scheme: str = "http") -> str:
    explicit = (os.environ.get("POD_VALIDATOR_PUBLIC_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    port = (os.environ.get("POD_VALIDATOR_PORT") or "5000").strip()
    host = (host_header or "127.0.0.1").split(",")[0].strip()
    if ":" in host and not host.startswith("["):
        host = host.split(":", 1)[0]
    return f"{scheme}://{host}:{port}"


def enabled() -> bool:
    return os.environ.get("POD_VALIDATOR_ENABLED", "1").strip().lower() not in ("0", "false", "no")


def auto_start() -> bool:
    return os.environ.get("POD_VALIDATOR_AUTO_START", "0").strip().lower() in ("1", "true", "yes")


def check_upstream(timeout: float = 3.0) -> dict[str, Any]:
    base = upstream_base()
    url = f"{base}/api/version"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip().startswith("{") else {}
            return {
                "ok": True,
                "upstream": base,
                "name": data.get("name") or "Validator",
                "version": data.get("version") or "",
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "upstream": base, "error": f"HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "upstream": base, "error": str(exc) or "unreachable"}


def client_config(host_header: str = "", scheme: str = "http") -> dict[str, Any]:
    health = check_upstream()
    pub = public_base(host_header, scheme)
    return {
        "enabled": enabled(),
        "iframeUrl": f"{pub}/",
        "openUrl": f"{pub}/",
        "upstream": upstream_base(),
        "upstreamOk": bool(health.get("ok")),
        "upstreamError": health.get("error") or "",
        "validatorVersion": health.get("version") or "",
        "autoStart": auto_start(),
        "features": [
            "iam_inventory",
            "service_inventory",
            "service_quotas",
            "connections",
            "admin",
        ],
    }


def try_start_validator(root_dir: str) -> dict[str, Any]:
    """Best-effort background start when POD_VALIDATOR_AUTO_START=1."""
    if not auto_start():
        return {"started": False, "reason": "auto_start_disabled"}
    if check_upstream().get("ok"):
        return {"started": False, "reason": "already_running"}
    validator_dir = os.path.join(root_dir, "..", "validator")
    run_sh = os.path.join(validator_dir, "run.sh")
    if not os.path.isfile(run_sh):
        return {"started": False, "reason": "validator/run.sh not found", "path": run_sh}
    import subprocess

    log = os.path.join(validator_dir, "validator-autostart.log")
    try:
        with open(log, "a", encoding="utf-8") as out:
            subprocess.Popen(
                ["bash", run_sh],
                cwd=validator_dir,
                stdout=out,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        return {"started": True, "log": log}
    except OSError as exc:
        return {"started": False, "reason": str(exc)}


def guess_request_scheme(headers: dict[str, str]) -> str:
    proto = (headers.get("X-Forwarded-Proto") or headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    if proto in ("http", "https"):
        return proto
    return "https" if os.environ.get("POD_VALIDATOR_HTTPS", "").strip() in ("1", "true") else "http"
