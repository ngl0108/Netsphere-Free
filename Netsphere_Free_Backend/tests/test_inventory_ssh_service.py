import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device
from app.models.device_inventory import DeviceInventoryItem
from app.services.inventory_ssh_service import InventorySshService


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
    def __init__(self, out):
        self.out = out

    def send_command(self, cmd, **kwargs):
        if kwargs.get("use_textfsm"):
            return None
        return self.out


def test_inventory_ssh_parses_ios_show_inventory_and_creates_tree(db):
    d = Device(name="SW1", ip_address="10.0.0.1", snmp_community="public", device_type="cisco_ios", status="online")
    db.add(d)
    db.commit()
    db.refresh(d)

    out = """
NAME: "Chassis", DESCR: "Cisco Catalyst 9407R Switch Chassis"
PID: C9407R           , VID: V01  , SN: FDO1234567A

NAME: "Slot 1", DESCR: "C9400-SUP-1"
PID: C9400-SUP-1      , VID: V01  , SN: SUPSERIAL

NAME: "Slot 2", DESCR: "48-Port 10/100/1000 Ethernet Module"
PID: C9400-LC-48T     , VID: V01  , SN: LCSERIAL
"""
    count = InventorySshService.refresh_device_inventory_from_ssh(db, d, FakeConn(out))
    db.commit()
    assert count == 3

    items = db.query(DeviceInventoryItem).filter(DeviceInventoryItem.device_id == d.id).all()
    assert len(items) == 3
    chassis = [x for x in items if x.class_id == 3]
    assert chassis
    assert d.model == "C9407R"
    assert d.serial_number == "FDO1234567A"
    for x in items:
        if x.class_id != 3:
            assert x.parent_index == chassis[0].ent_physical_index


def test_inventory_ssh_parses_juniper_show_chassis_hardware(db):
    d = Device(name="J1", ip_address="10.0.0.2", snmp_community="public", device_type="juniper_junos", status="online")
    db.add(d)
    db.commit()
    db.refresh(d)

    out = """
Hardware inventory:
Item             Version  Part number  Serial number     Description
Chassis                                ABC123            MX960 chassis
FPC 0            REV 07   750-012345   FPCSER            MPC Type 2 3D
"""
    count = InventorySshService.refresh_device_inventory_from_ssh(db, d, FakeConn(out))
    db.commit()
    assert count >= 2
