from app.models.cloud import CloudAccount, CloudResource
from app.models.device import Device, Issue


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_service_group_create_and_catalog(client, operator_user_token, db):
    device = Device(
        name="core-sw-1",
        ip_address="10.10.10.1",
        role="core",
        status="online",
        management_state="managed",
    )
    account = CloudAccount(
        name="aws-seoul",
        provider="aws",
        credentials={"access_key": "masked", "secret_key": "masked"},
        is_active=True,
    )
    db.add_all([device, account])
    db.commit()
    db.refresh(device)
    db.refresh(account)
    resource = CloudResource(
        account_id=int(account.id),
        resource_id="vpc-1234",
        resource_type="vpc",
        name="core-vpc",
        region="ap-northeast-2",
        state="available",
    )
    db.add(resource)
    db.commit()

    catalog_res = client.get("/api/v1/service-groups/catalog", headers=operator_user_token)
    assert catalog_res.status_code == 200
    catalog = _unwrap(catalog_res.json())
    assert any(int(row["id"]) == int(device.id) for row in catalog["devices"])
    assert any(str(row["resource_id"]) == "vpc-1234" for row in catalog["cloud_resources"])

    create_res = client.post(
        "/api/v1/service-groups/",
        json={
            "name": "민원 서비스",
            "description": "민원 업무망 핵심 서비스",
            "criticality": "high",
            "owner_team": "InfraOps",
            "color": "#22c55e",
            "is_active": True,
        },
        headers=operator_user_token,
    )
    assert create_res.status_code == 200
    body = _unwrap(create_res.json())
    assert body["name"] == "민원 서비스"
    assert body["member_count"] == 0


def test_service_group_add_device_and_cloud_member(client, operator_user_token, db):
    device = Device(
        name="edge-sw-1",
        ip_address="10.10.20.1",
        role="edge",
        status="online",
        management_state="managed",
    )
    account = CloudAccount(
        name="gcp-seoul",
        provider="gcp",
        credentials={"project_id": "demo", "service_account_json": "{}"},
        is_active=True,
    )
    db.add_all([device, account])
    db.commit()
    db.refresh(device)
    db.refresh(account)
    resource = CloudResource(
        account_id=int(account.id),
        resource_id="subnet-demo",
        resource_type="subnet",
        name="dmz-subnet",
        region="asia-northeast3",
        state="available",
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)

    create_res = client.post(
        "/api/v1/service-groups/",
        json={"name": "행정 포털", "description": "", "criticality": "standard", "owner_team": "NOC", "color": "#0ea5e9", "is_active": True},
        headers=operator_user_token,
    )
    group_id = int(_unwrap(create_res.json())["id"])

    add_device = client.post(f"/api/v1/service-groups/{group_id}/members/device/{int(device.id)}", headers=operator_user_token)
    assert add_device.status_code == 200
    detail = _unwrap(add_device.json())
    assert detail["device_count"] == 1
    assert any(row["member_type"] == "device" and row["display_name"] == "edge-sw-1" for row in detail["members"])

    add_cloud = client.post(f"/api/v1/service-groups/{group_id}/members/cloud/{int(resource.id)}", headers=operator_user_token)
    assert add_cloud.status_code == 200
    detail = _unwrap(add_cloud.json())
    assert detail["cloud_resource_count"] == 1
    assert any(row["member_type"] == "cloud_resource" and row["display_name"] == "dmz-subnet" for row in detail["members"])


def test_service_group_remove_member_and_delete(client, operator_user_token):
    create_res = client.post(
        "/api/v1/service-groups/",
        json={"name": "업무 시스템", "description": "", "criticality": "standard", "owner_team": "Ops", "color": "#6366f1", "is_active": True},
        headers=operator_user_token,
    )
    assert create_res.status_code == 200
    group = _unwrap(create_res.json())
    group_id = int(group["id"])

    list_res = client.get("/api/v1/service-groups/", headers=operator_user_token)
    assert list_res.status_code == 200
    rows = _unwrap(list_res.json())
    assert any(int(row["id"]) == group_id for row in rows)

    delete_res = client.delete(f"/api/v1/service-groups/{group_id}", headers=operator_user_token)
    assert delete_res.status_code == 200

    not_found = client.get(f"/api/v1/service-groups/{group_id}", headers=operator_user_token)
    assert not_found.status_code == 404


def test_service_group_health_summary(client, operator_user_token, db):
    managed_device = Device(
        name="svc-core-1",
        ip_address="10.20.0.1",
        role="core",
        status="offline",
        reachability_status="unreachable",
        management_state="managed",
    )
    discovered_device = Device(
        name="svc-edge-1",
        ip_address="10.20.0.2",
        role="edge",
        status="online",
        reachability_status="reachable",
        management_state="discovered_only",
    )
    db.add_all([managed_device, discovered_device])
    db.commit()
    db.refresh(managed_device)
    db.refresh(discovered_device)

    db.add(
        Issue(
            device_id=int(managed_device.id),
            title="Core uplink degraded",
            description="Critical issue for service health scoring",
            severity="critical",
            status="active",
            category="device",
        )
    )
    db.commit()

    create_res = client.post(
        "/api/v1/service-groups/",
        json={
            "name": "Service Health Demo",
            "description": "service health validation",
            "criticality": "high",
            "owner_team": "InfraOps",
            "color": "#2563eb",
            "is_active": True,
        },
        headers=operator_user_token,
    )
    assert create_res.status_code == 200
    group_id = int(_unwrap(create_res.json())["id"])

    add_managed = client.post(f"/api/v1/service-groups/{group_id}/members/device/{int(managed_device.id)}", headers=operator_user_token)
    assert add_managed.status_code == 200
    add_discovered = client.post(f"/api/v1/service-groups/{group_id}/members/device/{int(discovered_device.id)}", headers=operator_user_token)
    assert add_discovered.status_code == 200

    detail_res = client.get(f"/api/v1/service-groups/{group_id}", headers=operator_user_token)
    assert detail_res.status_code == 200
    detail = _unwrap(detail_res.json())
    assert detail["health"]["health_status"] in {"critical", "degraded"}
    assert int(detail["health"]["critical_issue_count"]) == 1
    assert int(detail["health"]["offline_device_count"]) == 1
    assert int(detail["health"]["discovered_only_device_count"]) == 1

    list_res = client.get("/api/v1/service-groups/", headers=operator_user_token)
    assert list_res.status_code == 200
    rows = _unwrap(list_res.json())
    target = next(row for row in rows if int(row["id"]) == group_id)
    assert "health" in target
    assert int(target["health"]["member_device_count"]) == 2
