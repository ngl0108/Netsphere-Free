from __future__ import annotations

import json
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.settings import SystemSetting


def _parse_list(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except Exception:
        return None
    if not isinstance(parsed, list):
        return None
    out: List[str] = []
    for x in parsed:
        s = str(x or "").strip()
        if s:
            out.append(s)
    return out or None


def _get_setting_list(db: Session, key: str) -> Optional[List[str]]:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        return None
    return _parse_list(row.value)


def resolve_post_check_commands(db: Session, device: Device) -> Optional[List[str]]:
    dt = str(getattr(device, "device_type", "") or "").lower().strip()
    role = str(getattr(device, "role", "") or "").strip()
    site_id = getattr(device, "site_id", None)
    device_id = int(getattr(device, "id"))

    keys = [
        f"post_check_device_{device_id}",
    ]
    if site_id is not None:
        keys.append(f"post_check_site_{int(site_id)}")
    if role:
        keys.append(f"post_check_role_{role}")
    if dt:
        keys.append(f"post_check_vendor_{dt}")
    keys.append("post_check_global")

    for k in keys:
        v = _get_setting_list(db, k)
        if v:
            return v
    return None


def _default_pre_check_commands(device_type: str) -> List[str]:
    dt = str(device_type or "").strip().lower()
    if "juniper" in dt or "junos" in dt:
        return ["show system uptime", "show chassis alarms", "show interfaces terse | no-more"]
    if "huawei" in dt:
        return ["display clock", "display version", "display interface brief"]
    if "arista" in dt or "eos" in dt:
        return ["show clock", "show version", "show interfaces status"]
    return ["show clock", "show version", "show ip interface brief"]


def resolve_pre_check_commands(db: Session, device: Device) -> Optional[List[str]]:
    dt = str(getattr(device, "device_type", "") or "").lower().strip()
    role = str(getattr(device, "role", "") or "").strip()
    site_id = getattr(device, "site_id", None)
    device_id = int(getattr(device, "id"))

    keys = [
        f"pre_check_device_{device_id}",
    ]
    if site_id is not None:
        keys.append(f"pre_check_site_{int(site_id)}")
    if role:
        keys.append(f"pre_check_role_{role}")
    if dt:
        keys.append(f"pre_check_vendor_{dt}")
    keys.append("pre_check_global")

    for k in keys:
        v = _get_setting_list(db, k)
        if v:
            return v
    return _default_pre_check_commands(dt)
