from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.settings import SystemSetting
from app.models.user_session import UserSession


class SessionService:
    @staticmethod
    def _get_int(db: Session, key: str, default: int) -> int:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not row or row.value is None:
            return int(default)
        try:
            return int(float(str(row.value).strip()))
        except Exception:
            return int(default)

    @staticmethod
    def get_idle_timeout_minutes(db: Session) -> int:
        v = SessionService._get_int(db, "session_timeout", 30)
        if v < 1:
            return 0
        return v

    @staticmethod
    def get_max_concurrent_sessions(db: Session) -> int:
        v = SessionService._get_int(db, "max_concurrent_sessions", 0)
        # 0 means unlimited. 1 means keep only the latest active session.
        if v <= 0:
            return 0
        return int(v)

    @staticmethod
    def enforce_concurrency(db: Session, *, user_id: int, keep_latest: int) -> bool:
        if keep_latest < 0:
            return False

        now = datetime.now(timezone.utc)
        sessions = (
            db.query(UserSession)
            .filter(
                UserSession.user_id == int(user_id),
                UserSession.revoked_at.is_(None),
            )
            .order_by(UserSession.last_seen_at.desc())
            .all()
        )
        changed = False
        kept = 0
        for s in sessions:
            expires_at = getattr(s, "expires_at", None)
            try:
                if expires_at and getattr(expires_at, "tzinfo", None) is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            except Exception:
                expires_at = None
            if expires_at and now > expires_at:
                s.revoked_at = now
                db.add(s)
                changed = True
                continue
            kept += 1
            if keep_latest == 0 or kept > keep_latest:
                s.revoked_at = now
                db.add(s)
                changed = True
        return changed

    @staticmethod
    def create(
        db: Session,
        *,
        user_id: int,
        jti: str,
        expires_at: datetime,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> UserSession:
        now = datetime.now(timezone.utc)
        max_sessions = SessionService.get_max_concurrent_sessions(db)
        if max_sessions > 0:
            SessionService.enforce_concurrency(db, user_id=int(user_id), keep_latest=max_sessions - 1)
        sess = UserSession(
            user_id=int(user_id),
            jti=str(jti),
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
            revoked_at=None,
            ip=str(ip) if ip else None,
            user_agent=str(user_agent) if user_agent else None,
        )
        db.add(sess)
        return sess

    @staticmethod
    def validate_and_touch(
        db: Session,
        *,
        user_id: int,
        jti: str,
        touch_interval_seconds: int = 60,
    ) -> Tuple[bool, str, bool]:
        now = datetime.now(timezone.utc)
        changed = False

        sess = db.query(UserSession).filter(UserSession.jti == str(jti)).first()
        if not sess:
            return False, "missing_session", False
        if int(sess.user_id) != int(user_id):
            return False, "session_user_mismatch", False
        if getattr(sess, "revoked_at", None):
            return False, "revoked", False

        expires_at = getattr(sess, "expires_at", None)
        if expires_at:
            try:
                if getattr(expires_at, "tzinfo", None) is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            except Exception:
                expires_at = None
        if expires_at and now > expires_at:
            sess.revoked_at = now
            db.add(sess)
            return False, "expired", True

        idle_minutes = SessionService.get_idle_timeout_minutes(db)
        if idle_minutes > 0:
            last_seen = getattr(sess, "last_seen_at", None) or getattr(sess, "created_at", None)
            try:
                if last_seen and getattr(last_seen, "tzinfo", None) is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
            except Exception:
                last_seen = None
            if last_seen and now - last_seen > timedelta(minutes=float(idle_minutes)):
                sess.revoked_at = now
                db.add(sess)
                return False, "idle_timeout", True

        last_seen = getattr(sess, "last_seen_at", None)
        try:
            if last_seen and getattr(last_seen, "tzinfo", None) is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
        except Exception:
            last_seen = None

        if not last_seen or (now - last_seen).total_seconds() >= float(max(1, int(touch_interval_seconds))):
            sess.last_seen_at = now
            db.add(sess)
            changed = True

        return True, "ok", changed

    @staticmethod
    def validate_for_refresh(
        db: Session,
        *,
        user_id: int,
        jti: str,
        grace_seconds: int = 120,
    ) -> Tuple[bool, str]:
        """
        Validate session for token refresh.
        Allows short grace window after `expires_at` to absorb clock drift/network delay.
        """
        now = datetime.now(timezone.utc)
        sess = db.query(UserSession).filter(UserSession.jti == str(jti)).first()
        if not sess:
            return False, "missing_session"
        if int(sess.user_id) != int(user_id):
            return False, "session_user_mismatch"
        if getattr(sess, "revoked_at", None):
            return False, "revoked"

        expires_at = getattr(sess, "expires_at", None)
        if expires_at:
            try:
                if getattr(expires_at, "tzinfo", None) is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
            except Exception:
                expires_at = None
        if not expires_at:
            return False, "expired"

        # hard-expired beyond grace
        if now > expires_at + timedelta(seconds=max(0, int(grace_seconds))):
            sess.revoked_at = now
            db.add(sess)
            return False, "expired"

        # idle timeout check (same policy as normal validation)
        idle_minutes = SessionService.get_idle_timeout_minutes(db)
        if idle_minutes > 0:
            last_seen = getattr(sess, "last_seen_at", None) or getattr(sess, "created_at", None)
            try:
                if last_seen and getattr(last_seen, "tzinfo", None) is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
            except Exception:
                last_seen = None
            if last_seen and now - last_seen > timedelta(minutes=float(idle_minutes)):
                sess.revoked_at = now
                db.add(sess)
                return False, "idle_timeout"

        return True, "ok"

    @staticmethod
    def revoke(db: Session, *, user_id: int, jti: str) -> bool:
        now = datetime.now(timezone.utc)
        sess = (
            db.query(UserSession)
            .filter(UserSession.user_id == int(user_id), UserSession.jti == str(jti))
            .first()
        )
        if not sess:
            return False
        if not getattr(sess, "revoked_at", None):
            sess.revoked_at = now
            db.add(sess)
        return True
