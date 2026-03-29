from app.models.device import Device, Issue


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _seed_issue(db):
    device = Device(
        name="svc-core-1",
        hostname="svc-core-1",
        ip_address="10.77.0.10",
        status="online",
        device_type="cisco_ios",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    issue = Issue(
        device_id=int(device.id),
        title="Core uplink degradation",
        description="Repeated packet loss and CRC errors were detected on the primary uplink.",
        severity="warning",
        category="performance",
        status="active",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return device, issue


def test_issue_sop_builds_from_issue_context(client, normal_user_token, db):
    _, issue = _seed_issue(db)

    res = client.get(f"/api/v1/sdn/issues/{int(issue.id)}/sop", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["issue_id"] == int(issue.id)
    assert body["readiness_status"] == "limited_context"
    assert len(list(body.get("steps") or [])) >= 4
    assert body["steps"][0]["id"] == "assess-scope"
    assert any(step["id"] == "verify-recovery" for step in body["steps"])


def test_issue_sop_uses_known_error_and_action_context(client, operator_user_token, normal_user_token, db):
    _, issue = _seed_issue(db)

    create_action = client.post(
        f"/api/v1/sdn/issues/{int(issue.id)}/actions",
        headers=operator_user_token,
        json={"assignee_name": "NOC-2", "note": "Investigate uplink optics immediately."},
    )
    assert create_action.status_code == 200

    create_ke = client.post(
        f"/api/v1/sdn/issues/{int(issue.id)}/knowledge",
        headers=operator_user_token,
        json={
            "root_cause": "Primary uplink transceiver degradation",
            "workaround": "Move traffic to the standby uplink and replace the optics.",
            "sop_summary": "Follow the uplink degradation SOP and verify CRC counters normalize.",
        },
    )
    assert create_ke.status_code == 200

    res = client.get(f"/api/v1/sdn/issues/{int(issue.id)}/sop", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["readiness_status"] == "ready"
    assert body["active_action_count"] == 1
    assert body["matched_known_error_count"] == 1
    assert body["recommended_owner"] == "NOC-2"
    assert body["top_known_error_title"] == "Core uplink degradation"
    step_ids = [step["id"] for step in list(body.get("steps") or [])]
    assert "apply-workaround" in step_ids
    assert "follow-runbook" in step_ids


def test_active_issues_include_sop_summary(client, operator_user_token, normal_user_token, db):
    _, issue = _seed_issue(db)

    create_ke = client.post(
        f"/api/v1/sdn/issues/{int(issue.id)}/knowledge",
        headers=operator_user_token,
        json={
            "root_cause": "Primary uplink transceiver degradation",
            "workaround": "Move traffic to the standby uplink.",
        },
    )
    assert create_ke.status_code == 200

    res = client.get("/api/v1/sdn/issues/active", headers=normal_user_token)
    assert res.status_code == 200
    rows = _unwrap(res.json())
    assert len(rows) == 1
    summary = rows[0].get("sop_summary") or {}
    assert summary.get("available") is True
    assert int(summary.get("step_count") or 0) >= 4
    assert summary.get("readiness_status") in {"ready", "limited_context"}
