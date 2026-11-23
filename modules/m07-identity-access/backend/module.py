"""M07 Identity & Access Management.

Plugs into the platform sign-in through ctx.identity hooks:
  on_token      every issued token becomes a tracked session (revocable, idle timeout, audit)
  on_login      MFA challenge when the user enrolled TOTP
  on_auth       revoked sessions, expired users, just-in-time role elevation
  resolve_token service identities (fdx_... API tokens)
Plus SSO (OIDC), SCIM 2.0 provisioning, access reviews, ABAC rules, IAM role analysis and
workload identity (EKS Pod Identity / IRSA) from the AWS cache and live read-only calls.
"""
from __future__ import annotations

import json
import re
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
from flask import has_request_context, jsonify, redirect, request

import m07_crypto as cr
import m07_oidc as oidc

API = "/api/m07"
SCHEMA = """
CREATE TABLE IF NOT EXISTS m07_sessions (
    jti TEXT PRIMARY KEY, user_id INTEGER NOT NULL, username TEXT, method TEXT, ip TEXT, user_agent TEXT,
    created_at TEXT NOT NULL, expires_at TEXT NOT NULL, last_seen TEXT, revoked_at TEXT, revoked_by TEXT, elevated INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_m07_sess_user ON m07_sessions(user_id, created_at);
CREATE TABLE IF NOT EXISTS m07_mfa (
    user_id INTEGER PRIMARY KEY, secret TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0, recovery TEXT,
    last_step INTEGER DEFAULT 0, created_at TEXT NOT NULL, enabled_at TEXT
);
CREATE TABLE IF NOT EXISTS m07_jit (
    id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, username TEXT, role_from TEXT, role_to TEXT NOT NULL, reason TEXT,
    hours REAL NOT NULL, status TEXT NOT NULL, requested_at TEXT NOT NULL, approver TEXT, decided_at TEXT,
    expires_at TEXT, ended_at TEXT
);
CREATE TABLE IF NOT EXISTS m07_service_tokens (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE, prefix TEXT,
    created_by TEXT, created_at TEXT NOT NULL, expires_at TEXT, last_used TEXT, revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS m07_user_expiry (user_id INTEGER PRIMARY KEY, expires_at TEXT NOT NULL, reason TEXT, set_by TEXT);
CREATE TABLE IF NOT EXISTS m07_reviews (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, scope TEXT, status TEXT NOT NULL, created_by TEXT, created_at TEXT NOT NULL,
    due_at TEXT, closed_at TEXT, closed_by TEXT
);
CREATE TABLE IF NOT EXISTS m07_review_items (
    review_id TEXT NOT NULL, user_id INTEGER NOT NULL, username TEXT, email TEXT, role TEXT, team TEXT, last_login TEXT,
    decision TEXT, decided_by TEXT, decided_at TEXT, note TEXT, PRIMARY KEY (review_id, user_id)
);
CREATE TABLE IF NOT EXISTS m07_sso_state (state TEXT PRIMARY KEY, data TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS m07_identities (
    provider TEXT NOT NULL, subject TEXT NOT NULL, user_id INTEGER NOT NULL, email TEXT, last_login TEXT,
    PRIMARY KEY (provider, subject)
);
"""
RANK = {"viewer": 1, "developer": 2, "approver": 3, "operator": 3, "security": 3, "admin": 9}
SVC_ROLES = ("viewer", "developer", "operator")
SVC_BASE = 10_000_000  # service identities use negative ids below -SVC_BASE


def _now_dt():
    return datetime.now(timezone.utc)


