import io
import json
import zipfile
from datetime import datetime, timezone

from app.api.v1.endpoints import ops as ops_endpoint

from app.models.device import Device, Issue
from app.models.operation_action import OperationAction
from app.models.settings import SystemSetting
from app.services import operations_review_package_service as operations_review_service
from app.services import support_bundle_service


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_ops_release_evidence_endpoint_returns_summary(client, normal_user_token, monkeypatch, db):
    db.add_all(
        [
            SystemSetting(key="release_evidence_refresh_enabled", value="true", description="x", category="ops"),
            SystemSetting(key="release_evidence_refresh_profile", value="release", description="x", category="ops"),
            SystemSetting(key="release_evidence_refresh_include_synthetic", value="true", description="x", category="ops"),
            SystemSetting(key="release_evidence_refresh_include_northbound_probe", value="true", description="x", category="ops"),
        ]
    )
    db.commit()

    monkeypatch.setattr(
        ops_endpoint,
        "get_release_evidence_snapshot",
        lambda refresh=False: {
            "generated_at": "2026-03-08T14:00:00+00:00",
            "source": "cache",
            "summary": {
                "overall_status": "warning",
                "accepted_gates": 2,
                "available_gates": 4,
                "total_gates": 4,
                "blocking_gates": [],
                "warning_gates": ["vendor_support"],
                "in_progress_gates": ["northbound_soak"],
            },
            "sections": {
                "kpi_readiness": {"id": "kpi_readiness", "status": "healthy", "accepted": True, "available": True},
                "vendor_support": {"id": "vendor_support", "status": "warning", "accepted": False, "available": True},
                "synthetic_validation": {"id": "synthetic_validation", "status": "healthy", "accepted": True, "available": True},
                "northbound_soak": {"id": "northbound_soak", "status": "in_progress", "accepted": False, "available": True},
            },
        },
    )
    monkeypatch.setattr(
        ops_endpoint,
        "get_release_evidence_refresh_status",
        lambda: {
            "status": "idle",
            "stage": "idle",
            "last_success_at": "2026-03-08T14:05:00+00:00",
        },
    )
    monkeypatch.setattr(
        ops_endpoint,
        "get_release_evidence_northbound_probe_runtime",
        lambda: {
            "auth_configured": True,
            "auth_mode": "token",
            "direct_mode_available": True,
            "execution_mode": "api",
            "base_url": "http://localhost:8000",
            "latest_probe_available": True,
        },
    )

    res = client.get("/api/v1/ops/release-evidence", headers=normal_user_token)

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["source"] == "cache"
    assert payload["summary"]["overall_status"] == "warning"
    assert payload["sections"]["northbound_soak"]["status"] == "in_progress"
    assert payload["refresh"]["status"] == "idle"
    assert payload["automation"]["enabled"] is True
    assert payload["automation"]["profile"] == "release"
    assert payload["automation"]["include_synthetic"] is True
    assert payload["automation"]["include_northbound_probe"] is True
    assert payload["automation"]["northbound_probe"]["auth_configured"] is True
    assert payload["automation"]["northbound_probe"]["execution_mode"] == "api"
    assert payload["automation"]["schedule"]["cadence"] == "daily"
    assert payload["automation"]["next_run_at"] is not None


def test_ops_release_evidence_refresh_starts_job(client, operator_user_token, monkeypatch):
    monkeypatch.setattr(
        ops_endpoint,
        "start_release_evidence_refresh",
        lambda profile="ci", include_synthetic=True, trigger_source="api": {
            "started": True,
            "reason": "started",
            "refresh": {
                "status": "queued",
                "stage": "synthetic_validation",
                "profile": profile,
                "include_synthetic": include_synthetic,
            },
        },
    )

    res = client.post("/api/v1/ops/release-evidence/refresh", headers=operator_user_token)

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["started"] is True
    assert payload["refresh"]["stage"] == "synthetic_validation"


def test_ops_release_evidence_bundle_downloads_zip(client, normal_user_token, monkeypatch):
    monkeypatch.setattr(ops_endpoint, "build_release_evidence_bundle", lambda refresh=False: b"zip-bytes")

    res = client.get("/api/v1/ops/release-evidence/bundle", headers=normal_user_token)

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/zip")
    assert "release_evidence_bundle_" in res.headers.get("content-disposition", "")
    assert res.content == b"zip-bytes"


def test_ops_pro_operator_package_downloads_zip(client, operator_user_token, monkeypatch):
    monkeypatch.setattr(ops_endpoint, "build_pro_operator_package", lambda *args, **kwargs: b"pro-package")

    res = client.get("/api/v1/ops/pro/operator-package", headers=operator_user_token)

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/zip")
    assert "pro_operator_package_" in res.headers.get("content-disposition", "")
    assert res.content == b"pro-package"


def test_ops_operations_review_bundle_downloads_zip(client, operator_user_token, monkeypatch):
    monkeypatch.setattr(ops_endpoint, "build_operations_review_bundle", lambda *args, **kwargs: b"ops-review")

    res = client.get("/api/v1/ops/operations-review-bundle", headers=operator_user_token)

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/zip")
    assert "operations_review_bundle_" in res.headers.get("content-disposition", "")
    assert res.content == b"ops-review"


