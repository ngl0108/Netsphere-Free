from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core import config
from app.models.mfa_challenge import MfaChallenge
from app.models.settings import SystemSetting
from app.models.user import User


class MfaService:
    @staticmethod
    def _get_str(db: Session, key: str, default: str) -> str:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not row or row.value is None:
            return default
        return str(row.value)

    @staticmethod
    def _get_int(db: Session, key: str, default: int) -> int:
        try:
            return int(float(MfaService._get_str(db, key, str(default)).strip()))
        except Exception:
            return int(default)

    @staticmethod
    def _get_bool(db: Session, key: str, default: bool) -> bool:
        v = MfaService._get_str(db, key, "true" if default else "false").strip().lower()
        return v in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def is_enabled(db: Session) -> bool:
        return MfaService._get_bool(db, "enable_2fa", False)

    @staticmethod
    def _hash_otp(*, nonce: str, otp: str) -> str:
        raw = f"{config.SECRET_KEY}:{nonce}:{otp}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _generate_otp(db: Session) -> str:
        length = MfaService._get_int(db, "mfa_otp_length", 6)
        if length < 4:
            length = 4
        if length > 10:
            length = 10
        upper = 10 ** int(length)
        n = secrets.randbelow(upper)
        return str(n).zfill(int(length))

    @staticmethod
    def create_email_challenge(db: Session, *, user: User) -> Tuple[MfaChallenge, str]:
        ttl_seconds = MfaService._get_int(db, "mfa_otp_ttl_seconds", 300)
        if ttl_seconds < 30:
            ttl_seconds = 30
        if ttl_seconds > 3600:
            ttl_seconds = 3600

        otp = MfaService._generate_otp(db)
        nonce = secrets.token_urlsafe(16)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=float(ttl_seconds))
        ch = MfaChallenge(
            user_id=int(user.id),
            delivery="email",
            nonce=nonce,
            otp_hash=MfaService._hash_otp(nonce=nonce, otp=otp),
            attempts=0,
            expires_at=expires_at,
            consumed_at=None,
        )
        db.add(ch)
        db.flush()
        return ch, otp

    @staticmethod
    def verify(db: Session, *, challenge_id: int, otp: str) -> Tuple[bool, Optional[User], str, bool]:
        now = datetime.now(timezone.utc)
        changed = False

        ch = db.query(MfaChallenge).filter(MfaChallenge.id == int(challenge_id)).first()
        if not ch:
            return False, None, "missing_challenge", False

        if getattr(ch, "consumed_at", None):
            return False, None, "already_consumed", False

        expires_at = getattr(ch, "expires_at", None)
        try:
            if expires_at and getattr(expires_at, "tzinfo", None) is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except Exception:
            expires_at = None
        if expires_at and now > expires_at:
            return False, None, "expired", False

        max_attempts = MfaService._get_int(db, "mfa_otp_max_attempts", 5)
        if max_attempts < 1:
            max_attempts = 1

        ch.attempts = int(getattr(ch, "attempts", 0) or 0) + 1
        db.add(ch)
        changed = True
        if ch.attempts > max_attempts:
            return False, None, "too_many_attempts", True

        candidate = MfaService._hash_otp(nonce=str(ch.nonce), otp=str(otp or ""))
        if secrets.compare_digest(candidate, str(ch.otp_hash)):
            ch.consumed_at = now
            db.add(ch)
            user = db.query(User).filter(User.id == int(ch.user_id)).first()
            if not user:
                return False, None, "missing_user", True
            return True, user, "ok", True

        return False, None, "invalid_otp", True
