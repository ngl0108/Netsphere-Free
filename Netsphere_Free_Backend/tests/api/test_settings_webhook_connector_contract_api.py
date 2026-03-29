import hmac
import json
from hashlib import sha256

import pytest

from app.models.device import EventLog


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


class _Resp:
    def __init__(self, status_code: int, text: str = ""):
        self.status_code = int(status_code)
        self.text = str(text or "")


@pytest.mark.parametrize(
    "mode,extra_settings,expected_http_status",
    [
        (
            "jira",
            {
                "webhook_jira_project_key": "NET",
                "webhook_jira_issue_type": "Incident",
            },
            201,
        ),
        (
            "servicenow",
            {
                "webhook_servicenow_table": "u_netmanager_incident",
            },
            200,
        ),
        (
            "splunk",
            {},
            200,
        ),
        (
            "elastic",
            {
                "webhook_elastic_index": "netmanager-alerts",
            },
            200,
        ),
    ],
)
def test_test_webhook_connector_mode_contract_and_signature(
    client,
    admin_user_token,
    monkeypatch,
    mode,
    extra_settings,
    expected_http_status,
):
    from app.services import webhook_service as webhook_mod

    captured = {}

    def fake_post(*args, **kwargs):
        captured["url"] = args[0] if args else kwargs.get("url")
        captured["body"] = kwargs.get("data")
        captured["headers"] = dict(kwargs.get("headers") or {})
        captured["timeout"] = kwargs.get("timeout")
        return _Resp(expected_http_status, "ok")

    monkeypatch.setattr(webhook_mod.requests, "post", fake_post)
    monkeypatch.setattr(webhook_mod.time, "time", lambda: 1700000000)

    settings_payload = {
        "webhook_enabled": True,
        "webhook_url": "https://itsm.local/webhook",
        "webhook_secret": "unit-secret",
        "webhook_delivery_mode": mode,
        "webhook_retry_attempts": 2,
        "webhook_retry_backoff_seconds": 0,
        "webhook_retry_jitter_seconds": 0,
    }
    settings_payload.update(extra_settings)

    put_res = client.put(
        "/api/v1/settings/general",
        json={"settings": settings_payload},
        headers=admin_user_token,
    )
    assert put_res.status_code == 200

    res = client.post(
        "/api/v1/settings/test-webhook-connector",
        json={
            "event_type": "test",
            "title": "connector contract test",
            "message": "connector contract test body",
        },
        headers=admin_user_token,
    )
    assert res.status_code == 200
    payload = _unwrap(res.json())
    result = payload.get("result") or {}
    assert result.get("mode") == mode
    assert int(result.get("attempts") or 0) == 1
    assert int(result.get("status_code") or 0) == int(expected_http_status)

    headers = captured.get("headers") or {}
    body_bytes = captured.get("body") or b""
    timestamp = str(headers.get("X-NetManager-Timestamp") or "")
    assert timestamp == "1700000000"
    assert str(headers.get("X-NetManager-Delivery-Id") or "").strip() != ""
    assert str(headers.get("X-NetManager-Event-Type") or "").strip() == "test"
    expected_sig_v2 = hmac.new(
        b"unit-secret",
        f"{timestamp}.".encode("utf-8") + body_bytes,
        sha256,
    ).hexdigest()
    assert headers.get("X-NetManager-Signature-V2") == f"sha256={expected_sig_v2}"

    body = json.loads(body_bytes.decode("utf-8") or "{}")
    if mode == "jira":
        fields = body.get("fields") or {}
        assert (fields.get("project") or {}).get("key") == "NET"
        assert (fields.get("issuetype") or {}).get("name") == "Incident"
    elif mode == "servicenow":
        assert body.get("table") == "u_netmanager_incident"
        assert str(body.get("short_description") or "") == "connector contract test"
    elif mode == "splunk":
        assert str(body.get("sourcetype") or "").startswith("netmanager:")
        assert isinstance(body.get("event"), dict)
    elif mode == "elastic":
        assert body.get("_index") == "netmanager-alerts"
        assert isinstance(body.get("event"), dict)


