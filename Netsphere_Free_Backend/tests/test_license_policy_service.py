from datetime import datetime, timedelta, timezone

import pytest

from app.core.license import LicenseSchema
from app.models.device import Device
from app.services.license_policy_service import LicensePolicyService, LicensePolicyViolation
from app.services.license_service import LicenseService


def _seed_devices(db, count: int) -> None:
    for i in range(int(count)):
        db.add(
            Device(
                name=f"dev-{i}",
                ip_address=f"10.{i // 250}.{(i // 25) % 250}.{(i % 25) + 1}",
                device_type="cisco_ios",
                status="online",
                owner_id=1,
            )
        )
    db.commit()


def test_free_tier_limit_is_enforced_without_license(db, monkeypatch):
    monkeypatch.setattr(LicenseService, "get_effective_license", staticmethod(lambda _db: None))
    _seed_devices(db, LicensePolicyService.FREE_TIER_MAX_DEVICES)

    with pytest.raises(LicensePolicyViolation) as exc_info:
        LicensePolicyService.assert_can_add_devices(db, source="unit_test_free_tier")

    assert exc_info.value.code == "free_tier_limit_reached"


def test_installed_license_limit_is_enforced(db, monkeypatch):
    _seed_devices(db, 2)
    lic = LicenseSchema(
        customer="ACME",
        expiration=datetime.now(timezone.utc) + timedelta(days=1),
        max_devices=2,
        features=["all"],
        is_valid=True,
        status="Active",
    )
    monkeypatch.setattr(LicenseService, "get_effective_license", staticmethod(lambda _db: lic))

    with pytest.raises(LicensePolicyViolation) as exc_info:
        LicensePolicyService.assert_can_add_devices(db, source="unit_test_license")

    assert exc_info.value.code == "license_limit_reached"
