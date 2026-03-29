from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.settings import SystemSetting


class ChangePolicyService:
    TEMPLATE_DIRECT_MAX_DEVICES_KEY = "change_policy_template_direct_max_devices"
    COMPLIANCE_DIRECT_MAX_DEVICES_KEY = "change_policy_compliance_direct_max_devices"
    FABRIC_LIVE_REQUIRES_APPROVAL_KEY = "change_policy_fabric_live_requires_approval"
    CLOUD_BOOTSTRAP_LIVE_REQUIRES_APPROVAL_KEY = "change_policy_cloud_bootstrap_live_requires_approval"
    CONFIG_DRIFT_APPROVAL_ENABLED_KEY = "config_drift_approval_enabled"

    @staticmethod
    def _get_setting(db: Session, key: str, default: str) -> str:
        try:
            row = db.query(SystemSetting).filter(SystemSetting.key == str(key)).first()
            if row is None or row.value is None:
                return str(default)
            return str(row.value)
        except Exception:
            return str(default)

    @staticmethod
    def _parse_bool(value: str, default: bool) -> bool:
        t = str(value or "").strip().lower()
        if not t:
            return bool(default)
        if t in {"1", "true", "yes", "y", "on"}:
            return True
        if t in {"0", "false", "no", "n", "off"}:
            return False
        return bool(default)

    @staticmethod
    def _parse_int(value: str, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    @staticmethod
    def template_direct_max_devices(db: Session) -> int:
        raw = ChangePolicyService._get_setting(
            db,
            ChangePolicyService.TEMPLATE_DIRECT_MAX_DEVICES_KEY,
            "3",
        )
        out = ChangePolicyService._parse_int(raw, 3)
        return max(0, int(out))

    @staticmethod
    def compliance_direct_max_devices(db: Session) -> int:
        raw = ChangePolicyService._get_setting(
            db,
            ChangePolicyService.COMPLIANCE_DIRECT_MAX_DEVICES_KEY,
            "3",
        )
        out = ChangePolicyService._parse_int(raw, 3)
        return max(0, int(out))

    @staticmethod
    def config_drift_approval_enabled(db: Session) -> bool:
        raw = ChangePolicyService._get_setting(
            db,
            ChangePolicyService.CONFIG_DRIFT_APPROVAL_ENABLED_KEY,
            "false",
        )
        return ChangePolicyService._parse_bool(raw, False)

    @staticmethod
    def requires_template_approval(
        db: Session,
        *,
        target_count: int,
        approval_id: int | None,
    ) -> bool:
        if approval_id is not None:
            return False
        max_direct = ChangePolicyService.template_direct_max_devices(db)
        return int(target_count or 0) > int(max_direct)

    @staticmethod
    def requires_compliance_remediate_approval(
        db: Session,
        *,
        target_count: int,
        approval_id: int | None,
    ) -> bool:
        if approval_id is not None:
            return False
        if int(target_count or 0) <= 0:
            return False
        if ChangePolicyService.config_drift_approval_enabled(db):
            return True
        max_direct = ChangePolicyService.compliance_direct_max_devices(db)
        return int(target_count or 0) > int(max_direct)

    @staticmethod
    def fabric_live_requires_approval(db: Session) -> bool:
        raw = ChangePolicyService._get_setting(
            db,
            ChangePolicyService.FABRIC_LIVE_REQUIRES_APPROVAL_KEY,
            "true",
        )
        return ChangePolicyService._parse_bool(raw, True)

    @staticmethod
    def requires_fabric_live_approval(
        db: Session,
        *,
        dry_run: bool,
        approval_id: int | None,
    ) -> bool:
        if bool(dry_run):
            return False
        if approval_id is not None:
            return False
        return ChangePolicyService.fabric_live_requires_approval(db)

    @staticmethod
    def cloud_bootstrap_live_requires_approval(db: Session) -> bool:
        raw = ChangePolicyService._get_setting(
            db,
            ChangePolicyService.CLOUD_BOOTSTRAP_LIVE_REQUIRES_APPROVAL_KEY,
            "true",
        )
        return ChangePolicyService._parse_bool(raw, True)

    @staticmethod
    def requires_cloud_bootstrap_live_approval(
        db: Session,
        *,
        dry_run: bool,
        approval_id: int | None,
    ) -> bool:
        if bool(dry_run):
            return False
        if approval_id is not None:
            return False
        return ChangePolicyService.cloud_bootstrap_live_requires_approval(db)
