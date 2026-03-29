import io
import zipfile
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.audit import AuditLog
from app.models import device as _device
from app.services.support_bundle_service import SupportBundleService


def test_support_bundle_zip_contains_expected_files():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.add(
            AuditLog(
                user_id=None,
                username="admin",
                ip_address="127.0.0.1",
                action="UPDATE",
                resource_type="Settings",
                resource_name="test",
                details='{"k":"v"}',
                status="success",
                timestamp=datetime.now(timezone.utc) - timedelta(hours=1),
            )
        )
        db.add(
            _device.EventLog(
                device_id=None,
                severity="info",
                event_id="TEST",
                message="hello",
                source="unit",
                timestamp=datetime.now(timezone.utc) - timedelta(hours=2),
            )
        )
        db.commit()

        data = SupportBundleService.build_zip(db, days=7, limit_per_table=100, include_app_log=False)
        z = zipfile.ZipFile(io.BytesIO(data), "r")
        names = set(z.namelist())
        assert "meta.json" in names
        assert "audit_logs.json" in names
        assert "event_logs.json" in names
    finally:
        db.close()

