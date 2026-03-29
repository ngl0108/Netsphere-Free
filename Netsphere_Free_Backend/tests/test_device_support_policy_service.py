from __future__ import annotations

import json

from app.models.device import Device
from app.models.settings import SystemSetting
from app.services.device_support_policy_service import DeviceSupportPolicyService


def _upsert_setting(db, key: str, value: str, *, category: str = "General") -> None:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value, description="", category=category))
    db.commit()


def test_device_support_policy_unknown_device_type_defaults_to_unsupported(db):
    out = DeviceSupportPolicyService.evaluate_metadata(
        db,
        device_type="vendor_x_not_supported",
        os_version="1.0",
        model="X-1",
    )
    assert out.get("tier") == "unsupported"
    features = out.get("features") or {}
    assert bool(features.get("config")) is False
    assert bool(features.get("ztp")) is False
    assert "device_type_not_covered_in_support_matrix" in list(out.get("reasons") or [])


def test_device_support_policy_override_blocks_sync_feature(db):
    policy = {
        "default_tier": "unsupported",
        "matrix_readiness_tier": {
            "full": "official",
            "extended": "limited",
            "basic": "limited",
            "partial": "limited",
            "none": "unsupported",
        },
        "tiers": {
            "official": {"discovery": True, "sync": True, "ztp": True, "config": True, "rollback": True},
            "limited": {"discovery": True, "sync": True, "ztp": True, "config": True, "rollback": True},
            "unsupported": {"discovery": True, "sync": True, "ztp": False, "config": False, "rollback": False},
        },
        "overrides": [
            {
                "device_type": "cisco_xe",
                "tier": "limited",
                "reason": "lab_sync_block",
                "features": {"sync": False},
            }
        ],
    }
    _upsert_setting(
        db,
        DeviceSupportPolicyService.SETTING_KEY,
        json.dumps(policy, ensure_ascii=False, separators=(",", ":")),
    )

    device = Device(
        name="policy-sync-blocked",
        hostname="policy-sync-blocked",
        ip_address="10.10.10.10",
        device_type="cisco_xe",
        model="C9300",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    out = DeviceSupportPolicyService.evaluate_device(db, device)
    assert out.get("tier") == "limited"
    assert bool((out.get("features") or {}).get("sync")) is False
    assert "lab_sync_block" in list(out.get("reasons") or [])
    assert (
        DeviceSupportPolicyService.is_feature_allowed(
            db,
            device=device,
            feature="sync",
        )
        is False
    )


def test_device_support_policy_respects_capability_read_only(db):
    capability_profile = {
        "default": {
            "allowed_protocols": ["snmp", "ssh", "gnmi"],
            "auto_reflection": {"approval": True, "topology": True, "sync": True},
            "read_only": False,
        },
        "sites": {},
        "device_types": {
            "cisco_xe": {
                "read_only": True,
            }
        },
    }
    _upsert_setting(
        db,
        "capability_profile_json",
        json.dumps(capability_profile, ensure_ascii=False, separators=(",", ":")),
    )

    out = DeviceSupportPolicyService.evaluate_metadata(
        db,
        device_type="cisco_xe",
        os_version="17.9.4",
        model="C9300-48P",
    )
    features = out.get("features") or {}
    assert bool(features.get("config")) is False
    assert bool(features.get("ztp")) is False
    assert bool(features.get("rollback")) is False
    assert "capability_profile_read_only" in list(out.get("reasons") or [])


def test_device_support_policy_disables_rollback_for_linux_types(db):
    out = DeviceSupportPolicyService.evaluate_metadata(
        db,
        device_type="linux",
        os_version="22.04",
        model="ubuntu",
    )
    features = out.get("features") or {}
    assert bool(features.get("rollback")) is False
    assert "rollback_strategy_unsupported" in list(out.get("reasons") or [])
    strategy = out.get("rollback_strategy") or {}
    assert bool(strategy.get("supported")) is False

