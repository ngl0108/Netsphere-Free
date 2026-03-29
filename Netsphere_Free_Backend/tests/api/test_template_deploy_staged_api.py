from app.api.v1.endpoints import config_template as template_ep
from app.models.approval import ApprovalRequest
from app.models.device import ConfigBackup, ConfigTemplate, Device
from app.models.settings import SystemSetting
from app.models.user import User


def _payload(res):
    body = res.json()
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_template_deploy_stops_after_failed_wave(client, operator_user_token, db, monkeypatch):
    tpl = ConfigTemplate(name="staged-template", category="ops", content="hostname {{ _dev_id }}", tags="v1")
    db.add(tpl)
    db.flush()
    db.add_all(
        [
            Device(name="d1", ip_address="10.90.0.1", device_type="cisco_ios", status="online"),
            Device(name="d2", ip_address="10.90.0.2", device_type="cisco_ios", status="online"),
            Device(name="d3", ip_address="10.90.0.3", device_type="cisco_ios", status="online"),
        ]
    )
    db.commit()
    device_ids = [
        int(d.id)
        for d in db.query(Device)
        .filter(Device.name.in_(["d1", "d2", "d3"]))
        .order_by(Device.id.asc())
        .all()
    ]

    def fake_worker(target, _template_content, _opts):
        did = int(target["dev_id"])
        if did == device_ids[1]:
            return {"id": did, "status": "failed", "error": "simulated error"}
        return {"id": did, "status": "success", "output": "ok"}

    monkeypatch.setattr(template_ep, "_deploy_worker", fake_worker)

    res = client.post(
        f"/api/v1/templates/{tpl.id}/deploy",
        json={
            "device_ids": device_ids,
            "wave_size": 1,
            "stop_on_wave_failure": True,
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    payload = _payload(res)

    summary = list(payload.get("summary") or [])
    by_id = {int(r["id"]): r for r in summary if "id" in r}

    assert by_id[device_ids[0]]["status"] == "success"
    assert by_id[device_ids[1]]["status"] == "failed"
    assert by_id[device_ids[2]]["status"] == "skipped_wave_halt"
    assert (payload.get("change_plan") or {}).get("route") == "direct"
    assert int((payload.get("totals") or {}).get("skipped") or 0) == 1

    execution = payload.get("execution") or {}
    assert execution.get("halted") is True
    assert execution.get("halted_wave") == 2


def test_template_deploy_duplicate_request_is_skipped(client, operator_user_token, db, monkeypatch):
    tpl = ConfigTemplate(name="dup-template", category="ops", content="hostname SW1", tags="v1")
    db.add(tpl)
    db.flush()
    db.add(Device(name="dup-d1", ip_address="10.91.0.1", device_type="cisco_ios", status="online"))
    db.commit()
    did = int(db.query(Device).filter(Device.name == "dup-d1").first().id)

    monkeypatch.setattr(template_ep.ChangeExecutionService, "claim_idempotency", staticmethod(lambda *_a, **_k: False))

    res = client.post(
        f"/api/v1/templates/{tpl.id}/deploy",
        json={"device_ids": [did], "wave_size": 1},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    payload = _payload(res)
    summary = list(payload.get("summary") or [])
    assert len(summary) == 1
    assert summary[0]["status"] == "skipped_idempotent"
    assert (payload.get("execution") or {}).get("waves_executed") == 0


def test_template_deploy_requires_approval_when_target_scope_is_wide(client, operator_user_token, db):
    tpl = ConfigTemplate(name="approval-template", category="ops", content="hostname SW", tags="v1")
    db.add(tpl)
    db.flush()
    db.add(
        SystemSetting(
            key="change_policy_template_direct_max_devices",
            value="3",
            description="",
            category="General",
        )
    )
    db.add_all(
        [
            Device(name="ad1", ip_address="10.191.0.1", device_type="cisco_ios", status="online"),
            Device(name="ad2", ip_address="10.191.0.2", device_type="cisco_ios", status="online"),
            Device(name="ad3", ip_address="10.191.0.3", device_type="cisco_ios", status="online"),
            Device(name="ad4", ip_address="10.191.0.4", device_type="cisco_ios", status="online"),
        ]
    )
    db.commit()

    device_ids = [
        int(d.id)
        for d in db.query(Device)
        .filter(Device.name.in_(["ad1", "ad2", "ad3", "ad4"]))
        .order_by(Device.id.asc())
        .all()
    ]

    res = client.post(
        f"/api/v1/templates/{tpl.id}/deploy",
        json={"device_ids": device_ids, "wave_size": 2},
        headers=operator_user_token,
    )
    assert res.status_code == 409
    body = res.json()
    msg = body.get("message") if isinstance(body, dict) else ""
    detail = body.get("detail") if isinstance(body, dict) else ""
    assert "Approval required for template deploy" in str(msg or detail or body)


def test_template_deploy_wide_scope_is_allowed_with_approval_id(client, operator_user_token, db, monkeypatch):
    tpl = ConfigTemplate(name="approval-template-2", category="ops", content="hostname SW2", tags="v1")
    db.add(tpl)
    db.flush()
    db.add(
        SystemSetting(
            key="change_policy_template_direct_max_devices",
            value="3",
            description="",
            category="General",
        )
    )
    db.add_all(
        [
            Device(name="ax1", ip_address="10.192.0.1", device_type="cisco_ios", status="online"),
            Device(name="ax2", ip_address="10.192.0.2", device_type="cisco_ios", status="online"),
            Device(name="ax3", ip_address="10.192.0.3", device_type="cisco_ios", status="online"),
            Device(name="ax4", ip_address="10.192.0.4", device_type="cisco_ios", status="online"),
        ]
    )
    db.commit()

    device_ids = [
        int(d.id)
        for d in db.query(Device)
        .filter(Device.name.in_(["ax1", "ax2", "ax3", "ax4"]))
        .order_by(Device.id.asc())
        .all()
    ]

    monkeypatch.setattr(
        template_ep,
        "_deploy_worker",
        lambda target, _template_content, _opts: {"id": int(target["dev_id"]), "status": "success", "output": "ok"},
    )

    requester = User(username="tpl-pol-req", email="tpl-pol-req@example.com", hashed_password="x", full_name="r", is_active=True, role="operator")
    approver = User(username="tpl-pol-appr", email="tpl-pol-appr@example.com", hashed_password="y", full_name="a", is_active=True, role="admin")
    db.add_all([requester, approver])
    db.commit()
    db.refresh(requester)
    db.refresh(approver)
    approval = ApprovalRequest(
        requester_id=int(requester.id),
        approver_id=int(approver.id),
        title="template deploy approved",
        request_type="template_deploy",
        payload={"template_id": int(tpl.id), "device_ids": list(device_ids)},
        status="approved",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    res = client.post(
        f"/api/v1/templates/{tpl.id}/deploy",
        json={"device_ids": device_ids, "approval_id": int(approval.id), "wave_size": 2},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    payload = _payload(res)
    rows = list(payload.get("summary") or [])
    assert len(rows) == 4
    assert all(int(r.get("approval_id")) == int(approval.id) for r in rows)
    db.refresh(approval)
    approval_payload = dict(approval.payload or {})
    assert approval_payload.get("approval_id") == int(approval.id)
    assert str(approval_payload.get("execution_id") or "").strip() == str(payload.get("execution_id") or "").strip()
    assert str(approval_payload.get("execution_status") or "").strip().lower() == "success"
    result_summary = approval_payload.get("execution_result_summary") or {}
    assert int((result_summary.get("summary") or {}).get("success") or 0) == 4


def test_template_deploy_rejects_non_approved_approval_id(client, operator_user_token, db):
    tpl = ConfigTemplate(name="approval-template-pending", category="ops", content="hostname SW3", tags="v1")
    db.add(tpl)
    db.flush()
    db.add(SystemSetting(key="change_policy_template_direct_max_devices", value="1", description="", category="General"))
    db.add_all(
        [
            Device(name="tx1", ip_address="10.197.0.1", device_type="cisco_ios", status="online"),
            Device(name="tx2", ip_address="10.197.0.2", device_type="cisco_ios", status="online"),
        ]
    )
    requester = User(username="tpl-pol-req2", email="tpl-pol-req2@example.com", hashed_password="x", full_name="r2", is_active=True, role="operator")
    approver = User(username="tpl-pol-appr2", email="tpl-pol-appr2@example.com", hashed_password="y", full_name="a2", is_active=True, role="admin")
    db.add_all([requester, approver])
    db.commit()
    db.refresh(requester)
    db.refresh(approver)
    device_ids = [
        int(d.id)
        for d in db.query(Device)
        .filter(Device.name.in_(["tx1", "tx2"]))
        .order_by(Device.id.asc())
        .all()
    ]
    approval = ApprovalRequest(
        requester_id=int(requester.id),
        approver_id=int(approver.id),
        title="template deploy pending",
        request_type="template_deploy",
        payload={"template_id": int(tpl.id), "device_ids": list(device_ids)},
        status="pending",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    res = client.post(
        f"/api/v1/templates/{tpl.id}/deploy",
        json={"device_ids": device_ids, "approval_id": int(approval.id), "wave_size": 1},
        headers=operator_user_token,
    )
    assert res.status_code == 409
    body = res.json()
    msg = body.get("message") if isinstance(body, dict) else ""
    detail = body.get("detail") if isinstance(body, dict) else ""
    assert "must be approved before execution" in str(msg or detail or body)


def test_template_deploy_rejects_wrong_request_type_approval_id(client, operator_user_token, db):
    tpl = ConfigTemplate(name="approval-template-wrong-type", category="ops", content="hostname SW4", tags="v1")
    db.add(tpl)
    db.flush()
    db.add(SystemSetting(key="change_policy_template_direct_max_devices", value="1", description="", category="General"))
    db.add_all(
        [
            Device(name="ty1", ip_address="10.198.0.1", device_type="cisco_ios", status="online"),
            Device(name="ty2", ip_address="10.198.0.2", device_type="cisco_ios", status="online"),
        ]
    )
    requester = User(username="tpl-pol-req3", email="tpl-pol-req3@example.com", hashed_password="x", full_name="r3", is_active=True, role="operator")
    approver = User(username="tpl-pol-appr3", email="tpl-pol-appr3@example.com", hashed_password="y", full_name="a3", is_active=True, role="admin")
    db.add_all([requester, approver])
    db.commit()
    db.refresh(requester)
    db.refresh(approver)
    device_ids = [
        int(d.id)
        for d in db.query(Device)
        .filter(Device.name.in_(["ty1", "ty2"]))
        .order_by(Device.id.asc())
        .all()
    ]
    approval = ApprovalRequest(
        requester_id=int(requester.id),
        approver_id=int(approver.id),
        title="wrong type approval",
        request_type="fabric_deploy",
        payload={"spine_ids": [device_ids[0]], "leaf_ids": [device_ids[1]]},
        status="approved",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    res = client.post(
        f"/api/v1/templates/{tpl.id}/deploy",
        json={"device_ids": device_ids, "approval_id": int(approval.id), "wave_size": 1},
        headers=operator_user_token,
    )
    assert res.status_code == 409
    body = res.json()
    msg = body.get("message") if isinstance(body, dict) else ""
    detail = body.get("detail") if isinstance(body, dict) else ""
    assert "expected=template_deploy" in str(msg or detail or body)


def test_template_deploy_rejects_execution_id_mismatch_for_bound_approval(client, operator_user_token, db):
    tpl = ConfigTemplate(name="approval-template-bound-exec", category="ops", content="hostname SW5", tags="v1")
    db.add(tpl)
    db.flush()
    db.add(Device(name="tz1", ip_address="10.199.0.1", device_type="cisco_ios", status="online"))
    requester = User(username="tpl-pol-req4", email="tpl-pol-req4@example.com", hashed_password="x", full_name="r4", is_active=True, role="operator")
    approver = User(username="tpl-pol-appr4", email="tpl-pol-appr4@example.com", hashed_password="y", full_name="a4", is_active=True, role="admin")
    db.add_all([requester, approver])
    db.commit()
    db.refresh(requester)
    db.refresh(approver)
    device_id = int(db.query(Device).filter(Device.name == "tz1").first().id)
    approval = ApprovalRequest(
        requester_id=int(requester.id),
        approver_id=int(approver.id),
        title="bound execution id",
        request_type="template_deploy",
        payload={"template_id": int(tpl.id), "device_ids": [device_id], "execution_id": "bound-exec-1"},
        status="approved",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    res = client.post(
        f"/api/v1/templates/{tpl.id}/deploy",
        json={"device_ids": [device_id], "approval_id": int(approval.id), "execution_id": "different-exec"},
        headers=operator_user_token,
    )
    assert res.status_code == 409
    body = res.json()
    msg = body.get("message") if isinstance(body, dict) else ""
    detail = body.get("detail") if isinstance(body, dict) else ""
    assert "already bound to execution_id=bound-exec-1" in str(msg or detail or body)


def test_template_dry_run_returns_diff_summary(client, operator_user_token, db):
    tpl = ConfigTemplate(
        name="dry-run-template",
        category="ops",
        content="hostname NEW-SW\ninterface Loopback0\n description test",
        tags="v1",
    )
    dev = Device(name="dry-run-dev", ip_address="10.195.0.1", device_type="cisco_ios", status="online")
    db.add_all([tpl, dev])
    db.flush()
    db.add(ConfigBackup(device_id=int(dev.id), raw_config="hostname OLD-SW\n!\n", is_golden=False))
    db.commit()

    res = client.post(
        f"/api/v1/templates/{tpl.id}/dry-run",
        json={"device_ids": [int(dev.id)], "include_rendered": False},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    payload = _payload(res)
    rows = list(payload.get("summary") or [])
    assert len(rows) == 1
    row = rows[0]
    assert row.get("status") == "ok"
    assert isinstance(row.get("diff_lines"), list)
    diff_summary = row.get("diff_summary") or {}
    assert diff_summary.get("has_changes") is True
    assert int(diff_summary.get("added_lines") or 0) >= 1
    assert int(diff_summary.get("removed_lines") or 0) >= 1
    assert isinstance(diff_summary.get("preview"), list)
    assert isinstance(row.get("pre_check_commands"), list)
    assert isinstance(row.get("post_check_commands"), list)
    assert isinstance(row.get("support_policy"), dict)
    assert (payload.get("change_plan") or {}).get("route") == "direct"


def test_template_dry_run_respects_runtime_guard_options(client, operator_user_token, db, monkeypatch):
    tpl = ConfigTemplate(name="dry-run-guard-template", category="ops", content="hostname NEW-GUARD", tags="v1")
    dev = Device(name="dry-run-guard-dev", ip_address="10.195.0.2", device_type="generic_linux", status="online")
    db.add_all([tpl, dev])
    db.commit()
    db.refresh(dev)

    fake_policy = {
        "tier": "fixture",
        "readiness": "basic",
        "fallback_mode": "cli",
        "capability_read_only": False,
        "reasons": [],
        "features": {"config": True, "rollback": False},
        "rollback_strategy": {"supported": False, "mode": None, "label": "unsupported"},
    }

    monkeypatch.setattr(
        template_ep.DeviceSupportPolicyService,
        "evaluate_device",
        staticmethod(lambda *_a, **_k: dict(fake_policy)),
    )
    monkeypatch.setattr(
        template_ep.DeviceSupportPolicyService,
        "collect_blocked_devices",
        staticmethod(
            lambda _db, devices=None, feature="config": (
                [{"id": int(d.id), "name": d.name, "device_type": d.device_type} for d in list(devices or [])]
                if feature == "rollback"
                else []
            )
        ),
    )

    res = client.post(
        f"/api/v1/templates/{tpl.id}/dry-run",
        json={
            "device_ids": [int(dev.id)],
            "rollback_on_failure": False,
            "post_check_enabled": False,
            "canary_count": 1,
            "wave_size": 2,
            "stop_on_wave_failure": False,
            "inter_wave_delay_seconds": 3.5,
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    payload = _payload(res)
    row = list(payload.get("summary") or [])[0]
    change_plan = payload.get("change_plan") or {}
    guard = row.get("change_guard") or {}

    assert change_plan.get("route") == "direct"
    assert change_plan.get("rollback_on_failure") is False
    assert (change_plan.get("rollout") or {}).get("canary_count") == 1
    assert (change_plan.get("rollout") or {}).get("wave_size") == 2
    assert (change_plan.get("rollout") or {}).get("stop_on_wave_failure") is False
    assert (change_plan.get("rollout") or {}).get("inter_wave_delay_seconds") == 3.5
    assert row.get("post_check_commands") == []
    assert guard.get("rollback_supported") is False
    assert "rollback_not_supported" not in list(guard.get("blocked_reasons") or [])


def test_template_deploy_returns_validation_and_rollback_metadata(client, operator_user_token, db, monkeypatch):
    tpl = ConfigTemplate(name="metadata-template", category="ops", content="hostname SWX", tags="v1")
    db.add(tpl)
    db.flush()
    d1 = Device(name="md1", ip_address="10.210.0.1", device_type="cisco_ios", status="online")
    d2 = Device(name="md2", ip_address="10.210.0.2", device_type="cisco_ios", status="online")
    db.add_all([d1, d2])
    db.commit()
    db.refresh(d1)
    db.refresh(d2)

    def fake_worker(target, _template_content, _opts):
        did = int(target["dev_id"])
        if did == int(d2.id):
            return {
                "id": did,
                "status": "postcheck_failed",
                "error": "Post-check failed",
                "pre_check": {"ok": True, "rows": [{"command": "show version", "ok": True}]},
                "post_check": {"ok": False, "command": None, "tried": [{"command": "show clock", "ok": False}]},
                "rollback_attempted": True,
                "rollback_success": True,
                "rollback_duration_ms": 1250,
                "rollback_prepared": True,
                "rollback_ref": "rb-md2",
                "backup_id": 901,
            }
        return {
            "id": did,
            "status": "success",
            "output": "ok",
            "pre_check": {"ok": True, "rows": [{"command": "show version", "ok": True}]},
            "post_check": {"ok": True, "command": "show clock", "output": "ok", "tried": []},
            "rollback_prepared": True,
            "rollback_ref": "rb-md1",
            "backup_id": 900,
        }

    monkeypatch.setattr(template_ep, "_deploy_worker", fake_worker)

    res = client.post(
        f"/api/v1/templates/{tpl.id}/deploy",
        json={"device_ids": [int(d1.id), int(d2.id)], "wave_size": 1},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    payload = _payload(res)
    rows = list(payload.get("summary") or [])
    by_id = {int(row["device_id"]): row for row in rows}

    assert by_id[int(d1.id)]["device_name"] == "md1"
    assert by_id[int(d1.id)]["pre_check"]["ok"] is True
    assert by_id[int(d1.id)]["post_check"]["ok"] is True
    assert by_id[int(d1.id)]["rollback"]["prepared"] is True
    assert by_id[int(d2.id)]["status"] == "postcheck_failed"
    assert by_id[int(d2.id)]["rollback"]["attempted"] is True
    assert by_id[int(d2.id)]["rollback"]["success"] is True
    assert by_id[int(d2.id)]["failure_cause"] == "post_check_failed"
    assert isinstance(by_id[int(d2.id)]["support_policy"], dict)
    totals = payload.get("totals") or {}
    assert int(totals.get("postcheck_failed") or 0) == 1
    assert int(totals.get("rollback_attempted") or 0) == 1
