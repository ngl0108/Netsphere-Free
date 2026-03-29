from app.models.approval import ApprovalRequest
import json

from app.models.device import Device, EventLog, SystemMetric
from app.models.settings import SystemSetting
from app.services import closed_loop_service as closed_loop_service_mod


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


def _sample_rule(rule_id: str = "r-cpu-high"):
    return {
        "id": rule_id,
        "name": "CPU High Rule",
        "enabled": True,
        "condition": {"path": "summary.cpu_avg", "operator": ">=", "value": 80},
        "action": {"type": "notify", "title": "CPU High", "message": "CPU threshold reached"},
        "require_approval": True,
        "cooldown_seconds": 600,
        "max_actions_per_hour": 5,
    }


def test_closed_loop_status_defaults(client, normal_user_token):
    res = client.get("/api/v1/intent/closed-loop/status", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["engine_enabled"] is False
    assert body["auto_execute_enabled"] is False
    assert body["execute_change_actions_enabled"] is False
    assert int((body.get("rules_lint") or {}).get("conflicts_count") or 0) == 0
    assert int((body.get("rules_lint") or {}).get("warnings_count") or 0) == 0
    assert int(body["default_cooldown_seconds"]) >= 5
    assert int(body["default_max_actions_per_hour"]) >= 1


def test_closed_loop_rules_save_and_get(client, operator_user_token):
    payload = {"rules": [_sample_rule()]}
    saved = client.put("/api/v1/intent/closed-loop/rules", json=payload, headers=operator_user_token)
    assert saved.status_code == 200
    body = _unwrap(saved.json())
    assert int(body["saved"]) == 1
    assert str(body["rules"][0]["id"]) == "r-cpu-high"
    assert int((body.get("lint") or {}).get("conflicts_count") or 0) == 0
    assert int((body.get("lint") or {}).get("warnings_count") or 0) == 0

    fetched = client.get("/api/v1/intent/closed-loop/rules", headers=operator_user_token)
    assert fetched.status_code == 200
    out = _unwrap(fetched.json())
    assert int(out["count"]) == 1
    assert str(out["rules"][0]["condition"]["path"]) == "summary.cpu_avg"


def test_closed_loop_rules_lint_detects_condition_action_conflict(client, operator_user_token):
    first = _sample_rule("r-conflict-a")
    second = _sample_rule("r-conflict-b")
    second["action"] = {
        "type": "open_approval",
        "title": "CPU review",
        "message": "review needed",
        "payload": {"risk": "high"},
    }
    second["require_approval"] = True

    res = client.post(
        "/api/v1/intent/closed-loop/rules/lint",
        json={"rules": [first, second]},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert int(body.get("rules_total") or 0) == 2
    assert int(body.get("rules_enabled") or 0) == 2
    assert int(body.get("conflicts_count") or 0) == 1
    assert int(body.get("warnings_count") or 0) == 0
    conflicts = list(body.get("conflicts") or [])
    assert len(conflicts) == 1
    assert conflicts[0].get("type") == "condition_action_conflict"
    assert set(conflicts[0].get("rule_ids") or []) == {"r-conflict-a", "r-conflict-b"}


def test_closed_loop_rules_save_returns_lint_summary(client, operator_user_token):
    first = _sample_rule("r-save-lint-a")
    second = _sample_rule("r-save-lint-b")
    second["action"] = {
        "type": "open_approval",
        "title": "CPU review",
        "message": "review needed",
        "payload": {"risk": "high"},
    }
    second["require_approval"] = True

    saved = client.put(
        "/api/v1/intent/closed-loop/rules",
        json={"rules": [first, second]},
        headers=operator_user_token,
    )
    assert saved.status_code == 200
    body = _unwrap(saved.json())
    lint = body.get("lint") or {}
    assert int(lint.get("conflicts_count") or 0) == 1
    assert int(lint.get("warnings_count") or 0) == 0

    current = client.get("/api/v1/intent/closed-loop/rules/lint", headers=operator_user_token)
    assert current.status_code == 200
    current_body = _unwrap(current.json())
    assert int(current_body.get("conflicts_count") or 0) == 1


def test_closed_loop_evaluate_blocked_when_engine_disabled(client, operator_user_token):
    res = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 91}}, "dry_run": True},
        headers=operator_user_token,
    )
    assert res.status_code == 403


