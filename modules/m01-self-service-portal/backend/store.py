"""SQLite data store for the M01 Self-Service Portal.

Holds the authoritative platform metadata: users, catalog items, requests,
approvals, deployments, resource inventory, notifications and the audit log.
Pure stdlib (sqlite3) plus hashlib for password hashing. No ORM.

Design notes:
- Every write that matters is paired with an audit entry by the API layer.
- Passwords are stored as salted PBKDF2-HMAC-SHA256 hashes, never plaintext.
- Row factory returns dicts so the API can jsonify directly.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone

import config

_LOCK = threading.Lock()


# ----------------------------------------------------------------- connection
def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


# ----------------------------------------------------------------- passwords
def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return f"pbkdf2$120000${salt}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt, _ = stored.split("$")
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
        return secrets.compare_digest(expected, stored.split("$")[-1])
    except Exception:
        return False


# ----------------------------------------------------------------- schema
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'developer',
    team TEXT DEFAULT 'Platform',
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | approved | rejected | disabled
    mfa INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    approved_by INTEGER,
    last_login TEXT
);

CREATE TABLE IF NOT EXISTS catalog_items (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    icon TEXT,
    description TEXT,
    risk_tier TEXT NOT NULL DEFAULT 'R2',
    approval_required INTEGER NOT NULL DEFAULT 1,
    est_cost TEXT,
    est_time TEXT,
    input_schema TEXT,                         -- JSON array of field defs
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS requests (
    id TEXT PRIMARY KEY,
    item_id TEXT NOT NULL,
    item_name TEXT NOT NULL,
    requester_id INTEGER NOT NULL,
    requester TEXT NOT NULL,
    team TEXT,
    environment TEXT,
    risk_tier TEXT,
    inputs TEXT,                               -- JSON of submitted fields
    status TEXT NOT NULL DEFAULT 'pending',    -- pending | approved | rejected | deploying | deployed | failed | cancelled
    est_cost TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (requester_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL,
    approver_id INTEGER,
    approver TEXT,
    decision TEXT NOT NULL,                    -- approved | rejected
    reason TEXT,
    decided_at TEXT NOT NULL,
    FOREIGN KEY (request_id) REFERENCES requests(id)
);

CREATE TABLE IF NOT EXISTS deployments (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    item_name TEXT,
    environment TEXT,
    status TEXT NOT NULL DEFAULT 'queued',     -- queued | running | succeeded | failed | rolled_back
    started_at TEXT,
    finished_at TEXT,
    log TEXT,
    FOREIGN KEY (request_id) REFERENCES requests(id)
);

CREATE TABLE IF NOT EXISTS resources (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    environment TEXT,
    owner_team TEXT,
    region TEXT,
    status TEXT NOT NULL DEFAULT 'healthy',    -- healthy | degraded | unhealthy
    request_id TEXT,
    tags TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                           -- NULL = broadcast to all
    level TEXT NOT NULL DEFAULT 'info',        -- info | success | warning | danger
    title TEXT NOT NULL,
    body TEXT,
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    user_id INTEGER,
    actor TEXT,
    action TEXT NOT NULL,
    target TEXT,
    level TEXT NOT NULL DEFAULT 'info',
    details TEXT
);

CREATE TABLE IF NOT EXISTS aws_accounts (
    id TEXT PRIMARY KEY,                       -- 12-digit AWS account id
    alias TEXT NOT NULL,
    name TEXT NOT NULL,
    method TEXT NOT NULL DEFAULT 'assume-role',-- assume-role | instance-role | profile
    role_arn TEXT,
    profile TEXT,                              -- local AWS profile name (method=profile)
    external_id TEXT,
    region TEXT NOT NULL DEFAULT 'us-east-1',
    env TEXT NOT NULL DEFAULT 'non-production',
    status TEXT NOT NULL DEFAULT 'unverified', -- connected | failed | unverified
    note TEXT,
    last_checked TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_prefs (
    user_id INTEGER NOT NULL,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (user_id, key)
);
"""


# ----------------------------------------------------------------- init / seed
def init_db() -> None:
    with _LOCK, _connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(aws_accounts)").fetchall()}
        if "profile" not in cols:  # databases created before v1.2
            conn.execute("ALTER TABLE aws_accounts ADD COLUMN profile TEXT")
        conn.commit()
        _seed_admin(conn)
        _seed_catalog(conn)
        # Demo resources/notifications are seeded ONLY when M01_SEED_DEMO=1.
        # Production starts with an empty inventory (no fabricated resources).
        if config.SEED_DEMO:
            _seed_demo(conn)


