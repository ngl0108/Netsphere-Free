import io
import json
import zipfile
from datetime import datetime, timezone

from app.models.approval import ApprovalRequest
from app.models.device import EventLog
from app.models.user import User


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_approval_evidence_package_downloads_zip_with_execution_artifacts(client, admin_user_token, db):
    admin_user = db.query(User).filter(User.username == "adminuser").first()
    approval = ApprovalRequest(
        requester_id=int(admin_user.id),
        approver_id=int(admin_user.id),
        title="Template rollout",
        description="Deploy template to distribution switches",
        request_type="template_deploy",
        status="approved",
        payload={
            "execution_status": "post_check_failed",
            "execution_id": "exec-001",
            "execution_result": {
                "summary": [
                    {
                        "device_id": 101,
                        "status": "post_check_failed",
                        "rollback_attempted": True,
                        "rollback_success": True,
                        "failure_cause": "post_check_failed",
                    }
                ]
            },
            "execution_trace": {
                "waves": [
                    {"wave": 1, "status": "failed", "device_ids": [101]},
                ]
            },
        },
    )
    db.add(approval)
    db.flush()
    approval.payload["approval_id"] = int(approval.id)
    db.add(
        EventLog(
            event_id="CHANGE_EXECUTION_KPI",
            severity="warning",
            source="change_engine",
            message=json.dumps(
                {
                    "approval_id": int(approval.id),
                    "execution_id": "exec-001",
                    "post_check_failed": 1,
                    "rollback_attempted": 1,
                    "rollback_success": 1,
                }
            ),
            timestamp=datetime.now(timezone.utc),
        )
    )
    db.commit()

    res = client.get(f"/api/v1/approval/{approval.id}/evidence-package", headers=admin_user_token)

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/zip")
    assert f"approval_evidence_{approval.id}_" in res.headers.get("content-disposition", "")

    zf = zipfile.ZipFile(io.BytesIO(res.content))
    names = set(zf.namelist())
    assert "README.txt" in names
    assert "approval-request.json" in names
    assert "approval-summary.json" in names
    assert "change-traces.json" in names
    assert "execution-result.json" in names
    assert "execution-trace.json" in names

    request_body = json.loads(zf.read("approval-request.json").decode("utf-8"))
    summary_body = json.loads(zf.read("approval-summary.json").decode("utf-8"))
    traces_body = json.loads(zf.read("change-traces.json").decode("utf-8"))

    assert int(request_body["id"]) == int(approval.id)
    assert summary_body["execution_status"] == "post_check_failed"
    assert summary_body["diagnostics"]["rollback_attempted"] == 1
    assert summary_body["diagnostics"]["rollback_success"] == 1
    assert isinstance(traces_body, list)
    assert len(traces_body) == 1


def test_webhook_delivery_history_lists_recent_deliveries_and_retry_replays(client, admin_user_token, db, monkeypatch):
    delivery_payload = {
        "delivery_id": "delivery-001",
        "mode": "jira",
        "event_type": "issue.created",
        "status": "failed",
        "attempts": 3,
        "retry_attempts": 2,
        "status_code": 503,
        "failure_cause": "http_5xx",
        "error": "service unavailable",
        "target_host": "jira.example.com",
        "target_path": "/rest/api/3/issue",
        "replay": {
            "event_type": "issue.created",
            "title": "[NetSphere] BGP alarm",
            "message": "BGP control-plane alarm is active",
            "severity": "critical",
            "source": "netmanager",
            "data": {"kind": "issue", "issue_id": 42},
        },
    }
    db.add(
        EventLog(
            event_id="NORTHBOUND_WEBHOOK_DELIVERY",
            severity="warning",
            source="webhook",
            message=json.dumps(delivery_payload),
            timestamp=datetime.now(timezone.utc),
        )
    )
    db.commit()

    history_res = client.get("/api/v1/settings/webhook-deliveries", headers=admin_user_token)

    assert history_res.status_code == 200
    body = _unwrap(history_res.json())
    assert body["total"] == 1
    item = body["items"][0]
    assert item["delivery_id"] == "delivery-001"
    assert item["status"] == "failed"
    assert item["replay_available"] is True
    assert item["target_host"] == "jira.example.com"

    from app.services import webhook_service as webhook_mod

    calls = {}

    def fake_send(db_session, *, event_type, title, message, severity, source, data):
      calls["event_type"] = event_type
      calls["title"] = title
      calls["message"] = message
      calls["severity"] = severity
      calls["source"] = source
      calls["data"] = dict(data or {})
      return {
          "success": True,
          "mode": "jira",
          "status_code": 201,
          "attempts": 1,
          "delivery_id": "delivery-002",
      }

    monkeypatch.setattr(webhook_mod.WebhookService, "send", staticmethod(fake_send))

    retry_res = client.post(
        "/api/v1/settings/webhook-deliveries/delivery-001/retry",
        json={"reason": "manual operator retry"},
        headers=admin_user_token,
    )

    assert retry_res.status_code == 200
    retry_body = _unwrap(retry_res.json())
    assert retry_body["result"]["replayed_delivery_id"] == "delivery-001"
    assert retry_body["result"]["delivery_id"] == "delivery-002"
    assert calls["event_type"] == "issue.created"
    assert calls["title"] == "[NetSphere] BGP alarm"
    assert calls["severity"] == "critical"
    assert calls["data"]["replay_of_delivery_id"] == "delivery-001"
    assert calls["data"]["retry_reason"] == "manual operator retry"
