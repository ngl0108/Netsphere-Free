from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.device import Device
from app.services.license_service import LicenseService


@dataclass
class LicensePolicyViolation(Exception):
    message: str
    code: str = "license_policy_blocked"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class LicensePolicyService:
    """
    Central policy service for license-based runtime gates.
    """

    FREE_TIER_MAX_DEVICES = 100

    @staticmethod
    def current_device_count(db: Session) -> int:
        return int(db.query(Device).count())

    @staticmethod
    def assert_can_add_devices(db: Session, *, additional_devices: int = 1, source: str = "runtime") -> dict:
        add_count = max(0, int(additional_devices or 0))
        if add_count <= 0:
            return {"allowed": True, "device_count": LicensePolicyService.current_device_count(db)}

        current_count = LicensePolicyService.current_device_count(db)
        target_count = current_count + add_count
        lic = LicenseService.get_effective_license(db)

        if lic:
            if not bool(lic.is_valid):
                raise LicensePolicyViolation(
                    message=f"License invalid: {lic.status} (source={source})",
                    code="license_invalid",
                )
            max_devices = int(getattr(lic, "max_devices", 0) or 0)
            if max_devices <= 0:
                raise LicensePolicyViolation(
                    message=f"License does not permit device onboarding (max_devices={max_devices}, source={source})",
                    code="license_limit_invalid",
                )
            if target_count > max_devices:
                raise LicensePolicyViolation(
                    message=(
                        f"License limit reached ({max_devices} devices max). "
                        f"current={current_count} requested={add_count} source={source}"
                    ),
                    code="license_limit_reached",
                )
            return {
                "allowed": True,
                "device_count": current_count,
                "target_count": target_count,
                "max_devices": max_devices,
                "license_status": str(getattr(lic, "status", "unknown")),
            }

        # No installed/effective license -> free tier fallback.
        free_limit = int(LicensePolicyService.FREE_TIER_MAX_DEVICES)
        if target_count > free_limit:
            raise LicensePolicyViolation(
                message=(
                    f"No license found. Free tier limit ({free_limit}) reached. "
                    f"current={current_count} requested={add_count} source={source}"
                ),
                code="free_tier_limit_reached",
            )
        return {
            "allowed": True,
            "device_count": current_count,
            "target_count": target_count,
            "max_devices": free_limit,
            "license_status": "free_tier",
        }
