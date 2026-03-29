from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device
from app.models.settings import SystemSetting


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def test_full_ssh_sync_all_skips_when_lock_is_held(monkeypatch, db_engine):
    from app.tasks import monitoring as task_module
    from app.services.ha_service import HaService

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(task_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(HaService, "enabled", staticmethod(lambda _db: False))
    monkeypatch.setattr(HaService, "is_active", staticmethod(lambda _db: True))

    db = SessionLocal()
    db.add(
        SystemSetting(
            key="full_ssh_sync_all_lock",
            value=(datetime.utcnow() + timedelta(hours=1)).isoformat(),
            description="full_ssh_sync_all_lock",
            category="system",
        )
    )
    db.add(Device(name="lab-lock-device", ip_address="10.0.0.10", device_type="cisco_ios"))
    db.commit()
    db.close()

    out = task_module.full_ssh_sync_all()
    assert out["status"] == "skipped"
    assert out["reason"] == "lock_held"


def test_full_ssh_sync_all_runs_and_clears_lock(monkeypatch, db_engine):
    from app.tasks import monitoring as task_module
    from app.services import ssh_service
    from app.services import topology_link_service
    from app.services.ha_service import HaService

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(task_module, "SessionLocal", SessionLocal)
    monkeypatch.setattr(HaService, "enabled", staticmethod(lambda _db: False))
    monkeypatch.setattr(HaService, "is_active", staticmethod(lambda _db: True))

    class FakeConnection:
        def __init__(self, *_args, **_kwargs):
            self.driver = None

        def connect(self):
            return True

        def get_facts(self):
            return {"model": "LabSwitch", "os_version": "1.0.0", "serial_number": "SER-001"}

        def get_running_config(self):
            return "hostname lab-switch"

        def get_neighbors(self):
            return []

        def disconnect(self):
            return None

    monkeypatch.setattr(ssh_service, "DeviceConnection", FakeConnection)
    monkeypatch.setattr(
        topology_link_service.TopologyLinkService,
        "refresh_links_for_device",
        staticmethod(lambda *_args, **_kwargs: None),
    )

    db = SessionLocal()
    device = Device(name="lab-sync-device", ip_address="10.0.0.11", device_type="cisco_ios")
    db.add(device)
    db.commit()
    device_id = int(device.id)
    db.close()

    out = task_module.full_ssh_sync_all()
    assert out["status"] == "ok"
    assert out["devices"] == 1
    assert out["synced"] == 1

    db = SessionLocal()
    updated = db.query(Device).filter(Device.id == device_id).first()
    assert updated is not None
    assert updated.status == "online"
    assert updated.model == "LabSwitch"
    assert updated.serial_number == "SER-001"
    lock_row = db.query(SystemSetting).filter(SystemSetting.key == "full_ssh_sync_all_lock").first()
    assert lock_row is not None
    assert (lock_row.value or "") == ""
    db.close()
