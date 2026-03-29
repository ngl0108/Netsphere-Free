try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn

        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

from app.api.v1.endpoints import ops as ops_ep
from app.db.session import SessionLocal
from app.models.settings import SystemSetting
from app.models.user import User
from app.services.release_evidence_service import (
    RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE,
    RELEASE_EVIDENCE_REFRESH_ENABLED_SETTING_KEY,
    RELEASE_EVIDENCE_REFRESH_INCLUDE_NORTHBOUND_PROBE_SETTING_KEY,
    RELEASE_EVIDENCE_REFRESH_INCLUDE_SYNTHETIC_SETTING_KEY,
    RELEASE_EVIDENCE_REFRESH_PROFILE_SETTING_KEY,
    RELEASE_EVIDENCE_REFRESH_PROFILES,
    run_release_evidence_refresh_blocking,
)


def _get_setting_value(db, key: str, default):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        return default
    value = row.value
    if value is None:
        return default
    return value


def _as_bool(raw, default: bool) -> bool:
    if raw is None:
        return bool(default)
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _as_int(raw, default: int | None, minimum: int | None = None, maximum: int | None = None) -> int | None:
    if raw is None or str(raw).strip() == "":
        return default
    try:
        out = int(float(str(raw).strip()))
    except Exception:
        return default
    if minimum is not None:
        out = max(minimum, out)
    if maximum is not None:
        out = min(maximum, out)
    return out


@shared_task(name="app.tasks.ops_kpi.run_daily_kpi_readiness_snapshot")
def run_daily_kpi_readiness_snapshot():
    db = SessionLocal()
    try:
        from app.services.ha_service import HaService

        if HaService.enabled(db) and not HaService.is_active(db):
            return {"status": "skipped", "reason": "ha_standby"}

        enabled = _as_bool(_get_setting_value(db, "ops_kpi_snapshot_enabled", "true"), True)
        if not enabled:
            return {"status": "skipped", "reason": "disabled"}

        require_sample_minimums = _as_bool(
            _get_setting_value(db, "ops_kpi_snapshot_require_sample_minimums", "true"),
            True,
        )
        site_id = _as_int(_get_setting_value(db, "ops_kpi_snapshot_site_id", ""), None, minimum=1)
        discovery_days = _as_int(_get_setting_value(db, "ops_kpi_snapshot_discovery_days", "30"), 30, minimum=1, maximum=90) or 30
        discovery_limit = _as_int(_get_setting_value(db, "ops_kpi_snapshot_discovery_limit", "300"), 300, minimum=1, maximum=1000) or 300
        sample_min_discovery_jobs = _as_int(
            _get_setting_value(
                db,
                "ops_kpi_snapshot_sample_min_discovery_jobs",
                str(ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["discovery_jobs"]),
            ),
            ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["discovery_jobs"],
            minimum=1,
            maximum=100000,
        ) or ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["discovery_jobs"]
        sample_min_change_events = _as_int(
            _get_setting_value(
                db,
                "ops_kpi_snapshot_sample_min_change_events",
                str(ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["change_events"]),
            ),
            ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["change_events"],
            minimum=1,
            maximum=100000,
        ) or ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["change_events"]
        sample_min_northbound_deliveries = _as_int(
            _get_setting_value(
                db,
                "ops_kpi_snapshot_sample_min_northbound_deliveries",
                str(ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["northbound_deliveries"]),
            ),
            ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["northbound_deliveries"],
            minimum=1,
            maximum=100000,
        ) or ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["northbound_deliveries"]
        sample_min_autonomy_issues_created = _as_int(
            _get_setting_value(
                db,
                "ops_kpi_snapshot_sample_min_autonomy_issues_created",
                str(ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["autonomy_issues_created"]),
            ),
            ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["autonomy_issues_created"],
            minimum=1,
            maximum=100000,
        ) or ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["autonomy_issues_created"]
        sample_min_autonomy_actions_executed = _as_int(
            _get_setting_value(
                db,
                "ops_kpi_snapshot_sample_min_autonomy_actions_executed",
                str(ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["autonomy_actions_executed"]),
            ),
            ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["autonomy_actions_executed"],
            minimum=1,
            maximum=100000,
        ) or ops_ep.DEFAULT_KPI_SAMPLE_MINIMUMS["autonomy_actions_executed"]

        actor = (
            db.query(User)
            .filter(User.is_active == True, User.role == "admin")
            .order_by(User.id.asc())
            .first()
        )
        if not actor:
            return {"status": "skipped", "reason": "no_active_admin"}

        readiness_payload = ops_ep.kpi_readiness(
            site_id=site_id,
            discovery_days=int(discovery_days),
            discovery_limit=int(discovery_limit),
            plug_scan_first_map_p50_max_seconds=300,
            plug_scan_first_map_p95_max_seconds=900,
            plug_scan_auto_reflection_min_pct=75.0,
            plug_scan_false_positive_max_pct=10.0,
            change_success_min_pct=98.0,
            change_failure_max_pct=1.0,
            change_rollback_p95_max_ms=180000,
            change_trace_coverage_min_pct=100.0,
            autonomy_auto_action_min_pct=60.0,
            autonomy_operator_intervention_max_pct=40.0,
            autonomy_mttd_baseline_seconds=None,
            autonomy_mttr_baseline_seconds=None,
            autonomy_mttd_improvement_min_pct=30.0,
            autonomy_mttr_improvement_min_pct=40.0,
            northbound_success_min_pct=95.0,
            northbound_p95_attempts_max=3,
            northbound_failed_24h_max=5,
            require_sample_minimums=bool(require_sample_minimums),
            sample_min_discovery_jobs=int(sample_min_discovery_jobs),
            sample_min_change_events=int(sample_min_change_events),
            sample_min_northbound_deliveries=int(sample_min_northbound_deliveries),
            sample_min_autonomy_issues_created=int(sample_min_autonomy_issues_created),
            sample_min_autonomy_actions_executed=int(sample_min_autonomy_actions_executed),
            db=db,
            current_user=actor,
        )

        snapshot = ops_ep.persist_kpi_readiness_snapshot(
            db,
            readiness_payload,
            source="OpsKPI.Celery",
            run_type="daily_scheduler",
            commit=True,
        )

        readiness = readiness_payload.get("readiness") if isinstance(readiness_payload.get("readiness"), dict) else {}
        return {
            "status": "ok",
            "readiness_status": readiness.get("status"),
            "pass_count": int(readiness.get("pass_count") or 0),
            "fail_count": int(readiness.get("fail_count") or 0),
            "unknown_count": int(readiness.get("unknown_count") or 0),
            "snapshot_event_log_id": int(snapshot.get("event_log_id") or 0),
            "site_id": site_id,
            "require_sample_minimums": bool(require_sample_minimums),
            "sample_minimums": {
                "discovery_jobs": int(sample_min_discovery_jobs),
                "change_events": int(sample_min_change_events),
                "northbound_deliveries": int(sample_min_northbound_deliveries),
                "autonomy_issues_created": int(sample_min_autonomy_issues_created),
                "autonomy_actions_executed": int(sample_min_autonomy_actions_executed),
            },
        }
    except Exception as exc:
        db.rollback()
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    finally:
        db.close()


