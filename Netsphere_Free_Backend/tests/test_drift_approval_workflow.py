from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, ConfigBackup, ConfigTemplate
from app.models.settings import SystemSetting
from app.models.approval import ApprovalRequest


@pytest.fixture()
def db_engine():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return engine


def test_scheduled_drift_creates_approval_request(monkeypatch, db_engine):
    from app.tasks import compliance as tc

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    monkeypatch.setattr(tc, "SessionLocal", SessionLocal)

    def fake_check(self, device_id: int):
        return {"device_id": device_id, "status": "drift", "golden_id": 10, "latest_id": 11}

    monkeypatch.setattr(tc.ComplianceEngine, "check_config_drift", fake_check)

    db = SessionLocal()
    dev = Device(name="sw1", ip_address="10.0.0.1")
    db.add(dev)
    db.commit()
    db.refresh(dev)
    dev_id = int(dev.id)
    db.add(SystemSetting(key="config_drift_approval_enabled", value="true", description="", category="General"))
    db.add(ConfigBackup(device_id=dev.id, raw_config="golden", is_golden=True))
    db.commit()
    db.close()

    tc.run_scheduled_config_drift_checks()
    tc.run_scheduled_config_drift_checks()

    db = SessionLocal()
    reqs = db.query(ApprovalRequest).filter(ApprovalRequest.request_type == "config_drift_remediate").all()
    assert len(reqs) == 1
    assert int((reqs[0].payload or {}).get("device_id")) == int(dev_id)
    db.close()


