import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, EventLog
from app.services.device_sync_service import DeviceSyncService


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_sync_failure_creates_event_log(db, monkeypatch):
    class FakeConn:
        def __init__(self, device_info):
            self.device_info = device_info
            self.last_error = "auth failed"
        def connect(self):
            return False
        def disconnect(self):
            return None

    import app.services.device_sync_service as mod
    monkeypatch.setattr(mod, "DeviceConnection", FakeConn)

    d = Device(
        name="sw1",
        ip_address="10.0.0.10",
        device_type="cisco_ios",
        status="unknown",
        owner_id=1,
        ssh_username="admin",
        ssh_password="pw",
    )
    db.add(d)
    db.commit()
    db.refresh(d)

    res = DeviceSyncService.sync_device(db, d.id)
    assert res["status"] == "offline"

    logs = db.query(EventLog).filter(EventLog.device_id == d.id).all()
    assert any(l.event_id == "DEVICE_SYNC_FAIL" for l in logs)

