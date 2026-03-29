from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.settings import SystemSetting
from app.services.capability_profile_service import CapabilityProfileService
from app.services.rollback_strategy_service import RollbackStrategyService


REPO_ROOT = Path(__file__).resolve().parents[3]
VENDOR_MATRIX_JSON_PATH = REPO_ROOT / "docs" / "reports" / "vendor-support-matrix.latest.json"


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _norm_text(value: Any) -> str:
    return str(value or "").strip().lower()


class DeviceSupportPolicyService:
    """
    Central vendor support tier policy:
    - Reads fixture-derived support matrix (device_type readiness).
    - Applies optional vendor/os/version overrides from settings.
    - Produces per-device feature gates and read-only fallback mode.
    """

    SETTING_KEY = "vendor_support_policy_json"

    DEFAULT_POLICY: Dict[str, Any] = {
        "default_tier": "unsupported",
        "matrix_readiness_tier": {
            "full": "official",
            "extended": "limited",
            "basic": "limited",
            "partial": "limited",
            "none": "unsupported",
        },
        "tiers": {
            "official": {
                "discovery": True,
                "sync": True,
                "ztp": True,
                "config": True,
                "rollback": True,
            },
            "limited": {
                "discovery": True,
                "sync": True,
                "ztp": True,
                "config": True,
                "rollback": True,
            },
            "unsupported": {
                "discovery": True,
                "sync": True,
                "ztp": False,
                "config": False,
                "rollback": False,
            },
        },
        "overrides": [],
    }

    _matrix_cache_payload: Dict[str, Any] | None = None
    _matrix_cache_mtime: float | None = None

    @staticmethod
    def _clone_default_policy() -> Dict[str, Any]:
        return json.loads(json.dumps(DeviceSupportPolicyService.DEFAULT_POLICY))

    @staticmethod
    def _normalize_features(raw: Any, *, fallback: Dict[str, bool]) -> Dict[str, bool]:
        out = {k: bool(v) for k, v in dict(fallback or {}).items()}
        if not isinstance(raw, dict):
            return out
        for key in ("discovery", "sync", "ztp", "config", "rollback"):
            if key in raw:
                out[key] = _to_bool(raw.get(key), default=out.get(key, False))
        return out

    @staticmethod
    def _normalize_policy(raw: Any) -> Dict[str, Any]:
        default_policy = DeviceSupportPolicyService._clone_default_policy()
        if not isinstance(raw, dict):
            return default_policy

        out = DeviceSupportPolicyService._clone_default_policy()
        default_tier = _norm_text(raw.get("default_tier"))
        if default_tier in {"official", "limited", "unsupported"}:
            out["default_tier"] = default_tier

        tiers_raw = raw.get("tiers")
        if isinstance(tiers_raw, dict):
            for tier_name in ("official", "limited", "unsupported"):
                base = out["tiers"].get(tier_name) or {}
                out["tiers"][tier_name] = DeviceSupportPolicyService._normalize_features(
                    tiers_raw.get(tier_name),
                    fallback=base,
                )

        map_raw = raw.get("matrix_readiness_tier")
        if isinstance(map_raw, dict):
            for readiness_name, tier_name in map_raw.items():
                rk = _norm_text(readiness_name)
                tv = _norm_text(tier_name)
                if not rk:
                    continue
                if tv in {"official", "limited", "unsupported"}:
                    out["matrix_readiness_tier"][rk] = tv

        overrides_out: List[Dict[str, Any]] = []
        overrides_raw = raw.get("overrides")
        if isinstance(overrides_raw, list):
            for item in overrides_raw:
                if not isinstance(item, dict):
                    continue
                tier_name = _norm_text(item.get("tier"))
                if tier_name not in {"official", "limited", "unsupported", ""}:
                    continue
                rule = {
                    "device_type": _norm_text(item.get("device_type")),
                    "vendor": _norm_text(item.get("vendor")),
                    "os": _norm_text(item.get("os")),
                    "version_regex": str(item.get("version_regex") or "").strip(),
                    "tier": tier_name or None,
                    "reason": str(item.get("reason") or "").strip() or None,
                    "features": DeviceSupportPolicyService._normalize_features(
                        item.get("features"),
                        fallback={},
                    ),
                }
                has_condition = bool(
                    rule["device_type"] or rule["vendor"] or rule["os"] or rule["version_regex"]
                )
                if has_condition:
                    overrides_out.append(rule)
        out["overrides"] = overrides_out
        return out

    @staticmethod
    def _load_policy_from_settings(db: Session) -> Dict[str, Any]:
        row = db.query(SystemSetting).filter(SystemSetting.key == DeviceSupportPolicyService.SETTING_KEY).first()
        if not row or not row.value or row.value == "********":
            return DeviceSupportPolicyService._clone_default_policy()
        try:
            parsed = json.loads(str(row.value))
        except Exception:
            return DeviceSupportPolicyService._clone_default_policy()
        return DeviceSupportPolicyService._normalize_policy(parsed)

    @staticmethod
    def normalize_policy_json(raw_value: Any) -> str:
        if isinstance(raw_value, str):
            parsed = json.loads(raw_value)
        elif isinstance(raw_value, dict):
            parsed = raw_value
        else:
            raise ValueError("vendor_support_policy_json must be JSON object or JSON string")
        normalized = DeviceSupportPolicyService._normalize_policy(parsed)
        return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _load_matrix_payload() -> Dict[str, Any]:
        path = VENDOR_MATRIX_JSON_PATH
        if not path.exists():
            return {}
        try:
            mtime = path.stat().st_mtime
        except Exception:
            mtime = None
        if (
            DeviceSupportPolicyService._matrix_cache_payload is not None
            and DeviceSupportPolicyService._matrix_cache_mtime == mtime
        ):
            return dict(DeviceSupportPolicyService._matrix_cache_payload or {})
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}
        DeviceSupportPolicyService._matrix_cache_payload = dict(payload)
        DeviceSupportPolicyService._matrix_cache_mtime = mtime
        return payload

    @staticmethod
    def _matrix_row_by_device_type(device_type: str) -> Dict[str, Any]:
        dt = _norm_text(device_type)
        if not dt:
            return {}
        payload = DeviceSupportPolicyService._load_matrix_payload()
        rows = payload.get("rows")
        if not isinstance(rows, list):
            return {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            if _norm_text(row.get("device_type")) == dt:
                return row
        return {}

    @staticmethod
    def _infer_vendor(device_type: str, model: str, hostname: str = "") -> str:
        dt = _norm_text(device_type)
        model_text = _norm_text(model)
        host_text = _norm_text(hostname)
        raw = " ".join([dt, model_text, host_text]).strip()
        if not raw:
            return ""
        checks = (
            ("cisco", ("cisco", "ios", "nxos", "wlc", "c9", "n9k", "c9k")),
            ("arista", ("arista", "eos", "dcs-")),
            ("juniper", ("juniper", "junos", "qfx", "mx", "srx", "ex")),
            ("huawei", ("huawei", "vrp", "ce", "s57", "s67", "s97")),
            ("fortinet", ("fortinet", "fortios", "fortigate")),
            ("paloalto", ("paloalto", "panos", "pa-")),
            ("nokia", ("nokia", "sros", "sr-")),
            ("extreme", ("extreme", "exos", "netiron")),
            ("dell", ("dell", "os10", "force10", "s52", "z93")),
            ("dasan", ("dasan", "nos")),
            ("ubiquoss", ("ubiquoss", "ubiquos")),
            ("handream", ("handream",)),
            ("piolink", ("piolink",)),
            ("linux", ("linux", "ubuntu", "debian", "centos", "rhel")),
        )
        for vendor, needles in checks:
            if any(n in raw for n in needles):
                return vendor
        return ""

    @staticmethod
    def _matches_override(override: Dict[str, Any], meta: Dict[str, str]) -> bool:
        dt_rule = _norm_text(override.get("device_type"))
        vendor_rule = _norm_text(override.get("vendor"))
        os_rule = _norm_text(override.get("os"))
        version_regex = str(override.get("version_regex") or "").strip()

        if dt_rule and dt_rule != _norm_text(meta.get("device_type")):
            return False
        if vendor_rule and vendor_rule != _norm_text(meta.get("vendor")):
            return False
        if os_rule and os_rule not in _norm_text(meta.get("os_version")):
            return False
        if version_regex:
            try:
                if not re.search(version_regex, str(meta.get("os_version") or ""), flags=re.IGNORECASE):
                    return False
            except re.error:
                return False
        return True

    @staticmethod
    def _evaluate_for_meta(
        db: Session,
        *,
        site_id: Optional[int],
        device_type: str,
        os_version: str,
        model: str,
        hostname: str = "",
    ) -> Dict[str, Any]:
        policy = DeviceSupportPolicyService._load_policy_from_settings(db)
        matrix_row = DeviceSupportPolicyService._matrix_row_by_device_type(device_type)
        readiness = _norm_text(matrix_row.get("readiness"))
        tier_map = policy.get("matrix_readiness_tier") or {}
        tier = _norm_text(tier_map.get(readiness) or "")
        if tier not in {"official", "limited", "unsupported"}:
            tier = _norm_text(policy.get("default_tier"))
        if tier not in {"official", "limited", "unsupported"}:
            tier = "unsupported"

        features = DeviceSupportPolicyService._normalize_features(
            (policy.get("tiers") or {}).get(tier),
            fallback=DeviceSupportPolicyService.DEFAULT_POLICY["tiers"]["unsupported"],
        )

        meta = {
            "device_type": _norm_text(device_type),
            "vendor": DeviceSupportPolicyService._infer_vendor(device_type, model, hostname),
            "os_version": str(os_version or ""),
            "model": str(model or ""),
            "hostname": str(hostname or ""),
        }
        matched_override = None
        for override in list(policy.get("overrides") or []):
            if not isinstance(override, dict):
                continue
            if not DeviceSupportPolicyService._matches_override(override, meta):
                continue
            matched_override = override
            override_tier = _norm_text(override.get("tier"))
            if override_tier in {"official", "limited", "unsupported"}:
                tier = override_tier
                features = DeviceSupportPolicyService._normalize_features(
                    (policy.get("tiers") or {}).get(tier),
                    fallback=features,
                )
            features = DeviceSupportPolicyService._normalize_features(
                override.get("features"),
                fallback=features,
            )
            break

        capability = CapabilityProfileService.get_effective_policy(db, site_id=site_id, device_type=device_type)
        read_only = bool(capability.get("read_only", False))
        if read_only:
            features["ztp"] = False
            features["config"] = False
            features["rollback"] = False

        rollback_strategy = RollbackStrategyService.resolve_strategy(device_type)
        if not bool(rollback_strategy.get("supported")):
            features["rollback"] = False

        fallback_mode = None
        if not features.get("config", False) or read_only:
            fallback_mode = "read_only_manual_approval"

        reasons: List[str] = []
        if not matrix_row:
            reasons.append("device_type_not_covered_in_support_matrix")
        if matched_override and matched_override.get("reason"):
            reasons.append(str(matched_override.get("reason")))
        if read_only:
            reasons.append("capability_profile_read_only")
        if tier == "unsupported":
            reasons.append("unsupported_tier")
        if not bool(rollback_strategy.get("supported")):
            reasons.append("rollback_strategy_unsupported")

        return {
            "tier": tier,
            "readiness": readiness or None,
            "device_type": _norm_text(device_type),
            "vendor": meta.get("vendor"),
            "features": features,
            "fallback_mode": fallback_mode,
            "reasons": reasons,
            "matrix_row": matrix_row,
            "override": matched_override,
            "capability_read_only": read_only,
            "rollback_strategy": rollback_strategy,
        }

    @staticmethod
    def evaluate_device(db: Session, device: Device | None) -> Dict[str, Any]:
        if not device:
            return DeviceSupportPolicyService._evaluate_for_meta(
                db,
                site_id=None,
                device_type="",
                os_version="",
                model="",
                hostname="",
            )
        return DeviceSupportPolicyService._evaluate_for_meta(
            db,
            site_id=getattr(device, "site_id", None),
            device_type=str(getattr(device, "device_type", "") or ""),
            os_version=str(getattr(device, "os_version", "") or ""),
            model=str(getattr(device, "model", "") or ""),
            hostname=str(getattr(device, "hostname", "") or getattr(device, "name", "") or ""),
        )

    @staticmethod
    def evaluate_metadata(
        db: Session,
        *,
        device_type: str,
        os_version: str = "",
        model: str = "",
        site_id: Optional[int] = None,
        hostname: str = "",
    ) -> Dict[str, Any]:
        return DeviceSupportPolicyService._evaluate_for_meta(
            db,
            site_id=site_id,
            device_type=device_type,
            os_version=os_version,
            model=model,
            hostname=hostname,
        )

    @staticmethod
    def is_feature_allowed(
        db: Session,
        *,
        device: Device | None = None,
        device_type: str = "",
        os_version: str = "",
        model: str = "",
        site_id: Optional[int] = None,
        feature: str,
    ) -> bool:
        ft = _norm_text(feature)
        if device is not None:
            policy = DeviceSupportPolicyService.evaluate_device(db, device)
        else:
            policy = DeviceSupportPolicyService.evaluate_metadata(
                db,
                device_type=device_type,
                os_version=os_version,
                model=model,
                site_id=site_id,
            )
        return bool((policy.get("features") or {}).get(ft, False))

    @staticmethod
    def assert_feature_allowed(
        db: Session,
        *,
        device: Device,
        feature: str,
        action_label: str,
    ) -> Dict[str, Any]:
        ft = _norm_text(feature)
        policy = DeviceSupportPolicyService.evaluate_device(db, device)
        allowed = bool((policy.get("features") or {}).get(ft, False))
        if allowed:
            return policy
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEVICE_SUPPORT_BLOCKED",
                "message": (
                    f"{action_label} is blocked for device '{getattr(device, 'name', device.id)}' "
                    f"(tier={policy.get('tier')}, fallback={policy.get('fallback_mode')})."
                ),
                "details": {
                    "device_id": int(getattr(device, "id")),
                    "device_name": getattr(device, "name", None),
                    "device_type": getattr(device, "device_type", None),
                    "feature": ft,
                    "tier": policy.get("tier"),
                    "fallback_mode": policy.get("fallback_mode"),
                    "reasons": list(policy.get("reasons") or []),
                },
            },
        )

    @staticmethod
    def collect_blocked_devices(
        db: Session,
        *,
        devices: Iterable[Device],
        feature: str,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        ft = _norm_text(feature)
        for device in list(devices or []):
            policy = DeviceSupportPolicyService.evaluate_device(db, device)
            if bool((policy.get("features") or {}).get(ft, False)):
                continue
            out.append(
                {
                    "device_id": int(getattr(device, "id")),
                    "device_name": getattr(device, "name", None),
                    "device_type": getattr(device, "device_type", None),
                    "tier": policy.get("tier"),
                    "fallback_mode": policy.get("fallback_mode"),
                    "reasons": list(policy.get("reasons") or []),
                }
            )
        return out
