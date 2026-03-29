from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.device import Device, Site
from app.models.settings import SystemSetting


@dataclass(frozen=True)
class VariableContext:
    merged: Dict[str, Any]
    sources: Dict[str, Dict[str, Any]]


def _safe_dict(v: Any) -> Dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _get_setting_value(db: Session, key: str) -> Optional[str]:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        return None
    try:
        return str(row.value or "")
    except Exception:
        return None


def _get_setting_json(db: Session, key: str) -> Dict[str, Any]:
    raw = _get_setting_value(db, key)
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return _safe_dict(parsed)
    except Exception:
        return {}


def upsert_setting_json(db: Session, key: str, value: Dict[str, Any], description: str = "", category: str = "variables") -> None:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    payload = json.dumps(_safe_dict(value), ensure_ascii=False)
    if row is None:
        row = SystemSetting(key=key, value=payload, description=description, category=category)
        db.add(row)
    else:
        row.value = payload
        if description:
            row.description = description
        if category:
            row.category = category
    db.commit()


def resolve_device_context(db: Session, device: Device, extra: Optional[Dict[str, Any]] = None) -> VariableContext:
    global_vars = _get_setting_json(db, "vars_global")

    site_vars: Dict[str, Any] = {}
    site_obj: Optional[Site] = None
    if getattr(device, "site_id", None):
        site_obj = db.query(Site).filter(Site.id == device.site_id).first()
        if site_obj:
            site_vars = _safe_dict(site_obj.variables)

    role_key = str(getattr(device, "role", "") or "").strip()
    role_vars = _get_setting_json(db, f"vars_role_{role_key}") if role_key else {}

    device_vars = _safe_dict(getattr(device, "variables", None))
    extra_vars = _safe_dict(extra)

    merged: Dict[str, Any] = {}
    merged.update(global_vars)
    merged.update(site_vars)
    merged.update(role_vars)
    merged.update(device_vars)
    merged.update(extra_vars)

    merged.setdefault("device", {})
    if not isinstance(merged["device"], dict):
        merged["device"] = {}

    merged["device"].update(
        {
            "id": int(device.id),
            "name": str(device.name),
            "ip": str(device.ip_address),
            "role": str(getattr(device, "role", "") or ""),
            "device_type": str(getattr(device, "device_type", "") or ""),
            "site_id": int(device.site_id) if getattr(device, "site_id", None) is not None else None,
        }
    )

    if site_obj:
        merged.setdefault("site", {})
        if not isinstance(merged["site"], dict):
            merged["site"] = {}
        merged["site"].update({"id": int(site_obj.id), "name": str(site_obj.name)})

    return VariableContext(
        merged=merged,
        sources={
            "global": global_vars,
            "site": site_vars,
            "role": role_vars,
            "device": device_vars,
            "extra": extra_vars,
        },
    )
