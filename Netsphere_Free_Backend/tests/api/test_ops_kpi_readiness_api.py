import json
from datetime import datetime, timedelta

from app.api.v1.endpoints import ops as ops_endpoint
from app.models.device import Device, EventLog, Issue
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.topology import TopologySnapshot


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_ops_kpi_readiness_returns_plan_evidence(client, normal_user_token, db):
    now = datetime.now()

    dev = Device(
        name="ops-kpi-dev",
        ip_address="10.250.0.10",
        device_type="cisco_ios",
        status="online",
    )
    db.add(dev)
    db.flush()

    job = DiscoveryJob(
        cidr="10.250.0.0/24",
        status="completed",
        logs="done",
        created_at=now - timedelta(seconds=180),
    )
    db.add(job)
    db.flush()

    db.add_all(
        [
            DiscoveredDevice(job_id=int(job.id), ip_address="10.250.0.11", status="approved", snmp_status="reachable"),
            DiscoveredDevice(job_id=int(job.id), ip_address="10.250.0.12", status="existing", snmp_status="reachable"),
            DiscoveredDevice(job_id=int(job.id), ip_address="10.250.0.13", status="approved", snmp_status="reachable"),
            DiscoveredDevice(job_id=int(job.id), ip_address="10.250.0.14", status="approved", snmp_status="reachable"),
        ]
    )
    db.add(
        TopologySnapshot(
            site_id=None,
            job_id=int(job.id),
            label="ops-kpi-first-map",
            node_count=2,
            link_count=1,
            nodes_json="[]",
            links_json="[]",
            metadata_json="{}",
            created_at=now - timedelta(seconds=90),
        )
    )

    for i in range(100):
        db.add(
            EventLog(
                device_id=int(dev.id),
                severity="info",
                event_id="CONFIG_DRIFT_REMEDIATION_KPI",
                message=json.dumps(
                    {
                        "status": "ok",
                        "device_id": int(dev.id),
                        "approval_id": 10000 + i,
                        "execution_id": f"exec-ok-{i}",
                        "post_check_failed": False,
                        "rollback_attempted": False,
                        "rollback_success": False,
                        "rollback_duration_ms": None,
                        "failure_cause": None,
                    }
                ),
                source="Compliance",
                timestamp=now - timedelta(minutes=20),
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
                    "approval_id": 20001,
                    "execution_id": "exec-fail-1",
                    "post_check_failed": True,
                    "rollback_attempted": True,
                    "rollback_success": True,
                    "rollback_duration_ms": 1200,
                    "failure_cause": "post_check_failed",
                }
            ),
            source="Compliance",
            timestamp=now - timedelta(minutes=19),
        )
    )

    for i in range(20):
        db.add(
            EventLog(
                device_id=None,
                severity="info",
                event_id="NORTHBOUND_WEBHOOK_DELIVERY",
                message=json.dumps(
                    {
                        "status": "ok",
                        "mode": "jira",
                        "event_type": "issue",
                        "attempts": 1,
                        "status_code": 201,
                        "failure_cause": None,
                    }
                ),
                source="Northbound",
                timestamp=now - timedelta(minutes=10),
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
                    "triggered": 10,
                    "executed": 8,
                    "blocked": 2,
                    "approvals_opened": 2,
                }
            ),
            source="ClosedLoop",
            timestamp=now - timedelta(minutes=5),
        )
    )

    db.add(
        EventLog(
            device_id=int(dev.id),
            severity="warning",
            event_id="INTERFACE_DOWN",
            message="link down",
            source="Syslog",
            timestamp=now - timedelta(seconds=240),
        )
    )
    db.add(
        Issue(
            device_id=int(dev.id),
            title="interface down",
            description="auto-created",
            severity="warning",
            status="resolved",
            category="performance",
            is_read=False,
            created_at=now - timedelta(seconds=120),
            resolved_at=now - timedelta(seconds=60),
        )
    )
    db.commit()

    res = client.get(
        "/api/v1/ops/kpi/readiness",
        params={
            "discovery_days": 30,
            "autonomy_mttd_baseline_seconds": 300,
            "autonomy_mttr_baseline_seconds": 180,
        },
        headers=normal_user_token,
    )
    assert res.status_code == 200
    payload = _unwrap(res.json())

    readiness = payload.get("readiness") or {}
    assert readiness.get("fail_count") == 0
    assert readiness.get("required_checks_total", 0) >= 10
    assert readiness.get("status") in {"healthy", "insufficient_data"}
    sample_coverage = ((payload.get("evidence") or {}).get("sample_coverage") or {})
    assert isinstance(sample_coverage, dict)
    assert sample_coverage["discovery_jobs"]["threshold"] == 30
    assert float(sample_coverage["discovery_jobs"]["coverage_pct"]) > 0.0
    assert sample_coverage["discovery_jobs"]["met"] in {True, False}

    checks = {str(row.get("id") or ""): row for row in list(payload.get("checks") or [])}
    assert checks["plug_scan.auto_reflection_rate_pct"]["status"] == "pass"
    assert checks["plug_scan.false_positive_rate_pct"]["status"] == "pass"
    assert checks["change.success_rate_pct"]["status"] == "pass"
    assert checks["change.failure_rate_pct"]["status"] == "pass"
    assert checks["change.rollback_p95_ms"]["status"] == "pass"
    assert checks["change.trace_coverage_pct"]["status"] == "pass"
    assert checks["autonomy.auto_action_rate_pct"]["status"] == "pass"
    assert checks["autonomy.operator_intervention_rate_pct"]["status"] == "pass"
    assert checks["northbound.success_rate_pct"]["status"] == "pass"
    assert checks["northbound.p95_attempts"]["status"] == "pass"
    assert checks["northbound.failed_24h"]["status"] == "pass"