def test_closed_loop_snapshot_uses_latest_metrics(client, operator_user_token, db):
    dev = Device(name="cl-snap-1", ip_address="10.55.0.1", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    db.add(SystemMetric(device_id=int(dev.id), cpu_usage=51.2, memory_usage=62.4, traffic_in=100.0, traffic_out=200.0))
    db.commit()

    res = client.get(f"/api/v1/intent/closed-loop/snapshot?device_id={int(dev.id)}", headers=operator_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    summary = body.get("summary") or {}
    assert int(summary.get("devices_total") or 0) == 1
    assert float(summary.get("cpu_avg") or 0.0) == 51.2
    assert float(summary.get("memory_avg") or 0.0) == 62.4
    assert float(summary.get("traffic_in_total") or 0.0) == 100.0
    assert float(summary.get("traffic_out_total") or 0.0) == 200.0


def test_closed_loop_evaluate_dry_run_match(client, operator_user_token, db):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "false")
    save = client.put(
        "/api/v1/intent/closed-loop/rules",
        json={"rules": [_sample_rule()]},
        headers=operator_user_token,
    )
    assert save.status_code == 200

    res = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 95}}, "dry_run": True},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["engine_enabled"] is True
    assert int(body["triggered"]) == 1
    assert int(body["executed"]) == 0
    decisions = list(body.get("decisions") or [])
    assert len(decisions) == 1
    assert decisions[0]["status"] == "matched_dry_run"


def test_closed_loop_evaluate_dry_run_logs_summary_but_dashboard_stats_ignore_it(
    client,
    operator_user_token,
    normal_user_token,
    db,
):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "false")
    save = client.put(
        "/api/v1/intent/closed-loop/rules",
        json={"rules": [_sample_rule("r-cpu-dry-kpi")]},
        headers=operator_user_token,
    )
    assert save.status_code == 200

    res = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 95}}, "dry_run": True},
        headers=operator_user_token,
    )
    assert res.status_code == 200

    logs = db.query(EventLog).filter(EventLog.event_id == "CLOSED_LOOP_EVAL_SUMMARY").all()
    assert len(logs) == 1
    payload = json.loads(str(logs[0].message or ""))
    assert payload["dry_run"] is True
    assert payload["source"] == "api"

    stats = client.get("/api/v1/sdn/dashboard/stats", headers=normal_user_token)
    assert stats.status_code == 200
    body = _unwrap(stats.json())
    closed_loop_kpi = body.get("closed_loop_kpi") or {}
    autonomy_kpi = body.get("autonomy_kpi") or {}
    assert int((closed_loop_kpi.get("totals") or {}).get("cycles") or 0) == 0
    assert int((closed_loop_kpi.get("totals") or {}).get("executed") or 0) == 0
    assert int((autonomy_kpi.get("totals") or {}).get("actions_executed") or 0) == 0


def test_closed_loop_live_evaluate_opens_approval_and_respects_cooldown(client, operator_user_token, db):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    live_rule = _sample_rule("r-cpu-live")
    live_rule["cooldown_seconds"] = 3600

    save = client.put(
        "/api/v1/intent/closed-loop/rules",
        json={"rules": [live_rule]},
        headers=operator_user_token,
    )
    assert save.status_code == 200

    first = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 95}}, "dry_run": False},
        headers=operator_user_token,
    )
    assert first.status_code == 200
    first_body = _unwrap(first.json())
    assert int(first_body["executed"]) == 1
    first_decisions = list(first_body.get("decisions") or [])
    assert len(first_decisions) == 1
    assert first_decisions[0]["status"] == "executed"
    approval_id = int(first_decisions[0].get("approval_id") or 0)
    assert approval_id > 0

    approvals = db.query(ApprovalRequest).all()
    assert len(approvals) == 1

    second = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 95}}, "dry_run": False},
        headers=operator_user_token,
    )
    assert second.status_code == 200
    second_body = _unwrap(second.json())
    assert int(second_body["blocked"]) == 1
    second_decisions = list(second_body.get("decisions") or [])
    assert len(second_decisions) == 1
    assert second_decisions[0]["status"] == "blocked_cooldown"

    approvals_after = db.query(ApprovalRequest).all()
    assert len(approvals_after) == 1


def test_closed_loop_run_scan_opens_approval_when_direct_change_execution_disabled(client, operator_user_token, db):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    _set_setting(db, "closed_loop_execute_change_actions", "false")

    rule = _sample_rule("r-run-scan-approval")
    rule["require_approval"] = False
    rule["action"] = {
        "type": "run_scan",
        "title": "Auto Discovery Scan",
        "message": "triggered",
        "payload": {"cidr": "10.77.0.0/24"},
    }

    save = client.put(
        "/api/v1/intent/closed-loop/rules",
        json={"rules": [rule]},
        headers=operator_user_token,
    )
    assert save.status_code == 200

    res = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 95}}, "dry_run": False},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert int(body["executed"]) == 1
    decisions = list(body.get("decisions") or [])
    assert len(decisions) == 1
    assert decisions[0]["status"] == "executed"
    assert int(decisions[0].get("approval_id") or 0) > 0
    assert (decisions[0].get("result") or {}).get("mode") == "approval_opened"


