"""SQLite cache for service version API results (Comcast-only, 10s refresh)."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from service_versions import (
    _is_arloxcld_url,
    _is_configured_version_url,
    _resolve_version_service_id,
    _version_overrides,
    catalog_service_meta,
    fetch_version_api_detail,
    list_version_catalog_entries,
    load_catalog,
)

_POD_DIR = Path(__file__).resolve().parent
_DB_PATH = Path(os.environ.get("POD_VERSION_DB", str(_POD_DIR / "data" / "service_versions.db")))
_DEFAULT_CACHE_SEC = 45


def cache_ttl_sec() -> int:
    return int(os.environ.get("POD_VERSION_CACHE_TTL", str(_DEFAULT_CACHE_SEC)))


def cache_refresh_sec() -> int:
    return int(os.environ.get("POD_VERSION_REFRESH_SEC", str(_DEFAULT_CACHE_SEC)))
_lock = threading.Lock()
_started = False
_last_ns_map: dict[str, list[str]] = {}
_last_ns_lock = threading.Lock()


def update_namespace_map(ns_map: dict[str, list[str]]) -> None:
    with _last_ns_lock:
        _last_ns_map.clear()
        _last_ns_map.update({k.lower(): v for k, v in ns_map.items()})


def get_namespace_map() -> dict[str, list[str]]:
    with _last_ns_lock:
        return dict(_last_ns_map)


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS service_versions (
                    service_id TEXT NOT NULL,
                    cluster TEXT NOT NULL DEFAULT '',
                    version TEXT NOT NULL DEFAULT '',
                    version_url TEXT NOT NULL DEFAULT '',
                    version_source TEXT NOT NULL DEFAULT '',
                    version_error TEXT NOT NULL DEFAULT '',
                    raw_json TEXT NOT NULL DEFAULT '',
                    fetched_at REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (service_id, cluster)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "serviceId": row["service_id"],
        "version": row["version"] or "",
        "versionUrl": row["version_url"] or "",
        "versionSource": row["version_source"] or "",
        "versionError": row["version_error"] or "",
        "hasVersionApi": bool(row["version_url"]),
        "raw": row["raw_json"] or "",
        "fetchedAt": row["fetched_at"],
        "ageSec": max(0, int(time.time() - (row["fetched_at"] or 0))),
    }


def get_cached(service_id: str, cluster: str = "") -> dict[str, Any] | None:
    init_db()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM service_versions WHERE service_id = ? AND cluster = ?",
            (service_id.lower(), cluster or ""),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def get_latest_cached(service_id: str, cluster: str = "") -> dict[str, Any] | None:
    """Newest cache row for a service (cluster match first, then any cluster)."""
    init_db()
    sid = service_id.lower()
    resolved = _resolve_version_service_id(sid)
    for key in dict.fromkeys((sid, resolved)):
        entry = _get_latest_cached_key(key, cluster)
        if entry:
            return entry
    return None


def _get_latest_cached_key(service_id: str, cluster: str = "") -> dict[str, Any] | None:
    sid = service_id.lower()
    conn = _connect()
    try:
        if cluster:
            row = conn.execute(
                """
                SELECT * FROM service_versions
                WHERE service_id = ? AND cluster = ?
                ORDER BY fetched_at DESC LIMIT 1
                """,
                (sid, cluster),
            ).fetchone()
            if row:
                return _row_to_dict(row)
        row = conn.execute(
            """
            SELECT * FROM service_versions
            WHERE service_id = ?
            ORDER BY fetched_at DESC LIMIT 1
            """,
            (sid,),
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def get_all_cached(cluster: str = "") -> dict[str, dict[str, Any]]:
    init_db()
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT * FROM service_versions
            WHERE cluster = ? OR ? = '' OR cluster = ''
            ORDER BY fetched_at DESC
            """,
            (cluster or "", cluster or ""),
        ).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            sid = str(row["service_id"]).lower()
            if sid not in out:
                parsed = _row_to_dict(row)
                if parsed:
                    out[sid] = parsed
        return out
    finally:
        conn.close()


def is_fresh(service_id: str, cluster: str = "", ttl: int | None = None) -> bool:
    entry = get_cached(service_id, cluster)
    if not entry:
        return False
    err = str(entry.get("versionError") or "").lower()
    if err and not entry.get("version"):
        # Retry failed lookups (e.g. arloxcld before in-cluster fix was deployed)
        if "unreachable" in err or "http " in err or "urlopen" in err or "not configured" in err:
            return False
    if "not configured" in err or not entry.get("versionUrl"):
        sid = service_id.lower()
        if sid in _version_overrides():
            return False
    age = time.time() - float(entry.get("fetchedAt") or 0)
    return age < (ttl if ttl is not None else cache_ttl_sec())


