from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.services.discovery_hint_cache_service import DiscoveryHintCacheService
from app.services.discovery_hint_rule_service import DiscoveryHintRuleService
from app.services.oui_service import OUIService


_CHIPSET_FALLBACK_DRIVERS = [
    "handream_sg",
    "linux",
    "domestic_cisco_like",
    "soltech_switch",
    "coreedge_switch",
    "nst_switch",
    "cisco_ios",
]

_DRIVER_NEIGHBOR_PATTERNS = {
    "handream_sg": [r"\bsg[-_ ]?\d{2,4}\b", r"\bes[-_ ]?\d{2,4}\b", r"handream", r"subgate"],
    "piolink_pas": [r"piolink", r"\bpas\b", r"\bpa[-_ ]?\d{2,4}\b"],
    "nst_switch": [r"\bnst[-_ ]?\d{2,4}\b", r"\bnst\b"],
    "soltech_switch": [r"soltech", r"\bsfc[-_ ]?\d{2,4}\b"],
    "coreedge_switch": [r"core[-_ ]?edge", r"\bce[-_ ]?\d{2,4}\b", r"\bedge[-_ ]?sw\b"],
    "domestic_cisco_like": [r"\bsw[-_ ]?\d{2,4}\b", r"\bsg[-_ ]?\d{2,4}\b", r"\bes[-_ ]?\d{2,4}\b"],
    "linux": [r"ip[-_ ]?time", r"davo[-_ ]?link", r"efm"],
}

_DOMESTIC_SEED_VENDOR_PATTERNS = [
    r"dasan",
    r"ubiquoss",
    r"handream",
    r"subgate",
    r"piolink",
    r"nst",
    r"soltech",
    r"coreedge",
    r"domestic",
    r"woori",
    r"coweaver",
    r"telefield",
]

_CHIPSET_VENDOR_DRIVER_HINTS = {
    "intel": ["handream_sg", "domestic_cisco_like", "cisco_ios"],
    "broadcom": ["nst_switch", "coreedge_switch", "domestic_cisco_like", "cisco_ios"],
    "realtek": ["soltech_switch", "domestic_cisco_like", "cisco_ios"],
    "marvell": ["domestic_cisco_like", "cisco_ios"],
    "liteon": ["domestic_cisco_like", "cisco_ios"],
    "azurewave": ["domestic_cisco_like", "cisco_ios"],
    "foxconn": ["domestic_cisco_like", "cisco_ios"],
    "mediatek": ["linux", "domestic_cisco_like", "cisco_ios"],
    "ralink": ["linux", "domestic_cisco_like", "cisco_ios"],
}