def test_operations_review_snapshot_includes_follow_up_agenda(monkeypatch, db):
    device = Device(
        name="svc-core-1",
        hostname="svc-core-1",
        ip_address="10.90.0.10",
        status="online",
        device_type="cisco_ios",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    issue = Issue(
        device_id=int(device.id),
        title="Service uplink packet loss",
        description="Packet loss is impacting the core uplink.",
        severity="critical",
        category="performance",
        status="active",
    )
    db.add(issue)
    db.commit()
    db.refresh(issue)

    action = OperationAction(
        issue_id=int(issue.id),
        device_id=int(device.id),
        source_type="issue",
        title="Investigate uplink degradation",
        summary="Check the uplink optics and counters.",
        severity="critical",
        status="investigating",
        assignee_name="NOC-1",
        latest_note="Optics counters review in progress.",
        created_by="operator",
        updated_by="operator",
        timeline=[],
    )
    db.add(action)
    db.commit()

    monkeypatch.setattr(
        operations_review_service.PreventiveCheckService,
        "build_summary",
        lambda _db: {"templates_total": 1, "recent_runs_total": 0},
    )
    monkeypatch.setattr(
        operations_review_service.PreventiveCheckService,
        "list_runs",
        lambda _db, limit=6: [],
    )
    monkeypatch.setattr(
        operations_review_service.ServiceGroupService,
        "list_groups",
        lambda _db: [],
    )
    monkeypatch.setattr(
        operations_review_service.ServiceGroupService,
        "build_issue_service_impact_summary_map",
        lambda _db, issues: {
            int(item.id): {
                "count": 1,
                "primary_name": "민원 서비스",
                "highest_criticality": "high",
                "matched_member_count": 2,
            }
            for item in issues
        },
    )
    monkeypatch.setattr(
        operations_review_service.KnownErrorService,
        "build_issue_summary_map",
        lambda _db, issues, limit=3: {int(item.id): {"recommendation_count": 0, "top_title": None} for item in issues},
    )
    monkeypatch.setattr(
        operations_review_service.IssueSopService,
        "build_issue_summary_map",
        lambda _db, issues: {
            int(item.id): {
                "available": True,
                "readiness_status": "limited_context",
                "step_count": 3,
                "primary_title": "Service uplink packet loss",
                "active_action_count": 1,
                "knowledge_match_count": 0,
            }
            for item in issues
        },
    )
    monkeypatch.setattr(
        operations_review_service,
        "get_release_evidence_snapshot",
        lambda refresh=False: {"summary": {"overall_status": "healthy"}, "sections": {}},
    )
    monkeypatch.setattr(
        operations_review_service.StateHistoryService,
        "build_review_summary",
        lambda _db, limit=12: {
            "snapshot_count": 2,
            "latest_snapshot": {
                "event_log_id": 21,
                "label": "Weekly review baseline",
                "generated_at": "2026-03-21T09:00:00+00:00",
                "age_hours": 2.5,
            },
            "latest_compare": {
                "result": "review",
                "changed_cards": 1,
                "improved_cards": 0,
                "review_cards": 2,
                "steady_cards": 3,
                "baseline_label": "Weekly review baseline",
                "current_label": "Current state",
            },
            "review_hotspots": [
                {
                    "key": "operations_pressure",
                    "title": "Operations Pressure",
                    "status": "review",
                    "tone": "warn",
                    "delta": "pressure +1",
                    "recommendation": "Investigate rising issue pressure before handoff.",
                }
            ],
        },
    )

    snapshot = operations_review_service.build_operations_review_snapshot(db)

    follow_up = snapshot.get("follow_up_agenda") or {}
    summary = follow_up.get("summary") or {}
    items = list(follow_up.get("items") or [])
    state_history = snapshot.get("state_history") or {}
    assert int(summary.get("needs_knowledge") or 0) == 1
    assert len(items) == 1
    assert items[0]["recommended_step"] == "capture_knowledge"
    assert items[0]["priority"] == "elevated"
    assert int(state_history.get("snapshot_count") or 0) == 2
    assert (state_history.get("latest_compare") or {}).get("result") == "review"


def test_operations_review_bundle_serializes_nested_datetimes(monkeypatch, db):
    monkeypatch.setattr(
        operations_review_service,
        "build_operations_review_snapshot",
        lambda _db, refresh_release_evidence=False: {
            "generated_at": "2026-03-21T15:00:00+00:00",
            "state_history": {
                "latest_snapshot": {
                    "generated_at": datetime(2026, 3, 21, 15, 0, tzinfo=timezone.utc),
                }
            },
        },
    )
    monkeypatch.setattr(
        operations_review_service,
        "build_operations_review_markdown",
        lambda snapshot: "# Operations Review\n",
    )
    monkeypatch.setattr(
        operations_review_service,
        "build_operations_review_pdf",
        lambda snapshot: b"%PDF-1.4\n",
    )

    bundle = operations_review_service.build_operations_review_bundle(db)

    with zipfile.ZipFile(io.BytesIO(bundle), mode="r") as zf:
        payload = json.loads(zf.read("operations_review.json").decode("utf-8"))
    assert payload["state_history"]["latest_snapshot"]["generated_at"].startswith("2026-03-21T15:00:00")


def test_support_bundle_build_zip_serializes_datetime_metadata(monkeypatch, db):
    monkeypatch.setattr(
        support_bundle_service.LicenseService,
        "get_status",
        lambda _db: {
            "installed": True,
            "expiration": datetime(2026, 4, 1, 9, 30, tzinfo=timezone.utc),
        },
    )

    bundle = support_bundle_service.SupportBundleService.build_zip(db, include_app_log=False)

    with zipfile.ZipFile(io.BytesIO(bundle), mode="r") as zf:
        meta = json.loads(zf.read("meta.json").decode("utf-8"))
    assert meta["license"]["expiration"].startswith("2026-04-01T09:30:00")
