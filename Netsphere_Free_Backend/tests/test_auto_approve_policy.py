import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.device import Device
from app.models.settings import SystemSetting
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


def test_auto_approve_job_filters_by_conf_snmp_and_issues(db):
    db.add(SystemSetting(key="auto_approve_enabled", value="true", description="", category="system"))
    db.add(SystemSetting(key="auto_approve_min_vendor_confidence", value="0.8", description="", category="system"))
    db.add(SystemSetting(key="auto_approve_require_snmp_reachable", value="true", description="", category="system"))
    db.add(SystemSetting(key="auto_approve_block_severities", value="error", description="", category="system"))
    job = DiscoveryJob(cidr="10.0.0.0/30", snmp_community="public", status="pending", logs="", snmp_version="v2c", snmp_port=161)
    db.add(job)
    db.commit()
    db.refresh(job)

    db.add_all(
        [
            DiscoveredDevice(
                job_id=job.id,
                ip_address="10.0.0.1",
                hostname="sw1",
                vendor="Cisco",
                snmp_status="reachable",
                vendor_confidence=0.9,
                issues=[],
                status="new",
            ),
            DiscoveredDevice(
                job_id=job.id,
                ip_address="10.0.0.2",
                hostname="sw2",
                vendor="Cisco",
                snmp_status="reachable",
                vendor_confidence=0.5,
                issues=[],
                status="new",
            ),
            DiscoveredDevice(
                job_id=job.id,
                ip_address="10.0.0.3",
                hostname="sw3",
                vendor="Cisco",
                snmp_status="reachable",
                vendor_confidence=0.95,
                issues=[{"code": "x", "severity": "error", "message": "bad"}],
                status="new",
            ),
            DiscoveredDevice(
                job_id=job.id,
                ip_address="10.0.0.4",
                hostname="sw4",
                vendor="Cisco",
                snmp_status="unreachable",
                vendor_confidence=0.95,
                issues=[],
                status="new",
            ),
        ]
    )
    db.commit()

    res = DiscoveryService(db).auto_approve_job(job.id)
    assert res["approved_count"] == 1
    assert len(res["device_ids"]) == 1

    approved = db.query(DiscoveredDevice).filter(DiscoveredDevice.job_id == job.id, DiscoveredDevice.status == "approved").all()
    assert len(approved) == 1
    assert approved[0].ip_address == "10.0.0.1"

    devices = db.query(Device).all()
    assert len(devices) == 1
    assert devices[0].ip_address == "10.0.0.1"


def test_auto_approve_job_uses_platform_fingerprint_for_created_device_type(db):
    db.add(SystemSetting(key="auto_approve_enabled", value="true", description="", category="system"))
    db.add(SystemSetting(key="auto_approve_min_vendor_confidence", value="0.8", description="", category="system"))
    job = DiscoveryJob(cidr="10.10.10.0/30", snmp_community="public", status="pending", logs="", snmp_version="v2c", snmp_port=161)
    db.add(job)
    db.commit()
    db.refresh(job)

    db.add(
        DiscoveredDevice(
            job_id=job.id,
            ip_address="10.10.10.10",
            hostname="core-n9k-01",
            vendor="Unknown",
            model="C93180YC-FX",
            os_version="Version 10.2(3)",
            sys_object_id="1.3.6.1.4.1.9.1.1208",
            sys_descr="Cisco Nexus Operating System (NX-OS) Software, Version 10.2(3), Nexus9000 C93180YC-FX",
            snmp_status="reachable",
            vendor_confidence=0.95,
            issues=[],
            status="new",
        )
    )
    db.commit()

    res = DiscoveryService(db).auto_approve_job(job.id)

    assert res["approved_count"] == 1
    device = db.query(Device).filter(Device.ip_address == "10.10.10.10").one()
    assert device.device_type == "cisco_nxos"