def test_closed_loop_run_scan_executes_dispatch_when_direct_change_enabled(client, operator_user_token, db, monkeypatch):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    _set_setting(db, "closed_loop_execute_change_actions", "true")

    rule = _sample_rule("r-run-scan-direct")
    rule["require_approval"] = False
    rule["action"] = {
        "type": "run_scan",
        "title": "Auto Discovery Scan",
        "message": "triggered",
        "payload": {"cidr": "10.88.0.0/24"},
    }

    save = client.put(
        "/api/v1/intent/closed-loop/rules",
        json={"rules": [rule]},
        headers=operator_user_token,
    )
    assert save.status_code == 200

    monkeypatch.setattr(
        closed_loop_service_mod.ClosedLoopService,
        "_execute_run_scan_action",
        staticmethod(lambda *_a, **_k: {"mode": "run_scan_dispatched", "job_id": 701}),
    )

    res = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 95}}, "dry_run": False},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert int(body["executed"]) == 1
    decisions = list(body.get("decisions") or [])
    assert len(decisions) == 1
    assert decisions[0]["status"] == "executed"
    assert int(decisions[0].get("approval_id") or 0) == 0
    result = decisions[0].get("result") or {}
    assert result.get("mode") == "run_scan_dispatched"
    assert int(result.get("job_id") or 0) == 701

    approvals = db.query(ApprovalRequest).filter(ApprovalRequest.request_type == "closed_loop_action").all()
    assert len(approvals) == 0


def test_closed_loop_template_deploy_executes_when_direct_change_enabled(client, operator_user_token, db, monkeypatch):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    _set_setting(db, "closed_loop_execute_change_actions", "true")

    rule = _sample_rule("r-template-direct")
    rule["require_approval"] = False
    rule["action"] = {
        "type": "template_deploy",
        "title": "Template Deploy",
        "message": "triggered",
        "payload": {"template_id": 3, "device_ids": [101, 102]},
    }

    save = client.put(
        "/api/v1/intent/closed-loop/rules",
        json={"rules": [rule]},
        headers=operator_user_token,
    )
    assert save.status_code == 200

    monkeypatch.setattr(
        closed_loop_service_mod.ClosedLoopService,
        "_execute_template_deploy_action",
        staticmethod(
            lambda *_a, **_k: {
                "mode": "template_deploy_dispatched",
                "template_id": 3,
                "device_ids": [101, 102],
                "execution": {"idempotency_key": "closed-loop:test"},
            }
        ),
    )

    res = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 95}}, "dry_run": False},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert int(body["executed"]) == 1
    decisions = list(body.get("decisions") or [])
    assert len(decisions) == 1
    assert decisions[0]["status"] == "executed"
    assert int(decisions[0].get("approval_id") or 0) == 0
    result = decisions[0].get("result") or {}
    assert result.get("mode") == "template_deploy_dispatched"
    assert int(result.get("template_id") or 0) == 3


def test_closed_loop_cloud_bootstrap_executes_when_direct_change_enabled(client, operator_user_token, db, monkeypatch):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    _set_setting(db, "closed_loop_execute_change_actions", "true")
    _set_setting(db, "change_policy_cloud_bootstrap_live_requires_approval", "false")

    rule = _sample_rule("r-cloud-bootstrap-direct")
    rule["require_approval"] = False
    rule["action"] = {
        "type": "cloud_bootstrap",
        "title": "Cloud Bootstrap",
        "message": "triggered",
        "payload": {"account_ids": [301], "dry_run": True},
    }

    save = client.put(
        "/api/v1/intent/closed-loop/rules",
        json={"rules": [rule]},
        headers=operator_user_token,
    )
    assert save.status_code == 200

    monkeypatch.setattr(
        closed_loop_service_mod.ClosedLoopService,
        "_execute_cloud_bootstrap_action",
        staticmethod(
            lambda *_a, **_k: {
                "mode": "cloud_bootstrap_dispatched",
                "status": "ok",
                "total_targets": 2,
                "success_targets": 2,
                "failed_targets": 0,
                "dry_run_targets": 2,
            }
        ),
    )

    res = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 95}}, "dry_run": False},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert int(body["executed"]) == 1
    decisions = list(body.get("decisions") or [])
    assert len(decisions) == 1
    assert decisions[0]["status"] == "executed"
    assert int(decisions[0].get("approval_id") or 0) == 0
    result = decisions[0].get("result") or {}
    assert result.get("mode") == "cloud_bootstrap_dispatched"
    assert int(result.get("total_targets") or 0) == 2


