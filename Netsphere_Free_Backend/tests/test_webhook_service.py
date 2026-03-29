import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import device as _device
from app.models.device import EventLog
from app.models.settings import SystemSetting
from app.services import webhook_service as webhook_mod
from app.services.webhook_service import WebhookService


def _new_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


def _set_setting(db, key: str, value: str):
    row = db.query(SystemSetting).filter(SystemSetting.key == str(key)).first()
    if row is None:
        row = SystemSetting(key=str(key), value=str(value), description="t", category="system")
    else:
        row.value = str(value)
    db.add(row)
    db.commit()


class _Resp:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = int(status_code)
        self.text = text


def test_webhook_send_retries_on_5xx_then_success(monkeypatch):
    db = _new_db()
    try:
        _set_setting(db, "webhook_enabled", "true")
        _set_setting(db, "webhook_url", "https://example.local/webhook")
        _set_setting(db, "webhook_retry_attempts", "3")
        _set_setting(db, "webhook_retry_backoff_seconds", "0")
        _set_setting(db, "webhook_retry_jitter_seconds", "0")

        calls = []
        responses = [_Resp(502, "bad gateway"), _Resp(200, "ok")]

        def fake_post(*args, **kwargs):
            calls.append((args, kwargs))
            return responses[len(calls) - 1]

        monkeypatch.setattr(webhook_mod.requests, "post", fake_post)
        monkeypatch.setattr(webhook_mod.time, "sleep", lambda *_: None)

        out = WebhookService.send(
            db,
            event_type="issue",
            title="critical issue",
            message="packet loss detected",
            severity="critical",
            source="monitoring",
            data={"device_id": 7},
        )

        assert out["success"] is True
        assert int(out["attempts"]) == 2
        assert len(calls) == 2
        evt = db.query(EventLog).filter(EventLog.event_id == "NORTHBOUND_WEBHOOK_DELIVERY").order_by(EventLog.id.desc()).first()
        assert evt is not None
        payload = json.loads(str(evt.message or "{}"))
        assert payload.get("status") == "ok"
        assert int(payload.get("attempts") or 0) == 2
        assert str(payload.get("mode") or "") == "generic"
    finally:
        db.close()


def test_webhook_send_does_not_retry_4xx_by_default(monkeypatch):
    db = _new_db()
    try:
        _set_setting(db, "webhook_enabled", "true")
        _set_setting(db, "webhook_url", "https://example.local/webhook")
        _set_setting(db, "webhook_retry_attempts", "3")
        _set_setting(db, "webhook_retry_backoff_seconds", "0")
        _set_setting(db, "webhook_retry_jitter_seconds", "0")

        calls = []
        responses = [_Resp(400, "bad request"), _Resp(200, "ok")]

        def fake_post(*args, **kwargs):
            calls.append((args, kwargs))
            return responses[len(calls) - 1]

        monkeypatch.setattr(webhook_mod.requests, "post", fake_post)
        monkeypatch.setattr(webhook_mod.time, "sleep", lambda *_: None)

        out = WebhookService.send(
            db,
            event_type="issue",
            title="warning",
            message="fan speed abnormal",
            severity="warning",
            source="monitoring",
            data={},
        )

        assert out["success"] is False
        assert int(out["status_code"]) == 400
        assert int(out["attempts"]) == 1
        assert len(calls) == 1
        evt = db.query(EventLog).filter(EventLog.event_id == "NORTHBOUND_WEBHOOK_DELIVERY").order_by(EventLog.id.desc()).first()
        assert evt is not None
        payload = json.loads(str(evt.message or "{}"))
        assert payload.get("status") == "failed"
        assert payload.get("failure_cause") == "http_4xx"
    finally:
        db.close()


def test_webhook_send_retries_4xx_when_enabled(monkeypatch):
    db = _new_db()
    try:
        _set_setting(db, "webhook_enabled", "true")
        _set_setting(db, "webhook_url", "https://example.local/webhook")
        _set_setting(db, "webhook_retry_attempts", "3")
        _set_setting(db, "webhook_retry_backoff_seconds", "0")
        _set_setting(db, "webhook_retry_jitter_seconds", "0")
        _set_setting(db, "webhook_retry_on_4xx", "true")

        calls = []
        responses = [_Resp(409, "conflict"), _Resp(202, "accepted")]

        def fake_post(*args, **kwargs):
            calls.append((args, kwargs))
            return responses[len(calls) - 1]

        monkeypatch.setattr(webhook_mod.requests, "post", fake_post)
        monkeypatch.setattr(webhook_mod.time, "sleep", lambda *_: None)

        out = WebhookService.send(
            db,
            event_type="closed_loop",
            title="auto action",
            message="triggered action",
            severity="info",
            source="closed_loop",
            data={"rule_id": "rule-1"},
        )

        assert out["success"] is True
        assert int(out["attempts"]) == 2
        assert len(calls) == 2
    finally:
        db.close()