def _seed_admin(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if count:
        return
    conn.execute(
        "INSERT INTO users (username,email,password_hash,role,team,status,mfa,created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (config.BOOTSTRAP_ADMIN_USER, config.BOOTSTRAP_ADMIN_EMAIL,
         _hash_password(config.BOOTSTRAP_ADMIN_PASSWORD), "admin", "Platform",
         "approved", 1, _now()),
    )
    conn.commit()


CATALOG_SEED = [
    {
        "id": "env-baseline", "name": "Standard Environment Baseline", "category": "Infrastructure",
        "icon": "bi-diagram-3", "description": "A compliant environment: network, logging, security tooling, budgets, tags.",
        "risk_tier": "R2", "approval_required": 1, "est_cost": "$320/mo", "est_time": "~60 min",
        "input_schema": [
            {"name": "team", "label": "Team", "type": "text", "required": True, "placeholder": "payments"},
            {"name": "environment", "label": "Environment", "type": "select", "options": ["sandbox", "non-production", "staging", "production"], "required": True},
            {"name": "region", "label": "Region", "type": "select", "options": ["us-east-1", "us-east-2", "us-west-2", "eu-west-1", "ap-south-1"], "required": True},
            {"name": "budget", "label": "Monthly budget (USD)", "type": "number", "required": False, "default": 500},
        ],
    },
    {
        "id": "k8s-namespace", "name": "Kubernetes Namespace", "category": "Containers",
        "icon": "bi-collection", "description": "A namespace with quota, labels and a default-deny network policy.",
        "risk_tier": "R1", "approval_required": 0, "est_cost": "$0", "est_time": "~5 min",
        "input_schema": [
            {"name": "name", "label": "Namespace name", "type": "text", "required": True, "placeholder": "payments-staging"},
            {"name": "cpu", "label": "CPU quota (cores)", "type": "number", "required": True, "default": 8},
            {"name": "memory", "label": "Memory quota (Gi)", "type": "number", "required": True, "default": 16},
            {"name": "netpol", "label": "Apply default-deny network policy", "type": "checkbox", "default": True},
        ],
    },
    {
        "id": "vpc-network", "name": "VPC and Networking", "category": "Infrastructure",
        "icon": "bi-hdd-network", "description": "Standard VPC with subnets, routing, endpoints and security group baselines.",
        "risk_tier": "R2", "approval_required": 1, "est_cost": "$140/mo", "est_time": "~60 min",
        "input_schema": [
            {"name": "team", "label": "Team", "type": "text", "required": True},
            {"name": "cidr", "label": "CIDR block", "type": "text", "required": True, "default": "10.0.0.0/16"},
            {"name": "azs", "label": "Availability zones", "type": "number", "required": True, "default": 3},
        ],
    },
    {
        "id": "postgres-db", "name": "PostgreSQL Database", "category": "Databases",
        "icon": "bi-database", "description": "Managed PostgreSQL with encryption, backups and optional Multi-AZ.",
        "risk_tier": "R2", "approval_required": 1, "est_cost": "$210/mo", "est_time": "~90 min",
        "input_schema": [
            {"name": "team", "label": "Owner team", "type": "text", "required": True},
            {"name": "environment", "label": "Environment", "type": "select", "options": ["non-production", "staging", "production"], "required": True},
            {"name": "instance_class", "label": "Instance class", "type": "text", "default": "db.r6g.large"},
            {"name": "multi_az", "label": "Multi-AZ high availability", "type": "checkbox", "default": True},
            {"name": "backup_days", "label": "Backup retention (days)", "type": "number", "default": 7},
        ],
    },
    {
        "id": "ec2-instance", "name": "EC2 Instance (direct, legacy)", "category": "Compute", "enabled": 0,
        "icon": "bi-server", "description": "Launch a virtual server in a connected AWS account with guided image, size and network choices.",
        "risk_tier": "R1", "approval_required": 0, "est_cost": "from $8/mo", "est_time": "~2 min",
        "input_schema": [
            {"name": "account_id", "label": "AWS account", "type": "text", "required": True},
            {"name": "instance_name", "label": "Instance name", "type": "text", "required": True},
            {"name": "team", "label": "Team", "type": "text", "required": True},
            {"name": "environment", "label": "Environment", "type": "select", "options": ["sandbox", "non-production", "staging", "production"], "required": True},
            {"name": "os", "label": "Operating system", "type": "select", "options": ["amazon-linux", "ubuntu", "windows"], "required": True},
            {"name": "instance_type", "label": "Instance type", "type": "text", "required": True},
            {"name": "volume_gb", "label": "Root volume (GB)", "type": "number", "default": 20},
            {"name": "key_name", "label": "Key pair", "type": "text"},
            {"name": "subnet_id", "label": "Subnet ID", "type": "text"},
            {"name": "security_group_ids", "label": "Security group IDs", "type": "text"},
            {"name": "user_data", "label": "User data script", "type": "text"},
        ],
    },
    {
        "id": "s3-bucket", "name": "S3 Bucket", "category": "Storage",
        "icon": "bi-bucket", "description": "Encrypted object storage with versioning and lifecycle rules.",
        "risk_tier": "R1", "approval_required": 0, "est_cost": "$5/mo", "est_time": "~2 min",
        "input_schema": [
            {"name": "name", "label": "Bucket name", "type": "text", "required": True},
            {"name": "versioning", "label": "Enable versioning", "type": "checkbox", "default": True},
        ],
    },
    {
        "id": "alb", "name": "Application Load Balancer", "category": "Networking",
        "icon": "bi-sign-intersection", "description": "HTTP/HTTPS load balancer with WAF association and access logging.",
        "risk_tier": "R2", "approval_required": 1, "est_cost": "$60/mo", "est_time": "~5 min",
        "input_schema": [
            {"name": "name", "label": "Name", "type": "text", "required": True},
            {"name": "scheme", "label": "Scheme", "type": "select", "options": ["internet-facing", "internal"], "required": True},
        ],
    },
    {
        "id": "iam-role", "name": "IAM Role", "category": "Security",
        "icon": "bi-person-badge", "description": "A permission-bounded IAM role for a workload or team.",
        "risk_tier": "R3", "approval_required": 1, "est_cost": "$0", "est_time": "~30 min",
        "input_schema": [
            {"name": "name", "label": "Role name", "type": "text", "required": True},
            {"name": "purpose", "label": "Purpose", "type": "text", "required": True},
        ],
    },
]