def save_entry(
    service_id: str,
    cluster: str,
    *,
    version: str = "",
    version_url: str = "",
    version_source: str = "",
    version_error: str = "",
    raw: str = "",
) -> None:
    init_db()
    now = time.time()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO service_versions
                    (service_id, cluster, version, version_url, version_source, version_error, raw_json, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(service_id, cluster) DO UPDATE SET
                    version = excluded.version,
                    version_url = excluded.version_url,
                    version_source = excluded.version_source,
                    version_error = excluded.version_error,
                    raw_json = excluded.raw_json,
                    fetched_at = excluded.fetched_at
                """,
                (
                    service_id.lower(),
                    cluster or "",
                    version or "",
                    version_url or "",
                    version_source or "",
                    version_error or "",
                    raw or "",
                    now,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def fetch_and_store(
    service_id: str,
    cluster: str = "",
    namespaces: list[str] | None = None,
    *,
    prefer_http: bool | None = None,
) -> dict[str, Any]:
    catalog = load_catalog()
    meta = catalog_service_meta(catalog, service_id, cluster_hint=cluster)
    url_hint = str(meta.get("versionUrl") or "")
    use_http = prefer_http if prefer_http is not None else (
        _is_configured_version_url(url_hint) and not _is_arloxcld_url(url_hint)
    )
    detail = fetch_version_api_detail(
        catalog,
        service_id,
        list(namespaces or []),
        prefer_http=use_http,
        cluster_hint=cluster,
    )
    url = str(detail.get("versionUrl") or "")
    if ".partnercat." in url.lower():
        url = url.lower().replace(".partnercat.", ".comcast.")
    save_entry(
        service_id,
        cluster,
        version=str(detail.get("version") or ""),
        version_url=url,
        version_source=str(detail.get("versionSource") or ""),
        version_error=str(detail.get("versionError") or ""),
        raw=str(detail.get("raw") or ""),
    )
    detail["versionUrl"] = url
    detail["fromCache"] = False
    return detail


def get_or_fetch(
    service_id: str,
    cluster: str = "",
    namespaces: list[str] | None = None,
    *,
    force: bool = False,
    prefer_http: bool | None = None,
) -> dict[str, Any]:
    if not force and is_fresh(service_id, cluster):
        cached = get_cached(service_id, cluster)
        if cached:
            cached["fromCache"] = True
            cached["ok"] = bool(cached.get("version"))
            cached["config"] = _parse_config_from_raw(cached.get("raw"))
            return cached
    detail = fetch_and_store(service_id, cluster, namespaces, prefer_http=prefer_http)
    detail["ok"] = bool(detail.get("version"))
    detail["fromCache"] = False
    detail["config"] = _parse_config_from_raw(detail.get("raw"))
    return detail


def _parse_config_from_raw(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def apply_versions_to_services(services: list[dict[str, Any]], cluster: str = "") -> None:
    cached = get_all_cached(cluster)
    catalog = load_catalog()
    ns_map = {str(s.get("id", "")).lower(): list(s.get("namespaces") or []) for s in services}

    for svc in services:
        sid = str(svc.get("id", "")).lower()
        entry = cached.get(sid) or get_latest_cached(sid, cluster)
        if entry and entry.get("version"):
            svc["version"] = entry.get("version") or ""
            svc["versionUrl"] = entry.get("versionUrl") or ""
            svc["versionSource"] = entry.get("versionSource") or ""
            svc["versionError"] = entry.get("versionError") or ""
            svc["hasVersionApi"] = bool(entry.get("versionUrl"))
            continue

        meta = catalog_service_meta(catalog, sid, cluster_hint=cluster)
        url = str(meta.get("versionUrl") or "")
        if ".partnercat." in url.lower():
            url = url.lower().replace(".partnercat.", ".comcast.")
        if not url:
            continue

        svc["hasVersionApi"] = True
        svc["versionUrl"] = url

        if entry and not entry.get("version"):
            err = str(entry.get("versionError") or "")
            if err and "not configured" in err.lower():
                svc["versionError"] = ""
            else:
                svc["versionError"] = err


def enrich_service_list(
    services: list[dict[str, Any]],
    cluster: str = "",
    *,
    sync_if_missing: bool = False,
) -> None:
    """Apply SQLite versions to service rows (always). Optionally fetch missing ones."""
    apply_versions_to_services(services, cluster)
    ns_map = {str(s.get("id", "")).lower(): list(s.get("namespaces") or []) for s in services}
    if ns_map:
        update_namespace_map(ns_map)

    overrides = _version_overrides()
    for svc in services:
        sid = str(svc.get("id", "")).lower()
        url = overrides.get(sid) or overrides.get(_resolve_version_service_id(sid))
        if not url:
            continue
        svc["hasVersionApi"] = True
        svc["versionUrl"] = url

    for svc in services:
        sid = str(svc.get("id", "")).lower()
        entry = get_latest_cached(sid, cluster)
        if entry and entry.get("version"):
            svc["version"] = entry["version"]
            svc["versionUrl"] = entry.get("versionUrl") or svc.get("versionUrl") or ""
            svc["versionSource"] = entry.get("versionSource") or ""
            svc["versionError"] = entry.get("versionError") or ""
            svc["hasVersionApi"] = bool(svc.get("versionUrl") or entry.get("versionUrl"))

    if not sync_if_missing:
        return

    for svc in services:
        if svc.get("version") or not svc.get("hasVersionApi"):
            continue
        sid = str(svc.get("id", "")).lower()
        try:
            detail = fetch_and_store(sid, cluster, ns_map.get(sid) or [])
        except Exception as exc:
            svc["versionError"] = str(exc)[:120]
            continue
        if detail.get("version"):
            svc["version"] = detail["version"]
            svc["versionUrl"] = detail.get("versionUrl") or svc.get("versionUrl") or ""
            svc["versionSource"] = detail.get("versionSource") or ""
            svc["versionError"] = ""
        elif detail.get("versionError"):
            svc["versionError"] = detail["versionError"]


def refresh_stale_services(
    cluster: str,
    ns_map: dict[str, list[str]],
    *,
    force: bool = False,
) -> int:
    """Fetch versions for catalog services missing or stale in cache."""
    catalog = load_catalog()
    count = 0
    for item in list_version_catalog_entries(catalog, cluster_hint=cluster):
        sid = str(item.get("id") or "").lower()
        if not sid:
            continue
        if not force and is_fresh(sid, cluster):
            cached = get_latest_cached(sid, cluster)
            if cached and cached.get("version"):
                continue
        fetch_and_store(sid, cluster, ns_map.get(sid) or [])
        count += 1
    return count


def refresh_all(cluster: str = "", service_namespaces: dict[str, list[str]] | None = None) -> int:
    catalog = load_catalog()
    entries = list_version_catalog_entries(catalog, cluster_hint=cluster)
    ns_map = service_namespaces or {}
    count = 0
    for item in entries:
        sid = str(item.get("id") or "")
        if not sid:
            continue
        url = str(item.get("versionUrl") or "")
        if ".partnercat." in url.lower():
            continue
        fetch_and_store(sid, cluster, ns_map.get(sid.lower()) or ns_map.get(sid) or [])
        count += 1
    return count


def trigger_background_refresh(cluster: str, ns_map: dict[str, list[str]]) -> None:
    """Non-blocking version refresh for stale/missing cache entries."""
    def _run() -> None:
        try:
            refresh_stale_services(cluster, ns_map)
        except Exception as exc:
            print(f"[version_cache] async refresh error: {exc}")

    threading.Thread(target=_run, daemon=True, name="version-cache-async").start()


def _background_loop(cluster_supplier) -> None:
    while True:
        try:
            cluster = cluster_supplier() if callable(cluster_supplier) else ""
            refresh_stale_services(cluster, get_namespace_map())
        except Exception as exc:
            print(f"[version_cache] background refresh error: {exc}")
        time.sleep(cache_refresh_sec())


def start_background_refresh(cluster_supplier=None) -> None:
    global _started
    if _started:
        return
    _started = True
    init_db()
    cluster_supplier = cluster_supplier or (lambda: "")
    thread = threading.Thread(
        target=_background_loop,
        args=(cluster_supplier,),
        daemon=True,
        name="version-cache-refresh",
    )
    thread.start()
    print(f"[version_cache] background refresh every {cache_refresh_sec()}s → {_DB_PATH}")
