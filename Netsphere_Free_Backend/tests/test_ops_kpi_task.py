from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import EventLog
from app.models.settings import SystemSetting
from app.models.user import User
from app.models import device as _device
from app.models import settings as _settings
from app.models import tenant as _tenant
from app.models import user as _user


def _set_setting(db, key: str, value: str):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        row = SystemSetting(key=key, value=str(value), description=key, category="ops")
    else:
        row.value = str(value)
    db.add(row)
    db.commit()
    return row


def test_daily_kpi_snapshot_task_uses_configured_sample_minimums(monkeypatch):
    from app.tasks import ops_kpi as task_mod

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(task_mod, "SessionLocal", SessionLocal)

    db = SessionLocal()
    db.add(
        User(
            username="ops-admin",
            email="ops-admin@example.com",
            hashed_password="x",
            full_name="Ops Admin",
            role="admin",
            is_active=True,
        )
    )
    db.commit()

    _set_setting(db, "ops_kpi_snapshot_enabled", "true")
    _set_setting(db, "ops_kpi_snapshot_require_sample_minimums", "true")
    _set_setting(db, "ops_kpi_snapshot_sample_min_discovery_jobs", "44")
    _set_setting(db, "ops_kpi_snapshot_sample_min_change_events", "55")
    _set_setting(db, "ops_kpi_snapshot_sample_min_northbound_deliveries", "66")
    _set_setting(db, "ops_kpi_snapshot_sample_min_autonomy_issues_created", "77")
    _set_setting(db, "ops_kpi_snapshot_sample_min_autonomy_actions_executed", "88")
    db.close()

    captured: dict[str, int | bool] = {}

    def fake_kpi_readiness(**kwargs):
        captured["sample_min_discovery_jobs"] = int(kwargs["sample_min_discovery_jobs"])
        captured["sample_min_change_events"] = int(kwargs["sample_min_change_events"])
        captured["sample_min_northbound_deliveries"] = int(kwargs["sample_min_northbound_deliveries"])
        captured["sample_min_autonomy_issues_created"] = int(kwargs["sample_min_autonomy_issues_created"])
        captured["sample_min_autonomy_actions_executed"] = int(kwargs["sample_min_autonomy_actions_executed"])
        captured["require_sample_minimums"] = bool(kwargs["require_sample_minimums"])
        return {
            "generated_at": int(datetime.now().timestamp()),
            "scope": {
                "site_id": None,
                "discovery_days": 30,
                "discovery_limit": 300,
                "require_sample_minimums": bool(kwargs["require_sample_minimums"]),
            },
            "readiness": {
                "status": "warning",
                "required_checks_total": 2,
                "pass_count": 1,
                "fail_count": 1,
                "unknown_count": 0,
            },
            "checks": [
                {
                    "id": "sample.discovery.jobs_count",
                    "title": "Sample minimum: discovery jobs",
                    "status": "fail",
                    "required": True,
                    "value": 10,
                    "threshold": int(kwargs["sample_min_discovery_jobs"]),
                    "operator": ">=",
                    "source": "ops.kpi.readiness.sample_gate",
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
            ],
            "evidence": {
                "sample_minimums_enforced": bool(kwargs["require_sample_minimums"]),
                "sample_totals": {
                    "discovery_jobs": 10,
                    "change_events": 20,
                    "northbound_deliveries": 30,
                    "autonomy_issues_created": 40,
                    "autonomy_actions_executed": 50,
                },
                "sample_thresholds": {
                    "discovery_jobs": int(kwargs["sample_min_discovery_jobs"]),
                    "change_events": int(kwargs["sample_min_change_events"]),
                    "northbound_deliveries": int(kwargs["sample_min_northbound_deliveries"]),
                    "autonomy_issues_created": int(kwargs["sample_min_autonomy_issues_created"]),
                    "autonomy_actions_executed": int(kwargs["sample_min_autonomy_actions_executed"]),
                },
            },
        }

    monkeypatch.setattr(task_mod.ops_ep, "kpi_readiness", fake_kpi_readiness)

    out = task_mod.run_daily_kpi_readiness_snapshot()
    assert out["status"] == "ok"
    assert out["require_sample_minimums"] is True
    assert out["sample_minimums"] == {
        "discovery_jobs": 44,
        "change_events": 55,
        "northbound_deliveries": 66,
        "autonomy_issues_created": 77,
        "autonomy_actions_executed": 88,
    }
    assert captured == {
        "sample_min_discovery_jobs": 44,
        "sample_min_change_events": 55,
        "sample_min_northbound_deliveries": 66,
        "sample_min_autonomy_issues_created": 77,
        "sample_min_autonomy_actions_executed": 88,
        "require_sample_minimums": True,
    }

    db = SessionLocal()
    row = db.query(EventLog).filter(EventLog.event_id == "OPS_KPI_READINESS_SNAPSHOT").first()
    assert row is not None
    payload = task_mod.ops_ep._to_json_dict(row.message)
    sample_thresholds = ((payload.get("evidence") or {}).get("sample_thresholds") or {})
    assert sample_thresholds == {
        "discovery_jobs": 44,
        "change_events": 55,
        "northbound_deliveries": 66,
        "autonomy_issues_created": 77,
        "autonomy_actions_executed": 88,
    }
    checks = list(payload.get("checks") or [])
    assert len(checks) == 2
    assert checks[0]["id"] == "sample.discovery.jobs_count"
    db.close()


def test_scheduled_release_evidence_refresh_task_uses_policy_settings(monkeypatch):
    from app.tasks import ops_kpi as task_mod

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(task_mod, "SessionLocal", SessionLocal)

    db = SessionLocal()
    _set_setting(db, "release_evidence_refresh_enabled", "true")
    _set_setting(db, "release_evidence_refresh_profile", "release")
    _set_setting(db, "release_evidence_refresh_include_synthetic", "true")
    _set_setting(db, "release_evidence_refresh_include_northbound_probe", "true")
    db.close()

    captured = {}

    def _fake_run_release_evidence_refresh_blocking(*, profile, include_synthetic, include_northbound_probe, trigger_source):
        captured["profile"] = profile
        captured["include_synthetic"] = bool(include_synthetic)
        captured["include_northbound_probe"] = bool(include_northbound_probe)
        captured["trigger_source"] = trigger_source
        return {
            "started": True,
            "reason": "completed",
            "refresh": {
                "status": "completed",
                "stage": "completed",
                "last_summary": {
                    "accepted_gates": 3,
                    "available_gates": 4,
                    "total_gates": 4,
                },
            },
        }

    monkeypatch.setattr(task_mod, "run_release_evidence_refresh_blocking", _fake_run_release_evidence_refresh_blocking)

    out = task_mod.run_scheduled_release_evidence_refresh()

    assert out == {
        "status": "ok",
        "reason": "completed",
        "profile": "release",
        "include_synthetic": True,
        "include_northbound_probe": True,
        "refresh_status": "completed",
        "stage": "completed",
        "accepted_gates": 3,
        "available_gates": 4,
        "total_gates": 4,
    }
    assert captured == {
        "profile": "release",
        "include_synthetic": True,
        "include_northbound_probe": True,
        "trigger_source": "scheduler",
    }