def _seed_catalog(conn: sqlite3.Connection) -> None:
    """Insert any catalog items that are missing (so new items reach existing databases)."""
    for item in CATALOG_SEED:
        conn.execute(
            "INSERT OR IGNORE INTO catalog_items (id,name,category,icon,description,risk_tier,approval_required,est_cost,est_time,input_schema,enabled) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (item["id"], item["name"], item["category"], item["icon"], item["description"],
             item["risk_tier"], item["approval_required"], item["est_cost"], item["est_time"],
             json.dumps(item["input_schema"]), item.get("enabled", 1)),
        )
    conn.commit()


def _seed_demo(conn: sqlite3.Connection) -> None:
    """A little starter inventory and a broadcast notice, only on a fresh DB."""
    if conn.execute("SELECT COUNT(*) AS c FROM resources").fetchone()["c"]:
        return
    demo_resources = [
        ("res-ec2-01", "web-01", "EC2 Instance", "production", "Web", config.AWS_REGION, "healthy"),
        ("res-rds-01", "orders-db", "RDS PostgreSQL", "production", "Orders", config.AWS_REGION, "degraded"),
        ("res-s3-01", "reports-bucket", "S3 Bucket", "non-production", "Data", config.AWS_REGION, "healthy"),
        ("res-eks-ns-01", "search-staging", "K8s Namespace", "staging", "Search", config.AWS_REGION, "healthy"),
    ]
    for rid, name, typ, env, team, region, status in demo_resources:
        conn.execute(
            "INSERT INTO resources (id,name,type,environment,owner_team,region,status,tags,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (rid, name, typ, env, team, region, status, json.dumps({"managed-by": "fde-nexus"}), _now()),
        )
    conn.execute(
        "INSERT INTO notifications (user_id,level,title,body,read,created_at) VALUES (NULL,?,?,?,0,?)",
        ("info", "Welcome to the Self-Service Portal",
         "Browse the catalog, submit a request, and track it through approval and deployment.", _now()),
    )
    conn.commit()


