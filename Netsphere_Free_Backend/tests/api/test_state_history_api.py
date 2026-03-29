from datetime import datetime, timedelta, timezone

from app.core.license import LicenseSchema
from app.models.approval import ApprovalRequest
from app.models.asset_change_event import AssetChangeEvent
from app.models.cloud import CloudAccount, CloudResource
from app.models.device import Device, Issue, Site
from app.models.monitoring_profile import MonitoringProfile, MonitoringProfileAssignment
from app.models.operation_action import OperationAction
from app.models.service_group import ServiceGroup, ServiceGroupMember
from app.models.user import User
from app.services.license_service import LicenseService


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _allow_license_features(monkeypatch, features: list[str]):
    lic = LicenseSchema(
        customer="StateHistory-Test",
        expiration=datetime.now(timezone.utc) + timedelta(days=30),
        max_devices=1000,
        features=list(features or []),
        is_valid=True,
        status="Active",
    )
    monkeypatch.setattr(
        LicenseService,
        "get_effective_license",
        staticmethod(lambda _db, _lic=lic: _lic),
    )


def _seed_operating_context(db):
    site = Site(name="HQ-State", type="campus")
    db.add(site)
    db.commit()
    db.refresh(site)

    core = Device(
        name="state-core-01",
        hostname="state-core-01",
        ip_address="10.20.0.1",
        serial_number="STATE-001",
        role="core",
        device_type="cisco_ios",
        status="online",
        management_state="managed",
        site_id=int(site.id),
    )
    edge = Device(
        name="state-edge-02",
        ip_address="10.20.0.2",
        role="access",
        device_type="dasan_nos",
        status="offline",
        management_state="discovered_only",
    )
    account = CloudAccount(
        name="state-aws",
        provider="aws",
        credentials={"access_key": "masked", "secret_key": "masked"},
        is_active=True,
    )
    group = ServiceGroup(
        name="state-public-service",
        criticality="high",
        owner_team="InfraOps",
        color="#0ea5e9",
    )
    db.add_all([core, edge, account, group])
    db.commit()
    db.refresh(core)
    db.refresh(edge)
    db.refresh(account)
    db.refresh(group)

    resource = CloudResource(
        account_id=int(account.id),
        resource_id="vpc-state-001",
        resource_type="vpc",
        name="state-vpc",
        region="ap-northeast-2",
        state="available",
    )
    db.add(resource)
    db.commit()
    db.refresh(resource)

    db.add_all(
        [
            ServiceGroupMember(service_group_id=int(group.id), member_type="device", device_id=int(core.id)),
            ServiceGroupMember(
                service_group_id=int(group.id),
                member_type="cloud_resource",
                cloud_resource_id=int(resource.id),
            ),
        ]
    )
    db.commit()

    profile = db.query(MonitoringProfile).filter(MonitoringProfile.key == "general-managed").first()
    db.add(
        MonitoringProfileAssignment(
            device_id=int(core.id),
            profile_id=int(profile.id),
            assignment_source="auto",
            confidence=0.92,
            recommendation_reasons=["baseline"],
        )
    )
    db.add(
        Issue(
            device_id=int(core.id),
            title="BGP neighbor flap",
            severity="critical",
            status="active",
            category="network",
        )
    )
    db.commit()
    issue = db.query(Issue).filter(Issue.device_id == int(core.id)).first()

    db.add(
        OperationAction(
            issue_id=int(issue.id),
            device_id=int(core.id),
            title="Investigate BGP flap",
            severity="critical",
            status="investigating",
            assignee_name="NOC-A",
            latest_note="Collected route and neighbor state",
            created_by="operator",
            updated_by="operator",
        )
    )

    admin_user = db.query(User).filter(User.username == "adminuser").first()
    db.add(
        ApprovalRequest(
            requester_id=int(admin_user.id),
            title="Review BGP stabilization",
            description="Stabilize route advertisements",
            request_type="cloud_policy",
            payload={"execution_trace": {"steps": 2}},
            status="pending",
        )
    )
    db.add(
        AssetChangeEvent(
            asset_kind="device",
            asset_key=f"device:{int(core.id)}",
            asset_name=str(core.name),
            action="updated",
            summary="Core device metadata refreshed",
            actor_name="operator",
            actor_role="operator",
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    return {
        "site": site,
        "core": core,
        "edge": edge,
        "account": account,
        "resource": resource,
        "group": group,
    }


def test_state_history_current_snapshot_and_create(client, admin_user_token, db, monkeypatch):
    _allow_license_features(monkeypatch, ["automation_hub"])
    _seed_operating_context(db)

    current_res = client.get("/api/v1/automation-hub/state-history/current", headers=admin_user_token)
    assert current_res.status_code == 200
    current = _unwrap(current_res.json())
    assert current["metrics"]["devices_total"] == 2
    assert current["metrics"]["active_issues_total"] == 1
    assert current["metrics"]["monitoring_profile_assignments_total"] == 1
    assert current["coverage"]["service_groups_with_owner"] == 1

    create_res = client.post(
        "/api/v1/automation-hub/state-history/snapshots",
        json={"label": "Weekly review baseline", "note": "Pre-maintenance snapshot"},
        headers=admin_user_token,
    )
    assert create_res.status_code == 200
    created = _unwrap(create_res.json())
    assert created["label"] == "Weekly review baseline"
    assert created["note"] == "Pre-maintenance snapshot"
    assert created["event_log_id"] > 0

    list_res = client.get("/api/v1/automation-hub/state-history/snapshots", headers=admin_user_token)
    assert list_res.status_code == 200
    rows = _unwrap(list_res.json())
    assert len(rows) >= 1
    assert rows[0]["event_log_id"] == created["event_log_id"]


def test_state_history_compare_snapshot_to_current(client, admin_user_token, db, monkeypatch):
    _allow_license_features(monkeypatch, ["automation_hub"])
    seeded = _seed_operating_context(db)

    create_res = client.post(
        "/api/v1/automation-hub/state-history/snapshots",
        json={"label": "Baseline A"},
        headers=admin_user_token,
    )
    assert create_res.status_code == 200
    baseline = _unwrap(create_res.json())

    device = seeded["edge"]
    device.management_state = "managed"
    device.status = "online"
    db.add(
        Issue(
            device_id=int(device.id),
            title="Interface error rate",
            severity="warning",
            status="active",
            category="performance",
        )
    )
    db.commit()

    compare_res = client.get(
        f"/api/v1/automation-hub/state-history/compare/{int(baseline['event_log_id'])}",
        headers=admin_user_token,
    )
    assert compare_res.status_code == 200
    payload = _unwrap(compare_res.json())
    assert payload["baseline"]["event_log_id"] == baseline["event_log_id"]
    assert payload["current"]["metrics"]["managed_devices"] == 2
    assert payload["summary"]["result"] in {"changed", "improved", "review", "steady"}
    assert len(payload["cards"]) >= 5
    keys = {row["key"] for row in payload["cards"]}
    assert "management_posture" in keys
    assert "operations_pressure" in keys
