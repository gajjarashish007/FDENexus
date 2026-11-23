"""FDE Nexus platform core: discovers module folders and plugs them into one backend.

Every module lives in its own folder under FDENexus/modules/<slug>/ with:
  manifest.json      id, name, capabilities (+ status), UI entry, enabled flag
  backend/module.py  optional: def register(app, ctx) adds routes under /api/<id lower>/
Modules share one process, one database, one login (JWT), one audit log and one UI.
See modules/_template/ for the starting point of a new module.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

from flask import jsonify, request

import api
import config
import store

log = logging.getLogger("fde.core")

MODULES_DIR = Path(__file__).resolve().parents[2]          # FDENexus/modules
CAPABILITY_STATUSES = ("live", "partial", "planned")

_manifests: dict[str, dict] = {}
_loaded: dict[str, object] = {}
services: dict[str, object] = {}                             # cross-module services, e.g. services["iac"]


SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS platform_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def init_settings() -> None:
    with store._LOCK, store._connect() as conn:
        conn.executescript(SETTINGS_SCHEMA)
        conn.commit()


def get_setting(key: str, default=None):
    with store._connect() as conn:
        r = conn.execute("SELECT value FROM platform_settings WHERE key=?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_setting(key: str, value) -> None:
    with store._LOCK, store._connect() as conn:
        conn.execute("INSERT INTO platform_settings (key,value) VALUES (?,?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, json.dumps(value)))
        conn.commit()


def _read_manifest(path: Path) -> dict | None:
    try:
        m = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        log.error("Bad manifest %s: %s", path, e)
        return None
    for key in ("id", "name", "capabilities"):
        if key not in m:
            log.error("Manifest %s is missing %r", path, key)
            return None
    for c in m["capabilities"]:
        if c.get("status") not in CAPABILITY_STATUSES:
            c["status"] = "planned"
    m["slug"] = path.parent.name
    return m


def discover() -> list[dict]:
    found = []
    for mf in sorted(MODULES_DIR.glob("m*/manifest.json")):
        m = _read_manifest(mf)
        if m:
            found.append(m)
    return found


def module_enabled(m: dict) -> bool:
    override = get_setting(f"module.{m['id']}.enabled")
    return bool(m.get("enabled", True) if override is None else override)


def public_manifest(m: dict) -> dict:
    caps = m["capabilities"]
    counts = {s: sum(1 for c in caps if c["status"] == s) for s in CAPABILITY_STATUSES}
    if counts["live"] == len(caps):
        maturity = "live"
    elif counts["live"] or counts["partial"]:
        maturity = "partial"
    else:
        maturity = "planned"
    return {**{k: v for k, v in m.items() if not k.startswith("_")},
            "enabled": module_enabled(m), "counts": counts, "maturity": maturity,
            "loaded": m["id"] in _loaded}


class _ModuleApp:
    """Proxy given to modules: endpoint names are prefixed with the module id so two modules
    can both define e.g. `overview()` without clashing in Flask's global endpoint map."""

    def __init__(self, app, mid: str):
        self._app, self._prefix = app, mid.lower()

    def route(self, rule, **options):
        def deco(fn):
            options.setdefault("endpoint", f"{self._prefix}.{fn.__name__}")
            self._app.add_url_rule(rule, view_func=fn, **options)
            return fn
        return deco

    def __getattr__(self, name):
        return getattr(self._app, name)


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        auth_required=api.auth_required, admin_required=api.admin_required,
        role_required=api.role_required, approver_roles=api.APPROVER_ROLES,
        store=store, config=config, services=services, identity=api.IDENTITY, issue_token=api._create_token,
        get_setting=get_setting, set_setting=set_setting, modules_dir=MODULES_DIR,
    )


def load_modules(app) -> None:
    init_settings()
    ctx = _context()
    for m in discover():
        _manifests[m["id"]] = m
        entry = MODULES_DIR / m["slug"] / "backend" / "module.py"
        if not entry.exists():
            continue
        name = f"fde_module_{m['id'].lower()}"
        spec = importlib.util.spec_from_file_location(name, entry, submodule_search_locations=[str(entry.parent)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        sys.path.insert(0, str(entry.parent))
        try:
            spec.loader.exec_module(mod)
            mod.register(_ModuleApp(app, m["id"]), ctx)
            _loaded[m["id"]] = mod
        except Exception:  # one broken module must not take the platform down
            log.exception("Module %s failed to load", m["id"])
        finally:
            sys.path.remove(str(entry.parent))
    _register_routes(app)


def _register_routes(app) -> None:
    @app.route("/api/modules")
    @api.auth_required
    def list_modules():
        show_all = request.args.get("all") == "1" and request.current_user["role"] == "admin"
        mods = [public_manifest(m) for m in _manifests.values()]
        if not show_all:
            mods = [m for m in mods if m["enabled"]]
        return jsonify({"modules": sorted(mods, key=lambda m: m["id"])}), 200

    @app.route("/api/modules/<mid>")
    @api.auth_required
    def get_module(mid):
        m = _manifests.get(mid.upper())
        if not m:
            return jsonify({"error": "Unknown module"}), 404
        return jsonify({"module": public_manifest(m)}), 200

    @app.route("/api/modules/<mid>", methods=["PUT"])
    @api.admin_required
    def set_module(mid):
        m = _manifests.get(mid.upper())
        if not m:
            return jsonify({"error": "Unknown module"}), 404
        if m["id"] == "M01":
            return jsonify({"error": "M01 is the platform core and cannot be disabled."}), 400
        enabled = bool((request.json or {}).get("enabled"))
        set_setting(f"module.{m['id']}.enabled", enabled)
        u = request.current_user
        store.add_audit(u["id"], u["username"], "module_enabled" if enabled else "module_disabled", target=m["id"])
        return jsonify({"module": public_manifest(m)}), 200