# ----------------------------------------------------------------- users
def _user_public(row: sqlite3.Row) -> dict:
    u = dict(row)
    u.pop("password_hash", None)
    u["mfa"] = bool(u.get("mfa"))
    return u


def create_signup(username: str, email: str, password: str, role: str | None = None):
    username = (username or "").strip()
    email = (email or "").strip().lower()
    if not username or not email or not password:
        return None, "Username, email and password are required."
    if len(password) < config.PASSWORD_MIN_LENGTH:
        return None, f"Password must be at least {config.PASSWORD_MIN_LENGTH} characters."
    with _LOCK, _connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username=? OR email=?", (username, email)
        ).fetchone()
        if exists:
            return None, "A user with that username or email already exists."
        cur = conn.execute(
            "INSERT INTO users (username,email,password_hash,role,team,status,mfa,created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (username, email, _hash_password(password), role or config.DEFAULT_ROLE,
             "Platform", "pending", 0, _now()),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id=?", (cur.lastrowid,)).fetchone()
        return _user_public(row), None


def authenticate(username: str, password: str):
    with _LOCK, _connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username=? OR email=?", (username, username.lower())
        ).fetchone()
        if not row or not _verify_password(password, row["password_hash"]):
            return None, "invalid"
        status = row["status"]
        if status != "approved":
            return _user_public(row), status  # blocked reason
        conn.execute("UPDATE users SET last_login=? WHERE id=?", (_now(), row["id"]))
        conn.commit()
        return _user_public(row), None


def get_user(user_id: int):
    with _connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return _user_public(row) if row else None


def list_users():
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
        return [_user_public(r) for r in rows]


def list_pending_users():
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM users WHERE status='pending' ORDER BY created_at").fetchall()
        return [_user_public(r) for r in rows]


def set_user_status(user_id: int, status: str, admin_id: int | None = None):
    with _LOCK, _connect() as conn:
        conn.execute("UPDATE users SET status=?, approved_by=? WHERE id=?", (status, admin_id, user_id))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return _user_public(row) if row else None


def set_user_role(user_id: int, role: str):
    with _LOCK, _connect() as conn:
        conn.execute("UPDATE users SET role=? WHERE id=?", (role, user_id))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return _user_public(row) if row else None


# ----------------------------------------------------------------- catalog
def list_catalog(enabled_only: bool = True):
    with _connect() as conn:
        q = "SELECT * FROM catalog_items"
        if enabled_only:
            q += " WHERE enabled=1"
        q += " ORDER BY category, name"
        rows = conn.execute(q).fetchall()
        items = []
        for r in rows:
            d = dict(r)
            d["approval_required"] = bool(d["approval_required"])
            d["enabled"] = bool(d["enabled"])
            d["input_schema"] = json.loads(d["input_schema"] or "[]")
            items.append(d)
        return items


def get_catalog_item(item_id: str):
    with _connect() as conn:
        r = conn.execute("SELECT * FROM catalog_items WHERE id=?", (item_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["approval_required"] = bool(d["approval_required"])
        d["input_schema"] = json.loads(d["input_schema"] or "[]")
        return d


# ----------------------------------------------------------------- requests
def _new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(3)}"


def create_request(item: dict, user: dict, inputs: dict):
    rid = _new_id("REQ")
    now = _now()
    env = inputs.get("environment") or "non-production"
    approval = item["approval_required"] or env == "production"
    status = "pending" if approval else "approved"
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO requests (id,item_id,item_name,requester_id,requester,team,environment,"
            "risk_tier,inputs,status,est_cost,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, item["id"], item["name"], user["id"], user["username"],
             inputs.get("team") or user.get("team"), env, item["risk_tier"],
             json.dumps(inputs), status, item.get("est_cost"), now, now),
        )
        conn.commit()
    if not approval:
        # auto-approved low-risk: record an auto approval
        add_approval(rid, None, "system", "approved", "Auto-approved (pre-approved low-risk item)")
    return get_request(rid)


def get_request(request_id: str):
    with _connect() as conn:
        r = conn.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["inputs"] = json.loads(d["inputs"] or "{}")
        return d


