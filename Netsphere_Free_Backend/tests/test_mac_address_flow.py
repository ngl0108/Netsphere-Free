import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.device import Device
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


def test_discovery_saves_mac_and_approve_copies_to_device(db):
    job = DiscoveryJob(cidr="10.0.0.0/30", snmp_community="public", status="pending", logs="")
    db.add(job)
    db.commit()
    db.refresh(job)

    svc = DiscoveryService(db)
    svc._save_discovered_device(
        db,
        job.id,
        {
            "ip_address": "10.0.0.1",
            "hostname": "sw1",
            "vendor": "Cisco",
            "model": "X",
            "os_version": "Y",
            "snmp_status": "reachable",
            "device_type": "cisco_ios",
            "sys_object_id": "1.3.6.1.4.1.9",
            "sys_descr": "Cisco IOS",
            "vendor_confidence": 0.9,
            "chassis_candidate": False,
            "mac_address": "0011.2233.4455",
            "issues": [],
            "evidence": {},
        },
    )
    db.commit()

    dd = db.query(DiscoveredDevice).filter(DiscoveredDevice.job_id == job.id, DiscoveredDevice.ip_address == "10.0.0.1").first()
    assert dd
    assert dd.mac_address == "0011.2233.4455"

    device = svc.approve_device(dd.id)
    assert isinstance(device, Device)
    assert device.mac_address == "0011.2233.4455"

