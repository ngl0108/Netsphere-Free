import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.session import Base
from app.models.device import Device, Interface, Link
from app.services.path_trace_service import PathTraceService


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


def test_path_trace_l3_uses_route_hints_when_available(db, monkeypatch):
    a = Device(name="A", hostname="A", ip_address="10.0.0.1", ssh_username="u", ssh_password="p", device_type="cisco_ios")
    b = Device(name="B", hostname="B", ip_address="10.0.0.2", ssh_username="u", ssh_password="p", device_type="cisco_ios")
    c = Device(name="C", hostname="C", ip_address="20.0.0.1", ssh_username="u", ssh_password="p", device_type="cisco_ios")
    db.add_all([a, b, c])
    db.flush()

    db.add_all(
        [
            Interface(device_id=a.id, name="Vlan10", ip_address="10.0.0.1/24"),
            Interface(device_id=c.id, name="Vlan20", ip_address="20.0.0.1/24"),
        ]
    )

    db.add_all(
        [
            Link(
                source_device_id=a.id,
                source_interface_name="GigabitEthernet0/1",
                target_device_id=b.id,
                target_interface_name="GigabitEthernet0/1",
                status="active",
                protocol="LLDP",
            ),
            Link(
                source_device_id=b.id,
                source_interface_name="GigabitEthernet0/2",
                target_device_id=c.id,
                target_interface_name="GigabitEthernet0/1",
                status="active",
                protocol="LLDP",
            ),
        ]
    )
    db.commit()

    svc = PathTraceService(db)

    def fake_route_hint(device, dst_ip, *args, **kwargs):
        if device.id == a.id:
            return {"outgoing_interface": "Gi0/1", "next_hop_ip": None, "protocol": "connected"}
        if device.id == b.id:
            return {"outgoing_interface": "Gi0/2", "next_hop_ip": None, "protocol": "static"}
        return {"outgoing_interface": None, "next_hop_ip": None, "protocol": None}

    monkeypatch.setattr(svc, "_get_route_hint", fake_route_hint)

    res = svc.trace_path("10.0.0.10", "20.0.0.20")
    assert res["status"] == "success"
    assert res.get("mode") == "l3"
    assert [n["name"] for n in res["path"]] == ["A", "B", "C"]
    assert res["path"][0]["egress_intf"] in ["Gi0/1", "GigabitEthernet0/1"]
    assert "evidence" in res["path"][0]
    assert res["summary"]["protocols"] == ["LLDP"]
    assert res["summary"]["layers"] == ["l2"]
    assert res["segments"][0]["status"] == "active"
    assert res["segments"][0]["link"]["protocol"] == "LLDP"


