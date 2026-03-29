import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.session import Base
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


def test_save_discovered_device_upserts_by_job_and_ip(db):
    job = DiscoveryJob(cidr="10.0.0.0/30", snmp_community="public", status="running", logs="")
    db.add(job)
    db.commit()
    db.refresh(job)

    svc = DiscoveryService(db)

    svc._save_discovered_device(
        db,
        job.id,
        {"ip_address": "10.0.0.1", "hostname": "sw1", "vendor": "Cisco", "model": "2960", "os_version": "15", "snmp_status": "reachable", "issues": [{"code": "x", "severity": "info", "message": "m"}]},
    )
    db.commit()

    svc._save_discovered_device(
        db,
        job.id,
        {"ip_address": "10.0.0.1", "hostname": "sw1.domain.local", "vendor": "Cisco", "model": "2960X", "os_version": "16", "snmp_status": "reachable", "issues": [{"code": "y", "severity": "warn", "message": "n"}]},
    )
    db.commit()

    rows = db.query(DiscoveredDevice).filter(DiscoveredDevice.job_id == job.id).all()
    assert len(rows) == 1
    assert rows[0].model == "2960X"
    assert rows[0].os_version == "16"
    assert rows[0].issues and rows[0].issues[0]["code"] == "y"
