"""Admin-managed EKS cluster registry (merged with AWS/kubeconfig discovery)."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_POD_DIR = Path(__file__).resolve().parent
_DEFAULT_REGISTRY = _POD_DIR / "data" / "clusters_registry.json"
_LOCK = threading.RLock()


def _registry_path() -> Path:
    env_path = (os.environ.get("POD_CLUSTERS_REGISTRY") or "").strip()
    if env_path:
        return Path(env_path)
    return _DEFAULT_REGISTRY


def _empty_registry() -> dict[str, Any]:
    return {"clusters": [], "nextId": 1}


def _load_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.is_file():
        return _empty_registry()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty_registry()
        data.setdefault("clusters", [])
        data.setdefault("nextId", 1)
        return data
    except (OSError, json.JSONDecodeError):
        return _empty_registry()


def _save_registry(data: dict[str, Any]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "name": row.get("name") or "",
        "region": row.get("region") or "us-east-2",
        "label": row.get("label") or row.get("name") or "",
        "notes": row.get("notes") or "",
        "roleArn": (row.get("roleArn") or row.get("role_arn") or "").strip(),
        "enabled": bool(row.get("enabled", True)),
        "source": "registry",
        "createdAt": row.get("createdAt"),
        "updatedAt": row.get("updatedAt"),
    }


def _normalize_role_arn(value: Optional[str]) -> str:
    return (value or "").strip()


def _validate_role_arn(role_arn: str) -> Optional[str]:
    if not role_arn:
        return None
    if not role_arn.startswith("arn:aws:iam::") or ":role/" not in role_arn:
        return "IAM role ARN must look like arn:aws:iam::123456789012:role/YourRole"
    return None


def list_registry_clusters(*, include_disabled: bool = False) -> list[dict[str, Any]]:
    with _LOCK:
        data = _load_registry()
        rows = []
        for row in data.get("clusters") or []:
            if not isinstance(row, dict):
                continue
            if not include_disabled and not row.get("enabled", True):
                continue
            rows.append(_row_to_dict(row))
        rows.sort(key=lambda c: (c.get("name") or "").lower())
        return rows


def get_registry_cluster_by_name(name: str) -> Optional[dict[str, Any]]:
    key = (name or "").strip().lower()
    if not key:
        return None
    with _LOCK:
        for row in _load_registry().get("clusters") or []:
            if isinstance(row, dict) and (row.get("name") or "").strip().lower() == key:
                return _row_to_dict(row)
    return None


def get_registry_cluster(cluster_id: int) -> Optional[dict[str, Any]]:
    with _LOCK:
        for row in _load_registry().get("clusters") or []:
            if isinstance(row, dict) and int(row.get("id") or 0) == cluster_id:
                return _row_to_dict(row)
    return None


def add_registry_cluster(
    *,
    name: str,
    region: str,
    label: str = "",
    notes: str = "",
    role_arn: str = "",
    enabled: bool = True,
    actor: dict[str, Any],
) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
    name = (name or "").strip()
    region = (region or "us-east-2").strip()
    role_arn = _normalize_role_arn(role_arn)
    if not name:
        return None, "Cluster name is required"
    if not region:
        return None, "AWS region is required"
    role_err = _validate_role_arn(role_arn)
    if role_err:
        return None, role_err
    now = time.time()
    with _LOCK:
        data = _load_registry()
        for row in data.get("clusters") or []:
            if isinstance(row, dict) and (row.get("name") or "").strip().lower() == name.lower():
                return None, f"Cluster '{name}' already exists in registry"
        cluster_id = int(data.get("nextId") or 1)
        entry = {
            "id": cluster_id,
            "name": name,
            "region": region,
            "label": (label or name).strip(),
            "notes": (notes or "").strip(),
            "roleArn": role_arn,
            "enabled": bool(enabled),
            "createdAt": now,
            "updatedAt": now,
        }
        data["clusters"].append(entry)
        data["nextId"] = cluster_id + 1
        _save_registry(data)
    from pod_rbac import log_audit
    log_audit(actor, name, "cluster.create", {
        "name": name,
        "region": region,
        "label": entry["label"],
        "hasRoleArn": bool(role_arn),
    })
    return _row_to_dict(entry), None


def update_registry_cluster(
    cluster_id: int,
    *,
    name: Optional[str] = None,
    region: Optional[str] = None,
    label: Optional[str] = None,
    notes: Optional[str] = None,
    role_arn: Optional[str] = None,
    enabled: Optional[bool] = None,
    actor: dict[str, Any],
) -> Tuple[Optional[dict[str, Any]], Optional[str]]:
    with _LOCK:
        data = _load_registry()
        rows = data.get("clusters") or []
        target = None
        for row in rows:
            if isinstance(row, dict) and int(row.get("id") or 0) == cluster_id:
                target = row
                break
        if not target:
            return None, "Cluster not found"
        if name is not None:
            new_name = name.strip()
            if not new_name:
                return None, "Cluster name cannot be empty"
            for row in rows:
                if row is not target and (row.get("name") or "").strip().lower() == new_name.lower():
                    return None, f"Cluster '{new_name}' already exists"
            target["name"] = new_name
        if region is not None:
            region_val = region.strip()
            if not region_val:
                return None, "Region cannot be empty"
            target["region"] = region_val
        if label is not None:
            target["label"] = label.strip()
        if notes is not None:
            target["notes"] = notes.strip()
        if role_arn is not None:
            role_val = _normalize_role_arn(role_arn)
            role_err = _validate_role_arn(role_val)
            if role_err:
                return None, role_err
            target["roleArn"] = role_val
        if enabled is not None:
            target["enabled"] = bool(enabled)
        target["updatedAt"] = time.time()
        _save_registry(data)
        result = _row_to_dict(target)
    from pod_rbac import log_audit
    log_audit(actor, result["name"], "cluster.update", {
        "id": cluster_id,
        "name": result["name"],
        "region": result["region"],
        "hasRoleArn": bool(result.get("roleArn")),
    })
    return result, None


def delete_registry_cluster(cluster_id: int, *, actor: dict[str, Any]) -> Tuple[bool, Optional[str]]:
    with _LOCK:
        data = _load_registry()
        rows = data.get("clusters") or []
        kept = []
        deleted = None
        for row in rows:
            if isinstance(row, dict) and int(row.get("id") or 0) == cluster_id:
                deleted = _row_to_dict(row)
            else:
                kept.append(row)
        if not deleted:
            return False, "Cluster not found"
        data["clusters"] = kept
        _save_registry(data)
    from pod_rbac import log_audit
    log_audit(actor, deleted["name"], "cluster.delete", {"id": cluster_id, "name": deleted["name"]})
    return True, None
