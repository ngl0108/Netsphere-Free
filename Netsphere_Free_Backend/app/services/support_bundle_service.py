from __future__ import annotations

import io
import json
import os
import re
import zipfile
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.device import EventLog
from app.models.settings import SystemSetting
from app.services.license_service import LicenseService


class SupportBundleService:
    _RESTORE_MAX_ZIP_BYTES = 20 * 1024 * 1024  # 20MB

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _iso(dt: Optional[datetime]) -> Optional[str]:
        if not dt:
            return None
        try:
            if getattr(dt, "tzinfo", None) is None:
                return dt.replace(tzinfo=timezone.utc).isoformat()
            return dt.astimezone(timezone.utc).isoformat()
        except Exception:
            return None

    @staticmethod
    def _mask_setting(key: str, value: Any) -> Any:
        k = str(key or "").lower()
        if any(x in k for x in ["password", "secret", "token", "private_key", "license", "encryption_key"]):
            if value in (None, "", "********"):
                return value
            return "********"
        return value

    @staticmethod
    def _collect_settings(db: Session) -> Dict[str, Any]:
        rows = db.query(SystemSetting).all()
        out: Dict[str, Any] = {}
        for r in rows:
            out[str(r.key)] = SupportBundleService._mask_setting(r.key, r.value)
        return out

    @staticmethod
    def _collect_audit_logs(db: Session, since: datetime, limit: int) -> List[Dict[str, Any]]:
        q = (
            db.query(AuditLog)
            .filter(AuditLog.timestamp >= since)
            .order_by(AuditLog.timestamp.desc())
            .limit(int(limit))
        )
        out: List[Dict[str, Any]] = []
        for r in q.all():
            out.append(
                {
                    "id": r.id,
                    "timestamp": SupportBundleService._iso(r.timestamp),
                    "user_id": r.user_id,
                    "username": r.username,
                    "ip_address": r.ip_address,
                    "action": r.action,
                    "resource_type": r.resource_type,
                    "resource_name": r.resource_name,
                    "details": r.details,
                    "status": r.status,
                }
            )
        return out

    @staticmethod
    def _collect_event_logs(db: Session, since: datetime, limit: int) -> List[Dict[str, Any]]:
        q = (
            db.query(EventLog)
            .filter(EventLog.timestamp >= since)
            .order_by(EventLog.timestamp.desc())
            .limit(int(limit))
        )
        out: List[Dict[str, Any]] = []
        for r in q.all():
            out.append(
                {
                    "id": r.id,
                    "timestamp": SupportBundleService._iso(r.timestamp),
                    "device_id": r.device_id,
                    "severity": r.severity,
                    "event_id": r.event_id,
                    "source": r.source,
                    "message": r.message,
                }
            )
        return out

    @staticmethod
    def _read_app_log_bytes(max_bytes: int = 1024 * 1024) -> Optional[bytes]:
        candidates = []
        env_file = os.getenv("LOG_FILE")
        if env_file:
            candidates.append(env_file)
        candidates.append(os.path.join("logs", "app.log"))

        for path in candidates:
            try:
                if not path or not os.path.exists(path):
                    continue
                size = os.path.getsize(path)
                with open(path, "rb") as f:
                    if size <= max_bytes:
                        return f.read()
                    f.seek(max(0, size - max_bytes))
                    return f.read()
            except Exception:
                continue
        return None

    @staticmethod
    def _mask_text(s: str) -> str:
        if not s:
            return s
        out = str(s)
        out = re.sub(r"\b(\d{1,3}\.){3}\d{1,3}\b", "***.***.***.***", out)
        out = re.sub(r"\b([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b", "**:**:**:**:**:**", out)
        out = re.sub(r"\b([0-9A-Fa-f]{2}-){5}[0-9A-Fa-f]{2}\b", "**-**-**-**-**-**", out)
        return out

    @staticmethod
    def _json_default(value: Any) -> str:
        if isinstance(value, datetime):
            if getattr(value, "tzinfo", None) is None:
                return value.replace(tzinfo=timezone.utc).isoformat()
            return value.astimezone(timezone.utc).isoformat()
        return str(value)

    @staticmethod
    def _json_dumps(payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=SupportBundleService._json_default)

    @staticmethod
    def _collect_system_info() -> Dict[str, Any]:
        info = {}
        # Disk Usage
        try:
            base_path = "/" if os.name == "posix" else os.path.abspath(os.sep)
            total, used, free = shutil.disk_usage(base_path)
            info["disk"] = {
                "total_gb": round(total / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "free_gb": round(free / (1024**3), 2),
                "percent": round((used / total) * 100, 1)
            }
        except Exception as e:
            info["disk"] = str(e)
            
        # Memory / Uptime / Network (Generic)
        cmds = {
            "memory": ["free", "-m"] if os.name == 'posix' else [],
            "uptime": ["uptime"] if os.name == 'posix' else [],
            "network": ["ip", "addr"] if os.name == 'posix' else [],
        }
        
        for k, cmd in cmds.items():
            if not cmd:
                continue
            try:
                out = subprocess.check_output(cmd, timeout=2, stderr=subprocess.STDOUT).decode(errors="replace").strip()
                info[k] = SupportBundleService._mask_text(out) if k == "network" else out
            except Exception:
                pass
                
        return info

    @staticmethod
    def build_zip(
        db: Session,
        *,
        days: int = 7,
        limit_per_table: int = 5000,
        include_app_log: bool = True,
    ) -> bytes:
        now = SupportBundleService._utcnow()
        days_i = int(days) if days is not None else 7
        if days_i < 1:
            days_i = 1
        limit_i = int(limit_per_table) if limit_per_table is not None else 5000
        if limit_i < 1:
            limit_i = 1

        since = now - timedelta(days=days_i)
        settings = SupportBundleService._collect_settings(db)
        license_status = LicenseService.get_status(db)
        if isinstance(license_status, dict):
            license_status.pop("license_jwt", None)

        audit_logs = SupportBundleService._collect_audit_logs(db, since, limit_i)
        event_logs = SupportBundleService._collect_event_logs(db, since, limit_i)
        sys_info = SupportBundleService._collect_system_info()

        meta = {
            "generated_at": now.isoformat(),
            "range": {"since": since.isoformat(), "days": days_i},
            "counts": {"audit_logs": len(audit_logs), "event_logs": len(event_logs)},
            "license": license_status,
            "settings": settings,
            "system_info": sys_info,
        }

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("meta.json", SupportBundleService._json_dumps(meta))
            zf.writestr("audit_logs.json", SupportBundleService._json_dumps(audit_logs))
            zf.writestr("event_logs.json", SupportBundleService._json_dumps(event_logs))
            if include_app_log:
                data = SupportBundleService._read_app_log_bytes()
                if data:
                    zf.writestr("app.log", data)

        return buf.getvalue()

    @staticmethod
    def _load_meta_from_zip(data: bytes) -> Dict[str, Any]:
        raw = bytes(data or b"")
        if not raw:
            raise ValueError("bundle is empty")
        if len(raw) > SupportBundleService._RESTORE_MAX_ZIP_BYTES:
            raise ValueError("bundle is too large")

        try:
            with zipfile.ZipFile(io.BytesIO(raw), mode="r") as zf:
                names = set(zf.namelist())
                if "meta.json" not in names:
                    raise ValueError("meta.json not found in bundle")
                with zf.open("meta.json") as f:
                    meta_raw = f.read()
        except zipfile.BadZipFile as e:
            raise ValueError("invalid zip bundle") from e

        try:
            payload = json.loads(meta_raw.decode("utf-8", errors="replace"))
        except Exception as e:
            raise ValueError("meta.json is not valid JSON") from e

        if not isinstance(payload, dict):
            raise ValueError("meta.json root must be an object")
        return payload

    @staticmethod
    def _sanitize_restore_settings(raw_settings: Dict[str, Any]) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key, value in dict(raw_settings or {}).items():
            k = str(key or "").strip()
            if not k:
                continue
            if value in (None, "", "********"):
                continue
            if any(x in k.lower() for x in ["password", "secret", "token", "private_key", "license", "encryption_key"]):
                continue
            out[k] = str(value)
        return out

    @staticmethod
    def restore_from_zip(
        db: Session,
        *,
        data: bytes,
        apply: bool = True,
        restore_settings: bool = True,
    ) -> Dict[str, Any]:
        meta = SupportBundleService._load_meta_from_zip(data)
        settings_payload = meta.get("settings") if isinstance(meta.get("settings"), dict) else {}
        sanitized_settings = SupportBundleService._sanitize_restore_settings(settings_payload)

        result: Dict[str, Any] = {
            "status": "preview" if not bool(apply) else "applied",
            "restored": {"settings": 0},
            "available": {"settings": len(sanitized_settings)},
            "skipped": {"settings": max(0, int(len(settings_payload or {})) - int(len(sanitized_settings)))},
        }

        if not bool(restore_settings):
            result["status"] = "skipped"
            result["message"] = "restore_settings=false; no changes applied"
            return result

        if not bool(apply):
            result["message"] = "preview only; no changes applied"
            return result

        restored_settings = 0
        for key, value in sanitized_settings.items():
            row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if row:
                row.value = str(value)
            else:
                db.add(SystemSetting(key=key, value=str(value), description="Restored from support bundle", category="General"))
            restored_settings += 1

        db.commit()
        result["restored"]["settings"] = int(restored_settings)
        result["message"] = "restore applied"
        return result