def list_requests(user: dict | None = None, status: str | None = None):
    with _connect() as conn:
        q = "SELECT * FROM requests"
        params: list = []
        clauses = []
        # non-admins see only their own requests
        if user and user.get("role") != "admin" and user.get("role") not in ("approver", "operator", "security"):
            clauses.append("requester_id=?")
            params.append(user["id"])
        if status:
            clauses.append("status=?")
            params.append(status)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC"
        rows = conn.execute(q, params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["inputs"] = json.loads(d["inputs"] or "{}")
            out.append(d)
        return out


def list_pending_approvals():
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM requests WHERE status='pending' ORDER BY created_at").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["inputs"] = json.loads(d["inputs"] or "{}")
            out.append(d)
        return out


def update_request_status(request_id: str, status: str):
    with _LOCK, _connect() as conn:
        conn.execute("UPDATE requests SET status=?, updated_at=? WHERE id=?", (status, _now(), request_id))
        conn.commit()
    return get_request(request_id)


# ----------------------------------------------------------------- approvals
def add_approval(request_id: str, approver_id, approver: str, decision: str, reason: str | None):
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO approvals (request_id,approver_id,approver,decision,reason,decided_at) "
            "VALUES (?,?,?,?,?,?)",
            (request_id, approver_id, approver, decision, reason, _now()),
        )
        conn.commit()


def list_approvals(request_id: str):
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM approvals WHERE request_id=? ORDER BY decided_at", (request_id,)).fetchall()
        return [dict(r) for r in rows]


# ----------------------------------------------------------------- deployments
def create_deployment(request: dict):
    did = _new_id("DEP")
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO deployments (id,request_id,item_name,environment,status,started_at,log) "
            "VALUES (?,?,?,?,?,?,?)",
            (did, request["id"], request["item_name"], request["environment"], "running", _now(), ""),
        )
        conn.commit()
    return did


def finish_deployment(deployment_id: str, status: str, log: str):
    with _LOCK, _connect() as conn:
        conn.execute(
            "UPDATE deployments SET status=?, finished_at=?, log=? WHERE id=?",
            (status, _now(), log, deployment_id),
        )
        conn.commit()


def list_deployments(limit: int = 50):
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM deployments ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]


# ----------------------------------------------------------------- resources
def add_resource(name, rtype, environment, owner_team, request_id=None, status="healthy", tags=None):
    rid = _new_id("res")
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO resources (id,name,type,environment,owner_team,region,status,request_id,tags,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, name, rtype, environment, owner_team, config.AWS_REGION, status,
             request_id, json.dumps(tags or {}), _now()),
        )
        conn.commit()
    return rid


def list_resources(search: str | None = None, env: str | None = None, status: str | None = None):
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM resources ORDER BY created_at DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d["tags"] or "{}")
        if env and d["environment"] != env:
            continue
        if status and d["status"] != status:
            continue
        if search:
            hay = f"{d['name']} {d['type']} {d['owner_team']} {d['environment']}".lower()
            if search.lower() not in hay:
                continue
        out.append(d)
    return out


def health_summary():
    res = list_resources()
    summary = {"healthy": 0, "degraded": 0, "unhealthy": 0, "total": len(res)}
    for r in res:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    return summary


# ----------------------------------------------------------------- notifications
def add_notification(user_id, level, title, body):
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO notifications (user_id,level,title,body,read,created_at) VALUES (?,?,?,?,0,?)",
            (user_id, level, title, body, _now()),
        )
        conn.commit()


def list_notifications(user_id: int, unread_only: bool = False):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE (user_id=? OR user_id IS NULL) "
            + ("AND read=0 " if unread_only else "")
            + "ORDER BY created_at DESC LIMIT 50",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_notifications_read(user_id: int):
    with _LOCK, _connect() as conn:
        conn.execute("UPDATE notifications SET read=1 WHERE user_id=? OR user_id IS NULL", (user_id,))
        conn.commit()


# ----------------------------------------------------------------- audit
def add_audit(user_id, actor, action, target=None, level="info", details=None):
    with _LOCK, _connect() as conn:
        conn.execute(
            "INSERT INTO audit_logs (ts,user_id,actor,action,target,level,details) VALUES (?,?,?,?,?,?,?)",
            (_now(), user_id, actor, action, target, level, details),
        )
        conn.commit()


def list_audit(limit: int = 200, user_id: int | None = None):
    with _connect() as conn:
        if user_id is None:
            rows = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM audit_logs WHERE user_id=? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


