from __future__ import annotations

from typing import Any, Dict, List

from app.services.discovery_hint_rule_service import DiscoveryHintRuleService


class DiscoveryHintSeedRuleService:
    DEFAULT_RULES: List[Dict[str, Any]] = [
        {
            "rule_key": "seed-dasan-oui-priority",
            "vendor_family": "dasan",
            "match_conditions": {
                "raw_vendor_contains": ["dasan"],
            },
            "driver_overrides": ["dasan_nos", "domestic_cisco_like"],
            "score_bonus": 0.34,
            "evidence_count": 1,
        },
        {
            "rule_key": "seed-ubiquoss-oui-priority",
            "vendor_family": "ubiquoss",
            "match_conditions": {
                "raw_vendor_contains": ["ubiquoss"],
            },
            "driver_overrides": ["ubiquoss_l2", "domestic_cisco_like"],
            "score_bonus": 0.31,
            "evidence_count": 1,
        },
        {
            "rule_key": "seed-handreamnet-intel-switch",
            "vendor_family": "handreamnet",
            "match_conditions": {
                "ssh_open": True,
                "raw_vendor_contains": ["intel"],
                "neighbor_name_regex": "(sg|sw|es)[-_ ]?\\d{2,4}",
            },
            "driver_overrides": ["handream_sg", "domestic_cisco_like"],
            "score_bonus": 0.37,
            "evidence_count": 1,
        },
        {
            "rule_key": "seed-soltech-realtek-switch",
            "vendor_family": "soltech",
            "match_conditions": {
                "ssh_open": True,
                "raw_vendor_contains": ["realtek"],
                "neighbor_name_regex": "(sol|sw|sg)[-_ ]?\\d{2,4}",
            },
            "driver_overrides": ["soltech_switch", "domestic_cisco_like"],
            "score_bonus": 0.28,
            "evidence_count": 1,
        },
        {
            "rule_key": "seed-coreedge-broadcom-domestic",
            "vendor_family": "coreedge",
            "match_conditions": {
                "ssh_open": True,
                "raw_vendor_contains": ["broadcom"],
                "seed_vendor_regex": "dasan|ubiquoss|soltech|coreedge|domestic",
            },
            "driver_overrides": ["coreedge_switch", "domestic_cisco_like"],
            "score_bonus": 0.24,
            "evidence_count": 1,
        },
        {
            "rule_key": "seed-piolink-oui-priority",
            "vendor_family": "piolink",
            "match_conditions": {
                "raw_vendor_contains": ["piolink"],
            },
            "driver_overrides": ["piolink_pas", "domestic_cisco_like"],
            "score_bonus": 0.29,
            "evidence_count": 1,
        },
        {
            "rule_key": "seed-nst-broadcom-switch",
            "vendor_family": "nst",
            "match_conditions": {
                "ssh_open": True,
                "raw_vendor_contains": ["broadcom", "nst"],
                "neighbor_name_regex": "(sw|sg|es|nst)[-_ ]?\\d{2,4}",
            },
            "driver_overrides": ["nst_switch", "domestic_cisco_like"],
            "score_bonus": 0.27,
            "evidence_count": 1,
        },
        {
            "rule_key": "seed-woorinet-domestic-cisco",
            "vendor_family": "woorinet",
            "match_conditions": {
                "ssh_open": True,
                "raw_vendor_contains": ["broadcom", "woorinet"],
                "seed_vendor_regex": "dasan|ubiquoss|soltech|coreedge|domestic",
            },
            "driver_overrides": ["domestic_cisco_like", "cisco_ios"],
            "score_bonus": 0.18,
            "evidence_count": 1,
        },
        {
            "rule_key": "seed-coweaver-domestic-cisco",
            "vendor_family": "coweaver",
            "match_conditions": {
                "ssh_open": True,
                "raw_vendor_contains": ["broadcom", "coweaver"],
                "seed_vendor_regex": "dasan|ubiquoss|soltech|coreedge|domestic",
            },
            "driver_overrides": ["domestic_cisco_like", "cisco_ios"],
            "score_bonus": 0.17,
            "evidence_count": 1,
        },
        {
            "rule_key": "seed-telefield-realtek-domestic",
            "vendor_family": "telefield",
            "match_conditions": {
                "ssh_open": True,
                "raw_vendor_contains": ["realtek", "telefield"],
                "seed_vendor_regex": "dasan|ubiquoss|soltech|coreedge|domestic",
            },
            "driver_overrides": ["domestic_cisco_like", "cisco_ios"],
            "score_bonus": 0.16,
            "evidence_count": 1,
        },
        {
            "rule_key": "seed-efmnetworks-ralink-linux",
            "vendor_family": "efmnetworks",
            "match_conditions": {
                "ssh_open": True,
                "raw_vendor_contains": ["ralink", "mediatek", "efm", "iptime"],
            },
            "driver_overrides": ["linux", "domestic_cisco_like"],
            "score_bonus": 0.22,
            "evidence_count": 1,
        },
        {
            "rule_key": "seed-davolink-realtek-linux",
            "vendor_family": "davolink",
            "match_conditions": {
                "ssh_open": True,
                "raw_vendor_contains": ["realtek", "davolink"],
            },
            "driver_overrides": ["linux", "domestic_cisco_like"],
            "score_bonus": 0.2,
            "evidence_count": 1,
        },
    ]

    @classmethod
    def install_defaults(cls) -> Dict[str, int]:
        existing_keys = {
            str(item.get("rule_key") or "").strip()
            for item in DiscoveryHintRuleService.list_rules_detailed(include_inactive=True)
            if str(item.get("rule_key") or "").strip()
        }
        inserted = 0
        for rule in cls.DEFAULT_RULES:
            rule_key = str(rule.get("rule_key") or "").strip()
            if rule_key and rule_key in existing_keys:
                continue
            payload = dict(rule)
            payload["source"] = "seed_defaults"
            payload["is_active"] = True
            row_id = DiscoveryHintRuleService.upsert_rule(payload)
            if isinstance(row_id, int):
                inserted += 1
                if rule_key:
                    existing_keys.add(rule_key)
        return {"installed": inserted, "available": len(cls.DEFAULT_RULES)}
