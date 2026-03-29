import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.session import Base
from app.models.device import Device
from app.services.topology_link_service import TopologyLinkService


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


def test_match_target_device_strips_domain_and_separators(db):
    d = Device(name="SW-01", hostname="sw-01.domain.local", ip_address="10.0.0.10", device_type="cisco_ios", status="online")
    db.add(d)
    db.commit()

    target, conf, reason = TopologyLinkService._match_target_device(db, "sw01.domain.local", "")
    assert target is not None
    assert target.id == d.id
    assert reason in ("name_exact", "name_normalized")
