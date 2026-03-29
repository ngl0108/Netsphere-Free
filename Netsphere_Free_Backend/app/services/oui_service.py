import os
import re
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.discovery_hint_learning import DiscoveryHintVendorAlias


_VENDOR_ALIAS_MAP = {
    "dasan": "Dasan",
    "dasan networks": "Dasan",
    "dasan electron": "Dasan",
    "dasan network solutions": "Dasan",
    "ubiquoss": "Ubiquoss",
    "ubiquoss inc": "Ubiquoss",
    "ubiquoss corporation": "Ubiquoss",
    "handream": "HanDreamnet",
    "handreamnet": "HanDreamnet",
    "han dreamnet": "HanDreamnet",
    "han dream net": "HanDreamnet",
    "handream inc": "HanDreamnet",
    "handreamnet inc": "HanDreamnet",
    "subgate": "HanDreamnet",
    "piolink": "Piolink",
    "piolink inc": "Piolink",
    "piolink co ltd": "Piolink",
    "nst": "NST",
    "nst ic": "NST",
    "soltech": "Soltech",
    "coreedge": "CoreEdge",
    "core edge": "CoreEdge",
    "core-edge": "CoreEdge",
    "woorinet": "WooriNet",
    "woori net": "WooriNet",
    "woori-net": "WooriNet",
    "woori net co ltd": "WooriNet",
    "coweaver": "Coweaver",
    "co weaver": "Coweaver",
    "telefield": "Telefield",
    "tele field": "Telefield",
    "davolink": "Davolink",
    "davo link": "Davolink",
    "efmnetworks": "EFMNetworks",
    "efm networks": "EFMNetworks",
    "efm-networks": "EFMNetworks",
    "efm networks co ltd": "EFMNetworks",
    "iptime": "EFMNetworks",
    "ip-time": "EFMNetworks",
    "ip time": "EFMNetworks",
}

_VENDOR_DRIVER_CANDIDATES = {
    "Dasan": ["dasan_nos", "cisco_ios"],
    "Ubiquoss": ["ubiquoss_l2", "cisco_ios"],
    "HanDreamnet": ["handream_sg", "cisco_ios"],
    "Piolink": ["piolink_pas", "cisco_ios"],
    "NST": ["nst_switch", "cisco_ios"],
    "Soltech": ["soltech_switch", "cisco_ios"],
    "CoreEdge": ["coreedge_switch", "cisco_ios"],
    "WooriNet": ["domestic_cisco_like", "cisco_ios"],
    "Coweaver": ["domestic_cisco_like", "cisco_ios"],
    "Telefield": ["domestic_cisco_like", "cisco_ios"],
    "Davolink": ["linux"],
    "EFMNetworks": ["linux"],
}

_DRIVER_VENDOR_LOOKUP = {
    str(driver or "").strip().lower(): vendor
    for vendor, drivers in _VENDOR_DRIVER_CANDIDATES.items()
    for driver in (drivers or [])
    if str(driver or "").strip()
}

_CANONICAL_VENDOR_LABELS = {
    str(value or "").strip().lower(): value
    for value in list(_VENDOR_DRIVER_CANDIDATES.keys()) + list(set(_VENDOR_ALIAS_MAP.values()))
    if str(value or "").strip()
}

_GENERIC_CHIPSET_OUI_VENDORS = {
    "intel",
    "broadcom",
    "realtek",
    "marvell",
    "liteon",
    "azurewave",
    "foxconn",
    "mediatek",
    "ralink",
}


