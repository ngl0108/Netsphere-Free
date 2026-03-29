from __future__ import annotations

import logging
import os
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import jwt
from pydantic import BaseModel

DEFAULT_PUBLIC_KEY_PATH = "public_key.pem"
DEFAULT_ALGORITHM = "RS256"
DEFAULT_REVOCATION_LIST_PATH = "license_revocations.json"

logger = logging.getLogger(__name__)


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


class LicenseSchema(BaseModel):
    customer: str
    expiration: datetime
    max_devices: int
    features: List[str]
    is_valid: bool
    status: str
    sku: Optional[str] = None
    jti: Optional[str] = None
    issued_at: Optional[datetime] = None
    not_before: Optional[datetime] = None
    days_to_expiration: Optional[int] = None
    in_grace_period: bool = False
    grace_until: Optional[datetime] = None
    revoked: bool = False
    revocation_reason: Optional[str] = None
    revocation_source: Optional[str] = None


class LicenseVerifier:
    def __init__(self):
        self.public_key_path = os.getenv("LICENSE_PUBLIC_KEY_PATH", DEFAULT_PUBLIC_KEY_PATH)
        self.algorithm = os.getenv("LICENSE_JWT_ALGORITHM", DEFAULT_ALGORITHM)
        self.issuer = str(os.getenv("LICENSE_JWT_ISSUER") or "").strip() or None
        self.audience = str(os.getenv("LICENSE_JWT_AUDIENCE") or "").strip() or None
        self.leeway_seconds = int(os.getenv("LICENSE_JWT_LEEWAY_SECONDS", "30") or "30")
        self.revocation_list_path = str(
            os.getenv("LICENSE_REVOCATION_LIST_PATH", DEFAULT_REVOCATION_LIST_PATH) or DEFAULT_REVOCATION_LIST_PATH
        ).strip()
        self.expiry_grace_days = max(0, _to_int(os.getenv("LICENSE_EXPIRY_GRACE_DAYS", "0"), default=0))
        self.expiry_warning_days = max(0, _to_int(os.getenv("LICENSE_EXPIRY_WARNING_DAYS", "30"), default=30))
        self.allow_dev_fallback = self._resolve_dev_fallback_policy()
        self.public_key = self._load_public_key()
        self.cached_license: Optional[LicenseSchema] = None

    def _resolve_dev_fallback_policy(self) -> bool:
        raw = os.getenv("ALLOW_DEV_LICENSE_FALLBACK")
        if raw is not None:
            return _to_bool(raw, default=False)
        app_env = (os.getenv("APP_ENV") or "").strip().lower()
        return app_env not in {"prod", "production"}

    def _load_public_key(self) -> Optional[bytes]:
        if not os.path.exists(self.public_key_path):
            if self.allow_dev_fallback:
                logger.warning(
                    "License public key not found (%s). Dev fallback enabled.",
                    self.public_key_path,
                )
            else:
                logger.error(
                    "License public key not found (%s). Production verification requires key.",
                    self.public_key_path,
                )
            return None
        try:
            with open(self.public_key_path, "rb") as f:
                return f.read()
        except Exception:
            logger.exception("Failed to load license public key from %s", self.public_key_path)
            return None

    @staticmethod
    def _extract_features(payload: Dict[str, Any]) -> List[str]:
        raw = payload.get("features")
        if raw is None:
            return []
        if isinstance(raw, (list, tuple, set)):
            return [str(x).strip() for x in raw if str(x).strip()]
        if isinstance(raw, str):
            return [x.strip() for x in raw.split(",") if x.strip()]
        return []

    @staticmethod
    def _extract_max_devices(payload: Dict[str, Any]) -> int:
        limits = payload.get("limits") if isinstance(payload.get("limits"), dict) else {}
        value = limits.get("devices", payload.get("max_devices", 0))
        try:
            return max(0, int(value or 0))
        except Exception:
            return 0

    @staticmethod
    def _extract_customer(payload: Dict[str, Any]) -> str:
        candidate = payload.get("sub", payload.get("customer", "Unknown"))
        text = str(candidate or "").strip()
        return text or "Unknown"

    @staticmethod
    def _extract_datetime_claim(payload: Dict[str, Any], key: str) -> Optional[datetime]:
        value = payload.get(key)
        if value is None:
            return None
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None

    @staticmethod
    def _days_to_expiration(exp: datetime, now: datetime) -> int:
        delta = exp - now
        return int(delta.total_seconds() // 86400)

    def _load_revocation_map(self) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}

        env_inline = str(os.getenv("LICENSE_REVOKED_JTIS", "") or "").strip()
        if env_inline:
            for raw in env_inline.split(","):
                jti = str(raw or "").strip()
                if jti:
                    out[jti] = {"reason": "revoked_by_env", "source": "env"}

        path = Path(self.revocation_list_path)
        if not path.exists():
            return out
        try:
            raw = path.read_text(encoding="utf-8").strip()
            if not raw:
                return out
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                for item in parsed:
                    jti = str(item or "").strip()
                    if jti:
                        out[jti] = {"reason": "revoked_by_file", "source": str(path)}
                return out
            revoked_items = parsed.get("revoked") if isinstance(parsed, dict) else None
            if not isinstance(revoked_items, list):
                return out
            for row in revoked_items:
                if isinstance(row, str):
                    jti = row.strip()
                    reason = "revoked_by_file"
                elif isinstance(row, dict):
                    jti = str(row.get("jti") or "").strip()
                    reason = str(row.get("reason") or "revoked_by_file").strip() or "revoked_by_file"
                else:
                    continue
                if not jti:
                    continue
                out[jti] = {"reason": reason, "source": str(path)}
            return out
        except Exception:
            logger.exception("Failed to parse license revocation list: %s", path)
            return out

    def _check_revoked(self, payload: Dict[str, Any]) -> tuple[bool, Optional[str], Optional[str]]:
        jti = str(payload.get("jti") or "").strip()
        if not jti:
            return False, None, None
        revoked = self._load_revocation_map()
        info = revoked.get(jti)
        if not info:
            return False, None, None
        return True, str(info.get("reason") or "revoked"), str(info.get("source") or "")

    def _decode_payload(self, token: str) -> Dict[str, Any]:
        options = {"verify_aud": bool(self.audience)}
        kwargs: Dict[str, Any] = {
            "algorithms": [self.algorithm],
            "options": options,
            "leeway": max(0, int(self.leeway_seconds or 0)),
        }
        if self.issuer:
            kwargs["issuer"] = self.issuer
        if self.audience:
            kwargs["audience"] = self.audience
        payload = jwt.decode(token, self.public_key, **kwargs)
        if not isinstance(payload, dict):
            raise ValueError("decoded payload is not an object")
        return payload

    def verify_license(self, token: str) -> LicenseSchema:
        token = str(token or "").strip()
        if not token:
            return self._create_invalid_license("Empty token")
        if self.allow_dev_fallback and token == "__dev_fallback__":
            return self._create_dev_license()

        if not self.public_key:
            if self.allow_dev_fallback:
                return self._create_dev_license()
            return self._create_invalid_license("License verifier key not configured")

        try:
            payload = self._decode_payload(token)
            exp_raw = payload.get("exp")
            if exp_raw is None:
                return self._create_invalid_license("Missing exp claim", payload)
            exp = datetime.fromtimestamp(float(exp_raw), tz=timezone.utc)
            now = datetime.now(timezone.utc)

            revoked, revocation_reason, revocation_source = self._check_revoked(payload)
            if revoked:
                return self._create_invalid_license(
                    "Revoked",
                    payload,
                    revoked=True,
                    revocation_reason=revocation_reason,
                    revocation_source=revocation_source,
                )

            grace_until = None
            in_grace_period = False
            if exp < now:
                if self.expiry_grace_days > 0:
                    grace_until = exp + timedelta(days=self.expiry_grace_days)
                    if now <= grace_until:
                        in_grace_period = True
                    else:
                        return self._create_invalid_license("Expired", payload)
                else:
                    return self._create_invalid_license("Expired", payload)

            days_to_expiration = self._days_to_expiration(exp, now)
            status = "Active"
            if in_grace_period:
                status = f"Grace Period ({self.expiry_grace_days}d)"
            elif days_to_expiration <= self.expiry_warning_days:
                status = "Expiring Soon"

            return LicenseSchema(
                customer=self._extract_customer(payload),
                expiration=exp,
                max_devices=self._extract_max_devices(payload),
                features=self._extract_features(payload),
                is_valid=True,
                status=status,
                sku=(str(payload.get("sku")).strip() if payload.get("sku") is not None else None),
                jti=(str(payload.get("jti")).strip() if payload.get("jti") is not None else None),
                issued_at=self._extract_datetime_claim(payload, "iat"),
                not_before=self._extract_datetime_claim(payload, "nbf"),
                days_to_expiration=days_to_expiration,
                in_grace_period=bool(in_grace_period),
                grace_until=grace_until,
                revoked=False,
            )
        except jwt.ExpiredSignatureError:
            return self._create_invalid_license("Expired")
        except jwt.PyJWTError as e:
            return self._create_invalid_license(f"Invalid Signature: {str(e)}")
        except Exception as e:
            return self._create_invalid_license(f"Error: {str(e)}")

    def _create_invalid_license(
        self,
        status: str,
        payload: dict | None = None,
        *,
        revoked: bool = False,
        revocation_reason: Optional[str] = None,
        revocation_source: Optional[str] = None,
    ) -> LicenseSchema:
        return LicenseSchema(
            customer=(str(payload.get("sub", "Unknown")) if payload else "Unknown"),
            expiration=datetime.now(timezone.utc),
            max_devices=0,
            features=[],
            is_valid=False,
            status=status,
            sku=(str(payload.get("sku")).strip() if isinstance(payload, dict) and payload.get("sku") is not None else None),
            jti=(str(payload.get("jti")).strip() if isinstance(payload, dict) and payload.get("jti") is not None else None),
            issued_at=(self._extract_datetime_claim(payload, "iat") if isinstance(payload, dict) else None),
            not_before=(self._extract_datetime_claim(payload, "nbf") if isinstance(payload, dict) else None),
            days_to_expiration=None,
            in_grace_period=False,
            grace_until=None,
            revoked=bool(revoked),
            revocation_reason=revocation_reason,
            revocation_source=revocation_source,
        )

    def _create_dev_license(self) -> LicenseSchema:
        return LicenseSchema(
            customer="Developer",
            expiration=datetime(2099, 12, 31, tzinfo=timezone.utc),
            max_devices=999,
            features=["all"],
            is_valid=True,
            status="Developer Mode",
            sku="DEV",
            jti="__dev_fallback__",
            days_to_expiration=99999,
            in_grace_period=False,
            revoked=False,
        )


license_verifier = LicenseVerifier()
