from app.models.approval import ApprovalRequest
from app.models.device import Device, Issue
from app.models.user import User


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _seed_issue(db, *, cloud: bool = False):
    variables = None
    device_type = "cisco_ios"
    if cloud:
        device_type = "cloud_virtual"
        variables = {
            "cloud": {
                "refs": [
                    {
                        "provider": "aws",
                        "account_id": 77,
                        "account_name": "aws-ops",
                        "region": "ap-northeast-2",
                        "resource_type": "subnet",
                        "resource_id": "subnet-ops-a",
                        "name": "ops-subnet-a",
                    }
                ]
            }
        }
    device = Device(
        name="ops-core-1" if not cloud else "cloud-edge-1",
        hostname="ops-core-1" if not cloud else "cloud-edge-1",
        ip_address="10.77.0.10",
        status="online",
        device_type=device_type,
        variables=variables,
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    issue = Issue(
        device_id=int(device.id),
        title="Routing instability" if not cloud else "Cloud subnet drift",
        description="Repeated instability detected on the monitored path.",
        severity="warning",
        category="performance" if not cloud else "config",
        status="active",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return device, issue


def test_issue_approval_context_matches_device_scope_and_execution_details(client, normal_user_token, admin_user_token, db):
    device, issue = _seed_issue(db)
    requester = db.query(User).filter(User.username == "adminuser").first()
    approval = ApprovalRequest(
        requester_id=int(requester.id),
        title="Core uplink rollback-ready change",
        request_type="template_deploy",
        status="approved",
        payload={
            "device_ids": [int(device.id)],
            "rollback_on_failure": True,
            "execution_status": "executed",
            "execution_result": {
                "summary": [
                    {
                        "status": "postcheck_failed",
                        "rollback_attempted": True,
                        "rollback_success": True,
                        "failure_cause": "post_check_failed",
                    }
                ]
            },
            "execution_trace": {"approval_id": 1, "execution_id": "exec-1"},
        },
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    res = client.get(f"/api/v1/sdn/issues/{int(issue.id)}/approval-context", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["issue_id"] == int(issue.id)
    assert body["summary"]["total"] == 1
    assert body["summary"]["approved"] == 1
    assert body["summary"]["evidence_ready_count"] == 1
    assert body["summary"]["rollback_tracked_count"] == 1
    assert "device_scope_match" in list(body.get("match_reasons") or [])
    item = body["items"][0]
    assert item["id"] == int(approval.id)
    assert item["request_type"] == "template_deploy"
    assert item["has_evidence"] is True
    assert item["rollback_attempted"] is True
    assert item["rollback_success"] is True
    assert item["post_check_failed"] is True
    assert item["top_cause"] == "post_check_failed"


def test_issue_approval_context_matches_cloud_scope(client, normal_user_token, admin_user_token, db):
    _, issue = _seed_issue(db, cloud=True)
    requester = db.query(User).filter(User.username == "adminuser").first()
    approval = ApprovalRequest(
        requester_id=int(requester.id),
        title="Cloud subnet intent",
        request_type="intent_apply",
        status="pending",
        payload={
            "account_ids": [77],
            "resource_ids": ["subnet-ops-a"],
            "region": "ap-northeast-2",
            "provider": "aws",
        },
    )
    db.add(approval)
    db.commit()

    res = client.get(f"/api/v1/sdn/issues/{int(issue.id)}/approval-context", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["summary"]["total"] == 1
    assert body["summary"]["pending"] == 1
    assert body["cloud_scope"] is not None
    assert any(reason in {"cloud_resource_match", "cloud_account_match", "cloud_region_match"} for reason in list(body.get("match_reasons") or []))


def test_active_issues_include_approval_summary(client, normal_user_token, admin_user_token, db):
    device, issue = _seed_issue(db)
    requester = db.query(User).filter(User.username == "adminuser").first()
    approval = ApprovalRequest(
        requester_id=int(requester.id),
        title="Approval summary seed",
        request_type="template_deploy",
        status="pending",
        payload={"device_id": int(device.id)},
    )
    db.add(approval)
    db.commit()

    res = client.get("/api/v1/sdn/issues/active", headers=normal_user_token)
    assert res.status_code == 200
    rows = _unwrap(res.json())
    assert len(rows) == 1
    summary = rows[0].get("approval_summary") or {}
    assert int(summary.get("total") or 0) == 1
    assert int(summary.get("pending") or 0) == 1
    assert summary.get("latest_status") == "pending"
    assert int(summary.get("latest_approval_id") or 0) == int(approval.id)
