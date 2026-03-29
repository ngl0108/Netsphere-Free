from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.settings import SystemSetting
from app.models.user import User
from app.services.email_verification_service import EmailVerificationService


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def test_email_verification_verify_success_sets_flag():
    db = _make_db()
    try:
        user = User(username="u1", email="u1@example.com", hashed_password="x", full_name="u1", role="admin", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        assert bool(getattr(user, "email_verified", False)) is False

        ch, otp = EmailVerificationService.create(db, user=user)
        db.commit()

        ok, verified_user, reason, changed = EmailVerificationService.verify(
            db,
            user_id=int(user.id),
            challenge_id=int(ch.id),
            otp=str(otp),
        )
        assert ok is True
        assert verified_user is not None
        assert reason == "ok"
        assert changed is True
        db.commit()

        refreshed = db.query(User).filter(User.id == int(user.id)).first()
        assert refreshed is not None
        assert bool(getattr(refreshed, "email_verified", False)) is True
    finally:
        db.close()


def test_email_verification_wrong_user_fails():
    db = _make_db()
    try:
        user1 = User(username="u1", email="u1@example.com", hashed_password="x", full_name="u1", role="admin", is_active=True)
        user2 = User(username="u2", email="u2@example.com", hashed_password="x", full_name="u2", role="admin", is_active=True)
        db.add(user1)
        db.add(user2)
        db.commit()
        db.refresh(user1)
        db.refresh(user2)

        ch, otp = EmailVerificationService.create(db, user=user1)
        db.commit()

        ok, verified_user, reason, changed = EmailVerificationService.verify(
            db,
            user_id=int(user2.id),
            challenge_id=int(ch.id),
            otp=str(otp),
        )
        assert ok is False
        assert verified_user is None
        assert reason == "challenge_user_mismatch"
        assert changed is False
    finally:
        db.close()


def test_email_verification_resend_cooldown_returns_retry_after():
    db = _make_db()
    try:
        db.add(SystemSetting(key="email_verify_resend_cooldown_seconds", value="60", description="d", category="General"))
        user = User(username="u3", email="u3@example.com", hashed_password="x", full_name="u3", role="admin", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        ch, otp = EmailVerificationService.create(db, user=user)
        ch.created_at = datetime.now(timezone.utc)
        db.add(ch)
        db.commit()

        retry = EmailVerificationService.get_retry_after_seconds(db, user_id=int(user.id))
        assert isinstance(retry, int)
        assert 1 <= retry <= 60
    finally:
        db.close()
