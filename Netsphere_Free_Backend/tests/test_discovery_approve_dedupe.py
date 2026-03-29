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


def test_approve_device_marks_existing_when_ip_already_registered(db):
    existing = Device(name="sw1", ip_address="10.0.0.10", device_type="cisco_ios", status="online", owner_id=1)
    db.add(existing)
    job = DiscoveryJob(cidr="10.0.0.0/24", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.commit()
    db.refresh(existing)
    db.refresh(job)

    disc = DiscoveredDevice(job_id=job.id, ip_address="10.0.0.10", hostname="sw1", vendor="Cisco", status="new", snmp_status="reachable")
    db.add(disc)
    db.commit()
    db.refresh(disc)

    svc = DiscoveryService(db)
    device = svc.approve_device(disc.id)
    db.refresh(disc)

    assert device.id == existing.id
    assert disc.status == "existing"
    assert disc.matched_device_id == existing.id


def test_approve_device_marks_existing_when_hostname_already_registered(db):
    existing = Device(name="core-sw", ip_address="10.0.0.11", device_type="cisco_ios", status="online", owner_id=1)
    db.add(existing)
    job = DiscoveryJob(cidr="10.0.0.0/24", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.commit()
    db.refresh(existing)
    db.refresh(job)

    disc = DiscoveredDevice(job_id=job.id, ip_address="10.0.0.12", hostname="core-sw", vendor="Cisco", status="new", snmp_status="reachable")
    db.add(disc)
    db.commit()
    db.refresh(disc)

    svc = DiscoveryService(db)
    device = svc.approve_device(disc.id)
    db.refresh(disc)

    assert device.id == existing.id
    assert disc.status == "existing"
    assert disc.matched_device_id == existing.id


def test_approve_device_marks_existing_when_normalized_hostname_matches(db):
    existing = Device(name="core-sw-01", ip_address="10.0.0.21", device_type="cisco_ios", status="online", owner_id=1)
    db.add(existing)
    job = DiscoveryJob(cidr="10.0.0.0/24", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.commit()
    db.refresh(existing)
    db.refresh(job)

    disc = DiscoveredDevice(
        job_id=job.id,
        ip_address="10.0.0.22",
        hostname="core_sw_01.example.local",
        vendor="Cisco",
        status="new",
        snmp_status="reachable",
    )
    db.add(disc)
    db.commit()
    db.refresh(disc)

    svc = DiscoveryService(db)
    device = svc.approve_device(disc.id)
    db.refresh(disc)

    assert device.id == existing.id
    assert disc.status == "existing"
    assert disc.matched_device_id == existing.id


def test_approve_device_marks_existing_when_mac_already_registered(db):
    existing = Device(
        name="edge-sw",
        ip_address="10.0.0.31",
        mac_address="aa:bb:cc:dd:ee:ff",
        device_type="cisco_ios",
        status="online",
        owner_id=1,
    )
    db.add(existing)
    job = DiscoveryJob(cidr="10.0.0.0/24", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.commit()
    db.refresh(existing)
    db.refresh(job)

    disc = DiscoveredDevice(
        job_id=job.id,
        ip_address="10.0.0.32",
        hostname="edge-sw-new",
        mac_address="aa:bb:cc:dd:ee:ff",
        vendor="Cisco",
        status="new",
        snmp_status="reachable",
    )
    db.add(disc)
    db.commit()
    db.refresh(disc)

    svc = DiscoveryService(db)
    device = svc.approve_device(disc.id)
    db.refresh(disc)

    assert device.id == existing.id
    assert disc.status == "existing"
    assert disc.matched_device_id == existing.id


def test_approve_device_marks_existing_when_mac_format_differs(db):
    existing = Device(
        name="edge-sw-2",
        ip_address="10.0.0.41",
        mac_address="aabb.ccdd.eeff",
        device_type="cisco_ios",
        status="online",
        owner_id=1,
    )
    db.add(existing)
    job = DiscoveryJob(cidr="10.0.0.0/24", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.commit()
    db.refresh(existing)
    db.refresh(job)

    disc = DiscoveredDevice(
        job_id=job.id,
        ip_address="10.0.0.42",
        hostname="edge-sw-2-new",
        mac_address="aa:bb:cc:dd:ee:ff",
        vendor="Cisco",
        status="new",
        snmp_status="reachable",
    )
    db.add(disc)
    db.commit()
    db.refresh(disc)

    svc = DiscoveryService(db)
    device = svc.approve_device(disc.id)
    db.refresh(disc)

    assert device.id == existing.id
    assert disc.status == "existing"
    assert disc.matched_device_id == existing.id


def test_approve_device_uses_platform_fingerprint_for_new_device_type(db):
    job = DiscoveryJob(cidr="10.0.1.0/24", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.commit()
    db.refresh(job)

    disc = DiscoveredDevice(
        job_id=job.id,
        ip_address="10.0.1.10",
        hostname="core-n9k-01",
        vendor="Cisco",
        model="C93180YC-FX",
        os_version="Version 10.2(3)",
        device_type="cisco_ios",
        sys_object_id="1.3.6.1.4.1.9.1.1208",
        sys_descr="Cisco Nexus Operating System (NX-OS) Software, Version 10.2(3), Nexus9000 C93180YC-FX",
        status="new",
        snmp_status="reachable",
    )
    db.add(disc)
    db.commit()
    db.refresh(disc)

    svc = DiscoveryService(db)
    device = svc.approve_device(disc.id)
    db.refresh(disc)

    assert disc.status == "approved"
    assert device.device_type == "cisco_nxos"
    assert device.model == "C93180YC-FX"


def test_approve_device_can_infer_platform_when_vendor_is_unknown(db):
    job = DiscoveryJob(cidr="10.0.2.0/24", snmp_community="public", status="completed", logs="")
    db.add(job)
    db.commit()
    db.refresh(job)

    disc = DiscoveredDevice(
        job_id=job.id,
        ip_address="10.0.2.10",
        hostname="edge-os10-01",
        vendor="Unknown",
        model="S5248F-ON",
        os_version="Version 10.5.1.0",
        device_type="unknown",
        sys_object_id="1.3.6.1.4.1.674.10895.5000",
        sys_descr="Dell EMC Networking OS10 Enterprise, Version 10.5.1.0",
        status="new",
        snmp_status="reachable",
    )
    db.add(disc)
    db.commit()
    db.refresh(disc)

    svc = DiscoveryService(db)
    device = svc.approve_device(disc.id)
    db.refresh(disc)

    assert disc.status == "approved"
    assert device.device_type == "dell_os10"
    assert device.model == "S5248F-ON"
