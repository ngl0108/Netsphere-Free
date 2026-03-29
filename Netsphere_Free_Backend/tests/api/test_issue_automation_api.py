import json

from app.models.approval import ApprovalRequest
from app.models.device import Device, EventLog, Issue, SystemMetric
from app.models.settings import SystemSetting


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _set_setting(db, key: str, value: str, category: str = "system"):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        row = SystemSetting(key=key, value=str(value), description=key, category=category)
    else:
        row.value = str(value)
        row.category = category
    db.add(row)
    db.commit()
    return row


def _seed_issue_rule(db):
    rule = {
        "id": "issue-bgp-run-scan",
        "name": "BGP Alert Scan",
        "enabled": True,
        "condition": {"path": "issue.signals.is_bgp", "operator": "==", "value": True},
        "action": {
            "type": "run_scan",
            "title": "Re-scan BGP Segment",
            "message": "BGP alert follow-up",
            "payload": {"cidr": "10.77.0.0/24"},
        },
        "require_approval": False,
        "cooldown_seconds": 300,
        "max_actions_per_hour": 5,
    }
    _set_setting(db, "closed_loop_rules_json", json.dumps([rule], ensure_ascii=False), category="closed_loop")
    return rule


def _seed_issue_fixture(db):
    device = Device(
        name="bgp-edge-1",
        hostname="bgp-edge-1",
        ip_address="10.77.0.10",
        status="online",
        device_type="cisco_ios",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    db.add(
        SystemMetric(
            device_id=int(device.id),
            cpu_usage=64.0,
            memory_usage=41.0,
            traffic_in=2500.0,
            traffic_out=1300.0,
        )
    )
    issue = Issue(
        device_id=int(device.id),
        title="BGP Neighbor Down: bgp-edge-1",
        description="peer 10.0.0.2 is down",
        severity="warning",
        category="system",
        status="active",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return device, issue


def _seed_cloud_issue_fixture(db):
    device = Device(
        name="aws-app-subnet-1",
        hostname="aws-app-subnet-1",
        ip_address="10.120.0.10",
        status="online",
        device_type="cloud_virtual",
        variables={
            "cloud": {
                "refs": [
                    {
                        "provider": "aws",
                        "account_id": 101,
                        "account_name": "aws-prod",
                        "region": "ap-northeast-2",
                        "resource_type": "subnet",
                        "resource_id": "subnet-001",
                        "name": "app-subnet-a",
                    },
                    {
                        "provider": "aws",
                        "account_id": 101,
                        "account_name": "aws-prod",
                        "region": "ap-northeast-2",
                        "resource_type": "route_table",
                        "resource_id": "rtb-001",
                        "name": "app-rtb",
                    },
                    {
                        "provider": "aws",
                        "account_id": 101,
                        "account_name": "aws-prod",
                        "region": "ap-northeast-2",
                        "resource_type": "security_group",
                        "resource_id": "sg-001",
                        "name": "app-sg",
                    },
                ],
            },
        },
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    issue = Issue(
        device_id=int(device.id),
        title="Cloud route drift detected",
        description="Detected an unexpected route path for app-subnet-a.",
        severity="warning",
        category="config",
        status="active",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return device, issue


def test_active_issues_include_automation_summary(client, normal_user_token, db):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    _set_setting(db, "closed_loop_execute_change_actions", "false")
    _seed_issue_rule(db)
    _seed_issue_fixture(db)

    res = client.get("/api/v1/sdn/issues/active", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert len(body) == 1
    automation = body[0].get("automation") or {}
    assert automation.get("primary_status") == "approval_required"
    assert int(automation.get("matched_rules") or 0) == 1
    primary_action = automation.get("primary_action") or {}
    assert primary_action.get("action_type") == "run_scan"


def test_issue_automation_preview_exposes_issue_signal_snapshot(client, normal_user_token, db):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    _set_setting(db, "closed_loop_execute_change_actions", "false")
    _seed_issue_rule(db)
    _, issue = _seed_issue_fixture(db)

    res = client.get(f"/api/v1/sdn/issues/{int(issue.id)}/automation", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    automation = body.get("automation") or {}
    snapshot = automation.get("snapshot") or {}
    issue_snapshot = snapshot.get("issue") or {}
    signals = issue_snapshot.get("signals") or {}
    assert body.get("issue_id") == int(issue.id)
    assert automation.get("primary_status") == "approval_required"
    assert automation.get("can_run") is True
    assert signals.get("is_bgp") is True
    assert "issue.signals.is_bgp" in list(issue_snapshot.get("match_paths") or [])


def test_active_issues_include_cloud_scope_for_cloud_virtual_device(client, normal_user_token, db):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _seed_cloud_issue_fixture(db)

    res = client.get("/api/v1/sdn/issues/active", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert len(body) == 1
    cloud_scope = body[0].get("cloud_scope") or {}
    assert cloud_scope.get("provider") == "aws"
    assert int(cloud_scope.get("account_id") or 0) == 101
    assert cloud_scope.get("account_name") == "aws-prod"
    assert cloud_scope.get("region") == "ap-northeast-2"
    assert cloud_scope.get("resource_type") == "subnet"
    assert cloud_scope.get("resource_name") == "app-subnet-a"
    assert cloud_scope.get("resource_id") == "subnet-001"
    assert sorted(list(cloud_scope.get("resource_types") or [])) == ["route_table", "security_group", "subnet"]
    assert cloud_scope.get("can_create_intent") is True


def test_issue_automation_run_opens_approval_for_direct_change_action(client, operator_user_token, db):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    _set_setting(db, "closed_loop_execute_change_actions", "false")
    _seed_issue_rule(db)
    _, issue = _seed_issue_fixture(db)

    res = client.post(f"/api/v1/sdn/issues/{int(issue.id)}/automation/run", headers=operator_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    result = body.get("result") or {}
    decisions = list(result.get("decisions") or [])
    assert int(result.get("executed") or 0) == 1
    assert len(decisions) == 1
    assert decisions[0].get("status") == "executed"
    assert int(decisions[0].get("approval_id") or 0) > 0
    assert (decisions[0].get("result") or {}).get("mode") == "approval_opened"

    approvals = db.query(ApprovalRequest).filter(ApprovalRequest.request_type == "closed_loop_action").all()
    assert len(approvals) == 1
    payload = dict(approvals[0].payload or {})
    context = payload.get("context") or {}
    issue_ctx = context.get("issue") or {}
    assert int(issue_ctx.get("id") or 0) == int(issue.id)

    logs = db.query(EventLog).filter(EventLog.event_id == "CLOSED_LOOP_EVAL_SUMMARY").all()
    assert len(logs) == 1
    summary = json.loads(str(logs[0].message or ""))
    assert summary.get("dry_run") is False
    assert summary.get("source") == "issue_automation"
    assert int(summary.get("issue_id") or 0) == int(issue.id)
    assert int(summary.get("device_id") or 0) == int(issue.device_id or 0)
    assert int(summary.get("executed") or 0) == 1
