from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device
from app.models.device_inventory import DeviceInventoryItem
from app.services.entity_mib_service import EntityMibService


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


def test_entity_mib_refresh_upserts_and_updates_device_model_serial(db, monkeypatch):
    d = Device(name="SW1", ip_address="10.0.0.1", snmp_community="public", device_type="cisco_ios", status="online")
    db.add(d)
    db.commit()
    db.refresh(d)

    fake_rows = [
        {
            "ent_physical_index": 1,
            "parent_index": None,
            "contained_in": 0,
            "class_id": 3,
            "class_name": "chassis",
            "name": "Chassis",
            "description": "Cisco 9407R",
            "model_name": "C9407R",
            "serial_number": "FDO1234",
            "mfg_name": "Cisco",
            "hardware_rev": None,
            "firmware_rev": None,
            "software_rev": None,
            "is_fru": True,
        },
        {
            "ent_physical_index": 10,
            "parent_index": 1,
            "contained_in": 1,
            "class_id": 9,
            "class_name": "module",
            "name": "Supervisor",
            "description": "SUP",
            "model_name": "C9400-SUP-1",
            "serial_number": "SUPSER",
            "mfg_name": "Cisco",
            "hardware_rev": "1.0",
            "firmware_rev": None,
            "software_rev": None,
            "is_fru": True,
        },
    ]

    monkeypatch.setattr(EntityMibService, "fetch_inventory", lambda ip, community: fake_rows)
    count = EntityMibService.refresh_device_inventory(db, d)
    db.commit()

    assert count == 2
    items = db.query(DeviceInventoryItem).filter(DeviceInventoryItem.device_id == d.id).all()
    assert len(items) == 2
    assert d.model == "C9407R"
    assert d.serial_number == "FDO1234"
