import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, Link
from app.models.topology_candidate import TopologyNeighborCandidate


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


def test_topology_refresh_infers_link_from_fdb_and_arp(db, monkeypatch):
    a = Device(name="a", ip_address="10.0.0.1", device_type="cisco_ios", status="online", owner_id=1, snmp_community="public")
    b = Device(name="b", ip_address="10.0.0.2", device_type="cisco_ios", status="online", owner_id=1, snmp_community="public")
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    import app.tasks.topology_refresh as mod

    class FakeSnmp:
        def __init__(self, *args, **kwargs):
            pass
        def get_interface_name_status_map(self):
            return {}

    monkeypatch.setattr(mod, "SnmpManager", FakeSnmp)
    monkeypatch.setattr(mod.SnmpL2Service, "get_lldp_neighbors", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod.SnmpL2Service, "get_qbridge_mac_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        mod.SnmpL2Service,
        "get_arp_table",
        lambda *args, **kwargs: [{"ip": b.ip_address, "mac": "aaaa.bbbb.cccc", "interface": "Vlan1"}],
    )
    monkeypatch.setattr(
        mod.SnmpL2Service,
        "get_bridge_mac_table",
        lambda *args, **kwargs: [{"mac": "aaaa.bbbb.cccc", "port": "Gi0/1", "discovery_source": "snmp_bridge"}],
    )

    monkeypatch.setattr(mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    res = mod.refresh_device_topology(a.id, discovery_job_id=None, max_depth=1)
    assert res["status"] == "ok"

    links = db.query(Link).all()
    assert len(links) == 1
    assert links[0].source_device_id in (a.id, b.id)
    assert links[0].target_device_id in (a.id, b.id)


def test_topology_refresh_infers_link_from_fdb_and_mac_match(db, monkeypatch):
    a = Device(name="a", ip_address="10.0.0.1", device_type="cisco_ios", status="online", owner_id=1, snmp_community="public")
    b = Device(
        name="b",
        ip_address="10.0.0.2",
        device_type="cisco_ios",
        status="online",
        owner_id=1,
        snmp_community="public",
        latest_parsed_data={"mac_aliases": ["aaaa.bbbb.cccc"]},
    )
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    import app.tasks.topology_refresh as mod

    class FakeSnmp:
        def __init__(self, *args, **kwargs):
            pass
        def get_interface_name_status_map(self):
            return {}

    monkeypatch.setattr(mod, "SnmpManager", FakeSnmp)
    monkeypatch.setattr(mod.SnmpL2Service, "get_lldp_neighbors", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod.SnmpL2Service, "get_qbridge_mac_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod.SnmpL2Service, "get_arp_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        mod.SnmpL2Service,
        "get_bridge_mac_table",
        lambda *args, **kwargs: [{"mac": "aaaa.bbbb.cccc", "port": "Gi0/1", "discovery_source": "snmp_bridge"}],
    )

    monkeypatch.setattr(mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)

    res = mod.refresh_device_topology(a.id, discovery_job_id=None, max_depth=1)
    assert res["status"] == "ok"
    links = db.query(Link).all()
    assert len(links) == 1


def test_topology_refresh_creates_low_confidence_candidate_on_weak_match(db, monkeypatch):
    a = Device(name="a", ip_address="10.0.1.1", device_type="cisco_ios", status="online", owner_id=1, snmp_community="public")
    b = Device(name="b", ip_address="10.0.1.2", device_type="cisco_ios", status="online", owner_id=1, snmp_community="public")
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    import app.tasks.topology_refresh as mod

    class FakeSnmp:
        def __init__(self, *args, **kwargs):
            pass

        def get_interface_name_status_map(self):
            return {}

    monkeypatch.setattr(mod, "SnmpManager", FakeSnmp)
    monkeypatch.setattr(
        mod.SnmpL2Service,
        "get_lldp_neighbors",
        lambda *args, **kwargs: [
            {
                "local_interface": "Gi0/1",
                "remote_interface": "Gi0/2",
                "neighbor_name": "b",
                "mgmt_ip": "10.0.1.2",
                "protocol": "LLDP",
            }
        ],
    )
    monkeypatch.setattr(mod.SnmpL2Service, "get_qbridge_mac_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod.SnmpL2Service, "get_arp_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod.SnmpL2Service, "get_bridge_mac_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(
        mod.TopologyLinkService,
        "_match_target_device",
        lambda *_args, **_kwargs: (b, 0.4, "name_prefix"),
    )

    res = mod.refresh_device_topology(a.id, discovery_job_id=None, max_depth=1)
    assert res["status"] == "ok"

    candidates = db.query(TopologyNeighborCandidate).all()
    assert len(candidates) >= 1
    assert any(c.status == "low_confidence" for c in candidates)


def test_topology_refresh_marks_ambiguous_neighbor_as_low_confidence(db, monkeypatch):
    a = Device(name="a", ip_address="10.0.2.1", device_type="cisco_ios", status="online", owner_id=1, snmp_community="public")
    db.add(a)
    db.commit()
    db.refresh(a)

    import app.tasks.topology_refresh as mod

    class FakeSnmp:
        def __init__(self, *args, **kwargs):
            pass

        def get_interface_name_status_map(self):
            return {}

    monkeypatch.setattr(mod, "SnmpManager", FakeSnmp)
    monkeypatch.setattr(
        mod.SnmpL2Service,
        "get_lldp_neighbors",
        lambda *args, **kwargs: [
            {
                "local_interface": "Gi0/10",
                "remote_interface": "Gi0/11",
                "neighbor_name": "core-sw",
                "mgmt_ip": "",
                "protocol": "LLDP",
            }
        ],
    )
    monkeypatch.setattr(mod.SnmpL2Service, "get_qbridge_mac_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod.SnmpL2Service, "get_arp_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod.SnmpL2Service, "get_bridge_mac_table", lambda *args, **kwargs: [])
    monkeypatch.setattr(mod, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    monkeypatch.setattr(
        mod.TopologyLinkService,
        "_match_target_device",
        lambda *_args, **_kwargs: (None, 0.0, "ambiguous_name_exact:1,2"),
    )

    res = mod.refresh_device_topology(a.id, discovery_job_id=None, max_depth=1)
    assert res["status"] == "ok"

    candidates = db.query(TopologyNeighborCandidate).all()
    assert len(candidates) == 1
    assert candidates[0].status == "low_confidence"