def _ts(dt=None):
    return (dt or _now_dt()).strftime("%Y-%m-%d %H:%M:%S")


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

    def audit(action, target="", details="", level="info", user=None):
        u = user or (getattr(request, "current_user", None) or {})
        store.add_audit(u.get("id"), u.get("username", "system"), action, target=target, details=str(details)[:500], level=level)

    def settings():
        s = ctx.get_setting("m07.settings", {}) or {}
        return {"mfa_required_roles": s.get("mfa_required_roles", ["admin"]), "session_idle_minutes": int(s.get("session_idle_minutes", 120)),
                "max_jit_hours": int(s.get("max_jit_hours", 8)), "abac_team_scope": bool(s.get("abac_team_scope", False)),
                "abac_prod_requires_mfa": bool(s.get("abac_prod_requires_mfa", False))}

    # ================================================================== hooks
    def on_token(user, payload):
        ok = has_request_context()
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip() if ok else ""
        ua = (request.headers.get("User-Agent", "") if ok else "")[:200]
        x("INSERT OR REPLACE INTO m07_sessions (jti,user_id,username,method,ip,user_agent,created_at,expires_at,last_seen) VALUES (?,?,?,?,?,?,?,?,?)",
          (payload["jti"], user["id"], user["username"], payload.get("amr", "password"), ip, ua, _ts(), _ts(payload["exp"]), _ts()))

    last_seen_cache: dict[str, float] = {}

    def on_auth(user, payload):
        jti = payload.get("jti")
        if jti:
            s = q("SELECT revoked_at,last_seen FROM m07_sessions WHERE jti=?", (jti,), one=True)
            if s and s["revoked_at"]:
                return ("This session was signed out. Sign in again.", 401)
            idle = settings()["session_idle_minutes"]
            if s and idle and s["last_seen"] and (_now_dt() - _parse(s["last_seen"])).total_seconds() > idle * 60:
                x("UPDATE m07_sessions SET revoked_at=?, revoked_by='idle-timeout' WHERE jti=?", (_ts(), jti))
                return (f"Signed out after {idle} minutes without activity.", 401)
            if time.time() - last_seen_cache.get(jti, 0) > 60:
                last_seen_cache[jti] = time.time()
                x("UPDATE m07_sessions SET last_seen=? WHERE jti=?", (_ts(), jti))
        exp = q("SELECT expires_at FROM m07_user_expiry WHERE user_id=?", (user["id"],), one=True)
        if exp and _parse(exp["expires_at"]) <= _now_dt():
            return ("Your access has expired. Ask an administrator to extend it.", 403)
        j = q("SELECT * FROM m07_jit WHERE user_id=? AND status='active' ORDER BY expires_at DESC LIMIT 1", (user["id"],), one=True)
        if j and _parse(j["expires_at"]) > _now_dt():
            user = dict(user, role=j["role_to"], base_role=user["role"], jit={"id": j["id"], "role": j["role_to"], "expires_at": j["expires_at"]})
            if jti:
                x("UPDATE m07_sessions SET elevated=1 WHERE jti=? AND elevated=0", (jti,))
        user = dict(user, amr=payload.get("amr", "password"))
        return user

    def on_login(user, d):
        m = q("SELECT enabled FROM m07_mfa WHERE user_id=?", (user["id"],), one=True)
        if not m or not m["enabled"]:
            return None
        challenge = jwt.encode({"sub": str(user["id"]), "purpose": "mfa", "exp": _now_dt() + timedelta(minutes=5)},
                               cfg.JWT_SECRET, algorithm="HS256")
        return jsonify({"mfa_required": True, "mfa_token": challenge, "user": {"username": user["username"]}}), 200

    def resolve_token(raw):
        if not raw.startswith("fdx_"):
            return None
        t = q("SELECT * FROM m07_service_tokens WHERE token_hash=?", (cr.hash_token(raw),), one=True)
        if not t or t["revoked_at"]:
            return ("Invalid or revoked service token.", 401)
        if t["expires_at"] and _parse(t["expires_at"]) <= _now_dt():
            return ("Service token expired.", 401)
        if not t["last_used"] or (_now_dt() - _parse(t["last_used"])).total_seconds() > 60:
            x("UPDATE m07_service_tokens SET last_used=? WHERE id=?", (_ts(), t["id"]))
        n = int(t["id"].split("-")[1], 16)
        return {"id": -(SVC_BASE + n), "username": f"svc:{t['name']}", "email": "", "role": t["role"], "team": "service",
                "status": "approved", "service_token": t["id"], "amr": "service-token"}

    ctx.identity["on_token"].append(on_token)
    ctx.identity["on_auth"].append(on_auth)
    ctx.identity["on_login"].append(on_login)
    ctx.identity["resolve_token"].append(resolve_token)

    # ABAC, used by M02 (and any module) before infrastructure changes
    def abac_check(user, resource: dict):
        s = settings()
        if user.get("role") == "admin":
            return None
        if s["abac_team_scope"] and resource.get("team") and user.get("role") in ("developer", "viewer"):
            if str(user.get("team", "")).strip().lower() != str(resource["team"]).strip().lower():
                return f"Access rule: your team ({user.get('team') or 'none'}) does not own {resource.get('name', 'this resource')} (team {resource['team']})."
        if s["abac_prod_requires_mfa"] and resource.get("tier") == "production" and user.get("amr") not in ("mfa", "sso"):
            return "Access rule: production changes need a session signed in with MFA or SSO."
        return None
    ctx.services["abac"] = abac_check

    # ================================================================== automatic revocation
    def sweep():
        now = _ts()
        for j in q("SELECT * FROM m07_jit WHERE status='active' AND expires_at<=?", (now,)):
            x("UPDATE m07_jit SET status='expired', ended_at=? WHERE id=?", (now, j["id"]))
            store.add_audit(None, "m07", "jit_expired", target=j["username"], details=f"{j['role_to']} {j['id']}")
        for e in q("SELECT e.user_id, u.username FROM m07_user_expiry e JOIN users u ON u.id=e.user_id WHERE e.expires_at<=? AND u.status='approved'", (now,)):
            store.set_user_status(e["user_id"], "disabled", None)
            x("UPDATE m07_sessions SET revoked_at=?, revoked_by='access-expired' WHERE user_id=? AND revoked_at IS NULL", (now, e["user_id"]))
            store.add_audit(None, "m07", "access_expired", target=e["username"], level="warn")
        x("UPDATE m07_service_tokens SET revoked_at=? WHERE revoked_at IS NULL AND expires_at IS NOT NULL AND expires_at<=?", (now, now))
        x("DELETE FROM m07_sso_state WHERE created_at < ?", (time.time() - 900,))

    def sweeper():
        while True:
            time.sleep(60)
            try:
                sweep()
            except Exception:
                pass
    threading.Thread(target=sweeper, name="m07-sweeper", daemon=True).start()

    # ================================================================== overview
    @app.route(f"{API}/overview")
    @auth
    def overview():
        u = me()
        users = store.list_users()
        mfa = {r["user_id"] for r in q("SELECT user_id FROM m07_mfa WHERE enabled=1")}
        req = set(settings()["mfa_required_roles"])
        active_sessions = q("SELECT COUNT(*) n FROM m07_sessions WHERE revoked_at IS NULL AND expires_at>?", (_ts(),), one=True)["n"]
        return jsonify({
            "me": {"username": u["username"], "role": u["role"], "base_role": u.get("base_role"), "jit": u.get("jit"), "amr": u.get("amr"),
                   "mfa_enabled": u["id"] in mfa, "mfa_required": u.get("base_role", u["role"]) in req},
            "users": len([x_ for x_ in users if x_["status"] == "approved"]),
            "mfa_coverage": {"enrolled": len([x_ for x_ in users if x_["id"] in mfa and x_["status"] == "approved"]),
                             "required_missing": [x_["username"] for x_ in users if x_["status"] == "approved" and x_["role"] in req and x_["id"] not in mfa]},
            "active_sessions": active_sessions,
            "pending_jit": q("SELECT COUNT(*) n FROM m07_jit WHERE status='pending'", one=True)["n"],
            "active_jit": q("SELECT COUNT(*) n FROM m07_jit WHERE status='active'", one=True)["n"],
            "open_reviews": q("SELECT COUNT(*) n FROM m07_reviews WHERE status='open'", one=True)["n"],
            "service_tokens": q("SELECT COUNT(*) n FROM m07_service_tokens WHERE revoked_at IS NULL", one=True)["n"],
            "expiring": q("SELECT e.expires_at, u.username FROM m07_user_expiry e JOIN users u ON u.id=e.user_id WHERE u.status='approved' ORDER BY e.expires_at LIMIT 10"),
            "settings": settings(), "sso": sso_public(),
        }), 200

    @app.route(f"{API}/settings", methods=["PUT"])
    @admin
    def put_settings():
        d, s = body(), settings()
        if "mfa_required_roles" in d:
            roles = [r for r in d["mfa_required_roles"] if r in RANK]
            s["mfa_required_roles"] = roles
        if "session_idle_minutes" in d:
            v = int(d["session_idle_minutes"])
            if not 0 <= v <= 1440:
                return err("Idle timeout must be 0 (off) to 1440 minutes.")
            s["session_idle_minutes"] = v
        if "max_jit_hours" in d:
            s["max_jit_hours"] = max(1, min(int(d["max_jit_hours"]), 24))
        for k in ("abac_team_scope", "abac_prod_requires_mfa"):
            if k in d:
                s[k] = bool(d[k])
        ctx.set_setting("m07.settings", s)
        audit("m07_settings_updated", details=json.dumps(d))
        return jsonify({"settings": settings()}), 200

    # ================================================================== sessions (session auditing)
    @app.route(f"{API}/sessions")
    @auth
    def sessions():
        u = me()
        everyone = request.args.get("all") == "1" and u["role"] in ("admin", "security")
        sql = "SELECT * FROM m07_sessions" + ("" if everyone else " WHERE user_id=?") + " ORDER BY created_at DESC LIMIT 300"
        rows = q(sql, () if everyone else (u["id"],))
        cur = (getattr(request, "token_payload", None) or {}).get("jti")
        now = _now_dt()
        for r in rows:
            r["current"] = r["jti"] == cur
            r["active"] = not r["revoked_at"] and _parse(r["expires_at"]) > now
            r["id"] = r.pop("jti")[:10]
        return jsonify({"sessions": rows}), 200

    @app.route(f"{API}/sessions/revoke", methods=["POST"])
    @auth
    def revoke_sessions():
        u, d = me(), body()
        sid, uid = str(d.get("id", "")), d.get("user_id")
        if uid is not None:
            if u["role"] not in ("admin", "security") and int(uid) != u["id"]:
                return err("You can only sign out your own sessions.", 403)
            cur = (getattr(request, "token_payload", None) or {}).get("jti", "")
            x("UPDATE m07_sessions SET revoked_at=?, revoked_by=? WHERE user_id=? AND revoked_at IS NULL AND jti<>?",
              (_ts(), u["username"], int(uid), cur if int(uid) == u["id"] else ""))
            audit("sessions_revoked", target=str(uid), level="warn")
            return jsonify({"message": "Signed out."}), 200
        s = q("SELECT * FROM m07_sessions WHERE jti LIKE ?", (sid + "%",), one=True) if len(sid) >= 8 else None
        if not s:
            return err("Unknown session", 404)
        if s["user_id"] != u["id"] and u["role"] not in ("admin", "security"):
            return err("You can only sign out your own sessions.", 403)
        x("UPDATE m07_sessions SET revoked_at=?, revoked_by=? WHERE jti=?", (_ts(), u["username"], s["jti"]))
        audit("session_revoked", target=s["username"], details=sid, level="warn")
        return jsonify({"message": "Session signed out."}), 200

    # ================================================================== MFA (TOTP)
    @app.route(f"{API}/mfa/enroll", methods=["POST"])
    @auth
    def mfa_enroll():
        u = me()
        if u["id"] < 0:
            return err("Service identities cannot use MFA.")
        if q("SELECT 1 FROM m07_mfa WHERE user_id=? AND enabled=1", (u["id"],), one=True):
            return err("MFA is already on. Turn it off first to enroll a new device.")
        secret = cr.new_totp_secret()
        x("INSERT OR REPLACE INTO m07_mfa (user_id,secret,enabled,created_at) VALUES (?,?,0,?)", (u["id"], cr.encrypt(cfg.JWT_SECRET, secret), _ts()))
        return jsonify({"secret": secret, "otpauth": cr.otpauth_uri(secret, u.get("email") or u["username"])}), 200

    @app.route(f"{API}/mfa/verify", methods=["POST"])
    @auth
    def mfa_verify():
        u = me()
        m = q("SELECT * FROM m07_mfa WHERE user_id=?", (u["id"],), one=True)
        if not m:
            return err("Start enrollment first.")
        step = cr.verify_totp(cr.decrypt(cfg.JWT_SECRET, m["secret"]), body().get("code"))
        if step is None:
            return err("That code is not valid. Check the time on your phone and try the current code.")
        codes = cr.new_recovery_codes()
        x("UPDATE m07_mfa SET enabled=1, enabled_at=?, last_step=?, recovery=? WHERE user_id=?",
          (_ts(), step, json.dumps([cr.hash_token(c) for c in codes]), u["id"]))
        audit("mfa_enabled", target=u["username"])
        return jsonify({"enabled": True, "recovery_codes": codes}), 200

    @app.route(f"{API}/mfa/disable", methods=["POST"])
    @auth
    def mfa_disable():
        u = me()
        m = q("SELECT * FROM m07_mfa WHERE user_id=? AND enabled=1", (u["id"],), one=True)
        if not m:
            return err("MFA is not on.")
        if cr.verify_totp(cr.decrypt(cfg.JWT_SECRET, m["secret"]), body().get("code")) is None:
            return err("Enter a current code from your authenticator to turn MFA off.")
        x("DELETE FROM m07_mfa WHERE user_id=?", (u["id"],))
        audit("mfa_disabled", target=u["username"], level="warn")
        return jsonify({"enabled": False}), 200

    @app.route(f"{API}/users/<int:uid>/mfa/reset", methods=["POST"])
    @admin
    def mfa_reset(uid):
        if uid == me()["id"]:
            return err("Reset your own MFA from Settings.")
        x("DELETE FROM m07_mfa WHERE user_id=?", (uid,))
        audit("mfa_reset", target=str(uid), level="warn")
        return jsonify({"message": "MFA removed. The user can enroll again."}), 200

    @app.route(f"{API}/mfa/login", methods=["POST"])
    def mfa_login():
        d = body()
        try:
            p = jwt.decode(str(d.get("mfa_token", "")), cfg.JWT_SECRET, algorithms=["HS256"])
            if p.get("purpose") != "mfa":
                raise jwt.InvalidTokenError()
        except jwt.PyJWTError:
            return err("The sign-in step expired. Enter your password again.", 401)
        uid = int(p["sub"])
        user = store.get_user(uid)
        m = q("SELECT * FROM m07_mfa WHERE user_id=? AND enabled=1", (uid,), one=True)
        if not user or not m or user["status"] != "approved":
            return err("Sign-in failed.", 401)
        code = str(d.get("code", "")).strip()
        ok = False
        if re.fullmatch(r"[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}", code):
            rec = json.loads(m["recovery"] or "[]")
            h = cr.hash_token(code)
            if h in rec:
                rec.remove(h)
                x("UPDATE m07_mfa SET recovery=? WHERE user_id=?", (json.dumps(rec), uid))
                ok, used = True, "recovery code"
        else:
            step = cr.verify_totp(cr.decrypt(cfg.JWT_SECRET, m["secret"]), code)
            if step is not None and step > (m["last_step"] or 0):  # no replay of a used code
                x("UPDATE m07_mfa SET last_step=? WHERE user_id=?", (step, uid))
                ok, used = True, "authenticator"
        if not ok:
            store.add_audit(uid, user["username"], "mfa_failed", level="warn")
            return err("That code is not valid.", 401)
        token = ctx.issue_token(user, "mfa")
        store.add_audit(uid, user["username"], "login", details=f"password + MFA ({used})")
        return jsonify({"token": token, "user": user}), 200

    # ================================================================== just-in-time / privileged access
    @app.route(f"{API}/jit")
    @auth
    def jit_list():
        u = me()
        everyone = u.get("base_role", u["role"]) in ("admin", "security")
        rows = q("SELECT * FROM m07_jit" + ("" if everyone else " WHERE user_id=?") + " ORDER BY requested_at DESC LIMIT 200",
                 () if everyone else (u["id"],))
        return jsonify({"requests": rows, "max_hours": settings()["max_jit_hours"]}), 200

    @app.route(f"{API}/jit", methods=["POST"])
    @auth
    def jit_request():
        u, d = me(), body()
        base = u.get("base_role", u["role"])
        target, reason = d.get("role"), str(d.get("reason", "")).strip()
        try:
            hours = float(d.get("hours", 1))
        except (TypeError, ValueError):
            return err("Hours must be a number.")
        if u["id"] < 0:
            return err("Service identities cannot request elevation.")
        if target not in RANK or RANK[target] <= RANK.get(base, 0):
            return err("Pick a role above your current one.")
        if not 0.25 <= hours <= settings()["max_jit_hours"]:
            return err(f"Duration: 15 minutes to {settings()['max_jit_hours']} hours.")
        if len(reason) < 10:
            return err("Give a reason (ticket or incident number and why).")
        if q("SELECT 1 FROM m07_jit WHERE user_id=? AND status IN ('pending','active')", (u["id"],), one=True):
            return err("You already have a pending or active elevation.")
        jid = "JIT-" + secrets.token_hex(3)
        x("INSERT INTO m07_jit (id,user_id,username,role_from,role_to,reason,hours,status,requested_at) VALUES (?,?,?,?,?,?,?,?,?)",
          (jid, u["id"], u["username"], base, target, reason[:500], hours, "pending", _ts()))
        store.add_notification(None, "warning", "Access elevation requested", f"{u['username']} asks for {target} for {hours} h: {reason[:120]}")
        audit("jit_requested", target=jid, details=f"{base}->{target} {hours}h: {reason}")
        return jsonify({"request": q("SELECT * FROM m07_jit WHERE id=?", (jid,), one=True)}), 201

    @app.route(f"{API}/jit/<jid>/<action>", methods=["POST"])
    @auth
    def jit_decide(jid, action):
        u = me()
        j = q("SELECT * FROM m07_jit WHERE id=?", (jid,), one=True)
        if not j:
            return err("Unknown request", 404)
        if action == "revoke":
            if j["status"] not in ("active", "pending"):
                return err("Nothing to revoke.")
            if j["user_id"] != u["id"] and u.get("base_role", u["role"]) not in ("admin", "security"):
                return err("Not allowed.", 403)
            x("UPDATE m07_jit SET status='revoked', ended_at=? WHERE id=?", (_ts(), jid))
            audit("jit_revoked", target=jid, level="warn")
            return jsonify({"request": q("SELECT * FROM m07_jit WHERE id=?", (jid,), one=True)}), 200
        if action not in ("approve", "reject"):
            return err("Unknown action", 404)
        if u.get("base_role", u["role"]) != "admin":
            return err("Only administrators approve elevation.", 403)
        if j["user_id"] == u["id"]:
            return err("You cannot approve your own elevation (separation of duties).", 403)
        if j["status"] != "pending":
            return err(f"Request is {j['status']}.")
        if action == "reject":
            x("UPDATE m07_jit SET status='rejected', approver=?, decided_at=? WHERE id=?", (u["username"], _ts(), jid))
            store.add_notification(j["user_id"], "warning", "Elevation rejected", f"{j['role_to']} ({jid})")
            audit("jit_rejected", target=jid)
        else:
            exp = _ts(_now_dt() + timedelta(hours=j["hours"]))
            x("UPDATE m07_jit SET status='active', approver=?, decided_at=?, expires_at=? WHERE id=?", (u["username"], _ts(), exp, jid))
            store.add_notification(j["user_id"], "success", "Elevation approved", f"You are {j['role_to']} until {exp} UTC ({jid}).")
            audit("jit_approved", target=jid, details=f"{j['username']} {j['role_from']}->{j['role_to']} until {exp}", level="warn")
        return jsonify({"request": q("SELECT * FROM m07_jit WHERE id=?", (jid,), one=True)}), 200

    # ================================================================== access expiration
    @app.route(f"{API}/users")
    @role("admin", "security")
    def users_view():
        mfa = {r["user_id"] for r in q("SELECT user_id FROM m07_mfa WHERE enabled=1")}
        exp = {r["user_id"]: r for r in q("SELECT * FROM m07_user_expiry")}
        idents = {}
        for r in q("SELECT provider, user_id FROM m07_identities"):
            idents.setdefault(r["user_id"], []).append(r["provider"])
        sess = {r["user_id"]: r["n"] for r in q("SELECT user_id, COUNT(*) n FROM m07_sessions WHERE revoked_at IS NULL AND expires_at>? GROUP BY user_id", (_ts(),))}
        jit = {r["user_id"]: r for r in q("SELECT * FROM m07_jit WHERE status='active'")}
        out = []
        for u in store.list_users():
            out.append({**u, "mfa_enabled": u["id"] in mfa, "expires_at": (exp.get(u["id"]) or {}).get("expires_at"),
                        "expiry_reason": (exp.get(u["id"]) or {}).get("reason"), "sources": idents.get(u["id"], ["local"]),
                        "active_sessions": sess.get(u["id"], 0), "jit": jit.get(u["id"])})
        return jsonify({"users": out, "mfa_required_roles": settings()["mfa_required_roles"]}), 200

    @app.route(f"{API}/users/<int:uid>/expiry", methods=["PUT"])
    @admin
    def set_expiry(uid):
        d = body()
        if uid == me()["id"]:
            return err("You cannot set an expiry on your own account.")
        if not d.get("expires_at"):
            x("DELETE FROM m07_user_expiry WHERE user_id=?", (uid,))
            audit("access_expiry_removed", target=str(uid))
            return jsonify({"expires_at": None}), 200
        try:
            dt = datetime.strptime(str(d["expires_at"])[:10], "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=timezone.utc)
        except ValueError:
            return err("Date must be YYYY-MM-DD.")
        if dt <= _now_dt():
            return err("Pick a future date.")
        x("INSERT INTO m07_user_expiry (user_id,expires_at,reason,set_by) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at, reason=excluded.reason, set_by=excluded.set_by",
          (uid, _ts(dt), str(d.get("reason", ""))[:200], me()["username"]))
        audit("access_expiry_set", target=str(uid), details=_ts(dt))
        return jsonify({"expires_at": _ts(dt)}), 200

    # ================================================================== access reviews
    @app.route(f"{API}/reviews")
    @role("admin", "security")
    def reviews():
        rows = q("SELECT * FROM m07_reviews ORDER BY created_at DESC LIMIT 50")
        for r in rows:
            st = q("SELECT COUNT(*) total, SUM(decision IS NOT NULL) decided, SUM(decision='revoke') revoke FROM m07_review_items WHERE review_id=?", (r["id"],), one=True)
            r.update({k: st[k] or 0 for k in ("total", "decided", "revoke")})
        return jsonify({"reviews": rows}), 200

    @app.route(f"{API}/reviews", methods=["POST"])
    @role("admin", "security")
    def review_create():
        d = body()
        name = str(d.get("name", "")).strip() or f"Access review {_now_dt():%Y-%m}"
        scope = d.get("scope", "all")
        days = max(1, min(int(d.get("due_days", 14)), 90))
        users = [u for u in store.list_users() if u["status"] == "approved" and (scope == "all" or u["role"] == scope or (scope == "privileged" and RANK.get(u["role"], 0) >= 3))]
        if not users:
            return err("No users in that scope.")
        rid = "REV-" + secrets.token_hex(3)
        x("INSERT INTO m07_reviews (id,name,scope,status,created_by,created_at,due_at) VALUES (?,?,?,?,?,?,?)",
          (rid, name[:120], scope, "open", me()["username"], _ts(), _ts(_now_dt() + timedelta(days=days))))
        with store._LOCK, store._connect() as conn:
            conn.executemany("INSERT INTO m07_review_items (review_id,user_id,username,email,role,team,last_login) VALUES (?,?,?,?,?,?,?)",
                             [(rid, u["id"], u["username"], u["email"], u["role"], u.get("team"), u.get("last_login")) for u in users])
            conn.commit()
        audit("access_review_started", target=rid, details=f"{len(users)} users, scope {scope}")
        return jsonify({"review": rid}), 201

    @app.route(f"{API}/reviews/<rid>")
    @role("admin", "security")
    def review_get(rid):
        r = q("SELECT * FROM m07_reviews WHERE id=?", (rid,), one=True)
        if not r:
            return err("Unknown review", 404)
        return jsonify({"review": r, "items": q("SELECT * FROM m07_review_items WHERE review_id=? ORDER BY role, username", (rid,))}), 200

    @app.route(f"{API}/reviews/<rid>/decide", methods=["POST"])
    @role("admin", "security")
    def review_decide(rid):
        d, u = body(), me()
        r = q("SELECT * FROM m07_reviews WHERE id=?", (rid,), one=True)
        if not r or r["status"] != "open":
            return err("Review is not open.")
        if d.get("decision") not in ("keep", "revoke", None):
            return err("Decision must be keep or revoke.")
        uid = int(d.get("user_id", 0))
        if uid == u["id"]:
            return err("You cannot certify your own access.", 403)
        x("UPDATE m07_review_items SET decision=?, decided_by=?, decided_at=?, note=? WHERE review_id=? AND user_id=?",
          (d.get("decision"), u["username"], _ts(), str(d.get("note", ""))[:200], rid, uid))
        return jsonify({"ok": True}), 200

    @app.route(f"{API}/reviews/<rid>/close", methods=["POST"])
    @role("admin", "security")
    def review_close(rid):
        r = q("SELECT * FROM m07_reviews WHERE id=?", (rid,), one=True)
        if not r or r["status"] != "open":
            return err("Review is not open.")
        undecided = q("SELECT COUNT(*) n FROM m07_review_items WHERE review_id=? AND decision IS NULL", (rid,), one=True)["n"]
        if undecided and not body().get("force"):
            return err(f"{undecided} user(s) still need a decision.")
        revoked = []
        for it in q("SELECT * FROM m07_review_items WHERE review_id=? AND decision='revoke'", (rid,)):
            store.set_user_status(it["user_id"], "disabled", me()["id"])
            x("UPDATE m07_sessions SET revoked_at=?, revoked_by=? WHERE user_id=? AND revoked_at IS NULL", (_ts(), f"review {rid}", it["user_id"]))
            x("UPDATE m07_jit SET status='revoked', ended_at=? WHERE user_id=? AND status IN ('pending','active')", (_ts(), it["user_id"]))
            revoked.append(it["username"])
        x("UPDATE m07_reviews SET status='closed', closed_at=?, closed_by=? WHERE id=?", (_ts(), me()["username"], rid))
        audit("access_review_closed", target=rid, details=f"revoked: {', '.join(revoked) or 'none'}", level="warn" if revoked else "info")
        return jsonify({"revoked": revoked}), 200

    # ================================================================== service identities
    @app.route(f"{API}/tokens")
    @admin
    def tokens():
        return jsonify({"tokens": [{k: v for k, v in t.items() if k != "token_hash"} for t in q("SELECT * FROM m07_service_tokens ORDER BY created_at DESC")]}), 200

    @app.route(f"{API}/tokens", methods=["POST"])
    @admin
    def token_create():
        d = body()
        name = str(d.get("name", "")).strip()
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,40}", name):
            return err("Name: 3-41 lowercase letters, digits and hyphens (e.g. gitlab-ci).")
        if d.get("role") not in SVC_ROLES:
            return err(f"Role must be one of {', '.join(SVC_ROLES)} (service identities never get admin).")
        try:
            days = int(d.get("days", 90))
        except (TypeError, ValueError):
            days = 0
        if not 1 <= days <= 365:
            return err("Lifetime: 1 to 365 days.")
        raw = "fdx_" + secrets.token_urlsafe(32)
        tid = "SVC-" + secrets.token_hex(3)
        x("INSERT INTO m07_service_tokens (id,name,role,token_hash,prefix,created_by,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?)",
          (tid, name, d["role"], cr.hash_token(raw), raw[:10], me()["username"], _ts(), _ts(_now_dt() + timedelta(days=days))))
        audit("service_token_created", target=tid, details=f"{name} role={d['role']} {days}d")
        return jsonify({"token": raw, "id": tid, "note": "Copy it now. It is shown only once and stored as a hash."}), 201

    @app.route(f"{API}/tokens/<tid>/revoke", methods=["POST"])
    @admin
    def token_revoke(tid):
        x("UPDATE m07_service_tokens SET revoked_at=? WHERE id=? AND revoked_at IS NULL", (_ts(), tid))
        audit("service_token_revoked", target=tid, level="warn")
        return jsonify({"message": "Revoked."}), 200

    # ================================================================== SSO (OIDC)
    def sso_cfg():
        return ctx.get_setting("m07.sso", {}) or {}

    def sso_public():
        c = sso_cfg()
        return {"enabled": bool(c.get("enabled") and c.get("issuer") and c.get("client_id")), "label": c.get("label") or "Single sign-on",
                "issuer": c.get("issuer", ""), "client_id": c.get("client_id", ""), "redirect_uri": c.get("redirect_uri", ""),
                "scopes": c.get("scopes", "openid email profile"), "groups_claim": c.get("groups_claim", "groups"),
                "role_map": c.get("role_map", {}), "default_role": c.get("default_role", "viewer"),
                "auto_provision": bool(c.get("auto_provision", True)), "secret_present": bool(oidc.client_secret())}

    @app.route(f"{API}/sso/public")
    def sso_info():
        p = sso_public()
        return jsonify({"enabled": p["enabled"], "label": p["label"]}), 200

    @app.route(f"{API}/sso", methods=["PUT"])
    @admin
    def sso_put():
        d = body()
        issuer = str(d.get("issuer", "")).strip().rstrip("/")
        if issuer and not (issuer.startswith("https://") or issuer.startswith("http://localhost") or issuer.startswith("http://127.0.0.1")):
            return err("Issuer must be an https URL.")
        rmap = d.get("role_map") or {}
        if not isinstance(rmap, dict) or any(v not in RANK for v in rmap.values()):
            return err("Role map: group name -> portal role.")
        if d.get("default_role", "viewer") not in RANK or d.get("default_role") == "admin":
            return err("Default role cannot be admin; map an IdP group to admin instead.")
        new = {"enabled": bool(d.get("enabled")), "label": str(d.get("label", "Single sign-on"))[:40], "issuer": issuer,
               "client_id": str(d.get("client_id", "")).strip()[:200], "redirect_uri": str(d.get("redirect_uri", "")).strip()[:300],
               "scopes": str(d.get("scopes") or "openid email profile")[:200], "groups_claim": str(d.get("groups_claim") or "groups")[:60],
               "role_map": {str(k)[:120]: v for k, v in rmap.items()}, "default_role": d.get("default_role", "viewer"),
               "auto_provision": bool(d.get("auto_provision", True))}
        if new["enabled"]:
            try:
                oidc.discovery(issuer)
            except oidc.OIDCError as e:
                return err(str(e))
        ctx.set_setting("m07.sso", new)
        audit("sso_configured", details=f"{issuer} enabled={new['enabled']}")
        return jsonify({"sso": sso_public()}), 200

    @app.route(f"{API}/sso/start")
    def sso_start():
        c = sso_cfg()
        if not sso_public()["enabled"]:
            return redirect("/login.html#sso_error=" + "Single sign-on is not configured.")
        try:
            url, saved = oidc.start(c)
        except oidc.OIDCError as e:
            return redirect("/login.html#sso_error=" + str(e)[:200])
        x("INSERT INTO m07_sso_state (state,data,created_at) VALUES (?,?,?)", (saved["state"], json.dumps(saved), time.time()))
        return redirect(url)

    @app.route(f"{API}/sso/callback")
    def sso_callback():
        from urllib.parse import quote
        c = sso_cfg()
        state = request.args.get("state", "")
        row = q("SELECT * FROM m07_sso_state WHERE state=?", (state,), one=True)
        x("DELETE FROM m07_sso_state WHERE state=?", (state,))
        if request.args.get("error"):
            return redirect("/login.html#sso_error=" + quote(request.args.get("error_description") or request.args["error"])[:300])
        if not row or time.time() - row["created_at"] > 600:
            return redirect("/login.html#sso_error=" + quote("Sign-in expired. Try again."))
        try:
            claims = oidc.finish(c, request.args.get("code", ""), json.loads(row["data"]))
        except oidc.OIDCError as e:
            store.add_audit(None, "sso", "sso_login_failed", details=str(e)[:200], level="warn")
            return redirect("/login.html#sso_error=" + quote(str(e)[:200]))
        sub, email = str(claims["sub"]), str(claims.get("email") or "").lower()
        uname = re.sub(r"[^a-z0-9._-]+", ".", (claims.get("preferred_username") or email.split("@")[0] or sub).lower())[:60]
        groups = claims.get(c.get("groups_claim") or "groups") or []
        groups = groups if isinstance(groups, list) else [groups]
        mapped = [c.get("role_map", {}).get(g) for g in groups if c.get("role_map", {}).get(g)]
        role_ = max(mapped, key=lambda r: RANK[r]) if mapped else c.get("default_role", "viewer")
        link = q("SELECT * FROM m07_identities WHERE provider=? AND subject=?", (c["issuer"], sub), one=True)
        user = store.get_user(link["user_id"]) if link else None
        if not user and email:
            with store._connect() as conn:
                r = conn.execute("SELECT id FROM users WHERE lower(email)=?", (email,)).fetchone()
            user = store.get_user(r["id"]) if r else None
        if not user:
            if not c.get("auto_provision", True):
                return redirect("/login.html#sso_error=" + quote("No portal account for this identity. Ask an administrator."))
            user, e = store.create_signup(uname if not q("SELECT 1 FROM users WHERE username=?", (uname,), one=True) else f"{uname}.{secrets.token_hex(2)}",
                                          email or f"{uname}@sso.invalid", secrets.token_urlsafe(24), role_)
            if e:
                return redirect("/login.html#sso_error=" + quote(e))
            store.set_user_status(user["id"], "approved", None)
            store.add_audit(user["id"], user["username"], "sso_user_provisioned", details=f"role {role_} from groups {groups[:5]}")
        elif mapped and user["role"] != role_ and user["role"] != "admin":
            store.set_user_role(user["id"], role_)  # IdP groups are the source of truth for mapped roles
        user = store.get_user(user["id"])
        if user["status"] != "approved":
            return redirect("/login.html#sso_error=" + quote("Your portal account is not active."))
        x("INSERT INTO m07_identities (provider,subject,user_id,email,last_login) VALUES (?,?,?,?,?) ON CONFLICT(provider,subject) DO UPDATE SET last_login=excluded.last_login",
          (c["issuer"], sub, user["id"], email, _ts()))
        token = ctx.issue_token(user, "sso")
        store.add_audit(user["id"], user["username"], "login", details=f"SSO {c['issuer']}")
        return redirect("/login.html#sso_token=" + token)

    # ================================================================== SCIM 2.0 provisioning
    SCIM = "/scim/v2"
    SCIM_USER = "urn:ietf:params:scim:schemas:core:2.0:User"

    def scim_auth():
        h = request.headers.get("Authorization", "")
        want = ctx.get_setting("m07.scim_token_hash")
        return bool(want and h.startswith("Bearer ") and secrets.compare_digest(cr.hash_token(h[7:]), want))

    def scim_err(detail, status):
        return jsonify({"schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"], "detail": detail, "status": str(status)}), status

    def scim_user(u):
        return {"schemas": [SCIM_USER], "id": str(u["id"]), "userName": u["email"] or u["username"], "active": u["status"] == "approved",
                "displayName": u["username"], "emails": [{"value": u["email"], "primary": True}],
                "meta": {"resourceType": "User", "created": str(u.get("created_at", "")).replace(" ", "T") + "Z", "location": f"{SCIM}/Users/{u['id']}"},
                "urn:fde:nexus:portal": {"role": u["role"]}}

    @app.route(f"{API}/scim/token", methods=["POST"])
    @admin
    def scim_token():
        raw = "scim_" + secrets.token_urlsafe(32)
        ctx.set_setting("m07.scim_token_hash", cr.hash_token(raw))
        audit("scim_token_rotated", level="warn")
        return jsonify({"token": raw, "base_url": request.host_url.rstrip("/") + SCIM, "note": "Shown once. Paste it into your IdP's SCIM app."}), 201

    @app.route(f"{SCIM}/ServiceProviderConfig")
    def scim_spc():
        return jsonify({"schemas": ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"], "patch": {"supported": True},
                        "bulk": {"supported": False}, "filter": {"supported": True, "maxResults": 200}, "changePassword": {"supported": False},
                        "sort": {"supported": False}, "etag": {"supported": False},
                        "authenticationSchemes": [{"type": "oauthbearertoken", "name": "Bearer token"}]}), 200

    @app.route(f"{SCIM}/Users", methods=["GET", "POST"])
    def scim_users():
        if not scim_auth():
            return scim_err("Unauthorized", 401)
        if request.method == "GET":
            users = store.list_users()
            f = request.args.get("filter", "")
            m = re.fullmatch(r'\s*userName\s+eq\s+"([^"]+)"\s*', f)
            if m:
                users = [u for u in users if m.group(1).lower() in ((u["email"] or "").lower(), u["username"].lower())]
            start, count = max(1, int(request.args.get("startIndex", 1))), min(200, int(request.args.get("count", 100)))
            page = users[start - 1:start - 1 + count]
            return jsonify({"schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"], "totalResults": len(users),
                            "startIndex": start, "itemsPerPage": len(page), "Resources": [scim_user(u) for u in page]}), 200
        d = request.get_json(silent=True) or {}
        email = str(d.get("userName") or next((e.get("value") for e in d.get("emails", []) if e.get("primary")), "")).lower()
        if "@" not in email:
            return scim_err("userName must be an email address.", 400)
        if q("SELECT 1 FROM users WHERE lower(email)=?", (email,), one=True):
            return scim_err("User already exists.", 409)
        uname = re.sub(r"[^a-z0-9._-]+", ".", email.split("@")[0])[:60]
        if q("SELECT 1 FROM users WHERE username=?", (uname,), one=True):
            uname = f"{uname}.{secrets.token_hex(2)}"
        role_ = (d.get("urn:fde:nexus:portal") or {}).get("role") or sso_public()["default_role"]
        role_ = role_ if role_ in RANK and role_ != "admin" else "viewer"
        user, e = store.create_signup(uname, email, secrets.token_urlsafe(24), role_)
        if e:
            return scim_err(e, 400)
        if d.get("active", True):
            store.set_user_status(user["id"], "approved", None)
        store.add_audit(None, "scim", "scim_user_created", target=uname, details=f"role {role_}")
        return jsonify(scim_user(store.get_user(user["id"]))), 201

    @app.route(f"{SCIM}/Users/<int:uid>", methods=["GET", "PUT", "PATCH", "DELETE"])
    def scim_user_one(uid):
        if not scim_auth():
            return scim_err("Unauthorized", 401)
        u = store.get_user(uid)
        if not u:
            return scim_err("Not found", 404)
        if request.method == "GET":
            return jsonify(scim_user(u)), 200
        if u["role"] == "admin":
            return scim_err("Administrator accounts are not managed through SCIM.", 403)
        active = None
        if request.method == "DELETE":
            active = False
        else:
            d = request.get_json(silent=True) or {}
            if request.method == "PUT":
                active = d.get("active")
            for op in d.get("Operations", []):
                if str(op.get("op", "")).lower() == "replace":
                    v = op.get("value")
                    if op.get("path") == "active":
                        active = v in (True, "true", "True")
                    elif isinstance(v, dict) and "active" in v:
                        active = v["active"] in (True, "true", "True")
        if active is not None:
            store.set_user_status(uid, "approved" if active else "disabled", None)
            if not active:
                x("UPDATE m07_sessions SET revoked_at=?, revoked_by='scim' WHERE user_id=? AND revoked_at IS NULL", (_ts(), uid))
            store.add_audit(None, "scim", "scim_user_activated" if active else "scim_user_deactivated", target=u["username"], level="info" if active else "warn")
        if request.method == "DELETE":
            return ("", 204)
        return jsonify(scim_user(store.get_user(uid))), 200

    # ================================================================== IAM role management + workload identity (AWS)
    def cache():
        c = ctx.services.get("aws_cache")
        if not c:
            raise RuntimeError("The AWS cache (M02) is not loaded.")
        return c

    @app.route(f"{API}/iam/roles")
    @auth
    def iam_roles():
        acct = request.args.get("account", "")
        if not store.get_aws_account(acct):
            return err("Pick a connected AWS account.")
        rows, off = [], 0
        while True:
            page = cache().resources(acct, service="iam_role", limit=1000, offset=off)["items"]
            rows += page
            off += len(page)
            if len(page) < 1000:
                break
        now = _now_dt()
        out = []
        for r in rows:
            det = (cache().resource(acct, r["region"], "iam_role", r["resource_id"]) or {}).get("detail", {})
            trust = det.get("AssumeRolePolicyDocument") or {}
            if isinstance(trust, str):
                from urllib.parse import unquote
                try:
                    trust = json.loads(unquote(trust))
                except ValueError:
                    trust = {}
            principals, flags = [], []
            for st in trust.get("Statement", []) if isinstance(trust, dict) else []:
                p = st.get("Principal", {})
                if p == "*" or (isinstance(p, dict) and p.get("AWS") in ("*", ["*"])):
                    flags.append("trusts anyone")
                foreign = False
                for kind, val in (p.items() if isinstance(p, dict) else []):
                    for v in (val if isinstance(val, list) else [val]):
                        principals.append(f"{kind}:{v}")
                        m = re.search(r"arn:aws:iam::(\d{12}):", str(v)) or re.fullmatch(r"(\d{12})", str(v))
                        if kind == "AWS" and m and m.group(1) != acct:
                            flags.append(f"cross-account {m.group(1)}")
                            foreign = True
                if foreign and "sts:ExternalId" not in json.dumps(st.get("Condition") or {}):
                    flags.append("cross-account without external ID")
            last = r["summary"].get("last_used")
            days = (now - datetime.fromisoformat(str(last).replace("Z", "+00:00"))).days if last else None
            if r["summary"].get("path", "").startswith("/aws-service-role/"):
                kind_ = "service-linked"
            elif any(p.startswith("Federated:") for p in principals):
                kind_ = "federated"
            elif any(p.startswith("Service:") for p in principals):
                kind_ = "service"
            else:
                kind_ = "assumable"
            if days is None and kind_ != "service-linked" and r["summary"].get("last_used_checked"):
                flags.append("never used")
            elif days is not None and days > 90 and kind_ != "service-linked":
                flags.append(f"unused {days} days")
            out.append({"name": r["name"], "arn": r["resource_id"], "kind": kind_, "path": r["summary"].get("path"), "created": r["summary"].get("created"),
                        "last_used": last, "days_unused": days, "principals": principals[:6], "flags": sorted(set(flags)),
                        "description": r["summary"].get("description")})
        out.sort(key=lambda r: (-len(r["flags"]), r["name"].lower()))
        return jsonify({"roles": out, "cached": len(rows), "note": "From the account data cache. Sync IAM roles there to refresh."}), 200

    @app.route(f"{API}/iam/roles/<name>")
    @auth
    def iam_role_detail(name):
        acct = store.get_aws_account(request.args.get("account", ""))
        if not acct:
            return err("Pick a connected AWS account.")
        if not re.fullmatch(r"[\w+=,.@-]{1,64}", name):
            return err("Invalid role name.")
        if not cfg.LIVE_READS:
            return err("Live reads are off.")
        try:
            import ec2 as m01_ec2
            iam = m01_ec2._session(acct).client("iam")
            attached = [p for pg in iam.get_paginator("list_attached_role_policies").paginate(RoleName=name) for p in pg["AttachedPolicies"]]
            inline = [n for pg in iam.get_paginator("list_role_policies").paginate(RoleName=name) for n in pg["PolicyNames"]]
        except Exception as e:
            return err(f"IAM read failed: {str(e)[:200]}", 502)
        risky = [p["PolicyName"] for p in attached if p["PolicyName"] in ("AdministratorAccess", "PowerUserAccess", "IAMFullAccess") or p["PolicyArn"].endswith(":policy/AdministratorAccess")]
        return jsonify({"attached": attached, "inline": inline, "privileged": risky}), 200

    @app.route(f"{API}/workload")
    @auth
    def workload_identity():
        acct = store.get_aws_account(request.args.get("account", ""))
        if not acct:
            return err("Pick a connected AWS account.")
        if not cfg.LIVE_READS:
            return err("Live reads are off.")
        clusters = cache().resources(acct["id"], service="eks", limit=200)["items"]
        import ec2 as m01_ec2
        out = []

        def one(c):
            try:
                eks = m01_ec2._session(acct, c["region"]).client("eks", region_name=c["region"])
                d = eks.describe_cluster(name=c["name"])["cluster"]
                assoc = [a for pg in eks.get_paginator("list_pod_identity_associations").paginate(clusterName=c["name"]) for a in pg["associations"]]
                details = []
                for a in assoc[:100]:
                    try:
                        det = eks.describe_pod_identity_association(clusterName=c["name"], associationId=a["associationId"])["association"]
                        details.append({"namespace": a["namespace"], "service_account": a["serviceAccount"], "role": det.get("roleArn", "").split("/")[-1]})
                    except Exception:
                        details.append({"namespace": a["namespace"], "service_account": a["serviceAccount"], "role": "?"})
                return {"cluster": c["name"], "region": c["region"], "oidc_issuer": ((d.get("identity") or {}).get("oidc") or {}).get("issuer"),
                        "pod_identity": details, "access_mode": (d.get("accessConfig") or {}).get("authenticationMode")}
            except Exception as e:
                return {"cluster": c["name"], "region": c["region"], "error": str(e)[:200]}
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(6) as pool:
            out = list(pool.map(one, clusters))
        irsa_roles = []
        for r in cache().resources(acct["id"], service="iam_role", q="oidc.eks", limit=500)["items"]:
            irsa_roles.append(r["name"])
        return jsonify({"clusters": out, "irsa_roles": irsa_roles}), 200
