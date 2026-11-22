"""RBAC: users, roles, module permissions, and audit logs (SQLite)."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_POD_DIR = Path(__file__).resolve().parent
_DEFAULT_DB = _POD_DIR / "data" / "rbac.db"
_FALLBACK_DB = Path.home() / ".pod-dashboard" / "rbac.db"
_RBAC_DB_MARKER = _POD_DIR / "data" / ".rbac_db_path"
_AUTH_DEFAULTS_FILE = _POD_DIR / "data" / "auth.defaults"
_db_path_cache: Optional[Path] = None
_auth_env_loaded = False


def _parse_env_line(line: str) -> Optional[tuple[str, str]]:
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[7:].strip()
    if "=" not in line:
        return None
    key, _, val = line.partition("=")
    key = key.strip()
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
        val = val[1:-1]
    if not key:
        return None
    return key, val


def _load_env_file(path: Path) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        parsed = _parse_env_line(line)
        if not parsed:
            continue
        key, val = parsed
        if key.startswith("POD_"):
            existing = os.environ.get(key)
            if key == "POD_AUTH_PASSWORD" and not (existing or "").strip():
                os.environ[key] = val
            else:
                os.environ.setdefault(key, val)


def load_auth_environment(*, force: bool = False) -> None:
    """Load POD_AUTH_* / POD_RBAC_DB from persisted files so login works after any restart."""
    global _auth_env_loaded, _db_path_cache
    if _auth_env_loaded and not force:
        return
    if force:
        _db_path_cache = None
    for env_file in (
        _POD_DIR / ".pod-dashboard.env",
        Path.home() / ".pod-dashboard.env",
        _AUTH_DEFAULTS_FILE,
    ):
        if env_file.is_file():
            _load_env_file(env_file)
    if _RBAC_DB_MARKER.is_file():
        try:
            marked = _RBAC_DB_MARKER.read_text(encoding="utf-8").strip()
            if marked:
                marked_path = Path(marked)
                if not marked_path.is_absolute():
                    marked_path = (_POD_DIR / marked_path).resolve()
                try:
                    under_pod = marked_path.resolve().is_relative_to(_POD_DIR.resolve())
                except (OSError, ValueError):
                    under_pod = False
                # Ignore absolute markers from another checkout/machine.
                if marked_path.is_absolute() and not under_pod and not marked_path.exists():
                    print(
                        f"[rbac] WARNING: ignoring stale RBAC marker {marked_path} — using local default",
                        flush=True,
                    )
                else:
                    os.environ.setdefault("POD_RBAC_DB", str(marked_path))
        except OSError:
            pass
    rbac_env = (os.environ.get("POD_RBAC_DB") or "").strip()
    if rbac_env:
        marked_path = Path(rbac_env)
        if not marked_path.is_absolute():
            marked_path = (_POD_DIR / marked_path).resolve()
            os.environ["POD_RBAC_DB"] = str(marked_path)
        try:
            under_pod = marked_path.resolve().is_relative_to(_POD_DIR.resolve())
        except (OSError, ValueError):
            under_pod = False
        # If configured path is outside this install and missing, fall back.
        if marked_path.is_absolute() and not under_pod and not marked_path.exists():
            print(
                f"[rbac] WARNING: POD_RBAC_DB={marked_path} is not usable — falling back to {_DEFAULT_DB}",
                flush=True,
            )
            os.environ["POD_RBAC_DB"] = str(_DEFAULT_DB)
            marked_path = _DEFAULT_DB
        if _db_path_cache is None or _db_path_cache.resolve() != marked_path.resolve():
            _db_path_cache = marked_path
    _auth_env_loaded = True


def persist_auth_defaults() -> Path:
    """Write auth.defaults + rbac db marker (called from start-pod-server.sh)."""
    load_auth_environment(force=True)
    data_dir = _POD_DIR / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db = db_path()
    user = (os.environ.get("POD_AUTH_USER") or "admin").strip() or "admin"
    password = os.environ.get("POD_AUTH_PASSWORD") or ""
    lines = [
        f"POD_AUTH_USER={user}",
        f"POD_RBAC_DB={db}",
    ]
    if password:
        lines.insert(1, f"POD_AUTH_PASSWORD={password}")
    try:
        _AUTH_DEFAULTS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.chmod(_AUTH_DEFAULTS_FILE, 0o600)
        _RBAC_DB_MARKER.write_text(str(db.resolve()), encoding="utf-8")
        os.chmod(_RBAC_DB_MARKER, 0o644)
    except OSError as exc:
        print(f"[rbac] WARNING: could not persist auth.defaults: {exc}", flush=True)
    return db


def _dir_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


def _path_writable(db_path: Path) -> bool:
    parent = db_path.parent
    if db_path.exists():
        return os.access(db_path, os.W_OK) and _dir_writable(parent)
    return _dir_writable(parent)


def _resolve_db_path() -> Path:
    load_auth_environment()
    env_path = (os.environ.get("POD_RBAC_DB") or "").strip()
    if env_path:
        return Path(env_path)
    if _path_writable(_DEFAULT_DB):
        return _DEFAULT_DB
    _FALLBACK_DB.parent.mkdir(parents=True, exist_ok=True)
    print(
        f"[rbac] WARNING: {_DEFAULT_DB.parent} is not writable — using {_FALLBACK_DB}",
        flush=True,
    )
    return _FALLBACK_DB


def db_path() -> Path:
    global _db_path_cache
    if _db_path_cache is None:
        _db_path_cache = _resolve_db_path()
    return _db_path_cache


def _use_db_path(path: Path) -> None:
    global _db_path_cache
    _db_path_cache = path

_LOCK = threading.RLock()

ROLE_SUPER_ADMIN = "super_admin"
ROLE_ADMIN = "admin"
ROLE_USER = "user"

ACTIONS = ("read", "create", "update", "delete")

MODULES: list[dict[str, str]] = [
    {"id": "dashboard", "label": "Cluster Overview", "section": "overview"},
    {"id": "all-services", "label": "All Services", "section": "all-services"},
    {"id": "pods", "label": "Pods", "section": "pods"},
    {"id": "nodes", "label": "Nodes", "section": "nodes"},
    {"id": "deployments", "label": "Deployments", "section": "deployments"},
    {"id": "services", "label": "K8s Services", "section": "services"},
    {"id": "ingress", "label": "Ingress", "section": "ingress"},
    {"id": "configmaps", "label": "ConfigMaps", "section": "configmaps"},
    {"id": "hpa", "label": "HPA", "section": "hpa"},
    {"id": "traffic-migration", "label": "Traffic Migration", "section": "traffic-migration"},
    {"id": "cleanup", "label": "Cleanup", "section": "cleanup"},
    {"id": "logs", "label": "Logs", "section": "logs"},
    {"id": "terminal", "label": "Terminal", "section": "terminal"},
    {"id": "validator", "label": "Infrastructure Validator", "section": "validator"},
    {"id": "admin", "label": "Admin Panel", "section": "admin"},
]

MODULE_IDS = {m["id"] for m in MODULES}


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
    except sqlite3.Error:
        pass
    return conn


def _hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return salt, digest.hex()


def _verify_password(password: str, salt: str, password_hash: str) -> bool:
    _, check = _hash_password(password, salt)
    return secrets.compare_digest(check, password_hash)


def init_db() -> None:
    try:
        _init_db_schema()
    except sqlite3.OperationalError as exc:
        if "readonly" not in str(exc).lower():
            raise
        current = db_path()
        fallback = _FALLBACK_DB
        if current.resolve() == fallback.resolve():
            raise RuntimeError(
                f"RBAC database is read-only at {current}. "
                f"Fix permissions or set POD_RBAC_DB to a writable path."
            ) from exc
        print(
            f"[rbac] Database read-only at {current} — switching to {fallback}",
            flush=True,
        )
        fallback.parent.mkdir(parents=True, exist_ok=True)
        _use_db_path(fallback)
        _init_db_schema()


def _init_db_schema() -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    display_name TEXT NOT NULL DEFAULT '',
                    password_salt TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_permissions (
                    user_id INTEGER NOT NULL,
                    module TEXT NOT NULL,
                    can_read INTEGER NOT NULL DEFAULT 0,
                    can_create INTEGER NOT NULL DEFAULT 0,
                    can_update INTEGER NOT NULL DEFAULT 0,
                    can_delete INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (user_id, module),
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_username TEXT NOT NULL,
                    target_username TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at DESC);
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    expires_at REAL NOT NULL,
                    last_seen_at REAL NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions(expires_at);
                """
            )
            conn.commit()
            _bootstrap_super_admin(conn)
            _sync_env_admin_password(conn)
        finally:
            conn.close()


