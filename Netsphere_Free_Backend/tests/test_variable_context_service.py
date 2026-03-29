import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, Site
from app.models.settings import SystemSetting
from app.services.variable_context_service import resolve_device_context


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


def test_resolve_device_context_precedence(db):
    db.add(SystemSetting(key="vars_global", value='{"x": 1, "g": 1}', description="", category="variables"))
    db.add(SystemSetting(key="vars_role_access", value='{"x": 3, "r": 1}', description="", category="variables"))
    site = Site(name="site1", variables={"x": 2, "s": 1})
    db.add(site)
    db.commit()
    db.refresh(site)

    dev = Device(name="sw1", ip_address="10.0.0.1", role="access", site_id=site.id, variables={"x": 4, "d": 1})
    db.add(dev)
    db.commit()
    db.refresh(dev)

    ctx = resolve_device_context(db, dev, extra={"x": 5, "e": 1})
    merged = ctx.merged

    assert merged["x"] == 5
    assert merged["g"] == 1
    assert merged["s"] == 1
    assert merged["r"] == 1
    assert merged["d"] == 1
    assert merged["e"] == 1
    assert merged["device"]["name"] == "sw1"