def test_ops_kpi_readiness_can_enforce_sample_minimums(client, normal_user_token, db):
    now = datetime.now()

    dev = Device(
        name="ops-kpi-sample-dev",
        ip_address="10.251.0.10",
        device_type="cisco_ios",
        status="online",
    )
    db.add(dev)
    db.flush()

    job = DiscoveryJob(
        cidr="10.251.0.0/24",
        status="completed",
        logs="done",
        created_at=now - timedelta(seconds=160),
    )
    db.add(job)
    db.flush()

    db.add_all(
        [
            DiscoveredDevice(job_id=int(job.id), ip_address="10.251.0.11", status="approved", snmp_status="reachable"),
            DiscoveredDevice(job_id=int(job.id), ip_address="10.251.0.12", status="approved", snmp_status="reachable"),
        ]
    )
    db.add(
        TopologySnapshot(
            site_id=None,
            job_id=int(job.id),
            label="ops-kpi-sample-map",
            node_count=1,
            link_count=0,
            nodes_json="[]",
            links_json="[]",
            metadata_json="{}",
            created_at=now - timedelta(seconds=90),
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
                    "approval_id": 777,
                    "execution_id": "sample-exec-1",
                    "post_check_failed": False,
                    "rollback_attempted": False,
                    "rollback_success": False,
                    "rollback_duration_ms": None,
                    "failure_cause": None,
                }
            ),
            source="Compliance",
            timestamp=now - timedelta(minutes=10),
        )
    )
    db.add(
        EventLog(
            device_id=None,
            severity="info",
            event_id="NORTHBOUND_WEBHOOK_DELIVERY",
            message=json.dumps(
                {
                    "status": "ok",
                    "mode": "jira",
                    "event_type": "issue",
                    "attempts": 1,
                    "status_code": 201,
                    "failure_cause": None,
                }
            ),
            source="Northbound",
            timestamp=now - timedelta(minutes=9),
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
                    "triggered": 1,
                    "executed": 1,
                    "blocked": 0,
                    "approvals_opened": 0,
                }
            ),
            source="ClosedLoop",
            timestamp=now - timedelta(minutes=8),
        )
    )
    db.add(
        Issue(
            device_id=int(dev.id),
            title="latency high",
            description="auto-created",
            severity="warning",
            status="resolved",
            category="performance",
            is_read=False,
            created_at=now - timedelta(seconds=120),
            resolved_at=now - timedelta(seconds=60),
        )
    )
    db.commit()

    res = client.get(
        "/api/v1/ops/kpi/readiness",
        params={
            "discovery_days": 30,
            "require_sample_minimums": True,
            "sample_min_discovery_jobs": 2,
            "sample_min_change_events": 2,
            "sample_min_northbound_deliveries": 2,
            "sample_min_autonomy_issues_created": 2,
            "sample_min_autonomy_actions_executed": 2,
        },
        headers=normal_user_token,
    )
    assert res.status_code == 200
    payload = _unwrap(res.json())

    evidence = payload.get("evidence") or {}
    assert evidence.get("sample_minimums_enforced") is True

    checks = {str(row.get("id") or ""): row for row in list(payload.get("checks") or [])}
    assert checks["sample.discovery.jobs_count"]["status"] == "fail"
    assert checks["sample.change.events"]["status"] == "fail"
    assert checks["sample.northbound.deliveries"]["status"] == "fail"
    assert checks["sample.autonomy.issues_created"]["status"] == "fail"
    assert checks["sample.autonomy.actions_executed"]["status"] == "fail"