def test_approve_dispatches_remediation_task(monkeypatch, db_engine):
    from app.api.v1.endpoints import approval as approval_endpoint

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    db = SessionLocal()

    dev = Device(name="sw1", ip_address="10.0.0.1")
    db.add(dev)
    db.commit()
    db.refresh(dev)

    from app.models.user import User

    requester = User(username="req", hashed_password="x", full_name="r", role="operator", is_active=True)
    approver = User(username="admin", hashed_password="y", full_name="a", role="admin", is_active=True)
    db.add(requester)
    db.add(approver)
    db.commit()
    db.refresh(requester)
    db.refresh(approver)

    req = ApprovalRequest(
        requester_id=requester.id,
        title="t",
        request_type="config_drift_remediate",
        payload={"device_id": dev.id},
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    from app.services import compliance_service as cs
    from app.tasks import compliance as compliance_task

    monkeypatch.setattr(
        cs.ComplianceEngine,
        "remediate_config_drift_batch",
        lambda *a, **k: {"summary": [], "execution": {"waves_total": 0, "waves_executed": 0, "halted": False, "halted_wave": None}},
    )
    monkeypatch.setattr(
        compliance_task.run_config_drift_remediation_for_approval,
        "apply_async",
        lambda *a, **k: SimpleNamespace(id="job-approval-1"),
        raising=False,
    )

    decision = approval_endpoint.ApprovalDecision(approver_comment="ok")
    out = approval_endpoint.approve_request(
        id=req.id,
        decision=decision,
        db=db,
        current_user=SimpleNamespace(id=approver.id, role="admin"),
    )

    assert out.status == "approved"
    assert out.payload.get("execution_status") == "queued"
    assert out.payload.get("approval_id") == int(req.id)
    assert str(out.payload.get("execution_id") or "").strip() != ""
    trace = out.payload.get("execution_trace") or {}
    assert int(trace.get("approval_id")) == int(req.id)
    assert str(trace.get("execution_id")) == str(out.payload.get("execution_id"))
    assert out.payload.get("execution_task_id") == "job-approval-1"
    db.close()


def test_approve_dispatches_template_deploy_with_trace(monkeypatch, db_engine):
    from app.api.v1.endpoints import approval as approval_endpoint
    from app.api.v1.endpoints import config_template as template_endpoint

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    db = SessionLocal()

    dev = Device(name="sw-template", ip_address="10.0.1.1", device_type="cisco_ios")
    tpl = ConfigTemplate(name="tpl1", category="ops", content="hostname {{ _dev_id }}", tags="v1")
    db.add_all([dev, tpl])
    db.commit()
    db.refresh(dev)
    db.refresh(tpl)

    from app.models.user import User

    requester = User(username="req2", hashed_password="x", full_name="r2", role="operator", is_active=True)
    approver = User(username="admin2", hashed_password="y", full_name="a2", role="admin", is_active=True)
    db.add_all([requester, approver])
    db.commit()
    db.refresh(requester)
    db.refresh(approver)

    req = ApprovalRequest(
        requester_id=requester.id,
        title="template deploy approve",
        request_type="template_deploy",
        payload={
            "template_id": int(tpl.id),
            "device_ids": [int(dev.id)],
            "wave_size": 1,
            "stop_on_wave_failure": True,
        },
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    monkeypatch.setattr(
        template_endpoint,
        "_deploy_worker",
        lambda target, _template_content, _opts: {"id": int(target["dev_id"]), "status": "success", "output": "ok"},
    )

    out = approval_endpoint.approve_request(
        id=req.id,
        decision=approval_endpoint.ApprovalDecision(approver_comment="go"),
        db=db,
        current_user=SimpleNamespace(id=approver.id, role="admin"),
    )

    assert out.status == "approved"
    assert out.payload.get("execution_status") == "executed"
    assert out.payload.get("approval_id") == int(req.id)
    execution_id = str(out.payload.get("execution_id") or "").strip()
    assert execution_id != ""
    trace = out.payload.get("execution_trace") or {}
    assert int(trace.get("approval_id")) == int(req.id)
    assert str(trace.get("execution_id")) == execution_id

    execution_result = out.payload.get("execution_result") or {}
    assert int(execution_result.get("approval_id")) == int(req.id)
    assert str(execution_result.get("execution_id")) == execution_id
    rows = list(execution_result.get("summary") or [])
    assert len(rows) == 1
    assert int(rows[0].get("approval_id")) == int(req.id)
    assert str(rows[0].get("execution_id")) == execution_id
    db.close()


def test_approve_dispatches_fabric_deploy_with_trace(db_engine):
    from app.api.v1.endpoints import approval as approval_endpoint

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    db = SessionLocal()

    spine = Device(name="f-spine", ip_address="10.0.2.1", device_type="cisco_ios", status="online")
    leaf = Device(name="f-leaf", ip_address="10.0.2.2", device_type="cisco_ios", status="online")
    db.add_all([spine, leaf])
    db.commit()
    db.refresh(spine)
    db.refresh(leaf)

    from app.models.user import User

    requester = User(username="req3", hashed_password="x", full_name="r3", role="operator", is_active=True)
    approver = User(username="admin3", hashed_password="y", full_name="a3", role="admin", is_active=True)
    db.add_all([requester, approver])
    db.commit()
    db.refresh(requester)
    db.refresh(approver)

    req = ApprovalRequest(
        requester_id=requester.id,
        title="fabric deploy approve",
        request_type="fabric_deploy",
        payload={
            "spine_ids": [int(spine.id)],
            "leaf_ids": [int(leaf.id)],
            "asn": 65000,
            "vni_base": 10000,
            "dry_run": True,
            "verify_commands": [],
        },
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    out = approval_endpoint.approve_request(
        id=req.id,
        decision=approval_endpoint.ApprovalDecision(approver_comment="run"),
        db=db,
        current_user=SimpleNamespace(id=approver.id, role="admin"),
    )

    assert out.status == "approved"
    assert out.payload.get("execution_status") == "executed"
    assert out.payload.get("approval_id") == int(req.id)
    execution_id = str(out.payload.get("execution_id") or "").strip()
    assert execution_id != ""
    trace = out.payload.get("execution_trace") or {}
    assert int(trace.get("approval_id")) == int(req.id)
    assert str(trace.get("execution_id")) == execution_id

    execution_result = out.payload.get("execution_result") or {}
    assert int(execution_result.get("approval_id")) == int(req.id)
    assert str(execution_result.get("execution_id")) == execution_id
    summary = dict(execution_result.get("summary") or {})
    assert int(summary.get("total") or 0) == 2
    assert int(summary.get("approval_id")) == int(req.id)
    assert str(summary.get("execution_id")) == execution_id
    rows = list(execution_result.get("results") or [])
    assert len(rows) == 2
    assert all(int(r.get("approval_id")) == int(req.id) for r in rows)
    assert all(str(r.get("execution_id")) == execution_id for r in rows)
    db.close()


def test_approve_dispatches_intent_apply_with_trace(monkeypatch, db_engine):
    from app.api.v1.endpoints import approval as approval_endpoint
    from app.services import intent_service as intent_service_mod

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    db = SessionLocal()

    from app.models.user import User

    requester = User(username="req-intent", hashed_password="x", full_name="req", role="operator", is_active=True)
    approver = User(username="admin-intent", hashed_password="y", full_name="admin", role="admin", is_active=True)
    db.add_all([requester, approver])
    db.commit()
    db.refresh(requester)
    db.refresh(approver)

    req = ApprovalRequest(
        requester_id=requester.id,
        title="cloud intent approval",
        request_type="intent_apply",
        payload={
            "intent_type": "cloud_policy",
            "name": "corp-guardrails",
            "dry_run": False,
            "spec": {
                "targets": {"providers": ["aws"], "account_ids": [101], "regions": ["ap-northeast-2"]},
                "required_tags": [{"key": "owner"}],
            },
            "metadata": {"source": "cloud_intents"},
        },
        status="pending",
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    monkeypatch.setattr(
        intent_service_mod.IntentService,
        "apply_intent",
        staticmethod(
            lambda _db, payload, actor_user=None: {
                "status": "applied",
                "message": "Intent applied and persisted.",
                "execution_id": str(payload.get("execution_id") or "intent-exec-approval"),
                "approval_id": int(payload.get("approval_id") or 0),
                "simulation": {
                    "risk_score": 45,
                    "terraform_plan_preview": {
                        "engine": "terraform",
                        "workspace_prefix": "netsphere-corp-guardrails",
                    },
                },
            }
        ),
    )

    out = approval_endpoint.approve_request(
        id=req.id,
        decision=approval_endpoint.ApprovalDecision(approver_comment="ship it"),
        db=db,
        current_user=SimpleNamespace(id=approver.id, role="admin"),
    )

    assert out.status == "approved"
    assert out.payload.get("execution_status") == "executed"
    assert out.payload.get("approval_id") == int(req.id)
    execution_id = str(out.payload.get("execution_id") or "").strip()
    assert execution_id != ""
    execution_result = out.payload.get("execution_result") or {}
    assert execution_result.get("status") == "applied"
    assert int(execution_result.get("approval_id") or 0) == int(req.id)
    trace = out.payload.get("execution_trace") or {}
    assert int(trace.get("approval_id") or 0) == int(req.id)
    assert str(trace.get("execution_id") or "").strip() == execution_id
    db.close()
