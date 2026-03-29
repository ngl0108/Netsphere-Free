from datetime import datetime, timedelta, timezone

from app.core.license import LicenseSchema
from app.models.cloud import CloudAccount, CloudResource
from app.models.device import Device, Site
from app.models.service_group import ServiceGroup, ServiceGroupMember
from app.services.license_service import LicenseService


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _allow_license_features(monkeypatch, features: list[str]):
    lic = LicenseSchema(
        customer="SoT-Test",
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


def test_source_of_truth_summary_counts_and_coverage(client, admin_user_token, operator_user_token, db, monkeypatch):
    _allow_license_features(monkeypatch, ["automation_hub"])
    site = Site(name="HQ", type="campus")
    db.add(site)
    db.commit()
    db.refresh(site)

    core = Device(
        name="core-sw-01",
        hostname="core-sw-01",
        ip_address="10.0.0.1",
        serial_number="SER-100",
        role="core",
        device_type="cisco_ios",
        status="online",
        management_state="managed",
        site_id=int(site.id),
    )
    edge = Device(
        name="edge-sw-02",
        ip_address="10.0.0.2",
        role="access",
        device_type="dasan_nos",
        status="offline",
        management_state="discovered_only",
    )
    account = CloudAccount(
        name="aws-prod",
        provider="aws",
        credentials={"access_key": "masked", "secret_key": "masked"},
        is_active=True,
    )
    db.add_all([core, edge, account])
    db.commit()
    db.refresh(core)
    db.refresh(edge)
    db.refresh(account)

    resource = CloudResource(
        account_id=int(account.id),
        resource_id="vpc-001",
        resource_type="vpc",
        name="core-vpc",
        region="ap-northeast-2",
        state="available",
    )
    group = ServiceGroup(
        name="public-service",
        criticality="high",
        owner_team="InfraOps",
        color="#0ea5e9",
    )
    db.add_all([resource, group])
    db.commit()
    db.refresh(resource)
    db.refresh(group)

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

    create_group = client.post(
        "/api/v1/service-groups/",
        json={
            "name": "branch-ops",
            "description": "Branch operating service group",
            "criticality": "elevated",
            "owner_team": "PlatformOps",
            "color": "#22c55e",
            "is_active": True,
        },
        headers=operator_user_token,
    )
    assert create_group.status_code == 200

    summary_res = client.get("/api/v1/automation-hub/source-of-truth/summary", headers=admin_user_token)
    assert summary_res.status_code == 200
    payload = _unwrap(summary_res.json())

    assert payload["metrics"]["devices_total"] == 2
    assert payload["metrics"]["managed_devices"] == 1
    assert payload["metrics"]["discovered_only_devices"] == 1
    assert payload["metrics"]["cloud_accounts_total"] == 1
    assert payload["metrics"]["cloud_resources_total"] == 1
    assert payload["metrics"]["service_groups_total"] == 2
    assert payload["coverage"]["devices_with_site"] == 1
    assert payload["coverage"]["devices_with_hostname"] == 1
    assert payload["coverage"]["devices_with_serial"] == 1
    assert payload["coverage"]["service_groups_with_owner"] == 2
    assert payload["coverage"]["cloud_resources_mapped_to_services"] == 1
    assert any(row["key"] == "core" for row in payload["distributions"]["device_roles"])
    assert any(row["key"] == "aws" for row in payload["distributions"]["cloud_providers"])
    assert any(str(row["action"]) == "created" for row in payload["recent_changes"])


def test_source_of_truth_recent_changes_include_cloud_and_profile_events(client, admin_user_token, operator_user_token, db, monkeypatch):
    _allow_license_features(monkeypatch, ["automation_hub", "cloud"])
    device = Device(
        name="dist-sw-10",
        ip_address="10.10.10.10",
        role="distribution",
        device_type="cisco_ios",
        status="online",
        management_state="managed",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    catalog = client.get("/api/v1/monitoring-profiles/catalog", headers=operator_user_token)
    assert catalog.status_code == 200
    profiles = _unwrap(catalog.json())["profiles"]
    general = next(row for row in profiles if str(row["key"]) == "general-managed")

    create_account = client.post(
        "/api/v1/cloud/accounts",
        json={
            "name": "azure-ops",
            "provider": "azure",
            "credentials": {
                "tenant_id": "tenant-1",
                "subscription_id": "subscription-1",
                "client_id": "client-1",
                "client_secret": "secret-1",
            },
            "is_active": True,
        },
        headers=admin_user_token,
    )
    assert create_account.status_code == 200

    assign_profile = client.post(
        f"/api/v1/monitoring-profiles/devices/{int(device.id)}/assign",
        json={"profile_id": int(general["id"])},
        headers=operator_user_token,
    )
    assert assign_profile.status_code == 200

    summary_res = client.get("/api/v1/automation-hub/source-of-truth/summary", headers=admin_user_token)
    assert summary_res.status_code == 200
    payload = _unwrap(summary_res.json())

    actions = {(row["asset_kind"], row["action"]) for row in payload["recent_changes"]}
    assert ("cloud_account", "created") in actions
    assert ("device", "profile_assigned") in actions
