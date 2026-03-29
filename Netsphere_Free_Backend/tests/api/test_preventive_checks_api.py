from datetime import datetime, timedelta, timezone

from app.models.device import ComplianceReport, Device, Issue


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_preventive_check_templates_seed_and_create(client, operator_user_token):
    seeded = client.get("/api/v1/ops/preventive-checks/templates", headers=operator_user_token)
    assert seeded.status_code == 200
    seeded_rows = _unwrap(seeded.json())
    assert any(str(row.get("name") or "").strip() == "Daily Managed Device Baseline" for row in seeded_rows)

    payload = {
        "name": "Core Preventive Review",
        "description": "Review core device availability and compliance posture.",
        "target_scope": {"roles": ["core"], "management_states": ["managed"]},
        "schedule": {"cadence": "daily", "hour": 8, "minute": 30, "timezone": "Asia/Seoul"},
        "checks": [
            {"key": "device_offline", "enabled": True, "severity": "critical"},
            {"key": "compliance_violation", "enabled": True, "severity": "warning", "min_score": 95},
        ],
        "is_enabled": True,
    }
    created = client.post("/api/v1/ops/preventive-checks/templates", json=payload, headers=operator_user_token)
    assert created.status_code == 200
    body = _unwrap(created.json())
    assert body["name"] == payload["name"]
    assert body["target_scope"]["roles"] == ["core"]
    assert body["schedule"]["cadence"] == "daily"
    assert isinstance(body.get("next_run_at"), str)


def test_preventive_check_run_collects_findings(client, operator_user_token, db):
    now = datetime.now(timezone.utc)
    offline = Device(
        name="core-sw-1",
        ip_address="10.0.0.10",
        status="offline",
        role="core",
        management_state="managed",
        last_seen=now - timedelta(hours=6),
    )
    discovered = Device(
        name="edge-sw-1",
        ip_address="10.0.0.20",
        status="online",
        role="edge",
        management_state="discovered_only",
        last_seen=now - timedelta(minutes=20),
    )
    db.add_all([offline, discovered])
    db.commit()
    db.refresh(offline)
    db.refresh(discovered)

    db.add(
        Issue(
            device_id=int(offline.id),
            title="Core down",
            severity="critical",
            status="active",
            category="system",
        )
    )
    db.add(
        ComplianceReport(
            device_id=int(offline.id),
            status="violation",
            match_percentage=82.0,
            details={
                "summary": {"status": "violation", "violations_total": 2, "score": 82.0},
                "automation": {"drift": {"status": "drift"}},
            },
        )
    )
    db.commit()

    create_res = client.post(
        "/api/v1/ops/preventive-checks/templates",
        json={
            "name": "Run Validation Template",
            "description": "Validate preventive run aggregation.",
            "target_scope": {"device_ids": [int(offline.id), int(discovered.id)], "management_states": ["managed", "discovered_only"]},
            "schedule": {"cadence": "manual"},
            "checks": [
                {"key": "device_offline", "enabled": True, "severity": "critical"},
                {"key": "stale_last_seen", "enabled": True, "severity": "warning", "threshold_minutes": 60},
                {"key": "active_critical_issues", "enabled": True, "severity": "critical"},
                {"key": "compliance_violation", "enabled": True, "severity": "warning", "min_score": 95},
                {"key": "drift_detected", "enabled": True, "severity": "warning"},
                {"key": "discovered_only_device", "enabled": True, "severity": "info"},
            ],
            "is_enabled": True,
        },
        headers=operator_user_token,
    )
    assert create_res.status_code == 200
    template_id = int(_unwrap(create_res.json())["id"])

    run_res = client.post(
        f"/api/v1/ops/preventive-checks/templates/{template_id}/run",
        headers=operator_user_token,
    )
    assert run_res.status_code == 200
    run = _unwrap(run_res.json())
    summary = run["summary"]
    assert summary["devices_total"] == 2
    assert summary["critical_devices"] == 1
    assert summary["info_devices"] == 1
    assert summary["failed_checks_total"] >= 5

    by_name = {row["device_name"]: row for row in run["findings"]}
    assert by_name["core-sw-1"]["status"] == "critical"
    assert any(f["check_key"] == "device_offline" for f in by_name["core-sw-1"]["findings"])
    assert any(f["check_key"] == "active_critical_issues" for f in by_name["core-sw-1"]["findings"])
    assert any(f["check_key"] == "compliance_violation" for f in by_name["core-sw-1"]["findings"])
    assert any(f["check_key"] == "drift_detected" for f in by_name["core-sw-1"]["findings"])
    assert by_name["edge-sw-1"]["status"] == "info"
    assert any(f["check_key"] == "discovered_only_device" for f in by_name["edge-sw-1"]["findings"])

    summary_res = client.get("/api/v1/ops/preventive-checks/summary", headers=operator_user_token)
    assert summary_res.status_code == 200
    assert _unwrap(summary_res.json())["recent_runs_total"] >= 1


