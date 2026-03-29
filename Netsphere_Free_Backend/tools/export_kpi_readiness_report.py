#!/usr/bin/env python
from __future__ import annotations

import argparse
import bisect
import json
import math
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import requests
from sqlalchemy import inspect as sa_inspect

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    from app.api.v1.endpoints import misc as _MISC_ENDPOINT
    from app.api.v1.endpoints import ops as _OPS_ENDPOINT
    from app.core import config as _APP_CONFIG
    from app.db.session import SessionLocal as _DIRECT_SESSION_LOCAL
    from app.models.device import Device as _DIRECT_DEVICE
    from app.models.device import EventLog as _DIRECT_EVENT_LOG
    from app.models.device import Issue as _DIRECT_ISSUE
    from app.models.settings import SystemSetting as _DIRECT_SYSTEM_SETTING
except Exception:
    _MISC_ENDPOINT = None
    _OPS_ENDPOINT = None
    _APP_CONFIG = None
    _DIRECT_SESSION_LOCAL = None
    _DIRECT_DEVICE = None
    _DIRECT_EVENT_LOG = None
    _DIRECT_ISSUE = None
    _DIRECT_SYSTEM_SETTING = None

DEFAULT_SAMPLE_MINIMUMS = {
    "sample_min_discovery_jobs": 30,
    "sample_min_change_events": 60,
    "sample_min_northbound_deliveries": 500,
    "sample_min_autonomy_issues_created": 20,
    "sample_min_autonomy_actions_executed": 20,
}


def _unwrap_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        return dict(raw.get("data") or {})
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _fmt(v: Any) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)


def _p95_int(values: list[int]) -> int | None:
    if not values:
        return None
    seq = sorted(int(v) for v in values)
    idx = min(len(seq) - 1, max(0, int(math.ceil(len(seq) * 0.95) - 1)))
    return int(seq[idx])


def _request_json(url: str, params: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
    resp = requests.get(url, params=params, headers=headers, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:400]}")
    body = resp.json()
    return _unwrap_payload(body)


def _ensure_direct_runtime() -> None:
    if (
        _OPS_ENDPOINT is None
        or _MISC_ENDPOINT is None
        or _DIRECT_SESSION_LOCAL is None
        or _DIRECT_DEVICE is None
        or _DIRECT_EVENT_LOG is None
        or _DIRECT_ISSUE is None
        or _DIRECT_SYSTEM_SETTING is None
    ):
        raise RuntimeError("direct-db mode is unavailable: backend runtime imports failed")
    if not str(os.environ.get("FIELD_ENCRYPTION_KEY") or "").strip() and not str(os.environ.get("SECRET_KEY") or "").strip():
        derived_secret = str(getattr(_APP_CONFIG, "SECRET_KEY", "") or "").strip() if _APP_CONFIG is not None else ""
        if derived_secret:
            os.environ["SECRET_KEY"] = derived_secret


def _build_direct_actor() -> Any:
    return SimpleNamespace(
        id=0,
        username="release-evidence",
        role="admin",
        is_active=True,
        full_name="Release Evidence",
        tenant_id=None,
    )


def _safe_parse_json_payload(raw: Any) -> Dict[str, Any] | None:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw or ""))
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _table_columns(db: Any, table_name: str) -> set[str]:
    try:
        inspector = sa_inspect(db.bind)
        return {str(col.get("name") or "").strip() for col in inspector.get_columns(str(table_name))}
    except Exception:
        return set()


def _direct_setting_float(db: Any, key: str, default: float) -> float:
    row = db.query(_DIRECT_SYSTEM_SETTING).filter(_DIRECT_SYSTEM_SETTING.key == str(key)).first()
    if row is None or row.value is None:
        return float(default)
    try:
        return float(str(row.value).strip())
    except Exception:
        return float(default)


