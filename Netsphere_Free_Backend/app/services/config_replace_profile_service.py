from __future__ import annotations

import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.settings import SystemSetting


def _parse_obj(value: Optional[str]) -> Optional[Dict[str, Any]]:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _get_setting_obj(db: Session, key: str) -> Optional[Dict[str, Any]]:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        return None
    return _parse_obj(row.value)


def resolve_config_replace_profile(db: Session, device: Device) -> Optional[Dict[str, Any]]:
    dt = str(getattr(device, "device_type", "") or "").lower().strip()
    role = str(getattr(device, "role", "") or "").strip()
    site_id = getattr(device, "site_id", None)
    device_id = int(getattr(device, "id"))

    keys = [
        f"config_replace_device_{device_id}",
    ]
    if site_id is not None:
        keys.append(f"config_replace_site_{int(site_id)}")
    if role:
        keys.append(f"config_replace_role_{role}")
    if dt:
        keys.append(f"config_replace_vendor_{dt}")
    keys.append("config_replace_global")

    for k in keys:
        v = _get_setting_obj(db, k)
        if v:
            return v
    return None
