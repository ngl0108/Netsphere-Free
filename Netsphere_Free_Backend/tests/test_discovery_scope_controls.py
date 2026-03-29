import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.settings import SystemSetting
from app.services.discovery_service import DiscoveryService
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


def test_neighbor_crawl_scope_include_exclude(db, monkeypatch):
    db.add(SystemSetting(key="neighbor_crawl_scope_include_cidrs", value="10.0.0.0/24", description="", category="system"))
    db.add(SystemSetting(key="neighbor_crawl_scope_exclude_cidrs", value="10.0.0.2/32", description="", category="system"))
    job = DiscoveryJob(cidr="seedip:10.0.0.1", snmp_community="public", status="pending", logs="")
    db.add(job)
    db.commit()
    db.refresh(job)

    svc = NeighborCrawlService(db)
    monkeypatch.setattr(
        svc,
        "_get_neighbors",
        lambda *args, **kwargs: [
            {"mgmt_ip": "10.0.0.2", "neighbor_name": "x", "local_interface": "Gi0/1", "remote_interface": "Gi0/1"},
            {"mgmt_ip": "10.0.0.3", "neighbor_name": "y", "local_interface": "Gi0/2", "remote_interface": "Gi0/2"},
        ],
    )
    monkeypatch.setattr(svc.discovery, "_scan_single_host", lambda ip, profile: {"ip_address": ip, "hostname": ip, "snmp_status": "unreachable"})

    res = svc.run_neighbor_crawl(job_id=job.id, seed_ip="10.0.0.1", max_depth=2, max_devices=10, min_interval_sec=0)
    assert res["status"] == "ok"
    assert db.query(DiscoveredDevice).filter(DiscoveredDevice.job_id == job.id, DiscoveredDevice.ip_address == "10.0.0.3").first()
    assert db.query(DiscoveredDevice).filter(DiscoveredDevice.job_id == job.id, DiscoveredDevice.ip_address == "10.0.0.2").first() is None


def test_neighbor_crawl_rejects_seed_outside_scope(db):
    db.add(SystemSetting(key="neighbor_crawl_scope_include_cidrs", value="10.0.0.0/24", description="", category="system"))
    job = DiscoveryJob(cidr="seedip:192.168.1.1", snmp_community="public", status="pending", logs="")
    db.add(job)
    db.commit()
    db.refresh(job)

    with pytest.raises(ValueError):
        NeighborCrawlService(db).run_neighbor_crawl(job_id=job.id, seed_ip="192.168.1.1", max_depth=1, max_devices=1, min_interval_sec=0)


def test_tcp_alive_sweep_respects_scope_filters(db, monkeypatch):
    import socket as sockmod

    class FakeSocket:
        def __init__(self, *args, **kwargs):
            self._closed = False
        def settimeout(self, *args, **kwargs):
            return None
        def connect_ex(self, *args, **kwargs):
            return 0
        def close(self):
            self._closed = True

    monkeypatch.setattr(sockmod, "socket", lambda *args, **kwargs: FakeSocket())

    svc = DiscoveryService(db)
    alive = svc._tcp_alive_sweep(
        "10.0.0.0/29",
        ports=[22],
        max_hosts=1024,
        timeout=0.01,
        include_cidrs=["10.0.0.2/32"],
        exclude_cidrs=["10.0.0.3/32"],
    )
    assert alive == ["10.0.0.2"]

