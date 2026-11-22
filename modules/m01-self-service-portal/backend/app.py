"""M01 Self-Service Portal: Flask entry point.

Backend-only REST API under /api (the central FDE Nexus UI is the frontend).
Run:  python app.py   (or use ../run.sh)
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS

import api
import config
import core


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


def create_app() -> Flask:
    """M01 is a backend-only module. The central FDE Nexus frontend (at the repo
    root) is the single front door and calls this module's API."""
    _preflight()
    app = Flask(__name__, static_folder=None)
    CORS(app)
    api.register_routes(app)
    core.load_modules(app)

    @app.route("/")
    def root():
        return jsonify({
            "module": "M01 Platform Experience & Self-Service Portal",
            "api_base": "/api",
            "health": "/api/health",
            "note": "Backend API only. Use the central FDE Nexus portal as the frontend.",
        }), 200

    return app


app = create_app()

if __name__ == "__main__":
    print("=" * 64)
    print(" FDE Nexus · M01 Self-Service Portal")
    print(f"   URL:    http://localhost:{config.PORT}")
    print(f"   Demo:   {'ON (infrastructure actions are simulated)' if config.DEMO_MODE else 'OFF'}")
    print(f"   Admin:  {config.BOOTSTRAP_ADMIN_USER} (bootstrapped on first run from M01_ADMIN_PASSWORD)")
    print(f"   DB:     {config.DB_PATH}")
    print("=" * 64)
    app.run(host=config.HOST, port=config.PORT, debug=os.environ.get("M01_DEBUG") == "1")
