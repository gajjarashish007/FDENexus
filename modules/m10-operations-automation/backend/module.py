"""M10 Operations Automation Engine.

Scheduled jobs, event-driven automation, incident-triggered workflows, and maintenance tasks.
All runs are recorded in m10_runs with full audit evidence. Demo mode simulates changes.
"""
from __future__ import annotations
import json
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from flask import jsonify, request
import ec2 as m01_ec2

API = "/api/m10"
SCHEMA = """
CREATE TABLE IF NOT EXISTS m10_jobs (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, owner TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
    trigger_type TEXT NOT NULL, trigger_config TEXT NOT NULL, preconditions TEXT,
    auth_scope TEXT, approval_required INTEGER DEFAULT 0, approver_roles TEXT,
    timeout_seconds INTEGER DEFAULT 300, retry_count INTEGER DEFAULT 2, retry_delay INTEGER DEFAULT 60,
    idempotency_key TEXT, verification_query TEXT, actions TEXT NOT NULL, created_at TEXT NOT NULL,
    updated_at TEXT, last_run TEXT, next_run TEXT, last_status TEXT, last_error TEXT
);
CREATE INDEX IF NOT EXISTS idx_m10_jobs_next ON m10_jobs(enabled, next_run);
CREATE TABLE IF NOT EXISTS m10_runs (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL, trigger TEXT NOT NULL, started_at TEXT NOT NULL,
    finished_at TEXT, status TEXT NOT NULL, output TEXT, error TEXT, approver TEXT,
    approved_at TEXT, resources TEXT, evidence TEXT
);
CREATE INDEX IF NOT EXISTS idx_m10_runs_job ON m10_runs(job_id, started_at DESC);
CREATE TABLE IF NOT EXISTS m10_schedules (
    id TEXT PRIMARY KEY, job_id TEXT NOT NULL, cron TEXT, timezone TEXT DEFAULT 'UTC',
    next_run TEXT, last_run TEXT, enabled INTEGER DEFAULT 1
);
"""

RANK = {"viewer": 1, "developer": 2, "approver": 3, "operator": 3, "security": 3, "admin": 9}
TRIGGER_TYPES = ("schedule", "event", "incident", "manual")
ACTION_TYPES = ("ec2_start", "ec2_stop", "ec2_terminate", "rds_snapshot", "rds_stop", "eks_update", "lambda_invoke", "s3_copy", "cleanup", "script")


def _now():
    return datetime.now(timezone.utc)


def _ts(dt=None):
    return (dt or _now()).strftime("%Y-%m-%d %H:%M:%S")


def _parse(ts):
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) if ts else None


def _cron_next(cron: str, tz: str = "UTC") -> datetime:
    """Simple cron: minute hour day month weekday. Returns next run after now."""
    import calendar
    now = _now()
    parts = cron.split()
    if len(parts) != 5:
        return now + timedelta(hours=1)
    minute, hour, dom, month, dow = parts

    def match(val, spec):
        if spec == "*":
            return True
        return str(val) in spec.split(",")

    for _ in range(366):
        now += timedelta(minutes=1)
        if match(now.minute, minute) and match(now.hour, hour) and \
           match(now.day, dom) and match(now.month, month) and \
           match(now.weekday(), dow if dow != "*" else "*"):
            return now
    return now + timedelta(hours=1)