def test_preventive_check_run_export_csv(client, operator_user_token):
    create_res = client.post(
        "/api/v1/ops/preventive-checks/templates",
        json={
            "name": "Export Validation Template",
            "description": "Export validation.",
            "target_scope": {"management_states": ["managed"]},
            "schedule": {"cadence": "manual"},
            "checks": [{"key": "device_offline", "enabled": True, "severity": "critical"}],
            "is_enabled": True,
        },
        headers=operator_user_token,
    )
    assert create_res.status_code == 200
    template_id = int(_unwrap(create_res.json())["id"])

    run_res = client.post(
        f"/api/v1/ops/preventive-checks/templates/{template_id}/run",
        headers=operator_user_token,
    )
    assert run_res.status_code == 200
    run_id = int(_unwrap(run_res.json())["id"])

    export_res = client.get(
        f"/api/v1/ops/preventive-checks/runs/{run_id}/export",
        headers=operator_user_token,
    )
    assert export_res.status_code == 200
    assert "text/csv" in str(export_res.headers.get("content-type") or "")
    assert "preventive_check_run_" in str(export_res.headers.get("content-disposition") or "")


def test_preventive_check_run_export_markdown(client, operator_user_token):
    create_res = client.post(
        "/api/v1/ops/preventive-checks/templates",
        json={
            "name": "Markdown Export Template",
            "description": "Markdown export validation.",
            "target_scope": {"management_states": ["managed"]},
            "schedule": {"cadence": "manual"},
            "checks": [{"key": "device_offline", "enabled": True, "severity": "critical"}],
            "is_enabled": True,
        },
        headers=operator_user_token,
    )
    assert create_res.status_code == 200
    template_id = int(_unwrap(create_res.json())["id"])

    run_res = client.post(
        f"/api/v1/ops/preventive-checks/templates/{template_id}/run",
        headers=operator_user_token,
    )
    assert run_res.status_code == 200
    run_id = int(_unwrap(run_res.json())["id"])

    export_res = client.get(
        f"/api/v1/ops/preventive-checks/runs/{run_id}/export",
        params={"format": "md"},
        headers=operator_user_token,
    )
    assert export_res.status_code == 200
    assert "text/markdown" in str(export_res.headers.get("content-type") or "")
    assert "preventive_check_run_" in str(export_res.headers.get("content-disposition") or "")
    assert "# Preventive Check Report:" in export_res.text


def test_preventive_check_run_export_pdf(client, operator_user_token):
    create_res = client.post(
        "/api/v1/ops/preventive-checks/templates",
        json={
            "name": "PDF Export Template",
            "description": "PDF export validation.",
            "target_scope": {"management_states": ["managed"]},
            "schedule": {"cadence": "manual"},
            "checks": [{"key": "device_offline", "enabled": True, "severity": "critical"}],
            "is_enabled": True,
        },
        headers=operator_user_token,
    )
    assert create_res.status_code == 200
    template_id = int(_unwrap(create_res.json())["id"])

    run_res = client.post(
        f"/api/v1/ops/preventive-checks/templates/{template_id}/run",
        headers=operator_user_token,
    )
    assert run_res.status_code == 200
    run_id = int(_unwrap(run_res.json())["id"])

    export_res = client.get(
        f"/api/v1/ops/preventive-checks/runs/{run_id}/export",
        params={"format": "pdf"},
        headers=operator_user_token,
    )
    assert export_res.status_code == 200
    assert "application/pdf" in str(export_res.headers.get("content-type") or "")
    assert 'filename="preventive_check_run_' in str(export_res.headers.get("content-disposition") or "")
    assert export_res.content.startswith(b"%PDF")