def _env_password() -> str:
    """Return POD_AUTH_PASSWORD as-is (do not strip — spaces may be intentional)."""
    return os.environ.get("POD_AUTH_PASSWORD") or ""


def sync_admin_password_from_env() -> bool:
    """Create or update the super-admin user from POD_AUTH_USER / POD_AUTH_PASSWORD."""
    load_auth_environment()
    password = _env_password()
    if not password.strip():
        return False
    username = (os.environ.get("POD_AUTH_USER") or "admin").strip() or "admin"
    salt, pwd_hash = _hash_password(password)
    now = time.time()
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE users SET password_salt = ?, password_hash = ?, updated_at = ?, role = ?, active = 1
                    WHERE id = ?
                    """,
                    (salt, pwd_hash, now, ROLE_SUPER_ADMIN, row["id"]),
                )
                print(f"[rbac] synced admin password for '{username}' at {db_path()}", flush=True)
            else:
                conn.execute(
                    """
                    INSERT INTO users (username, display_name, password_salt, password_hash, role, active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    """,
                    (username, username, salt, pwd_hash, ROLE_SUPER_ADMIN, now, now),
                )
                print(f"[rbac] created super admin '{username}' from POD_AUTH_PASSWORD at {db_path()}", flush=True)
            conn.commit()
            return True
        finally:
            conn.close()


def _sync_env_admin_password(conn: sqlite3.Connection) -> None:
    """Keep super-admin password in sync with POD_AUTH_PASSWORD when set."""
    password = _env_password()
    username = (os.environ.get("POD_AUTH_USER") or "admin").strip() or "admin"
    if not password.strip():
        return
    row = conn.execute(
        "SELECT id FROM users WHERE username = ? COLLATE NOCASE",
        (username,),
    ).fetchone()
    salt, pwd_hash = _hash_password(password)
    now = time.time()
    if row:
        conn.execute(
            """
            UPDATE users SET password_salt = ?, password_hash = ?, updated_at = ?, role = ?, active = 1
            WHERE id = ?
            """,
            (salt, pwd_hash, now, ROLE_SUPER_ADMIN, row["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO users (username, display_name, password_salt, password_hash, role, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (username, username, salt, pwd_hash, ROLE_SUPER_ADMIN, now, now),
        )
    conn.commit()


def _bootstrap_super_admin(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    if row and row["n"] > 0:
        return
    username = (os.environ.get("POD_AUTH_USER") or "admin").strip() or "admin"
    password = _env_password()
    if not password.strip():
        password = secrets.token_urlsafe(12)
        print(f"[rbac] Created super admin '{username}' with generated password: {password}")
    else:
        print(f"[rbac] Created super admin '{username}' from POD_AUTH_PASSWORD")
    salt, pwd_hash = _hash_password(password)
    now = time.time()
    conn.execute(
        """
        INSERT INTO users (username, display_name, password_salt, password_hash, role, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 1, ?, ?)
        """,
        (username, username, salt, pwd_hash, ROLE_SUPER_ADMIN, now, now),
    )
    conn.commit()


def _user_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "displayName": row["display_name"] or row["username"],
        "role": row["role"],
        "active": bool(row["active"]),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def _env_admin_username() -> str:
    return (os.environ.get("POD_AUTH_USER") or "admin").strip() or "admin"


def env_admin_credentials_match(username: str, password: str) -> bool:
    """True when username/password match POD_AUTH_USER / POD_AUTH_PASSWORD."""
    load_auth_environment()
    env_pass = _env_password()
    if not env_pass.strip():
        return False
    if (username or "").strip().lower() != _env_admin_username().lower():
        return False
    try:
        return secrets.compare_digest(
            (password or "").encode("utf-8"),
            env_pass.encode("utf-8"),
        )
    except Exception:
        return False


def authenticate(username: str, password: str) -> Optional[Dict[str, Any]]:
    load_auth_environment()
    username = (username or "").strip()

    # POD_AUTH_PASSWORD / auth.defaults is the source of truth for the env admin account.
    if env_admin_credentials_match(username, password):
        try:
            sync_admin_password_from_env()
        except Exception as exc:
            print(f"[rbac] admin password sync on login failed: {exc}", flush=True)
        user = get_user_by_username(_env_admin_username())
        if user and user.get("active"):
            return user

    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
            if row and row["active"] and _verify_password(password, row["password_salt"], row["password_hash"]):
                return _user_row_to_dict(row)
        finally:
            conn.close()
    return None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            return _user_row_to_dict(row) if row else None
        finally:
            conn.close()


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                (username.strip(),),
            ).fetchone()
            return _user_row_to_dict(row) if row else None
        finally:
            conn.close()


def list_users(search: str = "") -> list[dict[str, Any]]:
    with _LOCK:
        conn = _connect()
        try:
            q = (search or "").strip().lower()
            if q:
                rows = conn.execute(
                    """
                    SELECT * FROM users
                    WHERE lower(username) LIKE ? OR lower(display_name) LIKE ?
                    ORDER BY username COLLATE NOCASE
                    """,
                    (f"%{q}%", f"%{q}%"),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE").fetchall()
            return [_user_row_to_dict(r) for r in rows]
        finally:
            conn.close()


def create_user(
    *,
    username: str,
    password: str,
    display_name: str = "",
    role: str = ROLE_USER,
    actor: dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    username = username.strip()
    if not username:
        return None, "Username is required"
    if len(password) < 6:
        return None, "Password must be at least 6 characters"
    if role not in (ROLE_USER, ROLE_ADMIN, ROLE_SUPER_ADMIN):
        return None, "Invalid role"
    if role == ROLE_SUPER_ADMIN and actor.get("role") != ROLE_SUPER_ADMIN:
        return None, "Only super admin can create super admin users"
    salt, pwd_hash = _hash_password(password)
    now = time.time()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO users (username, display_name, password_salt, password_hash, role, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (username, display_name or username, salt, pwd_hash, role, now, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                (username,),
            ).fetchone()
            user = _user_row_to_dict(row) if row else None
            if user:
                conn.execute(
                    """
                    INSERT INTO audit_logs (actor_username, target_username, action, details, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        actor.get("username") or "system",
                        user["username"],
                        "user.create",
                        json.dumps({"role": role}, default=str),
                        time.time(),
                    ),
                )
                conn.commit()
            return user, None
        except sqlite3.IntegrityError:
            return None, "Username already exists"
        except sqlite3.Error as exc:
            return None, f"Database error: {exc}"
        finally:
            conn.close()


