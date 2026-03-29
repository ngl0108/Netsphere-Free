import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, Link, Site
from app.models.topology import TopologyChangeEvent, TopologySnapshot
from app.services.topology_link_service import TopologyLinkService
from app.services.topology_snapshot_policy_service import TopologySnapshotPolicyService
from app.services.topology_snapshot_service import TopologySnapshotService
from app.models.settings import SystemSetting


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


def test_snapshot_create_and_site_filter(db):
    s1 = Site(name="S1")
    s2 = Site(name="S2")
    db.add_all([s1, s2])
    db.commit()
    db.refresh(s1)
    db.refresh(s2)

    d1 = Device(name="sw1", ip_address="10.0.0.1", device_type="cisco_ios", site_id=s1.id)
    d2 = Device(name="sw2", ip_address="10.0.0.2", device_type="cisco_ios", site_id=s1.id)
    d3 = Device(name="sw3", ip_address="10.0.0.3", device_type="cisco_ios", site_id=s2.id)
    db.add_all([d1, d2, d3])
    db.commit()
    db.refresh(d1)
    db.refresh(d2)
    db.refresh(d3)

    db.add(
        Link(
            source_device_id=min(d1.id, d2.id),
            target_device_id=max(d1.id, d2.id),
            source_interface_name="Gi0/1",
            target_interface_name="Gi0/2",
            status="active",
            protocol="LLDP",
        )
    )
    db.commit()

    snap = TopologySnapshotService.create_snapshot(db, site_id=s1.id, label="s1")
    assert isinstance(snap, TopologySnapshot)
    assert snap.site_id == s1.id
    assert snap.node_count == 2
    assert snap.link_count == 1

    nodes = json.loads(snap.nodes_json)
    assert sorted([n["id"] for n in nodes]) == sorted([str(d1.id), str(d2.id)])


def test_snapshot_diff_added_removed_changed(db):
    s1 = Site(name="S1")
    db.add(s1)
    db.commit()
    db.refresh(s1)

    d1 = Device(name="sw1", ip_address="10.0.0.1", device_type="cisco_ios", site_id=s1.id)
    d2 = Device(name="sw2", ip_address="10.0.0.2", device_type="cisco_ios", site_id=s1.id)
    d3 = Device(name="sw3", ip_address="10.0.0.3", device_type="cisco_ios", site_id=s1.id)
    db.add_all([d1, d2, d3])
    db.commit()
    db.refresh(d1)
    db.refresh(d2)
    db.refresh(d3)

    l12 = Link(
        source_device_id=min(d1.id, d2.id),
        target_device_id=max(d1.id, d2.id),
        source_interface_name="Gi0/1",
        target_interface_name="Gi0/2",
        status="active",
        protocol="LLDP",
    )
    db.add(l12)
    db.commit()

    snap_a = TopologySnapshotService.create_snapshot(db, site_id=s1.id, label="a")

    l23 = Link(
        source_device_id=min(d2.id, d3.id),
        target_device_id=max(d2.id, d3.id),
        source_interface_name="Gi0/3",
        target_interface_name="Gi0/4",
        status="active",
        protocol="LLDP",
    )
    db.add(l23)
    l12.status = "inactive"
    db.commit()

    snap_b = TopologySnapshotService.create_snapshot(db, site_id=s1.id, label="b")
    diff = TopologySnapshotService.diff_snapshots(db, snap_a.id, snap_b.id)
    assert diff["counts"]["added"] == 1
    assert diff["counts"]["removed"] == 0
    assert diff["counts"]["changed"] == 1


def test_refresh_links_writes_change_events(db):
    s1 = Site(name="S1")
    db.add(s1)
    db.commit()
    db.refresh(s1)

    d1 = Device(name="sw1", hostname="sw1", ip_address="10.0.0.1", device_type="cisco_ios", site_id=s1.id)
    d2 = Device(name="sw2", hostname="sw2", ip_address="10.0.0.2", device_type="cisco_ios", site_id=s1.id)
    db.add_all([d1, d2])
    db.commit()
    db.refresh(d1)
    db.refresh(d2)

    db.add(
        Link(
            source_device_id=min(d1.id, d2.id),
            target_device_id=max(d1.id, d2.id),
            source_interface_name="Gi0/1",
            target_interface_name="Gi0/2",
            status="inactive",
            protocol="LLDP",
        )
    )
    db.commit()

    neighbors = [
        {
            "local_interface": "Gi0/1",
            "remote_interface": "Gi0/2",
            "neighbor_name": "sw2",
            "mgmt_ip": "10.0.0.2",
            "protocol": "LLDP",
        }
    ]
    TopologyLinkService.refresh_links_for_device(db, d1, neighbors)
    db.commit()

    ev = (
        db.query(TopologyChangeEvent)
        .filter(TopologyChangeEvent.event_type == "link_update")
        .order_by(TopologyChangeEvent.id.desc())
        .first()
    )
    assert ev is not None
    payload = json.loads(ev.payload_json)
    assert payload["state"] == "active"
    assert payload["local_interface"] == "Gi0/1"


def test_snapshot_policy_creates_on_threshold(db):
    s1 = Site(name="S1")
    db.add(s1)
    db.commit()
    db.refresh(s1)

    d1 = Device(name="sw1", hostname="sw1", ip_address="10.0.0.1", device_type="cisco_ios", site_id=s1.id)
    d2 = Device(name="sw2", hostname="sw2", ip_address="10.0.0.2", device_type="cisco_ios", site_id=s1.id)
    db.add_all([d1, d2])
    db.commit()
    db.refresh(d1)
    db.refresh(d2)

    db.add_all(
        [
            SystemSetting(key="topology_snapshot_auto_enabled", value="true"),
            SystemSetting(key="topology_snapshot_auto_scope", value="site"),
            SystemSetting(key="topology_snapshot_auto_interval_minutes", value="9999"),
            SystemSetting(key="topology_snapshot_auto_change_threshold_links", value="1"),
        ]
    )
    db.commit()

    TopologySnapshotService.create_snapshot(db, site_id=s1.id, label="baseline")
    assert db.query(TopologySnapshot).count() == 1

    db.add(
        Link(
            source_device_id=min(d1.id, d2.id),
            target_device_id=max(d1.id, d2.id),
            source_interface_name="Gi0/1",
            target_interface_name="Gi0/2",
            status="active",
            protocol="LLDP",
        )
    )
    db.commit()

    TopologySnapshotPolicyService.maybe_create_snapshot(db, site_id=s1.id, job_id=None, trigger="test")
    assert db.query(TopologySnapshot).count() == 2