def test_closed_loop_cloud_bootstrap_live_policy_opens_approval(client, operator_user_token, db):
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    _set_setting(db, "closed_loop_execute_change_actions", "true")
    _set_setting(db, "change_policy_cloud_bootstrap_live_requires_approval", "true")

    rule = _sample_rule("r-cloud-bootstrap-policy")
    rule["require_approval"] = False
    rule["action"] = {
        "type": "cloud_bootstrap",
        "title": "Cloud Bootstrap Live",
        "message": "triggered",
        "payload": {"account_ids": [401], "dry_run": False},
    }

    save = client.put(
        "/api/v1/intent/closed-loop/rules",
        json={"rules": [rule]},
        headers=operator_user_token,
    )
    assert save.status_code == 200

    res = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 95}}, "dry_run": False},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert int(body["executed"]) == 1
    decisions = list(body.get("decisions") or [])
    assert len(decisions) == 1
    assert decisions[0]["status"] == "executed"
    result = decisions[0].get("result") or {}
    assert result.get("mode") == "approval_opened"
    assert str(result.get("policy") or "") == "cloud_bootstrap_live_requires_approval"
    assert int(result.get("approval_id") or 0) > 0

    approvals = db.query(ApprovalRequest).filter(ApprovalRequest.request_type == "closed_loop_action").all()
    assert len(approvals) >= 1


def test_closed_loop_intent_apply_executes_when_direct_change_enabled(client, operator_user_token, db, monkeypatch):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    _set_setting(db, "closed_loop_execute_change_actions", "true")

    rule = _sample_rule("r-intent-apply-direct")
    rule["require_approval"] = False
    rule["action"] = {
        "type": "intent_apply",
        "title": "Intent Apply",
        "message": "triggered",
        "payload": {
            "intent_type": "cloud_policy",
            "name": "closed-loop-cloud-guardrail",
            "dry_run": True,
            "spec": {"targets": {"providers": ["aws"]}, "required_tags": [{"key": "owner"}]},
        },
    }

    save = client.put(
        "/api/v1/intent/closed-loop/rules",
        json={"rules": [rule]},
        headers=operator_user_token,
    )
    assert save.status_code == 200

    monkeypatch.setattr(
        closed_loop_service_mod.ClosedLoopService,
        "_execute_intent_apply_action",
        staticmethod(
            lambda *_a, **_k: {
                "mode": "intent_apply_dispatched",
                "intent_type": "cloud_policy",
                "intent_status": "dry_run",
                "execution_id": "intent-exec-901",
            }
        ),
    )

    res = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 95}}, "dry_run": False},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert int(body["executed"]) == 1
    decisions = list(body.get("decisions") or [])
    assert len(decisions) == 1
    assert decisions[0]["status"] == "executed"
    result = decisions[0].get("result") or {}
    assert result.get("mode") == "intent_apply_dispatched"
    assert result.get("intent_type") == "cloud_policy"


def test_closed_loop_intent_apply_opens_approval_when_direct_change_disabled(client, operator_user_token, db):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "closed_loop_engine_enabled", "true")
    _set_setting(db, "closed_loop_auto_execute_enabled", "true")
    _set_setting(db, "closed_loop_execute_change_actions", "false")

    rule = _sample_rule("r-intent-apply-approval")
    rule["require_approval"] = False
    rule["action"] = {
        "type": "intent_apply",
        "title": "Intent Apply",
        "message": "triggered",
        "payload": {
            "intent_type": "cloud_policy",
            "name": "closed-loop-cloud-guardrail-approval",
            "dry_run": False,
            "spec": {"targets": {"providers": ["aws"]}, "required_tags": [{"key": "owner"}]},
        },
    }

    save = client.put(
        "/api/v1/intent/closed-loop/rules",
        json={"rules": [rule]},
        headers=operator_user_token,
    )
    assert save.status_code == 200

    res = client.post(
        "/api/v1/intent/closed-loop/evaluate",
        json={"signals": {"summary": {"cpu_avg": 95}}, "dry_run": False},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert int(body["executed"]) == 1
    decisions = list(body.get("decisions") or [])
    assert len(decisions) == 1
    assert decisions[0]["status"] == "executed"
    assert int(decisions[0].get("approval_id") or 0) > 0
    result = decisions[0].get("result") or {}
    assert result.get("mode") == "approval_opened"
    assert result.get("direct_execution_enabled") is False