def test_ops_kpi_readiness_snapshot_and_history_api(client, admin_user_token, db):
    now = datetime.now()

    dev = Device(
        name="ops-kpi-snapshot-dev",
        ip_address="10.252.0.10",
        device_type="cisco_ios",
        status="online",
    )
    db.add(dev)
    db.flush()

    job = DiscoveryJob(
        cidr="10.252.0.0/24",
        status="completed",
        logs="done",
        created_at=now - timedelta(seconds=160),
    )
    db.add(job)
    db.flush()

    db.add_all(
        [
            DiscoveredDevice(job_id=int(job.id), ip_address="10.252.0.11", status="approved", snmp_status="reachable"),
            DiscoveredDevice(job_id=int(job.id), ip_address="10.252.0.12", status="approved", snmp_status="reachable"),
            DiscoveredDevice(job_id=int(job.id), ip_address="10.252.0.13", status="existing", snmp_status="reachable"),
        ]
    )
    db.add(
        TopologySnapshot(
            site_id=None,
            job_id=int(job.id),
            label="ops-kpi-snapshot-map",
            node_count=2,
            link_count=1,
            nodes_json="[]",
            links_json="[]",
            metadata_json="{}",
            created_at=now - timedelta(seconds=80),
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
                    "approval_id": 888,
                    "execution_id": "snapshot-exec-1",
                    "post_check_failed": False,
                    "rollback_attempted": False,
                    "rollback_success": False,
                    "rollback_duration_ms": None,
                    "failure_cause": None,
                }
            ),
            source="Compliance",
            timestamp=now - timedelta(minutes=8),
        )
    )
    db.add(
        EventLog(
            device_id=None,
            severity="info",
            event_id="NORTHBOUND_WEBHOOK_DELIVERY",
            message=json.dumps(
                {
                    "status": "ok",
                    "mode": "jira",
                    "event_type": "issue",
                    "attempts": 1,
                    "status_code": 201,
                    "failure_cause": None,
                }
            ),
            source="Northbound",
            timestamp=now - timedelta(minutes=7),
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
                    "triggered": 1,
                    "executed": 1,
                    "blocked": 0,
                    "approvals_opened": 0,
                }
            ),
            source="ClosedLoop",
            timestamp=now - timedelta(minutes=6),
        )
    )
    db.add(
        Issue(
            device_id=int(dev.id),
            title="cpu high",
            description="auto-created",
            severity="warning",
            status="resolved",
            category="performance",
            is_read=False,
            created_at=now - timedelta(seconds=140),
            resolved_at=now - timedelta(seconds=70),
        )
    )
    db.commit()

    snapshot = client.post(
        "/api/v1/ops/kpi/readiness/snapshot",
        params={"require_sample_minimums": False},
        headers=admin_user_token,
    )
    assert snapshot.status_code == 200
    snap_payload = _unwrap(snapshot.json())
    assert isinstance(snap_payload.get("snapshot"), dict)
    assert snap_payload["snapshot"]["event_id"] == "OPS_KPI_READINESS_SNAPSHOT"
    assert int(snap_payload["snapshot"]["event_log_id"]) > 0
    assert isinstance((snap_payload["snapshot"]["payload"] or {}).get("checks"), list)
    assert isinstance((((snap_payload["snapshot"]["payload"] or {}).get("evidence") or {}).get("sample_coverage")), dict)

    old_payload = {
        "generated_at": int((now - timedelta(days=1)).timestamp()),
        "scope": {
            "site_id": None,
            "discovery_days": 30,
            "discovery_limit": 300,
            "require_sample_minimums": True,
        },
        "readiness": {
            "status": "warning",
            "required_checks_total": 3,
            "pass_count": 1,
            "fail_count": 1,
            "unknown_count": 1,
        },
        "checks": [
            {
                "id": "plug_scan.auto_reflection_rate_pct",
                "title": "Plug & Scan auto reflection rate",
                "status": "fail",
                "required": True,
                "value": 55.0,
                "threshold": 75.0,
                "operator": ">=",
                "source": "discovery.kpi.summary",
            },
            {
                "id": "change.success_rate_pct",
                "title": "Change success rate",
                "status": "pass",
                "required": True,
                "value": 99.0,
                "threshold": 98.0,
                "operator": ">=",
                "source": "sdn.dashboard.stats.change_kpi",
            },
            {
                "id": "change.rollback_p95_ms",
                "title": "Change rollback P95",
                "status": "unknown",
                "required": True,
                "value": None,
                "threshold": 180000,
                "operator": "<=",
                "source": "sdn.dashboard.stats.change_kpi",
            },
        ],
        "evidence": {
            "sample_minimums_enforced": True,
            "sample_totals": {
                "discovery_jobs": 10,
                "change_events": 10,
                "northbound_deliveries": 2,
                "autonomy_issues_created": 1,
                "autonomy_actions_executed": 1,
            },
            "sample_thresholds": {
                "discovery_jobs": 30,
                "change_events": 60,
                "northbound_deliveries": 500,
                "autonomy_issues_created": 20,
                "autonomy_actions_executed": 20,
            },
        },
    }
    seeded = ops_endpoint.persist_kpi_readiness_snapshot(
        db,
        old_payload,
        source="OpsKPI.Test",
        run_type="seed_history",
        commit=False,
    )
    seeded_row = db.query(EventLog).filter(EventLog.id == int(seeded["event_log_id"])).first()
    assert seeded_row is not None
    seeded_row.timestamp = now - timedelta(days=1)
    db.commit()

    history = client.get(
        "/api/v1/ops/kpi/readiness/history",
        params={"days": 30, "limit": 10},
        headers=admin_user_token,
    )
    assert history.status_code == 200
    hist_payload = _unwrap(history.json())
    assert int((hist_payload.get("totals") or {}).get("count") or 0) >= 1
    assert isinstance(hist_payload.get("items"), list)
    assert len(hist_payload["items"]) >= 1
    assert str(hist_payload["items"][0].get("run_type") or "") in {"manual_api", "daily_scheduler"}
    assert isinstance(hist_payload["items"][0].get("checks"), list)
    assert isinstance(((hist_payload["items"][0].get("evidence") or {}).get("sample_coverage")), dict)
    assert hist_payload.get("previous") is not None
    assert isinstance(hist_payload.get("coverage"), dict)
    assert hist_payload["coverage"]["days_with_snapshots"] >= 1
    assert isinstance(hist_payload.get("comparison"), dict)
    assert hist_payload["comparison"]["available"] is True
    assert hist_payload["comparison"]["status_direction"] in {"stable", "improved", "regressed"}
    assert isinstance(hist_payload.get("top_failing_checks"), list)
    assert any(int(row.get("fail_count") or 0) >= 1 for row in hist_payload["top_failing_checks"])
    assert isinstance(hist_payload.get("top_unknown_checks"), list)
    assert any(int(row.get("unknown_count") or 0) >= 1 for row in hist_payload["top_unknown_checks"])
    previous_checks = {str(row.get("id") or ""): row for row in list((hist_payload.get("previous") or {}).get("checks") or [])}
    assert previous_checks["plug_scan.auto_reflection_rate_pct"]["status"] == "fail"
    assert previous_checks["change.rollback_p95_ms"]["status"] == "unknown"
