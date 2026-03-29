from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import fabric as fabric_ep
from app.models.approval import ApprovalRequest
from app.models.device import Device
from app.models.user import User


def test_fabric_live_deploy_requires_approval(db):
    db.add_all(
        [
            Device(name="fb-sp1", ip_address="10.193.0.1", device_type="cisco_ios", status="online"),
            Device(name="fb-lf1", ip_address="10.193.0.2", device_type="cisco_ios", status="online"),
        ]
    )
    db.commit()
    spine_id = int(db.query(Device).filter(Device.name == "fb-sp1").first().id)
    leaf_id = int(db.query(Device).filter(Device.name == "fb-lf1").first().id)

    with pytest.raises(HTTPException) as exc:
        fabric_ep.deploy_fabric_config(
            request=fabric_ep.FabricDeployRequest(
                spine_ids=[spine_id],
                leaf_ids=[leaf_id],
                dry_run=False,
            ),
            db=db,
            current_user=SimpleNamespace(id=1, role="operator"),
        )
    assert exc.value.status_code == 409
    assert "Approval required for live fabric deploy" in str(exc.value.detail)


def test_fabric_live_deploy_with_approval_id_is_allowed(db, monkeypatch):
    db.add_all(
        [
            Device(name="fb2-sp1", ip_address="10.194.0.1", device_type="cisco_ios", status="online"),
            Device(name="fb2-lf1", ip_address="10.194.0.2", device_type="cisco_ios", status="online"),
        ]
    )
    db.commit()
    spine_id = int(db.query(Device).filter(Device.name == "fb2-sp1").first().id)
    leaf_id = int(db.query(Device).filter(Device.name == "fb2-lf1").first().id)

    def fake_execute(_self, **kwargs):
        return {
            "summary": {
                "total": 2,
                "success": 2,
                "failed": 0,
                "skipped": 0,
                "dry_run": 0,
                "waves_total": 1,
                "waves_executed": 1,
                "halted": False,
                "halted_wave": None,
                "approval_id": int(kwargs.get("approval_id")),
                "execution_id": str(kwargs.get("execution_id") or "exec-fabric-policy"),
            },
            "results": [
                {
                    "id": spine_id,
                    "device_id": spine_id,
                    "status": "success",
                    "approval_id": int(kwargs.get("approval_id")),
                    "execution_id": str(kwargs.get("execution_id") or "exec-fabric-policy"),
                },
                {
                    "id": leaf_id,
                    "device_id": leaf_id,
                    "status": "success",
                    "approval_id": int(kwargs.get("approval_id")),
                    "execution_id": str(kwargs.get("execution_id") or "exec-fabric-policy"),
                },
            ],
            "execution": {
                "waves_total": 1,
                "waves_executed": 1,
                "halted": False,
                "halted_wave": None,
                "approval_id": int(kwargs.get("approval_id")),
                "execution_id": str(kwargs.get("execution_id") or "exec-fabric-policy"),
            },
            "approval_id": int(kwargs.get("approval_id")),
            "execution_id": str(kwargs.get("execution_id") or "exec-fabric-policy"),
        }

    monkeypatch.setattr(fabric_ep.FabricService, "execute_deploy", fake_execute)

    requester = User(username="fb-pol-req", email="fb-pol-req@example.com", hashed_password="x", full_name="r", is_active=True, role="operator")
    approver = User(username="fb-pol-appr", email="fb-pol-appr@example.com", hashed_password="y", full_name="a", is_active=True, role="admin")
    db.add_all([requester, approver])
    db.commit()
    db.refresh(requester)
    db.refresh(approver)
    approval = ApprovalRequest(
        requester_id=int(requester.id),
        approver_id=int(approver.id),
        title="fabric approved",
        request_type="fabric_deploy",
        payload={"spine_ids": [spine_id], "leaf_ids": [leaf_id]},
        status="approved",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    out = fabric_ep.deploy_fabric_config(
        request=fabric_ep.FabricDeployRequest(
            spine_ids=[spine_id],
            leaf_ids=[leaf_id],
            dry_run=False,
            approval_id=int(approval.id),
            execution_id="exec-991",
        ),
        db=db,
        current_user=SimpleNamespace(id=1, role="operator"),
    )
    assert int(out.get("approval_id")) == int(approval.id)
    assert str(out.get("execution_id")) == "exec-991"
    assert int((out.get("summary") or {}).get("approval_id")) == int(approval.id)
    db.refresh(approval)
    approval_payload = dict(approval.payload or {})
    assert approval_payload.get("approval_id") == int(approval.id)
    assert str(approval_payload.get("execution_id") or "").strip() == "exec-991"
    assert str(approval_payload.get("execution_status") or "").strip().lower() == "success"
    summary = (approval_payload.get("execution_result_summary") or {}).get("summary") or {}
    assert int(summary.get("success") or 0) == 2


def test_fabric_live_deploy_rejects_non_approved_approval_id(db):
    db.add_all(
        [
            Device(name="fb3-sp1", ip_address="10.195.0.1", device_type="cisco_ios", status="online"),
            Device(name="fb3-lf1", ip_address="10.195.0.2", device_type="cisco_ios", status="online"),
        ]
    )
    db.commit()
    spine_id = int(db.query(Device).filter(Device.name == "fb3-sp1").first().id)
    leaf_id = int(db.query(Device).filter(Device.name == "fb3-lf1").first().id)

    requester = User(username="fb-pol-req2", email="fb-pol-req2@example.com", hashed_password="x", full_name="r2", is_active=True, role="operator")
    approver = User(username="fb-pol-appr2", email="fb-pol-appr2@example.com", hashed_password="y", full_name="a2", is_active=True, role="admin")
    db.add_all([requester, approver])
    db.commit()
    db.refresh(requester)
    db.refresh(approver)
    approval = ApprovalRequest(
        requester_id=int(requester.id),
        approver_id=int(approver.id),
        title="fabric pending",
        request_type="fabric_deploy",
        payload={"spine_ids": [spine_id], "leaf_ids": [leaf_id]},
        status="pending",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    with pytest.raises(HTTPException) as exc:
        fabric_ep.deploy_fabric_config(
            request=fabric_ep.FabricDeployRequest(
                spine_ids=[spine_id],
                leaf_ids=[leaf_id],
                dry_run=False,
                approval_id=int(approval.id),
            ),
            db=db,
            current_user=SimpleNamespace(id=1, role="operator"),
        )
    assert exc.value.status_code == 409
    assert "must be approved before execution" in str(exc.value.detail)


def test_fabric_live_deploy_rejects_wrong_request_type_approval_id(db):
    db.add_all(
        [
            Device(name="fb4-sp1", ip_address="10.196.0.1", device_type="cisco_ios", status="online"),
            Device(name="fb4-lf1", ip_address="10.196.0.2", device_type="cisco_ios", status="online"),
        ]
    )
    db.commit()
    spine_id = int(db.query(Device).filter(Device.name == "fb4-sp1").first().id)
    leaf_id = int(db.query(Device).filter(Device.name == "fb4-lf1").first().id)

    requester = User(username="fb-pol-req3", email="fb-pol-req3@example.com", hashed_password="x", full_name="r3", is_active=True, role="operator")
    approver = User(username="fb-pol-appr3", email="fb-pol-appr3@example.com", hashed_password="y", full_name="a3", is_active=True, role="admin")
    db.add_all([requester, approver])
    db.commit()
    db.refresh(requester)
    db.refresh(approver)
    approval = ApprovalRequest(
        requester_id=int(requester.id),
        approver_id=int(approver.id),
        title="wrong type",
        request_type="template_deploy",
        payload={"template_id": 1},
        status="approved",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    with pytest.raises(HTTPException) as exc:
        fabric_ep.deploy_fabric_config(
            request=fabric_ep.FabricDeployRequest(
                spine_ids=[spine_id],
                leaf_ids=[leaf_id],
                dry_run=False,
                approval_id=int(approval.id),
            ),
            db=db,
            current_user=SimpleNamespace(id=1, role="operator"),
        )
    assert exc.value.status_code == 409
    assert "expected=fabric_deploy" in str(exc.value.detail)
