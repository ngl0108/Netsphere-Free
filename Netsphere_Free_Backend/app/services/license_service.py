from __future__ import annotations

import logging
import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
from sqlalchemy.orm import Session

from app.core.field_encryption import get_fernet
from app.core.license import LicenseSchema, license_verifier
from app.models.license_state import LicenseState
from app.models.device import Device

logger = logging.getLogger(__name__)


class LicenseService:
    _ENC_PREFIX = "enc:"
    _REVOCATION_FILE_FALLBACK = "license_revocations.json"

    @staticmethod
    def _allow_license_file_fallback() -> bool:
        raw = (os.getenv("ALLOW_LICENSE_FILE_FALLBACK") or "").strip().lower()
        if raw in {"1", "true", "yes", "y", "on"}:
            return True
        if raw in {"0", "false", "no", "n", "off"}:
            return False
        return (os.getenv("APP_ENV") or "").strip().lower() not in {"prod", "production"}

    @staticmethod
    def _is_encrypted_token(value: Any) -> bool:
        return isinstance(value, str) and value.startswith(LicenseService._ENC_PREFIX)

    @staticmethod
    def _encrypt_token(token: str) -> str:
        plain = str(token or "").strip()
        if not plain:
            return ""
        if LicenseService._is_encrypted_token(plain):
            return plain
        encrypted = get_fernet().encrypt(plain.encode("utf-8")).decode("utf-8")
        return f"{LicenseService._ENC_PREFIX}{encrypted}"

    @staticmethod
    def _decrypt_token(stored_value: str) -> Optional[str]:
        raw = str(stored_value or "").strip()
        if not raw:
            return None
        if not LicenseService._is_encrypted_token(raw):
            return raw
        token = raw[len(LicenseService._ENC_PREFIX):]
        try:
            return get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
        except Exception:
            logger.exception("Failed to decrypt stored license token")
            return None

    @staticmethod
    def _revocation_file_path() -> Path:
        raw = str(getattr(license_verifier, "revocation_list_path", "") or "").strip()
        if not raw:
            raw = LicenseService._REVOCATION_FILE_FALLBACK
        return Path(raw)

    @staticmethod
    def _load_revocations() -> list[dict[str, Any]]:
        path = LicenseService._revocation_file_path()
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8").strip()
            if not text:
                return []
            parsed = json.loads(text)
        except Exception:
            logger.exception("Failed to load revocation list: %s", path)
            return []

        if isinstance(parsed, list):
            out = []
            for item in parsed:
                jti = str(item or "").strip()
                if jti:
                    out.append({"jti": jti, "reason": "revoked_by_file"})
            return out

        if not isinstance(parsed, dict):
            return []
        rows = parsed.get("revoked")
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, str):
                jti = row.strip()
                if jti:
                    out.append({"jti": jti, "reason": "revoked_by_file"})
                continue
            if not isinstance(row, dict):
                continue
            jti = str(row.get("jti") or "").strip()
            if not jti:
                continue
            out.append(
                {
                    "jti": jti,
                    "reason": str(row.get("reason") or "revoked_by_file").strip() or "revoked_by_file",
                    "revoked_at": str(row.get("revoked_at") or "").strip() or None,
                    "revoked_by": str(row.get("revoked_by") or "").strip() or None,
                }
            )
        return out

    @staticmethod
    def _save_revocations(rows: list[dict[str, Any]]) -> None:
        path = LicenseService._revocation_file_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"revoked": rows}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def list_revocations() -> dict[str, Any]:
        rows = LicenseService._load_revocations()
        return {
            "revocation_file": str(LicenseService._revocation_file_path()),
            "count": len(rows),
            "revoked": rows,
        }

    @staticmethod
    def _extract_jti_from_token(token: str) -> Optional[str]:
        token_str = str(token or "").strip()
        if not token_str:
            return None
        try:
            payload = jwt.decode(
                token_str,
                options={
                    "verify_signature": False,
                    "verify_exp": False,
                    "verify_nbf": False,
                    "verify_iat": False,
                    "verify_aud": False,
                    "verify_iss": False,
                },
            )
            if isinstance(payload, dict):
                jti = str(payload.get("jti") or "").strip()
                return jti or None
        except Exception:
            return None
        return None

    @staticmethod
    def revoke_jti(jti: str, *, reason: str = "manual_revoke", revoked_by: str = "system") -> dict[str, Any]:
        normalized_jti = str(jti or "").strip()
        if not normalized_jti:
            raise ValueError("jti is required")
        normalized_reason = str(reason or "manual_revoke").strip() or "manual_revoke"
        normalized_actor = str(revoked_by or "system").strip() or "system"

        rows = LicenseService._load_revocations()
        for row in rows:
            if str(row.get("jti") or "").strip() == normalized_jti:
                row["reason"] = normalized_reason
                row["revoked_by"] = normalized_actor
                row["revoked_at"] = datetime.now(timezone.utc).isoformat()
                LicenseService._save_revocations(rows)
                return {"ok": True, "revoked": row, "updated": True}

        new_row = {
            "jti": normalized_jti,
            "reason": normalized_reason,
            "revoked_by": normalized_actor,
            "revoked_at": datetime.now(timezone.utc).isoformat(),
        }
        rows.append(new_row)
        LicenseService._save_revocations(rows)
        return {"ok": True, "revoked": new_row, "updated": False}

    @staticmethod
    def unrevoke_jti(jti: str) -> dict[str, Any]:
        normalized_jti = str(jti or "").strip()
        if not normalized_jti:
            raise ValueError("jti is required")
        rows = LicenseService._load_revocations()
        kept: list[dict[str, Any]] = []
        removed = False
        for row in rows:
            if str(row.get("jti") or "").strip() == normalized_jti:
                removed = True
                continue
            kept.append(row)
        if removed:
            LicenseService._save_revocations(kept)
        return {"ok": True, "jti": normalized_jti, "removed": removed}

    @staticmethod
    def revoke_installed_license(db: Session, *, reason: str = "manual_revoke", revoked_by: str = "system") -> dict[str, Any]:
        token = LicenseService.get_installed_token(db)
        if not token:
            raise ValueError("no installed license")
        jti = LicenseService._extract_jti_from_token(token)
        if not jti:
            raise ValueError("installed license has no jti claim")
        out = LicenseService.revoke_jti(jti, reason=reason, revoked_by=revoked_by)
        out["license_status"] = LicenseService.get_status(db)
        return out

    @staticmethod
    def _get_row(db: Session) -> LicenseState:
        row = db.query(LicenseState).filter(LicenseState.id == 1).first()
        if row:
            return row
        row = LicenseState(id=1, license_jwt=None)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @staticmethod
    def get_installed_token(db: Session) -> Optional[str]:
        row = db.query(LicenseState).filter(LicenseState.id == 1).first()
        if not row:
            return None
        stored_value = (row.license_jwt or "").strip()
        if not stored_value:
            return None

        plain = LicenseService._decrypt_token(stored_value)
        if not plain:
            return None

        # Backward-compatible migration: plaintext -> encrypted at rest
        if not LicenseService._is_encrypted_token(stored_value):
            try:
                row.license_jwt = LicenseService._encrypt_token(plain)
                db.add(row)
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("Failed to migrate plaintext license token to encrypted storage")
        return plain

    @staticmethod
    def verify_token(token: str) -> LicenseSchema:
        return license_verifier.verify_license(token)

    @staticmethod
    def get_effective_license(db: Session) -> Optional[LicenseSchema]:
        token = LicenseService.get_installed_token(db)
        if token:
            return LicenseService.verify_token(token)
        if LicenseService._allow_license_file_fallback():
            try:
                with open("license.key", "r", encoding="utf-8") as f:
                    token2 = f.read().strip()
                if token2:
                    return LicenseService.verify_token(token2)
            except Exception:
                return None
        if getattr(license_verifier, "allow_dev_fallback", False):
            return LicenseService.verify_token("__dev_fallback__")
        return None

    @staticmethod
    def get_status(db: Session) -> Dict[str, Any]:
        token = LicenseService.get_installed_token(db)
        lic = None
        if token:
            lic = LicenseService.verify_token(token)
        else:
            lic = LicenseService.get_effective_license(db)

        device_count = int(db.query(Device).count())
        revocations = LicenseService._load_revocations()
        payload: Dict[str, Any] = {
            "installed": bool(token),
            "device_count": device_count,
            "revocation_count": len(revocations),
        }
        if lic:
            payload["license"] = lic.model_dump()
            payload["max_devices"] = int(lic.max_devices or 0)
            payload["features"] = list(lic.features or [])
            payload["is_valid"] = bool(lic.is_valid)
            payload["status"] = str(lic.status)
            payload["expires_at"] = lic.expiration.isoformat() if getattr(lic, "expiration", None) else None
        else:
            payload["license"] = None
            payload["max_devices"] = 100
            payload["features"] = []
            payload["is_valid"] = False
            payload["status"] = "Not installed"
            payload["expires_at"] = None
        return payload

    @staticmethod
    def install(db: Session, token: str) -> Dict[str, Any]:
        token = str(token or "").strip()
        if not token:
            raise ValueError("license token is empty")
        lic = LicenseService.verify_token(token)
        if not lic.is_valid:
            raise ValueError(f"License invalid: {lic.status}")
        try:
            encrypted_token = LicenseService._encrypt_token(token)
        except Exception as exc:
            raise ValueError(f"Failed to encrypt license token at rest: {exc}") from exc
        row = LicenseService._get_row(db)
        row.license_jwt = encrypted_token
        row.installed_at = datetime.now(timezone.utc)
        db.add(row)
        db.commit()
        return LicenseService.get_status(db)

    @staticmethod
    def uninstall(db: Session) -> Dict[str, Any]:
        row = LicenseService._get_row(db)
        row.license_jwt = None
        db.add(row)
        db.commit()
        return LicenseService.get_status(db)
