import json
from copy import deepcopy
from typing import Any, Dict, Iterable

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.settings import SystemSetting


def _to_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return default
    s = str(v).strip().lower()
    return s in {"1", "true", "yes", "y", "on"}


def _norm_proto(p: Any) -> str:
    s = str(p or "").strip().lower()
    if s in {"snmp", "ssh", "gnmi"}:
        return s
    return ""


class CapabilityProfileService:
    SETTING_KEY = "capability_profile_json"

    DEFAULT_PROFILE: Dict[str, Any] = {
        "default": {
            "allowed_protocols": ["snmp", "ssh", "gnmi"],
            "auto_reflection": {
                "approval": True,
                "topology": True,
                "sync": True,
            },
            "read_only": False,
        },
        "sites": {},
        "device_types": {},
    }

    @staticmethod
    def _safe_json(value: str) -> Dict[str, Any]:
        if not value:
            return deepcopy(CapabilityProfileService.DEFAULT_PROFILE)
        try:
            loaded = json.loads(value)
            if not isinstance(loaded, dict):
                return deepcopy(CapabilityProfileService.DEFAULT_PROFILE)
            return loaded
        except Exception:
            return deepcopy(CapabilityProfileService.DEFAULT_PROFILE)

    @staticmethod
    def _compact_override_layer(layer: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        protocols = layer.get("allowed_protocols")
        if isinstance(protocols, list) and protocols:
            out["allowed_protocols"] = list(protocols)

        auto = layer.get("auto_reflection") or {}
        if isinstance(auto, dict):
            auto_out = {}
            for key in ("approval", "topology", "sync"):
                v = auto.get(key)
                if isinstance(v, bool):
                    auto_out[key] = v
            if auto_out:
                out["auto_reflection"] = auto_out

        ro = layer.get("read_only")
        if isinstance(ro, bool):
            out["read_only"] = ro
        return out

    @staticmethod
    def normalize_profile(profile: Dict[str, Any] | None) -> Dict[str, Any]:
        raw = profile if isinstance(profile, dict) else {}
        normalized: Dict[str, Any] = {
            "default": deepcopy(CapabilityProfileService.DEFAULT_PROFILE["default"]),
            "sites": {},
            "device_types": {},
        }

        # default layer is full (inheritable baseline)
        default_norm = CapabilityProfileService._normalize_layer(raw.get("default", {}))
        if default_norm["allowed_protocols"]:
            normalized["default"]["allowed_protocols"] = default_norm["allowed_protocols"]
        for action_key in ("approval", "topology", "sync"):
            v = default_norm["auto_reflection"].get(action_key)
            if isinstance(v, bool):
                normalized["default"]["auto_reflection"][action_key] = v
        if isinstance(default_norm["read_only"], bool):
            normalized["default"]["read_only"] = default_norm["read_only"]

        if not normalized["default"].get("allowed_protocols"):
            normalized["default"]["allowed_protocols"] = ["snmp", "ssh", "gnmi"]

        # site/device_type layers are sparse overrides
        sites_raw = raw.get("sites")
        if isinstance(sites_raw, dict):
            for site_key, site_layer in sites_raw.items():
                key = str(site_key or "").strip()
                if not key:
                    continue
                compact = CapabilityProfileService._compact_override_layer(
                    CapabilityProfileService._normalize_layer(site_layer)
                )
                if compact:
                    normalized["sites"][key] = compact

        types_raw = raw.get("device_types")
        if isinstance(types_raw, dict):
            for dtype_key, dtype_layer in types_raw.items():
                key = str(dtype_key or "").strip().lower()
                if not key:
                    continue
                compact = CapabilityProfileService._compact_override_layer(
                    CapabilityProfileService._normalize_layer(dtype_layer)
                )
                if compact:
                    normalized["device_types"][key] = compact

        return normalized

    @staticmethod
    def _read_raw_profile(db: Session) -> Dict[str, Any]:
        setting = db.query(SystemSetting).filter(SystemSetting.key == CapabilityProfileService.SETTING_KEY).first()
        raw = setting.value if setting and setting.value and setting.value != "********" else ""
        profile = CapabilityProfileService._safe_json(raw)
        return CapabilityProfileService.normalize_profile(profile)

    @staticmethod
    def _normalize_layer(layer: Dict[str, Any]) -> Dict[str, Any]:
        out = {
            "allowed_protocols": [],
            "auto_reflection": {
                "approval": None,
                "topology": None,
                "sync": None,
            },
            "read_only": None,
        }
        if not isinstance(layer, dict):
            return out

        protos = layer.get("allowed_protocols")
        if isinstance(protos, Iterable) and not isinstance(protos, (str, bytes, dict)):
            norm = []
            for p in protos:
                np = _norm_proto(p)
                if np and np not in norm:
                    norm.append(np)
            out["allowed_protocols"] = norm

        auto_reflection = layer.get("auto_reflection")
        if isinstance(auto_reflection, dict):
            for key in ("approval", "topology", "sync"):
                if key in auto_reflection:
                    out["auto_reflection"][key] = _to_bool(auto_reflection.get(key), default=False)

        if "read_only" in layer:
            out["read_only"] = _to_bool(layer.get("read_only"), default=False)

        return out

    @staticmethod
    def get_profile(db: Session) -> Dict[str, Any]:
        return CapabilityProfileService._read_raw_profile(db)

    @staticmethod
    def save_profile(db: Session, profile: Dict[str, Any] | None) -> Dict[str, Any]:
        normalized = CapabilityProfileService.normalize_profile(profile)
        serialized = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))

        setting = db.query(SystemSetting).filter(SystemSetting.key == CapabilityProfileService.SETTING_KEY).first()
        if not setting:
            setting = SystemSetting(
                key=CapabilityProfileService.SETTING_KEY,
                value=serialized,
                description="Capability profile policy JSON",
                category="automation",
            )
            db.add(setting)
        else:
            setting.value = serialized
        db.commit()
        return normalized

    @staticmethod
    def get_effective_policy(db: Session, site_id: int | None, device_type: str | None) -> Dict[str, Any]:
        profile = CapabilityProfileService._read_raw_profile(db)
        merged = deepcopy(CapabilityProfileService.DEFAULT_PROFILE["default"])

        def apply_layer(layer: Dict[str, Any]) -> None:
            norm = CapabilityProfileService._normalize_layer(layer)
            if norm["allowed_protocols"]:
                merged["allowed_protocols"] = norm["allowed_protocols"]
            for action_key in ("approval", "topology", "sync"):
                v = norm["auto_reflection"].get(action_key)
                if isinstance(v, bool):
                    merged["auto_reflection"][action_key] = v
            if isinstance(norm["read_only"], bool):
                merged["read_only"] = norm["read_only"]

        apply_layer(profile.get("default", {}))

        if site_id is not None:
            apply_layer((profile.get("sites") or {}).get(str(site_id), {}))

        if device_type:
            apply_layer((profile.get("device_types") or {}).get(str(device_type).lower(), {}))

        if not isinstance(merged.get("allowed_protocols"), list) or not merged["allowed_protocols"]:
            merged["allowed_protocols"] = ["snmp", "ssh", "gnmi"]
        return merged

    @staticmethod
    def get_policy_for_device(db: Session, device: Device | None) -> Dict[str, Any]:
        if not device:
            return deepcopy(CapabilityProfileService.DEFAULT_PROFILE["default"])
        return CapabilityProfileService.get_effective_policy(
            db,
            site_id=getattr(device, "site_id", None),
            device_type=getattr(device, "device_type", None),
        )

    @staticmethod
    def allows_protocol(db: Session, device: Device | None, protocol: str) -> bool:
        policy = CapabilityProfileService.get_policy_for_device(db, device)
        return _norm_proto(protocol) in {str(x).lower() for x in policy.get("allowed_protocols", [])}

    @staticmethod
    def allow_auto_action(db: Session, device: Device | None, action: str) -> bool:
        policy = CapabilityProfileService.get_policy_for_device(db, device)
        if _to_bool(policy.get("read_only"), default=False):
            return False
        action_k = str(action or "").strip().lower()
        return _to_bool((policy.get("auto_reflection") or {}).get(action_k), default=True)