def test_webhook_send_applies_auth_and_signatures(monkeypatch):
    db = _new_db()
    try:
        _set_setting(db, "webhook_enabled", "true")
        _set_setting(db, "webhook_url", "https://example.local/webhook")
        _set_setting(db, "webhook_retry_attempts", "1")
        _set_setting(db, "webhook_secret", "super-secret")
        _set_setting(db, "webhook_auth_type", "bearer")
        _set_setting(db, "webhook_auth_token", "token-123")
        _set_setting(db, "webhook_delivery_mode", "splunk")

        captured = {}

        def fake_post(*_args, **kwargs):
            captured["headers"] = dict(kwargs.get("headers") or {})
            captured["body"] = kwargs.get("data")
            return _Resp(200, "ok")

        monkeypatch.setattr(webhook_mod.requests, "post", fake_post)

        out = WebhookService.send(
            db,
            event_type="issue",
            title="critical issue",
            message="bgp down",
            severity="critical",
            source="monitoring",
            data={"site_id": 10},
        )

        assert out["success"] is True
        assert out["mode"] == "splunk"
        headers = captured["headers"]
        assert headers.get("Authorization") == "Bearer token-123"
        assert headers.get("Content-Type") == "application/json"
        assert headers.get("X-NetManager-Signature")
        assert str(headers.get("X-NetManager-Signature-V2", "")).startswith("sha256=")
        assert headers.get("X-NetManager-Delivery-Id")
        assert headers.get("X-NetManager-Timestamp")

        body = json.loads((captured.get("body") or b"{}").decode("utf-8"))
        assert body.get("sourcetype") == "netmanager:issue"
        assert isinstance(body.get("event"), dict)
    finally:
        db.close()


def test_webhook_send_jira_includes_project_and_issue_type(monkeypatch):
    db = _new_db()
    try:
        _set_setting(db, "webhook_enabled", "true")
        _set_setting(db, "webhook_url", "https://jira.local/rest/api/2/issue")
        _set_setting(db, "webhook_retry_attempts", "1")
        _set_setting(db, "webhook_delivery_mode", "jira")
        _set_setting(db, "webhook_jira_project_key", "NET")
        _set_setting(db, "webhook_jira_issue_type", "Incident")

        captured = {}

        def fake_post(*_args, **kwargs):
            captured["body"] = kwargs.get("data")
            return _Resp(201, "created")

        monkeypatch.setattr(webhook_mod.requests, "post", fake_post)

        out = WebhookService.send(
            db,
            event_type="closed_loop",
            title="Jira Connector Test",
            message="Jira payload check",
            severity="warning",
            source="northbound",
            data={"rule_id": "r-100"},
        )

        assert out["success"] is True
        assert out["mode"] == "jira"
        body = json.loads((captured.get("body") or b"{}").decode("utf-8"))
        fields = body.get("fields") or {}
        assert (fields.get("project") or {}).get("key") == "NET"
        assert (fields.get("issuetype") or {}).get("name") == "Incident"
    finally:
        db.close()


def test_webhook_send_servicenow_includes_table(monkeypatch):
    db = _new_db()
    try:
        _set_setting(db, "webhook_enabled", "true")
        _set_setting(db, "webhook_url", "https://snow.local/api/now/table/incident")
        _set_setting(db, "webhook_retry_attempts", "1")
        _set_setting(db, "webhook_delivery_mode", "servicenow")
        _set_setting(db, "webhook_servicenow_table", "u_custom_incident")

        captured = {}

        def fake_post(*_args, **kwargs):
            captured["body"] = kwargs.get("data")
            return _Resp(200, "ok")

        monkeypatch.setattr(webhook_mod.requests, "post", fake_post)

        out = WebhookService.send(
            db,
            event_type="issue",
            title="ServiceNow Connector Test",
            message="ServiceNow payload check",
            severity="critical",
            source="northbound",
            data={"device_id": 77},
        )

        assert out["success"] is True
        assert out["mode"] == "servicenow"
        body = json.loads((captured.get("body") or b"{}").decode("utf-8"))
        assert body.get("table") == "u_custom_incident"
        assert str(body.get("short_description") or "") == "ServiceNow Connector Test"
    finally:
        db.close()


def test_webhook_send_elastic_includes_index(monkeypatch):
    db = _new_db()
    try:
        _set_setting(db, "webhook_enabled", "true")
        _set_setting(db, "webhook_url", "https://elastic.local/netmanager/_doc")
        _set_setting(db, "webhook_retry_attempts", "1")
        _set_setting(db, "webhook_delivery_mode", "elastic")
        _set_setting(db, "webhook_elastic_index", "netmanager-alerts")

        captured = {}

        def fake_post(*_args, **kwargs):
            captured["body"] = kwargs.get("data")
            return _Resp(200, "ok")

        monkeypatch.setattr(webhook_mod.requests, "post", fake_post)

        out = WebhookService.send(
            db,
            event_type="issue",
            title="Elastic Connector Test",
            message="Elastic payload check",
            severity="info",
            source="northbound",
            data={"site_id": 10},
        )

        assert out["success"] is True
        assert out["mode"] == "elastic"
        body = json.loads((captured.get("body") or b"{}").decode("utf-8"))
        assert body.get("_index") == "netmanager-alerts"
        assert isinstance(body.get("event"), dict)
    finally:
        db.close()


