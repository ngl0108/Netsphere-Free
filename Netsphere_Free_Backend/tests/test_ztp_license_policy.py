import pytest

from app.models.ztp_queue import ZtpQueue, ZtpStatus
from app.services.license_policy_service import LicensePolicyService, LicensePolicyViolation
from app.services.ztp_service import ZtpService


def test_ztp_complete_provisioning_is_blocked_by_license_policy(db, monkeypatch):
    q = ZtpQueue(
        serial_number="SN123456",
        platform="C9300",
        software_version="17.9.3",
        ip_address="10.10.10.10",
        hostname="ztp-new",
        status=ZtpStatus.PROVISIONING.value,
        target_hostname="ztp-new",
    )
    db.add(q)
    db.commit()
    db.refresh(q)

    def _deny(*args, **kwargs):
        raise LicensePolicyViolation(message="license denied for ztp", code="license_limit_reached")

    monkeypatch.setattr(LicensePolicyService, "assert_can_add_devices", staticmethod(_deny))

    with pytest.raises(LicensePolicyViolation):
        ZtpService(db).complete_provisioning(q)

    db.refresh(q)
    assert q.status == ZtpStatus.ERROR.value
    assert "License policy blocked" in str(q.last_message or "")
