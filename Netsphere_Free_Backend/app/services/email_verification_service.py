from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core import config
from app.models.email_verification import EmailVerification
from app.models.settings import SystemSetting
from app.models.user import User


class EmailVerificationService:
    @staticmethod
    def _get_str(db: Session, key: str, default: str) -> str:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not row or row.value is None:
            return default
        return str(row.value)

    @staticmethod
    def _get_int(db: Session, key: str, default: int) -> int:
        try:
            return int(float(EmailVerificationService._get_str(db, key, str(default)).strip()))
        except Exception:
            return int(default)

    @staticmethod
    def _hash_otp(*, nonce: str, otp: str) -> str:
        raw = f"{config.SECRET_KEY}:email-verify:{nonce}:{otp}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _generate_otp(db: Session) -> str:
        length = EmailVerificationService._get_int(db, "email_verify_otp_length", 6)
        if length < 4:
            length = 4
        if length > 10:
            length = 10
        upper = 10 ** int(length)
        n = secrets.randbelow(upper)
        return str(n).zfill(int(length))

    @staticmethod
    def get_resend_cooldown_seconds(db: Session) -> int:
        v = EmailVerificationService._get_int(db, "email_verify_resend_cooldown_seconds", 60)
        if v < 0:
            v = 0
        if v > 3600:
            v = 3600
        return v

    @staticmethod
    def get_retry_after_seconds(db: Session, *, user_id: int) -> int:
        cooldown = EmailVerificationService.get_resend_cooldown_seconds(db)
        if cooldown <= 0:
            return 0

        ch = (
            db.query(EmailVerification)
            .filter(
                EmailVerification.user_id == int(user_id),
            )
            .order_by(EmailVerification.created_at.desc())
            .first()
        )
        if not ch:
            return 0

        created_at = getattr(ch, "created_at", None)
        try:
            if created_at and getattr(created_at, "tzinfo", None) is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except Exception:
            created_at = None
        if not created_at:
            return 0

        now = datetime.now(timezone.utc)
        elapsed = (now - created_at).total_seconds()
        remain = int(cooldown - elapsed)
        if remain <= 0:
            return 0
        return remain

    @staticmethod
    def create(db: Session, *, user: User) -> Tuple[EmailVerification, str]:
        ttl_seconds = EmailVerificationService._get_int(db, "email_verify_otp_ttl_seconds", 600)
        if ttl_seconds < 60:
            ttl_seconds = 60
        if ttl_seconds > 3600:
            ttl_seconds = 3600

        otp = EmailVerificationService._generate_otp(db)
        nonce = secrets.token_urlsafe(16)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=float(ttl_seconds))
        ch = EmailVerification(
            user_id=int(user.id),
            nonce=nonce,
            otp_hash=EmailVerificationService._hash_otp(nonce=nonce, otp=otp),
            attempts=0,
            expires_at=expires_at,
            consumed_at=None,
        )
        db.add(ch)
        db.flush()
        return ch, otp

    @staticmethod
    def verify(db: Session, *, user_id: int, challenge_id: int, otp: str) -> Tuple[bool, Optional[User], str, bool]:
        now = datetime.now(timezone.utc)
        changed = False

        ch = db.query(EmailVerification).filter(EmailVerification.id == int(challenge_id)).first()
        if not ch:
            return False, None, "missing_challenge", False
        if int(ch.user_id) != int(user_id):
            return False, None, "challenge_user_mismatch", False
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

        max_attempts = EmailVerificationService._get_int(db, "email_verify_otp_max_attempts", 5)
        if max_attempts < 1:
            max_attempts = 1

        ch.attempts = int(getattr(ch, "attempts", 0) or 0) + 1
        db.add(ch)
        changed = True
        if ch.attempts > max_attempts:
            return False, None, "too_many_attempts", True

        candidate = EmailVerificationService._hash_otp(nonce=str(ch.nonce), otp=str(otp or ""))
        if secrets.compare_digest(candidate, str(ch.otp_hash)):
            ch.consumed_at = now
            db.add(ch)
            user = db.query(User).filter(User.id == int(user_id)).first()
            if not user:
                return False, None, "missing_user", True
            user.email_verified = True
            db.add(user)
            return True, user, "ok", True

        return False, None, "invalid_otp", True
