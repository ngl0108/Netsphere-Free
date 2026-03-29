from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session, joinedload

from app.models.device import Device
from app.models.monitoring_profile import MonitoringProfile, MonitoringProfileAssignment
from app.schemas.monitoring_profile import MonitoringProfileDeviceSummary


class MonitoringProfileService:
    SCOPE_ANY = "any"
    SCOPE_MANAGED = "managed"
    SCOPE_DISCOVERED_ONLY = "discovered_only"

    SOURCE_AUTO = "auto"
    SOURCE_MANUAL = "manual"

    DEFAULT_PROFILES: List[Dict[str, Any]] = [
        {
            "key": "core-network",
            "name": "Core Network",
            "description": "High-priority switching and routing profile for core and distribution nodes.",
            "management_scope": "managed",
            "telemetry_mode": "hybrid",
            "polling_interval_override": 60,
            "status_interval_override": 60,
            "priority": 240,
            "match_roles": ["core", "distribution", "router"],
            "match_device_types": ["cisco_ios", "juniper_junos", "arista_eos", "huawei", "dell_os10"],
            "dashboard_tags": ["core", "routing", "critical"],
        },
        {
            "key": "access-network",
            "name": "Access Network",
            "description": "Balanced profile for access switching and domestic access platforms.",
            "management_scope": "managed",
            "telemetry_mode": "hybrid",
            "polling_interval_override": 120,
            "status_interval_override": 90,
            "priority": 180,
            "match_roles": ["access", "access_domestic"],
            "match_device_types": ["cisco_ios", "hp_procurve", "dasan_nos", "ubiquoss_l2", "handream_sg", "soltech_switch", "coreedge_switch", "nst_switch"],
            "dashboard_tags": ["access", "campus"],
        },
        {
            "key": "wireless-controller",
            "name": "Wireless Controller",
            "description": "Controller-oriented polling profile with wireless health emphasis.",
            "management_scope": "managed",
            "telemetry_mode": "hybrid",
            "polling_interval_override": 90,
            "status_interval_override": 60,
            "priority": 210,
            "match_roles": ["wlc"],
            "match_model_patterns": ["9800", "wireless"],
            "dashboard_tags": ["wireless", "controller"],
        },
        {
            "key": "security-edge",
            "name": "Security Edge",
            "description": "Security and edge devices with tighter status checks.",
            "management_scope": "managed",
            "telemetry_mode": "hybrid",
            "polling_interval_override": 90,
            "status_interval_override": 60,
            "priority": 200,
            "match_roles": ["security"],
            "match_device_types": ["fortinet"],
            "dashboard_tags": ["security", "edge"],
        },
        {
            "key": "discovered-light",
            "name": "Discovered Light",
            "description": "Low-touch recommendation for discovered-only assets before they are promoted into managed monitoring.",
            "management_scope": "discovered_only",
            "telemetry_mode": "snmp",
            "polling_interval_override": 300,
            "status_interval_override": 300,
            "priority": 120,
            "dashboard_tags": ["discovered", "free-tier"],
        },
        {
            "key": "general-managed",
            "name": "General Managed",
            "description": "Fallback profile for managed infrastructure when no vendor-specific profile is matched.",
            "management_scope": "managed",
            "telemetry_mode": "hybrid",
            "polling_interval_override": 180,
            "status_interval_override": 120,
            "priority": 100,
            "dashboard_tags": ["default", "managed"],
        },
    ]

    @classmethod
    def _normalize_text_list(cls, values: Any) -> List[str]:
        if not isinstance(values, Iterable) or isinstance(values, (str, bytes, dict)):
            return []
        out: List[str] = []
        for value in values:
            item = str(value or "").strip().lower()
            if item and item not in out:
                out.append(item)
        return out

    @classmethod
    def _normalize_int_list(cls, values: Any) -> List[int]:
        if not isinstance(values, Iterable) or isinstance(values, (str, bytes, dict)):
            return []
        out: List[int] = []
        for value in values:
            try:
                item = int(value)
            except Exception:
                continue
            if item not in out:
                out.append(item)
        return out

    @classmethod
    def _normalize_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = dict(payload or {})
        data["key"] = str(data.get("key") or "").strip().lower().replace(" ", "-")
        data["name"] = str(data.get("name") or "").strip()
        data["description"] = str(data.get("description") or "").strip() or None
        scope = str(data.get("management_scope") or cls.SCOPE_MANAGED).strip().lower()
        if scope not in {cls.SCOPE_ANY, cls.SCOPE_MANAGED, cls.SCOPE_DISCOVERED_ONLY}:
            scope = cls.SCOPE_MANAGED
        data["management_scope"] = scope
        telemetry = str(data.get("telemetry_mode") or "hybrid").strip().lower()
        if telemetry not in {"hybrid", "snmp", "ssh", "gnmi"}:
            telemetry = "hybrid"
        data["telemetry_mode"] = telemetry
        data["priority"] = int(data.get("priority") or 100)
        data["is_active"] = bool(data.get("is_active", True))
        data["match_device_types"] = cls._normalize_text_list(data.get("match_device_types"))
        data["match_roles"] = cls._normalize_text_list(data.get("match_roles"))
        data["match_vendor_patterns"] = cls._normalize_text_list(data.get("match_vendor_patterns"))
        data["match_model_patterns"] = cls._normalize_text_list(data.get("match_model_patterns"))
        data["match_site_ids"] = cls._normalize_int_list(data.get("match_site_ids"))
        data["dashboard_tags"] = cls._normalize_text_list(data.get("dashboard_tags"))
        for key in ("polling_interval_override", "status_interval_override"):
            try:
                data[key] = int(data.get(key)) if data.get(key) is not None else None
            except Exception:
                data[key] = None
        return data

    @classmethod
    def install_defaults(cls, db: Session) -> Dict[str, int]:
        installed = 0
        changed = False
        available = len(cls.DEFAULT_PROFILES)
        for payload in cls.DEFAULT_PROFILES:
            normalized = cls._normalize_payload(payload)
            existing = db.query(MonitoringProfile).filter(MonitoringProfile.key == normalized["key"]).first()
            if existing is None:
                db.add(MonitoringProfile(**normalized))
                installed += 1
                changed = True
                continue
            row_changed = False
            for key, value in normalized.items():
                if getattr(existing, key) != value:
                    setattr(existing, key, value)
                    row_changed = True
            if row_changed:
                db.add(existing)
                changed = True
        if changed:
            db.commit()
        else:
            db.flush()
        return {"installed": int(installed), "available": int(available)}

    @classmethod
    def list_profiles(cls, db: Session) -> List[MonitoringProfile]:
        return db.query(MonitoringProfile).order_by(MonitoringProfile.priority.desc(), MonitoringProfile.name.asc()).all()

    @classmethod
    def get_profile(cls, db: Session, profile_id: int) -> Optional[MonitoringProfile]:
        return db.query(MonitoringProfile).filter(MonitoringProfile.id == int(profile_id)).first()

    @classmethod
    def create_profile(cls, db: Session, payload: Dict[str, Any]) -> MonitoringProfile:
        profile = MonitoringProfile(**cls._normalize_payload(payload))
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile

    @classmethod
    def update_profile(cls, db: Session, profile: MonitoringProfile, payload: Dict[str, Any]) -> MonitoringProfile:
        changes = cls._normalize_payload({**profile.__dict__, **payload})
        for key, value in changes.items():
            setattr(profile, key, value)
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile

    @classmethod
    def delete_profile(cls, db: Session, profile: MonitoringProfile) -> None:
        db.delete(profile)
        db.commit()

    @classmethod
    def _matches_scope(cls, profile: MonitoringProfile, device: Device) -> bool:
        scope = str(getattr(profile, "management_scope", cls.SCOPE_MANAGED) or cls.SCOPE_MANAGED).strip().lower()
        is_managed = str(getattr(device, "management_state", "managed") or "managed").strip().lower() == "managed"
        if scope == cls.SCOPE_ANY:
            return True
        if scope == cls.SCOPE_MANAGED:
            return is_managed
        if scope == cls.SCOPE_DISCOVERED_ONLY:
            return not is_managed
        return False

    @classmethod
    def _score_profile(cls, profile: MonitoringProfile, device: Device) -> Tuple[float, List[str]]:
        if not bool(getattr(profile, "is_active", True)):
            return -1.0, []
        if not cls._matches_scope(profile, device):
            return -1.0, []

        score = 0.0
        reasons: List[str] = []
        role = str(getattr(device, "role", "") or "").strip().lower()
        device_type = str(getattr(device, "device_type", "") or "").strip().lower()
        model = str(getattr(device, "model", "") or "").strip().lower()
        os_version = str(getattr(device, "os_version", "") or "").strip().lower()
        variables = getattr(device, "variables", None) or {}
        if not isinstance(variables, dict):
            variables = {}
        support = variables.get("support_policy") if isinstance(variables.get("support_policy"), dict) else {}
        tier = str(support.get("tier") or "").strip().lower()

        if str(getattr(device, "management_state", "managed") or "managed").strip().lower() == "managed":
            score += 20.0
            reasons.append("managed_scope")
        else:
            score += 8.0
            reasons.append("discovered_scope")

        if device_type and device_type in set(cls._normalize_text_list(profile.match_device_types)):
            score += 55.0
            reasons.append("device_type")
        if role and role in set(cls._normalize_text_list(profile.match_roles)):
            score += 45.0
            reasons.append("role")
        if getattr(device, "site_id", None) in set(cls._normalize_int_list(profile.match_site_ids)):
            score += 20.0
            reasons.append("site")

        for pattern in cls._normalize_text_list(profile.match_model_patterns):
            if pattern and (pattern in model or pattern in os_version):
                score += 20.0
                reasons.append(f"model:{pattern}")
                break

        vendor_hints = " ".join(
            [
                device_type,
                model,
                os_version,
                str(getattr(device, "hostname", "") or "").strip().lower(),
                str(tier or ""),
            ]
        )
        for pattern in cls._normalize_text_list(profile.match_vendor_patterns):
            if pattern and pattern in vendor_hints:
                score += 18.0
                reasons.append(f"vendor:{pattern}")
                break

        score += min(max(float(getattr(profile, "priority", 100) or 100), 0.0), 400.0) / 10.0
        return score, reasons

    @classmethod
    def recommend_profile(cls, db: Session, device: Device) -> Optional[Tuple[MonitoringProfile, float, List[str]]]:
        profiles = cls.list_profiles(db)
        best: Optional[Tuple[MonitoringProfile, float, List[str]]] = None
        for profile in profiles:
            score, reasons = cls._score_profile(profile, device)
            if score < 0:
                continue
            if best is None or score > best[1]:
                best = (profile, score, reasons)
        return best

    @classmethod
    def get_assignment(cls, db: Session, device_id: int) -> Optional[MonitoringProfileAssignment]:
        return (
            db.query(MonitoringProfileAssignment)
            .options(joinedload(MonitoringProfileAssignment.profile))
            .filter(MonitoringProfileAssignment.device_id == int(device_id))
            .first()
        )

    @classmethod
    def ensure_assignment(cls, db: Session, device: Device, *, commit: bool = False) -> Optional[MonitoringProfileAssignment]:
        existing = cls.get_assignment(db, int(device.id))
        if existing is not None and str(existing.assignment_source or "").strip().lower() == cls.SOURCE_MANUAL:
            return existing

        recommendation = cls.recommend_profile(db, device)
        if recommendation is None:
            return existing
        profile, confidence, reasons = recommendation

        if existing is None:
            existing = MonitoringProfileAssignment(
                device_id=int(device.id),
                profile_id=int(profile.id),
                assignment_source=cls.SOURCE_AUTO,
                confidence=float(confidence),
                recommendation_reasons=list(reasons),
            )
        else:
            existing.profile_id = int(profile.id)
            existing.assignment_source = cls.SOURCE_AUTO
            existing.confidence = float(confidence)
            existing.recommendation_reasons = list(reasons)

        db.add(existing)
        if commit:
            db.commit()
            db.refresh(existing)
        else:
            db.flush()
        if existing.profile is None:
            existing.profile = profile
        return existing

    @classmethod
    def assign_profile(
        cls,
        db: Session,
        *,
        device: Device,
        profile: MonitoringProfile,
        source: str = SOURCE_MANUAL,
    ) -> MonitoringProfileAssignment:
        existing = cls.get_assignment(db, int(device.id))
        score, reasons = cls._score_profile(profile, device)
        confidence = max(float(score), 1.0)
        if existing is None:
            existing = MonitoringProfileAssignment(device_id=int(device.id), profile_id=int(profile.id))
        existing.profile_id = int(profile.id)
        existing.assignment_source = str(source or cls.SOURCE_MANUAL).strip().lower() or cls.SOURCE_MANUAL
        existing.confidence = float(confidence)
        existing.recommendation_reasons = list(reasons) or ["manual_override"]
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    @classmethod
    def build_device_summary(cls, db: Session, device: Optional[Device]) -> Optional[MonitoringProfileDeviceSummary]:
        if device is None or getattr(device, "id", None) is None:
            return None
        assignment = cls.get_assignment(db, int(device.id))
        profile = assignment.profile if assignment is not None else None
        confidence = float(getattr(assignment, "confidence", 0.0) or 0.0)
        reasons = [
            str(item or "")
            for item in list(getattr(assignment, "recommendation_reasons", None) or [])
            if str(item or "").strip()
        ]
        assignment_source = str(getattr(assignment, "assignment_source", cls.SOURCE_AUTO) or cls.SOURCE_AUTO)

        if profile is None:
            recommendation = cls.recommend_profile(db, device)
            if recommendation is None:
                return None
            profile, confidence, reasons = recommendation
            assignment_source = cls.SOURCE_AUTO

        if profile is None:
            return None

        is_managed = str(getattr(device, "management_state", "managed") or "managed").strip().lower() == "managed"
        activation_state = "active"
        scope = str(getattr(profile, "management_scope", cls.SCOPE_MANAGED) or cls.SCOPE_MANAGED).strip().lower()
        if scope == cls.SCOPE_DISCOVERED_ONLY and is_managed:
            activation_state = "standby"
        elif scope == cls.SCOPE_MANAGED and not is_managed:
            activation_state = "ready_when_managed"

        effective_polling = (
            int(profile.polling_interval_override)
            if profile.polling_interval_override is not None
            else int(getattr(device, "polling_interval", 0) or 0)
        )
        effective_status = (
            int(profile.status_interval_override)
            if profile.status_interval_override is not None
            else int(getattr(device, "status_interval", 0) or 0)
        )
        return MonitoringProfileDeviceSummary(
            profile_id=int(profile.id),
            key=str(profile.key or ""),
            name=str(profile.name or ""),
            assignment_source=assignment_source,
            confidence=round(float(confidence or 0.0), 2),
            management_scope=str(profile.management_scope or cls.SCOPE_MANAGED),
            telemetry_mode=str(profile.telemetry_mode or "hybrid"),
            polling_interval_override=int(effective_polling or 0) or None,
            status_interval_override=int(effective_status or 0) or None,
            dashboard_tags=cls._normalize_text_list(profile.dashboard_tags),
            recommendation_reasons=reasons,
            activation_state=activation_state,
            policy_summary={
                "managed_state": str(getattr(device, "management_state", "managed") or "managed"),
                "site_id": getattr(device, "site_id", None),
                "device_type": str(getattr(device, "device_type", "") or ""),
                "role": str(getattr(device, "role", "") or ""),
            },
        )

    @classmethod
    def build_catalog(cls, db: Session) -> Dict[str, Any]:
        profiles = cls.list_profiles(db)
        assignments = db.query(MonitoringProfileAssignment).all()
        assigned_by_profile: Dict[int, int] = {}
        manual_assignments = 0
        for assignment in assignments:
            assigned_by_profile[int(assignment.profile_id)] = assigned_by_profile.get(int(assignment.profile_id), 0) + 1
            if str(assignment.assignment_source or "").strip().lower() == cls.SOURCE_MANUAL:
                manual_assignments += 1
        devices = db.query(Device).all()
        managed = sum(1 for device in devices if str(getattr(device, "management_state", "managed") or "managed").strip().lower() == "managed")
        return {
            "profiles": [
                {
                    **{column.name: getattr(profile, column.name) for column in profile.__table__.columns},
                    "assigned_devices": int(assigned_by_profile.get(int(profile.id), 0)),
                }
                for profile in profiles
            ],
            "coverage": {
                "total_devices": int(len(devices)),
                "managed_devices": int(managed),
                "assigned_devices": int(len(assignments)),
                "manual_overrides": int(manual_assignments),
                "active_profiles": int(sum(1 for profile in profiles if bool(profile.is_active))),
            },
        }