@shared_task(name="app.tasks.ops_kpi.run_scheduled_release_evidence_refresh")
def run_scheduled_release_evidence_refresh():
    db = SessionLocal()
    try:
        from app.services.ha_service import HaService

        if HaService.enabled(db) and not HaService.is_active(db):
            return {"status": "skipped", "reason": "ha_standby"}

        enabled = _as_bool(
            _get_setting_value(db, RELEASE_EVIDENCE_REFRESH_ENABLED_SETTING_KEY, "true"),
            True,
        )
        if not enabled:
            return {"status": "skipped", "reason": "disabled"}

        profile = str(
            _get_setting_value(
                db,
                RELEASE_EVIDENCE_REFRESH_PROFILE_SETTING_KEY,
                RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE,
            )
            or RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE
        ).strip().lower() or RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE
        if profile not in RELEASE_EVIDENCE_REFRESH_PROFILES:
            profile = RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE

        include_synthetic = _as_bool(
            _get_setting_value(db, RELEASE_EVIDENCE_REFRESH_INCLUDE_SYNTHETIC_SETTING_KEY, "false"),
            False,
        )
        include_northbound_probe = _as_bool(
            _get_setting_value(db, RELEASE_EVIDENCE_REFRESH_INCLUDE_NORTHBOUND_PROBE_SETTING_KEY, "false"),
            False,
        )
    finally:
        db.close()

    try:
        result = run_release_evidence_refresh_blocking(
            profile=profile,
            include_synthetic=bool(include_synthetic),
            include_northbound_probe=bool(include_northbound_probe),
            trigger_source="scheduler",
        )
    except Exception as exc:
        return {
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "profile": profile,
            "include_synthetic": bool(include_synthetic),
            "include_northbound_probe": bool(include_northbound_probe),
        }

    refresh = result.get("refresh") if isinstance(result.get("refresh"), dict) else {}
    summary = refresh.get("last_summary") if isinstance(refresh.get("last_summary"), dict) else {}
    reason = str(result.get("reason") or "").strip().lower()
    if result.get("started") is False and reason == "already_running":
        return {
            "status": "skipped",
            "reason": "already_running",
            "profile": profile,
            "include_synthetic": bool(include_synthetic),
            "include_northbound_probe": bool(include_northbound_probe),
            "refresh_status": str(refresh.get("status") or "unknown"),
            "stage": str(refresh.get("stage") or "unknown"),
        }

    return {
        "status": "ok" if str(refresh.get("status") or "").lower() == "completed" else "error",
        "reason": reason or ("completed" if str(refresh.get("status") or "").lower() == "completed" else "failed"),
        "profile": profile,
        "include_synthetic": bool(include_synthetic),
        "include_northbound_probe": bool(include_northbound_probe),
        "refresh_status": str(refresh.get("status") or "unknown"),
        "stage": str(refresh.get("stage") or "unknown"),
        "accepted_gates": int(summary.get("accepted_gates") or 0),
        "available_gates": int(summary.get("available_gates") or 0),
        "total_gates": int(summary.get("total_gates") or 0),
    }
