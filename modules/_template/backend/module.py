"""Template for an FDE Nexus module backend.

The core (modules/m01-self-service-portal/backend/core.py) imports this file and calls
register(app, ctx). Put routes under /api/<module id lower>/ and reuse ctx for auth,
the shared database, the audit log and other modules' services.

ctx.auth_required / ctx.admin_required / ctx.role_required(*roles)   decorators
ctx.store       shared SQLite helpers (_connect, _LOCK, add_audit, add_notification, ...)
ctx.config      runtime config (DEMO_MODE, AWS_REGION, ...)
ctx.services    cross-module services, e.g. ctx.services["iac"] (M03 change engine)
ctx.get_setting / ctx.set_setting   persisted platform settings

Rules: never call AWS to create or change infrastructure directly. Propose a change through
ctx.services["iac"].propose(...) so policy, cost, approval and GitLab review always apply.
Name helper files uniquely (e.g. m99_logic.py): all modules share one Python process.
"""
from flask import jsonify, request

API = "/api/m99"


def register(app, ctx):
    @app.route(f"{API}/status")
    @ctx.auth_required
    def m99_status():
        return jsonify({"module": "M99", "user": request.current_user["username"]}), 200