def test_webhook_send_signature_v2_matches_timestamp_and_body(monkeypatch):
    db = _new_db()
    try:
        _set_setting(db, "webhook_enabled", "true")
        _set_setting(db, "webhook_url", "https://example.local/webhook")
        _set_setting(db, "webhook_retry_attempts", "1")
        _set_setting(db, "webhook_secret", "super-secret")

        captured = {}

        def fake_post(*_args, **kwargs):
            captured["headers"] = dict(kwargs.get("headers") or {})
            captured["body"] = kwargs.get("data")
            return _Resp(200, "ok")

        monkeypatch.setattr(webhook_mod.requests, "post", fake_post)
        monkeypatch.setattr(webhook_mod.time, "time", lambda: 1700000000)

        out = WebhookService.send(
            db,
            event_type="issue",
            title="signature test",
            message="signature test body",
            severity="info",
            source="northbound",
            data={"x": 1},
        )
        assert out["success"] is True

        headers = captured.get("headers") or {}
        body = captured.get("body") or b""
        timestamp = str(headers.get("X-NetManager-Timestamp") or "")
        assert timestamp == "1700000000"
        expected = WebhookService._signature_v2("super-secret", timestamp, body)
        assert headers.get("X-NetManager-Signature-V2") == f"sha256={expected}"
    finally:
        db.close()


def test_webhook_send_retry_backoff_is_capped_by_max(monkeypatch):
    db = _new_db()
    try:
        _set_setting(db, "webhook_enabled", "true")
        _set_setting(db, "webhook_url", "https://example.local/webhook")
        _set_setting(db, "webhook_retry_attempts", "4")
        _set_setting(db, "webhook_retry_backoff_seconds", "2")
        _set_setting(db, "webhook_retry_max_backoff_seconds", "3")
        _set_setting(db, "webhook_retry_jitter_seconds", "0")

        monkeypatch.setattr(webhook_mod.requests, "post", lambda *_a, **_k: _Resp(503, "unavailable"))

        sleeps = []
        monkeypatch.setattr(webhook_mod.time, "sleep", lambda sec: sleeps.append(float(sec)))

        out = WebhookService.send(
            db,
            event_type="issue",
            title="backoff cap",
            message="backoff cap",
            severity="warning",
            source="northbound",
            data={},
        )
        assert out["success"] is False
        assert int(out.get("attempts") or 0) == 4
        assert sleeps == [2.0, 3.0, 3.0]
    finally:
        db.close()


def test_webhook_send_long_run_mixed_outcomes_emits_delivery_events(monkeypatch):
    db = _new_db()
    try:
        _set_setting(db, "webhook_enabled", "true")
        _set_setting(db, "webhook_url", "https://example.local/webhook")
        _set_setting(db, "webhook_retry_attempts", "2")
        _set_setting(db, "webhook_retry_backoff_seconds", "0")
        _set_setting(db, "webhook_retry_jitter_seconds", "0")
        _set_setting(db, "webhook_retry_on_4xx", "false")

        seen_deliveries = []
        delivery_mode = {}
        delivery_attempts = {}

        def fake_post(*_args, **kwargs):
            headers = dict(kwargs.get("headers") or {})
            delivery_id = str(headers.get("X-NetManager-Delivery-Id") or "")
            if delivery_id not in delivery_mode:
                delivery_mode[delivery_id] = len(seen_deliveries) % 4
                seen_deliveries.append(delivery_id)
            delivery_attempts[delivery_id] = int(delivery_attempts.get(delivery_id, 0)) + 1
            scenario = int(delivery_mode[delivery_id])
            attempt = int(delivery_attempts[delivery_id])

            if scenario == 0:
                return _Resp(200, "ok")
            if scenario == 1:
                return _Resp(502, "bad gateway") if attempt == 1 else _Resp(200, "ok")
            if scenario == 2:
                return _Resp(409, "conflict")
            return _Resp(503, "service unavailable")

        monkeypatch.setattr(webhook_mod.requests, "post", fake_post)
        monkeypatch.setattr(webhook_mod.time, "sleep", lambda *_: None)

        results = []
        for i in range(20):
            out = WebhookService.send(
                db,
                event_type="issue",
                title=f"long-run-{i}",
                message="long-run",
                severity="info",
                source="northbound",
                data={"idx": i},
            )
            results.append(bool(out.get("success")))

        assert len(results) == 20
        assert any(results) is True
        assert any(not x for x in results) is True

        rows = (
            db.query(EventLog)
            .filter(EventLog.event_id == "NORTHBOUND_WEBHOOK_DELIVERY")
            .order_by(EventLog.id.asc())
            .all()
        )
        assert len(rows) == 20
        payloads = [json.loads(str(r.message or "{}")) for r in rows]
        statuses = {str(p.get("status") or "").strip().lower() for p in payloads}
        causes = {str(p.get("failure_cause") or "").strip().lower() for p in payloads if p.get("failure_cause")}
        assert "ok" in statuses
        assert "failed" in statuses
        assert "http_4xx" in causes
        assert "http_5xx" in causes
    finally:
        db.close()