def test_path_trace_l3_fills_egress_from_arp_mac_when_missing(db, monkeypatch):
    a = Device(name="A", hostname="A", ip_address="10.0.0.1", ssh_username="u", ssh_password="p", device_type="cisco_ios")
    b = Device(name="B", hostname="B", ip_address="10.0.0.2", ssh_username="u", ssh_password="p", device_type="cisco_ios")
    c = Device(name="C", hostname="C", ip_address="20.0.0.1", ssh_username="u", ssh_password="p", device_type="cisco_ios")
    db.add_all([a, b, c])
    db.flush()

    db.add_all(
        [
            Interface(device_id=a.id, name="Vlan10", ip_address="10.0.0.1/24"),
            Interface(device_id=c.id, name="Vlan20", ip_address="20.0.0.1/24"),
        ]
    )

    db.add_all(
        [
            Link(
                source_device_id=a.id,
                source_interface_name="GigabitEthernet0/1",
                target_device_id=b.id,
                target_interface_name="GigabitEthernet0/1",
                status="active",
                protocol="LLDP",
            ),
            Link(
                source_device_id=b.id,
                source_interface_name="GigabitEthernet0/2",
                target_device_id=c.id,
                target_interface_name="GigabitEthernet0/1",
                status="active",
                protocol="LLDP",
            ),
        ]
    )
    db.commit()

    svc = PathTraceService(db)

    def fake_route_hint(device, dst_ip, *args, **kwargs):
        if device.id == a.id:
            return {"outgoing_interface": None, "next_hop_ip": "10.0.0.2", "protocol": "ospf", "vrf": "BLUE"}
        if device.id == b.id:
            return {"outgoing_interface": None, "next_hop_ip": None, "protocol": "connected", "vrf": "BLUE"}
        return {"outgoing_interface": None, "next_hop_ip": None, "protocol": None}

    def fake_arp_mac(device, dst_ip, next_hop_ip, vrf):
        if device.id == a.id:
            return (
                "Gi0/1",
                {"ip": next_hop_ip, "mac": "aaaa.bbbb.cccc", "interface": "Gi0/1"},
                {"mac": "aaaa.bbbb.cccc", "port": "Gi0/1", "vlan": "10"},
            )
        if device.id == b.id:
            return (
                "Gi0/2",
                {"ip": dst_ip, "mac": "dddd.eeee.ffff", "interface": "Gi0/2"},
                {"mac": "dddd.eeee.ffff", "port": "Gi0/2", "vlan": "20"},
            )
        return (None, None, None)

    monkeypatch.setattr(svc, "_get_route_hint", fake_route_hint)
    monkeypatch.setattr(svc, "_resolve_outgoing_interface_via_arp_mac", fake_arp_mac)

    res = svc.trace_path("10.0.0.10", "20.0.0.20")
    assert res["status"] == "success"
    assert res.get("mode") == "l3"
    assert [n["name"] for n in res["path"]] == ["A", "B", "C"]
    assert res["path"][0]["egress_intf"] in ["Gi0/1", "GigabitEthernet0/1"]
    assert res["path"][0]["evidence"]["vrf"] == "BLUE"
    assert res["path"][0]["evidence"]["arp"]["mac"] == "aaaa.bbbb.cccc"
    assert res["path"][0]["evidence"]["mac"]["port"] == "Gi0/1"
    assert res["summary"]["mode"] == "l3"
    assert res["summary"]["route_lookup_hops"] >= 2


def test_route_hint_uses_device_interface_match_to_narrow_vrf(db, monkeypatch):
    a = Device(name="A", hostname="A", ip_address="10.0.0.1", ssh_username="u", ssh_password="p", device_type="cisco_ios")
    c = Device(name="C", hostname="C", ip_address="20.0.0.1", ssh_username="u", ssh_password="p", device_type="cisco_ios")
    db.add_all([a, c])
    db.flush()

    db.add_all(
        [
            Interface(device_id=a.id, name="Vlan10", ip_address="10.0.0.1/24"),
            Interface(device_id=a.id, name="Vlan20", ip_address="20.0.0.254/24"),
            Interface(device_id=c.id, name="Vlan20", ip_address="20.0.0.1/24"),
        ]
    )
    db.commit()

    svc = PathTraceService(db)

    calls = {"route_vrf": []}

    import types, sys as _sys

    class FakeConn:
        def connect(self):
            return True

        def disconnect(self):
            return None

        def get_route_to(self, ip, vrf=None):
            calls["route_vrf"].append(vrf)
            if vrf == "BLUE":
                return {"outgoing_interface": "Vlan20", "next_hop_ip": None, "protocol": "connected", "vrf": "BLUE"}
            return {"outgoing_interface": None, "next_hop_ip": None, "protocol": None, "vrf": None}

        def get_interface_vrf(self, interface_name):
            if interface_name == "Vlan20":
                return {"interface": interface_name, "vrf": "BLUE", "raw": "ok"}
            return {"interface": interface_name, "vrf": None, "raw": "ok"}

        def get_vrfs(self):
            return ["RED", "BLUE", "GREEN"]

    class FakeDeviceInfo:
        def __init__(self, *args, **kwargs):
            pass

    class FakeDeviceConnection:
        def __init__(self, *args, **kwargs):
            self._inner = FakeConn()

        def connect(self):
            return self._inner.connect()

        def disconnect(self):
            return self._inner.disconnect()

        def get_route_to(self, ip, vrf=None):
            return self._inner.get_route_to(ip, vrf=vrf)

        def get_interface_vrf(self, interface_name):
            return self._inner.get_interface_vrf(interface_name)

        def get_vrfs(self):
            return self._inner.get_vrfs()

    fake_module = types.SimpleNamespace(DeviceConnection=FakeDeviceConnection, DeviceInfo=FakeDeviceInfo)
    monkeypatch.setitem(_sys.modules, "app.services.ssh_service", fake_module)

    hint = svc._get_route_hint(a, "20.0.0.20", ingress_interface_name="Vlan10")
    assert hint.get("vrf") == "BLUE"
    assert "BLUE" in calls["route_vrf"]


