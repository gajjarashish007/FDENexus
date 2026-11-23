"""M11 Observability & SRE.

Metrics, logs, traces, alerts, incidents, SLOs and reliability analytics.
Reads from CloudWatch (live reads) and the AWS cache (resources, clusters, databases).
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

API = "/api/m11"
SCHEMA = """
CREATE TABLE IF NOT EXISTS m11_services (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, tier TEXT, team TEXT, owner TEXT,
    health TEXT DEFAULT 'unknown', slo_target REAL, slo_window_days INTEGER DEFAULT 30,
    good_events INTEGER DEFAULT 0, total_events INTEGER DEFAULT 0, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_m11_services_health ON m11_services(health);
CREATE TABLE IF NOT EXISTS m11_incidents (
    id TEXT PRIMARY KEY, service_id TEXT, title TEXT NOT NULL, severity TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, acknowledged_at TEXT, resolved_at TEXT,
    created_by TEXT, acknowledged_by TEXT, resolved_by TEXT, rca TEXT, duration_minutes INTEGER
);
CREATE INDEX IF NOT EXISTS idx_m11_incidents_status ON m11_incidents(status, created_at DESC);
CREATE TABLE IF NOT EXISTS m11_alerts (
    id TEXT PRIMARY KEY, service_id TEXT, source TEXT NOT NULL, name TEXT NOT NULL,
    severity TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL,
    acknowledged_at TEXT, acknowledged_by TEXT, labels TEXT, annotations TEXT
);
CREATE INDEX IF NOT EXISTS idx_m11_alerts_status ON m11_alerts(status, created_at DESC);
CREATE TABLE IF NOT EXISTS m11_slos (
    id TEXT PRIMARY KEY, service_id TEXT NOT NULL, name TEXT NOT NULL, target REAL NOT NULL,
    window_days INTEGER DEFAULT 30, good_query TEXT, total_query TEXT, current REAL,
    error_budget_remaining REAL, updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_m11_slos_service ON m11_slos(service_id);
"""

SEVERITIES = ("critical", "high", "medium", "low", "info")
INCIDENT_STATUS = ("open", "investigating", "identified", "monitoring", "resolved")
ALERT_STATUS = ("firing", "resolved", "acknowledged", "silenced")


def _now():
    return datetime.now(timezone.utc)


def _ts(dt=None):
    return (dt or _now()).strftime("%Y-%m-%d %H:%M:%S")


def _parse(ts):
    return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) if ts else None


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

    # ================================================================ services
    @app.route(f"{API}/services")
    @auth
    def list_services():
        services = q("SELECT * FROM m11_services ORDER BY name")
        for s in services:
            slo = s.get("slo_target")
            if slo and s["total_events"] > 0:
                s["slo_current"] = round(100 * s["good_events"] / s["total_events"], 2)
                s["error_budget_remaining"] = round(s["slo_current"] - slo, 2)
        return jsonify({"services": services}), 200

    @app.route(f"{API}/services", methods=["POST"])
    @role("developer", "operator", "security", "admin")
    def create_service():
        d = body()
        name = str(d.get("name", "")).strip()
        if not 2 <= len(name) <= 80:
            return err("Name: 2-80 characters.")
        sid = "SVC-" + secrets.token_hex(4)
        x("""INSERT INTO m11_services (id,name,tier,team,owner,slo_target,slo_window_days,updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
          (sid, name, d.get("tier", ""), d.get("team", ""), d.get("owner", ""),
           d.get("slo_target"), d.get("slo_window_days", 30), _ts()))
        audit("service_created", sid, name)
        return jsonify({"service": q("SELECT * FROM m11_services WHERE id=?", (sid,), one=True)}), 201

    @app.route(f"{API}/services/<sid>", methods=["PUT"])
    @role("developer", "operator", "security", "admin")
    def update_service(sid):
        s = q("SELECT * FROM m11_services WHERE id=?", (sid,), one=True)
        if not s:
            return err("Not found.", 404)
        d = body()
        if "slo_target" in d:
            x("UPDATE m11_services SET slo_target=?, updated_at=? WHERE id=?",
              (d["slo_target"], _ts(), sid))
        if "health" in d:
            x("UPDATE m11_services SET health=?, updated_at=? WHERE id=?",
              (d["health"], _ts(), sid))
        audit("service_updated", sid)
        return jsonify({"service": q("SELECT * FROM m11_services WHERE id=?", (sid,), one=True)}), 200

    # ================================================================ incidents
    @app.route(f"{API}/incidents")
    @auth
    def list_incidents():
        status = request.args.get("status", "")
        limit = min(200, int(request.args.get("limit", 50)))
        sql = "SELECT * FROM m11_incidents"
        args = []
        if status:
            sql += " WHERE status=?"
            args.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        incidents = q(sql, args)
        return jsonify({"incidents": incidents}), 200

    @app.route(f"{API}/incidents", methods=["POST"])
    @auth
    def create_incident():
        d = body()
        title = str(d.get("title", "")).strip()
        if not 5 <= len(title) <= 200:
            return err("Title: 5-200 characters.")
        severity = str(d.get("severity", "high"))
        if severity not in SEVERITIES:
            return err(f"Severity must be one of: {', '.join(SEVERITIES)}.")
        iid = "INC-" + secrets.token_hex(4)
        x("""INSERT INTO m11_incidents (id,service_id,title,severity,status,created_at,created_by)
            VALUES (?,?,?,?,?,?,?)""",
          (iid, d.get("service_id"), title, severity, "open", _ts(), me()["username"]))
        audit("incident_created", iid, f"{title} {severity}")
        return jsonify({"incident": q("SELECT * FROM m11_incidents WHERE id=?", (iid,), one=True)}), 201

    @app.route(f"{API}/incidents/<iid>/acknowledge", methods=["POST"])
    @auth
    def ack_incident(iid):
        inc = q("SELECT * FROM m11_incidents WHERE id=?", (iid,), one=True)
        if not inc:
            return err("Not found.", 404)
        if inc["status"] not in ("open",):
            return err("Can only acknowledge open incidents.")
        x("UPDATE m11_incidents SET status='investigating', acknowledged_at=?, acknowledged_by=? WHERE id=?",
          (_ts(), me()["username"], iid))
        audit("incident_acknowledged", iid)
        return jsonify({"incident": q("SELECT * FROM m11_incidents WHERE id=?", (iid,), one=True)}), 200

    @app.route(f"{API}/incidents/<iid>/resolve", methods=["POST"])
    @auth
    def resolve_incident(iid):
        d = body()
        inc = q("SELECT * FROM m11_incidents WHERE id=?", (iid,), one=True)
        if not inc:
            return err("Not found.", 404)
        if inc["status"] in ("resolved",):
            return err("Incident already resolved.")
        created = _parse(inc["created_at"])
        duration = int((_now() - created).total_seconds() / 60)
        x("UPDATE m11_incidents SET status='resolved', resolved_at=?, resolved_by=?, rca=?, duration_minutes=? WHERE id=?",
          (_ts(), me()["username"], d.get("rca", ""), duration, iid))
        audit("incident_resolved", iid, f"duration {duration} min")
        return jsonify({"incident": q("SELECT * FROM m11_incidents WHERE id=?", (iid,), one=True)}), 200

    # ================================================================ alerts
    @app.route(f"{API}/alerts")
    @auth
    def list_alerts():
        status = request.args.get("status", "")
        limit = min(200, int(request.args.get("limit", 50)))
        sql = "SELECT * FROM m11_alerts"
        args = []
        if status:
            sql += " WHERE status=?"
            args.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        alerts = q(sql, args)
        for a in alerts:
            a["labels"] = json.loads(a["labels"] or "{}")
            a["annotations"] = json.loads(a["annotations"] or "{}")
        return jsonify({"alerts": alerts}), 200

    @app.route(f"{API}/alerts", methods=["POST"])
    @auth
    def create_alert():
        d = body()
        name = str(d.get("name", "")).strip()
        if not 2 <= len(name) <= 100:
            return err("Name: 2-100 characters.")
        severity = str(d.get("severity", "high"))
        if severity not in SEVERITIES:
            return err(f"Severity must be one of: {', '.join(SEVERITIES)}.")
        aid = "ALT-" + secrets.token_hex(4)
        x("""INSERT INTO m11_alerts (id,service_id,source,name,severity,status,created_at,labels,annotations)
            VALUES (?,?,?,?,?,?,?,?,?)""",
          (aid, d.get("service_id"), d.get("source", "manual"), name, severity, "firing", _ts(),
           json.dumps(d.get("labels", {})), json.dumps(d.get("annotations", {}))))
        audit("alert_created", aid, f"{name} {severity}")
        return jsonify({"alert": q("SELECT * FROM m11_alerts WHERE id=?", (aid,), one=True)}), 201

    @app.route(f"{API}/alerts/<aid>/acknowledge", methods=["POST"])
    @auth
    def ack_alert(aid):
        a = q("SELECT * FROM m11_alerts WHERE id=?", (aid,), one=True)
        if not a:
            return err("Not found.", 404)
        x("UPDATE m11_alerts SET status='acknowledged', acknowledged_at=?, acknowledged_by=? WHERE id=?",
          (_ts(), me()["username"], aid))
        audit("alert_acknowledged", aid)
        return jsonify({"alert": q("SELECT * FROM m11_alerts WHERE id=?", (aid,), one=True)}), 200

    @app.route(f"{API}/alerts/<aid>/resolve", methods=["POST"])
    @auth
    def resolve_alert(aid):
        a = q("SELECT * FROM m11_alerts WHERE id=?", (aid,), one=True)
        if not a:
            return err("Not found.", 404)
        x("UPDATE m11_alerts SET status='resolved' WHERE id=?", (aid,))
        audit("alert_resolved", aid)
        return jsonify({"alert": q("SELECT * FROM m11_alerts WHERE id=?", (aid,), one=True)}), 200

    # ================================================================ SLOs
    @app.route(f"{API}/slos")
    @auth
    def list_slos():
        slos = q("SELECT * FROM m11_slos ORDER BY name")
        for s in slos:
            if s["current"]:
                s["error_budget_remaining"] = round(s["current"] - s["target"], 2)
        return jsonify({"slos": slos}), 200

    @app.route(f"{API}/slos", methods=["POST"])
    @role("developer", "operator", "security", "admin")
    def create_slo():
        d = body()
        name = str(d.get("name", "")).strip()
        if not 2 <= len(name) <= 80:
            return err("Name: 2-80 characters.")
        target = float(d.get("target", 99.9))
        if not 0 < target <= 100:
            return err("Target must be 0-100.")
        sid = "SLO-" + secrets.token_hex(4)
        x("""INSERT INTO m11_slos (id,service_id,name,target,window_days,good_query,total_query,updated_at)
            VALUES (?,?,?,?,?,?,?,?)""",
          (sid, d.get("service_id"), name, target, d.get("window_days", 30),
           d.get("good_query", ""), d.get("total_query", ""), _ts()))
        audit("slo_created", sid, name)
        return jsonify({"slo": q("SELECT * FROM m11_slos WHERE id=?", (sid,), one=True)}), 201

    @app.route(f"{API}/slos/<sid>/record", methods=["POST"])
    @role("operator", "admin")
    def record_slo_event(sid):
        """Record good/total events for SLO calculation."""
        d = body()
        good = int(d.get("good", 0))
        total = int(d.get("total", 0))
        if total < good:
            return err("Total must be >= good.")
        x("UPDATE m11_slos SET current=?, updated_at=? WHERE id=?",
          (round(100 * good / total, 4) if total > 0 else None, _ts(), sid))
        audit("slo_recorded", sid, f"good={good} total={total}")
        return jsonify({"slo": q("SELECT * FROM m11_slos WHERE id=?", (sid,), one=True)}), 200

    # ================================================================ CloudWatch integration
    @app.route(f"{API}/cloudwatch/metrics")
    @auth
    def cw_metrics():
        """Fetch CloudWatch metrics for a service."""
        account = request.args.get("account", "")
        region = request.args.get("region", "eu-west-1")
        namespace = request.args.get("namespace", "AWS/EC2")
        metric = request.args.get("metric", "CPUUtilization")
        period = int(request.args.get("period", 300))
        hours = int(request.args.get("hours", 1))

        if not cfg.LIVE_READS:
            return jsonify({"error": "Live reads are off.", "datapoints": []}), 200

        acct = store.get_aws_account(account)
        if not acct:
            return err("Pick a connected AWS account.")

        try:
            cw = m01_ec2._session(acct, region).client("cloudwatch", region_name=region)
            end = _now()
            start = end - timedelta(hours=hours)
            resp = cw.get_metric_statistics(
                Namespace=namespace, MetricName=metric,
                StartTime=start, EndTime=end, Period=period,
                Statistics=["Average", "Maximum", "Minimum"]
            )
            dps = sorted(resp.get("Datapoints", []), key=lambda x: x["Timestamp"])
            return jsonify({"datapoints": dps, "namespace": namespace, "metric": metric}), 200
        except Exception as e:
            return err(f"CloudWatch error: {str(e)[:200]}", 502)

    @app.route(f"{API}/cloudwatch/alarms")
    @auth
    def cw_alarms():
        """Fetch CloudWatch alarms for an account."""
        account = request.args.get("account", "")
        region = request.args.get("region", "eu-west-1")

        if not cfg.LIVE_READS:
            return jsonify({"error": "Live reads are off.", "alarms": []}), 200

        acct = store.get_aws_account(account)
        if not acct:
            return err("Pick a connected AWS account.")

        try:
            cw = m01_ec2._session(acct, region).client("cloudwatch", region_name=region)
            alarms = []
            for page in cw.get_paginator("describe_alarms").paginate():
                for a in page.get("MetricAlarms", []):
                    alarms.append({
                        "name": a["AlarmName"], "state": a["StateValue"],
                        "metric": a.get("MetricName", ""), "namespace": a.get("Namespace", ""),
                        "threshold": a.get("Threshold"), "comparison": a.get("ComparisonOperator"),
                        "period": a.get("Period"), "eval_periods": a.get("EvaluationPeriods"),
                        "updated": a.get("StateUpdatedTimestamp")
                    })
                if len(alarms) >= 200:
                    break
            return jsonify({"alarms": alarms, "count": len(alarms)}), 200
        except Exception as e:
            return err(f"CloudWatch error: {str(e)[:200]}", 502)

    # ================================================================ overview
    @app.route(f"{API}/overview")
    @auth
    def overview():
        services = q("SELECT id,health FROM m11_services")
        incidents = q("SELECT id,severity,status FROM m11_incidents WHERE status IN ('open','investigating','identified')")
        alerts = q("SELECT id,severity FROM m11_alerts WHERE status='firing'")
        slos = q("SELECT id,target,current FROM m11_slos WHERE current IS NOT NULL")

        healthy = sum(1 for s in services if s["health"] == "healthy")
        degraded = sum(1 for s in services if s["health"] == "degraded")
        down = sum(1 for s in services if s["health"] == "down")

        slo_burn = sum(1 for s in slos if s["current"] and s["current"] < s["target"])

        return jsonify({
            "services": len(services),
            "services_by_health": {"healthy": healthy, "degraded": degraded, "down": down, "unknown": len(services) - healthy - degraded - down},
            "incidents_open": len(incidents),
            "incidents_by_severity": {s: sum(1 for i in incidents if i["severity"] == s) for s in SEVERITIES},
            "alerts_firing": len(alerts),
            "alerts_by_severity": {s: sum(1 for a in alerts if a["severity"] == s) for s in SEVERITIES},
            "slos_total": len(slos),
            "slos_burning": slo_burn
        }), 200
