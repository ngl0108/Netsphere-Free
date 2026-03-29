from app.models.device import Device, Issue


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _seed_issue(db):
    device = Device(
        name="ops-edge-1",
        hostname="ops-edge-1",
        ip_address="10.88.0.10",
        status="online",
        device_type="cisco_ios",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    issue = Issue(
        device_id=int(device.id),
        title="Core uplink instability",
        description="Repeated packet loss was detected on the core uplink.",
        severity="warning",
        category="performance",
        status="active",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return device, issue


def test_issue_action_create_list_and_update(client, operator_user_token, normal_user_token, db):
    _, issue = _seed_issue(db)

    create_res = client.post(
        f"/api/v1/sdn/issues/{int(issue.id)}/actions",
        headers=operator_user_token,
        json={
            "assignee_name": "NOC-1",
            "note": "Investigate packet drops around the uplink.",
        },
    )
    assert create_res.status_code == 200
    created = _unwrap(create_res.json())
    assert created["issue_id"] == int(issue.id)
    assert created["status"] == "open"
    assert created["assignee_name"] == "NOC-1"
    assert created["latest_note"] == "Investigate packet drops around the uplink."
    assert len(list(created.get("timeline") or [])) == 1

    list_res = client.get(f"/api/v1/sdn/issues/{int(issue.id)}/actions", headers=normal_user_token)
    assert list_res.status_code == 200
    rows = _unwrap(list_res.json())
    assert len(rows) == 1
    assert rows[0]["id"] == int(created["id"])

    update_res = client.put(
        f"/api/v1/sdn/actions/{int(created['id'])}",
        headers=operator_user_token,
        json={
            "status": "investigating",
            "note": "Core uplink optics inspection started.",
        },
    )
    assert update_res.status_code == 200
    updated = _unwrap(update_res.json())
    assert updated["status"] == "investigating"
    assert updated["latest_note"] == "Core uplink optics inspection started."
    assert len(list(updated.get("timeline") or [])) == 2


def test_active_issues_include_action_summary(client, operator_user_token, normal_user_token, db):
    _, issue = _seed_issue(db)

    create_res = client.post(
        f"/api/v1/sdn/issues/{int(issue.id)}/actions",
        headers=operator_user_token,
        json={"note": "Escalate to network operations."},
    )
    assert create_res.status_code == 200
    created = _unwrap(create_res.json())

    update_res = client.put(
        f"/api/v1/sdn/actions/{int(created['id'])}",
        headers=operator_user_token,
        json={"status": "investigating"},
    )
    assert update_res.status_code == 200

    issues_res = client.get("/api/v1/sdn/issues/active", headers=normal_user_token)
    assert issues_res.status_code == 200
    rows = _unwrap(issues_res.json())
    assert len(rows) == 1
    summary = rows[0].get("action_summary") or {}
    assert int(summary.get("total") or 0) == 1
    assert int(summary.get("investigating") or 0) == 1
    assert summary.get("has_active") is True
    assert summary.get("latest_status") == "investigating"
    assert summary.get("latest_title") == "Core uplink instability"
    assert summary.get("latest_note") == "Escalate to network operations."
    assert summary.get("latest_updated_at") is not None


def test_issue_action_requires_operator_for_mutation(client, normal_user_token, db):
    _, issue = _seed_issue(db)

    create_res = client.post(
        f"/api/v1/sdn/issues/{int(issue.id)}/actions",
        headers=normal_user_token,
        json={"note": "Viewer should not create this."},
    )
    assert create_res.status_code == 403