def test_test_webhook_connector_retry_backoff_contract(client, admin_user_token, db, monkeypatch):
    from app.services import webhook_service as webhook_mod

    calls = []
    sleeps = []

    def fake_post(*_args, **_kwargs):
        calls.append(1)
        if len(calls) < 4:
            return _Resp(503, "service unavailable")
        return _Resp(200, "ok")

    monkeypatch.setattr(webhook_mod.requests, "post", fake_post)
    monkeypatch.setattr(webhook_mod.time, "sleep", lambda sec: sleeps.append(float(sec)))

    put_res = client.put(
        "/api/v1/settings/general",
        json={
            "settings": {
                "webhook_enabled": True,
                "webhook_url": "https://itsm.local/webhook",
                "webhook_secret": "unit-secret",
                "webhook_delivery_mode": "generic",
                "webhook_retry_attempts": 4,
                "webhook_retry_backoff_seconds": 2,
                "webhook_retry_max_backoff_seconds": 3,
                "webhook_retry_jitter_seconds": 0,
            }
        },
        headers=admin_user_token,
    )
    assert put_res.status_code == 200

    res = client.post(
        "/api/v1/settings/test-webhook-connector",
        json={"event_type": "test", "title": "retry contract", "message": "retry contract"},
        headers=admin_user_token,
    )
    assert res.status_code == 200
    payload = _unwrap(res.json())
    result = payload.get("result") or {}
    assert int(result.get("attempts") or 0) == 4
    assert int(result.get("status_code") or 0) == 200
    assert sleeps == [2.0, 3.0, 3.0]

    evt = (
        db.query(EventLog)
        .filter(EventLog.event_id == "NORTHBOUND_WEBHOOK_DELIVERY")
        .order_by(EventLog.id.desc())
        .first()
    )
    assert evt is not None
    evt_payload = json.loads(str(evt.message or "{}"))
    assert evt_payload.get("status") == "ok"
    assert int(evt_payload.get("attempts") or 0) == 4


def test_test_webhook_connector_returns_400_when_remote_4xx_and_no_retry(
    client,
    admin_user_token,
    db,
    monkeypatch,
):
    from app.services import webhook_service as webhook_mod

    calls = []

    def fake_post(*_args, **_kwargs):
        calls.append(1)
        return _Resp(403, "forbidden")

    monkeypatch.setattr(webhook_mod.requests, "post", fake_post)
    monkeypatch.setattr(webhook_mod.time, "sleep", lambda *_: None)

    put_res = client.put(
        "/api/v1/settings/general",
        json={
            "settings": {
                "webhook_enabled": True,
                "webhook_url": "https://itsm.local/webhook",
                "webhook_delivery_mode": "generic",
                "webhook_retry_attempts": 3,
                "webhook_retry_backoff_seconds": 0,
                "webhook_retry_jitter_seconds": 0,
                "webhook_retry_on_4xx": False,
            }
        },
        headers=admin_user_token,
    )
    assert put_res.status_code == 200

    res = client.post(
        "/api/v1/settings/test-webhook-connector",
        json={"event_type": "test", "title": "4xx contract", "message": "4xx contract"},
        headers=admin_user_token,
    )
    assert res.status_code == 400
    assert len(calls) == 1

    evt = (
        db.query(EventLog)
        .filter(EventLog.event_id == "NORTHBOUND_WEBHOOK_DELIVERY")
        .order_by(EventLog.id.desc())
        .first()
    )
    assert evt is not None
    payload = json.loads(str(evt.message or "{}"))
    assert payload.get("status") == "failed"
    assert payload.get("failure_cause") == "http_4xx"
    assert int(payload.get("attempts") or 0) == 1