def register(app, ctx):
    store, cfg = ctx.store, ctx.config
    auth, admin, role = ctx.auth_required, ctx.admin_required, ctx.role_required
    with store._LOCK, store._connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()

    def q(sql, args=(), one=False):
        with store._connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
        return (rows[0] if rows else None) if one else rows

    def x(sql, args=()):
        with store._LOCK, store._connect() as conn:
            conn.execute(sql, args)
            conn.commit()

    def err(msg, code=400):
        return jsonify({"error": msg}), code

    def body():
        return request.get_json(silent=True) or {}

    def me():
        return request.current_user

    def audit(action, target="", details=""):
        u = getattr(request, "current_user", None) or {}
        store.add_audit(u.get("id"), u.get("username", "system"), action, target=target, details=str(details)[:500])

    def cache():
        c = ctx.services.get("aws_cache")
        if not c:
            raise RuntimeError("The AWS cache (M02) is not loaded.")
        return c

    # ================================================================ job CRUD
    @app.route(f"{API}/jobs")
    @auth
    def list_jobs():
        jobs = q("SELECT * FROM m10_jobs ORDER BY name")
        for j in jobs:
            j["actions"] = json.loads(j["actions"] or "[]")
            j["trigger_config"] = json.loads(j["trigger_config"] or "{}")
            j["preconditions"] = json.loads(j["preconditions"] or "[]")
            j["auth_scope"] = json.loads(j["auth_scope"] or "{}")
            j["approver_roles"] = json.loads(j["approver_roles"] or "[]")
        runs = q("SELECT job_id, COUNT(*) n, MAX(started_at) last_run FROM m10_runs GROUP BY job_id")
        run_map = {r["job_id"]: r for r in runs}
        for j in jobs:
            j["run_count"] = run_map.get(j["id"], {}).get("n", 0)
        return jsonify({"jobs": jobs}), 200

    @app.route(f"{API}/jobs", methods=["POST"])
    @role("operator", "security", "admin")
    def create_job():
        d = body()
        name = str(d.get("name", "")).strip()
        if not 2 <= len(name) <= 80:
            return err("Name: 2-80 characters.")
        trigger_type = str(d.get("trigger_type", ""))
        if trigger_type not in TRIGGER_TYPES:
            return err(f"Trigger type must be one of: {', '.join(TRIGGER_TYPES)}.")
        actions = d.get("actions", [])
        if not isinstance(actions, list) or not actions:
            return err("Actions: non-empty list.")
        for a in actions:
            if a.get("type") not in ACTION_TYPES:
                return err(f"Action type must be one of: {', '.join(ACTION_TYPES)}.")
        jid = "JOB-" + secrets.token_hex(4)
        x("""INSERT INTO m10_jobs (id,name,owner,enabled,trigger_type,trigger_config,preconditions,auth_scope,approval_required,approver_roles,timeout_seconds,retry_count,retry_delay,idempotency_key,verification_query,actions,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (jid, name, me()["username"], 1, trigger_type, json.dumps(d.get("trigger_config", {})),
           json.dumps(d.get("preconditions", [])), json.dumps(d.get("auth_scope", {})),
           1 if d.get("approval_required") else 0, json.dumps(d.get("approver_roles", ["admin"])),
           int(d.get("timeout_seconds", 300)), int(d.get("retry_count", 2)), int(d.get("retry_delay", 60)),
           d.get("idempotency_key") or "", d.get("verification_query") or "", json.dumps(actions), _ts()))
        audit("job_created", jid, f"{name} {trigger_type}")
        return jsonify({"job": q("SELECT * FROM m10_jobs WHERE id=?", (jid,), one=True)}), 201

    @app.route(f"{API}/jobs/<jid>", methods=["PUT"])
    @role("operator", "security", "admin")
    def update_job(jid):
        job = q("SELECT * FROM m10_jobs WHERE id=?", (jid,), one=True)
        if not job:
            return err("Not found.", 404)
        if job["owner"] != me()["username"] and me()["role"] != "admin":
            return err("Only the owner or an admin can edit.", 403)
        d = body()
        if "name" in d:
            name = str(d["name"]).strip()
            if not 2 <= len(name) <= 80:
                return err("Name: 2-80 characters.")
            x("UPDATE m10_jobs SET name=?, updated_at=? WHERE id=?", (name, _ts(), jid))
        if "enabled" in d:
            x("UPDATE m10_jobs SET enabled=?, updated_at=? WHERE id=?", (1 if d["enabled"] else 0, _ts(), jid))
        if "actions" in d:
            actions = d["actions"]
            if not isinstance(actions, list) or not actions:
                return err("Actions: non-empty list.")
            x("UPDATE m10_jobs SET actions=?, updated_at=? WHERE id=?", (json.dumps(actions), _ts(), jid))
        audit("job_updated", jid)
        return jsonify({"job": q("SELECT * FROM m10_jobs WHERE id=?", (jid,), one=True)}), 200

    @app.route(f"{API}/jobs/<jid>", methods=["DELETE"])
    @role("operator", "security", "admin")
    def delete_job(jid):
        job = q("SELECT * FROM m10_jobs WHERE id=?", (jid,), one=True)
        if not job:
            return err("Not found.", 404)
        if job["owner"] != me()["username"] and me()["role"] != "admin":
            return err("Only the owner or an admin can delete.", 403)
        x("DELETE FROM m10_runs WHERE job_id=?", (jid,))
        x("DELETE FROM m10_schedules WHERE job_id=?", (jid,))
        x("DELETE FROM m10_jobs WHERE id=?", (jid,))
        audit("job_deleted", jid)
        return jsonify({"deleted": jid}), 200

    # ================================================================ run execution
    def execute_job(job: dict, trigger: str, approver: str = None) -> dict:
        """Execute a job's actions. Demo mode simulates; live mode (future) would call AWS."""
        jid = job["id"]
        rid = "RUN-" + secrets.token_hex(6)
        started = _ts()
        actions = json.loads(job["actions"] or "[]")
        resources, evidence = [], []
        status, error = "success", None

        try:
            if job["timeout_seconds"]:
                pass  # In a real implementation, wrap with timeout
            for i, a in enumerate(actions):
                atype = a.get("type")
                target = a.get("target", "")
                result = {"action": i, "type": atype, "target": target}

                if cfg.DEMO_MODE:
                    result["simulated"] = True
                    result["output"] = f"[demo] {atype} on {target}"
                else:
                    # Live mode: call AWS (future implementation)
                    result["output"] = f"[live] {atype} on {target} (not implemented)"

                resources.append(target)
                evidence.append(result)

        except Exception as e:
            status, error = "failed", str(e)[:500]
            if job["retry_count"] > 0:
                status = "retrying"

        finished = _ts()
        x("""INSERT INTO m10_runs (id,job_id,trigger,started_at,finished_at,status,output,error,approver,approved_at,resources,evidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
          (rid, jid, trigger, started, finished, status, json.dumps(evidence), error, approver,
           _ts() if approver else None, json.dumps(resources), json.dumps(evidence)))
        x("UPDATE m10_jobs SET last_run=?, last_status=?, last_error=? WHERE id=?",
          (finished, status, error, jid))
        audit("job_run", rid, f"{jid} {trigger} {status}")
        return {"run_id": rid, "status": status, "error": error}

    @app.route(f"{API}/jobs/<jid>/run", methods=["POST"])
    @role("operator", "security", "admin")
    def run_job(jid):
        job = q("SELECT * FROM m10_jobs WHERE id=?", (jid,), one=True)
        if not job:
            return err("Not found.", 404)
        if not job["enabled"]:
            return err("Job is disabled.")
        if job["approval_required"]:
            return err("This job requires approval. Use /approve.", 403)
        result = execute_job(job, "manual")
        return jsonify(result), 200 if result["status"] != "failed" else 500

    @app.route(f"{API}/jobs/<jid>/approve", methods=["POST"])
    @role("operator", "security", "admin")
    def approve_run(jid):
        job = q("SELECT * FROM m10_jobs WHERE id=?", (jid,), one=True)
        if not job:
            return err("Not found.", 404)
        if not job["approval_required"]:
            return err("This job does not require approval.")
        approver_roles = json.loads(job["approver_roles"] or "[]")
        if me()["role"] not in approver_roles:
            return err(f"Only {', '.join(approver_roles)} can approve.")
        result = execute_job(job, "approved", approver=me()["username"])
        return jsonify(result), 200

    # ================================================================ runs history
    @app.route(f"{API}/runs")
    @auth
    def list_runs():
        jid = request.args.get("job_id", "")
        limit = min(200, int(request.args.get("limit", 50)))
        sql = "SELECT * FROM m10_runs"
        args = []
        if jid:
            sql += " WHERE job_id=?"
            args.append(jid)
        sql += " ORDER BY started_at DESC LIMIT ?"
        args.append(limit)
        runs = q(sql, args)
        for r in runs:
            r["output"] = json.loads(r["output"] or "[]")
            r["resources"] = json.loads(r["resources"] or "[]")
            r["evidence"] = json.loads(r["evidence"] or "[]")
        return jsonify({"runs": runs}), 200

    @app.route(f"{API}/runs/<rid>")
    @auth
    def get_run(rid):
        r = q("SELECT * FROM m10_runs WHERE id=?", (rid,), one=True)
        if not r:
            return err("Not found.", 404)
        r["output"] = json.loads(r["output"] or "[]")
        r["resources"] = json.loads(r["resources"] or "[]")
        r["evidence"] = json.loads(r["evidence"] or "[]")
        return jsonify({"run": r}), 200

    # ================================================================ scheduler
    def scheduler_loop():
        while True:
            try:
                now = _ts()
                jobs = q("SELECT * FROM m10_jobs WHERE enabled=1 AND trigger_type='schedule' AND next_run<=?", (now,))
                for job in jobs:
                    cfg_data = json.loads(job["trigger_config"] or "{}")
                    cron = cfg_data.get("cron", "0 * * * *")
                    if job["approval_required"]:
                        continue  # Skip auto-run if approval required
                    try:
                        execute_job(job, "scheduled")
                    except Exception as e:
                        store.add_audit(None, "m10", "scheduler_error", details=str(e)[:200], level="error")
                    next_dt = _cron_next(cron)
                    x("UPDATE m10_jobs SET next_run=? WHERE id=?", (_ts(next_dt), job["id"]))
            except Exception:
                pass
            time.sleep(60)

    threading.Thread(target=scheduler_loop, name="m10-scheduler", daemon=True).start()

    # ================================================================ overview
    @app.route(f"{API}/overview")
    @auth
    def overview():
        jobs = q("SELECT id,enabled,trigger_type,last_status FROM m10_jobs")
        runs = q("SELECT status FROM m10_runs WHERE started_at>=?",
                 ((_now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"),))
        by_status = {}
        for r in runs:
            by_status[r["status"]] = by_status.get(r["status"], 0) + 1
        return jsonify({
            "jobs": len(jobs),
            "enabled": sum(1 for j in jobs if j["enabled"]),
            "by_trigger": {t: sum(1 for j in jobs if j["trigger_type"] == t) for t in TRIGGER_TYPES},
            "runs_7d": len(runs),
            "runs_by_status": by_status
        }), 200
