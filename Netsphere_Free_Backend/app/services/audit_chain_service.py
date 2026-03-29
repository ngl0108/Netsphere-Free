from __future__ import annotations

import hmac
import json
import socket
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.core import config
from app.models.audit import AuditLog
from app.models.settings import SystemSetting


class AuditChainService:
    @staticmethod
    def _get_setting(db: Session, key: str, default: str = "") -> str:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not row or row.value is None:
            return default
        return str(row.value)

    @staticmethod
    def _get_bool(db: Session, key: str, default: bool) -> bool:
        v = AuditChainService._get_setting(db, key, "true" if default else "false").strip().lower()
        return v in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _get_int(db: Session, key: str, default: int) -> int:
        try:
            return int(float(AuditChainService._get_setting(db, key, str(default)).strip()))
        except Exception:
            return int(default)

    @staticmethod
    def enabled(db: Session) -> bool:
        return AuditChainService._get_bool(db, "audit_chain_enabled", True)

    @staticmethod
    def _hmac_key(db: Session) -> bytes:
        k = AuditChainService._get_setting(db, "audit_hmac_key", "").strip()
        if k:
            return k.encode("utf-8")
        return str(config.SECRET_KEY).encode("utf-8")

    @staticmethod
    def canonical_payload(log: AuditLog, prev_hash: Optional[str], version: int = 1) -> str:
        def iso(dt: Any) -> Optional[str]:
            if not dt:
                return None
            try:
                if getattr(dt, "tzinfo", None) is None:
                    return dt.replace(tzinfo=timezone.utc).isoformat()
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                return None

        payload: Dict[str, Any] = {
            "v": int(version),
            "id": int(getattr(log, "id", 0) or 0),
            "timestamp": iso(getattr(log, "timestamp", None)),
            "user_id": getattr(log, "user_id", None),
            "username": getattr(log, "username", None),
            "ip_address": getattr(log, "ip_address", None),
            "action": getattr(log, "action", None),
            "resource_type": getattr(log, "resource_type", None),
            "resource_name": getattr(log, "resource_name", None),
            "details": getattr(log, "details", None),
            "status": getattr(log, "status", None),
            "prev_hash": prev_hash or "",
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True, default=str)

    @staticmethod
    def compute_hash(db: Session, canonical: str) -> str:
        key = AuditChainService._hmac_key(db)
        return hmac.new(key, canonical.encode("utf-8"), sha256).hexdigest()

    @staticmethod
    def get_latest_hash(db: Session) -> Optional[str]:
        row = (
            db.query(AuditLog)
            .filter(AuditLog.chain_hash.isnot(None))
            .order_by(AuditLog.id.desc())
            .first()
        )
        if not row:
            return None
        return getattr(row, "chain_hash", None) or None

    @staticmethod
    def seal_entry(db: Session, log: AuditLog) -> None:
        version = int(getattr(log, "chain_version", 1) or 1)
        prev_hash = (
            db.query(AuditLog)
            .filter(AuditLog.chain_hash.isnot(None), AuditLog.id != int(getattr(log, "id", 0) or 0))
            .order_by(AuditLog.id.desc())
            .first()
        )
        prev_hash = getattr(prev_hash, "chain_hash", None) if prev_hash else None
        canonical = AuditChainService.canonical_payload(log, prev_hash, version=version)
        h = AuditChainService.compute_hash(db, canonical)
        log.chain_prev_hash = prev_hash
        log.chain_hash = h
        log.chain_alg = "HMAC-SHA256"
        log.chain_version = version

    @staticmethod
    def verify_chain(db: Session, days: int = 30, limit: int = 20000) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=int(days) if days and days > 0 else 30)
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.timestamp >= since)
            .order_by(AuditLog.id.asc())
            .limit(int(limit))
            .all()
        )
        ok = True
        missing = 0
        broken_at: Optional[int] = None
        last_hash: Optional[str] = None
        checked = 0
        for r in rows:
            checked += 1
            if not r.chain_hash or r.chain_alg != "HMAC-SHA256":
                missing += 1
                last_hash = r.chain_hash or last_hash
                continue
            canonical = AuditChainService.canonical_payload(r, r.chain_prev_hash, version=int(r.chain_version or 1))
            expected = AuditChainService.compute_hash(db, canonical)
            if expected != r.chain_hash:
                ok = False
                broken_at = r.id
                break
            if last_hash and (r.chain_prev_hash or "") != (last_hash or ""):
                ok = False
                broken_at = r.id
                break
            last_hash = r.chain_hash

        return {
            "ok": ok,
            "checked": checked,
            "missing": missing,
            "broken_at_id": broken_at,
            "since": since.isoformat(),
            "now": now.isoformat(),
        }

    @staticmethod
    def backfill_chain(db: Session, days: int = 365, limit: int = 200000) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=int(days) if days and days > 0 else 365)
        rows = (
            db.query(AuditLog)
            .filter(AuditLog.timestamp >= since)
            .order_by(AuditLog.id.asc())
            .limit(int(limit))
            .all()
        )
        prev_hash: Optional[str] = None
        updated = 0
        for r in rows:
            if r.chain_hash and r.chain_alg == "HMAC-SHA256":
                prev_hash = r.chain_hash
                continue
            canonical = AuditChainService.canonical_payload(r, prev_hash, version=1)
            h = AuditChainService.compute_hash(db, canonical)
            r.chain_prev_hash = prev_hash
            r.chain_hash = h
            r.chain_alg = "HMAC-SHA256"
            r.chain_version = 1
            db.add(r)
            updated += 1
            prev_hash = h
        db.commit()
        return {"updated": updated, "since": since.isoformat(), "now": now.isoformat()}

    @staticmethod
    def _syslog_enabled(db: Session) -> bool:
        return AuditChainService._get_bool(db, "audit_forward_syslog_enabled", False)

    @staticmethod
    def send_syslog(db: Session, msg: str) -> None:
        if not AuditChainService._syslog_enabled(db):
            return
        host = AuditChainService._get_setting(db, "audit_forward_syslog_host", "").strip()
        if not host:
            return
        port = AuditChainService._get_int(db, "audit_forward_syslog_port", 514)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.sendto(msg.encode("utf-8"), (host, int(port)))
            finally:
                sock.close()
        except Exception:
            return