# ----------------------------------------------------------------- search
def global_search(query: str, user: dict):
    q = (query or "").strip().lower()
    if not q:
        return {"catalog": [], "requests": [], "resources": []}
    catalog = [c for c in list_catalog() if q in (c["name"] + c["category"] + (c["description"] or "")).lower()][:5]
    requests_ = [r for r in list_requests(user) if q in (r["id"] + r["item_name"] + (r["team"] or "")).lower()][:5]
    resources = [r for r in list_resources(search=q)][:5]
    return {
        "catalog": [{"id": c["id"], "name": c["name"], "category": c["category"]} for c in catalog],
        "requests": [{"id": r["id"], "name": r["item_name"], "status": r["status"]} for r in requests_],
        "resources": [{"id": r["id"], "name": r["name"], "type": r["type"]} for r in resources],
    }


# ----------------------------------------------------------------- AWS accounts
def list_aws_accounts() -> list:
    with _connect() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM aws_accounts ORDER BY created_at").fetchall()]


def get_aws_account(acct_id: str):
    with _connect() as conn:
        r = conn.execute("SELECT * FROM aws_accounts WHERE id=?", (acct_id,)).fetchone()
    return dict(r) if r else None


def add_aws_account(d: dict, created_by: str):
    with _LOCK, _connect() as conn:
        if conn.execute("SELECT 1 FROM aws_accounts WHERE id=?", (d["id"],)).fetchone():
            return None, "Account already registered"
        conn.execute(
            "INSERT INTO aws_accounts (id,alias,name,method,role_arn,profile,external_id,region,env,status,note,created_by,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (d["id"], d["alias"], d["name"], d["method"], d.get("role_arn") or "", d.get("profile") or "", d.get("external_id") or "",
             d["region"], d["env"], "unverified", "", created_by, _now()))
        conn.commit()
    return get_aws_account(d["id"]), None


def update_aws_account(acct_id: str, d: dict):
    with _LOCK, _connect() as conn:
        conn.execute("UPDATE aws_accounts SET alias=?, name=?, method=?, role_arn=?, profile=?, external_id=?, region=?, env=?, "
                     "status='unverified', note='' WHERE id=?",
                     (d["alias"], d["name"], d["method"], d.get("role_arn") or "", d.get("profile") or "",
                      d.get("external_id") or "", d["region"], d["env"], acct_id))
        conn.commit()
    return get_aws_account(acct_id)


def set_aws_account_status(acct_id: str, status: str, note: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("UPDATE aws_accounts SET status=?, note=?, last_checked=? WHERE id=?",
                     (status, note, _now(), acct_id))
        conn.commit()


def delete_aws_account(acct_id: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("DELETE FROM aws_accounts WHERE id=?", (acct_id,))
        conn.execute("DELETE FROM user_prefs WHERE key='active_account' AND value=?", (acct_id,))
        conn.commit()


def get_pref(user_id: int, key: str):
    with _connect() as conn:
        r = conn.execute("SELECT value FROM user_prefs WHERE user_id=? AND key=?", (user_id, key)).fetchone()
    return r["value"] if r else None


def set_pref(user_id: int, key: str, value: str) -> None:
    with _LOCK, _connect() as conn:
        conn.execute("INSERT INTO user_prefs (user_id,key,value) VALUES (?,?,?) "
                     "ON CONFLICT(user_id,key) DO UPDATE SET value=excluded.value", (user_id, key, value))
        conn.commit()


# ----------------------------------------------------------------- catalog configuration
def update_catalog_item(item_id: str, approval_required: bool, enabled: bool):
    with _LOCK, _connect() as conn:
        conn.execute("UPDATE catalog_items SET approval_required=?, enabled=? WHERE id=?",
                     (1 if approval_required else 0, 1 if enabled else 0, item_id))
        conn.commit()
    return get_catalog_item(item_id)


def change_password(user_id: int, current: str, new: str):
    """Returns an error string, or None on success."""
    if len(new or "") < config.PASSWORD_MIN_LENGTH:
        return f"New password must be at least {config.PASSWORD_MIN_LENGTH} characters."
    with _LOCK, _connect() as conn:
        row = conn.execute("SELECT password_hash FROM users WHERE id=?", (user_id,)).fetchone()
        if not row or not _verify_password(current or "", row["password_hash"]):
            return "Current password is incorrect."
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (_hash_password(new), user_id))
        conn.commit()
    return None
