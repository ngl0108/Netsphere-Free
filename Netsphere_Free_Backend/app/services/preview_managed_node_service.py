from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.settings import SystemSetting


class PreviewManagedNodeService:
    MANAGED_NODE_LIMIT = 50

    STATE_MANAGED = "managed"
    STATE_DISCOVERED_ONLY = "discovered_only"

    REASON_AUTO_SELECTED = "auto_selected"
    REASON_USER_SELECTED = "user_selected"
    REASON_USER_RELEASED = "user_released"
    REASON_EDITION_LIMIT = "edition_limit"

    @classmethod
    def _utcnow(cls) -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def is_preview_managed_quota_enabled(cls, db: Session) -> bool:
        values = {
            row.key: str(row.value or "").strip()
            for row in db.query(SystemSetting)
            .filter(SystemSetting.key.in_(["product_edition", "preview_deployment_role"]))
            .all()
        }
        edition = str(values.get("product_edition") or "enterprise").strip().lower()
        deployment_role = str(values.get("preview_deployment_role") or "standalone").strip().lower()
        if deployment_role == "collector":
            deployment_role = "collector_installed"
        return edition == "preview" and deployment_role != "intake_server"

    @classmethod
    def get_managed_node_limit(cls, db: Session) -> Optional[int]:
        if not cls.is_preview_managed_quota_enabled(db):
            return None
        return int(cls.MANAGED_NODE_LIMIT)

    @classmethod
    def is_managed_device(cls, device: Optional[Device]) -> bool:
        return bool(device and str(getattr(device, "management_state", "") or "").strip().lower() == cls.STATE_MANAGED)

    @classmethod
    def _eligible_devices(cls, db: Session) -> List[Device]:
        return (
            db.query(Device)
            .filter(Device.device_type != "cloud_virtual")
            .order_by(Device.id.asc())
            .all()
        )

    @classmethod
    def _compute_priority(cls, device: Device) -> float:
        score = 0.0
        role = str(getattr(device, "role", "") or "").strip().lower()
        status = str(getattr(device, "status", "") or "").strip().lower()
        reachability = str(getattr(device, "reachability_status", "") or "").strip().lower()
        variables = getattr(device, "variables", None) or {}
        if not isinstance(variables, dict):
            variables = {}

        if variables.get("management_pinned") is True:
            score += 500.0
        if variables.get("discovery_seed") is True:
            score += 250.0

        if role == "core":
            score += 120.0
        elif role in {"distribution", "security", "wlc"}:
            score += 90.0
        elif role in {"router", "access_domestic"}:
            score += 60.0
        else:
            score += 30.0

        if status == "online":
            score += 40.0
        elif reachability == "reachable":
            score += 20.0

        if getattr(device, "site_id", None):
            score += 10.0
        if getattr(device, "last_seen", None):
            score += 5.0

        latest_parsed_data = getattr(device, "latest_parsed_data", None) or {}
        if isinstance(latest_parsed_data, dict):
            if latest_parsed_data.get("wireless"):
                score += 15.0
            if latest_parsed_data.get("bgp_summary"):
                score += 20.0
            if latest_parsed_data.get("ospf_neighbors"):
                score += 20.0

        return score

    @classmethod
    def _apply_state(
        cls,
        device: Device,
        *,
        state: str,
        reason: Optional[str],
        score: float,
    ) -> None:
        device.management_state = state
        device.management_reason = reason
        device.management_priority_score = float(score)
        if state == cls.STATE_MANAGED:
            if device.managed_since is None:
                device.managed_since = cls._utcnow()
        else:
            device.managed_since = None

    @classmethod
    def reconcile_managed_devices(cls, db: Session, *, commit: bool = True) -> Dict[str, int]:
        if not cls.is_preview_managed_quota_enabled(db):
            return cls.summarize(db)

        limit = int(cls.get_managed_node_limit(db) or 0)
        devices = cls._eligible_devices(db)
        pinned: List[Device] = []
        blocked_ids = set()
        candidates: List[tuple[float, Device]] = []

        for device in devices:
            score = cls._compute_priority(device)
            device.management_priority_score = float(score)
            current_reason = str(getattr(device, "management_reason", "") or "").strip().lower()
            current_state = str(getattr(device, "management_state", "") or "").strip().lower()

            if current_reason == cls.REASON_USER_SELECTED and current_state == cls.STATE_MANAGED:
                pinned.append(device)
                continue
            if current_reason == cls.REASON_USER_RELEASED and current_state != cls.STATE_MANAGED:
                blocked_ids.add(int(device.id))
                cls._apply_state(
                    device,
                    state=cls.STATE_DISCOVERED_ONLY,
                    reason=cls.REASON_USER_RELEASED,
                    score=score,
                )
                continue
            candidates.append((score, device))

        pinned = sorted(
            pinned,
            key=lambda device: (
                -(float(getattr(device, "management_priority_score", 0.0) or 0.0)),
                int(getattr(device, "id", 0) or 0),
            ),
        )[:limit]

        reserved_slots = min(len(blocked_ids), max(0, limit - len(pinned)))
        remaining_slots = max(0, limit - len(pinned) - reserved_slots)
        ranked_candidates = sorted(
            candidates,
            key=lambda item: (-float(item[0]), int(getattr(item[1], "id", 0) or 0)),
        )

        auto_selected_ids = {
            int(device.id)
            for _, device in ranked_candidates[:remaining_slots]
            if int(device.id) not in blocked_ids
        }

        for device in pinned:
            cls._apply_state(
                device,
                state=cls.STATE_MANAGED,
                reason=cls.REASON_USER_SELECTED,
                score=float(getattr(device, "management_priority_score", 0.0) or 0.0),
            )

        for score, device in ranked_candidates:
            device_id = int(device.id)
            if device_id in blocked_ids:
                continue
            if device_id in auto_selected_ids:
                cls._apply_state(
                    device,
                    state=cls.STATE_MANAGED,
                    reason=cls.REASON_AUTO_SELECTED,
                    score=score,
                )
            else:
                cls._apply_state(
                    device,
                    state=cls.STATE_DISCOVERED_ONLY,
                    reason=cls.REASON_EDITION_LIMIT,
                    score=score,
                )

        if commit:
            db.commit()
            for device in devices:
                db.refresh(device)
        return cls.summarize(db)

    @classmethod
    def summarize(cls, db: Session) -> Dict[str, int]:
        devices = cls._eligible_devices(db)
        managed = 0
        discovered_only = 0
        for device in devices:
            if cls.is_managed_device(device):
                managed += 1
            else:
                discovered_only += 1
        limit = cls.get_managed_node_limit(db)
        return {
            "managed_limit": int(limit or 0),
            "total_discovered": int(len(devices)),
            "managed": int(managed),
            "discovered_only": int(discovered_only),
            "remaining_slots": max(0, int(limit or 0) - int(managed)),
        }

    @classmethod
    def promote_device_to_managed(cls, db: Session, device: Device) -> Dict[str, int]:
        if not cls.is_preview_managed_quota_enabled(db):
            return cls.summarize(db)
        if cls.is_managed_device(device):
            return cls.summarize(db)

        summary = cls.summarize(db)
        if int(summary["remaining_slots"]) <= 0:
            raise ValueError("Managed node limit reached")

        score = cls._compute_priority(device) + 1000.0
        variables = getattr(device, "variables", None) or {}
        if not isinstance(variables, dict):
            variables = {}
        variables["management_pinned"] = True
        device.variables = variables
        cls._apply_state(
            device,
            state=cls.STATE_MANAGED,
            reason=cls.REASON_USER_SELECTED,
            score=score,
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        return cls.summarize(db)

    @classmethod
    def release_managed_slot(cls, db: Session, device: Device) -> Dict[str, int]:
        if not cls.is_preview_managed_quota_enabled(db):
            return cls.summarize(db)

        variables = getattr(device, "variables", None) or {}
        if not isinstance(variables, dict):
            variables = {}
        variables["management_pinned"] = False
        device.variables = variables
        cls._apply_state(
            device,
            state=cls.STATE_DISCOVERED_ONLY,
            reason=cls.REASON_USER_RELEASED,
            score=cls._compute_priority(device),
        )
        db.add(device)
        db.commit()
        db.refresh(device)
        return cls.summarize(db)

    @classmethod
    def assert_managed_for_feature(cls, db: Session, device: Optional[Device], *, feature: str) -> None:
        if not cls.is_preview_managed_quota_enabled(db):
            return
        if cls.is_managed_device(device):
            return
        summary = cls.summarize(db)
        raise PermissionError(
            {
                "code": "PREVIEW_MANAGED_NODE_LIMIT",
                "message": f"{feature} is available only for managed nodes in NetSphere Free.",
                "details": {
                    "feature": feature,
                    "device_id": int(getattr(device, "id", 0) or 0) if device else None,
                    "managed_limit": int(summary["managed_limit"]),
                    "managed": int(summary["managed"]),
                    "discovered_only": int(summary["discovered_only"]),
                    "remaining_slots": int(summary["remaining_slots"]),
                },
            }
        )
