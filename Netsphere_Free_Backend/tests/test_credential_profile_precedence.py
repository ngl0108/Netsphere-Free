import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.credentials import SnmpCredentialProfile
from app.models.device import Site
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


def test_scan_job_uses_site_profile_when_profile_id_not_provided(db):
    p = SnmpCredentialProfile(name="p1", snmp_version="v2c", snmp_port=161, snmp_community="site-comm")
    db.add(p)
    db.commit()
    db.refresh(p)

    site = Site(name="site1", type="area")
    site.snmp_profile_id = p.id
    db.add(site)
    db.commit()
    db.refresh(site)

    svc = DiscoveryService(db)
    job = svc.create_scan_job("10.0.0.0/24", "public", site_id=site.id)
    assert job.snmp_community == "site-comm"
    assert job.snmp_profile_id == p.id
    assert job.site_id == site.id


def test_scan_job_profile_id_overrides_site_profile(db):
    p_site = SnmpCredentialProfile(name="p_site", snmp_version="v2c", snmp_port=161, snmp_community="site-comm")
    p_job = SnmpCredentialProfile(name="p_job", snmp_version="v2c", snmp_port=161, snmp_community="job-comm")
    db.add_all([p_site, p_job])
    db.commit()
    db.refresh(p_site)
    db.refresh(p_job)

    site = Site(name="site2", type="area")
    site.snmp_profile_id = p_site.id
    db.add(site)
    db.commit()
    db.refresh(site)

    svc = DiscoveryService(db)
    job = svc.create_scan_job("10.0.1.0/24", "public", site_id=site.id, snmp_profile_id=p_job.id)
    assert job.snmp_community == "job-comm"
    assert job.snmp_profile_id == p_job.id

