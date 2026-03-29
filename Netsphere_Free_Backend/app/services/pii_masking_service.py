from __future__ import annotations

import re
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.settings import SystemSetting


class PiiMaskingService:
    _IPV4_RE = re.compile(r"\b(?:(?:\d{1,3})\.){3}(?:\d{1,3})\b")
    _IPV6_RE = re.compile(r"\b(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}\b")
    _MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
    _EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-])([A-Za-z0-9._%+-]*?)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
    _PHONE_RE = re.compile(r"\b(0\d{1,2})-?(\d{3,4})-?(\d{4})\b")

    @staticmethod
    def _get_bool_from_map(values: Dict[str, str], key: str, default: bool) -> bool:
        raw = values.get(key)
        if raw is None:
            return bool(default)
        s = str(raw).strip().lower()
        return s in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def get_policy(db: Session) -> Dict[str, bool]:
        keys = [
            "pii_masking_enabled",
            "pii_mask_ip",
            "pii_mask_mac",
            "pii_mask_phone",
            "pii_mask_email",
        ]
        rows = db.query(SystemSetting).filter(SystemSetting.key.in_(keys)).all()
        values = {r.key: r.value for r in rows}
        enabled = PiiMaskingService._get_bool_from_map(values, "pii_masking_enabled", False)
        return {
            "enabled": enabled,
            "mask_ip": enabled and PiiMaskingService._get_bool_from_map(values, "pii_mask_ip", True),
            "mask_mac": enabled and PiiMaskingService._get_bool_from_map(values, "pii_mask_mac", True),
            "mask_phone": enabled and PiiMaskingService._get_bool_from_map(values, "pii_mask_phone", True),
            "mask_email": enabled and PiiMaskingService._get_bool_from_map(values, "pii_mask_email", True),
        }

    @staticmethod
    def _mask_ipv4(ip: str) -> str:
        parts = ip.split(".")
        if len(parts) != 4:
            return ip
        return f"{parts[0]}.{parts[1]}.*.*"

    @staticmethod
    def _mask_ipv6(ip: str) -> str:
        chunks = ip.split(":")
        chunks = [c for c in chunks if c != ""]
        if len(chunks) < 2:
            return ip
        return f"{chunks[0]}:{chunks[1]}::*"

    @staticmethod
    def _mask_mac(mac: str) -> str:
        sep = ":" if ":" in mac else "-"
        parts = mac.split(sep)
        if len(parts) != 6:
            return mac
        return sep.join([parts[0], parts[1], parts[2], "**", "**", "**"])

    @staticmethod
    def _mask_phone(match: re.Match) -> str:
        head = match.group(1)
        tail = match.group(3)
        return f"{head}-****-{tail}"

    @staticmethod
    def _mask_email(match: re.Match) -> str:
        first = match.group(1)
        domain = match.group(3)
        return f"{first}***@{domain}"

    @staticmethod
    def mask_text(text: Any, policy: Dict[str, bool]) -> Any:
        if not policy.get("enabled"):
            return text
        if text is None:
            return None
        s = str(text)
        if policy.get("mask_ip"):
            s = PiiMaskingService._IPV4_RE.sub(lambda m: PiiMaskingService._mask_ipv4(m.group(0)), s)
            s = PiiMaskingService._IPV6_RE.sub(lambda m: PiiMaskingService._mask_ipv6(m.group(0)), s)
        if policy.get("mask_mac"):
            s = PiiMaskingService._MAC_RE.sub(lambda m: PiiMaskingService._mask_mac(m.group(0)), s)
        if policy.get("mask_phone"):
            s = PiiMaskingService._PHONE_RE.sub(PiiMaskingService._mask_phone, s)
        if policy.get("mask_email"):
            s = PiiMaskingService._EMAIL_RE.sub(PiiMaskingService._mask_email, s)
        return s
