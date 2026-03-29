from __future__ import annotations

import json

from app.models.device import Device
from app.models.settings import SystemSetting
from app.services.post_check_service import resolve_pre_check_commands


def _set_list_setting(db, key: str, commands: list[str]) -> None:
    value = json.dumps(commands, ensure_ascii=False, separators=(",", ":"))
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value, description="", category="automation"))
    db.commit()


def test_resolve_pre_check_commands_uses_vendor_defaults(db):
    d = Device(
        name="junos-precheck-default",
        ip_address="10.0.0.101",
        device_type="juniper_junos",
        role="core",
    )
    db.add(d)
    db.commit()
    db.refresh(d)

    cmds = resolve_pre_check_commands(db, d)
    assert isinstance(cmds, list)
    assert "show system uptime" in cmds
    assert "show chassis alarms" in cmds


def test_resolve_pre_check_commands_prefers_vendor_override_setting(db):
    d = Device(
        name="junos-precheck-override",
        ip_address="10.0.0.102",
        device_type="juniper_junos",
        role="core",
    )
    db.add(d)
    db.commit()
    db.refresh(d)

    expected = ["show version | no-more", "show interfaces terse | no-more"]
    _set_list_setting(db, "pre_check_vendor_juniper_junos", expected)

    cmds = resolve_pre_check_commands(db, d)
    assert cmds == expected

