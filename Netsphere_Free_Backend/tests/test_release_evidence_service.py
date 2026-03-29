import json
import io
import sys
import types
import zipfile

from app.services import release_evidence_service as svc


def test_build_release_evidence_summary_reads_latest_reports(tmp_path, monkeypatch):
    kpi_path = tmp_path / "kpi.json"
    vendor_path = tmp_path / "vendor.json"
    synthetic_path = tmp_path / "synthetic.json"
    northbound_path = tmp_path / "northbound.json"

    kpi_path.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-03-08 12:00:00",
                "payload": {
                    "readiness": {
                        "status": "warning",
                        "required_checks_total": 18,
                        "pass_count": 12,
                        "fail_count": 4,
                        "unknown_count": 2,
                    },
                    "evidence": {
                        "sample_totals": {
                            "discovery_jobs": 20,
                            "change_events": 72,
                        },
                        "sample_thresholds": {
                            "discovery_jobs": 30,
                            "change_events": 60,
                        },
                    },
                    "checks": [
                        {
                            "id": "plug_scan.auto_reflection_rate_pct",
                            "title": "Plug & Scan auto reflection rate",
                            "status": "fail",
                            "required": True,
                            "value": 61.2,
                            "threshold": 75.0,
                            "operator": ">=",
                            "source": "discovery.kpi.summary",
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
                },
            }
        ),
        encoding="utf-8",
    )
    vendor_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-08T13:13:44+00:00",
                "summary": {
                    "total_supported_device_types": 49,
                    "covered_device_types": 49,
                    "coverage_pct": 100.0,
                    "readiness": {"full": 15, "extended": 1, "basic": 28, "partial": 5, "none": 0},
                },
                "rows": [
                    {
                        "device_type": "cisco_ios",
                        "readiness": "partial",
                        "readiness_score": 40,
                        "by_type": {"neighbors": {"total": 2, "passed": 2, "failed": 0}},
                        "driver_modes": ["generic"],
                        "fixture_groups": ["default"],
                    },
                    {
                        "device_type": "aruba_os",
                        "readiness": "full",
                        "readiness_score": 100,
                        "by_type": {"facts": {"total": 1, "passed": 1, "failed": 0}},
                        "driver_modes": ["generic", "manager"],
                        "fixture_groups": ["default", "global_switch"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    synthetic_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-08T13:25:47+00:00",
                "profile": "ci",
                "scenario_catalog": {
                    "scenarios": [
                        {
                            "name": "security_incident",
                            "counts": {"devices": 72, "links": 100, "events": 21},
                            "severities": {"critical": 21, "warning": 0},
                            "focus_areas": ["security", "policy"],
                            "protocols": ["vxlan", "lldp"],
                        }
                    ],
                    "summary": {
                        "focus_areas_present": ["security", "rollback", "hybrid"],
                        "protocols_present": ["lldp", "vxlan", "bgp"],
                    },
                    "pass": {"required_scenarios_present": True},
                },
                "manifest": {
                    "digital_twin_vendors": ["cisco", "juniper", "fortinet"],
                },
                "soak_matrix": {
                    "summary": {"max_duplicate_ratio": 0.08, "max_queue_depth": 919, "max_throughput_eps": 185.6},
                    "pass": {"all_runs_healthy": True},
                },
                "eve_plan": {
                    "first_wave_vendors": ["Juniper", "Fortinet", "Palo Alto"],
                    "pass": {"required_first_wave_vendors_present": True},
                },
                "summary": {
                    "overall_pass": True,
                    "checked_fixture_scenarios": 4,
                    "executed_soak_runs": 3,
                    "total_processed_events": 1894,
                },
            }
        ),
        encoding="utf-8",
    )
    northbound_path.write_text(
        json.dumps(
            {
                "status": "running",
                "generated_at_utc": "2026-03-05 11:03:56",
                "started_at_utc": "2026-03-04 15:55:36",
                "expected_finish_utc": "2099-03-07 15:55:36",
                "summary": {
                    "total_attempts": 574,
                    "success_rate_pct": 100.0,
                    "failure_count": 0,
                    "elapsed_seconds": 68899,
                    "remaining_seconds": 190300,
                },
                "last_record": {
                    "mode": "servicenow",
                    "http_status": 200,
                    "latency_ms": 70.13,
                    "attempts": 1,
                    "timestamp": "2026-03-05T11:03:56.081966+00:00",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        svc,
        "REPORT_SOURCE_CANDIDATES",
        {
            "kpi_readiness": (kpi_path,),
            "vendor_support": (vendor_path,),
            "synthetic_validation": (synthetic_path,),
            "northbound_soak": (northbound_path,),
            "northbound_probe": tuple(),
        },
    )
    monkeypatch.setattr(
        svc,
        "_build_discovery_hinting_section",
        lambda: {
            "id": "discovery_hinting",
            "title": "Discovery Hinting",
            "available": True,
            "status": "healthy",
            "accepted": True,
            "generated_at": "2026-03-08T13:40:00+00:00",
            "source_path": "runtime:discovery_hinting",
            "source_name": "runtime discovery hinting",
            "summary": "12/14 successful hints",
            "active_rules": 4,
            "total_rules": 4,
            "success_count": 12,
            "total_events": 14,
            "false_positive_count": 1,
            "unknown_after_hint": 1,
            "success_rate_pct": 85.71,
            "false_positive_rate_pct": 7.14,
            "details": {
                "sync": {
                    "enabled": True,
                    "rule_version": "v2",
                    "last_pull_status": "ok:v2",
                    "last_push_status": "ok:14",
                },
                "benchmark": {
                    "total": 14,
                    "success": 12,
                    "false_positive": 1,
                    "unknown_after_hint": 1,
                    "success_rate_pct": 85.71,
                    "false_positive_rate_pct": 7.14,
                },
                "top_vendors": [{"vendor": "dasan", "total": 5, "success": 5, "false_positive": 0, "success_rate_pct": 100.0}],
                "top_drivers": [{"driver": "dasan_nos", "total": 5, "success": 5, "success_rate_pct": 100.0}],
            },
        },
    )

    payload = svc.build_release_evidence_summary()

    assert payload["summary"]["overall_status"] == "warning"
    assert payload["summary"]["accepted_gates"] == 2
    assert payload["summary"]["in_progress_gates"] == ["northbound_soak"]
    assert payload["sections"]["kpi_readiness"]["status"] == "warning"
    assert payload["sections"]["kpi_readiness"]["sample_coverage"]["met_count"] == 1
    assert payload["sections"]["kpi_readiness"]["details"]["blocking_checks"][0]["id"] == "plug_scan.auto_reflection_rate_pct"
    assert payload["sections"]["kpi_readiness"]["details"]["sample_gaps"][0]["id"] == "discovery_jobs"
    assert payload["sections"]["vendor_support"]["status"] == "warning"
    assert payload["sections"]["discovery_hinting"]["accepted"] is True
    assert payload["sections"]["discovery_hinting"]["active_rules"] == 4
    assert payload["sections"]["vendor_support"]["details"]["weakest_device_types"][0]["device_type"] == "cisco_ios"
    assert payload["sections"]["synthetic_validation"]["accepted"] is True
    assert payload["sections"]["synthetic_validation"]["details"]["scenarios"][0]["name"] == "security_incident"
    assert payload["sections"]["synthetic_validation"]["details"]["scenarios"][0]["focus_areas"] == ["security", "policy"]
    assert payload["sections"]["synthetic_validation"]["details"]["focus_areas"] == ["security", "rollback", "hybrid"]
    assert payload["sections"]["synthetic_validation"]["details"]["digital_twin_vendors"] == ["cisco", "juniper", "fortinet"]
    assert payload["sections"]["northbound_soak"]["status"] == "in_progress"
    assert payload["sections"]["northbound_soak"]["details"]["last_record"]["mode"] == "servicenow"


def test_build_release_evidence_summary_marks_stale_running_northbound_soak_warning(tmp_path, monkeypatch):
    northbound_path = tmp_path / "northbound.json"
    northbound_path.write_text(
        json.dumps(
            {
                "status": "running",
                "generated_at_utc": "2026-03-05 11:03:56",
                "started_at_utc": "2026-03-04 15:55:36",
                "expected_finish_utc": "2026-03-07 15:55:36",
                "summary": {
                    "total_attempts": 574,
                    "success_rate_pct": 100.0,
                    "failure_count": 0,
                    "elapsed_seconds": 68899,
                    "remaining_seconds": 190300,
                },
                "last_record": {
                    "mode": "servicenow",
                    "http_status": 200,
                    "latency_ms": 70.13,
                    "attempts": 1,
                    "timestamp": "2026-03-05T11:03:56.081966+00:00",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        svc,
        "REPORT_SOURCE_CANDIDATES",
        {
            "kpi_readiness": tuple(),
            "vendor_support": tuple(),
            "synthetic_validation": tuple(),
            "northbound_soak": (northbound_path,),
            "northbound_probe": tuple(),
        },
    )
    monkeypatch.setattr(svc, "_utc_now", lambda: svc.datetime(2026, 3, 9, 0, 0, 0, tzinfo=svc.timezone.utc))

    payload = svc.build_release_evidence_summary()

    section = payload["sections"]["northbound_soak"]
    assert section["status"] == "warning"
    assert section["summary"] == "stale_running"
    assert section["stale"] is True
    assert section["remaining_seconds"] == 0
    assert section["details"]["window"]["stale"] is True
    assert section["details"]["window"]["stale_seconds"] == 115464


def test_build_release_evidence_summary_uses_probe_when_only_probe_exists(tmp_path, monkeypatch):
    probe_path = tmp_path / "northbound-probe.json"
    probe_path.write_text(
        json.dumps(
            {
                "status": "pass",
                "generated_at_utc": "2026-03-09 00:00:00",
                "summary": {
                    "duration_seconds": 18,
                    "total_attempts": 10,
                    "success_rate_pct": 100.0,
                    "failure_count": 0,
                },
                "last_record": {
                    "mode": "jira",
                    "http_status": 200,
                    "latency_ms": 31.5,
                    "attempts": 1,
                    "timestamp": "2026-03-09T00:00:00+00:00",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        svc,
        "REPORT_SOURCE_CANDIDATES",
        {
            "kpi_readiness": tuple(),
            "vendor_support": tuple(),
            "synthetic_validation": tuple(),
            "northbound_soak": tuple(),
            "northbound_probe": (probe_path,),
        },
    )

    payload = svc.build_release_evidence_summary()

    section = payload["sections"]["northbound_soak"]
    assert section["status"] == "warning"
    assert section["summary"] == "probe_only"
    assert section["accepted"] is False
    assert section["details"]["probe"]["status"] == "healthy"
    assert section["details"]["probe"]["summary"] == "pass"


def test_build_release_evidence_summary_attaches_probe_to_stale_72h_report(tmp_path, monkeypatch):
    northbound_path = tmp_path / "northbound.json"
    probe_path = tmp_path / "northbound-probe.json"
    northbound_path.write_text(
        json.dumps(
            {
                "status": "running",
                "generated_at_utc": "2026-03-05 11:03:56",
                "started_at_utc": "2026-03-04 15:55:36",
                "expected_finish_utc": "2026-03-07 15:55:36",
                "summary": {
                    "total_attempts": 574,
                    "success_rate_pct": 100.0,
                    "failure_count": 0,
                    "elapsed_seconds": 68899,
                    "remaining_seconds": 190300,
                },
            }
        ),
        encoding="utf-8",
    )
    probe_path.write_text(
        json.dumps(
            {
                "status": "pass",
                "generated_at_utc": "2026-03-09 00:00:00",
                "summary": {
                    "duration_seconds": 18,
                    "total_attempts": 10,
                    "success_rate_pct": 100.0,
                    "failure_count": 0,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        svc,
        "REPORT_SOURCE_CANDIDATES",
        {
            "kpi_readiness": tuple(),
            "vendor_support": tuple(),
            "synthetic_validation": tuple(),
            "northbound_soak": (northbound_path,),
            "northbound_probe": (probe_path,),
        },
    )
    monkeypatch.setattr(svc, "_utc_now", lambda: svc.datetime(2026, 3, 9, 0, 0, 0, tzinfo=svc.timezone.utc))

    payload = svc.build_release_evidence_summary()

    section = payload["sections"]["northbound_soak"]
    assert section["status"] == "warning"
    assert section["summary"] == "stale_running_probe_healthy"
    assert section["details"]["probe"]["summary"] == "pass"


def test_build_discovery_hinting_section_uses_runtime_summary(monkeypatch):
    class _DummyDb:
        def close(self):
            return None

    class _DummySyncService:
        @staticmethod
        def build_status_summary(db, benchmark_limit=250):
            assert benchmark_limit == 250
            return {
                "sync": {
                    "enabled": True,
                    "rule_version": "v7",
                    "last_pull_at": "2026-03-09T00:01:00+00:00",
                    "last_push_at": "2026-03-09T00:02:00+00:00",
                    "last_pull_status": "ok:v7",
                    "last_push_status": "ok:3",
                    "pull_interval_seconds": 1800,
                    "push_interval_seconds": 300,
                },
                "rules": {"total": 3, "active": 2, "version": "v7"},
                "benchmark": {
                    "summary": {
                        "total": 3,
                        "success": 3,
                        "false_positive": 0,
                        "unknown_after_hint": 0,
                        "success_rate_pct": 100.0,
                        "false_positive_rate_pct": 0.0,
                    },
                    "by_vendor": [{"vendor": "dasan", "total": 3, "success": 3, "false_positive": 0, "success_rate_pct": 100.0}],
                    "by_driver": [{"driver": "dasan_nos", "total": 3, "success": 3, "success_rate_pct": 100.0}],
                },
            }

    monkeypatch.setattr(svc, "SessionLocal", lambda: _DummyDb())
    monkeypatch.setitem(
        sys.modules,
        "app.services.discovery_hint_sync_service",
        types.SimpleNamespace(DiscoveryHintSyncService=_DummySyncService),
    )

    section = svc._build_discovery_hinting_section()

    assert section["available"] is True
    assert section["status"] == "healthy"
    assert section["accepted"] is True
    assert section["active_rules"] == 2
    assert section["success_rate_pct"] == 100.0
    assert section["details"]["top_vendors"][0]["vendor"] == "dasan"


def test_get_release_evidence_snapshot_uses_cache_when_present(tmp_path, monkeypatch):
    cache_path = tmp_path / "release-evidence.latest.json"
    cache_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-08T14:00:00+00:00",
                "summary": {"overall_status": "healthy", "accepted_gates": 4, "available_gates": 4, "total_gates": 4},
                "sections": {},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(svc, "RELEASE_EVIDENCE_CACHE_PATH", cache_path)

    payload = svc.get_release_evidence_snapshot(refresh=False)

    assert payload["source"] == "cache"
    assert payload["summary"]["overall_status"] == "healthy"


def test_build_release_evidence_bundle_includes_cached_reports_and_runbooks(tmp_path, monkeypatch):
    cache_dir = tmp_path / "reports_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    runbooks_dir = cache_dir / "runbooks"
    runbooks_dir.mkdir(parents=True, exist_ok=True)

    release_cache = cache_dir / "release-evidence.latest.json"
    release_cache.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-08T14:00:00+00:00",
                "summary": {"overall_status": "warning", "accepted_gates": 1, "available_gates": 4, "total_gates": 4},
                "sections": {},
            }
        ),
        encoding="utf-8",
    )
    (cache_dir / "kpi-readiness-30d-latest.json").write_text("{}", encoding="utf-8")
    (cache_dir / "kpi-readiness-30d-latest.md").write_text("# KPI\n", encoding="utf-8")
    (runbooks_dir / "KPI_READINESS_RUNBOOK.md").write_text("# Runbook\n", encoding="utf-8")

    monkeypatch.setattr(svc, "REPORT_CACHE_DIR", cache_dir)
    monkeypatch.setattr(svc, "RUNBOOK_CACHE_DIR", runbooks_dir)
    monkeypatch.setattr(svc, "RELEASE_EVIDENCE_CACHE_PATH", release_cache)
    monkeypatch.setattr(svc, "mirror_release_evidence_assets", lambda: {"reports": [], "runbooks": []})
    monkeypatch.setattr(
        svc,
        "get_release_evidence_snapshot",
        lambda refresh=False: {
            "generated_at": "2026-03-08T14:00:00+00:00",
            "source": "cache",
            "summary": {"overall_status": "warning", "accepted_gates": 1, "available_gates": 4, "total_gates": 4},
            "sections": {},
        },
    )

    bundle = svc.build_release_evidence_bundle(refresh=False)

    with zipfile.ZipFile(io.BytesIO(bundle), mode="r") as zf:
        names = set(zf.namelist())
        assert "manifest.json" in names
        assert "release-evidence.latest.json" in names
        assert "reports/kpi-readiness-30d-latest.json" in names
        assert "reports/kpi-readiness-30d-latest.md" in names
        assert "runbooks/KPI_READINESS_RUNBOOK.md" in names


def test_run_release_evidence_refresh_runs_steps_and_returns_summary(monkeypatch):
    seen: list[str] = []

    def _fake_run(cmd, *, stage, timeout_seconds=600):
        seen.append(stage)
        return {"stage": stage, "command": [str(part) for part in cmd], "output_tail": f"{stage}-ok"}

    monkeypatch.setattr(svc, "_run_refresh_command", _fake_run)
    monkeypatch.setattr(
        svc,
        "get_release_evidence_snapshot",
        lambda refresh=False: {
            "summary": {
                "overall_status": "warning",
                "accepted_gates": 1,
                "available_gates": 4,
                "total_gates": 4,
            }
        },
    )

    payload = svc.run_release_evidence_refresh(profile="ci", include_synthetic=True)

    assert seen == ["synthetic_validation", "kpi_readiness_export", "release_evidence_cache"]
    assert payload["summary"]["overall_status"] == "warning"
    assert payload["steps"][0]["stage"] == "synthetic_validation"
    assert payload["include_northbound_probe"] is False


def test_run_release_evidence_refresh_local_profile_collects_ops_kpi_samples_first(monkeypatch):
    seen: list[str] = []

    def _fake_run(cmd, *, stage, timeout_seconds=600):
        seen.append(stage)
        return {"stage": stage, "command": [str(part) for part in cmd], "output_tail": f"{stage}-ok"}

    monkeypatch.setattr(svc, "_run_refresh_command", _fake_run)
    monkeypatch.setattr(
        svc,
        "get_release_evidence_snapshot",
        lambda refresh=False: {
            "summary": {
                "overall_status": "warning",
                "accepted_gates": 2,
                "available_gates": 4,
                "total_gates": 4,
            }
        },
    )

    payload = svc.run_release_evidence_refresh(profile="local", include_synthetic=False, include_northbound_probe=False)

    assert seen == ["ops_kpi_sample_collection", "kpi_readiness_export", "release_evidence_cache"]
    assert payload["steps"][0]["stage"] == "ops_kpi_sample_collection"


def test_run_release_evidence_refresh_uses_direct_db_northbound_probe_without_auth(monkeypatch):
    seen: list[tuple[str, list[str]]] = []

    def _fake_run(cmd, *, stage, timeout_seconds=600):
        seen.append((stage, [str(part) for part in cmd]))
        return {"stage": stage, "command": [str(part) for part in cmd], "output_tail": f"{stage}-ok"}

    monkeypatch.setattr(svc, "_run_refresh_command", _fake_run)
    monkeypatch.setattr(
        svc,
        "get_release_evidence_snapshot",
        lambda refresh=False: {
            "summary": {
                "overall_status": "warning",
                "accepted_gates": 2,
                "available_gates": 4,
                "total_gates": 4,
            }
        },
    )
    monkeypatch.delenv(svc.NORTHBOUND_PROBE_TOKEN_ENV, raising=False)
    monkeypatch.delenv(svc.NORTHBOUND_PROBE_LOGIN_USERNAME_ENV, raising=False)
    monkeypatch.delenv(svc.NORTHBOUND_PROBE_LOGIN_PASSWORD_ENV, raising=False)
    monkeypatch.setattr(
        svc,
        "get_release_evidence_northbound_probe_runtime",
        lambda: {
            "auth_configured": False,
            "auth_mode": None,
            "direct_mode_available": True,
            "execution_mode": "direct_db",
            "base_url": "http://localhost:8000",
            "latest_probe_available": False,
        },
    )

    payload = svc.run_release_evidence_refresh(
        profile="ci",
        include_synthetic=False,
        include_northbound_probe=True,
    )

    assert seen[0][0] == "northbound_probe"
    assert "--direct-db" in seen[0][1]
    assert seen[1][0] == "kpi_readiness_export"
    assert seen[2][0] == "release_evidence_cache"
    assert payload["include_northbound_probe"] is True
    assert payload["steps"][0]["stage"] == "northbound_probe"
    assert payload["steps"][0].get("skipped") is not True


def test_run_release_evidence_refresh_runs_northbound_probe_when_auth_exists(monkeypatch):
    seen: list[str] = []

    def _fake_run(cmd, *, stage, timeout_seconds=600):
        seen.append(stage)
        return {"stage": stage, "command": [str(part) for part in cmd], "output_tail": f"{stage}-ok"}

    monkeypatch.setattr(svc, "_run_refresh_command", _fake_run)
    monkeypatch.setattr(
        svc,
        "get_release_evidence_snapshot",
        lambda refresh=False: {
            "summary": {
                "overall_status": "warning",
                "accepted_gates": 2,
                "available_gates": 4,
                "total_gates": 4,
            }
        },
    )
    monkeypatch.setenv(svc.NORTHBOUND_PROBE_TOKEN_ENV, "token-value")
    monkeypatch.setattr(
        svc,
        "get_release_evidence_northbound_probe_runtime",
        lambda: {
            "auth_configured": True,
            "auth_mode": "token",
            "direct_mode_available": False,
            "execution_mode": "api",
            "base_url": "http://localhost:8000",
            "latest_probe_available": False,
        },
    )

    payload = svc.run_release_evidence_refresh(
        profile="ci",
        include_synthetic=False,
        include_northbound_probe=True,
    )

    assert seen == ["northbound_probe", "kpi_readiness_export", "release_evidence_cache"]
    assert payload["steps"][0]["stage"] == "northbound_probe"
    assert payload["include_northbound_probe"] is True


def test_run_release_evidence_refresh_validates_profile():
    try:
        svc.run_release_evidence_refresh(profile="invalid-profile", include_synthetic=False)
    except ValueError as exc:
        assert "Unsupported release evidence refresh profile" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unsupported profile")
