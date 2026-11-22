"""M03 Infrastructure as Code and Automation: HTTP routes. Logic lives in engine.py."""
from __future__ import annotations

import re

from flask import jsonify, request

import engine as engine_mod
import gitlab as gitlab_mod
import policy as policy_mod

API = "/api/m03"


def register(app, ctx):
    eng = engine_mod.Engine(ctx)
    ctx.services["iac"] = eng
    auth, admin, role = ctx.auth_required, ctx.admin_required, ctx.role_required
    approvers = ctx.approver_roles

    def fail(e: Exception):
        if isinstance(e, engine_mod.ChangeError):
            return jsonify({"error": str(e), "details": e.details}), e.status
        if isinstance(e, gitlab_mod.GitLabError):
            return jsonify({"error": str(e)}), 502
        raise e

    # ---------------- registry and policies
    @app.route(f"{API}/registry")
    @auth
    def registry():
        return jsonify({"components": list(eng.registry().values())}), 200

    @app.route(f"{API}/registry/<name>")
    @auth
    def registry_source(name):
        try:
            return jsonify({"component": eng.registry()[name], "files": eng.component_source(name)}), 200
        except (KeyError, engine_mod.ChangeError):
            return jsonify({"error": "Unknown component"}), 404

    @app.route(f"{API}/policies")
    @auth
    def policies():
        return jsonify({"rules": policy_mod.catalog()}), 200

    # ---------------- settings (GitLab, auto-approve)
    @app.route(f"{API}/settings")
    @auth
    def get_settings():
        return jsonify(eng.settings()), 200

    @app.route(f"{API}/settings", methods=["PUT"])
    @admin
    def put_settings():
        d = request.json or {}
        g = d.get("gitlab")
        if g is not None:
            url = str(g.get("url", "")).strip().rstrip("/")
            if url and not (url.startswith("https://") or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")):
                return jsonify({"error": "GitLab URL must use https."}), 400
            branch = str(g.get("target_branch", "main")).strip() or "main"
            if not re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", branch):
                return jsonify({"error": "Invalid branch name."}), 400
            prefix = str(g.get("path_prefix", "")).strip().strip("/")
            if prefix and (".." in prefix or not re.fullmatch(r"[A-Za-z0-9._/-]{1,200}", prefix)):
                return jsonify({"error": "Invalid path prefix."}), 400
            ctx.set_setting("m03.gitlab", {"url": url, "project": str(g.get("project", "")).strip()[:200],
                                           "target_branch": branch, "path_prefix": prefix})
        if "auto_approve_nonprod" in d:
            ctx.set_setting("m03.auto_approve_nonprod", bool(d["auto_approve_nonprod"]))
        if "state_bucket_pattern" in d:
            pat = str(d["state_bucket_pattern"])
            if "{account_id}" not in pat or not re.fullmatch(r"[a-z0-9.{}_-]{3,63}", pat):
                return jsonify({"error": "State bucket pattern must contain {account_id} and be a valid bucket name."}), 400
            ctx.set_setting("m03.state_bucket_pattern", pat)
        u = request.current_user
        ctx.store.add_audit(u["id"], u["username"], "m03_settings_updated", details=",".join(sorted(d)))
        return jsonify(eng.settings()), 200

    @app.route(f"{API}/gitlab/test", methods=["POST"])
    @admin
    def gitlab_test():
        try:
            gl = eng.gitlab_client()
            if not gl:
                return jsonify({"error": "Set the GitLab URL and project first."}), 400
            return jsonify({"project": gl.project_info()}), 200
        except gitlab_mod.GitLabError as e:
            return jsonify({"error": str(e)}), 502

    # ---------------- stacks
    @app.route(f"{API}/stacks")
    @auth
    def stacks():
        out = [{"env": s["env"], "meta": s["meta"], "version": s["version"], "updated_at": s["updated_at"],
                "components": len(s["components"])} for s in eng.list_stacks()]
        return jsonify({"stacks": out}), 200

    @app.route(f"{API}/stacks/<env>")
    @auth
    def stack(env):
        s = eng.get_stack(env)
        if not s:
            return jsonify({"error": "Unknown environment"}), 404
        return jsonify({"stack": s, "yaml": eng.render(env, s["meta"], s["components"]),
                        "path": eng.stack_path(s["meta"], env), "versions": eng.stack_versions(env)}), 200

    @app.route(f"{API}/stacks/<env>/rollback", methods=["POST"])
    @role("admin", "operator")
    def rollback(env):
        try:
            return jsonify({"change": eng.rollback(env, int((request.json or {}).get("version", -1)), request.current_user)}), 201
        except Exception as e:  # noqa: BLE001
            return fail(e)

    @app.route(f"{API}/drift", methods=["POST"])
    @role("admin", "operator", "security")
    def drift():
        d = request.json or {}
        try:
            return jsonify(eng.drift(str(d.get("env", "")), str(d.get("instance", "")), request.current_user)), 200
        except Exception as e:  # noqa: BLE001
            return fail(e)

    # ---------------- changes
    @app.route(f"{API}/changes")
    @auth
    def changes():
        return jsonify({"changes": eng.list_changes(request.args.get("env"), request.args.get("status"))}), 200

    @app.route(f"{API}/changes/<cid>")
    @auth
    def change(cid):
        ch = eng.get_change(cid)
        if not ch:
            return jsonify({"error": "Not found"}), 404
        return jsonify({"change": ch}), 200

    def _decide(cid, fn):
        try:
            return jsonify({"change": fn()}), 200
        except Exception as e:  # noqa: BLE001
            return fail(e)

    @app.route(f"{API}/changes/<cid>/approve", methods=["POST"])
    @role(*approvers)
    def approve(cid):
        return _decide(cid, lambda: eng.approve(cid, request.current_user, str((request.json or {}).get("reason", ""))[:500]))

    @app.route(f"{API}/changes/<cid>/reject", methods=["POST"])
    @role(*approvers)
    def reject(cid):
        return _decide(cid, lambda: eng.reject(cid, request.current_user, str((request.json or {}).get("reason", ""))[:500]))

    @app.route(f"{API}/changes/<cid>/cancel", methods=["POST"])
    @auth
    def cancel(cid):
        return _decide(cid, lambda: eng.cancel(cid, request.current_user))

    @app.route(f"{API}/changes/<cid>/refresh", methods=["POST"])
    @auth
    def refresh(cid):
        return _decide(cid, lambda: eng.refresh(cid))

    @app.route(f"{API}/changes/<cid>/merge", methods=["POST"])
    @role(*approvers)
    def merge(cid):
        return _decide(cid, lambda: eng.merge(cid, request.current_user))

    @app.route(f"{API}/changes/<cid>/<mode>", methods=["POST"])
    @role("admin", "operator")
    def run(cid, mode):
        if mode not in ("plan", "apply"):
            return jsonify({"error": "Not found"}), 404
        try:
            return jsonify(eng.run(cid, mode, request.current_user)), 200
        except Exception as e:  # noqa: BLE001
            return fail(e)
