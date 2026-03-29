from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import credentials as _credentials
from app.models import device as _device
from app.models import discovery as _discovery
from app.models import settings as _settings
from app.models import tenant as _tenant
from app.models import topology as _topology
from app.models import user as _user
from app.models.device import EventLog, Issue
from app.models.discovery import DiscoveryJob
from tools import run_ops_kpi_sample_collection as tool

_REGISTER_MODELS = (_credentials, _device, _discovery, _settings, _tenant, _topology, _user)


def test_run_ops_kpi_sample_collection_seeds_local_evidence(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(tool, "SessionLocal", SessionLocal)

    result = tool.run_ops_kpi_sample_collection(
        profile="local",
        discovery_jobs=5,
        change_events=12,
        northbound_deliveries=24,
        autonomy_issues=6,
        autonomy_actions=6,
        device_count=3,
    )

    assert result["status"] == "ok"
    assert result["devices"]["count"] == 3
    assert result["discovery"]["jobs"] == 5
    assert result["change"]["emitted"] == 12
    assert result["northbound"]["deliveries"] == 24
    assert result["autonomy"]["issues_created"] == 6
    assert result["autonomy"]["events"] == 6

    db = SessionLocal()
    try:
        assert db.query(DiscoveryJob).count() == 5
        assert (
            db.query(EventLog)
            .filter(EventLog.event_id == "CHANGE_EXECUTION_KPI", EventLog.source == tool.CHANGE_EVENT_SOURCE)
            .count()
            == 12
        )
        assert (
            db.query(EventLog)
            .filter(EventLog.event_id == "NORTHBOUND_WEBHOOK_DELIVERY", EventLog.source == tool.NORTHBOUND_EVENT_SOURCE)
            .count()
            == 24
        )
        assert db.query(Issue).count() == 6
        assert (
            db.query(EventLog)
            .filter(EventLog.event_id == "CLOSED_LOOP_EVAL_SUMMARY")
            .count()
            == 6
        )
    finally:
        db.close()
