import io
import os
import shutil
import subprocess
import time
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.device import EventLog
from app.models.user import User
from app.services.policy_translator import PolicyTranslator
from app.services.inventory_parsers import inventory_parser_support_matrix
from app.services.release_evidence_service import (
    RELEASE_EVIDENCE_AUTOMATION_HOUR,
    RELEASE_EVIDENCE_AUTOMATION_MINUTE,
    RELEASE_EVIDENCE_AUTOMATION_TIMEZONE,
    RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE,
    RELEASE_EVIDENCE_REFRESH_ENABLED_SETTING_KEY,
    RELEASE_EVIDENCE_REFRESH_INCLUDE_NORTHBOUND_PROBE_SETTING_KEY,
    RELEASE_EVIDENCE_REFRESH_INCLUDE_SYNTHETIC_SETTING_KEY,
    RELEASE_EVIDENCE_REFRESH_PROFILE_SETTING_KEY,
    RELEASE_EVIDENCE_REFRESH_PROFILES,
    build_release_evidence_bundle,
    get_release_evidence_northbound_probe_runtime,
    get_release_evidence_refresh_status,
    get_release_evidence_snapshot,
    start_release_evidence_refresh,
)
from app.services.pro_operator_package_service import build_pro_operator_package
from app.services.operations_review_package_service import build_operations_review_bundle
from app.services.policy_manifest_service import PolicyManifestService
from app.models.settings import SystemSetting


router = APIRouter()


OBSERVABILITY_CONTAINERS = [
    "netsphere-loki",
    "netsphere-prometheus",
    "netsphere-redis-exporter",
    "netsphere-celery-exporter",
    "netsphere-promtail",
    "netsphere-grafana",
]
OBSERVABILITY_RUNTIME_SETTING_KEY = "ops_observability_enabled"

KPI_READINESS_SNAPSHOT_EVENT_ID = "OPS_KPI_READINESS_SNAPSHOT"
KPI_READINESS_SNAPSHOT_SOURCE = "OpsKPI"
KPI_READINESS_STATUSES = {"healthy", "warning", "critical", "insufficient_data"}
DEFAULT_KPI_SAMPLE_MINIMUMS = {
    "discovery_jobs": 30,
    "change_events": 60,
    "northbound_deliveries": 500,
    "autonomy_issues_created": 20,
    "autonomy_actions_executed": 20,
}
KPI_READINESS_STATUS_RANK = {
    "healthy": 0,
    "insufficient_data": 1,
    "warning": 2,
    "critical": 3,
}


def _toggle_enabled() -> bool:
    v = str(os.getenv("ENABLE_OBSERVABILITY_TOGGLE", "0")).strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _docker_runtime_available() -> bool:
    try:
        return bool(os.path.exists("/var/run/docker.sock"))
    except Exception:
        return False


def _logical_observability_enabled(db: Session) -> bool:
    row = db.query(SystemSetting).filter(SystemSetting.key == OBSERVABILITY_RUNTIME_SETTING_KEY).first()
    if not row:
        default_enabled = _to_bool(os.getenv("OBSERVABILITY_DEFAULT_ENABLED", "1"), default=True)
        return bool(default_enabled)
    return _to_bool(getattr(row, "value", None), default=False)


def _set_logical_observability_enabled(db: Session, enabled: bool) -> None:
    normalized = "true" if bool(enabled) else "false"
    row = db.query(SystemSetting).filter(SystemSetting.key == OBSERVABILITY_RUNTIME_SETTING_KEY).first()
    if row:
        if str(getattr(row, "value", "")).strip().lower() == normalized:
            return
        row.value = normalized
    else:
        db.add(
            SystemSetting(
                key=OBSERVABILITY_RUNTIME_SETTING_KEY,
                value=normalized,
                description="Logical observability runtime toggle (used when docker control is unavailable).",
                category="ops",
            )
        )
    db.commit()


def _get_setting_value(db: Session, key: str, default: Any = None) -> Any:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        return default
    value = getattr(row, "value", None)
    return default if value is None else value


def _next_daily_run_iso(*, hour: int, minute: int, tz_offset_hours: int = 9) -> str:
    local_tz = timezone(timedelta(hours=tz_offset_hours))
    now_local = datetime.now(local_tz)
    next_run = now_local.replace(hour=int(hour), minute=int(minute), second=0, microsecond=0)
    if next_run <= now_local:
        next_run = next_run + timedelta(days=1)
    return next_run.isoformat()


def _build_release_evidence_automation_policy(db: Session) -> dict[str, Any]:
    enabled = _to_bool(
        _get_setting_value(db, RELEASE_EVIDENCE_REFRESH_ENABLED_SETTING_KEY, "true"),
        default=True,
    )
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
    include_synthetic = _to_bool(
        _get_setting_value(db, RELEASE_EVIDENCE_REFRESH_INCLUDE_SYNTHETIC_SETTING_KEY, "false"),
        default=False,
    )
    include_northbound_probe = _to_bool(
        _get_setting_value(db, RELEASE_EVIDENCE_REFRESH_INCLUDE_NORTHBOUND_PROBE_SETTING_KEY, "false"),
        default=False,
    )
    northbound_probe_runtime = get_release_evidence_northbound_probe_runtime()
    next_run_at = _next_daily_run_iso(
        hour=RELEASE_EVIDENCE_AUTOMATION_HOUR,
        minute=RELEASE_EVIDENCE_AUTOMATION_MINUTE,
    )
    return {
        "enabled": bool(enabled),
        "profile": profile,
        "include_synthetic": bool(include_synthetic),
        "include_northbound_probe": bool(include_northbound_probe),
        "northbound_probe": {
            "enabled": bool(include_northbound_probe),
            "auth_configured": bool(northbound_probe_runtime.get("auth_configured")),
            "auth_mode": northbound_probe_runtime.get("auth_mode"),
            "direct_mode_available": bool(northbound_probe_runtime.get("direct_mode_available")),
            "execution_mode": northbound_probe_runtime.get("execution_mode"),
            "base_url": northbound_probe_runtime.get("base_url"),
            "latest_probe_available": bool(northbound_probe_runtime.get("latest_probe_available")),
        },
        "schedule": {
            "cadence": "daily",
            "timezone": RELEASE_EVIDENCE_AUTOMATION_TIMEZONE,
            "hour": int(RELEASE_EVIDENCE_AUTOMATION_HOUR),
            "minute": int(RELEASE_EVIDENCE_AUTOMATION_MINUTE),
            "label": f"Daily {RELEASE_EVIDENCE_AUTOMATION_HOUR:02d}:{RELEASE_EVIDENCE_AUTOMATION_MINUTE:02d} {RELEASE_EVIDENCE_AUTOMATION_TIMEZONE}",
        },
        "next_run_at": next_run_at if enabled else None,
    }


