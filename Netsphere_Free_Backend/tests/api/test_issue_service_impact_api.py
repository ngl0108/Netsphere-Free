from app.models.cloud import CloudAccount, CloudResource
from app.models.device import Device, Issue
from app.models.service_group import ServiceGroup, ServiceGroupMember


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _seed_device_issue(db):
    device = Device(
        name="svc-edge-1",
        hostname="svc-edge-1",
        ip_address="10.66.0.10",
        status="online",
        device_type="cisco_ios",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    issue = Issue(
        device_id=int(device.id),
        title="Citizen service edge degradation",
        description="Packet loss was detected on the citizen services edge device.",
        severity="warning",
        category="performance",
        status="active",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)

    group = ServiceGroup(name="Citizen Services", criticality="high", owner_team="InfraOps")
    db.add(group)
    db.commit()
    db.refresh(group)

    member = ServiceGroupMember(service_group_id=int(group.id), member_type="device", device_id=int(device.id))
    db.add(member)
    db.commit()
    return issue, group


def _seed_cloud_issue(db):
    account = CloudAccount(name="aws-seoul", provider="aws", credentials={"mode": "test"})
    db.add(account)
    db.commit()
    db.refresh(account)

    resource = CloudResource(
        account_id=int(account.id),
        resource_id="subnet-1234",
        resource_type="subnet",
        name="citizen-subnet",
        region="ap-northeast-2",
        state="available",
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)

    device = Device(
        name="citizen-subnet-node",
        hostname="citizen-subnet-node",
        ip_address="10.66.10.10",
        status="online",
        device_type="cloud_virtual",
        variables={"cloud": {"refs": [{"resource_id": "subnet-1234", "resource_type": "subnet", "provider": "aws"}]}},
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    issue = Issue(
        device_id=int(device.id),
        title="Citizen subnet alert",
        description="Health degradation detected on a mapped cloud subnet.",
        severity="warning",
        category="system",
        status="active",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)

    group = ServiceGroup(name="Citizen Cloud", criticality="elevated", owner_team="CloudOps")
    db.add(group)
    db.commit()
    db.refresh(group)

    member = ServiceGroupMember(service_group_id=int(group.id), member_type="cloud_resource", cloud_resource_id=int(resource.id))
    db.add(member)
    db.commit()
    return issue, group


def test_issue_service_impact_returns_matching_groups(client, normal_user_token, db):
    issue, group = _seed_device_issue(db)

    res = client.get(f"/api/v1/sdn/issues/{int(issue.id)}/service-impact", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["issue_id"] == int(issue.id)
    assert len(body["groups"]) == 1
    assert body["groups"][0]["name"] == group.name
    assert body["groups"][0]["matched_member_count"] == 1
    assert body["groups"][0]["health_status"] in {"healthy", "degraded", "critical", "review"}
    assert "health_score" in body["groups"][0]


def test_issue_service_impact_matches_cloud_refs(client, normal_user_token, db):
    issue, group = _seed_cloud_issue(db)

    res = client.get(f"/api/v1/sdn/issues/{int(issue.id)}/service-impact", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert len(body["groups"]) == 1
    assert body["groups"][0]["name"] == group.name
    assert body["groups"][0]["matched_members"][0]["member_type"] == "cloud_resource"


def test_active_issues_include_service_impact_summary(client, normal_user_token, db):
    _, group = _seed_device_issue(db)

    res = client.get("/api/v1/sdn/issues/active", headers=normal_user_token)
    assert res.status_code == 200
    rows = _unwrap(res.json())
    assert len(rows) == 1
    summary = rows[0].get("service_impact_summary") or {}
    assert int(summary.get("count") or 0) == 1
    assert int(summary.get("primary_group_id") or 0) == int(group.id)
    assert summary.get("primary_name") == group.name
    assert "primary_health_score" in summary
    assert summary.get("primary_health_status") in {"healthy", "degraded", "critical", "review", None}


def test_dashboard_stats_include_service_group_health_summary(client, normal_user_token, db):
    _seed_device_issue(db)

    res = client.get("/api/v1/sdn/dashboard/stats", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    service_groups = body.get("service_groups") or {}
    assert int(service_groups.get("total") or 0) == 1
    assert "average_health_score" in service_groups
    assert isinstance(service_groups.get("items"), list)
    assert service_groups["items"][0]["name"] == "Citizen Services"
    state_history = body.get("state_history") or {}
    assert "snapshot_count" in state_history
    assert "latest_snapshot" in state_history
