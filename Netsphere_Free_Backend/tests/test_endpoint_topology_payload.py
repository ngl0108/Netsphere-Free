import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.session import Base
from app.models.device import Device, Site
from app.models.device import Link
from app.models.endpoint import Endpoint, EndpointAttachment
from app.api.v1.endpoints.devices import get_topology_links, get_endpoint_group_details


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


def test_topology_links_includes_endpoint_nodes(db):
    s = Site(name="HQ")
    d = Device(name="SW1", hostname="sw1", ip_address="10.0.0.1", device_type="cisco_ios", status="online")
    d.site = s
    db.add_all([s, d])
    db.flush()

    ep = Endpoint(mac_address="aaaa.bbbb.cccc", ip_address="10.0.0.10", hostname="pc-01", endpoint_type="pc")
    db.add(ep)
    db.flush()

    att = EndpointAttachment(endpoint_id=ep.id, device_id=d.id, interface_name="Gi1/0/10", vlan="10")
    db.add(att)
    db.commit()

    res = get_topology_links(db=db, current_user=None)
    node_ids = {n["id"] for n in res["nodes"]}
    assert f"ep-{ep.id}" in node_ids
    assert any(l["target"] == f"ep-{ep.id}" for l in res["links"])


def test_topology_links_groups_multiple_endpoints_on_same_port(db):
    s = Site(name="HQ")
    d = Device(name="SW1", hostname="sw1", ip_address="10.0.0.1", device_type="cisco_ios", status="online")
    d.site = s
    db.add_all([s, d])
    db.flush()

    ep1 = Endpoint(mac_address="02aa.bbbb.cccc", ip_address=None, hostname=None, endpoint_type="unknown")
    ep2 = Endpoint(mac_address="aabb.ccdd.eeff", ip_address=None, hostname=None, endpoint_type="unknown")
    db.add_all([ep1, ep2])
    db.flush()

    db.add_all(
        [
            EndpointAttachment(endpoint_id=ep1.id, device_id=d.id, interface_name="Gi1/0/10", vlan="10"),
            EndpointAttachment(endpoint_id=ep2.id, device_id=d.id, interface_name="Gi1/0/10", vlan="10"),
        ]
    )
    db.commit()

    res = get_topology_links(db=db, current_user=None)
    group_nodes = [n for n in res["nodes"] if n.get("role") == "endpoint_group"]
    assert group_nodes
    assert any("Gi1/0/10" in n["label"] for n in group_nodes)

    details = get_endpoint_group_details(device_id=d.id, port="Gi1/0/10", db=db, current_user=None)
    assert details["count"] == 2
    assert any(ep["private_mac"] for ep in details["endpoints"])


def test_topology_links_include_confidence_and_evidence(db):
    s = Site(name="HQ")
    d1 = Device(name="SW1", hostname="sw1", ip_address="10.0.0.1", device_type="cisco_ios", status="online")
    d2 = Device(name="SW2", hostname="sw2", ip_address="10.0.0.2", device_type="cisco_ios", status="online")
    d1.site = s
    d2.site = s
    db.add_all([s, d1, d2])
    db.flush()

    db.add(
        Link(
            source_device_id=d1.id,
            target_device_id=d2.id,
            source_interface_name="Gi1/0/1",
            target_interface_name="Gi1/0/2",
            status="active",
            protocol="LLDP",
            confidence=0.95,
            discovery_source="snmp_lldp",
        )
    )
    db.commit()

    res = get_topology_links(db=db, current_user=None)
    links = [l for l in res["links"] if l.get("source") == str(d1.id) and l.get("target") == str(d2.id)]
    assert links, "expected at least one link between SW1 and SW2"
    link = links[0]
    assert float(link.get("confidence") or 0) == pytest.approx(0.95, rel=1e-3)
    assert link.get("discovery_source") == "snmp_lldp"
    evidence = link.get("evidence") or {}
    assert evidence.get("quality") == "high"
    assert evidence.get("protocol") == "LLDP"
