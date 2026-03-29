from app.models.device import Device
from app.models.monitoring_profile import MonitoringProfileAssignment


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_monitoring_profile_catalog_seeds_defaults(client, operator_user_token):
    res = client.get("/api/v1/monitoring-profiles/catalog", headers=operator_user_token)
    assert res.status_code == 200
    payload = _unwrap(res.json())

    profile_keys = {str(row.get("key") or "") for row in payload["profiles"]}
    assert "core-network" in profile_keys
    assert "general-managed" in profile_keys
    assert "discovered-light" in profile_keys
    assert payload["coverage"]["active_profiles"] >= 3


def test_monitoring_profile_create_update_delete(client, admin_user_token, operator_user_token):
    create_res = client.post(
        "/api/v1/monitoring-profiles/",
        json={
            "key": "branch-edge",
            "name": "Branch Edge",
            "description": "Edge monitoring profile for branch uplinks.",
            "management_scope": "managed",
            "telemetry_mode": "hybrid",
            "priority": 165,
            "match_roles": ["edge"],
            "match_device_types": ["fortinet"],
            "dashboard_tags": ["branch", "edge"],
        },
        headers=admin_user_token,
    )
    assert create_res.status_code == 200
    created = _unwrap(create_res.json())
    assert created["key"] == "branch-edge"
    assert created["assigned_devices"] == 0

    update_res = client.put(
        f"/api/v1/monitoring-profiles/{created['id']}",
        json={
            "name": "Branch Edge Updated",
            "priority": 175,
            "dashboard_tags": ["branch", "edge", "priority"],
        },
        headers=admin_user_token,
    )
    assert update_res.status_code == 200
    updated = _unwrap(update_res.json())
    assert updated["name"] == "Branch Edge Updated"
    assert updated["priority"] == 175
    assert "priority" in list(updated["dashboard_tags"] or [])

    list_res = client.get("/api/v1/monitoring-profiles/", headers=operator_user_token)
    assert list_res.status_code == 200
    rows = _unwrap(list_res.json())
    assert any(int(row["id"]) == int(created["id"]) for row in rows)

    delete_res = client.delete(f"/api/v1/monitoring-profiles/{created['id']}", headers=admin_user_token)
    assert delete_res.status_code == 200

    list_after = client.get("/api/v1/monitoring-profiles/", headers=operator_user_token)
    rows_after = _unwrap(list_after.json())
    assert all(int(row["id"]) != int(created["id"]) for row in rows_after)


def test_monitoring_profile_recommendation_is_read_only_and_respects_discovered_only_scope(client, normal_user_token, db):
    device = Device(
        name="edge-free-01",
        ip_address="10.40.0.10",
        device_type="dasan_nos",
        role="access",
        status="online",
        management_state="discovered_only",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    before_count = db.query(MonitoringProfileAssignment).count()
    res = client.get(f"/api/v1/monitoring-profiles/devices/{device.id}/recommendation", headers=normal_user_token)
    assert res.status_code == 200
    payload = _unwrap(res.json())
    rec = payload["recommendation"]
    assert rec["key"] == "discovered-light"
    assert rec["activation_state"] == "active"
    assert rec["assignment_source"] == "auto"

    after_count = db.query(MonitoringProfileAssignment).count()
    assert after_count == before_count


def test_monitoring_profile_manual_assign_and_recompute_keep_manual_override(client, operator_user_token, db):
    device = Device(
        name="core-sw-02",
        ip_address="10.50.0.2",
        device_type="cisco_ios",
        role="core",
        status="online",
        management_state="managed",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    catalog = client.get("/api/v1/monitoring-profiles/catalog", headers=operator_user_token)
    assert catalog.status_code == 200
    profiles = _unwrap(catalog.json())["profiles"]
    fallback = next(row for row in profiles if str(row.get("key")) == "general-managed")

    assign_res = client.post(
        f"/api/v1/monitoring-profiles/devices/{device.id}/assign",
        json={"profile_id": int(fallback["id"])},
        headers=operator_user_token,
    )
    assert assign_res.status_code == 200
    assigned = _unwrap(assign_res.json())["recommendation"]
    assert assigned["key"] == "general-managed"
    assert assigned["assignment_source"] == "manual"

    recompute_res = client.post(
        f"/api/v1/monitoring-profiles/devices/{device.id}/recompute",
        headers=operator_user_token,
    )
    assert recompute_res.status_code == 200
    recomputed = _unwrap(recompute_res.json())["recommendation"]
    assert recomputed["key"] == "general-managed"
    assert recomputed["assignment_source"] == "manual"


def test_device_payload_includes_monitoring_profile_summary(client, normal_user_token, db):
    device = Device(
        name="dist-sw-01",
        ip_address="10.60.0.1",
        device_type="cisco_ios",
        role="distribution",
        status="online",
        management_state="managed",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    detail_res = client.get(f"/api/v1/devices/{device.id}", headers=normal_user_token)
    assert detail_res.status_code == 200
    detail = _unwrap(detail_res.json())
    assert detail["monitoring_profile"]["key"] == "core-network"
    assert detail["monitoring_profile"]["activation_state"] == "active"

    list_res = client.get("/api/v1/devices/", headers=normal_user_token)
    assert list_res.status_code == 200
    rows = _unwrap(list_res.json())
    row = next(item for item in rows if int(item["id"]) == int(device.id))
    assert row["monitoring_profile"]["key"] == "core-network"

