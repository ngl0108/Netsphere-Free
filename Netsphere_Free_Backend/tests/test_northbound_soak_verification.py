from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import EventLog
from app.models.settings import SystemSetting
from app.services.webhook_service import WebhookService
from tools import run_northbound_soak_verification as tool


def test_direct_db_client_records_delivery_and_builds_northbound_kpi(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    monkeypatch.setattr(tool, "_DIRECT_SESSION_LOCAL", SessionLocal)
    monkeypatch.setattr(tool, "_DIRECT_EVENT_LOG", EventLog)
    monkeypatch.setattr(tool, "_DIRECT_SYSTEM_SETTING", SystemSetting)
    monkeypatch.setattr(tool, "_DIRECT_WEBHOOK_SERVICE", WebhookService)

    server, _state = tool._start_local_receiver(
        port=18081,
        secret="soak-secret",
        fail_every=0,
        enforce_signature=True,
    )
    try:
        snapshot = tool._snapshot_direct_webhook_settings()
        client = tool._DirectDbClient()
        put_res = client.put(
            "/api/v1/settings/general",
            {
                "settings": {
                    "webhook_enabled": True,
                    "webhook_url": "http://127.0.0.1:18081/webhook",
                    "webhook_secret": "soak-secret",
                    "webhook_timeout_seconds": 5,
                    "webhook_delivery_mode": "servicenow",
                    "webhook_auth_type": "none",
                    "webhook_retry_attempts": 1,
                    "webhook_retry_backoff_seconds": 0,
                    "webhook_retry_max_backoff_seconds": 0,
                    "webhook_retry_jitter_seconds": 0,
                    "webhook_retry_on_4xx": False,
                    "webhook_servicenow_table": "incident",
                }
            },
        )
        assert put_res.status_code == 200

        post_res = client.post(
            "/api/v1/settings/test-webhook-connector",
            {
                "event_type": "soak_test",
                "title": "Soak Test [servicenow]",
                "message": "run_id=test idx=1",
            },
        )
        assert post_res.status_code == 200
        post_body = tool._unwrap_payload(post_res.json())
        result = post_body.get("result") or {}
        assert result.get("mode") == "servicenow"
        assert int(result.get("attempts") or 0) == 1

        stats_res = client.get("/api/v1/sdn/dashboard/stats")
        assert stats_res.status_code == 200
        stats_body = tool._unwrap_payload(stats_res.json())
        northbound = stats_body.get("northbound_kpi") or {}
        totals = northbound.get("totals") or {}
        assert int(totals.get("deliveries") or 0) == 1
        assert int(totals.get("success") or 0) == 1
        assert int(totals.get("failed") or 0) == 0
        assert float(northbound.get("success_rate_pct") or 0) == 100.0
        assert str(northbound.get("status") or "") == "healthy"

        db = SessionLocal()
        try:
            logs = db.query(EventLog).filter(EventLog.event_id == "NORTHBOUND_WEBHOOK_DELIVERY").all()
            assert len(logs) == 1
        finally:
            db.close()

        tool._restore_direct_webhook_settings(snapshot)
        db = SessionLocal()
        try:
            rows = db.query(SystemSetting).filter(SystemSetting.key.in_(list(tool._WEBHOOK_SETTING_KEYS))).all()
            assert rows == []
        finally:
            db.close()
    finally:
        server.shutdown()
        server.server_close()
