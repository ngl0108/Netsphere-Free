from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

try:
    import requests
except Exception:
    requests = None
from sqlalchemy.orm import Session

from app.models.ip_intel import IpIntelCache


class IpIntelService:
    @staticmethod
    def guess_provider(text: str) -> Optional[str]:
        s = (text or "").lower()
        if not s:
            return None
        if "amazon" in s or "aws" in s or "amzn" in s:
            return "aws"
        if "microsoft" in s or "azure" in s or "msft" in s:
            return "azure"
        if "google" in s or "gcp" in s or "google cloud" in s:
            return "gcp"
        if "naver" in s or "ncloud" in s or "ntruss" in s:
            return "naver"
        return None

    @staticmethod
    def get_cached(db: Session, ip: str, *, max_age_hours: int = 168) -> Optional[IpIntelCache]:
        ip_norm = (ip or "").strip()
        if not ip_norm:
            return None
        row = db.query(IpIntelCache).filter(IpIntelCache.ip == ip_norm).first()
        if not row:
            return None
        if max_age_hours and row.updated_at:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=int(max_age_hours))
            try:
                if row.updated_at < cutoff:
                    return None
            except Exception:
                pass
        return row

    @staticmethod
    def fetch_from_bgpview(ip: str, *, timeout_sec: float = 3.0) -> Optional[Dict[str, Any]]:
        if requests is None:
            return None
        url = f"https://api.bgpview.io/ip/{ip}"
        r = requests.get(url, timeout=timeout_sec)
        if r.status_code != 200:
            return None
        try:
            payload = r.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("status") != "ok":
            return None
        data = payload.get("data") or {}
        prefixes = data.get("prefixes") or []
        best = prefixes[0] if prefixes else {}
        asn = None
        as_name = None
        org = None
        if isinstance(best, dict):
            asn_obj = best.get("asn") or {}
            if isinstance(asn_obj, dict):
                asn = asn_obj.get("asn")
                as_name = asn_obj.get("name")
                org = asn_obj.get("description") or asn_obj.get("name")
        out = {
            "asn": str(asn) if asn is not None else None,
            "as_name": str(as_name) if as_name is not None else None,
            "org_name": str(org) if org is not None else None,
            "raw": payload,
        }
        return out

    @staticmethod
    def fetch_from_rdap(ip: str, *, timeout_sec: float = 3.0) -> Optional[Dict[str, Any]]:
        if requests is None:
            return None
        url = f"https://rdap.org/ip/{ip}"
        r = requests.get(url, timeout=timeout_sec, headers={"accept": "application/rdap+json"})
        if r.status_code != 200:
            return None
        try:
            payload = r.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        name = payload.get("name") or payload.get("handle")
        out = {
            "asn": None,
            "as_name": None,
            "org_name": str(name) if name is not None else None,
            "raw": payload,
        }
        return out

    @staticmethod
    def get_or_fetch(db: Session, ip: str, *, max_age_hours: int = 168) -> Optional[Dict[str, Any]]:
        ip_norm = (ip or "").strip()
        if not ip_norm:
            return None

        cached = IpIntelService.get_cached(db, ip_norm, max_age_hours=max_age_hours)
        if cached:
            return {
                "ip": cached.ip,
                "provider_guess": cached.provider_guess,
                "asn": cached.asn,
                "as_name": cached.as_name,
                "org_name": cached.org_name,
                "source": cached.source,
            }

        if str(os.getenv("DISABLE_IP_INTEL", "") or "").strip() in {"1", "true", "yes"}:
            return None

        fetched = None
        source = None
        try:
            fetched = IpIntelService.fetch_from_bgpview(ip_norm)
            source = "bgpview"
        except Exception:
            fetched = None
        if not fetched:
            try:
                fetched = IpIntelService.fetch_from_rdap(ip_norm)
                source = "rdap"
            except Exception:
                fetched = None

        if not fetched:
            return None

        combined_text = " ".join(
            [str(fetched.get("as_name") or ""), str(fetched.get("org_name") or ""), str(fetched.get("asn") or "")]
        ).strip()
        provider = IpIntelService.guess_provider(combined_text)

        row = IpIntelCache(
            ip=ip_norm,
            provider_guess=provider,
            asn=fetched.get("asn"),
            as_name=fetched.get("as_name"),
            org_name=fetched.get("org_name"),
            source=source,
            raw_json=json.dumps(fetched.get("raw") or {}, ensure_ascii=False, default=str),
        )
        db.add(row)
        db.commit()

        return {
            "ip": ip_norm,
            "provider_guess": provider,
            "asn": fetched.get("asn"),
            "as_name": fetched.get("as_name"),
            "org_name": fetched.get("org_name"),
            "source": source,
        }
