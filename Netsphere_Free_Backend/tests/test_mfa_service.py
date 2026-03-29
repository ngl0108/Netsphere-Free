from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.settings import SystemSetting
from app.models.user import User
from app.services.mfa_service import MfaService


def _make_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def test_mfa_challenge_verify_success():
    db = _make_db()
    try:
        db.add(SystemSetting(key="enable_2fa", value="true", description="d", category="General"))
        db.add(SystemSetting(key="mfa_otp_ttl_seconds", value="300", description="d", category="General"))
        db.add(SystemSetting(key="mfa_otp_length", value="6", description="d", category="General"))
        db.add(SystemSetting(key="mfa_otp_max_attempts", value="5", description="d", category="General"))
        user = User(username="u1", email="u1@example.com", hashed_password="x", full_name="u1", role="admin", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        ch, otp = MfaService.create_email_challenge(db, user=user)
        db.commit()

        ok, verified_user, reason, changed = MfaService.verify(db, challenge_id=int(ch.id), otp=str(otp))
        assert ok is True
        assert verified_user is not None
        assert verified_user.id == user.id
        assert reason == "ok"
        assert changed is True
        db.commit()
    finally:
        db.close()


def test_mfa_invalid_otp_increments_attempts():
    db = _make_db()
    try:
        db.add(SystemSetting(key="enable_2fa", value="true", description="d", category="General"))
        db.add(SystemSetting(key="mfa_otp_ttl_seconds", value="300", description="d", category="General"))
        db.add(SystemSetting(key="mfa_otp_max_attempts", value="2", description="d", category="General"))
        user = User(username="u2", email="u2@example.com", hashed_password="x", full_name="u2", role="admin", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)

        ch, otp = MfaService.create_email_challenge(db, user=user)
        db.commit()

        ok1, _, reason1, changed1 = MfaService.verify(db, challenge_id=int(ch.id), otp="000000")
        assert ok1 is False
        assert reason1 in {"invalid_otp", "too_many_attempts"}
        assert changed1 is True
        db.commit()

        ok2, _, reason2, changed2 = MfaService.verify(db, challenge_id=int(ch.id), otp=str(otp))
        assert changed2 is True
        db.commit()

        assert ok2 is True or reason2 == "too_many_attempts"
    finally:
        db.close()