class DiscoveryHintService:
    def __init__(self, db=None):
        self.db = db

    def build_ip_hint(self, ip: str, open_ports: Optional[List[int]] = None) -> Optional[Dict[str, Any]]:
        cache_hit = DiscoveryHintCacheService.lookup_ip(ip)
        if not cache_hit:
            return None

        oui_detail = OUIService.lookup_vendor_detail(cache_hit.get("mac") or "")
        candidates = self._score_driver_candidates(cache_hit, oui_detail, open_ports or [])
        if not candidates:
            return None

        return {
            "target_ip": str(ip or "").strip(),
            "mac": cache_hit.get("mac"),
            "oui_prefix": oui_detail.get("prefix"),
            "raw_vendor": oui_detail.get("raw_vendor"),
            "normalized_vendor": oui_detail.get("normalized_vendor"),
            "cache_context": cache_hit,
            "driver_candidates": candidates,
        }

    def build_hint_telemetry_event(
        self,
        *,
        ip: str,
        hint: Optional[Dict[str, Any]],
        chosen_driver: str | None,
        final_driver: str | None,
        success: bool,
        failure_reason: str | None = None,
    ) -> Dict[str, Any]:
        hint = hint if isinstance(hint, dict) else {}
        context = hint.get("cache_context") if isinstance(hint.get("cache_context"), dict) else {}
        candidates = hint.get("driver_candidates") if isinstance(hint.get("driver_candidates"), list) else []
        event_type = "hint_success" if success else "unknown_after_hint"
        if not success and candidates and chosen_driver and final_driver and chosen_driver != final_driver:
            event_type = "hint_false_positive"
        return {
            "event_type": event_type,
            "target_ip": str(ip or "").strip(),
            "mac": context.get("mac"),
            "oui_prefix": hint.get("oui_prefix"),
            "raw_vendor": hint.get("raw_vendor"),
            "normalized_vendor": hint.get("normalized_vendor"),
            "seed_device_id": context.get("seed_device_id"),
            "seed_ip": context.get("seed_ip"),
            "seed_vendor": context.get("seed_vendor"),
            "local_interface": context.get("local_interface"),
            "neighbor_name": context.get("neighbor_name"),
            "neighbor_mgmt_ip": context.get("neighbor_mgmt_ip"),
            "chosen_driver": chosen_driver,
            "final_driver": final_driver,
            "success": bool(success),
            "failure_reason": str(failure_reason or "").strip() or None,
            "candidates": [
                {
                    "driver": c.get("driver"),
                    "score": c.get("score"),
                    "reasons": list(c.get("reasons") or []),
                }
                for c in candidates[:5]
                if isinstance(c, dict)
            ],
        }

    def _score_driver_candidates(
        self,
        cache_hit: Dict[str, Any],
        oui_detail: Dict[str, Any],
        open_ports: List[int],
    ) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        base_vendor = str(oui_detail.get("normalized_vendor") or "").strip()
        raw_vendor = str(oui_detail.get("raw_vendor") or "").strip()
        ssh_open = any(int(port) in {22, 830} for port in open_ports if str(port).isdigit())

        if base_vendor:
            drivers = list(oui_detail.get("driver_candidates") or [])
            for index, driver in enumerate(drivers):
                score = 0.55 - (index * 0.09)
                reasons = ["oui_match"]
                if cache_hit.get("local_interface"):
                    score += 0.10
                    reasons.append("fdb_port_seen")
                if cache_hit.get("neighbor_name") or cache_hit.get("neighbor_mgmt_ip"):
                    score += 0.10
                    reasons.append("lldp_context")
                if ssh_open:
                    score += 0.08
                    reasons.append("ssh_open")
                if cache_hit.get("seed_vendor"):
                    score += 0.04
                    reasons.append("seed_context")
                score, reasons = self._apply_contextual_driver_bonus(
                    score=score,
                    reasons=reasons,
                    driver=driver,
                    cache_hit=cache_hit,
                    raw_vendor=raw_vendor,
                )
                candidates.append(
                    {
                        "vendor_family": base_vendor,
                        "driver": driver,
                        "score": round(min(score, 0.99), 3),
                        "reasons": reasons,
                    }
                )

        if ssh_open and OUIService.is_generic_chipset_vendor(raw_vendor):
            for index, driver in enumerate(_CHIPSET_FALLBACK_DRIVERS):
                score = 0.26 - (index * 0.03)
                if score <= 0:
                    continue
                score, reasons = self._apply_contextual_driver_bonus(
                    score=score,
                    reasons=["generic_chipset_oui", "ssh_open"],
                    driver=driver,
                    cache_hit=cache_hit,
                    raw_vendor=raw_vendor,
                )
                candidates.append(
                    {
                        "vendor_family": "generic_chipset_override",
                        "driver": driver,
                        "score": round(score, 3),
                        "reasons": reasons,
                    }
                )

        candidates.extend(
            DiscoveryHintRuleService.evaluate_overrides(
                cache_hit=cache_hit,
                raw_vendor=raw_vendor,
                normalized_vendor=base_vendor,
                open_ports=open_ports,
            )
        )

        deduped: List[Dict[str, Any]] = []
        seen = set()
        for row in sorted(candidates, key=lambda item: float(item.get("score") or 0.0), reverse=True):
            driver = str(row.get("driver") or "").strip().lower()
            if not driver or driver in seen:
                continue
            seen.add(driver)
            deduped.append(row)
        return deduped

    def _apply_contextual_driver_bonus(
        self,
        *,
        score: float,
        reasons: List[str],
        driver: str,
        cache_hit: Dict[str, Any],
        raw_vendor: str,
    ) -> tuple[float, List[str]]:
        updated_score = float(score or 0.0)
        updated_reasons = list(reasons or [])
        neighbor_name = str(cache_hit.get("neighbor_name") or "").strip()
        seed_vendor = str(cache_hit.get("seed_vendor") or "").strip()
        raw_vendor_lower = str(raw_vendor or "").strip().lower()

        if neighbor_name and self._matches_any_pattern(driver, neighbor_name):
            updated_score += 0.12
            updated_reasons.append("neighbor_pattern")

        if seed_vendor and self._looks_domestic_seed(seed_vendor) and driver in {
            "handream_sg",
            "domestic_cisco_like",
            "nst_switch",
            "soltech_switch",
            "coreedge_switch",
            "piolink_pas",
            "linux",
        }:
            updated_score += 0.06
            updated_reasons.append("domestic_seed_affinity")

        chipset_hints = self._chipset_driver_preferences(raw_vendor_lower)
        if driver in chipset_hints:
            index = chipset_hints.index(driver)
            updated_score += max(0.02, 0.08 - (index * 0.02))
            updated_reasons.append("chipset_driver_fit")

        return round(min(updated_score, 0.99), 3), updated_reasons

    @staticmethod
    def _matches_any_pattern(driver: str, text: str) -> bool:
        patterns = list(_DRIVER_NEIGHBOR_PATTERNS.get(str(driver or "").strip(), []))
        if not patterns:
            return False
        target = str(text or "").strip()
        if not target:
            return False
        return any(re.search(pattern, target, re.IGNORECASE) for pattern in patterns)

    @staticmethod
    def _looks_domestic_seed(seed_vendor: str) -> bool:
        target = str(seed_vendor or "").strip()
        if not target:
            return False
        return any(re.search(pattern, target, re.IGNORECASE) for pattern in _DOMESTIC_SEED_VENDOR_PATTERNS)

    @staticmethod
    def _chipset_driver_preferences(raw_vendor_lower: str) -> List[str]:
        target = str(raw_vendor_lower or "").strip().lower()
        if not target:
            return []
        for chipset, drivers in _CHIPSET_VENDOR_DRIVER_HINTS.items():
            if chipset in target:
                return list(drivers)
        return []