def test_path_trace_best_effort_uses_degraded_topology_when_active_path_missing(db, monkeypatch):
    a = Device(name="A", hostname="A", ip_address="10.0.0.1", device_type="cisco_ios")
    b = Device(name="B", hostname="B", ip_address="10.0.0.2", device_type="cisco_ios")
    c = Device(name="C", hostname="C", ip_address="20.0.0.1", device_type="cisco_ios")
    db.add_all([a, b, c])
    db.flush()

    db.add_all(
        [
            Interface(device_id=a.id, name="Vlan10", ip_address="10.0.0.1/24"),
            Interface(device_id=c.id, name="Vlan20", ip_address="20.0.0.1/24"),
        ]
    )

    db.add_all(
        [
            Link(
                source_device_id=a.id,
                source_interface_name="Gi0/1",
                target_device_id=b.id,
                target_interface_name="Gi0/1",
                status="degraded",
                protocol="LLDP",
                confidence=0.64,
                discovery_source="synthetic",
            ),
            Link(
                source_device_id=b.id,
                source_interface_name="Gi0/2",
                target_device_id=c.id,
                target_interface_name="Gi0/1",
                status="active",
                protocol="LLDP",
                confidence=0.96,
                discovery_source="synthetic",
            ),
        ]
    )
    db.commit()

    svc = PathTraceService(db)
    monkeypatch.setattr(svc, "_trace_path_l3", lambda *args, **kwargs: None)

    res = svc.trace_path("10.0.0.10", "20.0.0.20")

    assert res["status"] == "success"
    assert res["mode"] == "topology_best_effort"
    assert [n["name"] for n in res["path"]] == ["A", "B", "C"]
    assert res["summary"]["health"] == "degraded"
    assert res["summary"]["degraded_segments"] == 1
    assert res["summary"]["warnings"]
    assert res["segments"][0]["status"] == "degraded"
    assert res["segments"][0]["link"]["confidence"] == pytest.approx(0.64, rel=1e-3)


def test_path_trace_segments_prefer_protocol_matching_link_between_same_devices(db, monkeypatch):
    a = Device(name="A", hostname="A", ip_address="10.0.0.1", ssh_username="u", ssh_password="p", device_type="cisco_ios")
    b = Device(name="B", hostname="B", ip_address="20.0.0.1", ssh_username="u", ssh_password="p", device_type="cisco_ios")
    db.add_all([a, b])
    db.flush()

    db.add_all(
        [
            Interface(device_id=a.id, name="Vlan10", ip_address="10.0.0.1/24"),
            Interface(device_id=b.id, name="Vlan20", ip_address="20.0.0.1/24"),
        ]
    )

    lldp_link = Link(
        source_device_id=a.id,
        source_interface_name="Gi0/1",
        target_device_id=b.id,
        target_interface_name="Gi0/1",
        status="active",
        protocol="LLDP",
        confidence=0.99,
    )
    bgp_link = Link(
        source_device_id=a.id,
        source_interface_name="",
        target_device_id=b.id,
        target_interface_name="",
        status="active",
        protocol="BGP",
        confidence=0.85,
    )
    db.add_all([lldp_link, bgp_link])
    db.commit()

    svc = PathTraceService(db)

    def fake_route_hint(device, dst_ip, *args, **kwargs):
        if device.id == a.id:
            return {"outgoing_interface": None, "next_hop_ip": "20.0.0.1", "protocol": "bgp"}
        return {"outgoing_interface": None, "next_hop_ip": None, "protocol": None}

    monkeypatch.setattr(svc, "_get_route_hint", fake_route_hint)
    monkeypatch.setattr(svc, "_resolve_outgoing_interface_via_arp_mac", lambda *args, **kwargs: (None, None, None))

    res = svc.trace_path("10.0.0.10", "20.0.0.20")

    assert res["status"] == "success"
    assert res["segments"][0]["protocol"] == "BGP"
    assert res["segments"][0]["link"]["id"] == bgp_link.id
    assert res["summary"]["protocols"] == ["BGP"]
