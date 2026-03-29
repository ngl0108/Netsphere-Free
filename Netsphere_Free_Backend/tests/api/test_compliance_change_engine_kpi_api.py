import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import compliance as compliance_ep
from app.models.approval import ApprovalRequest
from app.models.device import Device, EventLog, Issue
from app.models.settings import SystemSetting
from app.models.user import User


def _create_approval(db, *, request_type: str, status: str = "approved", payload=None) -> int:
    requester = User(
        username=f"cmp-req-{request_type}-{status}",
        email=f"cmp-req-{request_type}-{status}@example.com",
        hashed_password="x",
        full_name="r",
        is_active=True,
        role="operator",
    )
    approver = User(
        username=f"cmp-appr-{request_type}-{status}",
        email=f"cmp-appr-{request_type}-{status}@example.com",
        hashed_password="y",
        full_name="a",
        is_active=True,
        role="admin",
    )
    db.add_all([requester, approver])
    db.commit()
    db.refresh(requester)
    db.refresh(approver)
    req = ApprovalRequest(
        requester_id=int(requester.id),
        approver_id=int(approver.id),
        title=f"{request_type} {status}",
        request_type=str(request_type),
        payload=dict(payload or {}),
        status=str(status),
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return int(req.id)


def test_compliance_batch_remediation_halts_on_wave_failure(db, monkeypatch):
    db.add_all(
        [
            Device(name="cmp-d1", ip_address="10.210.0.1", device_type="cisco_ios", status="online"),
            Device(name="cmp-d2", ip_address="10.210.0.2", device_type="cisco_ios", status="online"),
            Device(name="cmp-d3", ip_address="10.210.0.3", device_type="cisco_ios", status="online"),
        ]
    )
    db.commit()
    device_ids = [
        int(d.id)
        for d in db.query(Device)
        .filter(Device.name.in_(["cmp-d1", "cmp-d2", "cmp-d3"]))
        .order_by(Device.id.asc())
        .all()
    ]

    monkeypatch.setattr(
        compliance_ep.ComplianceEngine,
        "check_config_drift",
        lambda _self, did: {"status": "drift", "device_id": int(did), "golden_id": 1, "latest_id": 2},
    )

    def fake_remediate(_self, device_id: int, **_kwargs):
        if int(device_id) == int(device_ids[1]):
            return {
                "status": "failed",
                "device_id": int(device_id),
                "error": "Post-check failed",
                "rollback_attempted": True,
                "rollback_success": True,
                "rollback_duration_ms": 1800,
            }
        return {"status": "ok", "device_id": int(device_id)}

    monkeypatch.setattr(compliance_ep.ComplianceEngine, "remediate_config_drift", fake_remediate)

    body = compliance_ep.remediate_config_drift_batch(
        req=compliance_ep.DriftRemediateBatchRequest(
            device_ids=device_ids,
            wave_size=1,
            stop_on_wave_failure=True,
        ),
        db=db,
        current_user=SimpleNamespace(id=1, role="operator"),
    )

    rows = list(body.get("summary") or [])
    by_id = {int(r["device_id"]): r for r in rows if "device_id" in r}

    assert by_id[device_ids[0]]["status"] == "success"
    assert by_id[device_ids[1]]["status"] == "failed"
    assert by_id[device_ids[2]]["status"] == "skipped_wave_halt"

    execution = body.get("execution") or {}
    assert execution.get("halted") is True
    assert execution.get("halted_wave") == 2
    assert str(body.get("execution_id") or "").strip() != ""
    assert str(body.get("idempotency_key") or "").strip() != ""
    assert str(execution.get("execution_id") or "").strip() == str(body.get("execution_id") or "").strip()
    assert execution.get("approval_id") is None
    assert str(execution.get("idempotency_key") or "").strip() == str(body.get("idempotency_key") or "").strip()

    assert str(by_id[device_ids[0]].get("execution_id") or "").strip() == str(body.get("execution_id") or "").strip()
    assert str(by_id[device_ids[1]].get("execution_id") or "").strip() == str(body.get("execution_id") or "").strip()
    assert str(by_id[device_ids[2]].get("execution_id") or "").strip() == str(body.get("execution_id") or "").strip()


def test_compliance_batch_remediation_preserves_detailed_failure_statuses(db, monkeypatch):
    db.add_all(
        [
            Device(name="cmp-detail-d1", ip_address="10.210.1.1", device_type="cisco_ios", status="online"),
            Device(name="cmp-detail-d2", ip_address="10.210.1.2", device_type="cisco_ios", status="online"),
            Device(name="cmp-detail-d3", ip_address="10.210.1.3", device_type="cisco_ios", status="online"),
        ]
    )
    db.commit()
    device_ids = [
        int(d.id)
        for d in db.query(Device)
        .filter(Device.name.in_(["cmp-detail-d1", "cmp-detail-d2", "cmp-detail-d3"]))
        .order_by(Device.id.asc())
        .all()
    ]

    monkeypatch.setattr(
        compliance_ep.ComplianceEngine,
        "check_config_drift",
        lambda _self, did: {"status": "drift", "device_id": int(did), "golden_id": 1, "latest_id": 2},
    )

    def fake_remediate(_self, device_id: int, **_kwargs):
        did = int(device_id)
        if did == int(device_ids[0]):
            return {
                "status": "precheck_failed",
                "device_id": did,
                "error": "Pre-check failed before remediation",
                "pre_check": {"ok": False, "rows": [{"command": "show version", "ok": False}]},
                "failure_cause": "precheck_failed",
                "rollback_attempted": False,
                "rollback_success": False,
            }
        if did == int(device_ids[1]):
            return {
                "status": "postcheck_failed",
                "device_id": did,
                "error": "Post-check failed",
                "post_check": {"ok": False, "tried": [{"command": "show clock", "ok": False}]},
                "post_check_failed": True,
                "failure_cause": "post_check_failed",
                "rollback_attempted": True,
                "rollback_success": True,
                "rollback_duration_ms": 700,
            }
        return {"status": "ok", "device_id": did}

    monkeypatch.setattr(compliance_ep.ComplianceEngine, "remediate_config_drift", fake_remediate)

    body = compliance_ep.remediate_config_drift_batch(
        req=compliance_ep.DriftRemediateBatchRequest(
            device_ids=device_ids,
            wave_size=1,
            stop_on_wave_failure=False,
        ),
        db=db,
        current_user=SimpleNamespace(id=1, role="operator"),
    )

    rows = list(body.get("summary") or [])
    by_id = {int(r["device_id"]): r for r in rows if "device_id" in r}

    assert by_id[device_ids[0]]["status"] == "precheck_failed"
    assert by_id[device_ids[0]].get("failure_cause") == "precheck_failed"
    assert bool((by_id[device_ids[0]].get("pre_check") or {}).get("ok")) is False

    assert by_id[device_ids[1]]["status"] == "postcheck_failed"
    assert by_id[device_ids[1]].get("failure_cause") == "post_check_failed"
    assert bool(by_id[device_ids[1]].get("post_check_failed")) is True
    assert bool(by_id[device_ids[1]].get("rollback_attempted")) is True
    assert bool(by_id[device_ids[1]].get("rollback_success")) is True

    assert by_id[device_ids[2]]["status"] == "success"
    assert body.get("counts", {}).get("success") == 1
    assert body.get("counts", {}).get("failed") == 2


def test_compliance_batch_remediation_requires_approval_when_scope_exceeds_policy(db):
    db.add(SystemSetting(key="change_policy_compliance_direct_max_devices", value="1", description="", category="General"))
    db.add_all(
        [
            Device(name="cmp-pol-d1", ip_address="10.212.0.1", device_type="cisco_ios", status="online"),
            Device(name="cmp-pol-d2", ip_address="10.212.0.2", device_type="cisco_ios", status="online"),
        ]
    )
    db.commit()
    device_ids = [
        int(d.id)
        for d in db.query(Device)
        .filter(Device.name.in_(["cmp-pol-d1", "cmp-pol-d2"]))
        .order_by(Device.id.asc())
        .all()
    ]

    with pytest.raises(HTTPException) as exc:
        compliance_ep.remediate_config_drift_batch(
            req=compliance_ep.DriftRemediateBatchRequest(device_ids=device_ids),
            db=db,
            current_user=SimpleNamespace(id=1, role="operator"),
        )

    assert exc.value.status_code == 409
    assert "Approval required for config drift remediation targeting 2 devices" in str(exc.value.detail)


def test_compliance_batch_remediation_scope_policy_is_bypassed_with_approval_id(db, monkeypatch):
    db.add(SystemSetting(key="change_policy_compliance_direct_max_devices", value="1", description="", category="General"))
    db.add_all(
        [
            Device(name="cmp-pol-ok-d1", ip_address="10.213.0.1", device_type="cisco_ios", status="online"),
            Device(name="cmp-pol-ok-d2", ip_address="10.213.0.2", device_type="cisco_ios", status="online"),
        ]
    )
    db.commit()
    device_ids = [
        int(d.id)
        for d in db.query(Device)
        .filter(Device.name.in_(["cmp-pol-ok-d1", "cmp-pol-ok-d2"]))
        .order_by(Device.id.asc())
        .all()
    ]

    captured = {}

    def fake_batch(_self, ids, **kwargs):
        captured["ids"] = list(ids or [])
        captured["kwargs"] = dict(kwargs or {})
        exec_id = str(kwargs.get("execution_id") or "cmp-pol-exec")
        return {
            "summary": [],
            "execution": {
                "waves_total": 0,
                "waves_executed": 0,
                "halted": False,
                "halted_wave": None,
                "approval_id": kwargs.get("approval_id"),
                "execution_id": exec_id,
            },
            "counts": {"total": 0, "success": 0, "failed": 0, "skipped": 0, "gate_failed": 0},
            "approval_id": kwargs.get("approval_id"),
            "execution_id": exec_id,
            "idempotency_key": "cmp-pol-idem",
        }

    monkeypatch.setattr(compliance_ep.ComplianceEngine, "remediate_config_drift_batch", fake_batch)
    approval_id = _create_approval(
        db,
        request_type="config_drift_remediate",
        status="approved",
        payload={"device_ids": list(device_ids)},
    )

    out = compliance_ep.remediate_config_drift_batch(
        req=compliance_ep.DriftRemediateBatchRequest(
            device_ids=device_ids,
            approval_id=approval_id,
            pre_check_commands=["show version", "show clock"],
        ),
        db=db,
        current_user=SimpleNamespace(id=1, role="operator"),
    )

    assert captured.get("ids") == list(device_ids)
    assert list((captured.get("kwargs") or {}).get("pre_check_commands") or []) == ["show version", "show clock"]
    assert int(out.get("approval_id")) == int(approval_id)
    execution = out.get("execution") or {}
    assert int(execution.get("approval_id")) == int(approval_id)
    approval = db.query(ApprovalRequest).filter(ApprovalRequest.id == int(approval_id)).first()
    payload = dict((approval.payload if approval else {}) or {})
    assert payload.get("approval_id") == int(approval_id)
    assert str(payload.get("execution_id") or "").strip() == str(out.get("execution_id") or "").strip()
    assert str(payload.get("execution_status") or "").strip().lower() in {"executed", "success"}


def test_compliance_single_remediation_passes_pre_check_commands_to_batch(db, monkeypatch):
    dev = Device(name="cmp-single-precheck", ip_address="10.214.2.1", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    captured = {}

    def fake_batch(_self, ids, **kwargs):
        captured["ids"] = list(ids or [])
        captured["kwargs"] = dict(kwargs or {})
        return {
            "summary": [
                {
                    "id": int(dev.id),
                    "device_id": int(dev.id),
                    "status": "precheck_failed",
                    "error": "Pre-check failed before remediation",
                    "wave": 1,
                    "result": {
                        "status": "precheck_failed",
                        "device_id": int(dev.id),
                        "failure_cause": "precheck_failed",
                    },
                }
            ],
            "execution": {
                "waves_total": 1,
                "waves_executed": 1,
                "halted": False,
                "halted_wave": None,
                "approval_id": kwargs.get("approval_id"),
                "execution_id": str(kwargs.get("execution_id") or "cmp-single-precheck-exec"),
                "idempotency_key": "cmp-single-precheck-idem",
            },
            "counts": {"total": 1, "success": 0, "failed": 1, "skipped": 0, "gate_failed": 0},
            "approval_id": kwargs.get("approval_id"),
            "execution_id": str(kwargs.get("execution_id") or "cmp-single-precheck-exec"),
            "idempotency_key": "cmp-single-precheck-idem",
        }

    monkeypatch.setattr(compliance_ep.ComplianceEngine, "remediate_config_drift_batch", fake_batch)

    out = compliance_ep.remediate_config_drift(
        device_id=int(dev.id),
        req=compliance_ep.DriftRemediateRequest(
            pre_check_commands=["show version", "show ip interface brief"],
            post_check_enabled=True,
            post_check_commands=[],
        ),
        db=db,
        current_user=SimpleNamespace(id=1, role="operator"),
    )

    assert captured.get("ids") == [int(dev.id)]
    assert list((captured.get("kwargs") or {}).get("pre_check_commands") or []) == [
        "show version",
        "show ip interface brief",
    ]
    assert str(out.get("status") or "") == "precheck_failed"


def test_compliance_single_remediation_requires_approval_when_drift_approval_enabled(db):
    db.add(SystemSetting(key="config_drift_approval_enabled", value="true", description="", category="General"))
    dev = Device(name="cmp-single-pol", ip_address="10.214.0.1", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    with pytest.raises(HTTPException) as exc:
        compliance_ep.remediate_config_drift(
            device_id=int(dev.id),
            req=compliance_ep.DriftRemediateRequest(),
            db=db,
            current_user=SimpleNamespace(id=1, role="operator"),
        )

    assert exc.value.status_code == 409
    assert "Approval required for config drift remediation" in str(exc.value.detail)


def test_compliance_batch_remediation_idempotent_duplicate_keeps_trace(db, monkeypatch):
    dev = Device(name="cmp-idem-1", ip_address="10.211.0.1", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)
    dev_id = int(dev.id)

    monkeypatch.setattr(
        compliance_ep.ComplianceEngine,
        "check_config_drift",
        lambda _self, did: {"status": "drift", "device_id": int(did), "golden_id": 10, "latest_id": 11},
    )
    monkeypatch.setattr(
        compliance_ep.ComplianceEngine,
        "remediate_config_drift",
        lambda _self, device_id, **_kwargs: {"status": "ok", "device_id": int(device_id)},
    )

    approval_id = _create_approval(
        db,
        request_type="config_drift_remediate",
        status="approved",
        payload={"device_ids": [int(dev_id)]},
    )

    req = compliance_ep.DriftRemediateBatchRequest(
        device_ids=[dev_id],
        wave_size=1,
        stop_on_wave_failure=True,
        idempotency_key="cmp-idem-dup-key",
        approval_id=approval_id,
    )

    first = compliance_ep.remediate_config_drift_batch(
        req=req,
        db=db,
        current_user=SimpleNamespace(id=1, role="operator"),
    )
    second = compliance_ep.remediate_config_drift_batch(
        req=req,
        db=db,
        current_user=SimpleNamespace(id=1, role="operator"),
    )

    assert str(first.get("execution_id") or "").strip() != ""
    assert str(second.get("execution_id") or "").strip() == str(first.get("execution_id") or "").strip()
    assert str(second.get("idempotency_key") or "").strip() == "cmp-idem-dup-key"
    assert int(second.get("approval_id")) == int(approval_id)

    rows = list(second.get("summary") or [])
    assert len(rows) == 1
    assert rows[0].get("status") == "skipped_idempotent"
    assert int(rows[0].get("approval_id")) == int(approval_id)
    assert str(rows[0].get("execution_id") or "").strip() == str(second.get("execution_id") or "").strip()

    execution = second.get("execution") or {}
    assert execution.get("halted") is False
    assert execution.get("halted_wave") is None
    assert int(execution.get("approval_id")) == int(approval_id)
    assert str(execution.get("execution_id") or "").strip() == str(second.get("execution_id") or "").strip()
    assert str(execution.get("idempotency_key") or "").strip() == "cmp-idem-dup-key"


def test_compliance_batch_remediation_rejects_non_approved_approval_id(db):
    dev = Device(name="cmp-pol-pending-1", ip_address="10.215.0.1", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)
    approval_id = _create_approval(
        db,
        request_type="config_drift_remediate",
        status="pending",
        payload={"device_ids": [int(dev.id)]},
    )

    with pytest.raises(HTTPException) as exc:
        compliance_ep.remediate_config_drift_batch(
            req=compliance_ep.DriftRemediateBatchRequest(device_ids=[int(dev.id)], approval_id=approval_id),
            db=db,
            current_user=SimpleNamespace(id=1, role="operator"),
        )
    assert exc.value.status_code == 409
    assert "must be approved before execution" in str(exc.value.detail)


def test_compliance_batch_remediation_rejects_wrong_request_type_approval_id(db):
    dev = Device(name="cmp-pol-wrong-1", ip_address="10.216.0.1", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)
    approval_id = _create_approval(
        db,
        request_type="template_deploy",
        status="approved",
        payload={"device_ids": [int(dev.id)]},
    )

    with pytest.raises(HTTPException) as exc:
        compliance_ep.remediate_config_drift_batch(
            req=compliance_ep.DriftRemediateBatchRequest(device_ids=[int(dev.id)], approval_id=approval_id),
            db=db,
            current_user=SimpleNamespace(id=1, role="operator"),
        )
    assert exc.value.status_code == 409
    assert "expected=config_drift_remediate" in str(exc.value.detail)


def test_compliance_drift_kpi_summary_returns_rollback_p95_and_failure_causes(db):
    dev = Device(name="kpi-dev", ip_address="10.220.0.10", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    entries = [
        {
            "status": "failed",
            "device_id": int(dev.id),
            "approval_id": 11,
            "execution_id": "exec-11",
            "post_check_failed": True,
            "rollback_attempted": True,
            "rollback_success": True,
            "rollback_duration_ms": 1200,
            "failure_cause": "post_check_failed",
        },
        {
            "status": "failed",
            "device_id": int(dev.id),
            "approval_id": 12,
            "execution_id": "exec-12",
            "post_check_failed": True,
            "rollback_attempted": True,
            "rollback_success": False,
            "rollback_duration_ms": 2400,
            "failure_cause": "post_check_failed_rollback_failed",
        },
        {
            "status": "ok",
            "device_id": int(dev.id),
            "approval_id": 13,
            "execution_id": "exec-13",
            "post_check_failed": False,
            "rollback_attempted": False,
            "rollback_success": False,
            "rollback_duration_ms": None,
            "failure_cause": None,
        },
    ]
    for e in entries:
        db.add(
            EventLog(
                device_id=int(dev.id),
                severity="info",
                event_id="CONFIG_DRIFT_REMEDIATION_KPI",
                message=json.dumps(e),
                source="Compliance",
                timestamp=datetime.now(),
            )
        )
    db.commit()

    body = compliance_ep.get_drift_kpi_summary(
        days=30,
        site_id=None,
        limit=5000,
        db=db,
        current_user=SimpleNamespace(id=1, role="viewer"),
    )

    assert body["totals"]["events"] == 3
    assert body["totals"]["failed"] == 2
    assert body["totals"]["post_check_failures"] == 2
    assert body["totals"]["rollback_attempted"] == 2
    assert body["totals"]["rollback_success"] == 1
    assert body["kpi"]["rollback_p95_ms"] == 2400
    assert body["kpi"]["approval_execution_trace_coverage_pct"] == 100.0

    causes = {x["cause"]: int(x["count"]) for x in list(body.get("failure_causes") or [])}
    assert causes.get("post_check_failed") == 1
    assert causes.get("post_check_failed_rollback_failed") == 1


def test_compliance_drift_kpi_trace_coverage_is_based_on_approval_events_only(db):
    dev = Device(name="kpi-trace-dev", ip_address="10.220.0.11", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    with_approval = {
        "status": "ok",
        "device_id": int(dev.id),
        "approval_id": 91,
        "execution_id": "exec-91",
        "post_check_failed": False,
        "rollback_attempted": False,
        "rollback_success": False,
        "rollback_duration_ms": None,
        "failure_cause": None,
    }
    manual_no_approval = {
        "status": "ok",
        "device_id": int(dev.id),
        "approval_id": None,
        "execution_id": None,
        "post_check_failed": False,
        "rollback_attempted": False,
        "rollback_success": False,
        "rollback_duration_ms": None,
        "failure_cause": None,
    }

    for payload in [with_approval, manual_no_approval]:
        db.add(
            EventLog(
                device_id=int(dev.id),
                severity="info",
                event_id="CONFIG_DRIFT_REMEDIATION_KPI",
                message=json.dumps(payload),
                source="Compliance",
                timestamp=datetime.now(),
            )
        )
    db.commit()

    body = compliance_ep.get_drift_kpi_summary(
        days=30,
        site_id=None,
        limit=5000,
        db=db,
        current_user=SimpleNamespace(id=1, role="viewer"),
    )

    assert body["totals"]["events"] == 2
    assert body["totals"]["approval_context_events"] == 1
    assert body["totals"]["approval_traced"] == 1
    assert body["kpi"]["approval_execution_trace_coverage_pct"] == 100.0


def test_dashboard_stats_includes_change_kpi(client, normal_user_token, db):
    dev = Device(name="dash-dev", ip_address="10.230.0.10", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    for dur in [900, 1700]:
        db.add(
            EventLog(
                device_id=int(dev.id),
                severity="warning",
                event_id="CONFIG_DRIFT_REMEDIATION_KPI",
                message=json.dumps(
                    {
                        "status": "failed",
                        "device_id": int(dev.id),
                        "approval_id": 21,
                        "execution_id": f"exec-{dur}",
                        "post_check_failed": True,
                        "rollback_attempted": True,
                        "rollback_success": True,
                        "rollback_duration_ms": int(dur),
                        "failure_cause": "post_check_failed",
                    }
                ),
                source="Compliance",
                timestamp=datetime.now(),
            )
        )
    db.add(
        EventLog(
            device_id=int(dev.id),
            severity="info",
            event_id="CONFIG_DRIFT_REMEDIATION_KPI",
            message=json.dumps(
                {
                    "status": "ok",
                    "device_id": int(dev.id),
                    "approval_id": None,
                    "execution_id": None,
                    "post_check_failed": False,
                    "rollback_attempted": False,
                    "rollback_success": False,
                    "rollback_duration_ms": None,
                    "failure_cause": None,
                }
            ),
            source="Compliance",
            timestamp=datetime.now(),
        )
    )
    db.commit()

    res = client.get("/api/v1/sdn/dashboard/stats", headers=normal_user_token)
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert "change_kpi" in payload
    assert payload["change_kpi"]["totals"]["events"] >= 3
    assert payload["change_kpi"]["totals"]["approval_context_events"] == 2
    assert payload["change_kpi"]["totals"]["approval_traced"] == 2
    assert payload["change_kpi"]["rollback_p95_ms"] == 1700
    assert payload["change_kpi"]["approval_execution_trace_coverage_pct"] == 100.0
    assert payload["change_kpi"]["change_success_rate_pct"] == 33.33
    assert payload["change_kpi"]["change_failure_rate_pct"] == 66.67
    assert payload["change_kpi"]["status"] in {"warning", "critical"}
    targets = payload["change_kpi"].get("targets") or {}
    assert float(targets.get("min_success_rate_pct") or 0) == 98.0
    assert float(targets.get("max_failure_rate_pct") or 0) == 1.0
    assert int(targets.get("max_rollback_p95_ms") or 0) == 180000
    assert float(targets.get("min_trace_coverage_pct") or 0) == 100.0
    alert_codes = {str(a.get("code") or "") for a in list(payload["change_kpi"].get("alerts") or [])}
    assert "change_success_rate_low" in alert_codes
    assert "change_failure_rate_high" in alert_codes


def test_dashboard_stats_change_kpi_includes_common_change_execution_events(client, normal_user_token, db):
    dev = Device(name="dash-change-common-dev", ip_address="10.230.0.12", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    db.add(
        EventLog(
            device_id=int(dev.id),
            severity="info",
            event_id="CHANGE_EXECUTION_KPI",
            message=json.dumps(
                {
                    "status": "ok",
                    "raw_status": "success",
                    "change_type": "template_deploy",
                    "device_id": int(dev.id),
                    "approval_id": 501,
                    "execution_id": "tmpl-exec-1",
                    "wave": 1,
                    "post_check_failed": False,
                    "rollback_attempted": False,
                    "rollback_success": False,
                    "rollback_duration_ms": None,
                    "failure_cause": None,
                }
            ),
            source="Template",
            timestamp=datetime.now(),
        )
    )
    db.add(
        EventLog(
            device_id=int(dev.id),
            severity="warning",
            event_id="CHANGE_EXECUTION_KPI",
            message=json.dumps(
                {
                    "status": "failed",
                    "raw_status": "failed",
                    "change_type": "fabric_deploy",
                    "device_id": int(dev.id),
                    "approval_id": 502,
                    "execution_id": "fabric-exec-1",
                    "wave": 2,
                    "post_check_failed": True,
                    "rollback_attempted": True,
                    "rollback_success": True,
                    "rollback_duration_ms": 1450,
                    "failure_cause": "post_check_failed",
                }
            ),
            source="Fabric",
            timestamp=datetime.now(),
        )
    )
    db.commit()

    res = client.get("/api/v1/sdn/dashboard/stats", headers=normal_user_token)
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body

    change_kpi = payload.get("change_kpi") or {}
    totals = change_kpi.get("totals") or {}
    failure_causes = list(change_kpi.get("failure_causes") or [])

    assert int(totals.get("events") or 0) >= 2
    assert int(totals.get("approval_context_events") or 0) >= 2
    assert int(totals.get("approval_traced") or 0) >= 2
    assert int(change_kpi.get("rollback_p95_ms") or 0) == 1450
    assert any(str(row.get("cause") or "") == "post_check_failed" for row in failure_causes)


def test_dashboard_change_traces_returns_approval_execution_samples(client, normal_user_token, db):
    dev = Device(name="dash-trace-dev", ip_address="10.230.0.15", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    db.add(
        EventLog(
            device_id=int(dev.id),
            severity="info",
            event_id="CHANGE_EXECUTION_KPI",
            message=json.dumps(
                {
                    "status": "ok",
                    "change_type": "template_deploy",
                    "device_id": int(dev.id),
                    "approval_id": 7001,
                    "execution_id": "exec-7001",
                    "wave": 1,
                    "post_check_failed": False,
                    "rollback_attempted": False,
                    "rollback_success": False,
                    "failure_cause": None,
                }
            ),
            source="Template",
            timestamp=datetime.now(),
        )
    )
    db.add(
        EventLog(
            device_id=int(dev.id),
            severity="warning",
            event_id="CONFIG_DRIFT_REMEDIATION_KPI",
            message=json.dumps(
                {
                    "status": "failed",
                    "device_id": int(dev.id),
                    "approval_id": 7002,
                    "execution_id": "",
                    "post_check_failed": True,
                    "rollback_attempted": True,
                    "rollback_success": True,
                    "rollback_duration_ms": 1300,
                    "failure_cause": "post_check_failed",
                }
            ),
            source="Compliance",
            timestamp=datetime.now(),
        )
    )
    db.add(
        EventLog(
            device_id=int(dev.id),
            severity="info",
            event_id="CHANGE_EXECUTION_KPI",
            message=json.dumps(
                {
                    "status": "ok",
                    "change_type": "fabric_deploy",
                    "device_id": int(dev.id),
                    "approval_id": None,
                    "execution_id": None,
                }
            ),
            source="Fabric",
            timestamp=datetime.now(),
        )
    )
    db.commit()

    res = client.get("/api/v1/sdn/dashboard/change-traces?days=30&limit=20", headers=normal_user_token)
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body

    assert int(payload.get("total") or 0) == 2
    summary = payload.get("summary") or {}
    assert int(summary.get("approval_context_events") or 0) == 2
    assert int(summary.get("approval_traced") or 0) == 1
    assert float(summary.get("trace_coverage_pct") or 0) == 50.0

    items = list(payload.get("items") or [])
    assert len(items) == 2
    first = items[0]
    second = items[1]
    assert str(first.get("timestamp") or "").strip() != ""
    assert first.get("approval_id") in {7001, 7002}
    assert second.get("approval_id") in {7001, 7002}
    assert any(str(row.get("change_type") or "") == "compliance_drift" for row in items)

    ok_only = client.get("/api/v1/sdn/dashboard/change-traces?days=30&status=ok&limit=20", headers=normal_user_token)
    assert ok_only.status_code == 200
    ok_payload = ok_only.json()
    ok_data = ok_payload.get("data") if isinstance(ok_payload, dict) and "data" in ok_payload else ok_payload
    ok_items = list(ok_data.get("items") or [])
    assert len(ok_items) == 1
    assert str(ok_items[0].get("status") or "") == "ok"


def test_dashboard_stats_includes_closed_loop_kpi(client, normal_user_token, db):
    dev = Device(name="dash-loop-dev", ip_address="10.230.0.11", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    events = [
        {
            "status": "ok",
            "dry_run": False,
            "triggered": 5,
            "executed": 2,
            "blocked": 3,
            "approvals_opened": 2,
            "rules_total": 4,
            "auto_execute_enabled": True,
            "summary": {"devices_total": 10},
        },
        {
            "status": "ok",
            "dry_run": False,
            "triggered": 3,
            "executed": 1,
            "blocked": 2,
            "approvals_opened": 1,
            "rules_total": 4,
            "auto_execute_enabled": True,
            "summary": {"devices_total": 10},
        },
    ]
    for payload in events:
        db.add(
            EventLog(
                device_id=None,
                severity="info",
                event_id="CLOSED_LOOP_EVAL_SUMMARY",
                message=json.dumps(payload),
                source="ClosedLoop",
                timestamp=datetime.now(),
            )
        )
    db.commit()

    res = client.get("/api/v1/sdn/dashboard/stats", headers=normal_user_token)
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert "closed_loop_kpi" in payload
    kpi = payload["closed_loop_kpi"]
    assert int(kpi["totals"]["cycles"]) == 2
    assert int(kpi["totals"]["triggered"]) == 8
    assert int(kpi["totals"]["executed"]) == 3
    assert int(kpi["totals"]["blocked"]) == 5
    assert int(kpi["totals"]["approvals_opened"]) == 3
    assert float(kpi["execute_per_trigger_pct"]) == 37.5
    assert float(kpi["blocked_per_trigger_pct"]) == 62.5
    assert float(kpi["approvals_per_execution_pct"]) == 100.0
    assert float(kpi["avg_triggered_per_cycle"]) == 4.0
    assert float(kpi["avg_executed_per_cycle"]) == 1.5


def test_dashboard_stats_closed_loop_kpi_alerts_when_engine_enabled_and_cycles_low(client, normal_user_token, db):
    db.add(SystemSetting(key="closed_loop_engine_enabled", value="true", description="t", category="system"))
    db.add(SystemSetting(key="ops_alerts_min_closed_loop_cycles_30d", value="3", description="t", category="system"))
    db.add(SystemSetting(key="ops_alerts_min_closed_loop_execute_per_trigger_pct", value="50", description="t", category="system"))
    db.add(SystemSetting(key="ops_alerts_max_closed_loop_blocked_per_trigger_pct", value="40", description="t", category="system"))
    db.commit()

    db.add(
        EventLog(
            device_id=None,
            severity="info",
            event_id="CLOSED_LOOP_EVAL_SUMMARY",
            message=json.dumps(
                {
                    "status": "ok",
                    "dry_run": False,
                    "triggered": 4,
                    "executed": 1,
                    "blocked": 3,
                    "approvals_opened": 1,
                }
            ),
            source="ClosedLoop",
            timestamp=datetime.now(),
        )
    )
    db.commit()

    res = client.get("/api/v1/sdn/dashboard/stats", headers=normal_user_token)
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    kpi = payload["closed_loop_kpi"]
    assert kpi["engine_enabled"] is True
    assert kpi["status"] in {"warning", "critical"}
    assert int(kpi["alerts_count"]) >= 1
    codes = {str(a.get("code") or "") for a in list(kpi.get("alerts") or [])}
    assert "closed_loop_cycles_low" in codes
    assert "closed_loop_execute_rate_low" in codes
    assert "closed_loop_blocked_rate_high" in codes


def test_dashboard_stats_includes_northbound_kpi(client, normal_user_token, db):
    now = datetime.now()
    entries = [
        {
            "status": "ok",
            "mode": "servicenow",
            "event_type": "issue",
            "attempts": 1,
            "status_code": 201,
            "failure_cause": None,
        },
        {
            "status": "failed",
            "mode": "jira",
            "event_type": "closed_loop",
            "attempts": 3,
            "status_code": 502,
            "failure_cause": "http_5xx",
        },
        {
            "status": "ok",
            "mode": "splunk",
            "event_type": "issue",
            "attempts": 2,
            "status_code": 200,
            "failure_cause": None,
        },
    ]
    for idx, payload in enumerate(entries, start=1):
        db.add(
            EventLog(
                device_id=None,
                severity="info",
                event_id="NORTHBOUND_WEBHOOK_DELIVERY",
                message=json.dumps(payload),
                source="Northbound",
                timestamp=now,
            )
        )
    db.commit()

    res = client.get("/api/v1/sdn/dashboard/stats", headers=normal_user_token)
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert "northbound_kpi" in payload
    kpi = payload["northbound_kpi"]
    totals = kpi.get("totals") or {}
    assert int(totals.get("deliveries") or 0) >= 3
    assert int(totals.get("success") or 0) >= 2
    assert int(totals.get("failed") or 0) >= 1
    assert float(kpi.get("success_rate_pct") or 0) > 0
    assert int(kpi.get("p95_attempts") or 0) >= 1
    failure_causes = {str(x.get("cause") or "") for x in list(kpi.get("failure_causes") or [])}
    assert "http_5xx" in failure_causes


def test_dashboard_stats_includes_autonomy_kpi(client, normal_user_token, db):
    dev = Device(name="dash-autonomy-dev", ip_address="10.230.0.12", device_type="cisco_ios", status="online")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    now = datetime.now()
    event_1_ts = now
    event_2_ts = now

    db.add(
        EventLog(
            device_id=int(dev.id),
            severity="warning",
            event_id="BGP_NEIGHBOR_DOWN",
            message="bgp down",
            source="Monitoring",
            timestamp=event_1_ts,
        )
    )
    db.add(
        EventLog(
            device_id=int(dev.id),
            severity="critical",
            event_id="INTERFACE_DOWN",
            message="interface down",
            source="Syslog",
            timestamp=event_2_ts,
        )
    )

    issue_1_created = event_1_ts + timedelta(seconds=120)
    issue_2_created = event_2_ts + timedelta(seconds=240)
    db.add(
        Issue(
            device_id=int(dev.id),
            title="BGP Neighbor Down",
            description="auto-created",
            severity="warning",
            status="resolved",
            category="system",
            created_at=issue_1_created,
            resolved_at=issue_1_created + timedelta(minutes=10),
        )
    )
    db.add(
        Issue(
            device_id=int(dev.id),
            title="Interface Down",
            description="auto-created",
            severity="critical",
            status="resolved",
            category="system",
            created_at=issue_2_created,
            resolved_at=issue_2_created + timedelta(minutes=20),
        )
    )

    db.add(
        EventLog(
            device_id=None,
            severity="info",
            event_id="CLOSED_LOOP_EVAL_SUMMARY",
            message=json.dumps(
                {
                    "status": "ok",
                    "dry_run": False,
                    "triggered": 8,
                    "executed": 5,
                    "blocked": 3,
                    "approvals_opened": 2,
                }
            ),
            source="ClosedLoop",
            timestamp=now,
        )
    )
    db.commit()

    res = client.get("/api/v1/sdn/dashboard/stats", headers=normal_user_token)
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body

    assert "autonomy_kpi" in payload
    kpi = payload["autonomy_kpi"]
    totals = kpi.get("totals") or {}

    assert int(totals.get("issues_created") or 0) == 2
    assert int(totals.get("issues_resolved") or 0) == 2
    assert int(totals.get("mttd_samples") or 0) == 2
    assert int(totals.get("mttr_samples") or 0) == 2
    assert int(totals.get("actions_executed") or 0) == 5
    assert int(totals.get("actions_auto") or 0) == 3
    assert int(totals.get("actions_manual") or 0) == 2

    assert float(kpi.get("auto_action_rate_pct") or 0) == 60.0
    assert float(kpi.get("operator_intervention_rate_pct") or 0) == 40.0
    assert float(kpi.get("mttd_seconds") or 0) == 180.0
    assert float(kpi.get("mttd_p95_seconds") or 0) == 240.0
    assert float(kpi.get("mttr_seconds") or 0) == 900.0
    assert float(kpi.get("mttr_p95_seconds") or 0) == 1200.0
    assert str(kpi.get("status") or "") == "healthy"
    trend_7d = list(kpi.get("trend_7d") or [])
    assert len(trend_7d) == 7
    today_key = now.strftime("%Y-%m-%d")
    today_row = next((r for r in trend_7d if str(r.get("date") or "") == today_key), None)
    assert isinstance(today_row, dict)
    assert int(today_row.get("issues_created") or 0) == 2
    assert int(today_row.get("issues_resolved") or 0) == 2
    assert int(today_row.get("actions_executed") or 0) == 5
    assert int(today_row.get("actions_auto") or 0) == 3
    assert int(today_row.get("actions_manual") or 0) == 2
    assert float(today_row.get("auto_action_rate_pct") or 0) == 60.0
    assert float(today_row.get("operator_intervention_rate_pct") or 0) == 40.0


def test_dashboard_stats_autonomy_kpi_uses_threshold_settings(client, normal_user_token, db):
    dev = Device(name="dash-autonomy-thr-dev", ip_address="10.230.0.13", device_type="cisco_ios", status="online")
    db.add(dev)
    db.add(SystemSetting(key="ops_alerts_min_auto_action_rate_pct", value="80", description="t", category="system"))
    db.add(SystemSetting(key="ops_alerts_max_operator_intervention_rate_pct", value="20", description="t", category="system"))
    db.add(
        EventLog(
            device_id=None,
            severity="info",
            event_id="CLOSED_LOOP_EVAL_SUMMARY",
            message=json.dumps(
                {
                    "status": "ok",
                    "dry_run": False,
                    "triggered": 8,
                    "executed": 5,
                    "blocked": 3,
                    "approvals_opened": 2,
                }
            ),
            source="ClosedLoop",
            timestamp=datetime.now(),
        )
    )
    db.commit()

    res = client.get("/api/v1/sdn/dashboard/stats", headers=normal_user_token)
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    kpi = payload.get("autonomy_kpi") or {}
    targets = kpi.get("targets") or {}

    assert float(targets.get("min_auto_action_rate_pct") or 0) == 80.0
    assert float(targets.get("max_operator_intervention_rate_pct") or 0) == 20.0
    assert float(kpi.get("auto_action_rate_pct") or 0) == 60.0
    assert float(kpi.get("operator_intervention_rate_pct") or 0) == 40.0
    assert str(kpi.get("status") or "") == "warning"