def _direct_closed_loop_kpi_event(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if str(payload.get("status") or "").strip().lower() != "ok":
        return False
    if bool(payload.get("dry_run")):
        return False
    return True


def _build_lightweight_dashboard_payload(db: Any, site_id: int | None = None) -> Dict[str, Any]:
    now_dt = datetime.now()
    device_columns = _table_columns(db, "devices")
    device_query = db.query(_DIRECT_DEVICE.id)
    if site_id is not None and "site_id" in device_columns:
        device_query = device_query.filter(_DIRECT_DEVICE.site_id == int(site_id))
    target_ids = [int(getattr(row, "id", 0) or 0) for row in device_query.all() if int(getattr(row, "id", 0) or 0) > 0]

    change_min_success_rate = _direct_setting_float(db, "ops_alerts_min_change_success_rate_pct", 98.0)
    change_max_failure_rate = _direct_setting_float(db, "ops_alerts_max_change_failure_rate_pct", 1.0)
    change_max_rollback_p95_ms = _direct_setting_float(db, "ops_alerts_max_change_rollback_p95_ms", 180000.0)
    change_min_trace_coverage = _direct_setting_float(db, "ops_alerts_min_change_trace_coverage_pct", 100.0)

    change_kpi = {
        "window_days": 30,
        "status": "idle",
        "change_success_rate_pct": 100.0,
        "change_failure_rate_pct": 0.0,
        "rollback_p95_ms": None,
        "rollback_success_rate_pct": 100.0,
        "approval_execution_trace_coverage_pct": 100.0,
        "alerts": [],
        "failure_causes": [],
        "targets": {
            "min_success_rate_pct": float(change_min_success_rate),
            "max_failure_rate_pct": float(change_max_failure_rate),
            "max_rollback_p95_ms": int(change_max_rollback_p95_ms),
            "min_trace_coverage_pct": float(change_min_trace_coverage),
        },
        "totals": {
            "events": 0,
            "success": 0,
            "failed": 0,
            "post_check_failures": 0,
            "rollback_attempted": 0,
            "rollback_success": 0,
            "approval_context_events": 0,
            "approval_traced": 0,
        },
    }
    since_kpi = now_dt - timedelta(days=30)
    change_query = db.query(_DIRECT_EVENT_LOG).filter(
        _DIRECT_EVENT_LOG.event_id.in_(["CONFIG_DRIFT_REMEDIATION_KPI", "CHANGE_EXECUTION_KPI"]),
        _DIRECT_EVENT_LOG.timestamp >= since_kpi,
    )
    if site_id is not None and target_ids:
        change_query = change_query.filter(_DIRECT_EVENT_LOG.device_id.in_(target_ids))
    change_rows = change_query.limit(5000).all()
    change_payloads = [p for p in (_safe_parse_json_payload(getattr(row, "message", None)) for row in change_rows) if p]
    if change_payloads:
        durations: list[int] = []
        failure_causes: dict[str, int] = {}
        total_events = len(change_payloads)
        ok_cnt = 0
        failed_cnt = 0
        post_check_fail_cnt = 0
        rollback_attempted_cnt = 0
        rollback_success_cnt = 0
        approval_context_cnt = 0
        traced_cnt = 0
        for payload in change_payloads:
            status_text = str(payload.get("status") or "").strip().lower()
            if status_text == "ok":
                ok_cnt += 1
            else:
                failed_cnt += 1
                cause = str(payload.get("failure_cause") or "unknown").strip() or "unknown"
                failure_causes[cause] = int(failure_causes.get(cause) or 0) + 1
            if bool(payload.get("post_check_failed")):
                post_check_fail_cnt += 1
            if bool(payload.get("rollback_attempted")):
                rollback_attempted_cnt += 1
                if bool(payload.get("rollback_success")):
                    rollback_success_cnt += 1
            if bool(payload.get("post_check_failed")) and bool(payload.get("rollback_attempted")):
                try:
                    if payload.get("rollback_duration_ms") is not None:
                        durations.append(int(payload.get("rollback_duration_ms")))
                except Exception:
                    pass
            if payload.get("approval_id") is not None:
                approval_context_cnt += 1
                if str(payload.get("execution_id") or "").strip():
                    traced_cnt += 1
        rollback_p95 = None
        if durations:
            rollback_p95 = int(_p95_int(durations) or 0)
        success_rate = round((ok_cnt / total_events) * 100.0, 2) if total_events > 0 else 100.0
        failure_rate = round((failed_cnt / total_events) * 100.0, 2) if total_events > 0 else 0.0
        trace_coverage_pct = 100.0 if approval_context_cnt == 0 else round((traced_cnt / approval_context_cnt) * 100.0, 2)
        alerts = []
        if success_rate < float(change_min_success_rate):
            alerts.append({"code": "change_success_rate_low"})
        if failure_rate > float(change_max_failure_rate):
            alerts.append({"code": "change_failure_rate_high"})
        if rollback_p95 is not None and float(rollback_p95) > float(change_max_rollback_p95_ms):
            alerts.append({"code": "change_rollback_p95_high"})
        if trace_coverage_pct < float(change_min_trace_coverage):
            alerts.append({"code": "change_trace_coverage_low"})
        status = "healthy"
        if len(alerts) >= 2:
            status = "critical"
        elif alerts:
            status = "warning"
        change_kpi = {
            **change_kpi,
            "status": status,
            "change_success_rate_pct": float(success_rate),
            "change_failure_rate_pct": float(failure_rate),
            "rollback_p95_ms": rollback_p95,
            "rollback_success_rate_pct": 100.0 if rollback_attempted_cnt == 0 else round((rollback_success_cnt / rollback_attempted_cnt) * 100.0, 2),
            "approval_execution_trace_coverage_pct": float(trace_coverage_pct),
            "alerts": alerts,
            "failure_causes": sorted(
                [{"cause": key, "count": int(value)} for key, value in failure_causes.items()],
                key=lambda row: row["count"],
                reverse=True,
            )[:10],
            "totals": {
                "events": int(total_events),
                "success": int(ok_cnt),
                "failed": int(failed_cnt),
                "post_check_failures": int(post_check_fail_cnt),
                "rollback_attempted": int(rollback_attempted_cnt),
                "rollback_success": int(rollback_success_cnt),
                "approval_context_events": int(approval_context_cnt),
                "approval_traced": int(traced_cnt),
            },
        }

    since_nb = now_dt - timedelta(days=30)
    since_24h = now_dt - timedelta(hours=24)
    nb_rows = (
        db.query(_DIRECT_EVENT_LOG)
        .filter(
            _DIRECT_EVENT_LOG.event_id == "NORTHBOUND_WEBHOOK_DELIVERY",
            _DIRECT_EVENT_LOG.timestamp >= since_nb,
        )
        .order_by(_DIRECT_EVENT_LOG.timestamp.desc())
        .limit(5000)
        .all()
    )
    deliveries = 0
    success = 0
    failed = 0
    failed_24h = 0
    attempts_values: list[int] = []
    mode_counts: dict[str, int] = {}
    failure_counts: dict[str, int] = {}
    for row in nb_rows:
        payload = _safe_parse_json_payload(getattr(row, "message", None))
        if not payload:
            continue
        deliveries += 1
        status_text = str(payload.get("status") or "").strip().lower()
        if status_text == "ok":
            success += 1
        else:
            failed += 1
            if getattr(row, "timestamp", None) is not None and row.timestamp >= since_24h:
                failed_24h += 1
            cause = str(payload.get("failure_cause") or "unknown").strip().lower() or "unknown"
            failure_counts[cause] = int(failure_counts.get(cause) or 0) + 1
        try:
            attempts_values.append(max(1, int(payload.get("attempts") or 1)))
        except Exception:
            attempts_values.append(1)
        mode = str(payload.get("mode") or "generic").strip().lower() or "generic"
        mode_counts[mode] = int(mode_counts.get(mode) or 0) + 1
    northbound_success_rate = 100.0 if deliveries == 0 else round((success / deliveries) * 100.0, 2)
    northbound_p95_attempts = int(_p95_int(attempts_values) or 0) if attempts_values else 0
    northbound_status = "idle"
    if deliveries > 0:
        if northbound_success_rate < 80.0 or failed_24h > 20:
            northbound_status = "critical"
        elif northbound_success_rate < 95.0 or northbound_p95_attempts > 3 or failed_24h > 5:
            northbound_status = "warning"
        else:
            northbound_status = "healthy"
    northbound_kpi = {
        "window_days": 30,
        "status": northbound_status,
        "success_rate_pct": float(northbound_success_rate),
        "avg_attempts": round((sum(attempts_values) / len(attempts_values)), 2) if attempts_values else 0.0,
        "p95_attempts": int(northbound_p95_attempts),
        "failure_causes": sorted(
            [{"cause": key, "count": int(value)} for key, value in failure_counts.items()],
            key=lambda row: row["count"],
            reverse=True,
        )[:10],
        "modes": sorted(
            [{"mode": key, "count": int(value)} for key, value in mode_counts.items()],
            key=lambda row: row["count"],
            reverse=True,
        )[:10],
        "totals": {
            "deliveries": int(deliveries),
            "success": int(success),
            "failed": int(failed),
            "failed_24h": int(failed_24h),
        },
    }

    autonomy_min_auto_action_rate = _direct_setting_float(db, "ops_alerts_min_auto_action_rate_pct", 60.0)
    autonomy_max_operator_intervention_rate = _direct_setting_float(db, "ops_alerts_max_operator_intervention_rate_pct", 40.0)
    since_autonomy = now_dt - timedelta(days=30)
    issue_columns = _table_columns(db, "issues")
    issue_query_columns = []
    if "device_id" in issue_columns:
        issue_query_columns.append(_DIRECT_ISSUE.device_id)
    if "created_at" in issue_columns:
        issue_query_columns.append(_DIRECT_ISSUE.created_at)
    if "resolved_at" in issue_columns:
        issue_query_columns.append(_DIRECT_ISSUE.resolved_at)
    if issue_query_columns:
        issue_query = db.query(*issue_query_columns)
        if "created_at" in issue_columns:
            issue_query = issue_query.filter(_DIRECT_ISSUE.created_at >= since_autonomy)
        if site_id is not None and target_ids and "device_id" in issue_columns:
            issue_query = issue_query.filter(_DIRECT_ISSUE.device_id.in_(target_ids))
        if "created_at" in issue_columns:
            issue_query = issue_query.order_by(_DIRECT_ISSUE.created_at.desc())
        issue_rows = issue_query.limit(5000).all()
    else:
        issue_rows = []
    issues_created = int(len(issue_rows))
    issues_resolved = 0
    mttr_samples: list[int] = []
    for issue in issue_rows:
        created_at = getattr(issue, "created_at", None)
        resolved_at = getattr(issue, "resolved_at", None)
        if created_at is None or resolved_at is None:
            continue
        try:
            dur = int((resolved_at - created_at).total_seconds())
        except Exception:
            continue
        if dur >= 0:
            issues_resolved += 1
            mttr_samples.append(dur)

    mttd_lookback_seconds = 6 * 3600
    event_ts_by_device: dict[int, list[float]] = {}
    if target_ids:
        event_rows = (
            db.query(_DIRECT_EVENT_LOG.device_id, _DIRECT_EVENT_LOG.timestamp, _DIRECT_EVENT_LOG.severity)
            .filter(
                _DIRECT_EVENT_LOG.device_id.in_(target_ids),
                _DIRECT_EVENT_LOG.timestamp >= (since_autonomy - timedelta(seconds=mttd_lookback_seconds)),
            )
            .limit(20000)
            .all()
        )
        for dev_id, ts, sev in event_rows:
            if dev_id is None or ts is None:
                continue
            sev_text = str(sev or "").strip().lower()
            if sev_text not in {"warning", "critical"}:
                continue
            try:
                event_ts_by_device.setdefault(int(dev_id), []).append(float(ts.timestamp()))
            except Exception:
                continue
        for values in event_ts_by_device.values():
            values.sort()

    mttd_samples: list[int] = []
    for issue in issue_rows:
        dev_id = getattr(issue, "device_id", None)
        created_at = getattr(issue, "created_at", None)
        if dev_id is None or created_at is None:
            continue
        ts_values = event_ts_by_device.get(int(dev_id))
        if not ts_values:
            continue
        try:
            created_epoch = float(created_at.timestamp())
        except Exception:
            continue
        idx = bisect.bisect_right(ts_values, created_epoch) - 1
        if idx < 0:
            continue
        delay = int(created_epoch - ts_values[idx])
        if 0 <= delay <= int(mttd_lookback_seconds):
            mttd_samples.append(delay)

    loop_rows = (
        db.query(_DIRECT_EVENT_LOG)
        .filter(
            _DIRECT_EVENT_LOG.event_id == "CLOSED_LOOP_EVAL_SUMMARY",
            _DIRECT_EVENT_LOG.timestamp >= since_autonomy,
        )
        .limit(5000)
        .all()
    )
    actions_executed = 0
    approvals_opened = 0
    trend_7d: dict[str, dict[str, Any]] = {
        (now_dt - timedelta(days=offset)).strftime("%Y-%m-%d"): {
            "date": (now_dt - timedelta(days=offset)).strftime("%Y-%m-%d"),
            "issues_created": 0,
            "issues_resolved": 0,
            "actions_executed": 0,
            "actions_auto": 0,
            "actions_manual": 0,
        }
        for offset in range(6, -1, -1)
    }
    for issue in issue_rows:
        created_at = getattr(issue, "created_at", None)
        if created_at is not None:
            key = created_at.strftime("%Y-%m-%d")
            if key in trend_7d:
                trend_7d[key]["issues_created"] += 1
        resolved_at = getattr(issue, "resolved_at", None)
        if resolved_at is not None:
            key = resolved_at.strftime("%Y-%m-%d")
            if key in trend_7d:
                trend_7d[key]["issues_resolved"] += 1
    for row in loop_rows:
        payload = _safe_parse_json_payload(getattr(row, "message", None))
        if not _direct_closed_loop_kpi_event(payload):
            continue
        executed = int(payload.get("executed") or 0)
        approvals = int(payload.get("approvals_opened") or 0)
        actions_executed += executed
        approvals_opened += approvals
        ts = getattr(row, "timestamp", None)
        if ts is not None:
            key = ts.strftime("%Y-%m-%d")
            if key in trend_7d:
                auto_day = max(0, executed - approvals)
                manual_day = min(executed, max(0, approvals))
                trend_7d[key]["actions_executed"] += int(executed)
                trend_7d[key]["actions_auto"] += int(auto_day)
                trend_7d[key]["actions_manual"] += int(manual_day)

    actions_auto = max(0, actions_executed - approvals_opened)
    actions_manual = min(actions_executed, max(0, approvals_opened))
    action_total = int(actions_auto + actions_manual)
    auto_rate = round((actions_auto / action_total) * 100.0, 2) if action_total > 0 else 0.0
    operator_rate = round((actions_manual / action_total) * 100.0, 2) if action_total > 0 else 0.0
    mttd_avg = round(sum(mttd_samples) / len(mttd_samples), 2) if mttd_samples else None
    mttr_avg = round(sum(mttr_samples) / len(mttr_samples), 2) if mttr_samples else None
    autonomy_status = "idle"
    if issues_created > 0 or action_total > 0:
        autonomy_status = "healthy"
        if auto_rate < float(autonomy_min_auto_action_rate) or operator_rate > float(autonomy_max_operator_intervention_rate):
            autonomy_status = "warning"
    trend_rows = []
    for key in sorted(trend_7d.keys()):
        row = trend_7d[key]
        total_actions = int(row["actions_auto"] + row["actions_manual"])
        trend_rows.append(
            {
                **row,
                "auto_action_rate_pct": round((row["actions_auto"] / total_actions) * 100.0, 2) if total_actions > 0 else 0.0,
                "operator_intervention_rate_pct": round((row["actions_manual"] / total_actions) * 100.0, 2) if total_actions > 0 else 0.0,
            }
        )
    autonomy_kpi = {
        "window_days": 30,
        "status": autonomy_status,
        "mttd_seconds": mttd_avg,
        "mttd_p95_seconds": int(_p95_int(mttd_samples) or 0) if mttd_samples else None,
        "mttr_seconds": mttr_avg,
        "mttr_p95_seconds": int(_p95_int(mttr_samples) or 0) if mttr_samples else None,
        "auto_action_rate_pct": float(auto_rate),
        "operator_intervention_rate_pct": float(operator_rate),
        "mttd_signal_coverage_pct": 100.0 if issues_created == 0 else round((len(mttd_samples) / issues_created) * 100.0, 2),
        "mttr_coverage_pct": 100.0 if issues_resolved == 0 else round((len(mttr_samples) / issues_resolved) * 100.0, 2),
        "targets": {
            "min_auto_action_rate_pct": float(autonomy_min_auto_action_rate),
            "max_operator_intervention_rate_pct": float(autonomy_max_operator_intervention_rate),
        },
        "trend_7d": trend_rows,
        "totals": {
            "issues_created": int(issues_created),
            "issues_resolved": int(issues_resolved),
            "mttd_samples": int(len(mttd_samples)),
            "mttr_samples": int(len(mttr_samples)),
            "actions_executed": int(actions_executed),
            "actions_auto": int(actions_auto),
            "actions_manual": int(actions_manual),
        },
    }
    return {
        "change_kpi": change_kpi,
        "northbound_kpi": northbound_kpi,
        "autonomy_kpi": autonomy_kpi,
    }


def _request_direct_kpi_payload(
    *,
    params: Dict[str, Any],
    history_params: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    _ensure_direct_runtime()
    db = _DIRECT_SESSION_LOCAL()
    try:
        actor = _build_direct_actor()
        original_dashboard_stats = _MISC_ENDPOINT.get_dashboard_stats
        try:
            _MISC_ENDPOINT.get_dashboard_stats = lambda site_id=None, db=None, current_user=None: _build_lightweight_dashboard_payload(db=db, site_id=site_id)
            payload = _OPS_ENDPOINT.kpi_readiness(
                site_id=params.get("site_id"),
                discovery_days=int(params.get("discovery_days") or 30),
                discovery_limit=int(params.get("discovery_limit") or 300),
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
                autonomy_mttd_baseline_seconds=params.get("autonomy_mttd_baseline_seconds"),
                autonomy_mttr_baseline_seconds=params.get("autonomy_mttr_baseline_seconds"),
                autonomy_mttd_improvement_min_pct=30.0,
                autonomy_mttr_improvement_min_pct=40.0,
                northbound_success_min_pct=95.0,
                northbound_p95_attempts_max=3,
                northbound_failed_24h_max=5,
                require_sample_minimums=bool(params.get("require_sample_minimums")),
                sample_min_discovery_jobs=int(params.get("sample_min_discovery_jobs") or DEFAULT_SAMPLE_MINIMUMS["sample_min_discovery_jobs"]),
                sample_min_change_events=int(params.get("sample_min_change_events") or DEFAULT_SAMPLE_MINIMUMS["sample_min_change_events"]),
                sample_min_northbound_deliveries=int(params.get("sample_min_northbound_deliveries") or DEFAULT_SAMPLE_MINIMUMS["sample_min_northbound_deliveries"]),
                sample_min_autonomy_issues_created=int(params.get("sample_min_autonomy_issues_created") or DEFAULT_SAMPLE_MINIMUMS["sample_min_autonomy_issues_created"]),
                sample_min_autonomy_actions_executed=int(params.get("sample_min_autonomy_actions_executed") or DEFAULT_SAMPLE_MINIMUMS["sample_min_autonomy_actions_executed"]),
                db=db,
                current_user=actor,
            )
        finally:
            _MISC_ENDPOINT.get_dashboard_stats = original_dashboard_stats
        history = _OPS_ENDPOINT.get_kpi_readiness_history(
            days=int(history_params.get("days") or 30),
            limit=int(history_params.get("limit") or 90),
            site_id=history_params.get("site_id"),
            status=None,
            db=db,
            current_user=actor,
        )
        return dict(payload or {}), dict(history or {})
    finally:
        db.close()


def _build_markdown(
    payload: Dict[str, Any],
    query_params: Dict[str, Any],
    generated_at_utc: str,
    history_payload: Dict[str, Any],
) -> str:
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    sample_totals = evidence.get("sample_totals") if isinstance(evidence.get("sample_totals"), dict) else {}
    sample_thresholds = evidence.get("sample_thresholds") if isinstance(evidence.get("sample_thresholds"), dict) else {}
    sample_coverage = evidence.get("sample_coverage") if isinstance(evidence.get("sample_coverage"), dict) else {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), list) else []
    coverage = history_payload.get("coverage") if isinstance(history_payload.get("coverage"), dict) else {}
    comparison = history_payload.get("comparison") if isinstance(history_payload.get("comparison"), dict) else {}
    top_failing_checks = (
        history_payload.get("top_failing_checks") if isinstance(history_payload.get("top_failing_checks"), list) else []
    )
    top_unknown_checks = (
        history_payload.get("top_unknown_checks") if isinstance(history_payload.get("top_unknown_checks"), list) else []
    )
    current_streak = history_payload.get("current_streak") if isinstance(history_payload.get("current_streak"), dict) else {}
    sample_coverage_latest = (
        history_payload.get("sample_coverage_latest")
        if isinstance(history_payload.get("sample_coverage_latest"), dict)
        else {}
    )
    history_totals = history_payload.get("totals") if isinstance(history_payload.get("totals"), dict) else {}

    lines: list[str] = []
    lines.append("# KPI Readiness Evidence")
    lines.append("")
    lines.append(f"- Generated (UTC): `{generated_at_utc}`")
    lines.append(f"- Readiness Status: `{_fmt(readiness.get('status'))}`")
    lines.append(f"- Required Checks: `{_fmt(readiness.get('required_checks_total'))}`")
    lines.append(f"- Pass / Fail / Unknown: `{_fmt(readiness.get('pass_count'))}` / `{_fmt(readiness.get('fail_count'))}` / `{_fmt(readiness.get('unknown_count'))}`")
    lines.append("")

    lines.append("## Scope")
    lines.append("")
    lines.append(f"- site_id: `{_fmt(scope.get('site_id'))}`")
    lines.append(f"- discovery_days: `{_fmt(scope.get('discovery_days'))}`")
    lines.append(f"- discovery_limit: `{_fmt(scope.get('discovery_limit'))}`")
    lines.append(f"- require_sample_minimums: `{_fmt(scope.get('require_sample_minimums'))}`")
    lines.append("")

    lines.append("## Query Params")
    lines.append("")
    for key in sorted(query_params.keys()):
        lines.append(f"- {key}: `{_fmt(query_params.get(key))}`")
    lines.append("")

    lines.append("## Sample Evidence")
    lines.append("")
    if sample_totals:
        lines.append("| Metric | Observed | Threshold |")
        lines.append("|---|---:|---:|")
        for key in sorted(sample_totals.keys()):
            lines.append(
                f"| `{key}` | `{_fmt(sample_totals.get(key))}` | `{_fmt(sample_thresholds.get(key))}` |"
            )
    else:
        lines.append("- No sample evidence returned.")
    lines.append("")

    lines.append("## Sample Coverage Ratios")
    lines.append("")
    if sample_coverage:
        lines.append("| Metric | Observed | Threshold | Coverage % | Met |")
        lines.append("|---|---:|---:|---:|---|")
        for key in sorted(sample_coverage.keys()):
            row = sample_coverage.get(key) if isinstance(sample_coverage.get(key), dict) else {}
            lines.append(
                f"| `{key}` | `{_fmt(row.get('observed'))}` | `{_fmt(row.get('threshold'))}` | `{_fmt(row.get('coverage_pct'))}` | `{_fmt(row.get('met'))}` |"
            )
    else:
        lines.append("- No sample coverage ratios returned.")
    lines.append("")

    lines.append("## Check Results")
    lines.append("")
    lines.append("| Check ID | Status | Value | Threshold | Required | Source |")
    lines.append("|---|---|---:|---:|---|---|")
    for row in checks:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| `{_fmt(row.get('id'))}` | `{_fmt(row.get('status'))}` | `{_fmt(row.get('value'))}` | `{_fmt(row.get('threshold'))}` | `{_fmt(row.get('required'))}` | `{_fmt(row.get('source'))}` |"
        )
    lines.append("")

    lines.append("## Snapshot History")
    lines.append("")
    if history_totals:
        lines.append(f"- Snapshot Count: `{_fmt(history_totals.get('count'))}`")
        lines.append(f"- Coverage Days: `{_fmt(coverage.get('days_with_snapshots'))}` / `{_fmt(coverage.get('expected_days'))}`")
        lines.append(f"- Coverage %: `{_fmt(coverage.get('coverage_pct'))}`")
        lines.append(f"- Missing Days: `{_fmt(coverage.get('missing_days'))}`")
        lines.append(f"- Status Transitions: `{_fmt(coverage.get('status_transition_count'))}`")
        lines.append(f"- Current Streak: `{_fmt(current_streak.get('status'))}` x `{_fmt(current_streak.get('snapshots'))}` snapshots")
    else:
        lines.append("- No snapshot history available.")
    lines.append("")

    lines.append("## Latest vs Previous Snapshot")
    lines.append("")
    if comparison.get("available"):
        lines.append(f"- Status: `{_fmt(comparison.get('previous_status'))}` -> `{_fmt(comparison.get('latest_status'))}`")
        lines.append(f"- Direction: `{_fmt(comparison.get('status_direction'))}`")
        lines.append(f"- Pass / Fail / Unknown Delta: `{_fmt(comparison.get('pass_delta'))}` / `{_fmt(comparison.get('fail_delta'))}` / `{_fmt(comparison.get('unknown_delta'))}`")
        lines.append(f"- Interval Hours: `{_fmt(comparison.get('interval_hours'))}`")
        sample_total_delta = comparison.get("sample_total_delta") if isinstance(comparison.get("sample_total_delta"), dict) else {}
        if sample_total_delta:
            lines.append("")
            lines.append("| Sample Metric | Delta |")
            lines.append("|---|---:|")
            for key in sorted(sample_total_delta.keys()):
                lines.append(f"| `{key}` | `{_fmt(sample_total_delta.get(key))}` |")
    else:
        lines.append("- No previous snapshot available.")
    lines.append("")

    lines.append("## Top Failing Checks (History)")
    lines.append("")
    if top_failing_checks:
        lines.append("| Check ID | Fail Count | Fail Rate % | Latest Status | Latest Value | Threshold |")
        lines.append("|---|---:|---:|---|---:|---:|")
        for row in top_failing_checks:
            lines.append(
                f"| `{_fmt(row.get('id'))}` | `{_fmt(row.get('fail_count'))}` | `{_fmt(row.get('fail_rate_pct'))}` | `{_fmt(row.get('latest_status'))}` | `{_fmt(row.get('latest_value'))}` | `{_fmt(row.get('latest_threshold'))}` |"
            )
    else:
        lines.append("- No failing checks in snapshot history.")
    lines.append("")

    lines.append("## Top Unknown Checks (History)")
    lines.append("")
    if top_unknown_checks:
        lines.append("| Check ID | Unknown Count | Unknown Rate % | Latest Status | Latest Value | Threshold |")
        lines.append("|---|---:|---:|---|---:|---:|")
        for row in top_unknown_checks:
            lines.append(
                f"| `{_fmt(row.get('id'))}` | `{_fmt(row.get('unknown_count'))}` | `{_fmt(row.get('unknown_rate_pct'))}` | `{_fmt(row.get('latest_status'))}` | `{_fmt(row.get('latest_value'))}` | `{_fmt(row.get('latest_threshold'))}` |"
            )
    else:
        lines.append("- No unknown checks in snapshot history.")
    lines.append("")

    lines.append("## Latest Snapshot Sample Coverage")
    lines.append("")
    if sample_coverage_latest:
        lines.append("| Metric | Observed | Threshold | Coverage % | Met |")
        lines.append("|---|---:|---:|---:|---|")
        for key in sorted(sample_coverage_latest.keys()):
            row = sample_coverage_latest.get(key) if isinstance(sample_coverage_latest.get(key), dict) else {}
            lines.append(
                f"| `{key}` | `{_fmt(row.get('observed'))}` | `{_fmt(row.get('threshold'))}` | `{_fmt(row.get('coverage_pct'))}` | `{_fmt(row.get('met'))}` |"
            )
    else:
        lines.append("- No latest snapshot sample coverage available.")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export measured KPI readiness evidence as JSON + Markdown report.",
    )
    parser.add_argument("--base-url", default="http://localhost:8000", help="NetSphere base URL.")
    parser.add_argument(
        "--token",
        default=os.getenv("NETSPHERE_TOKEN") or os.getenv("NETMANAGER_TOKEN", ""),
        help="Bearer token. Defaults to NETSPHERE_TOKEN, then NETMANAGER_TOKEN.",
    )
    parser.add_argument("--direct-db", action="store_true", help="Read KPI readiness directly from local DB/services without API auth.")
    parser.add_argument("--site-id", type=int, default=None, help="Optional site scope.")
    parser.add_argument("--discovery-days", type=int, default=30, help="Discovery KPI window days.")
    parser.add_argument("--discovery-limit", type=int, default=300, help="Discovery KPI sample limit.")
    parser.add_argument("--autonomy-mttd-baseline-seconds", type=float, default=None)
    parser.add_argument("--autonomy-mttr-baseline-seconds", type=float, default=None)
    parser.add_argument("--require-sample-minimums", action="store_true")
    parser.add_argument("--sample-min-discovery-jobs", type=int, default=DEFAULT_SAMPLE_MINIMUMS["sample_min_discovery_jobs"])
    parser.add_argument("--sample-min-change-events", type=int, default=DEFAULT_SAMPLE_MINIMUMS["sample_min_change_events"])
    parser.add_argument("--sample-min-northbound-deliveries", type=int, default=DEFAULT_SAMPLE_MINIMUMS["sample_min_northbound_deliveries"])
    parser.add_argument("--sample-min-autonomy-issues-created", type=int, default=DEFAULT_SAMPLE_MINIMUMS["sample_min_autonomy_issues_created"])
    parser.add_argument("--sample-min-autonomy-actions-executed", type=int, default=DEFAULT_SAMPLE_MINIMUMS["sample_min_autonomy_actions_executed"])
    parser.add_argument("--history-days", type=int, default=30, help="Readiness snapshot history window days.")
    parser.add_argument("--history-limit", type=int, default=90, help="Readiness snapshot history item limit.")
    parser.add_argument("--output-dir", default="docs/reports", help="Directory to store report files.")
    parser.add_argument("--filename-prefix", default="kpi-readiness", help="Output filename prefix.")
    parser.add_argument("--latest-json-path", default="", help="Optional fixed-path JSON output (copied from latest timestamped report).")
    parser.add_argument("--latest-md-path", default="", help="Optional fixed-path Markdown output (copied from latest timestamped report).")
    parser.add_argument("--fail-on-unhealthy", action="store_true", help="Return non-zero if readiness is not healthy.")
    args = parser.parse_args()

    params: Dict[str, Any] = {
        "discovery_days": int(args.discovery_days),
        "discovery_limit": int(args.discovery_limit),
        "require_sample_minimums": bool(args.require_sample_minimums),
        "sample_min_discovery_jobs": int(args.sample_min_discovery_jobs),
        "sample_min_change_events": int(args.sample_min_change_events),
        "sample_min_northbound_deliveries": int(args.sample_min_northbound_deliveries),
        "sample_min_autonomy_issues_created": int(args.sample_min_autonomy_issues_created),
        "sample_min_autonomy_actions_executed": int(args.sample_min_autonomy_actions_executed),
    }
    if args.site_id is not None:
        params["site_id"] = int(args.site_id)
    if args.autonomy_mttd_baseline_seconds is not None:
        params["autonomy_mttd_baseline_seconds"] = float(args.autonomy_mttd_baseline_seconds)
    if args.autonomy_mttr_baseline_seconds is not None:
        params["autonomy_mttr_baseline_seconds"] = float(args.autonomy_mttr_baseline_seconds)

    history_params: Dict[str, Any] = {
        "days": int(args.history_days),
        "limit": int(args.history_limit),
    }
    if args.site_id is not None:
        history_params["site_id"] = int(args.site_id)
    if bool(args.direct_db):
        try:
            payload, history_payload = _request_direct_kpi_payload(
                params=params,
                history_params=history_params,
            )
        except Exception as exc:
            print(f"[ERROR] Direct KPI export failed: {exc}", file=sys.stderr)
            return 1
    else:
        url = str(args.base_url).rstrip("/") + "/api/v1/ops/kpi/readiness"
        headers: Dict[str, str] = {}
        if str(args.token or "").strip():
            headers["Authorization"] = f"Bearer {str(args.token).strip()}"

        try:
            payload = _request_json(url, params=params, headers=headers)
        except Exception as exc:
            print(f"[ERROR] Request failed: {exc}", file=sys.stderr)
            return 1

        history_url = str(args.base_url).rstrip("/") + "/api/v1/ops/kpi/readiness/history"
        try:
            history_payload = _request_json(history_url, params=history_params, headers=headers)
        except Exception as exc:
            print(f"[WARN] Snapshot history unavailable: {exc}", file=sys.stderr)
            history_payload = {}

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    generated_at_utc = now.strftime("%Y-%m-%d %H:%M:%S")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{args.filename_prefix}-{stamp}.json"
    md_path = out_dir / f"{args.filename_prefix}-{stamp}.md"

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at_utc": generated_at_utc,
                "query": params,
                "payload": payload,
                "history": history_payload,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    md_text = _build_markdown(
        payload=payload,
        query_params=params,
        generated_at_utc=generated_at_utc,
        history_payload=history_payload,
    )
    with md_path.open("w", encoding="utf-8") as f:
        f.write(md_text)

    latest_json_path = str(args.latest_json_path or "").strip()
    latest_md_path = str(args.latest_md_path or "").strip()
    if latest_json_path:
        latest_json = Path(latest_json_path)
        latest_json.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(json_path, latest_json)
    if latest_md_path:
        latest_md = Path(latest_md_path)
        latest_md.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(md_path, latest_md)

    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    status = str(readiness.get("status") or "").strip().lower()
    print(f"[OK] JSON report: {json_path}")
    print(f"[OK] Markdown report: {md_path}")
    if latest_json_path:
        print(f"[OK] Fixed JSON report: {latest_json_path}")
    if latest_md_path:
        print(f"[OK] Fixed Markdown report: {latest_md_path}")
    print(f"[INFO] readiness.status={status or '-'}")

    if args.fail_on_unhealthy and status != "healthy":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
