"""REST API for the M01 Self-Service Portal.

All routes are registered on the Flask app passed to register_routes().
Auth is JWT bearer tokens. Every meaningful action writes an audit entry.
Infrastructure actions are simulated in DEMO_MODE.
"""
from __future__ import annotations

import json
import secrets
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Response, jsonify, request

import config
import ec2
import middleware
import store
import validators


# ----------------------------------------------------------------- identity hooks (M07 plugs in here)
# on_login(user, body)        -> None to continue, or a Flask response (e.g. an MFA challenge)
# on_token(user, payload)     -> called for every issued token (session tracking)
# resolve_token(raw)          -> user dict for non-JWT credentials (service tokens), else None
# on_auth(user, payload)      -> user (possibly with an elevated temporary role) or (error, http_code)
IDENTITY = {"on_login": [], "on_token": [], "resolve_token": [], "on_auth": []}


# ----------------------------------------------------------------- tokens
def _create_token(user: dict, method: str = "password") -> str:
    payload = {
        "sub": str(user["id"]),
        "username": user["username"],
        "role": user["role"],
        "jti": secrets.token_urlsafe(16),
        "amr": method,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=config.JWT_EXPIRY_HOURS),
    }
    for hook in IDENTITY["on_token"]:
        hook(user, payload)
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def _decode_token(token: str):
    try:
        return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "Authentication required"}), 401
        raw = header[7:]
        for hook in IDENTITY["resolve_token"]:
            svc = hook(raw)
            if svc:
                if isinstance(svc, tuple):
                    return jsonify({"error": svc[0]}), svc[1]
                request.current_user = svc
                return fn(*args, **kwargs)
        payload = _decode_token(raw)
        if not payload:
            return jsonify({"error": "Invalid or expired token"}), 401
        user = store.get_user(int(payload["sub"]))
        if not user:
            return jsonify({"error": "User not found"}), 401
        if user.get("status") != "approved":
            return jsonify({"error": "Account is not active"}), 403
        for hook in IDENTITY["on_auth"]:
            res = hook(user, payload)
            if isinstance(res, tuple):
                return jsonify({"error": res[0]}), res[1]
            user = res or user
        request.current_user = user
        request.token_payload = payload
        return fn(*args, **kwargs)
    return wrapper


def role_required(*roles):
    def deco(fn):
        @wraps(fn)
        @auth_required
        def wrapper(*args, **kwargs):
            if request.current_user.get("role") not in roles and request.current_user.get("role") != "admin":
                return jsonify({"error": "Insufficient permissions"}), 403
            return fn(*args, **kwargs)
        return wrapper
    return deco


def admin_required(fn):
    return role_required("admin")(fn)


# approver-capable roles (and admin, handled in role_required)
APPROVER_ROLES = ("approver", "operator", "security")


