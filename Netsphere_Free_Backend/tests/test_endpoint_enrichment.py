import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.session import Base
from app.models.device import Device, Link
from app.models.endpoint import Endpoint


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


class FakeConn:
    def get_mac_table(self):
        return [
            {"mac": "aaaa.bbbb.cccc", "vlan": "10", "port": "Gi1/0/10", "type": "dynamic"},
            {"mac": "1111.2222.3333", "vlan": "10", "port": "Gi1/0/1", "type": "dynamic"},
        ]

    def get_arp_table(self):
        return [{"ip": "10.0.0.10", "mac": "aaaa.bbbb.cccc", "interface": "Vlan10"}]

    def get_dhcp_snooping_bindings(self):
        return [{"mac": "aaaa.bbbb.cccc", "ip": "10.0.0.11", "vlan": "10", "interface": "Gi1/0/10"}]

    def get_lldp_neighbors_detail(self):
        return [
            {"local_interface": "Gi1/0/10", "system_name": "AP-01", "system_description": "Cisco Catalyst AP"},
            {"local_interface": "Gi1/0/1", "system_name": "SW-UP", "system_description": "Cisco IOS XE Switch"},
        ]


def test_endpoint_enrichment_prefers_dhcp_ip_and_infers_ap_type(db):
    import types
    import importlib

    class _DeviceInfo:
        def __init__(self, *args, **kwargs):
            pass

    class _DeviceConnection:
        def __init__(self, *args, **kwargs):
            pass

    old = sys.modules.get("app.services.ssh_service")
    sys.modules["app.services.ssh_service"] = types.SimpleNamespace(DeviceConnection=_DeviceConnection, DeviceInfo=_DeviceInfo)
    try:
        DeviceSyncService = importlib.import_module("app.services.device_sync_service").DeviceSyncService
    finally:
        if old is None:
            sys.modules.pop("app.services.ssh_service", None)
        else:
            sys.modules["app.services.ssh_service"] = old
    from app.services.oui_service import OUIService

    sw = Device(name="SW1", hostname="sw1", ip_address="10.0.0.1", device_type="cisco_ios", status="online")
    db.add(sw)
    db.commit()
    db.refresh(sw)

    db.add(Link(source_device_id=sw.id, target_device_id=999, source_interface_name="Gi1/0/1", target_interface_name="Gi0/0", status="active"))
    db.commit()

    OUIService.set_override_map_for_tests({"aabbcc": "Apple"})
    try:
        DeviceSyncService._refresh_endpoints_from_mac_table(db, sw, FakeConn())
    finally:
        OUIService.set_override_map_for_tests(None)
    db.commit()

    eps = db.query(Endpoint).all()
    assert len(eps) == 1
    ep = eps[0]
    assert ep.mac_address == "aaaa.bbbb.cccc"
    assert ep.ip_address == "10.0.0.11"
    assert ep.endpoint_type == "ap"
    assert ep.hostname == "AP-01"
