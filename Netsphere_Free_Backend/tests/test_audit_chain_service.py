from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.audit import AuditLog
from app.models.settings import SystemSetting
from app.services.audit_chain_service import AuditChainService


def test_audit_chain_seal_and_verify_ok():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add(SystemSetting(key="audit_chain_enabled", value="true", description="d", category="General"))
        db.add(SystemSetting(key="audit_hmac_key", value="unit-test-key", description="d", category="General"))
        db.commit()

        a1 = AuditLog(
            user_id=None,
            username="admin",
            ip_address="127.0.0.1",
            action="POST",
            resource_type="devices",
            resource_name="/api/v1/devices",
            details="ok",
            status="success",
            timestamp=datetime.now(timezone.utc),
        )
        db.add(a1)
        db.flush()
        AuditChainService.seal_entry(db, a1)
        db.commit()

        a2 = AuditLog(
            user_id=None,
            username="admin",
            ip_address="127.0.0.1",
            action="PUT",
            resource_type="devices",
            resource_name="/api/v1/devices/1",
            details="ok2",
            status="success",
            timestamp=datetime.now(timezone.utc),
        )
        db.add(a2)
        db.flush()
        AuditChainService.seal_entry(db, a2)
        db.commit()

        res = AuditChainService.verify_chain(db, days=1, limit=100)
        assert res["ok"] is True
    finally:
        db.close()

