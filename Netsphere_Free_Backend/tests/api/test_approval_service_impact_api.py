from app.models.approval import ApprovalRequest
from app.models.cloud import CloudAccount, CloudResource
from app.models.device import Device
from app.models.service_group import ServiceGroup, ServiceGroupMember
def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_approval_service_impact_matches_device_scope(client, admin_user_token, db):
    device = Device(
        name="svc-access-1",
        hostname="svc-access-1",
        ip_address="10.71.0.10",
        status="online",
        device_type="cisco_ios",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    group = ServiceGroup(name="Citizen Edge", criticality="high", owner_team="InfraOps")
    db.add(group)
    db.commit()
    db.refresh(group)

    member = ServiceGroupMember(service_group_id=int(group.id), member_type="device", device_id=int(device.id), role_label="edge")
    db.add(member)
    db.commit()

    req = ApprovalRequest(
        requester_id=1,
        title="Deploy edge change",
        request_type="template_deploy",
        payload={"device_ids": [int(device.id)]},
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    res = client.get(f"/api/v1/approval/{int(req.id)}/service-impact", headers=admin_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["approval_id"] == int(req.id)
    assert body["summary"]["count"] == 1
    assert body["groups"][0]["name"] == group.name
    assert body["groups"][0]["matched_members"][0]["match_reason"] == "device_scope"


def test_approval_service_impact_matches_cloud_scope(client, admin_user_token, db):
    account = CloudAccount(name="aws-seoul", provider="aws", credentials={"mode": "test"})
    db.add(account)
    db.commit()
    db.refresh(account)

    resource = CloudResource(
        account_id=int(account.id),
        resource_id="subnet-4444",
        resource_type="subnet",
        name="citizen-subnet",
        region="ap-northeast-2",
        state="available",
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)

    group = ServiceGroup(name="Citizen Cloud", criticality="elevated", owner_team="CloudOps")
    db.add(group)
    db.commit()
    db.refresh(group)

    member = ServiceGroupMember(service_group_id=int(group.id), member_type="cloud_resource", cloud_resource_id=int(resource.id), role_label="network")
    db.add(member)
    db.commit()

    req = ApprovalRequest(
        requester_id=1,
        title="Apply cloud intent",
        request_type="intent_apply",
        payload={
            "account_id": int(account.id),
            "resource_id": "subnet-4444",
            "provider": "aws",
            "region": "ap-northeast-2",
        },
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    res = client.get(f"/api/v1/approval/{int(req.id)}/service-impact", headers=admin_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["summary"]["count"] == 1
    assert body["groups"][0]["name"] == group.name
    assert body["groups"][0]["matched_members"][0]["member_type"] == "cloud_resource"
    assert body["groups"][0]["matched_members"][0]["match_reason"] == "resource_scope"