def update_user(
    user_id: int,
    *,
    display_name: Optional[str] = None,
    role: Optional[str] = None,
    active: Optional[bool] = None,
    password: Optional[str] = None,
    actor: dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    target = get_user_by_id(user_id)
    if not target:
        return None, "User not found"
    if target["role"] == ROLE_SUPER_ADMIN and actor.get("role") != ROLE_SUPER_ADMIN:
        return None, "Cannot modify super admin"
    if actor.get("id") == user_id and role and role != target["role"]:
        return None, "Cannot change your own role"
    if actor.get("id") == user_id and active is False:
        return None, "Cannot deactivate yourself"
    if role == ROLE_SUPER_ADMIN and actor.get("role") != ROLE_SUPER_ADMIN:
        return None, "Only super admin can assign super admin role"
    fields: list[str] = []
    values: list[Any] = []
    if display_name is not None:
        fields.append("display_name = ?")
        values.append(display_name)
    if role is not None:
        fields.append("role = ?")
        values.append(role)
    if active is not None:
        fields.append("active = ?")
        values.append(1 if active else 0)
    if password:
        if len(password) < 6:
            return None, "Password must be at least 6 characters"
        salt, pwd_hash = _hash_password(password)
        fields.extend(["password_salt = ?", "password_hash = ?"])
        values.extend([salt, pwd_hash])
    if not fields:
        return target, None
    fields.append("updated_at = ?")
    values.append(time.time())
    values.append(user_id)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
            conn.commit()
            updated = get_user_by_id(user_id)
            log_audit(actor, target["username"], "user.update", {
                "before": target,
                "after": {k: updated.get(k) for k in ("displayName", "role", "active")} if updated else {},
            })
            return updated, None
        finally:
            conn.close()


def delete_user(user_id: int, *, actor: dict[str, Any]) -> Tuple[bool, Optional[str]]:
    target = get_user_by_id(user_id)
    if not target:
        return False, "User not found"
    if actor.get("id") == user_id:
        return False, "Cannot delete yourself"
    if target["role"] == ROLE_SUPER_ADMIN:
        return False, "Cannot delete super admin"
    actor_role = actor.get("role") or ROLE_USER
    if actor_role not in (ROLE_SUPER_ADMIN, ROLE_ADMIN):
        return False, "Insufficient permissions"
    if actor_role == ROLE_ADMIN and target["role"] == ROLE_ADMIN:
        return False, "Only super admin can delete admin users"
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
            if conn.total_changes == 0:
                return False, "User not found"
            conn.commit()
            log_audit(actor, target["username"], "user.delete", {
                "role": target.get("role"),
                "displayName": target.get("displayName"),
            })
            return True, None
        finally:
            conn.close()

    return {a: False for a in ACTIONS}


def _empty_permission() -> dict[str, bool]:
    return {a: False for a in ACTIONS}


def _full_permission() -> dict[str, bool]:
    return {a: True for a in ACTIONS}


def get_user_permissions(user_id: int) -> dict[str, dict[str, bool]]:
    user = get_user_by_id(user_id)
    if not user:
        return {}
    if user["role"] == ROLE_SUPER_ADMIN:
        return {mid: _full_permission() for mid in MODULE_IDS}
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                "SELECT * FROM user_permissions WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            result = {mid: _empty_permission() for mid in MODULE_IDS}
            for row in rows:
                mod = row["module"]
                if mod not in result:
                    continue
                result[mod] = {
                    "read": bool(row["can_read"]),
                    "create": bool(row["can_create"]),
                    "update": bool(row["can_update"]),
                    "delete": bool(row["can_delete"]),
                }
            if user["role"] == ROLE_ADMIN and not rows:
                return {mid: _full_permission() for mid in MODULE_IDS}
            return result
        finally:
            conn.close()


def set_user_permissions(
    user_id: int,
    permissions: dict[str, dict[str, bool]],
    *,
    actor: dict[str, Any],
) -> Tuple[bool, Optional[str]]:
    target = get_user_by_id(user_id)
    if not target:
        return False, "User not found"
    if target["role"] == ROLE_SUPER_ADMIN:
        return False, "Cannot set custom permissions for super admin"
    if actor.get("id") == user_id:
        return False, "Cannot modify your own permissions"
    before = get_user_permissions(user_id)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
            for module, perms in permissions.items():
                if module not in MODULE_IDS:
                    continue
                conn.execute(
                    """
                    INSERT INTO user_permissions (user_id, module, can_read, can_create, can_update, can_delete)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        module,
                        1 if perms.get("read") else 0,
                        1 if perms.get("create") else 0,
                        1 if perms.get("update") else 0,
                        1 if perms.get("delete") else 0,
                    ),
                )
            conn.commit()
            log_audit(actor, target["username"], "permissions.update", {
                "before": before,
                "after": permissions,
            })
            return True, None
        finally:
            conn.close()


def reset_user_permissions(user_id: int, *, actor: dict[str, Any]) -> Tuple[bool, Optional[str]]:
    target = get_user_by_id(user_id)
    if not target:
        return False, "User not found"
    if target["role"] == ROLE_SUPER_ADMIN:
        return False, "Cannot reset permissions for super admin"
    if actor.get("id") == user_id:
        return False, "Cannot reset your own permissions"
    before = get_user_permissions(user_id)
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
            conn.commit()
            log_audit(actor, target["username"], "permissions.reset", {"before": before})
            return True, None
        finally:
            conn.close()


def user_has_permission(user: dict[str, Any], module: str, action: str) -> bool:
    if not user:
        return False
    role = user.get("role") or ROLE_USER
    if role == ROLE_SUPER_ADMIN:
        return True
    if module not in MODULE_IDS:
        return False
    if action not in ACTIONS:
        return False
    perms = get_user_permissions(user["id"])
    mod_perms = perms.get(module, _empty_permission())
    return bool(mod_perms.get(action))


def permissions_for_client(user: dict[str, Any]) -> dict[str, Any]:
    perms = get_user_permissions(user["id"])
    sections = []
    for mod in MODULES:
        mp = perms.get(mod["id"], _empty_permission())
        if user.get("role") == ROLE_SUPER_ADMIN or mp.get("read"):
            if mod.get("section"):
                sections.append(mod["section"])
    return {
        "role": user.get("role"),
        "userId": user.get("id"),
        "modules": perms,
        "sections": sorted(set(sections)),
        "canManageUsers": user.get("role") in (ROLE_SUPER_ADMIN, ROLE_ADMIN),
    }


def log_audit(actor: dict[str, Any], target_username: str, action: str, details: dict[str, Any]) -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO audit_logs (actor_username, target_username, action, details, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    actor.get("username") or "system",
                    target_username or "",
                    action,
                    json.dumps(details, default=str),
                    time.time(),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def log_activity(
    actor: Optional[dict[str, Any]],
    action: str,
    details: Optional[dict[str, Any]] = None,
    *,
    target: str = "",
) -> None:
    """Record a user or system activity for the admin audit log."""
    actor = actor or {"username": "system", "role": "system"}
    log_audit(actor, target, action, details or {})


def list_audit_logs(
    limit: int = 100,
    *,
    action_prefix: str = "",
    actor: str = "",
    since: float = 0,
) -> list[dict[str, Any]]:
    limit = max(1, min(limit, 500))
    clauses = ["1=1"]
    params: list[Any] = []
    if action_prefix:
        clauses.append("action LIKE ?")
        params.append(f"{action_prefix}%")
    if actor:
        clauses.append("actor_username = ? COLLATE NOCASE")
        params.append(actor.strip())
    if since > 0:
        clauses.append("created_at >= ?")
        params.append(since)
    where = " AND ".join(clauses)
    params.append(limit)
    with _LOCK:
        conn = _connect()
        try:
            rows = conn.execute(
                f"SELECT * FROM audit_logs WHERE {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
            out = []
            for row in rows:
                try:
                    details = json.loads(row["details"] or "{}")
                except json.JSONDecodeError:
                    details = {}
                out.append({
                    "id": row["id"],
                    "actor": row["actor_username"],
                    "target": row["target_username"],
                    "action": row["action"],
                    "details": details,
                    "createdAt": row["created_at"],
                })
            return out
        finally:
            conn.close()


def resolve_route_permission(method: str, path: str) -> Optional[Tuple[str, str]]:
    """Map HTTP route to (module, action). None = auth-only, no module check."""
    p = (path or "").split("?", 1)[0].rstrip("/") or "/"
    m = (method or "GET").upper()

    if p.startswith("/api/auth/"):
        return None
    if p in ("/login", "/login.html", "/dashboard.html", "/", "/api/health"):
        return None

    if p.startswith("/api/admin"):
        if m == "GET":
            return "admin", "read"
        if m == "POST":
            admin_rest = p[len("/api/admin/"):].strip("/")
            admin_parts = [part for part in admin_rest.split("/") if part]
            if admin_parts == ["users"] or admin_parts == ["clusters"]:
                return "admin", "create"
            if len(admin_parts) >= 2 and admin_parts[0] == "users" and admin_parts[1].isdigit():
                return "admin", "update"
            # POST /api/admin/clusters/{id} — enable/disable/update existing cluster
            if len(admin_parts) >= 2 and admin_parts[0] == "clusters":
                return "admin", "update"
            return "admin", "create"
        if m in ("PUT", "PATCH"):
            return "admin", "update"
        if m == "DELETE":
            return "admin", "delete"
        return "admin", "read"

    post_actions: dict[str, tuple[str, str]] = {
        "/rollout-restart-deployment": ("deployments", "update"),
        "/rollout-restart-deployments": ("deployments", "update"),
        "/delete": ("pods", "delete"),
        "/cleanup": ("cleanup", "delete"),
        "/exec": ("terminal", "create"),
        "/kubectl-exec": ("terminal", "create"),
        "/execute": ("terminal", "create"),
        "/terminal-session": ("terminal", "create"),
        "/api/clusters/switch": ("dashboard", "update"),
        "/api/pods/multi-cluster": ("pods", "read"),
    }
    if m == "POST" and p in post_actions:
        return post_actions[p]

    prefix_modules: list[tuple[str, str]] = [
        ("/api/status", "dashboard"),
        ("/api/clusters", "dashboard"),
        ("/cluster-name", "dashboard"),
        ("/api/service-pods", "all-services"),
        ("/api/service-version/", "all-services"),
        ("/api/version-catalog", "all-services"),
        ("/api/version-config", "all-services"),
        ("/api/service-hide-list", "all-services"),
        ("/api/validator/", "validator"),
        ("/api/pods", "pods"),
        ("/pods", "pods"),
        ("/api/search", "dashboard"),
        ("/describe", "pods"),
        ("/logs", "logs"),
        ("/api/nodes", "nodes"),
        ("/nodes", "nodes"),
        ("/describe-node", "nodes"),
        ("/api/deployments", "deployments"),
        ("/deployments", "deployments"),
        ("/describe-deployment", "deployments"),
        ("/deployment-yaml", "deployments"),
        ("/services", "services"),
        ("/describe-svc", "services"),
        ("/ingress", "ingress"),
        ("/describe-ingress", "ingress"),
        ("/configmaps", "configmaps"),
        ("/describe-configmap", "configmaps"),
        ("/hpa", "hpa"),
        ("/api/traffic-migration", "traffic-migration"),
        ("/data/traffic_migration_hosts.json", "traffic-migration"),
        ("/namespaces", "dashboard"),
        ("/kubectl-version", "dashboard"),
        ("/exec", "terminal"),
        ("/troubleshoot", "terminal"),
        ("/portal", "terminal"),
        ("/terminal", "terminal"),
    ]
    for prefix, module in prefix_modules:
        if p.startswith(prefix):
            return module, "read"
    return "dashboard", "read"


def ensure_session_schema() -> None:
    """Ensure auth_sessions exists (safe on every request / startup)."""
    init_db()


def upsert_auth_session(
    token: str,
    user_id: int,
    username: str,
    role: str,
    expires_at: float,
) -> None:
    now = time.time()
    with _LOCK:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO auth_sessions (token, user_id, username, role, created_at, expires_at, last_seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(token) DO UPDATE SET
                    user_id = excluded.user_id,
                    username = excluded.username,
                    role = excluded.role,
                    expires_at = excluded.expires_at,
                    last_seen_at = excluded.last_seen_at
                """,
                (token, user_id, username, role, now, expires_at, now),
            )
            conn.commit()
        finally:
            conn.close()


def create_auth_session(
    token: str,
    user_id: int,
    username: str,
    role: str,
    expires_at: float,
) -> None:
    upsert_auth_session(token, user_id, username, role, expires_at)


def get_auth_session(token: str) -> Optional[dict[str, Any]]:
    with _LOCK:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT token, user_id, username, role, created_at, expires_at, last_seen_at FROM auth_sessions WHERE token = ?",
                (token,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def touch_auth_session(token: str, expires_at: float) -> bool:
    now = time.time()
    with _LOCK:
        conn = _connect()
        try:
            cur = conn.execute(
                """
                UPDATE auth_sessions
                SET expires_at = ?, last_seen_at = ?
                WHERE token = ?
                """,
                (expires_at, now, token),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def delete_auth_session(token: str) -> None:
    with _LOCK:
        conn = _connect()
        try:
            conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
            conn.commit()
        finally:
            conn.close()


def purge_expired_auth_sessions() -> int:
    now = time.time()
    with _LOCK:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now,))
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


load_auth_environment()
