from datetime import datetime, timedelta, timezone

from app.core.license import LicenseSchema
from app.models.device import Device
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.user import User
from app.services.license_policy_service import LicensePolicyService, LicensePolicyViolation
from app.services.license_service import LicenseService


def _deny(*args, **kwargs):
    raise LicensePolicyViolation(message="license policy denied", code="license_limit_reached")


def _error_message(res) -> str:
    body = res.json()
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else {}
        return str(err.get("message") or body.get("detail") or "")
    return ""


def test_manual_device_create_path_is_blocked_when_license_policy_denies(client, admin_user_token, monkeypatch):
    monkeypatch.setattr(LicensePolicyService, "assert_can_add_devices", staticmethod(_deny))
    payload = {
        "name": "blocked-device",
        "ip_address": "10.50.50.10",
        "device_type": "cisco_ios",
        "snmp_community": "public",
    }
    res = client.post("/api/v1/devices/", json=payload, headers=admin_user_token)
    assert res.status_code == 403
    assert "license policy denied" in _error_message(res).lower()


def test_discovery_approve_path_is_blocked_when_license_policy_denies(
    client,
    operator_user_token,
    db,
    monkeypatch,
):
    job = DiscoveryJob(cidr="10.0.0.0/24", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.flush()
    discovered = DiscoveredDevice(
        job_id=job.id,
        ip_address="10.0.0.90",
        hostname="edge-90",
        vendor="Cisco",
        status="new",
        snmp_status="reachable",
        issues=[],
    )
    db.add(discovered)
    db.commit()

    monkeypatch.setattr(LicensePolicyService, "assert_can_add_devices", staticmethod(_deny))
    res = client.post(f"/api/v1/discovery/approve/{discovered.id}", headers=operator_user_token)
    assert res.status_code == 403
    assert "license policy denied" in _error_message(res).lower()


def test_cloud_hybrid_api_path_is_blocked_when_license_policy_denies(
    client,
    admin_user_token,
    db,
    monkeypatch,
):
    admin_user = db.query(User).filter(User.username == "adminuser").first()
    db.add(
        Device(
            name="r-cloud",
            ip_address="10.0.0.5",
            owner_id=int(admin_user.id),
            device_type="cisco_ios",
            latest_parsed_data={
                "l3_routing": {"bgp_neighbors": [{"neighbor_ip": "8.8.8.8", "state": "Established"}]}
            },
        )
    )
    db.commit()

    monkeypatch.setattr(
        LicenseService,
        "get_effective_license",
        staticmethod(
            lambda _db: LicenseSchema(
                customer="ACME",
                expiration=datetime.now(timezone.utc) + timedelta(days=30),
                max_devices=1000,
                features=["cloud"],
                is_valid=True,
                status="Active",
            )
        ),
    )
    monkeypatch.setattr(LicensePolicyService, "assert_can_add_devices", staticmethod(_deny))
    res = client.post("/api/v1/cloud/hybrid/infer", headers=admin_user_token)
    assert res.status_code == 403
    assert "license policy denied" in _error_message(res).lower()
