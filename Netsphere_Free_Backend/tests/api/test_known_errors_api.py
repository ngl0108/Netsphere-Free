from app.models.device import Device, Issue


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _seed_issue(db):
    device = Device(
        name="core-dist-1",
        hostname="core-dist-1",
        ip_address="10.98.0.10",
        status="online",
        device_type="cisco_ios",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    issue = Issue(
        device_id=int(device.id),
        title="Core uplink packet loss",
        description="Repeated packet loss and CRC errors on the core uplink were detected.",
        severity="warning",
        category="performance",
        status="active",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)
    return device, issue


def test_create_known_error_from_issue_and_recommend_it(client, operator_user_token, normal_user_token, db):
    _, issue = _seed_issue(db)

    create_res = client.post(
        f"/api/v1/sdn/issues/{int(issue.id)}/knowledge",
        headers=operator_user_token,
        json={
            "root_cause": "Optical module degradation on core uplink",
            "workaround": "Switch traffic to the standby uplink and replace optics",
            "sop_summary": "Follow uplink degradation SOP and verify CRC counters normalize.",
            "tags": ["uplink", "packet-loss"],
        },
    )
    assert create_res.status_code == 200
    created = _unwrap(create_res.json())
    assert created["title"] == "Core uplink packet loss"
    assert created["category"] == "performance"
    assert created["device_type_scope"] == "cisco_ios"
    assert created["root_cause"] == "Optical module degradation on core uplink"

    recommendation_res = client.get(
        f"/api/v1/sdn/issues/{int(issue.id)}/knowledge",
        headers=normal_user_token,
    )
    assert recommendation_res.status_code == 200
    rows = _unwrap(recommendation_res.json())
    assert len(rows) == 1
    assert rows[0]["title"] == "Core uplink packet loss"
    assert float(rows[0]["match_score"] or 0.0) > 0.0
    assert "category_match" in list(rows[0].get("match_reasons") or [])


def test_active_issues_include_known_error_summary(client, operator_user_token, normal_user_token, db):
    _, issue = _seed_issue(db)

    create_res = client.post(
        f"/api/v1/sdn/issues/{int(issue.id)}/knowledge",
        headers=operator_user_token,
        json={
            "title": "Core uplink degradation",
            "symptom_pattern": "uplink packet loss crc errors",
            "root_cause": "Transceiver degradation",
            "workaround": "Move traffic to standby uplink",
        },
    )
    assert create_res.status_code == 200

    issues_res = client.get("/api/v1/sdn/issues/active", headers=normal_user_token)
    assert issues_res.status_code == 200
    rows = _unwrap(issues_res.json())
    assert len(rows) == 1
    summary = rows[0].get("knowledge_summary") or {}
    assert int(summary.get("recommendation_count") or 0) == 1
    assert summary.get("top_title") == "Core uplink degradation"
