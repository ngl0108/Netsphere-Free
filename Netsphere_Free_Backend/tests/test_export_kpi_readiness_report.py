from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from tools import export_kpi_readiness_report as tool


def test_request_direct_kpi_payload_uses_local_ops_endpoint(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(tool, "_DIRECT_SESSION_LOCAL", SessionLocal)
    monkeypatch.setattr(
        tool,
        "_OPS_ENDPOINT",
        SimpleNamespace(
            kpi_readiness=lambda **kwargs: {"readiness": {"status": "warning"}, "checks": []},
            get_kpi_readiness_history=lambda **kwargs: {"items": [], "totals": {"count": 0}},
        ),
    )

    payload, history = tool._request_direct_kpi_payload(
        params={
            "discovery_days": 30,
            "discovery_limit": 300,
            "require_sample_minimums": True,
            "sample_min_discovery_jobs": 30,
            "sample_min_change_events": 60,
            "sample_min_northbound_deliveries": 500,
            "sample_min_autonomy_issues_created": 20,
            "sample_min_autonomy_actions_executed": 20,
        },
        history_params={"days": 30, "limit": 90},
    )

    assert payload["readiness"]["status"] == "warning"
    assert history["totals"]["count"] == 0