class OUIService:
    _override_map: Optional[Dict[str, str]] = None
    _session_factory: Optional[Callable[[], Session]] = None

    @classmethod
    def _persistence_enabled(cls) -> bool:
        app_env = str(os.getenv("APP_ENV") or "").strip().lower()
        if app_env in {"test", "pytest"} and cls._session_factory is None:
            return False
        raw = os.getenv("DISCOVERY_HINT_ALIAS_PERSIST", "true")
        return str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    @classmethod
    def _get_session_factory(cls) -> Callable[[], Session]:
        return cls._session_factory or SessionLocal

    @staticmethod
    def _normalize_mac_prefix(mac: str) -> Optional[str]:
        if not mac:
            return None
        s = str(mac).strip().lower()
        s = re.sub(r"[^0-9a-f]", "", s)
        if len(s) < 6:
            return None
        return s[:6]

    @staticmethod
    def _possible_paths() -> list:
        env = os.getenv("OUI_DB_PATH")
        paths = []
        if env:
            paths.append(env)
        here = os.path.dirname(os.path.abspath(__file__))
        paths.append(os.path.join(here, "..", "data", "oui.csv"))
        paths.append(os.path.join(here, "..", "data", "oui.txt"))
        return paths

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_map() -> Dict[str, str]:
        if isinstance(OUIService._override_map, dict):
            return OUIService._override_map

        mapping: Dict[str, str] = {}
        for p in OUIService._possible_paths():
            try:
                if not p or not os.path.exists(p):
                    continue
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        ln = line.strip()
                        if not ln:
                            continue
                        if ln.startswith("#"):
                            continue
                        if "," in ln:
                            parts = [x.strip() for x in ln.split(",")]
                            if len(parts) >= 2:
                                prefix = OUIService._normalize_mac_prefix(parts[0])
                                vendor = parts[1].strip()
                                if prefix and vendor:
                                    mapping[prefix] = vendor
                            continue

                        m = re.search(r"^([0-9A-Fa-f]{2}[:-]){2}[0-9A-Fa-f]{2}", ln)
                        if m:
                            prefix = OUIService._normalize_mac_prefix(m.group(0))
                            vendor = ln[m.end() :].strip()
                            vendor = re.sub(r"^\(hex\)\s*", "", vendor, flags=re.IGNORECASE).strip()
                            if prefix and vendor:
                                mapping[prefix] = vendor
                            continue
            except Exception:
                continue

        return mapping

    @staticmethod
    def lookup_vendor(mac: str) -> Optional[str]:
        prefix = OUIService._normalize_mac_prefix(mac)
        if not prefix:
            return None
        return OUIService._load_map().get(prefix)

    @staticmethod
    def _alias_key(raw_vendor: Any) -> str:
        text = str(raw_vendor or "").strip().lower()
        text = re.sub(r"[\s\-_]+", " ", text).strip()
        return text

    @staticmethod
    def _canonical_vendor_label(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        if not text:
            return None
        return _CANONICAL_VENDOR_LABELS.get(text.lower(), text)

    @staticmethod
    @lru_cache(maxsize=1)
    def _load_db_alias_map() -> Dict[str, str]:
        if not OUIService._persistence_enabled():
            return {}
        db = OUIService._get_session_factory()()
        try:
            rows = (
                db.query(DiscoveryHintVendorAlias)
                .filter(DiscoveryHintVendorAlias.is_active.is_(True))
                .all()
            )
            mapping: Dict[str, str] = {}
            for row in rows:
                key = OUIService._alias_key(getattr(row, "raw_alias_key", None) or getattr(row, "raw_alias", None))
                vendor = OUIService._canonical_vendor_label(getattr(row, "vendor_family", None))
                if key and vendor:
                    mapping[key] = vendor
            return mapping
        finally:
            db.close()

    @staticmethod
    def _merged_alias_map() -> Dict[str, str]:
        merged = {OUIService._alias_key(key): value for key, value in _VENDOR_ALIAS_MAP.items()}
        merged.update(OUIService._load_db_alias_map())
        return merged

    @staticmethod
    def normalize_vendor_name(raw_vendor: str) -> Optional[str]:
        raw_text = str(raw_vendor or "").strip()
        text = OUIService._alias_key(raw_text)
        if not text:
            return None
        alias_map = OUIService._merged_alias_map()
        if text in alias_map:
            return OUIService._canonical_vendor_label(alias_map[text])
        for alias, canonical in alias_map.items():
            if alias in text:
                return OUIService._canonical_vendor_label(canonical)
        return OUIService._canonical_vendor_label(raw_text) or raw_text

    @staticmethod
    def driver_candidates_for_vendor(raw_vendor: str) -> List[str]:
        normalized = OUIService._canonical_vendor_label(OUIService.normalize_vendor_name(raw_vendor))
        if not normalized:
            return []
        candidates = list(_VENDOR_DRIVER_CANDIDATES.get(normalized, []))
        return [c for c in candidates if c]

    @staticmethod
    def vendor_for_driver(driver: str) -> Optional[str]:
        value = str(driver or "").strip().lower()
        if not value:
            return None
        return _DRIVER_VENDOR_LOOKUP.get(value)

    @staticmethod
    def is_generic_chipset_vendor(raw_vendor: str) -> bool:
        text = str(raw_vendor or "").strip().lower()
        if not text:
            return False
        return any(vendor in text for vendor in _GENERIC_CHIPSET_OUI_VENDORS)

    @staticmethod
    def lookup_vendor_detail(mac: str) -> Dict[str, Any]:
        prefix = OUIService._normalize_mac_prefix(mac)
        raw_vendor = OUIService.lookup_vendor(mac)
        normalized_vendor = OUIService.normalize_vendor_name(raw_vendor or "")
        return {
            "prefix": prefix,
            "raw_vendor": raw_vendor,
            "normalized_vendor": normalized_vendor,
            "driver_candidates": OUIService.driver_candidates_for_vendor(raw_vendor or ""),
            "is_generic_chipset": OUIService.is_generic_chipset_vendor(raw_vendor or ""),
        }

    @staticmethod
    def set_override_map_for_tests(mapping: Optional[Dict[str, str]]) -> None:
        OUIService._override_map = mapping
        OUIService._load_map.cache_clear()

    @staticmethod
    def set_session_factory_for_tests(factory: Optional[Callable[[], Session]]) -> None:
        OUIService._session_factory = factory
        OUIService._load_db_alias_map.cache_clear()

    @staticmethod
    def clear_aliases_for_tests() -> None:
        OUIService._load_db_alias_map.cache_clear()
        if not OUIService._persistence_enabled():
            return
        db = OUIService._get_session_factory()()
        try:
            db.query(DiscoveryHintVendorAlias).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @staticmethod
    def list_vendor_aliases() -> List[Dict[str, Any]]:
        if not OUIService._persistence_enabled():
            return []
        db = OUIService._get_session_factory()()
        try:
            rows = db.query(DiscoveryHintVendorAlias).order_by(DiscoveryHintVendorAlias.raw_alias.asc()).all()
            return [
                {
                    "id": int(row.id),
                    "raw_alias": str(row.raw_alias or ""),
                    "raw_alias_key": str(row.raw_alias_key or ""),
                    "vendor_family": OUIService._canonical_vendor_label(row.vendor_family),
                    "source": str(row.source or "").strip() or None,
                    "is_active": bool(row.is_active),
                }
                for row in rows
            ]
        finally:
            db.close()

    @staticmethod
    def upsert_vendor_alias(*, raw_alias: str, vendor_family: str, source: str = "telemetry") -> Optional[int]:
        alias_key = OUIService._alias_key(raw_alias)
        canonical_vendor = OUIService._canonical_vendor_label(vendor_family)
        if not OUIService._persistence_enabled() or not alias_key or not canonical_vendor:
            return None
        db = OUIService._get_session_factory()()
        try:
            row = (
                db.query(DiscoveryHintVendorAlias)
                .filter(DiscoveryHintVendorAlias.raw_alias_key == alias_key)
                .first()
            )
            if row is None:
                row = DiscoveryHintVendorAlias(raw_alias_key=alias_key, raw_alias=str(raw_alias or "").strip())
                db.add(row)
            row.raw_alias = str(raw_alias or "").strip() or alias_key
            row.vendor_family = canonical_vendor
            row.source = str(source or "telemetry").strip() or "telemetry"
            row.is_active = True
            db.commit()
            db.refresh(row)
            OUIService._load_db_alias_map.cache_clear()
            return int(row.id)
        except Exception:
            db.rollback()
            return None
        finally:
            db.close()
