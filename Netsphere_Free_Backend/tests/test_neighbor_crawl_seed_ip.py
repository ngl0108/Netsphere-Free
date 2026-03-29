import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.services.neighbor_crawl_service import NeighborCrawlService


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


def test_neighbor_crawl_accepts_seed_ip_without_device(db, monkeypatch):
    job = DiscoveryJob(cidr="seedip:10.0.0.1", snmp_community="public", status="pending", logs="")
    db.add(job)
    db.commit()
    db.refresh(job)

    svc = NeighborCrawlService(db)
    monkeypatch.setattr(svc, "_get_neighbors", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        svc.discovery,
        "_scan_single_host",
        lambda ip, profile: {"hostname": ip, "vendor": "Unknown", "snmp_status": "unreachable"},
    )

    res = svc.run_neighbor_crawl(job_id=job.id, seed_ip="10.0.0.1", max_depth=1, max_devices=1, min_interval_sec=0)
    assert res["status"] == "ok"
    assert db.query(DiscoveredDevice).filter(DiscoveredDevice.job_id == job.id, DiscoveredDevice.ip_address == "10.0.0.1").first()


def test_neighbor_crawl_uses_mac_alias_cache_when_arp_missing(db, monkeypatch):
    from app.models.device import Device

    job = DiscoveryJob(cidr="seedip:10.0.0.1", snmp_community="public", status="pending", logs="")
    db.add(job)
    db.add(Device(name="b", ip_address="10.0.0.2", device_type="cisco_ios", status="online", owner_id=1, mac_address="bbbb.cccc.dddd"))
    db.add(Device(name="c", ip_address="10.0.0.3", device_type="cisco_ios", status="online", owner_id=1, latest_parsed_data={"mac_aliases": ["aaaa.bbbb.cccc"]}))
    db.commit()
    db.refresh(job)

    svc = NeighborCrawlService(db)

    class FakeSnmp:
        pass

    monkeypatch.setattr(svc, "_snmp_for_device", lambda *args, **kwargs: FakeSnmp())
    monkeypatch.setattr(svc.discovery, "_scan_single_host", lambda ip, profile: {"hostname": ip, "vendor": "Unknown", "snmp_status": "unreachable"})

    from app.services.snmp_l2_service import SnmpL2Service
    monkeypatch.setattr(SnmpL2Service, "get_lldp_neighbors", lambda *args, **kwargs: [])
    monkeypatch.setattr(SnmpL2Service, "get_cdp_neighbors", lambda *args, **kwargs: [])
    monkeypatch.setattr(SnmpL2Service, "get_arp_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(SnmpL2Service, "get_qbridge_mac_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(SnmpL2Service, "get_bridge_mac_table", lambda *args, **kwargs: [{"mac": "aaaa.bbbb.cccc", "port": "Gi0/1"}])

    res = svc.run_neighbor_crawl(job_id=job.id, seed_ip="10.0.0.1", max_depth=1, max_devices=3, min_interval_sec=0)
    assert res["status"] == "ok"
    assert db.query(DiscoveredDevice).filter(DiscoveredDevice.job_id == job.id, DiscoveredDevice.ip_address == "10.0.0.3").first()
