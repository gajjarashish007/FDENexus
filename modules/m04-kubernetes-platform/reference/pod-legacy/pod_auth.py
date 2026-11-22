"""Session-based login for the pod dashboard (integrated with pod_rbac)."""
from __future__ import annotations

import os
import secrets
import threading
import time
from typing import Any, Optional, Tuple, Dict

import pod_rbac

SESSION_COOKIE = "pod_session"
_DEFAULT_USER = "admin"
_SESSION_LOCK = threading.Lock()
_SESSIONS: dict[str, dict[str, Any]] = {}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def is_enabled() -> bool:
    pod_rbac.load_auth_environment()
    if _env_bool("POD_AUTH_ENABLED", False):
        return True
    if (os.environ.get("POD_AUTH_PASSWORD") or "").strip():
        return True
    try:
        users = pod_rbac.list_users()
        return len(users) > 0
    except Exception:
        return False


def configured_username() -> str:
    return (os.environ.get("POD_AUTH_USER") or _DEFAULT_USER).strip() or _DEFAULT_USER


def _env_password() -> str:
    return os.environ.get("POD_AUTH_PASSWORD") or ""


def session_ttl_sec() -> int:
    try:
        hours = float(os.environ.get("POD_AUTH_SESSION_HOURS", "24"))
    except ValueError:
        hours = 24.0
    return max(300, int(hours * 3600))


def _purge_expired_memory() -> None:
    now = time.time()
    expired = [token for token, meta in _SESSIONS.items() if meta.get("expires_at", 0) <= now]
    for token in expired:
        _SESSIONS.pop(token, None)


def _purge_expired_db() -> None:
    try:
        pod_rbac.purge_expired_auth_sessions()
    except Exception:
        pass


def _session_meta_from_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "role": row["role"],
        "created_at": row.get("created_at"),
        "expires_at": row["expires_at"],
    }


def _user_from_meta(meta: dict[str, Any]) -> Dict[str, Any]:
    user_id = meta.get("user_id") or 0
    username = meta.get("username") or configured_username()
    role = meta.get("role") or pod_rbac.ROLE_SUPER_ADMIN
    return {
        "id": int(user_id) if user_id else 0,
        "username": username,
        "displayName": username,
        "role": role,
    }


def _ensure_db_session(token: str, meta: dict[str, Any]) -> None:
    """Re-create session row if memory is valid but SQLite row is missing."""
    try:
        pod_rbac.ensure_session_schema()
        row = pod_rbac.get_auth_session(token)
        if row and row.get("expires_at", 0) > time.time():
            return
        pod_rbac.upsert_auth_session(
            token,
            int(meta["user_id"]),
            str(meta.get("username") or configured_username()),
            str(meta.get("role") or pod_rbac.ROLE_SUPER_ADMIN),
            float(meta.get("expires_at") or (time.time() + session_ttl_sec())),
        )
    except Exception as exc:
        print(f"[auth] ensure db session failed: {exc}", flush=True)


def _load_session_meta(token: str) -> Optional[dict[str, Any]]:
    now = time.time()
    with _SESSION_LOCK:
        _purge_expired_memory()
        meta = _SESSIONS.get(token)
        if meta and meta.get("expires_at", 0) > now:
            _ensure_db_session(token, meta)
            return meta

    try:
        pod_rbac.ensure_session_schema()
        row = pod_rbac.get_auth_session(token)
    except Exception as exc:
        print(f"[auth] session DB lookup failed: {exc}", flush=True)
        with _SESSION_LOCK:
            meta = _SESSIONS.get(token)
            if meta and meta.get("expires_at", 0) > now:
                return meta
        return None

    if not row or row.get("expires_at", 0) <= now:
        if row:
            try:
                pod_rbac.delete_auth_session(token)
            except Exception:
                pass
        with _SESSION_LOCK:
            _SESSIONS.pop(token, None)
        return None

    meta = _session_meta_from_row(row)
    with _SESSION_LOCK:
        _SESSIONS[token] = meta
    return meta


def login(username: str, password: str) -> Tuple[Optional[str], Optional[str]]:
    if not is_enabled():
        return None, "Authentication is not configured"
    pod_rbac.load_auth_environment()
    pod_rbac.ensure_session_schema()
    if _env_password().strip():
        try:
            pod_rbac.sync_admin_password_from_env()
        except Exception:
            pass
    user = pod_rbac.authenticate(username, password)
    if not user:
        return None, "Invalid username or password"
    token = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + session_ttl_sec()
    meta = {
        "user_id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "created_at": now,
        "expires_at": expires_at,
    }
    with _SESSION_LOCK:
        _purge_expired_memory()
        _SESSIONS[token] = meta
    try:
        pod_rbac.upsert_auth_session(
            token,
            int(user["id"]),
            user["username"],
            user["role"],
            expires_at,
        )
    except Exception as exc:
        with _SESSION_LOCK:
            _SESSIONS.pop(token, None)
        print(f"[auth] login session persist failed: {exc}", flush=True)
        return None, "Could not create session — check RBAC database permissions"
    return token, None


def logout(token: Optional[str]) -> None:
    if not token:
        return
    with _SESSION_LOCK:
        _SESSIONS.pop(token, None)
    try:
        pod_rbac.delete_auth_session(token)
    except Exception:
        pass


def touch_session(token: Optional[str]) -> bool:
    """Extend session expiry (sliding window). Never invalidates a valid session."""
    if not token:
        return False
    meta = _load_session_meta(token)
    if not meta:
        return False
    expires_at = time.time() + session_ttl_sec()
    try:
        pod_rbac.ensure_session_schema()
        if not pod_rbac.touch_auth_session(token, expires_at):
            _ensure_db_session(token, {**meta, "expires_at": expires_at})
    except Exception as exc:
        print(f"[auth] touch session failed (ignored): {exc}", flush=True)
    with _SESSION_LOCK:
        if token in _SESSIONS:
            _SESSIONS[token]["expires_at"] = expires_at
    return True


def validate_session(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    meta = _load_session_meta(token)
    if not meta:
        return None
    fallback = _user_from_meta(meta)
    user_id = meta.get("user_id")
    if not user_id:
        return fallback
    try:
        user = pod_rbac.get_user_by_id(int(user_id))
    except Exception as exc:
        print(f"[auth] user lookup failed (using session meta): {exc}", flush=True)
        return fallback
    if not user:
        return fallback
    if not user.get("active"):
        logout(token)
        return None
    return {
        "id": user["id"],
        "username": user["username"],
        "displayName": user.get("displayName") or user["username"],
        "role": user["role"],
    }


def is_public_path(method: str, path: str) -> bool:
    path = (path or "").split("?", 1)[0].rstrip("/") or "/"
    if path in ("/login", "/login.html", "/api/health", "/pod-base.js"):
        return True
    if path.startswith("/api/auth/login") and method.upper() == "POST":
        return True
    if path == "/api/auth/logout" and method.upper() == "POST":
        return True
    return False


def startup_message() -> Optional[str]:
    if not is_enabled():
        return (
            "Authentication DISABLED — set POD_AUTH_PASSWORD or run init to create admin user "
            "before exposing this server publicly"
        )
    try:
        pod_rbac.ensure_session_schema()
    except Exception as exc:
        return f"Authentication WARNING — session schema: {exc}"
    users = pod_rbac.list_users()
    admins = [u for u in users if u.get("role") == pod_rbac.ROLE_SUPER_ADMIN]
    return (
        f"Authentication enabled — {len(users)} user(s), {len(admins)} super admin(s), "
        f"persistent session {session_ttl_sec() // 3600}h"
    )