# ----------------------------------------------------------------- routes
def register_routes(app):
    store.init_db()
    ec2.init()

    # --- health ---
    @app.route("/api/health")
    def health():
        return jsonify({"status": "healthy", "demo": config.DEMO_MODE, "live_reads": config.LIVE_READS,
                        "region": config.AWS_REGION}), 200

    # ================= Auth =================
    @app.route("/api/auth/signup", methods=["POST"])
    def signup():
        d = request.json or {}
        if d.get("password") != d.get("confirmPassword", d.get("password")):
            return jsonify({"error": "Passwords do not match"}), 400
        user, err = store.create_signup(d.get("username"), d.get("email"), d.get("password"))
        if err:
            return jsonify({"error": err}), 400
        store.add_audit(user["id"], user["username"], "signup_request", target=user["email"])
        store.add_notification(None, "info", "New signup pending",
                               f"{user['username']} requested access and needs approval.")
        return jsonify({"message": "Signup submitted. An administrator must approve your account.",
                        "user": user}), 201

    @app.route("/api/auth/login", methods=["POST"])
    def login():
        d = request.json or {}
        user, blocked = store.authenticate(d.get("username", ""), d.get("password", ""))
        if blocked == "invalid" or not user:
            store.add_audit(None, d.get("username"), "login_failed", level="warn")
            return jsonify({"error": "Invalid username or password"}), 401
        if blocked:  # pending / rejected / disabled
            msgs = {
                "pending": "Your account is pending administrator approval.",
                "rejected": "Your signup request was rejected. Contact an administrator.",
                "disabled": "Your account is disabled. Contact an administrator.",
            }
            return jsonify({"error": msgs.get(blocked, "Account not active"), "status": blocked}), 403
        for hook in IDENTITY["on_login"]:
            challenge = hook(user, d)
            if challenge is not None:
                return challenge
        token = _create_token(user)
        store.add_audit(user["id"], user["username"], "login")
        return jsonify({"token": token, "user": user}), 200

    @app.route("/api/auth/me")
    @auth_required
    def me():
        return jsonify({"user": request.current_user}), 200

    @app.route("/api/auth/password", methods=["POST"])
    @auth_required
    def change_my_password():
        d = request.json or {}
        u = request.current_user
        err = store.change_password(u["id"], d.get("current"), d.get("new"))
        if err:
            store.add_audit(u["id"], u["username"], "password_change_failed", level="warn")
            return jsonify({"error": err}), 400
        store.add_audit(u["id"], u["username"], "password_changed")
        return jsonify({"message": "Password updated"}), 200

    @app.route("/api/auth/logout", methods=["POST"])
    @auth_required
    def logout():
        u = request.current_user
        store.add_audit(u["id"], u["username"], "logout")
        return jsonify({"message": "Logged out"}), 200

    # ================= Users / admin =================
    @app.route("/api/users", methods=["GET"])
    @admin_required
    def users():
        return jsonify({"users": store.list_users(), "roles": sorted(config.ROLES, key=config.ROLES.get)}), 200

    @app.route("/api/users", methods=["POST"])
    @admin_required
    def create_user():
        d = request.json or {}
        role = d.get("role") or config.DEFAULT_ROLE
        if role not in config.ROLES:
            return jsonify({"error": "Unknown role"}), 400
        user, err = store.create_signup(d.get("username"), d.get("email"), d.get("password"), role)
        if err:
            return jsonify({"error": err}), 400
        admin = request.current_user
        user = store.set_user_status(user["id"], "approved", admin["id"])
        store.add_audit(admin["id"], admin["username"], "user_created", target=user["username"], details=role)
        return jsonify({"user": user}), 201

    @app.route("/api/users/<int:user_id>/<state>", methods=["POST"])
    @admin_required
    def toggle_user(user_id, state):
        if state not in ("disable", "enable"):
            return jsonify({"error": "Not found"}), 404
        admin = request.current_user
        if user_id == admin["id"]:
            return jsonify({"error": "You cannot disable your own account."}), 400
        user = store.set_user_status(user_id, "disabled" if state == "disable" else "approved", admin["id"])
        if not user:
            return jsonify({"error": "Not found"}), 404
        store.add_audit(admin["id"], admin["username"], f"user_{state}d", target=user["username"], level="warn")
        return jsonify({"user": user}), 200

    @app.route("/api/users/pending")
    @admin_required
    def pending_users():
        return jsonify({"users": store.list_pending_users()}), 200

    @app.route("/api/users/<int:user_id>/approve", methods=["POST"])
    @admin_required
    def approve_user(user_id):
        admin = request.current_user
        user = store.set_user_status(user_id, "approved", admin["id"])
        store.add_audit(admin["id"], admin["username"], "user_approved", target=user["username"])
        store.add_notification(user_id, "success", "Account approved",
                               "An administrator approved your account. You can now sign in.")
        return jsonify({"user": user}), 200

    @app.route("/api/users/<int:user_id>/reject", methods=["POST"])
    @admin_required
    def reject_user(user_id):
        admin = request.current_user
        user = store.set_user_status(user_id, "rejected", admin["id"])
        store.add_audit(admin["id"], admin["username"], "user_rejected", target=user["username"], level="warn")
        return jsonify({"user": user}), 200

    @app.route("/api/users/<int:user_id>/role", methods=["POST"])
    @admin_required
    def change_role(user_id):
        role = (request.json or {}).get("role", "")
        if role not in config.ROLES:
            return jsonify({"error": "Unknown role"}), 400
        if user_id == request.current_user["id"]:
            return jsonify({"error": "You cannot change your own role."}), 400
        user = store.set_user_role(user_id, role)
        store.add_audit(request.current_user["id"], request.current_user["username"],
                        "user_role_changed", target=f"{user['username']} -> {role}")
        return jsonify({"user": user}), 200

    # ================= Catalog =================
    @app.route("/api/catalog")
    @auth_required
    def catalog():
        return jsonify({"items": store.list_catalog()}), 200

    @app.route("/api/catalog/<item_id>")
    @auth_required
    def catalog_item(item_id):
        item = store.get_catalog_item(item_id)
        if not item:
            return jsonify({"error": "Not found"}), 404
        return jsonify({"item": item}), 200

    # ================= Requests =================
    @app.route("/api/requests", methods=["GET"])
    @auth_required
    def get_requests():
        status = request.args.get("status")
        return jsonify({"requests": store.list_requests(request.current_user, status)}), 200

    @app.route("/api/requests", methods=["POST"])
    @auth_required
    def create_request():
        d = request.json or {}
        if request.current_user["role"] == "viewer":
            return jsonify({"error": "Viewers have read-only access and cannot submit requests."}), 403
        item = store.get_catalog_item(d.get("itemId", ""))
        if not item:
            return jsonify({"error": "Unknown catalog item"}), 400
        cleaned, errors = validators.validate_inputs(item["input_schema"], d.get("inputs", {}))
        if errors:
            return jsonify({"error": "Validation failed", "details": errors}), 400
        if item["id"] == "ec2-instance":
            ec2_errors = ec2.validate(cleaned, store.get_aws_account(str(cleaned.get("account_id", ""))))
            if ec2_errors:
                return jsonify({"error": "Validation failed", "details": ec2_errors}), 400
        req = store.create_request(item, request.current_user, cleaned)
        u = request.current_user
        store.add_audit(u["id"], u["username"], "request_created", target=req["id"], details=item["name"])
        if req["status"] == "pending":
            store.add_notification(None, "info", "Approval needed",
                                   f"{u['username']} requested {item['name']} ({req['id']}).")
        else:
            store.add_notification(u["id"], "success", "Request auto-approved",
                                   f"{item['name']} ({req['id']}) was auto-approved and is deploying.")
            _start_deployment(req)
        return jsonify({"request": req}), 201

    @app.route("/api/requests/<request_id>")
    @auth_required
    def get_request(request_id):
        req = store.get_request(request_id)
        if not req:
            return jsonify({"error": "Not found"}), 404
        return jsonify({"request": req, "approvals": store.list_approvals(request_id)}), 200

    @app.route("/api/requests/<request_id>/manifest", methods=["GET"])
    @auth_required
    def request_manifest(request_id):
        req = store.get_request(request_id)
        if not req:
            return jsonify({"error": "Not found"}), 404
        item = store.get_catalog_item(req["item_id"])
        return jsonify({"manifest": middleware.generate_manifest(item, req["inputs"])}), 200

    @app.route("/api/requests/<request_id>/cancel", methods=["POST"])
    @auth_required
    def cancel_request(request_id):
        req = store.get_request(request_id)
        if not req:
            return jsonify({"error": "Not found"}), 404
        u = request.current_user
        if req["requester_id"] != u["id"] and u["role"] != "admin":
            return jsonify({"error": "Only the requester or an admin can cancel"}), 403
        if req["status"] not in ("pending", "approved"):
            return jsonify({"error": "Request cannot be cancelled in its current state"}), 400
        store.update_request_status(request_id, "cancelled")
        store.add_audit(u["id"], u["username"], "request_cancelled", target=request_id)
        return jsonify({"request": store.get_request(request_id)}), 200

    # ================= Approvals =================
    @app.route("/api/approvals")
    @role_required(*APPROVER_ROLES)
    def approvals():
        return jsonify({"requests": store.list_pending_approvals()}), 200

    @app.route("/api/requests/<request_id>/approve", methods=["POST"])
    @role_required(*APPROVER_ROLES)
    def approve_request(request_id):
        req = store.get_request(request_id)
        if not req:
            return jsonify({"error": "Not found"}), 404
        if req["status"] != "pending":
            return jsonify({"error": "Request is not pending"}), 400
        u = request.current_user
        # separation of duties: a requester cannot approve their own request
        if req["requester_id"] == u["id"]:
            return jsonify({"error": "You cannot approve your own request (separation of duties)."}), 403
        reason = (request.json or {}).get("reason", "")
        store.add_approval(request_id, u["id"], u["username"], "approved", reason)
        store.update_request_status(request_id, "approved")
        store.add_audit(u["id"], u["username"], "request_approved", target=request_id)
        store.add_notification(req["requester_id"], "success", "Request approved",
                               f"{req['item_name']} ({request_id}) was approved and is deploying.")
        req = store.get_request(request_id)
        _start_deployment(req)
        return jsonify({"request": req}), 200

    @app.route("/api/requests/<request_id>/reject", methods=["POST"])
    @role_required(*APPROVER_ROLES)
    def reject_request(request_id):
        req = store.get_request(request_id)
        if not req:
            return jsonify({"error": "Not found"}), 404
        if req["status"] != "pending":
            return jsonify({"error": "Request is not pending"}), 400
        u = request.current_user
        if req["requester_id"] == u["id"]:
            return jsonify({"error": "You cannot decide your own request (separation of duties)."}), 403
        reason = (request.json or {}).get("reason", "")
        store.add_approval(request_id, u["id"], u["username"], "rejected", reason)
        store.update_request_status(request_id, "rejected")
        store.add_audit(u["id"], u["username"], "request_rejected", target=request_id, level="warn")
        store.add_notification(req["requester_id"], "warning", "Request rejected",
                               f"{req['item_name']} ({request_id}) was rejected. {reason}".strip())
        return jsonify({"request": store.get_request(request_id)}), 200

    # ================= Plan (preview) =================
    @app.route("/api/requests/<request_id>/plan", methods=["GET"])
    @auth_required
    def plan_stream(request_id):
        req = store.get_request(request_id)
        if not req:
            return jsonify({"error": "Not found"}), 404
        item = store.get_catalog_item(req["item_id"])
        lines = middleware.plan_lines(item, req["inputs"])

        def generate():
            for line in lines:
                yield f"data: {json.dumps({'type': 'line', 'line': line})}\n\n"
                time.sleep(0.05)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return Response(generate(), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ================= Deployments =================
    @app.route("/api/deployments")
    @auth_required
    def deployments():
        return jsonify({"deployments": store.list_deployments()}), 200

    # ================= Resources / inventory =================
    @app.route("/api/resources")
    @auth_required
    def resources():
        return jsonify({"resources": store.list_resources(
            search=request.args.get("q"),
            env=request.args.get("env"),
            status=request.args.get("status"),
        )}), 200

    # ================= Operational health =================
    @app.route("/api/health-summary")
    @auth_required
    def health_summary():
        return jsonify({
            "resources": store.health_summary(),
            "requests": _request_counts(),
            "deployments_recent": store.list_deployments(limit=5),
        }), 200

    # ================= Dashboard overview =================
    @app.route("/api/overview")
    @auth_required
    def overview():
        u = request.current_user
        reqs = store.list_requests(u)
        return jsonify({
            "kpis": {
                "my_requests": len([r for r in reqs if r["requester_id"] == u["id"]]),
                "pending_approvals": len(store.list_pending_approvals()),
                "resources": store.health_summary()["total"],
                "catalog_items": len(store.list_catalog()),
            },
            "health": store.health_summary(),
            "recent_requests": reqs[:5],
            "recent_activity": store.list_audit(limit=8),
        }), 200

    # ================= Notifications =================
    @app.route("/api/notifications")
    @auth_required
    def notifications():
        unread = request.args.get("unread") == "1"
        return jsonify({"notifications": store.list_notifications(request.current_user["id"], unread)}), 200

    @app.route("/api/notifications/read", methods=["POST"])
    @auth_required
    def notifications_read():
        store.mark_notifications_read(request.current_user["id"])
        return jsonify({"message": "marked read"}), 200

    # ================= Global search =================
    @app.route("/api/search")
    @auth_required
    def search():
        return jsonify(store.global_search(request.args.get("q", ""), request.current_user)), 200

    # ================= AI assistant =================
    @app.route("/api/assistant", methods=["POST"])
    @auth_required
    def assistant():
        msg = (request.json or {}).get("message", "")
        u = request.current_user
        store.add_audit(u["id"], u["username"], "assistant_message", details=msg[:120])
        return jsonify({"reply": middleware.assistant_reply(msg)}), 200


    # ================= AWS accounts (persisted) =================
    @app.route("/api/aws-accounts", methods=["GET"])
    @auth_required
    def aws_accounts():
        accts = store.list_aws_accounts()
        active = store.get_pref(request.current_user["id"], "active_account")
        if not active or not any(a["id"] == active for a in accts):
            active = next((a["id"] for a in accts if a["status"] == "connected"), None)
        return jsonify({"accounts": accts, "active": active}), 200

    def _account_from_body(d):
        """Validate an account definition from the UI. Returns (account_dict, error)."""
        acct_id = str(d.get("id", "")).strip()
        method = d.get("method", "assume-role")
        role_arn = (d.get("role_arn") or "").strip()
        if not re.fullmatch(r"\d{12}", acct_id):
            return None, "Account ID must be 12 digits"
        if method not in ("assume-role", "instance-role", "profile"):
            return None, "Unknown connection method"
        profile = (d.get("profile") or "").strip()
        if method == "profile":
            if profile not in _aws_profiles():
                return None, f"Profile '{profile}' is not in the portal host's AWS config."
        if method == "assume-role" and not re.fullmatch(r"arn:aws[a-z-]*:iam::\d{12}:role/[\w+=,.@/-]+", role_arn):
            return None, "A valid IAM role ARN is required for AssumeRole"
        if method == "assume-role" and role_arn.split(":")[4] != acct_id:
            return None, "Role ARN account does not match the Account ID"
        region = d.get("region") or config.AWS_REGION
        if not re.fullmatch(r"[a-z]{2}(-[a-z]+)+-\d", str(region)):
            return None, "Invalid region"
        alias = (d.get("alias") or "").strip() or f"acct-{acct_id[:4]}"
        return {"id": acct_id, "alias": alias[:40], "name": (d.get("name") or alias)[:80], "method": method,
                "role_arn": role_arn if method == "assume-role" else "", "profile": profile if method == "profile" else "", "external_id": (d.get("external_id") or "").strip()[:100],
                "region": region, "env": d.get("env") or "non-production"}, None

    def _aws_profiles():
        try:
            import boto3
            return sorted(boto3.Session().available_profiles)
        except Exception:
            return []

    @app.route("/api/aws-accounts/profiles")
    @admin_required
    def aws_profiles():
        """Profile NAMES from the host's ~/.aws/config (no credentials are read or returned)."""
        return jsonify({"profiles": _aws_profiles()}), 200

    @app.route("/api/aws-accounts/suggestions")
    @admin_required
    def aws_account_suggestions():
        """For each failing account: host profiles that belong to it (names only)."""
        out = {}
        for acc in store.list_aws_accounts():
            if acc["status"] != "connected" and acc["method"] != "profile":
                found = middleware.profiles_for_account(acc["id"])
                if found:
                    out[acc["id"]] = found
        return jsonify({"suggestions": out}), 200

    @app.route("/api/aws-accounts/<acct_id>", methods=["PUT"])
    @admin_required
    def aws_account_update(acct_id):
        if not store.get_aws_account(acct_id):
            return jsonify({"error": "Not found"}), 404
        body = dict(request.get_json(silent=True) or {}, id=acct_id)
        acct, err = _account_from_body(body)
        if err:
            return jsonify({"error": err}), 400
        store.update_aws_account(acct_id, acct)
        status, note = middleware.test_aws_account(store.get_aws_account(acct_id))
        store.set_aws_account_status(acct_id, status, note)
        u = request.current_user
        store.add_audit(u["id"], u["username"], "aws_account_updated", target=acct_id, details=f"{acct['method']} -> {status}")
        return jsonify({"account": store.get_aws_account(acct_id)}), 200

    @app.route("/api/aws-accounts/test-config", methods=["POST"])
    @admin_required
    def aws_account_test_config():
        """Test a connection before saving it. Nothing is stored."""
        acct, err = _account_from_body(request.get_json(silent=True) or {})
        if err:
            return jsonify({"error": err}), 400
        status, note = middleware.test_aws_account(acct)
        u = request.current_user
        store.add_audit(u["id"], u["username"], "aws_account_tested", target=acct["id"], details=f"unsaved: {status}")
        return jsonify({"status": status, "note": note, "simulated": config.DEMO_MODE,
                        "suggested_profiles": middleware.profiles_for_account(acct["id"]) if status == "failed" else []}), 200

    @app.route("/api/aws-accounts/test-all", methods=["POST"])
    @auth_required
    def aws_account_test_all():
        out = []
        for a in store.list_aws_accounts():
            status, note = middleware.test_aws_account(a)
            store.set_aws_account_status(a["id"], status, note)
            out.append({"id": a["id"], "alias": a["alias"], "status": status, "note": note})
        u = request.current_user
        store.add_audit(u["id"], u["username"], "aws_accounts_tested", details=", ".join(f"{o['id']}={o['status']}" for o in out)[:400])
        return jsonify({"results": out, "simulated": config.DEMO_MODE}), 200

    @app.route("/api/aws-accounts", methods=["POST"])
    @admin_required
    def aws_account_add():
        acct, err = _account_from_body(request.get_json(silent=True) or {})
        if err:
            return jsonify({"error": err}), 400
        acct_id = acct["id"]
        acct, err = store.add_aws_account(acct, request.current_user["username"])
        if err:
            return jsonify({"error": err}), 409
        status, note = middleware.test_aws_account(acct)
        store.set_aws_account_status(acct_id, status, note)
        u = request.current_user
        store.add_audit(u["id"], u["username"], "aws_account_added", target=acct_id, details=acct["method"])
        return jsonify({"account": store.get_aws_account(acct_id)}), 201

    @app.route("/api/aws-accounts/<acct_id>/test", methods=["POST"])
    @auth_required
    def aws_account_test(acct_id):
        acct = store.get_aws_account(acct_id)
        if not acct:
            return jsonify({"error": "Not found"}), 404
        status, note = middleware.test_aws_account(acct)
        store.set_aws_account_status(acct_id, status, note)
        u = request.current_user
        store.add_audit(u["id"], u["username"], "aws_account_tested", target=acct_id, details=status)
        return jsonify({"account": store.get_aws_account(acct_id), "simulated": config.DEMO_MODE,
                        "suggested_profiles": middleware.profiles_for_account(acct_id) if status == "failed" else []}), 200

    @app.route("/api/aws-accounts/<acct_id>/active", methods=["POST"])
    @auth_required
    def aws_account_activate(acct_id):
        acct = store.get_aws_account(acct_id)
        if not acct:
            return jsonify({"error": "Not found"}), 404
        if acct["status"] != "connected":
            return jsonify({"error": "Only connected accounts can be made active. Run a connection test first."}), 400
        store.set_pref(request.current_user["id"], "active_account", acct_id)
        return jsonify({"active": acct_id}), 200

    @app.route("/api/aws-accounts/<acct_id>", methods=["DELETE"])
    @admin_required
    def aws_account_delete(acct_id):
        if not store.get_aws_account(acct_id):
            return jsonify({"error": "Not found"}), 404
        store.delete_aws_account(acct_id)
        u = request.current_user
        store.add_audit(u["id"], u["username"], "aws_account_removed", target=acct_id, level="warn")
        return jsonify({"message": "Removed"}), 200

    # ================= Module configuration (admin) =================
    @app.route("/api/config", methods=["GET"])
    @admin_required
    def get_config():
        return jsonify({
            "runtime": {"demo_mode": config.DEMO_MODE, "live_reads": config.LIVE_READS, "region": config.AWS_REGION,
                        "region_source": config.AWS_REGION_SOURCE,
                        "jwt_expiry_hours": config.JWT_EXPIRY_HOURS,
                        "env": {"M01_DEMO": "1" if config.DEMO_MODE else "0", "M01_LIVE_READS": "1" if config.LIVE_READS else "0",
                                "AWS_PROFILE": os.environ.get("AWS_PROFILE", ""), "AWS_REGION": config.AWS_REGION,
                                "JWT_EXPIRY_HOURS": str(config.JWT_EXPIRY_HOURS)}},
            "catalog": store.list_catalog(enabled_only=False),
        }), 200

    @app.route("/api/catalog/<item_id>", methods=["PUT"])
    @admin_required
    def update_catalog(item_id):
        item = store.get_catalog_item(item_id)
        if not item:
            return jsonify({"error": "Not found"}), 404
        d = request.json or {}
        updated = store.update_catalog_item(item_id, bool(d.get("approval_required", item["approval_required"])),
                                            bool(d.get("enabled", item.get("enabled", 1))))
        u = request.current_user
        store.add_audit(u["id"], u["username"], "catalog_updated", target=item_id,
                        details=f"approval_required={updated['approval_required']} enabled={updated.get('enabled')}")
        return jsonify({"item": updated}), 200

    # ================= EC2 launch and lifecycle =================
    def _account_from_query():
        acct_id = request.args.get("account") or store.get_pref(request.current_user["id"], "active_account")
        acct = store.get_aws_account(acct_id) if acct_id else None
        return acct

    @app.route("/api/ec2/catalog")
    @auth_required
    def ec2_catalog():
        return jsonify(ec2.catalog()), 200

    @app.route("/api/ec2/options")
    @auth_required
    def ec2_options():
        acct = _account_from_query()
        if not acct:
            return jsonify({"error": "No AWS account selected"}), 400
        try:
            return jsonify(ec2.options(acct)), 200
        except Exception as e:  # boto errors: report, keep the form usable
            return jsonify({"simulated": False, "keyPairs": [], "subnets": [], "securityGroups": [],
                            "message": f"Could not read network options: {str(e)[:160]}"}), 200

    @app.route("/api/ec2/instances")
    @auth_required
    def ec2_instances():
        acct = _account_from_query()
        if not acct:
            return jsonify({"instances": [], "simulated": config.DEMO_MODE, "message": "No AWS account selected"}), 200
        try:
            return jsonify({"instances": ec2.list_instances(acct), "simulated": config.DEMO_MODE,
                            "live": config.LIVE_READS}), 200
        except Exception as e:
            return jsonify({"error": f"Could not list instances: {str(e)[:160]}"}), 502

    @app.route("/api/ec2/instances/<iid>/<action>", methods=["POST"])
    @auth_required
    def ec2_action(iid, action):
        acct = _account_from_query()
        if not acct:
            return jsonify({"error": "No AWS account selected"}), 400
        u = request.current_user
        if action == "terminate" and u["role"] not in ("admin", "operator"):
            return jsonify({"error": "Only an admin or operator can terminate instances."}), 403
        if u["role"] == "viewer":
            return jsonify({"error": "Viewers cannot change instances."}), 403
        try:
            state = ec2.act(acct, iid, action)
        except LookupError as e:
            return jsonify({"error": str(e)}), 404
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": f"AWS error: {str(e)[:160]}"}), 502
        store.add_audit(u["id"], u["username"], f"ec2_{action}", target=iid, details=acct["id"],
                        level="warn" if action == "terminate" else "info")
        return jsonify({"instanceId": iid, "state": state}), 200

    # ================= Audit =================
    @app.route("/api/audit")
    @auth_required
    def audit():
        u = request.current_user
        limit = request.args.get("limit", 200, type=int)
        logs = store.list_audit(limit) if u["role"] == "admin" else store.list_audit(limit, u["id"])
        return jsonify({"logs": logs}), 200


# ----------------------------------------------------------------- helpers
def _request_counts() -> dict:
    counts = {"pending": 0, "approved": 0, "rejected": 0, "deployed": 0, "deploying": 0, "failed": 0, "cancelled": 0}
    for r in store.list_requests(None):
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def _start_deployment(req: dict):
    """Simulate a deployment on a background thread, then register inventory."""
    item = store.get_catalog_item(req["item_id"])
    store.update_request_status(req["id"], "deploying")
    dep_id = store.create_deployment(req)

    def run_ec2():
        inputs = dict(req["inputs"], request_id=req["id"], owner=req["requester"])
        try:
            acct = store.get_aws_account(str(inputs.get("account_id", "")))
            if not acct:
                raise RuntimeError("AWS account is no longer registered")
            iid = ec2.launch(acct, inputs)
        except Exception as e:
            store.finish_deployment(dep_id, "failed", f"EC2 launch failed: {e}")
            store.update_request_status(req["id"], "failed")
            store.add_audit(req["requester_id"], req["requester"], "deployment_failed", target=req["id"], level="warn")
            store.add_notification(req["requester_id"], "danger", "Launch failed", f"{req['id']}: {str(e)[:200]}")
            return
        mode = "simulated" if config.DEMO_MODE else "live"
        store.finish_deployment(dep_id, "succeeded",
                                f"EC2 instance {iid} launched in account {acct['id']} ({inputs['instance_type']}, {mode}).")
        store.update_request_status(req["id"], "deployed")
        store.add_resource(inputs["instance_name"], "EC2 Instance", req["environment"], req.get("team"),
                           request_id=req["id"], status="healthy", tags={"instance_id": iid, "account": acct["id"]})
        store.add_audit(req["requester_id"], req["requester"], "ec2_launched", target=iid, details=req["id"])
        store.add_notification(req["requester_id"], "success", "Instance launched",
                               f"{inputs['instance_name']} ({iid}) is running ({mode}).")

    def run():
        lines = middleware.apply_lines(item, req["inputs"])
        time.sleep(1.2)  # simulate work
        store.finish_deployment(dep_id, "succeeded", "\n".join(lines))
        store.update_request_status(req["id"], "deployed")
        name = req["inputs"].get("name") or req["inputs"].get("team") or item["name"]
        store.add_resource(name, item["name"], req["environment"], req.get("team"),
                           request_id=req["id"], status="healthy")
        store.add_audit(req["requester_id"], req["requester"], "deployment_succeeded",
                        target=req["id"], details=item["name"])
        store.add_notification(req["requester_id"], "success", "Deployment complete",
                               f"{item['name']} ({req['id']}) deployed successfully.")

    threading.Thread(target=run_ec2 if item["id"] == "ec2-instance" else run, daemon=True).start()
