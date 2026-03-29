from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core import security
from app.models.settings import SystemSetting
from app.models.user import User
from app.models.user_password_history import UserPasswordHistory


class PasswordPolicyService:
    @staticmethod
    def _get_str(db: Session, key: str, default: str) -> str:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not row or row.value is None:
            return default
        return str(row.value)

    @staticmethod
    def _get_int(db: Session, key: str, default: int) -> int:
        try:
            return int(float(PasswordPolicyService._get_str(db, key, str(default)).strip()))
        except Exception:
            return int(default)

    @staticmethod
    def _get_bool(db: Session, key: str, default: bool) -> bool:
        v = PasswordPolicyService._get_str(db, key, "true" if default else "false").strip().lower()
        return v in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def validate_password(
        db: Session,
        *,
        username: str,
        password: str,
        current_user: Optional[User] = None,
    ) -> List[str]:
        pw = str(password or "")
        uname = str(username or "")

        min_len = PasswordPolicyService._get_int(db, "password_min_length", 10)
        required_classes = PasswordPolicyService._get_int(db, "password_required_classes", 3)
        forbid_username = PasswordPolicyService._get_bool(db, "password_forbid_username", True)

        errors: List[str] = []
        if len(pw) < min_len:
            errors.append(f"Password must be at least {min_len} characters long.")

        classes = 0
        if re.search(r"[a-z]", pw):
            classes += 1
        if re.search(r"[A-Z]", pw):
            classes += 1
        if re.search(r"[0-9]", pw):
            classes += 1
        if re.search(r"[^A-Za-z0-9]", pw):
            classes += 1

        if required_classes and classes < required_classes:
            errors.append("Password must include at least 3 of: lowercase, uppercase, number, special character.")

        if forbid_username and uname and len(uname) >= 3:
            if uname.lower() in pw.lower():
                errors.append("Password must not contain the username.")

        history_count = PasswordPolicyService._get_int(db, "password_history_count", 5)
        if current_user and history_count and history_count > 0:
            recent = (
                db.query(UserPasswordHistory)
                .filter(UserPasswordHistory.user_id == current_user.id)
                .order_by(UserPasswordHistory.id.desc())
                .limit(history_count)
                .all()
            )
            for h in recent:
                if security.verify_password(pw, h.hashed_password):
                    errors.append(f"Password must not match the last {history_count} passwords.")
                    break

            if current_user.hashed_password and security.verify_password(pw, current_user.hashed_password):
                errors.append("New password must be different from the current password.")

        return errors

    @staticmethod
    def record_password(db: Session, user: User) -> None:
        hist = UserPasswordHistory(user_id=int(user.id), hashed_password=str(user.hashed_password))
        db.add(hist)

    @staticmethod
    def get_lockout_policy(db: Session) -> Tuple[int, int]:
        max_attempts = PasswordPolicyService._get_int(db, "max_login_attempts", 5)
        lockout_minutes = PasswordPolicyService._get_int(db, "lockout_minutes", 15)
        if max_attempts < 1:
            max_attempts = 1
        if lockout_minutes < 1:
            lockout_minutes = 1
        return max_attempts, lockout_minutes

    @staticmethod
    def is_locked(user: User) -> bool:
        locked_until = getattr(user, "locked_until", None)
        if not locked_until:
            return False
        try:
            if getattr(locked_until, "tzinfo", None) is None:
                return datetime.utcnow() < locked_until
            return datetime.now(timezone.utc) < locked_until
        except Exception:
            return False

    @staticmethod
    def lock_user(db: Session, user: User, lockout_minutes: int) -> None:
        now = datetime.now(timezone.utc)
        user.failed_login_attempts = int(getattr(user, "failed_login_attempts", 0) or 0)
        user.failed_login_attempts += 1
        user.locked_until = now + timedelta(minutes=float(lockout_minutes))
        db.add(user)

    @staticmethod
    def register_failed_login(db: Session, user: User) -> bool:
        max_attempts, lockout_minutes = PasswordPolicyService.get_lockout_policy(db)
        user.failed_login_attempts = int(getattr(user, "failed_login_attempts", 0) or 0) + 1
        if user.failed_login_attempts >= max_attempts:
            PasswordPolicyService.lock_user(db, user, lockout_minutes)
            return True
        db.add(user)
        return False

    @staticmethod
    def register_success_login(db: Session, user: User) -> None:
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = datetime.now(timezone.utc)
        db.add(user)

    @staticmethod
    def apply_password_expiry(db: Session, user: User) -> None:
        expire_days = PasswordPolicyService._get_int(db, "password_expire_days", 0)
        if not expire_days or expire_days <= 0:
            return
        ts = getattr(user, "password_changed_at", None)
        if not ts:
            user.must_change_password = True
            db.add(user)
            return
        now = datetime.now(timezone.utc)
        try:
            if getattr(ts, "tzinfo", None) is None:
                age_days = (datetime.utcnow() - ts).total_seconds() / 86400.0
            else:
                age_days = (now - ts).total_seconds() / 86400.0
        except Exception:
            return
        if age_days >= float(expire_days):
            user.must_change_password = True
            db.add(user)

