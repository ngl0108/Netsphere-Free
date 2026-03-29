from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
import re
from threading import RLock
from typing import Any, Callable, Dict, Iterable, Optional

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.discovery_hint import DiscoveryHintCacheEntry


class DiscoveryHintCacheService:
    _lock = RLock()
    _ip_hints: Dict[str, Dict[str, Any]] = {}
    _default_ttl_seconds = 3600
    _session_factory: Optional[Callable[[], Session]] = None

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _ensure_aware(value: datetime | None) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _normalize_ip(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _normalize_mac(value: Any) -> str:
        s = str(value or "").strip().lower()
        if not s:
            return ""
        s = re.sub(r"[^0-9a-f]", "", s)
        if len(s) < 12:
            return ""
        s = s[:12]
        return f"{s[0:4]}.{s[4:8]}.{s[8:12]}"

    @classmethod
    def _persistence_enabled(cls) -> bool:
        app_env = str(os.getenv("APP_ENV") or "").strip().lower()
        if app_env in {"test", "pytest"} and cls._session_factory is None:
            return False
        raw = os.getenv("DISCOVERY_HINT_CACHE_PERSIST", "true")
        return str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    @classmethod
    def _get_session_factory(cls) -> Callable[[], Session]:
        return cls._session_factory or SessionLocal

    @classmethod
    def set_session_factory_for_tests(cls, factory: Optional[Callable[[], Session]]) -> None:
        cls._session_factory = factory

    @classmethod
    def _payload_from_row(cls, row: DiscoveryHintCacheEntry) -> Dict[str, Any]:
        return {
            "ip": cls._normalize_ip(row.ip_address),
            "mac": cls._normalize_mac(row.mac_address),
            "seed_device_id": int(row.seed_device_id) if row.seed_device_id is not None else None,
            "seed_ip": cls._normalize_ip(row.seed_ip) or None,
            "seed_vendor": str(row.seed_vendor or "").strip() or None,
            "local_interface": str(row.local_interface or "").strip() or None,
            "arp_interface": str(row.arp_interface or "").strip() or None,
            "vlan": str(row.vlan or "").strip() or None,
            "neighbor_name": str(row.neighbor_name or "").strip() or None,
            "neighbor_mgmt_ip": cls._normalize_ip(row.neighbor_mgmt_ip) or None,
            "remote_interface": str(row.remote_interface or "").strip() or None,
            "protocol": str(row.protocol or "").strip() or None,
            "sources": list(row.sources or []),
            "observed_at": cls._ensure_aware(row.observed_at),
            "ttl_expires_at": cls._ensure_aware(row.ttl_expires_at),
        }

    @classmethod
    def _prune_expired(cls) -> None:
        now = cls._now()
        expired = [
            ip
            for ip, payload in cls._ip_hints.items()
            if isinstance(payload, dict)
            and isinstance(payload.get("ttl_expires_at"), datetime)
            and cls._ensure_aware(payload["ttl_expires_at"]) is not None
            and cls._ensure_aware(payload["ttl_expires_at"]) <= now
        ]
        for ip in expired:
            cls._ip_hints.pop(ip, None)

    @classmethod
    def _prune_persistent_expired(cls) -> None:
        if not cls._persistence_enabled():
            return
        db = cls._get_session_factory()()
        try:
            db.query(DiscoveryHintCacheEntry).filter(DiscoveryHintCacheEntry.ttl_expires_at <= cls._now()).delete(
                synchronize_session=False
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @classmethod
    def reset_memory_for_tests(cls) -> None:
        with cls._lock:
            cls._ip_hints = {}

    @classmethod
    def clear_for_tests(cls) -> None:
        with cls._lock:
            cls._ip_hints = {}
        if not cls._persistence_enabled():
            return
        db = cls._get_session_factory()()
        try:
            db.query(DiscoveryHintCacheEntry).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @classmethod
    def _persist_payloads(cls, payloads: Dict[str, Dict[str, Any]]) -> None:
        if not payloads or not cls._persistence_enabled():
            return
        db = cls._get_session_factory()()
        try:
            cls._prune_persistent_expired()
            ips = list(payloads.keys())
            existing_rows = {
                str(row.ip_address or "").strip(): row
                for row in db.query(DiscoveryHintCacheEntry).filter(DiscoveryHintCacheEntry.ip_address.in_(ips)).all()
            }
            for ip, payload in payloads.items():
                row = existing_rows.get(ip)
                if row is None:
                    row = DiscoveryHintCacheEntry(ip_address=ip)
                    db.add(row)
                row.mac_address = payload.get("mac")
                row.seed_device_id = payload.get("seed_device_id")
                row.seed_ip = payload.get("seed_ip")
                row.seed_vendor = payload.get("seed_vendor")
                row.local_interface = payload.get("local_interface")
                row.arp_interface = payload.get("arp_interface")
                row.vlan = payload.get("vlan")
                row.neighbor_name = payload.get("neighbor_name")
                row.neighbor_mgmt_ip = payload.get("neighbor_mgmt_ip")
                row.remote_interface = payload.get("remote_interface")
                row.protocol = payload.get("protocol")
                row.sources = list(payload.get("sources") or [])
                row.observed_at = payload.get("observed_at") or cls._now()
                row.ttl_expires_at = payload.get("ttl_expires_at") or (cls._now() + timedelta(seconds=3600))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @classmethod
    def record_seed_snapshot(
        cls,
        *,
        seed_device_id: int | None,
        seed_ip: str | None,
        seed_vendor: str | None = None,
        arp_rows: Optional[Iterable[Dict[str, Any]]] = None,
        lldp_rows: Optional[Iterable[Dict[str, Any]]] = None,
        fdb_rows: Optional[Iterable[Dict[str, Any]]] = None,
        ttl_seconds: int | None = None,
    ) -> int:
        now = cls._now()
        ttl = int(ttl_seconds or cls._default_ttl_seconds)
        ttl_expires_at = now + timedelta(seconds=max(60, ttl))

        arp_map: Dict[str, Dict[str, Any]] = {}
        for row in arp_rows or []:
            ip = cls._normalize_ip(row.get("ip"))
            mac = cls._normalize_mac(row.get("mac"))
            if not ip or not mac:
                continue
            arp_map[mac] = {
                "ip": ip,
                "mac": mac,
                "interface": str(row.get("interface") or "").strip() or None,
            }

        lldp_by_port: Dict[str, Dict[str, Any]] = {}
        for row in lldp_rows or []:
            local_interface = str(row.get("local_interface") or "").strip()
            if not local_interface:
                continue
            lldp_by_port[local_interface] = {
                "neighbor_name": str(row.get("neighbor_name") or row.get("system_name") or "").strip() or None,
                "mgmt_ip": cls._normalize_ip(row.get("mgmt_ip")) or None,
                "remote_interface": str(row.get("remote_interface") or "").strip() or None,
                "protocol": str(row.get("protocol") or row.get("discovery_source") or "").strip() or None,
            }

        recorded = 0
        payloads: Dict[str, Dict[str, Any]] = {}
        with cls._lock:
            cls._prune_expired()

            for row in fdb_rows or []:
                mac = cls._normalize_mac(row.get("mac"))
                local_interface = str(row.get("port") or row.get("local_interface") or "").strip()
                if not mac or not local_interface:
                    continue
                arp_row = arp_map.get(mac)
                if not arp_row:
                    continue
                ip = arp_row["ip"]
                lldp = lldp_by_port.get(local_interface) or {}
                payload = {
                    "ip": ip,
                    "mac": mac,
                    "seed_device_id": int(seed_device_id) if seed_device_id is not None else None,
                    "seed_ip": cls._normalize_ip(seed_ip) or None,
                    "seed_vendor": str(seed_vendor or "").strip() or None,
                    "local_interface": local_interface,
                    "arp_interface": arp_row.get("interface"),
                    "vlan": str(row.get("vlan") or "").strip() or None,
                    "neighbor_name": lldp.get("neighbor_name"),
                    "neighbor_mgmt_ip": lldp.get("mgmt_ip"),
                    "remote_interface": lldp.get("remote_interface"),
                    "protocol": lldp.get("protocol"),
                    "sources": sorted(
                        {
                            str(row.get("discovery_source") or "snmp_fdb"),
                            "snmp_arp",
                            str(lldp.get("protocol") or "seed_context"),
                        }
                    ),
                    "observed_at": now,
                    "ttl_expires_at": ttl_expires_at,
                }
                cls._ip_hints[ip] = payload
                payloads[ip] = payload
                recorded += 1

            for arp_row in arp_map.values():
                ip = arp_row["ip"]
                if ip in cls._ip_hints:
                    continue
                payload = {
                    "ip": ip,
                    "mac": arp_row["mac"],
                    "seed_device_id": int(seed_device_id) if seed_device_id is not None else None,
                    "seed_ip": cls._normalize_ip(seed_ip) or None,
                    "seed_vendor": str(seed_vendor or "").strip() or None,
                    "local_interface": None,
                    "arp_interface": arp_row.get("interface"),
                    "vlan": None,
                    "neighbor_name": None,
                    "neighbor_mgmt_ip": None,
                    "remote_interface": None,
                    "protocol": "snmp_arp",
                    "sources": ["snmp_arp"],
                    "observed_at": now,
                    "ttl_expires_at": ttl_expires_at,
                }
                cls._ip_hints[ip] = payload
                payloads[ip] = payload
                recorded += 1

        cls._persist_payloads(payloads)
        return recorded

    @classmethod
    def _lookup_ip_from_db(cls, ip: str) -> Optional[Dict[str, Any]]:
        if not cls._persistence_enabled():
            return None
        db = cls._get_session_factory()()
        try:
            cls._prune_persistent_expired()
            row = (
                db.query(DiscoveryHintCacheEntry)
                .filter(DiscoveryHintCacheEntry.ip_address == ip)
                .first()
            )
            if not row:
                return None
            payload = cls._payload_from_row(row)
            if isinstance(payload.get("ttl_expires_at"), datetime) and cls._ensure_aware(payload["ttl_expires_at"]) <= cls._now():
                return None
            return payload
        except Exception:
            return None
        finally:
            db.close()

    @classmethod
    def lookup_ip(cls, ip: str) -> Optional[Dict[str, Any]]:
        ip_key = cls._normalize_ip(ip)
        if not ip_key:
            return None
        with cls._lock:
            cls._prune_expired()
            payload = cls._ip_hints.get(ip_key)
            if isinstance(payload, dict):
                return dict(payload)

        payload = cls._lookup_ip_from_db(ip_key)
        if isinstance(payload, dict):
            with cls._lock:
                cls._ip_hints[ip_key] = dict(payload)
            return dict(payload)
        return None
