from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.settings import SystemSetting
from app.models.user import User
from app.models.user_session import UserSession
from app.services.session_service import SessionService


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def test_session_idle_timeout_revokes():
    db = _make_db()
    try:
        db.add(SystemSetting(key="session_timeout", value="1", description="d", category="General"))
        user = User(username="u1", hashed_password="x", full_name="u1", role="admin", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        sess = UserSession(
            user_id=int(user.id),
            jti="j1",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            last_seen_at=datetime.now(timezone.utc) - timedelta(minutes=2),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        db.add(sess)
        db.commit()

        ok, reason, changed = SessionService.validate_and_touch(db, user_id=int(user.id), jti="j1", touch_interval_seconds=60)
        assert ok is False
        assert reason == "idle_timeout"
        assert changed is True
        db.commit()

        refreshed = db.query(UserSession).filter(UserSession.jti == "j1").first()
        assert refreshed is not None
        assert refreshed.revoked_at is not None
    finally:
        db.close()


def test_session_touch_updates_last_seen():
    db = _make_db()
    try:
        db.add(SystemSetting(key="session_timeout", value="0", description="d", category="General"))
        user = User(username="u2", hashed_password="x", full_name="u2", role="admin", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        old_last_seen = datetime.now(timezone.utc) - timedelta(minutes=5)
        sess = UserSession(
            user_id=int(user.id),
            jti="j2",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=6),
            last_seen_at=old_last_seen,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        )
        db.add(sess)
        db.commit()

        ok, reason, changed = SessionService.validate_and_touch(db, user_id=int(user.id), jti="j2", touch_interval_seconds=1)
        assert ok is True
        assert reason == "ok"
        assert changed is True
        db.commit()

        refreshed = db.query(UserSession).filter(UserSession.jti == "j2").first()
        assert refreshed is not None
        assert refreshed.last_seen_at is not None
        refreshed_last = refreshed.last_seen_at
        if getattr(refreshed_last, "tzinfo", None) is None:
            refreshed_last = refreshed_last.replace(tzinfo=timezone.utc)
        assert refreshed_last > old_last_seen
    finally:
        db.close()


def test_session_revoke_marks_revoked_at():
    db = _make_db()
    try:
        db.add(SystemSetting(key="session_timeout", value="30", description="d", category="General"))
        user = User(username="u3", hashed_password="x", full_name="u3", role="admin", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        SessionService.create(db, user_id=int(user.id), jti="j3", expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
        db.commit()

        ok = SessionService.revoke(db, user_id=int(user.id), jti="j3")
        assert ok is True
        db.commit()

        refreshed = db.query(UserSession).filter(UserSession.jti == "j3").first()
        assert refreshed is not None
        assert refreshed.revoked_at is not None
    finally:
        db.close()


def test_session_concurrency_revokes_previous():
    db = _make_db()
    try:
        db.add(SystemSetting(key="session_timeout", value="30", description="d", category="General"))
        db.add(SystemSetting(key="max_concurrent_sessions", value="1", description="d", category="General"))
        user = User(username="u4", hashed_password="x", full_name="u4", role="admin", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        SessionService.create(db, user_id=int(user.id), jti="j4a", expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
        db.commit()

        SessionService.create(db, user_id=int(user.id), jti="j4b", expires_at=datetime.now(timezone.utc) + timedelta(minutes=10))
        db.commit()

        s1 = db.query(UserSession).filter(UserSession.jti == "j4a").first()
        s2 = db.query(UserSession).filter(UserSession.jti == "j4b").first()
        assert s1 is not None and s2 is not None
        assert s1.revoked_at is not None
        assert s2.revoked_at is None
    finally:
        db.close()
