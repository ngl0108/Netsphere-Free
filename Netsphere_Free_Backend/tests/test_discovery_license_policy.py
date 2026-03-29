import pytest

from app.models.discovery import DiscoveredDevice, DiscoveryJob
from app.services.discovery_service import DiscoveryService
from app.services.license_policy_service import LicensePolicyService, LicensePolicyViolation


def test_discovery_approve_is_blocked_by_license_policy_and_marks_issue(db, monkeypatch):
    job = DiscoveryJob(cidr="10.0.0.0/24", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.flush()
    discovered = DiscoveredDevice(
        job_id=job.id,
        ip_address="10.0.0.50",
        hostname="edge-50",
        vendor="Cisco",
        status="new",
        snmp_status="reachable",
        issues=[],
    )
    db.add(discovered)
    db.commit()
    db.refresh(discovered)

    def _deny(*args, **kwargs):
        raise LicensePolicyViolation(message="license denied for discovery", code="license_limit_reached")

    monkeypatch.setattr(LicensePolicyService, "assert_can_add_devices", staticmethod(_deny))

    svc = DiscoveryService(db)
    with pytest.raises(LicensePolicyViolation):
        svc.approve_device(discovered.id)

    db.refresh(discovered)
    assert discovered.status == "new"
    assert isinstance(discovered.issues, list)
    assert any(str(x.get("code")) == "license_policy_blocked" for x in discovered.issues)
