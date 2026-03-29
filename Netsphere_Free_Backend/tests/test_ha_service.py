from datetime import datetime, timedelta, timezone
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.ha_lease import HaLease
from app.services.ha_service import HaService


def _make_engine_and_sessionmaker():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine(f"sqlite:///{tmp.name}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, SessionLocal


def test_ha_lease_exclusive_and_takeover_after_expiry():
    engine, SessionLocal = _make_engine_and_sessionmaker()
    db1 = SessionLocal()
    db2 = SessionLocal()
    try:
        key = "k1"

        with db1.begin():
            ok1, leader1, exp1 = HaService.try_acquire_or_renew(db1, key=key, node_id="node-a", ttl_seconds=10)
        assert ok1 is True
        assert leader1 == "node-a"
        assert exp1 is not None

        with db2.begin():
            ok2, leader2, exp2 = HaService.try_acquire_or_renew(db2, key=key, node_id="node-b", ttl_seconds=10)
        assert ok2 is False
        assert leader2 == "node-a"

        lease = db1.query(HaLease).filter(HaLease.key == key).first()
        assert lease is not None
        lease.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db1.add(lease)
        db1.commit()

        with db2.begin():
            ok3, leader3, exp3 = HaService.try_acquire_or_renew(db2, key=key, node_id="node-b", ttl_seconds=10)
        assert ok3 is True
        assert leader3 == "node-b"
        assert exp3 is not None
    finally:
        db1.close()
        db2.close()


def test_ha_lease_renew_extends_expiration():
    engine, SessionLocal = _make_engine_and_sessionmaker()
    db = SessionLocal()
    try:
        key = "k2"
        with db.begin():
            ok1, leader1, exp1 = HaService.try_acquire_or_renew(db, key=key, node_id="node-a", ttl_seconds=5)
        assert ok1 is True
        assert leader1 == "node-a"
        assert exp1 is not None

        lease = db.query(HaLease).filter(HaLease.key == key).first()
        assert lease is not None
        old_exp = lease.expires_at
        db.commit()

        with db.begin():
            ok2, leader2, exp2 = HaService.try_acquire_or_renew(db, key=key, node_id="node-a", ttl_seconds=30)
        assert ok2 is True
        assert leader2 == "node-a"
        assert exp2 is not None

        lease2 = db.query(HaLease).filter(HaLease.key == key).first()
        assert lease2 is not None
        assert lease2.expires_at >= old_exp
    finally:
        db.close()


def test_ha_env_aliases_support_netsphere_prefix(monkeypatch):
    monkeypatch.delenv("NETSPHERE_NODE_ID", raising=False)
    monkeypatch.delenv("NETMANAGER_NODE_ID", raising=False)
    monkeypatch.delenv("NETSPHERE_HA_ENABLED", raising=False)
    monkeypatch.delenv("NETMANAGER_HA_ENABLED", raising=False)

    monkeypatch.setenv("NETSPHERE_NODE_ID", "netsphere-node-a")
    monkeypatch.setenv("NETSPHERE_HA_ENABLED", "true")

    assert HaService.node_id(None) == "netsphere-node-a"
    assert HaService.enabled(None) is True


def test_ha_env_aliases_fall_back_to_netmanager_prefix(monkeypatch):
    monkeypatch.delenv("NETSPHERE_NODE_ID", raising=False)
    monkeypatch.delenv("NETSPHERE_HA_ENABLED", raising=False)
    monkeypatch.setenv("NETMANAGER_NODE_ID", "legacy-node-a")
    monkeypatch.setenv("NETMANAGER_HA_ENABLED", "true")

    assert HaService.node_id(None) == "legacy-node-a"
    assert HaService.enabled(None) is True
