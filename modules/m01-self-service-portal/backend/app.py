"""FDE Nexus portal: one process, one port.

Serves the central web UI (repo root: *.html, js/, css/, spec/) at /
and the REST API of every module under /api.
Run:  ./start-portal.sh   (or python app.py)
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import threading

from flask import Flask, abort, jsonify, make_response, redirect, request, send_from_directory

import api
import config
import core

UI_ROOT = Path(__file__).resolve().parents[3]          # FDENexus/
UI_DIRS = {"js", "css", "spec"}                         # only these folders are public
UI_EXT = {".html", ".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".gif", ".ico", ".webp", ".woff", ".woff2", ".json", ".map"}
SAFE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")


def _preflight() -> None:
    """Refuse to run with insecure defaults unless explicitly allowed (local)."""
    if config.ALLOW_INSECURE:
        return
    problems = []
    if "change-me" in config.JWT_SECRET or len(config.JWT_SECRET) < 32:
        problems.append("JWT_SECRET is the dev default or too short (set a strong 32+ char secret).")
    if config.BOOTSTRAP_ADMIN_PASSWORD == "admin":
        problems.append("M01_ADMIN_PASSWORD is still 'admin' (set a strong password).")
    if config.DEMO_MODE:
        problems.append("M01_DEMO is on (set M01_DEMO=0 for production once real backends are wired).")
    if problems:
        raise SystemExit("Refusing to start (M01_ALLOW_INSECURE=0):\n  - " + "\n  - ".join(problems))


def _register_ui(app: Flask) -> None:
    """Static UI on the same origin as the API. Only HTML at the repo root and files under
    js/, css/ and spec/ are served; modules/ (database, Terraform), .git and dotfiles never are."""

    @app.route("/")
    def ui_index():
        return redirect("/login.html")

    @app.route("/<path:path>")
    def ui_file(path):
        if path.startswith("api/") or not SAFE_PATH.match(path) or ".." in path or "/." in "/" + path:
            abort(404)
        p = Path(path)
        if p.suffix.lower() not in UI_EXT:
            abort(404)
        if len(p.parts) == 1:
            if p.suffix.lower() != ".html" or p.name.startswith("_"):
                abort(404)
        elif p.parts[0] not in UI_DIRS:
            abort(404)
        full = (UI_ROOT / p).resolve()
        if UI_ROOT not in full.parents or not full.is_file():
            abort(404)
        resp = send_from_directory(UI_ROOT, path, max_age=0)
        resp.headers["Cache-Control"] = "no-cache"  # always revalidate (cheap 304) so an upgrade is never hidden by a stale copy
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "same-origin"
        return resp

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({"error": "Not found"}), 404


COMPAT_PORT = int(os.environ.get("M01_COMPAT_PORT", "5001"))   # 0 disables


def _register_compat(app: Flask) -> None:
    """Older builds of the UI called the API on a separate port (5001). Browsers that still hold those
    files in their cache keep calling it. The same app answers there too, and every response tells the
    browser to drop its stale copies (Clear-Site-Data), so the next page load uses the current files."""
    if not COMPAT_PORT:
        return
    main = {f"http://localhost:{config.PORT}", f"http://127.0.0.1:{config.PORT}"}

    def is_compat():
        return request.host.rsplit(":", 1)[-1] == str(COMPAT_PORT)

    @app.before_request
    def compat_preflight():
        if is_compat() and request.method == "OPTIONS" and request.headers.get("Origin") in main:
            return make_response("", 204)

    @app.after_request
    def compat_headers(resp):
        origin = request.headers.get("Origin")
        if is_compat():
            if origin in main:
                resp.headers["Access-Control-Allow-Origin"] = origin
                resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
                resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
                resp.headers["Vary"] = "Origin"
            resp.headers["Clear-Site-Data"] = '"cache"'
        elif request.path in ("/login.html", "/api/health"):
            resp.headers["Clear-Site-Data"] = '"cache"'   # cheap: every UI file is no-cache anyway
        return resp


def _serve_compat(app: Flask) -> None:
    if not COMPAT_PORT or COMPAT_PORT == config.PORT:
        return
    from werkzeug.serving import make_server
    try:
        srv = make_server(config.HOST, COMPAT_PORT, app, threaded=True)
    except OSError as e:
        print(f"   Compat: port {COMPAT_PORT} not available ({e}); stale browser tabs must be refreshed.")
        return
    threading.Thread(target=srv.serve_forever, name="compat-port", daemon=True).start()
    print(f"   Compat: also answering on port {COMPAT_PORT} for browsers holding old cached files")


def create_app() -> Flask:
    _preflight()
    app = Flask(__name__, static_folder=None)
    origins = [o.strip() for o in os.environ.get("M01_CORS_ORIGINS", "").split(",") if o.strip()]
    if origins:  # only needed when the UI is hosted elsewhere
        from flask_cors import CORS
        CORS(app, origins=origins)
    api.register_routes(app)
    core.load_modules(app)
    _register_ui(app)
    _register_compat(app)
    return app


app = create_app()

if __name__ == "__main__":
    print("=" * 64)
    print(" FDE Nexus portal")
    print(f"   Open:   http://localhost:{config.PORT}/login.html   (UI and API on this one port)")
    print(f"   Mode:   {'changes simulated (M01_DEMO=1)' if config.DEMO_MODE else 'LIVE changes'}; "
          f"{'live reads from AWS' if config.LIVE_READS else 'offline'}")
    print(f"   Admin:  {config.BOOTSTRAP_ADMIN_USER} (bootstrapped on first run from M01_ADMIN_PASSWORD)")
    print(f"   DB:     {config.DB_PATH}")
    _serve_compat(app)
    print("=" * 64)
    app.run(host=config.HOST, port=config.PORT, debug=os.environ.get("M01_DEBUG") == "1", threaded=True)