def _run_docker(args: list[str], timeout_seconds: int = 15) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Docker CLI not available in backend container.")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="Docker command timed out.")


def _inspect_container(name: str) -> dict[str, Any]:
    p = _run_docker(["inspect", name])
    if p.returncode != 0:
        stderr = (p.stderr or "").strip()
        if "No such object" in stderr or "Error: No such object" in stderr:
            return {"name": name, "exists": False, "status": "missing"}
        return {"name": name, "exists": False, "status": "error", "error": stderr[:300]}
    try:
        import json

        data = json.loads(p.stdout or "[]")
        state = (data[0] or {}).get("State") or {}
        return {
            "name": name,
            "exists": True,
            "status": state.get("Status") or "unknown",
            "running": bool(state.get("Running")),
        }
    except Exception:
        return {"name": name, "exists": True, "status": "unknown"}


class ObservabilitySetRequest(BaseModel):
    enabled: bool


@router.get("/policy-manifest")
def get_policy_manifest(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return PolicyManifestService.build(db, current_user)


def _read_text(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return None


def _read_int(path: str) -> int | None:
    raw = _read_text(path)
    if raw is None:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _get_cgroup_memory() -> dict[str, Any]:
    limit = _read_text("/sys/fs/cgroup/memory.max")
    current = _read_int("/sys/fs/cgroup/memory.current")
    if limit is not None and limit != "max" and current is not None:
        limit_b = int(limit)
        used_b = int(current)
        pct = (used_b / limit_b * 100.0) if limit_b > 0 else None
        return {"limit_bytes": limit_b, "used_bytes": used_b, "used_percent": pct}

    limit_b = _read_int("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    used_b = _read_int("/sys/fs/cgroup/memory/memory.usage_in_bytes")
    if limit_b is not None and used_b is not None:
        pct = (used_b / limit_b * 100.0) if limit_b > 0 else None
        return {"limit_bytes": limit_b, "used_bytes": used_b, "used_percent": pct}

    mem_total_kb = None
    mem_avail_kb = None
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail_kb = int(line.split()[1])
    except Exception:
        pass
    if mem_total_kb is None:
        return {"limit_bytes": None, "used_bytes": None, "used_percent": None}
    total_b = mem_total_kb * 1024
    if mem_avail_kb is None:
        return {"limit_bytes": total_b, "used_bytes": None, "used_percent": None}
    avail_b = mem_avail_kb * 1024
    used_b = max(0, total_b - avail_b)
    pct = (used_b / total_b * 100.0) if total_b > 0 else None
    return {"limit_bytes": total_b, "used_bytes": used_b, "used_percent": pct}


def _get_cpu_percent(sample_seconds: float = 0.15) -> float | None:
    def read_cpu() -> tuple[int, int] | None:
        try:
            with open("/proc/stat", "r", encoding="utf-8") as f:
                line = f.readline()
            if not line.startswith("cpu "):
                return None
            parts = line.split()
            nums = [int(x) for x in parts[1:]]
            total = sum(nums)
            idle = nums[3] + (nums[4] if len(nums) > 4 else 0)
            return total, idle
        except Exception:
            return None

    a = read_cpu()
    if a is None:
        return None
    time.sleep(max(0.05, sample_seconds))
    b = read_cpu()
    if b is None:
        return None
    total_delta = b[0] - a[0]
    idle_delta = b[1] - a[1]
    if total_delta <= 0:
        return None
    usage = (1.0 - (idle_delta / total_delta)) * 100.0
    return max(0.0, min(100.0, usage))


def _disk_usage(path: str) -> dict[str, Any] | None:
    try:
        usage = shutil.disk_usage(path)
        used_pct = (usage.used / usage.total * 100.0) if usage.total > 0 else None
        return {
            "path": path,
            "total_bytes": int(usage.total),
            "used_bytes": int(usage.used),
            "free_bytes": int(usage.free),
            "used_percent": used_pct,
        }
    except Exception:
        return None


def _docker_compose_related_status() -> list[dict[str, Any]] | None:
    if _read_text("/var/run/docker.sock") is None and not os.path.exists("/var/run/docker.sock"):
        return None
    p = _run_docker(["ps", "-a", "--format", "{{.Names}}\t{{.Status}}"], timeout_seconds=10)
    if p.returncode != 0:
        return None
    items: list[dict[str, Any]] = []
    for line in (p.stdout or "").splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        name, status = parts[0].strip(), parts[1].strip()
        lowered = name.lower()
        if "netmanager" not in lowered and "netsphere" not in lowered:
            continue
        items.append({"name": name, "status": status})
    return items


def _unwrap_api_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        if "data" in raw and isinstance(raw.get("data"), dict):
            return dict(raw.get("data") or {})
        return dict(raw)
    return {}


def _read_json_response_payload(resp: Any) -> dict[str, Any]:
    if resp is None:
        return {}
    if isinstance(resp, dict):
        return _unwrap_api_payload(resp)
    body = getattr(resp, "body", None)
    if body is None:
        return {}
    try:
        import json

        if isinstance(body, bytes):
            decoded = body.decode("utf-8")
        else:
            decoded = str(body)
        parsed = json.loads(decoded or "{}")
        return _unwrap_api_payload(parsed)
    except Exception:
        return {}


def _num(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _build_check(
    *,
    check_id: str,
    title: str,
    value: Any,
    threshold: Any,
    operator: str,
    source: str,
    required: bool = True,
) -> dict[str, Any]:
    value_n = _num(value)
    threshold_n = _num(threshold)
    if value_n is None or threshold_n is None:
        status = "unknown"
        passed = None
    else:
        if operator == "<=":
            passed = bool(value_n <= threshold_n)
        elif operator == ">=":
            passed = bool(value_n >= threshold_n)
        else:
            passed = None
        status = "pass" if passed is True else "fail"
    return {
        "id": str(check_id),
        "title": str(title),
        "value": value,
        "threshold": threshold,
        "operator": operator,
        "status": status,
        "pass": passed,
        "required": bool(required),
        "source": source,
    }


def _to_json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _severity_for_readiness(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "healthy":
        return "info"
    if normalized == "warning":
        return "warning"
    if normalized == "critical":
        return "error"
    return "warning"


def _build_sample_coverage(
    sample_totals: dict[str, Any] | None,
    sample_thresholds: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    totals = sample_totals if isinstance(sample_totals, dict) else {}
    thresholds = sample_thresholds if isinstance(sample_thresholds, dict) else {}
    coverage: dict[str, dict[str, Any]] = {}
    for key in sorted(set(totals.keys()) | set(thresholds.keys())):
        observed_raw = totals.get(key)
        threshold_raw = thresholds.get(key)
        observed = _num(observed_raw)
        threshold = _num(threshold_raw)
        met = None
        coverage_pct = None
        deficit = None
        if observed is not None and threshold is not None:
            met = bool(observed >= threshold)
            if threshold > 0:
                coverage_pct = round((observed / threshold) * 100.0, 2)
            deficit = round(max(0.0, threshold - observed), 2)
        coverage[str(key)] = {
            "observed": observed_raw,
            "threshold": threshold_raw,
            "coverage_pct": coverage_pct,
            "met": met,
            "deficit": deficit,
        }
    return coverage


def _compact_kpi_check_row(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    check_id = str(row.get("id") or "").strip()
    if not check_id:
        return None
    return {
        "id": check_id,
        "title": str(row.get("title") or check_id),
        "status": str(row.get("status") or "unknown").strip().lower(),
        "required": bool(row.get("required", True)),
        "value": row.get("value"),
        "threshold": row.get("threshold"),
        "operator": str(row.get("operator") or ""),
        "source": str(row.get("source") or ""),
    }


def _snapshot_checks_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    checks_raw = payload.get("checks")
    checks: list[dict[str, Any]] = []
    if isinstance(checks_raw, list):
        for row in checks_raw:
            compact = _compact_kpi_check_row(row if isinstance(row, dict) else {})
            if compact:
                checks.append(compact)
    if checks:
        return checks

    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    legacy_checks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for status_key, status_value in (("failed_check_ids", "fail"), ("unknown_check_ids", "unknown")):
        for check_id in list(readiness.get(status_key) or []):
            normalized_id = str(check_id or "").strip()
            if not normalized_id or normalized_id in seen_ids:
                continue
            seen_ids.add(normalized_id)
            legacy_checks.append(
                {
                    "id": normalized_id,
                    "title": normalized_id,
                    "status": status_value,
                    "required": True,
                    "value": None,
                    "threshold": None,
                    "operator": "",
                    "source": "legacy_snapshot",
                }
            )
    return legacy_checks


def _status_direction(previous_status: str | None, latest_status: str | None) -> str:
    previous_rank = KPI_READINESS_STATUS_RANK.get(str(previous_status or "").strip().lower())
    latest_rank = KPI_READINESS_STATUS_RANK.get(str(latest_status or "").strip().lower())
    if previous_rank is None or latest_rank is None:
        return "unknown"
    if latest_rank > previous_rank:
        return "regressed"
    if latest_rank < previous_rank:
        return "improved"
    return "stable"


def _summarize_readiness_history(items: list[dict[str, Any]], days: int) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    per_day: dict[str, dict[str, Any]] = {}
    check_rollup: dict[str, dict[str, Any]] = {}

    for item in items:
        readiness = item.get("readiness") if isinstance(item.get("readiness"), dict) else {}
        read_status = str(readiness.get("status") or "insufficient_data").strip().lower()
        by_status[read_status] = int(by_status.get(read_status, 0) + 1)

        day = str(item.get("generated_date") or "")
        day_row = per_day.setdefault(
            day,
            {
                "healthy": 0,
                "warning": 0,
                "critical": 0,
                "insufficient_data": 0,
                "total": 0,
                "latest_generated_at": 0,
                "latest_status": "insufficient_data",
                "latest_fail_count": 0,
                "latest_unknown_count": 0,
            },
        )
        if read_status not in day_row:
            day_row[read_status] = 0
        day_row[read_status] = int(day_row[read_status] + 1)
        day_row["total"] = int(day_row.get("total", 0) + 1)

        generated_at = int(item.get("generated_at") or 0)
        if generated_at >= int(day_row.get("latest_generated_at") or 0):
            day_row["latest_generated_at"] = generated_at
            day_row["latest_status"] = read_status
            day_row["latest_fail_count"] = int(readiness.get("fail_count") or 0)
            day_row["latest_unknown_count"] = int(readiness.get("unknown_count") or 0)

        for check in list(item.get("checks") or []):
            if not isinstance(check, dict):
                continue
            check_id = str(check.get("id") or "").strip()
            if not check_id:
                continue
            status = str(check.get("status") or "unknown").strip().lower()
            rollup = check_rollup.setdefault(
                check_id,
                {
                    "id": check_id,
                    "title": str(check.get("title") or check_id),
                    "source": str(check.get("source") or ""),
                    "required": bool(check.get("required", True)),
                    "total": 0,
                    "pass_count": 0,
                    "fail_count": 0,
                    "unknown_count": 0,
                    "latest_status": "unknown",
                    "latest_value": None,
                    "latest_threshold": None,
                    "latest_generated_at": 0,
                },
            )
            rollup["total"] = int(rollup["total"] + 1)
            if status == "pass":
                rollup["pass_count"] = int(rollup["pass_count"] + 1)
            elif status == "fail":
                rollup["fail_count"] = int(rollup["fail_count"] + 1)
            else:
                rollup["unknown_count"] = int(rollup["unknown_count"] + 1)

            if generated_at >= int(rollup.get("latest_generated_at") or 0):
                rollup["latest_generated_at"] = generated_at
                rollup["latest_status"] = status
                rollup["latest_value"] = check.get("value")
                rollup["latest_threshold"] = check.get("threshold")
                rollup["required"] = bool(check.get("required", True))
                rollup["title"] = str(check.get("title") or check_id)
                rollup["source"] = str(check.get("source") or "")

    trend: list[dict[str, Any]] = []
    for day in sorted(per_day.keys()):
        row = dict(per_day[day])
        row["date"] = day
        trend.append(row)

    latest = items[0] if items else None
    previous = items[1] if len(items) > 1 else None
    latest_readiness = latest.get("readiness") if isinstance(latest, dict) else {}
    previous_readiness = previous.get("readiness") if isinstance(previous, dict) else {}

    latest_samples = (
        latest.get("evidence", {}).get("sample_totals")
        if isinstance(latest, dict) and isinstance(latest.get("evidence"), dict)
        else {}
    )
    previous_samples = (
        previous.get("evidence", {}).get("sample_totals")
        if isinstance(previous, dict) and isinstance(previous.get("evidence"), dict)
        else {}
    )
    sample_delta: dict[str, Any] = {}
    for key in sorted(set((latest_samples or {}).keys()) | set((previous_samples or {}).keys())):
        current_value = _num((latest_samples or {}).get(key))
        prev_value = _num((previous_samples or {}).get(key))
        sample_delta[key] = None if current_value is None or prev_value is None else round(current_value - prev_value, 2)

    latest_status = str(latest_readiness.get("status") or "insufficient_data").strip().lower()
    streak_count = 0
    streak_days: set[str] = set()
    for item in items:
        item_status = str(item.get("readiness", {}).get("status") or "insufficient_data").strip().lower()
        if item_status != latest_status:
            break
        streak_count += 1
        streak_days.add(str(item.get("generated_date") or ""))

    expected_dates = {
        (datetime.now(timezone.utc).date() - timedelta(days=offset)).isoformat()
        for offset in range(max(1, int(days)))
    }
    active_dates = {str(item.get("generated_date") or "") for item in items if str(item.get("generated_date") or "")}
    days_with_snapshots = len(expected_dates & active_dates)
    expected_days = len(expected_dates)

    check_rows = list(check_rollup.values())
    for row in check_rows:
        total = max(1, int(row.get("total") or 0))
        row["fail_rate_pct"] = round((int(row.get("fail_count") or 0) / total) * 100.0, 2)
        row["unknown_rate_pct"] = round((int(row.get("unknown_count") or 0) / total) * 100.0, 2)

    top_failing_checks = sorted(
        [row for row in check_rows if int(row.get("fail_count") or 0) > 0],
        key=lambda row: (
            -int(row.get("fail_count") or 0),
            -float(row.get("fail_rate_pct") or 0.0),
            str(row.get("id") or ""),
        ),
    )[:5]
    top_unknown_checks = sorted(
        [row for row in check_rows if int(row.get("unknown_count") or 0) > 0],
        key=lambda row: (
            -int(row.get("unknown_count") or 0),
            -float(row.get("unknown_rate_pct") or 0.0),
            str(row.get("id") or ""),
        ),
    )[:5]

    latest_checks = list(latest.get("checks") or []) if isinstance(latest, dict) else []
    latest_failed_checks = [row for row in latest_checks if str(row.get("status") or "") == "fail"]
    latest_unknown_checks = [row for row in latest_checks if str(row.get("status") or "") == "unknown"]

    comparison = {
        "available": bool(latest and previous),
        "latest_status": latest_status if latest else None,
        "previous_status": str(previous_readiness.get("status") or "insufficient_data").strip().lower() if previous else None,
        "status_direction": _status_direction(
            str(previous_readiness.get("status") or "") if previous else None,
            latest_status if latest else None,
        ),
        "status_changed": bool(latest and previous and latest_status != str(previous_readiness.get("status") or "").strip().lower()),
        "pass_delta": None
        if not latest or not previous
        else int(latest_readiness.get("pass_count") or 0) - int(previous_readiness.get("pass_count") or 0),
        "fail_delta": None
        if not latest or not previous
        else int(latest_readiness.get("fail_count") or 0) - int(previous_readiness.get("fail_count") or 0),
        "unknown_delta": None
        if not latest or not previous
        else int(latest_readiness.get("unknown_count") or 0) - int(previous_readiness.get("unknown_count") or 0),
        "sample_total_delta": sample_delta,
        "interval_hours": None
        if not latest or not previous
        else round((int(latest.get("generated_at") or 0) - int(previous.get("generated_at") or 0)) / 3600.0, 2),
    }

    coverage = {
        "expected_days": expected_days,
        "days_with_snapshots": days_with_snapshots,
        "missing_days": max(0, expected_days - days_with_snapshots),
        "coverage_pct": round((days_with_snapshots / expected_days) * 100.0, 2) if expected_days > 0 else 0.0,
        "snapshots_per_active_day_avg": round((len(items) / days_with_snapshots), 2) if days_with_snapshots > 0 else 0.0,
        "latest_age_hours": None
        if not latest
        else round((time.time() - int(latest.get("generated_at") or 0)) / 3600.0, 2),
        "status_transition_count": sum(
            1
            for idx in range(1, len(items))
            if str(items[idx - 1].get("readiness", {}).get("status") or "").strip().lower()
            != str(items[idx].get("readiness", {}).get("status") or "").strip().lower()
        ),
    }

    return {
        "totals": {
            "count": int(len(items)),
            "by_status": by_status,
        },
        "trend_by_day": trend,
        "coverage": coverage,
        "comparison": comparison,
        "current_streak": {
            "status": latest_status if latest else None,
            "snapshots": streak_count,
            "days": len([day for day in streak_days if day]),
        },
        "latest_failed_checks": latest_failed_checks,
        "latest_unknown_checks": latest_unknown_checks,
        "top_failing_checks": top_failing_checks,
        "top_unknown_checks": top_unknown_checks,
        "sample_coverage_latest": (
            latest.get("evidence", {}).get("sample_coverage")
            if isinstance(latest, dict) and isinstance(latest.get("evidence"), dict)
            else {}
        ),
    }


def persist_kpi_readiness_snapshot(
    db: Session,
    readiness_payload: dict[str, Any],
    *,
    source: str = KPI_READINESS_SNAPSHOT_SOURCE,
    run_type: str = "manual",
    commit: bool = True,
) -> dict[str, Any]:
    payload = dict(readiness_payload or {})
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    checks = list(payload.get("checks") or [])
    generated_at = int(payload.get("generated_at") or int(time.time()))
    generated_at_utc = datetime.fromtimestamp(generated_at, tz=timezone.utc).isoformat()

    failed_check_ids: list[str] = []
    unknown_check_ids: list[str] = []
    for row in checks:
        if not isinstance(row, dict):
            continue
        check_id = str(row.get("id") or "").strip()
        if not check_id:
            continue
        status = str(row.get("status") or "").strip().lower()
        if status == "fail":
            failed_check_ids.append(check_id)
        elif status == "unknown":
            unknown_check_ids.append(check_id)

    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    sample_totals = evidence.get("sample_totals") if isinstance(evidence.get("sample_totals"), dict) else {}
    sample_thresholds = evidence.get("sample_thresholds") if isinstance(evidence.get("sample_thresholds"), dict) else {}
    sample_coverage = _build_sample_coverage(sample_totals, sample_thresholds)
    snapshot_checks = [compact for compact in (_compact_kpi_check_row(row) for row in checks) if compact]

    snapshot_payload = {
        "generated_at": generated_at,
        "generated_at_utc": generated_at_utc,
        "run_type": str(run_type or "manual"),
        "scope": {
            "site_id": scope.get("site_id"),
            "discovery_days": scope.get("discovery_days"),
            "discovery_limit": scope.get("discovery_limit"),
            "require_sample_minimums": bool(scope.get("require_sample_minimums")),
        },
        "readiness": {
            "status": str(readiness.get("status") or "insufficient_data"),
            "required_checks_total": int(readiness.get("required_checks_total") or 0),
            "pass_count": int(readiness.get("pass_count") or 0),
            "fail_count": int(readiness.get("fail_count") or 0),
            "unknown_count": int(readiness.get("unknown_count") or 0),
            "failed_check_ids": failed_check_ids,
            "unknown_check_ids": unknown_check_ids,
        },
        "evidence": {
            "sample_minimums_enforced": bool(evidence.get("sample_minimums_enforced")),
            "sample_totals": sample_totals,
            "sample_thresholds": sample_thresholds,
            "sample_coverage": sample_coverage,
        },
        "checks": snapshot_checks,
    }

    row = EventLog(
        device_id=None,
        severity=_severity_for_readiness(snapshot_payload["readiness"]["status"]),
        event_id=KPI_READINESS_SNAPSHOT_EVENT_ID,
        message=json.dumps(snapshot_payload, ensure_ascii=False, separators=(",", ":"), default=str),
        source=str(source or KPI_READINESS_SNAPSHOT_SOURCE),
        timestamp=datetime.now(),
    )
    db.add(row)
    db.flush()
    if commit:
        db.commit()

    return {
        "event_log_id": int(row.id or 0),
        "event_id": KPI_READINESS_SNAPSHOT_EVENT_ID,
        "source": row.source,
        "severity": row.severity,
        "payload": snapshot_payload,
    }


def _serialize_kpi_snapshot_row(row: EventLog) -> dict[str, Any] | None:
    payload = _to_json_dict(row.message)
    if not payload:
        return None

    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else {}
    scope = payload.get("scope") if isinstance(payload.get("scope"), dict) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
    checks = _snapshot_checks_from_payload(payload)

    generated_at = payload.get("generated_at")
    if generated_at is None:
        generated_at = int(getattr(row, "timestamp", datetime.now()).timestamp())
    try:
        generated_at = int(generated_at)
    except Exception:
        generated_at = int(getattr(row, "timestamp", datetime.now()).timestamp())

    generated_dt = datetime.fromtimestamp(generated_at, tz=timezone.utc)

    return {
        "event_log_id": int(getattr(row, "id", 0) or 0),
        "generated_at": generated_at,
        "generated_at_utc": generated_dt.isoformat(),
        "generated_date": generated_dt.date().isoformat(),
        "severity": str(getattr(row, "severity", "") or ""),
        "source": str(getattr(row, "source", "") or ""),
        "run_type": str(payload.get("run_type") or "manual"),
        "scope": {
            "site_id": scope.get("site_id"),
            "discovery_days": scope.get("discovery_days"),
            "discovery_limit": scope.get("discovery_limit"),
            "require_sample_minimums": bool(scope.get("require_sample_minimums")),
        },
        "readiness": {
            "status": str(readiness.get("status") or "insufficient_data"),
            "required_checks_total": int(readiness.get("required_checks_total") or 0),
            "pass_count": int(readiness.get("pass_count") or 0),
            "fail_count": int(readiness.get("fail_count") or 0),
            "unknown_count": int(readiness.get("unknown_count") or 0),
            "failed_check_ids": [str(x) for x in list(readiness.get("failed_check_ids") or [])],
            "unknown_check_ids": [str(x) for x in list(readiness.get("unknown_check_ids") or [])],
        },
        "evidence": {
            "sample_minimums_enforced": bool(evidence.get("sample_minimums_enforced")),
            "sample_totals": evidence.get("sample_totals") if isinstance(evidence.get("sample_totals"), dict) else {},
            "sample_thresholds": evidence.get("sample_thresholds") if isinstance(evidence.get("sample_thresholds"), dict) else {},
            "sample_coverage": (
                evidence.get("sample_coverage")
                if isinstance(evidence.get("sample_coverage"), dict)
                else _build_sample_coverage(
                    evidence.get("sample_totals") if isinstance(evidence.get("sample_totals"), dict) else {},
                    evidence.get("sample_thresholds") if isinstance(evidence.get("sample_thresholds"), dict) else {},
                )
            ),
        },
        "checks": checks,
    }


@router.get("/observability")
def observability_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    if not _toggle_enabled():
        raise HTTPException(status_code=404, detail="Observability toggle is disabled.")
    enabled = _logical_observability_enabled(db)
    warning = None
    if _docker_runtime_available():
        containers = [_inspect_container(n) for n in OBSERVABILITY_CONTAINERS]
    else:
        containers = [
            {
                "name": name,
                "exists": None,
                "status": "unavailable_no_docker_socket",
                "running": None,
            }
            for name in OBSERVABILITY_CONTAINERS
        ]
        warning = "Docker socket is unavailable in backend container; this toggle controls collection state only."
    return {
        "enabled": bool(enabled),
        "containers": containers,
        "control_mode": "logical",
        "managed_by": "compose",
        "warning": warning,
    }


@router.post("/observability")
def observability_set(
    req: ObservabilitySetRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    if not _toggle_enabled():
        raise HTTPException(status_code=404, detail="Observability toggle is disabled.")
    _set_logical_observability_enabled(db, bool(req.enabled))
    warning = None
    if _docker_runtime_available():
        containers = [_inspect_container(n) for n in OBSERVABILITY_CONTAINERS]
    else:
        containers = [
            {
                "name": name,
                "exists": None,
                "status": "logical_on" if bool(req.enabled) else "logical_off",
                "running": bool(req.enabled),
            }
            for name in OBSERVABILITY_CONTAINERS
        ]
        warning = "Docker socket is unavailable in backend container; container start/stop is managed by compose."
    return {
        "enabled": bool(req.enabled),
        "containers": containers,
        "control_mode": "logical",
        "managed_by": "compose",
        "warning": warning,
    }


@router.get("/self-health")
def self_health(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    uptime_seconds = None
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            uptime_seconds = float(f.read().split()[0])
    except Exception:
        pass

    load1 = load5 = load15 = None
    try:
        load1, load5, load15 = os.getloadavg()
    except Exception:
        pass

    mem = _get_cgroup_memory()

    disks: list[dict[str, Any]] = []
    for p in ["/", "/app", "/var/log/netsphere"]:
        d = _disk_usage(p)
        if d and all(x.get("path") != d["path"] for x in disks):
            disks.append(d)

    cpu_percent = _get_cpu_percent()

    services = _docker_compose_related_status()

    return {
        "ok": True,
        "timestamp": time.time(),
        "uptime_seconds": uptime_seconds,
        "cpu": {
            "percent": cpu_percent,
            "cores": os.cpu_count(),
            "load1": load1,
            "load5": load5,
            "load15": load15,
        },
        "memory": mem,
        "disks": disks,
        "services": services,
    }


@router.get("/support-matrix")
def support_matrix(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return {
        "policy_translators": PolicyTranslator.support_matrix(),
        "inventory_parsers": inventory_parser_support_matrix(),
        "fallback_mode": "read_only_manual_approval",
    }


@router.get("/kpi/readiness")
def kpi_readiness(
    site_id: int | None = Query(default=None),
    discovery_days: int = Query(default=30, ge=1, le=90),
    discovery_limit: int = Query(default=300, ge=1, le=1000),
    plug_scan_first_map_p50_max_seconds: int = Query(default=300, ge=1, le=86400),
    plug_scan_first_map_p95_max_seconds: int = Query(default=900, ge=1, le=86400),
    plug_scan_auto_reflection_min_pct: float = Query(default=75.0, ge=0, le=100),
    plug_scan_false_positive_max_pct: float = Query(default=10.0, ge=0, le=100),
    change_success_min_pct: float = Query(default=98.0, ge=0, le=100),
    change_failure_max_pct: float = Query(default=1.0, ge=0, le=100),
    change_rollback_p95_max_ms: int = Query(default=180000, ge=0, le=3600000),
    change_trace_coverage_min_pct: float = Query(default=100.0, ge=0, le=100),
    autonomy_auto_action_min_pct: float = Query(default=60.0, ge=0, le=100),
    autonomy_operator_intervention_max_pct: float = Query(default=40.0, ge=0, le=100),
    autonomy_mttd_baseline_seconds: float | None = Query(default=None, ge=0),
    autonomy_mttr_baseline_seconds: float | None = Query(default=None, ge=0),
    autonomy_mttd_improvement_min_pct: float = Query(default=30.0, ge=0, le=100),
    autonomy_mttr_improvement_min_pct: float = Query(default=40.0, ge=0, le=100),
    northbound_success_min_pct: float = Query(default=95.0, ge=0, le=100),
    northbound_p95_attempts_max: int = Query(default=3, ge=1, le=50),
    northbound_failed_24h_max: int = Query(default=5, ge=0, le=100000),
    require_sample_minimums: bool = Query(default=False),
    sample_min_discovery_jobs: int = Query(default=DEFAULT_KPI_SAMPLE_MINIMUMS["discovery_jobs"], ge=1, le=100000),
    sample_min_change_events: int = Query(default=DEFAULT_KPI_SAMPLE_MINIMUMS["change_events"], ge=1, le=100000),
    sample_min_northbound_deliveries: int = Query(default=DEFAULT_KPI_SAMPLE_MINIMUMS["northbound_deliveries"], ge=1, le=100000),
    sample_min_autonomy_issues_created: int = Query(default=DEFAULT_KPI_SAMPLE_MINIMUMS["autonomy_issues_created"], ge=1, le=100000),
    sample_min_autonomy_actions_executed: int = Query(default=DEFAULT_KPI_SAMPLE_MINIMUMS["autonomy_actions_executed"], ge=1, le=100000),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    from app.api.v1.endpoints import discovery as discovery_ep
    from app.api.v1.endpoints import misc as misc_ep

    discovery_summary = discovery_ep.get_kpi_summary(
        days=int(discovery_days),
        limit=int(discovery_limit),
        site_id=site_id,
        db=db,
        current_user=current_user,
    )
    discovery_data = _unwrap_api_payload(discovery_summary)
    discovery_kpi = discovery_data.get("kpi") if isinstance(discovery_data.get("kpi"), dict) else {}
    discovery_totals = discovery_data.get("totals") if isinstance(discovery_data.get("totals"), dict) else {}

    dashboard_raw = misc_ep.get_dashboard_stats(
        site_id=site_id,
        db=db,
        current_user=current_user,
    )
    dashboard_data = _read_json_response_payload(dashboard_raw)
    change_kpi = dashboard_data.get("change_kpi") if isinstance(dashboard_data.get("change_kpi"), dict) else {}
    autonomy_kpi = dashboard_data.get("autonomy_kpi") if isinstance(dashboard_data.get("autonomy_kpi"), dict) else {}
    northbound_kpi = dashboard_data.get("northbound_kpi") if isinstance(dashboard_data.get("northbound_kpi"), dict) else {}
    change_totals = change_kpi.get("totals") if isinstance(change_kpi.get("totals"), dict) else {}
    autonomy_totals = autonomy_kpi.get("totals") if isinstance(autonomy_kpi.get("totals"), dict) else {}
    northbound_totals = northbound_kpi.get("totals") if isinstance(northbound_kpi.get("totals"), dict) else {}

    checks: list[dict[str, Any]] = []

    checks.append(
        _build_check(
            check_id="plug_scan.first_map_p50_seconds",
            title="Plug & Scan first map P50",
            value=discovery_kpi.get("first_map_seconds_median"),
            threshold=int(plug_scan_first_map_p50_max_seconds),
            operator="<=",
            source="discovery.kpi.summary",
        )
    )
    checks.append(
        _build_check(
            check_id="plug_scan.first_map_p95_seconds",
            title="Plug & Scan first map P95",
            value=discovery_kpi.get("first_map_seconds_p95"),
            threshold=int(plug_scan_first_map_p95_max_seconds),
            operator="<=",
            source="discovery.kpi.summary",
        )
    )
    checks.append(
        _build_check(
            check_id="plug_scan.auto_reflection_rate_pct",
            title="Plug & Scan auto reflection rate",
            value=discovery_kpi.get("auto_reflection_rate_pct"),
            threshold=float(plug_scan_auto_reflection_min_pct),
            operator=">=",
            source="discovery.kpi.summary",
        )
    )
    checks.append(
        _build_check(
            check_id="plug_scan.false_positive_rate_pct",
            title="Plug & Scan false positive rate",
            value=discovery_kpi.get("false_positive_rate_pct"),
            threshold=float(plug_scan_false_positive_max_pct),
            operator="<=",
            source="discovery.kpi.summary",
        )
    )

    checks.append(
        _build_check(
            check_id="change.success_rate_pct",
            title="Change success rate",
            value=change_kpi.get("change_success_rate_pct"),
            threshold=float(change_success_min_pct),
            operator=">=",
            source="sdn.dashboard.stats.change_kpi",
        )
    )
    checks.append(
        _build_check(
            check_id="change.failure_rate_pct",
            title="Change failure rate",
            value=change_kpi.get("change_failure_rate_pct"),
            threshold=float(change_failure_max_pct),
            operator="<=",
            source="sdn.dashboard.stats.change_kpi",
        )
    )
    checks.append(
        _build_check(
            check_id="change.rollback_p95_ms",
            title="Change rollback P95",
            value=change_kpi.get("rollback_p95_ms"),
            threshold=int(change_rollback_p95_max_ms),
            operator="<=",
            source="sdn.dashboard.stats.change_kpi",
        )
    )
    checks.append(
        _build_check(
            check_id="change.trace_coverage_pct",
            title="Approval trace coverage",
            value=change_kpi.get("approval_execution_trace_coverage_pct"),
            threshold=float(change_trace_coverage_min_pct),
            operator=">=",
            source="sdn.dashboard.stats.change_kpi",
        )
    )

    checks.append(
        _build_check(
            check_id="autonomy.auto_action_rate_pct",
            title="Autonomy auto action rate",
            value=autonomy_kpi.get("auto_action_rate_pct"),
            threshold=float(autonomy_auto_action_min_pct),
            operator=">=",
            source="sdn.dashboard.stats.autonomy_kpi",
        )
    )
    checks.append(
        _build_check(
            check_id="autonomy.operator_intervention_rate_pct",
            title="Autonomy operator intervention rate",
            value=autonomy_kpi.get("operator_intervention_rate_pct"),
            threshold=float(autonomy_operator_intervention_max_pct),
            operator="<=",
            source="sdn.dashboard.stats.autonomy_kpi",
        )
    )

    mttd_now = _num(autonomy_kpi.get("mttd_seconds"))
    mttr_now = _num(autonomy_kpi.get("mttr_seconds"))
    mttd_improvement = None
    mttr_improvement = None
    if autonomy_mttd_baseline_seconds is not None and autonomy_mttd_baseline_seconds > 0 and mttd_now is not None:
        mttd_improvement = round(
            max(-100.0, min(100.0, ((float(autonomy_mttd_baseline_seconds) - float(mttd_now)) / float(autonomy_mttd_baseline_seconds)) * 100.0)),
            2,
        )
    if autonomy_mttr_baseline_seconds is not None and autonomy_mttr_baseline_seconds > 0 and mttr_now is not None:
        mttr_improvement = round(
            max(-100.0, min(100.0, ((float(autonomy_mttr_baseline_seconds) - float(mttr_now)) / float(autonomy_mttr_baseline_seconds)) * 100.0)),
            2,
        )

    checks.append(
        _build_check(
            check_id="autonomy.mttd_improvement_pct",
            title="MTTD improvement vs baseline",
            value=mttd_improvement,
            threshold=float(autonomy_mttd_improvement_min_pct),
            operator=">=",
            source="sdn.dashboard.stats.autonomy_kpi",
            required=False,
        )
    )
    checks.append(
        _build_check(
            check_id="autonomy.mttr_improvement_pct",
            title="MTTR improvement vs baseline",
            value=mttr_improvement,
            threshold=float(autonomy_mttr_improvement_min_pct),
            operator=">=",
            source="sdn.dashboard.stats.autonomy_kpi",
            required=False,
        )
    )

    checks.append(
        _build_check(
            check_id="northbound.success_rate_pct",
            title="Northbound delivery success rate",
            value=northbound_kpi.get("success_rate_pct"),
            threshold=float(northbound_success_min_pct),
            operator=">=",
            source="sdn.dashboard.stats.northbound_kpi",
        )
    )
    checks.append(
        _build_check(
            check_id="northbound.p95_attempts",
            title="Northbound delivery attempts P95",
            value=northbound_kpi.get("p95_attempts"),
            threshold=int(northbound_p95_attempts_max),
            operator="<=",
            source="sdn.dashboard.stats.northbound_kpi",
        )
    )
    checks.append(
        _build_check(
            check_id="northbound.failed_24h",
            title="Northbound failed deliveries (24h)",
            value=(northbound_totals.get("failed_24h") if northbound_totals else None),
            threshold=int(northbound_failed_24h_max),
            operator="<=",
            source="sdn.dashboard.stats.northbound_kpi",
        )
    )

    sample_totals = {
        "discovery_jobs": int(discovery_data.get("jobs_count") or 0),
        "change_events": int(change_totals.get("events") or 0),
        "northbound_deliveries": int(northbound_totals.get("deliveries") or 0),
        "autonomy_issues_created": int(autonomy_totals.get("issues_created") or 0),
        "autonomy_actions_executed": int(autonomy_totals.get("actions_executed") or 0),
    }
    sample_thresholds = {
        "discovery_jobs": int(sample_min_discovery_jobs),
        "change_events": int(sample_min_change_events),
        "northbound_deliveries": int(sample_min_northbound_deliveries),
        "autonomy_issues_created": int(sample_min_autonomy_issues_created),
        "autonomy_actions_executed": int(sample_min_autonomy_actions_executed),
    }
    sample_coverage = _build_sample_coverage(sample_totals, sample_thresholds)

    checks.append(
        _build_check(
            check_id="sample.discovery.jobs_count",
            title="Sample minimum: discovery jobs",
            value=sample_totals["discovery_jobs"],
            threshold=sample_thresholds["discovery_jobs"],
            operator=">=",
            source="ops.kpi.readiness.sample_gate",
            required=bool(require_sample_minimums),
        )
    )
    checks.append(
        _build_check(
            check_id="sample.change.events",
            title="Sample minimum: change events",
            value=sample_totals["change_events"],
            threshold=sample_thresholds["change_events"],
            operator=">=",
            source="ops.kpi.readiness.sample_gate",
            required=bool(require_sample_minimums),
        )
    )
    checks.append(
        _build_check(
            check_id="sample.northbound.deliveries",
            title="Sample minimum: northbound deliveries",
            value=sample_totals["northbound_deliveries"],
            threshold=sample_thresholds["northbound_deliveries"],
            operator=">=",
            source="ops.kpi.readiness.sample_gate",
            required=bool(require_sample_minimums),
        )
    )
    checks.append(
        _build_check(
            check_id="sample.autonomy.issues_created",
            title="Sample minimum: autonomy issues created",
            value=sample_totals["autonomy_issues_created"],
            threshold=sample_thresholds["autonomy_issues_created"],
            operator=">=",
            source="ops.kpi.readiness.sample_gate",
            required=bool(require_sample_minimums),
        )
    )
    checks.append(
        _build_check(
            check_id="sample.autonomy.actions_executed",
            title="Sample minimum: autonomy actions executed",
            value=sample_totals["autonomy_actions_executed"],
            threshold=sample_thresholds["autonomy_actions_executed"],
            operator=">=",
            source="ops.kpi.readiness.sample_gate",
            required=bool(require_sample_minimums),
        )
    )

    required_checks = [c for c in checks if bool(c.get("required", True))]
    fail_count = sum(1 for c in required_checks if c.get("status") == "fail")
    pass_count = sum(1 for c in required_checks if c.get("status") == "pass")
    unknown_count = sum(1 for c in required_checks if c.get("status") == "unknown")

    if fail_count > 0:
        overall_status = "critical" if fail_count >= 3 else "warning"
    elif unknown_count > 0:
        overall_status = "insufficient_data"
    else:
        overall_status = "healthy"

    return {
        "generated_at": int(time.time()),
        "scope": {
            "site_id": int(site_id) if site_id is not None else None,
            "discovery_days": int(discovery_days),
            "discovery_limit": int(discovery_limit),
            "require_sample_minimums": bool(require_sample_minimums),
        },
        "readiness": {
            "status": overall_status,
            "required_checks_total": int(len(required_checks)),
            "pass_count": int(pass_count),
            "fail_count": int(fail_count),
            "unknown_count": int(unknown_count),
        },
        "checks": checks,
        "snapshots": {
            "discovery": {
                "jobs_count": int(discovery_data.get("jobs_count") or 0),
                "totals": discovery_totals,
                "kpi": discovery_kpi,
            },
            "change_kpi": change_kpi,
            "autonomy_kpi": autonomy_kpi,
            "northbound_kpi": northbound_kpi,
        },
        "evidence": {
            "sample_minimums_enforced": bool(require_sample_minimums),
            "sample_totals": sample_totals,
            "sample_thresholds": sample_thresholds,
            "sample_coverage": sample_coverage,
        },
    }


@router.post("/kpi/readiness/snapshot")
def create_kpi_readiness_snapshot(
    site_id: int | None = Query(default=None),
    discovery_days: int = Query(default=30, ge=1, le=90),
    discovery_limit: int = Query(default=300, ge=1, le=1000),
    require_sample_minimums: bool = Query(default=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    readiness_payload = kpi_readiness(
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
        sample_min_discovery_jobs=DEFAULT_KPI_SAMPLE_MINIMUMS["discovery_jobs"],
        sample_min_change_events=DEFAULT_KPI_SAMPLE_MINIMUMS["change_events"],
        sample_min_northbound_deliveries=DEFAULT_KPI_SAMPLE_MINIMUMS["northbound_deliveries"],
        sample_min_autonomy_issues_created=DEFAULT_KPI_SAMPLE_MINIMUMS["autonomy_issues_created"],
        sample_min_autonomy_actions_executed=DEFAULT_KPI_SAMPLE_MINIMUMS["autonomy_actions_executed"],
        db=db,
        current_user=current_user,
    )
    snapshot = persist_kpi_readiness_snapshot(
        db,
        readiness_payload,
        source=KPI_READINESS_SNAPSHOT_SOURCE,
        run_type="manual_api",
        commit=True,
    )
    return {
        "generated_at": readiness_payload.get("generated_at"),
        "readiness": readiness_payload.get("readiness"),
        "snapshot": snapshot,
    }


@router.get("/kpi/readiness/history")
def get_kpi_readiness_history(
    days: int = Query(default=30, ge=1, le=180),
    limit: int = Query(default=90, ge=1, le=1000),
    site_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    status_filter = str(status or "").strip().lower() or None
    if status_filter and status_filter not in KPI_READINESS_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status filter. Allowed values: {', '.join(sorted(KPI_READINESS_STATUSES))}",
        )

    since = datetime.now() - timedelta(days=int(days))
    query = (
        db.query(EventLog)
        .filter(
            EventLog.event_id == KPI_READINESS_SNAPSHOT_EVENT_ID,
            EventLog.timestamp >= since,
        )
        .order_by(EventLog.timestamp.desc())
        .limit(int(max(limit * 5, limit)))
    )
    rows = query.all()

    items: list[dict[str, Any]] = []
    for row in rows:
        item = _serialize_kpi_snapshot_row(row)
        if not item:
            continue
        if site_id is not None:
            item_site_id = item.get("scope", {}).get("site_id")
            try:
                item_site_id_num = int(item_site_id) if item_site_id is not None else None
            except Exception:
                item_site_id_num = None
            if item_site_id_num is None or item_site_id_num != int(site_id):
                continue
        if status_filter and str(item.get("readiness", {}).get("status") or "").strip().lower() != status_filter:
            continue
        items.append(item)
        if len(items) >= int(limit):
            break

    history_summary = _summarize_readiness_history(items, int(days))

    return {
        "range": {
            "days": int(days),
            "since": int(since.timestamp()),
            "limit": int(limit),
        },
        "filters": {
            "site_id": int(site_id) if site_id is not None else None,
            "status": status_filter,
        },
        "totals": history_summary.get("totals") or {"count": int(len(items)), "by_status": {}},
        "latest": items[0] if items else None,
        "previous": items[1] if len(items) > 1 else None,
        "coverage": history_summary.get("coverage") or {},
        "comparison": history_summary.get("comparison") or {},
        "current_streak": history_summary.get("current_streak") or {},
        "latest_failed_checks": history_summary.get("latest_failed_checks") or [],
        "latest_unknown_checks": history_summary.get("latest_unknown_checks") or [],
        "top_failing_checks": history_summary.get("top_failing_checks") or [],
        "top_unknown_checks": history_summary.get("top_unknown_checks") or [],
        "sample_coverage_latest": history_summary.get("sample_coverage_latest") or {},
        "trend_by_day": history_summary.get("trend_by_day") or [],
        "items": items,
    }


@router.get("/release-evidence")
def get_release_evidence(
    refresh: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    payload = get_release_evidence_snapshot(refresh=bool(refresh))
    if isinstance(payload, dict):
        payload["refresh"] = get_release_evidence_refresh_status()
        payload["automation"] = _build_release_evidence_automation_policy(db)
    return payload


@router.post("/release-evidence/refresh")
def refresh_release_evidence(
    profile: str = Query(default="ci"),
    include_synthetic: bool = Query(default=True),
    current_user: User = Depends(deps.require_operator),
):
    try:
        return start_release_evidence_refresh(
            profile=profile,
            include_synthetic=bool(include_synthetic),
            trigger_source="api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/release-evidence/bundle")
def download_release_evidence_bundle(
    refresh: bool = Query(default=False),
    current_user: User = Depends(deps.require_viewer),
):
    data = build_release_evidence_bundle(refresh=bool(refresh))
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"release_evidence_bundle_{ts}.zip"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/pro/operator-package")
def download_pro_operator_package(
    support_days: int = Query(default=7, ge=1, le=30),
    support_limit_per_table: int = Query(default=5000, ge=100, le=50000),
    include_app_log: bool = Query(default=True),
    refresh_release_evidence: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    data = build_pro_operator_package(
        db,
        support_days=int(support_days),
        support_limit_per_table=int(support_limit_per_table),
        include_app_log=bool(include_app_log),
        refresh_release_evidence=bool(refresh_release_evidence),
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"pro_operator_package_{ts}.zip"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/operations-review-bundle")
def download_operations_review_bundle(
    refresh_release_evidence: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    data = build_operations_review_bundle(
        db,
        refresh_release_evidence=bool(refresh_release_evidence),
    )
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"operations_review_bundle_{ts}.zip"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
