"""Central AWS resource cache: one place in the portal database for everything in every connected account.

Sync = read-only calls per (account, region, service). Each slice is replaced atomically on success,
so deleted resources disappear and a failure keeps the last good data (marked stale with the error).
Every module reads from here instead of calling AWS itself (ctx.services["aws_cache"]).
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import m02_collectors as col

SCHEMA = """
CREATE TABLE IF NOT EXISTS aws_cache_resources (
    account_id TEXT NOT NULL, region TEXT NOT NULL, service TEXT NOT NULL, resource_id TEXT NOT NULL,
    name TEXT, state TEXT, summary TEXT, tags TEXT, detail TEXT, fetched_at TEXT NOT NULL,
    PRIMARY KEY (account_id, region, service, resource_id)
);
CREATE INDEX IF NOT EXISTS idx_cache_lookup ON aws_cache_resources(account_id, service, region);
CREATE TABLE IF NOT EXISTS aws_cache_slices (
    account_id TEXT NOT NULL, region TEXT NOT NULL, service TEXT NOT NULL,
    status TEXT NOT NULL, count INTEGER NOT NULL DEFAULT 0, error TEXT, duration_ms INTEGER,
    synced_at TEXT, attempted_at TEXT NOT NULL,
    PRIMARY KEY (account_id, region, service)
);
CREATE TABLE IF NOT EXISTS aws_cache_jobs (
    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, regions TEXT NOT NULL, services TEXT NOT NULL,
    status TEXT NOT NULL, total INTEGER NOT NULL, done INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0,
    resources INTEGER NOT NULL DEFAULT 0, trigger TEXT, started_by TEXT, started_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE IF NOT EXISTS aws_cache_accounts (
    account_id TEXT PRIMARY KEY, regions TEXT NOT NULL, services TEXT NOT NULL,
    auto_refresh INTEGER NOT NULL DEFAULT 1, last_job TEXT, last_synced TEXT
);
"""
WORKERS = 8


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _err(e: Exception) -> str:
    code = (getattr(e, "response", None) or {}).get("Error", {}).get("Code")
    msg = str(e)
    if code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation", "AuthorizationError"):
        return f"{code}: these credentials may not read this service."
    if code in ("OptInRequired", "UnrecognizedClientException", "InvalidClientTokenId") or "not subscribed" in msg:
        return f"{code or 'Error'}: region or service not enabled for this account."
    if "Token has expired" in msg or "SSO" in msg:
        return "SSO session expired: run `aws sso login --profile <name>` on the portal host."
    return msg[:300]


class Cache:
    def __init__(self, ctx, session_factory):
        self.ctx, self.store, self.session_factory = ctx, ctx.store, session_factory
        with self.store._LOCK, self.store._connect() as conn:
            conn.executescript(SCHEMA)
            conn.execute("UPDATE aws_cache_jobs SET status='interrupted', finished_at=? WHERE status IN ('queued','running')", (_now(),))
            conn.commit()
        self._running: dict[str, str] = {}   # account_id -> job id
        self._lock = threading.Lock()
        self._stop = threading.Event()
        threading.Thread(target=self._scheduler, name="aws-cache-scheduler", daemon=True).start()

    # ------------------------------------------------------------------ db helpers
    def _q(self, sql, args=(), one=False):
        with self.store._connect() as conn:
            rows = [dict(r) for r in conn.execute(sql, args).fetchall()]
        return (rows[0] if rows else None) if one else rows

    def _x(self, sql, args=()):
        with self.store._LOCK, self.store._connect() as conn:
            conn.execute(sql, args)
            conn.commit()

    # ------------------------------------------------------------------ settings
    def interval_minutes(self) -> int:
        return int(self.ctx.get_setting("aws_cache.interval_minutes", 60))

    def account_config(self, acct_id):
        r = self._q("SELECT * FROM aws_cache_accounts WHERE account_id=?", (acct_id,), one=True)
        if r:
            r["regions"], r["services"] = json.loads(r["regions"]), json.loads(r["services"])
        return r

    # ------------------------------------------------------------------ regions
    def enabled_regions(self, account) -> list[str]:
        try:
            ec2 = self.session_factory(account).client("ec2", region_name=account["region"])
            return sorted(r["RegionName"] for r in ec2.describe_regions(AllRegions=False)["Regions"])
        except Exception:
            return [account["region"]]

    # ------------------------------------------------------------------ sync
    def start_sync(self, account, regions, services, user, trigger="manual"):
        services = [s for s in (services or list(col.SERVICES)) if s in col.SERVICES]
        if not services:
            raise ValueError("Pick at least one service.")
        if regions == "all":
            regions = self.enabled_regions(account)
        elif not regions or regions == "current":
            regions = [account["region"]]
        regions = sorted(set(regions))
        with self._lock:
            if account["id"] in self._running:
                return self.job(self._running[account["id"]]), False
            jid = "SYNC-" + secrets.token_hex(3)
            self._running[account["id"]] = jid
        pairs = [(reg, svc) for svc in services for reg in (["global"] if col.SERVICES[svc][3] == "global" else regions)]
        pairs = list(dict.fromkeys(pairs))
        self._x("INSERT INTO aws_cache_jobs (id,account_id,regions,services,status,total,trigger,started_by,started_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (jid, account["id"], json.dumps(regions), json.dumps(services), "running", len(pairs), trigger, user, _now()))
        self._x("INSERT INTO aws_cache_accounts (account_id,regions,services,auto_refresh,last_job) VALUES (?,?,?,1,?) "
                "ON CONFLICT(account_id) DO UPDATE SET regions=excluded.regions, services=excluded.services, last_job=excluded.last_job",
                (account["id"], json.dumps(regions), json.dumps(services), jid))
        threading.Thread(target=self._run, args=(jid, account, pairs), name=f"sync-{jid}", daemon=True).start()
        return self.job(jid), True

    def _run(self, jid, account, pairs):
        try:
            session = self.session_factory(account)
        except Exception as e:
            self._x("UPDATE aws_cache_jobs SET status='failed', errors=?, done=?, finished_at=? WHERE id=?", (len(pairs), len(pairs), _now(), jid))
            for reg, svc in pairs:
                self._slice_failed(account["id"], reg, svc, _err(e), 0)
            with self._lock:
                self._running.pop(account["id"], None)
            return
        lock = threading.Lock()
        totals = {"done": 0, "errors": 0, "resources": 0}

        def one(pair):
            reg, svc = pair
            t0 = time.time()
            try:
                rows = col.SERVICES[svc][2](session, account["region"] if reg == "global" else reg)
                self._replace_slice(account["id"], reg, svc, rows, int((time.time() - t0) * 1000))
                n, bad = len(rows), 0
            except Exception as e:
                self._slice_failed(account["id"], reg, svc, _err(e), int((time.time() - t0) * 1000))
                n, bad = 0, 1
            with lock:
                totals["done"] += 1
                totals["errors"] += bad
                totals["resources"] += n
                self._x("UPDATE aws_cache_jobs SET done=?, errors=?, resources=? WHERE id=?", (totals["done"], totals["errors"], totals["resources"], jid))
        with ThreadPoolExecutor(WORKERS) as pool:
            list(pool.map(one, pairs))
        status = "completed" if not totals["errors"] else ("failed" if totals["errors"] == len(pairs) else "completed_with_errors")
        self._x("UPDATE aws_cache_jobs SET status=?, finished_at=? WHERE id=?", (status, _now(), jid))
        self._x("UPDATE aws_cache_accounts SET last_synced=? WHERE account_id=?", (_now(), account["id"]))
        self.store.add_audit(None, "aws-cache", "aws_cache_synced", target=account["id"],
                             details=f"{jid}: {totals['resources']} resources, {totals['errors']} failed slices of {len(pairs)}",
                             level="warn" if totals["errors"] else "info")
        with self._lock:
            self._running.pop(account["id"], None)

    def _replace_slice(self, acct, reg, svc, rows, ms):
        now = _now()
        with self.store._LOCK, self.store._connect() as conn:
            conn.execute("DELETE FROM aws_cache_resources WHERE account_id=? AND region=? AND service=?", (acct, reg, svc))
            conn.executemany("INSERT OR REPLACE INTO aws_cache_resources VALUES (?,?,?,?,?,?,?,?,?,?)",
                             [(acct, reg, svc, r["id"], r["name"], r["state"], json.dumps(r["summary"], default=str),
                               json.dumps(r["tags"], default=str), json.dumps(r["detail"], default=str), now) for r in rows])
            conn.execute("INSERT INTO aws_cache_slices VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(account_id,region,service) DO UPDATE SET "
                         "status=excluded.status, count=excluded.count, error=NULL, duration_ms=excluded.duration_ms, synced_at=excluded.synced_at, attempted_at=excluded.attempted_at",
                         (acct, reg, svc, "ok", len(rows), None, ms, now, now))
            conn.commit()

    def _slice_failed(self, acct, reg, svc, error, ms):
        self._x("INSERT INTO aws_cache_slices (account_id,region,service,status,count,error,duration_ms,attempted_at) VALUES (?,?,?,?,?,?,?,?) "
                "ON CONFLICT(account_id,region,service) DO UPDATE SET status='error', error=excluded.error, duration_ms=excluded.duration_ms, attempted_at=excluded.attempted_at",
                (acct, reg, svc, "error", 0, error, ms, _now()))

    def job(self, jid):
        j = self._q("SELECT * FROM aws_cache_jobs WHERE id=?", (jid,), one=True)
        if j:
            j["regions"], j["services"] = json.loads(j["regions"]), json.loads(j["services"])
        return j

    def jobs(self, acct, limit=20):
        rows = self._q("SELECT * FROM aws_cache_jobs WHERE account_id=? ORDER BY started_at DESC LIMIT ?", (acct, limit))
        for j in rows:
            j["regions"], j["services"] = json.loads(j["regions"]), json.loads(j["services"])
        return rows

    # ------------------------------------------------------------------ scheduler
    def _scheduler(self):
        while not self._stop.wait(60):
            try:
                mins = self.interval_minutes()
                if mins <= 0:
                    continue
                for cfg in self._q("SELECT * FROM aws_cache_accounts WHERE auto_refresh=1"):
                    last = cfg.get("last_synced")
                    if last and (datetime.now(timezone.utc) - datetime.strptime(last, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)).total_seconds() < mins * 60:
                        continue
                    acct = self.store.get_aws_account(cfg["account_id"])
                    if not acct or acct["status"] != "connected" or not self.ctx.config.LIVE_READS:
                        continue
                    self.start_sync(acct, json.loads(cfg["regions"]), json.loads(cfg["services"]), "scheduler", trigger="scheduled")
            except Exception:
                pass  # the scheduler must never die; failures are recorded per slice

    # ------------------------------------------------------------------ queries
    def summary(self, acct):
        slices = self._q("SELECT * FROM aws_cache_slices WHERE account_id=? ORDER BY service, region", (acct,))
        by_service = {}
        for s in slices:
            meta = col.SERVICES.get(s["service"], (s["service"], "Other", None, ""))
            e = by_service.setdefault(s["service"], {"service": s["service"], "label": meta[0], "category": meta[1], "count": 0,
                                                       "regions": {}, "errors": 0, "oldest": None})
            e["count"] += s["count"] if s["status"] == "ok" else self._q(
                "SELECT COUNT(*) n FROM aws_cache_resources WHERE account_id=? AND region=? AND service=?", (acct, s["region"], s["service"]), one=True)["n"]
            e["regions"][s["region"]] = {"status": s["status"], "count": s["count"], "error": s["error"], "synced_at": s["synced_at"]}
            e["errors"] += s["status"] == "error"
            if s["synced_at"] and (not e["oldest"] or s["synced_at"] < e["oldest"]):
                e["oldest"] = s["synced_at"]
        states = self._q("SELECT service, state, COUNT(*) n FROM aws_cache_resources WHERE account_id=? GROUP BY service, state", (acct,))
        for s in states:
            if s["service"] in by_service:
                by_service[s["service"]].setdefault("states", {})[s["state"] or "-"] = s["n"]
        regions = self._q("SELECT region, COUNT(*) n FROM aws_cache_resources WHERE account_id=? GROUP BY region ORDER BY n DESC", (acct,))
        with self._lock:
            running = self._running.get(acct)
        return {"services": sorted(by_service.values(), key=lambda x: (x["category"], x["label"])), "regions": regions,
                "total": sum(x["count"] for x in by_service.values()), "config": self.account_config(acct),
                "running_job": self.job(running) if running else None, "last_jobs": self.jobs(acct, 5),
                "catalog": [{"id": k, "label": v[0], "category": v[1], "scope": v[3]} for k, v in col.SERVICES.items()],
                "interval_minutes": self.interval_minutes()}

    def resources(self, acct, service=None, region=None, q=None, state=None, tag=None, limit=100, offset=0, sort="name"):
        sql, args = "FROM aws_cache_resources WHERE account_id=?", [acct]
        if service:
            sql += " AND service=?"; args.append(service)
        if region:
            sql += " AND region=?"; args.append(region)
        if state:
            sql += " AND state=?"; args.append(state)
        if q:
            like = f"%{q.lower()}%"
            sql += " AND (lower(resource_id) LIKE ? OR lower(name) LIKE ? OR lower(summary) LIKE ? OR lower(tags) LIKE ?)"
            args += [like] * 4
        if tag and "=" in tag:
            k, v = tag.split("=", 1)
            sql += " AND tags LIKE ?"; args.append(f'%"{k}": "{v}"%')
        order = {"name": "(name IS NULL OR name = ''), lower(name), resource_id", "state": "state, lower(name)", "region": "region, lower(name)",
                 "service": "service, lower(name)", "fetched": "fetched_at DESC"}.get(sort, "lower(name)")
        total = self._q("SELECT COUNT(*) n " + sql, tuple(args), one=True)["n"]
        rows = self._q(f"SELECT account_id,region,service,resource_id,name,state,summary,tags,fetched_at {sql} ORDER BY {order} LIMIT ? OFFSET ?",
                       tuple(args + [max(1, min(limit, 1000)), max(0, offset)]))
        for r in rows:
            r["summary"], r["tags"] = json.loads(r["summary"] or "{}"), json.loads(r["tags"] or "{}")
            r["service_label"] = col.SERVICES.get(r["service"], (r["service"],))[0]
        return {"total": total, "items": rows}

    def resource(self, acct, region, service, rid):
        r = self._q("SELECT * FROM aws_cache_resources WHERE account_id=? AND region=? AND service=? AND resource_id=?", (acct, region, service, rid), one=True)
        if r:
            for k in ("summary", "tags", "detail"):
                r[k] = json.loads(r[k] or "{}")
        return r

    def forget(self, acct):
        with self.store._LOCK, self.store._connect() as conn:
            for t in ("aws_cache_resources", "aws_cache_slices", "aws_cache_accounts"):
                conn.execute(f"DELETE FROM {t} WHERE account_id=?", (acct,))
            conn.commit()
