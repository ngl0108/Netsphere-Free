import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.services.discovery_service import DiscoveryService


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


def test_save_discovered_device_adds_hostname_conflict_issue(db):
    existing = Device(name="core-sw", ip_address="10.0.0.10", device_type="cisco_ios", status="online", owner_id=1)
    db.add(existing)
    job = DiscoveryJob(cidr="10.0.0.0/24", snmp_community="public", status="running", logs="")
    db.add(job)
    db.commit()
    db.refresh(existing)
    db.refresh(job)

    svc = DiscoveryService(db)
    svc._save_discovered_device(
        db,
        job.id,
        {"ip_address": "10.0.0.20", "hostname": "core-sw", "vendor": "Dasan", "snmp_status": "reachable"},
    )
    db.commit()

    row = db.query(DiscoveredDevice).filter(DiscoveredDevice.job_id == job.id).first()
    assert row
    assert any((i.get("code") == "hostname_conflict") for i in (row.issues or []))
