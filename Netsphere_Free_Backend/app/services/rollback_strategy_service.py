from __future__ import annotations

from typing import Dict


class RollbackStrategyService:
    """
    Vendor/device-type rollback strategy resolver.
    Used to pre-block rollback requests on unsupported platforms.
    """

    @staticmethod
    def resolve_strategy(device_type: str) -> Dict[str, str | bool]:
        dt = str(device_type or "").strip().lower()
        if not dt:
            return {"supported": False, "strategy": "none", "reason": "missing_device_type"}

        unsupported_exact = {"unknown", "manageable_device", "web_device"}
        if dt in unsupported_exact:
            return {"supported": False, "strategy": "none", "reason": "generic_device_type"}

        unsupported_prefixes = ("linux", "windows")
        if any(dt.startswith(prefix) for prefix in unsupported_prefixes):
            return {"supported": False, "strategy": "none", "reason": "host_os_no_network_rollback"}

        # Junos can use native rollback; most network OSes can use snapshot/replace flow.
        if "junos" in dt or "juniper" in dt:
            return {"supported": True, "strategy": "native_junos_rollback", "reason": ""}

        network_vendor_tokens = (
            "cisco",
            "arista",
            "huawei",
            "fortinet",
            "paloalto",
            "nokia",
            "extreme",
            "dell",
            "hp_",
            "alcatel",
            "dasan",
            "ubiquoss",
            "handream",
            "piolink",
            "f5_",
            "checkpoint",
        )
        if any(token in dt for token in network_vendor_tokens):
            return {"supported": True, "strategy": "snapshot_replace_rollback", "reason": ""}

        return {"supported": False, "strategy": "none", "reason": "no_vendor_strategy"}

