import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, Link, Site
from app.services.topology_link_service import TopologyLinkService
from app.services.topology_snapshot_service import TopologySnapshotService


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


def test_refresh_links_emits_link_update_events(db, monkeypatch):
    published = []

    def fake_publish(event, data):
        published.append((event, data))

    from app.services import realtime_event_bus as reb

    monkeypatch.setattr(reb.realtime_event_bus, "publish", fake_publish)

    a = Device(name="a", ip_address="10.0.0.1", device_type="cisco_ios", status="online", owner_id=1)
    b = Device(name="b", ip_address="10.0.0.2", device_type="cisco_ios", status="online", owner_id=1)
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    neighbors = [
        {
            "local_interface": "Gi0/1",
            "remote_interface": "Gi0/2",
            "neighbor_name": "b",
            "mgmt_ip": "10.0.0.2",
            "protocol": "LLDP",
        }
    ]
    TopologyLinkService.refresh_links_for_device(db, a, neighbors)
    db.commit()

    assert any(evt == "link_update" and d.get("state") == "active" for evt, d in published)
    assert any(d.get("neighbor_device_id") == b.id for _, d in published)
    assert any(evt == "topology_refresh" and d.get("scope") == "l2_links" for evt, d in published)

    published.clear()
    TopologyLinkService.refresh_links_for_device(db, a, [])
    db.commit()

    assert any(evt == "link_update" and d.get("state") == "down" for evt, d in published)
    assert any(evt == "topology_refresh" and d.get("topology_changed") is True for evt, d in published)


def test_refresh_l3_links_emits_realtime_events(db, monkeypatch):
    published = []

    def fake_publish(event, data):
        published.append((event, data))

    from app.services import realtime_event_bus as reb

    monkeypatch.setattr(reb.realtime_event_bus, "publish", fake_publish)

    a = Device(name="r1", ip_address="10.0.0.1", device_type="cisco_ios", status="online", owner_id=1)
    b = Device(name="r2", ip_address="10.0.0.2", device_type="cisco_ios", status="online", owner_id=1)
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    TopologyLinkService.refresh_l3_links_for_device(
        db,
        a,
        ospf_neighbors=[
            {
                "neighbor_ip": "10.0.0.2",
                "neighbor_id": "2.2.2.2",
                "interface": "Gi0/1",
                "state": "FULL/DR",
            }
        ],
        bgp_neighbors=[
            {
                "neighbor_ip": "10.0.0.2",
                "state": "Established",
            }
        ],
    )
    db.commit()

    assert any(evt == "link_update" and d.get("protocol") == "OSPF" and d.get("state") == "active" for evt, d in published)
    assert any(evt == "link_update" and d.get("protocol") == "BGP" and d.get("state") == "active" for evt, d in published)
    assert any(evt == "topology_refresh" and d.get("scope") == "l3_links" for evt, d in published)


def test_create_snapshot_emits_realtime_event(db, monkeypatch):
    published = []

    def fake_publish(event, data):
        published.append((event, data))

    from app.services import realtime_event_bus as reb

    monkeypatch.setattr(reb.realtime_event_bus, "publish", fake_publish)

    site = Site(name="HQ")
    db.add(site)
    db.commit()
    db.refresh(site)

    a = Device(name="edge-r1", ip_address="10.0.0.1", device_type="cisco_ios", status="online", owner_id=1, site_id=site.id)
    b = Device(name="wan-r2", ip_address="10.0.0.2", device_type="cisco_ios", status="online", owner_id=1, site_id=site.id)
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    db.add(
        Link(
            source_device_id=min(a.id, b.id),
            target_device_id=max(a.id, b.id),
            source_interface_name="Gi0/1",
            target_interface_name="Gi0/2",
            status="active",
            protocol="LLDP",
        )
    )
    db.commit()

    snapshot = TopologySnapshotService.create_snapshot(db, site_id=site.id, label="auto-refresh")

    assert snapshot.id is not None
    assert any(
        evt == "topology_snapshot_created"
        and d.get("label") == "auto-refresh"
        and d.get("refresh_hint") == "snapshots"
        for evt, d in published
    )
