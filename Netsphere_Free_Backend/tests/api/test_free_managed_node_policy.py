from app.models.device import Device
from app.models.settings import SystemSetting
from app.services.preview_managed_node_service import PreviewManagedNodeService


def _preview_settings(db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="collector_installed", description="", category="preview"),
        ]
    )
    db.commit()


def _make_device(idx: int, **overrides):
    payload = {
        "name": f"free-node-{idx}",
        "ip_address": f"10.10.0.{idx}",
        "device_type": "cisco_ios",
        "status": "online",
        "role": "access",
    }
    payload.update(overrides)
    return Device(**payload)


def test_preview_policy_exposes_managed_node_limit_and_summary(client, normal_user_token, db):
    _preview_settings(db)
    db.add_all([_make_device(1, role="core"), _make_device(2)])
    db.commit()

    res = client.get("/api/v1/preview/policy", headers=normal_user_token)

    assert res.status_code == 200
    payload = res.json()["data"]
    assert payload["managed_node_limit"] == 50
    assert payload["managed_nodes"]["total_discovered"] == 2
    assert payload["managed_nodes"]["managed"] == 2
    assert payload["managed_nodes"]["discovered_only"] == 0
    assert "/edition/compare" in payload["allowed_nav_exact_paths"]


def test_free_managed_summary_and_slot_assignment_flow(client, admin_user_token, normal_user_token, db):
    _preview_settings(db)
    db.add_all([_make_device(i) for i in range(1, 53)])
    db.commit()
    summary = PreviewManagedNodeService.reconcile_managed_devices(db)
    assert summary["managed"] == 50
    assert summary["discovered_only"] == 2

    res = client.get("/api/v1/devices/managed-summary", headers=normal_user_token)
    assert res.status_code == 200
    payload = res.json()["data"]
    assert payload["managed_limit"] == 50
    assert payload["managed"] == 50
    assert payload["discovered_only"] == 2

    discovered_only = (
        db.query(Device)
        .filter(Device.management_state == PreviewManagedNodeService.STATE_DISCOVERED_ONLY)
        .order_by(Device.id.asc())
        .first()
    )
    managed = (
        db.query(Device)
        .filter(Device.management_state == PreviewManagedNodeService.STATE_MANAGED)
        .order_by(Device.id.asc())
        .first()
    )

    blocked = client.post(f"/api/v1/devices/{discovered_only.id}/manage", headers=admin_user_token)
    assert blocked.status_code == 409

    released = client.post(f"/api/v1/devices/{managed.id}/release-management", headers=admin_user_token)
    assert released.status_code == 200
    assert released.json()["data"]["summary"]["remaining_slots"] == 1

    refreshed = client.get("/api/v1/devices/managed-summary", headers=normal_user_token)
    assert refreshed.status_code == 200
    assert refreshed.json()["data"]["remaining_slots"] == 1

    promoted = client.post(f"/api/v1/devices/{discovered_only.id}/manage", headers=admin_user_token)
    assert promoted.status_code == 200
    assert promoted.json()["data"]["device"]["management_state"] == "managed"


def test_free_preview_blocks_sync_for_discovered_only_nodes(client, admin_user_token, db):
    _preview_settings(db)
    db.add_all([_make_device(i) for i in range(1, 52)])
    db.commit()
    PreviewManagedNodeService.reconcile_managed_devices(db)

    discovered_only = (
        db.query(Device)
        .filter(Device.management_state == PreviewManagedNodeService.STATE_DISCOVERED_ONLY)
        .order_by(Device.id.asc())
        .first()
    )
    denied_sync = client.post(f"/api/v1/devices/{discovered_only.id}/sync", headers=admin_user_token)
    assert denied_sync.status_code == 403
    assert "PREVIEW_MANAGED_NODE_LIMIT" in str(denied_sync.json())
