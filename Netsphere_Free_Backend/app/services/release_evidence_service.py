from __future__ import annotations

import copy
import io
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from app.db.session import SessionLocal
from app.models.settings import SystemSetting

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent
REPORT_CACHE_DIR = BACKEND_ROOT / "reports_cache"
RELEASE_EVIDENCE_CACHE_PATH = REPORT_CACHE_DIR / "release-evidence.latest.json"
RELEASE_EVIDENCE_REFRESH_STATUS_PATH = REPORT_CACHE_DIR / "release-evidence.refresh-status.json"

REPORT_SOURCE_CANDIDATES: dict[str, tuple[Path, ...]] = {
    "kpi_readiness": (
        REPORT_CACHE_DIR / "kpi-readiness-30d-latest.json",
        PROJECT_ROOT / "docs" / "reports" / "kpi-readiness-30d-latest.json",
    ),
    "vendor_support": (
        REPORT_CACHE_DIR / "vendor-support-matrix.latest.json",
        PROJECT_ROOT / "docs" / "reports" / "vendor-support-matrix.latest.json",
    ),
    "synthetic_validation": (
        REPORT_CACHE_DIR / "synthetic-validation-matrix.latest.json",
        PROJECT_ROOT / "docs" / "reports" / "synthetic-validation-matrix.latest.json",
    ),
    "northbound_soak": (
        REPORT_CACHE_DIR / "northbound-soak-72h-latest.json",
        PROJECT_ROOT / "docs" / "reports" / "northbound-soak-72h-latest.json",
    ),
    "northbound_probe": (
        REPORT_CACHE_DIR / "northbound-soak-probe.latest.json",
        PROJECT_ROOT / "docs" / "reports" / "northbound-soak-probe.latest.json",
    ),
}
REPORT_MIRROR_SPECS: dict[str, tuple[Path, ...]] = {
    "kpi-readiness-30d-latest.json": (PROJECT_ROOT / "docs" / "reports" / "kpi-readiness-30d-latest.json",),
    "kpi-readiness-30d-latest.md": (PROJECT_ROOT / "docs" / "reports" / "kpi-readiness-30d-latest.md",),
    "vendor-support-matrix.latest.json": (PROJECT_ROOT / "docs" / "reports" / "vendor-support-matrix.latest.json",),
    "vendor-support-matrix.latest.md": (PROJECT_ROOT / "docs" / "reports" / "vendor-support-matrix.latest.md",),
    "real-device-acceptance.latest.json": (PROJECT_ROOT / "docs" / "reports" / "real-device-acceptance.latest.json",),
    "real-device-acceptance.latest.md": (PROJECT_ROOT / "docs" / "reports" / "real-device-acceptance.latest.md",),
    "real-device-acceptance-checklist.latest.csv": (PROJECT_ROOT / "docs" / "reports" / "real-device-acceptance-checklist.latest.csv",),
    "synthetic-validation-matrix.latest.json": (PROJECT_ROOT / "docs" / "reports" / "synthetic-validation-matrix.latest.json",),
    "synthetic-validation-matrix.latest.md": (PROJECT_ROOT / "docs" / "reports" / "synthetic-validation-matrix.latest.md",),
    "northbound-soak-72h-latest.json": (PROJECT_ROOT / "docs" / "reports" / "northbound-soak-72h-latest.json",),
    "northbound-soak-72h-latest.md": (PROJECT_ROOT / "docs" / "reports" / "northbound-soak-72h-latest.md",),
    "northbound-soak-probe.latest.json": (PROJECT_ROOT / "docs" / "reports" / "northbound-soak-probe.latest.json",),
    "northbound-soak-probe.latest.md": (PROJECT_ROOT / "docs" / "reports" / "northbound-soak-probe.latest.md",),
}
RUNBOOK_MIRROR_SPECS: dict[str, Path] = {
    "KPI_READINESS_RUNBOOK.md": PROJECT_ROOT / "docs" / "KPI_READINESS_RUNBOOK.md",
    "NORTHBOUND_72H_SOAK_RUNBOOK.md": PROJECT_ROOT / "docs" / "NORTHBOUND_72H_SOAK_RUNBOOK.md",
    "VENDOR_SUPPORT_POLICY.md": PROJECT_ROOT / "docs" / "VENDOR_SUPPORT_POLICY.md",
    "RELEASE_GATE_RUNBOOK.md": PROJECT_ROOT / "docs" / "RELEASE_GATE_RUNBOOK.md",
    "cloud-operational-test-plan.md": PROJECT_ROOT / "docs" / "cloud-operational-test-plan.md",
    "REAL_DEVICE_ACCEPTANCE_RUNBOOK.md": PROJECT_ROOT / "docs" / "operational-validation" / "REAL_DEVICE_ACCEPTANCE_RUNBOOK.md",
}
RUNBOOK_CACHE_DIR = REPORT_CACHE_DIR / "runbooks"
RELEASE_EVIDENCE_REFRESH_TIMEOUT_SECONDS = 600
RELEASE_EVIDENCE_REFRESH_PROFILES = {"local", "ci", "release"}
RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE = "ci"
RELEASE_EVIDENCE_REFRESH_ENABLED_SETTING_KEY = "release_evidence_refresh_enabled"
RELEASE_EVIDENCE_REFRESH_PROFILE_SETTING_KEY = "release_evidence_refresh_profile"
RELEASE_EVIDENCE_REFRESH_INCLUDE_SYNTHETIC_SETTING_KEY = "release_evidence_refresh_include_synthetic"
RELEASE_EVIDENCE_REFRESH_INCLUDE_NORTHBOUND_PROBE_SETTING_KEY = "release_evidence_refresh_include_northbound_probe"
RELEASE_EVIDENCE_REFRESH_LOCK_KEY = "release_evidence_refresh_lock_until"
RELEASE_EVIDENCE_REFRESH_LOCK_TTL_SECONDS = RELEASE_EVIDENCE_REFRESH_TIMEOUT_SECONDS + 120
RELEASE_EVIDENCE_AUTOMATION_TIMEZONE = "Asia/Seoul"
RELEASE_EVIDENCE_AUTOMATION_HOUR = 4
RELEASE_EVIDENCE_AUTOMATION_MINUTE = 30
SYNTHETIC_VALIDATION_SCRIPT = BACKEND_ROOT / "tools" / "run_synthetic_validation_matrix.py"
NORTHBOUND_SOAK_PROBE_SCRIPT = BACKEND_ROOT / "tools" / "run_northbound_soak_verification.py"
OPS_KPI_SAMPLE_COLLECTION_SCRIPT = BACKEND_ROOT / "tools" / "run_ops_kpi_sample_collection.py"
KPI_READINESS_EXPORT_SCRIPT = BACKEND_ROOT / "tools" / "export_kpi_readiness_report.py"
RELEASE_EVIDENCE_CACHE_SCRIPT = BACKEND_ROOT / "tools" / "build_release_evidence_cache.py"
NORTHBOUND_PROBE_BASE_URL_ENV = "NETSPHERE_RELEASE_EVIDENCE_BASE_URL"
NORTHBOUND_PROBE_TOKEN_ENV = "NETSPHERE_RELEASE_EVIDENCE_TOKEN"
NORTHBOUND_PROBE_LOGIN_USERNAME_ENV = "NETSPHERE_RELEASE_EVIDENCE_LOGIN_USERNAME"
NORTHBOUND_PROBE_LOGIN_PASSWORD_ENV = "NETSPHERE_RELEASE_EVIDENCE_LOGIN_PASSWORD"
NORTHBOUND_PROBE_FILENAME_PREFIX = "northbound-soak-probe"
NORTHBOUND_PROBE_PROFILE_SPECS: dict[str, dict[str, float | int]] = {
    "local": {"duration_hours": 0.0025, "interval_seconds": 2.0, "timeout_seconds": 90},
    "ci": {"duration_hours": 0.005, "interval_seconds": 2.0, "timeout_seconds": 120},
    "release": {"duration_hours": 0.015, "interval_seconds": 5.0, "timeout_seconds": 180},
}

_STATUS_RANK = {
    "healthy": 0,
    "in_progress": 1,
    "warning": 2,
    "critical": 3,
    "unavailable": 4,
}
_SAMPLE_LABELS = {
    "discovery_jobs": "Discovery jobs",
    "change_events": "Change events",
    "northbound_deliveries": "Northbound deliveries",
    "autonomy_issues_created": "Autonomy issues created",
    "autonomy_actions_executed": "Autonomy actions executed",
}
_VENDOR_READINESS_RANK = {
    "none": 0,
    "partial": 1,
    "basic": 2,
    "extended": 3,
    "full": 4,
}


class ReleaseEvidenceRefreshError(RuntimeError):
    def __init__(
        self,
        *,
        stage: str,
        message: str,
        returncode: int | None = None,
        output_tail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.stage = stage
        self.returncode = returncode
        self.output_tail = output_tail


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return default
    if parsed != parsed:
        return default
    return parsed


def _normalize_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    for parser in (
        lambda: datetime.fromisoformat(text),
        lambda: datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc),
    ):
        try:
            parsed = parser()
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except Exception:
            continue
    return None


def _parse_normalized_datetime(value: Any) -> datetime | None:
    normalized = _normalize_timestamp(value)
    if not normalized:
        return None
    try:
        return datetime.fromisoformat(normalized)
    except Exception:
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
        encoding="utf-8",
    )
    temp_path.replace(path)
    return path


def _default_refresh_state() -> dict[str, Any]:
    return {
        "status": "idle",
        "stage": "idle",
        "profile": None,
        "include_synthetic": True,
        "include_northbound_probe": False,
        "started_at": None,
        "finished_at": None,
        "duration_seconds": None,
        "trigger_source": None,
        "error": None,
        "last_success_at": None,
        "last_summary": None,
        "steps": [],
        "output_tail": None,
    }


def _normalize_refresh_state(payload: dict[str, Any] | None) -> dict[str, Any]:
    state = _default_refresh_state()
    if isinstance(payload, dict):
        for key in state.keys():
            if key in payload:
                state[key] = copy.deepcopy(payload[key])
    profile = str(state.get("profile") or "").strip().lower() or None
    if profile is not None and profile not in RELEASE_EVIDENCE_REFRESH_PROFILES:
        profile = RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE
    state["profile"] = profile
    state["include_synthetic"] = bool(state.get("include_synthetic", True))
    state["include_northbound_probe"] = bool(state.get("include_northbound_probe", False))
    state["status"] = normalize_refresh_status_token(state.get("status"), default="idle")
    state["stage"] = normalize_refresh_status_token(state.get("stage"), default="idle")
    state["steps"] = list(state.get("steps") or [])
    state["error"] = copy.deepcopy(state.get("error")) if isinstance(state.get("error"), dict) else None
    state["last_summary"] = (
        copy.deepcopy(state.get("last_summary")) if isinstance(state.get("last_summary"), dict) else None
    )
    state["output_tail"] = _tail_text(state.get("output_tail"))
    return state


def normalize_refresh_status_token(value: Any, *, default: str = "idle") -> str:
    token = str(value or "").strip().lower().replace(" ", "_")
    return token or str(default)


def load_release_evidence_refresh_status(path: Path | None = None) -> dict[str, Any] | None:
    target = path or RELEASE_EVIDENCE_REFRESH_STATUS_PATH
    payload = _read_json(target)
    if payload is None:
        return None
    return _normalize_refresh_state(payload)


def persist_release_evidence_refresh_status(
    payload: dict[str, Any],
    *,
    path: Path | None = None,
) -> dict[str, Any]:
    normalized = _normalize_refresh_state(payload)
    _write_json(path or RELEASE_EVIDENCE_REFRESH_STATUS_PATH, normalized)
    return normalized


def _claim_release_evidence_refresh_lock(ttl_seconds: int = RELEASE_EVIDENCE_REFRESH_LOCK_TTL_SECONDS) -> bool:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        lock_until = now + timedelta(seconds=max(60, int(ttl_seconds)))
        row = db.query(SystemSetting).filter(SystemSetting.key == RELEASE_EVIDENCE_REFRESH_LOCK_KEY).first()
        if row and row.value:
            try:
                expiry = datetime.fromisoformat(str(row.value))
                if expiry > now:
                    return False
            except Exception:
                pass
        if row is None:
            row = SystemSetting(
                key=RELEASE_EVIDENCE_REFRESH_LOCK_KEY,
                value=lock_until.isoformat(),
                description=RELEASE_EVIDENCE_REFRESH_LOCK_KEY,
                category="system",
            )
        else:
            row.value = lock_until.isoformat()
            if not row.category:
                row.category = "system"
        db.add(row)
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()


def _release_evidence_refresh_lock() -> None:
    db = SessionLocal()
    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == RELEASE_EVIDENCE_REFRESH_LOCK_KEY).first()
        if row:
            row.value = datetime.utcnow().isoformat()
            db.add(row)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _display_path(path: Path) -> str:
    for root in (PROJECT_ROOT, BACKEND_ROOT):
        try:
            return str(path.relative_to(root)).replace("\\", "/")
        except Exception:
            continue
    return path.name


def _read_first_json(paths: tuple[Path, ...]) -> tuple[dict[str, Any] | None, str | None]:
    for path in paths:
        payload = _read_json(path)
        if payload is not None:
            return payload, _display_path(path)
    return None, None


def _first_existing(paths: tuple[Path, ...]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _copy_asset(src: Path, dst: Path) -> bool:
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    except Exception:
        return False


def _tail_text(value: str | None, *, lines: int = 30, chars: int = 3000) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    rows = text.splitlines()
    if len(rows) > lines:
        rows = rows[-lines:]
    text = "\n".join(rows).strip()
    if len(text) > chars:
        text = text[-chars:]
    return text or None


def _display_name(value: str | None) -> str | None:
    text = str(value or "").strip()
    return Path(text).name if text else None


def _read_env_text(key: str, default: str = "") -> str:
    return str(os.getenv(key, default) or default).strip()


def get_release_evidence_northbound_probe_runtime() -> dict[str, Any]:
    token = _read_env_text(NORTHBOUND_PROBE_TOKEN_ENV)
    login_username = _read_env_text(NORTHBOUND_PROBE_LOGIN_USERNAME_ENV)
    login_password = str(os.getenv(NORTHBOUND_PROBE_LOGIN_PASSWORD_ENV, "") or "")
    direct_mode_available = bool(NORTHBOUND_SOAK_PROBE_SCRIPT.exists())
    if token:
        auth_mode = "token"
        auth_configured = True
        execution_mode = "api"
    elif login_username and login_password:
        auth_mode = "login"
        auth_configured = True
    else:
        auth_mode = None
        auth_configured = False
    execution_mode = "direct_db" if direct_mode_available else ("api" if auth_configured else None)
    return {
        "auth_configured": bool(auth_configured),
        "auth_mode": auth_mode,
        "direct_mode_available": bool(direct_mode_available),
        "execution_mode": execution_mode,
        "base_url": _read_env_text(NORTHBOUND_PROBE_BASE_URL_ENV, "http://localhost:8000") or "http://localhost:8000",
        "latest_probe_available": _first_existing(REPORT_SOURCE_CANDIDATES["northbound_probe"]) is not None,
    }


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
        observed = _safe_float(observed_raw, default=None)
        threshold = _safe_float(threshold_raw, default=None)
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


def _compact_check(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    check_id = str(row.get("id") or "").strip()
    if not check_id:
        return None
    return {
        "id": check_id,
        "title": str(row.get("title") or check_id),
        "status": str(row.get("status") or "unknown").strip().lower() or "unknown",
        "required": bool(row.get("required", True)),
        "value": row.get("value"),
        "threshold": row.get("threshold"),
        "operator": str(row.get("operator") or ""),
        "source": str(row.get("source") or ""),
    }


def _build_sample_rows(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    sample_totals = evidence.get("sample_totals") if isinstance(evidence.get("sample_totals"), dict) else {}
    sample_thresholds = evidence.get("sample_thresholds") if isinstance(evidence.get("sample_thresholds"), dict) else {}
    sample_coverage = evidence.get("sample_coverage") if isinstance(evidence.get("sample_coverage"), dict) else {}
    if not sample_coverage and (sample_totals or sample_thresholds):
        sample_coverage = _build_sample_coverage(sample_totals, sample_thresholds)
    rows: list[dict[str, Any]] = []
    for key in sorted(sample_coverage.keys()):
        entry = sample_coverage.get(key) if isinstance(sample_coverage.get(key), dict) else {}
        rows.append(
            {
                "id": str(key),
                "title": _SAMPLE_LABELS.get(str(key), str(key).replace("_", " ")),
                "observed": entry.get("observed", sample_totals.get(key)),
                "threshold": entry.get("threshold", sample_thresholds.get(key)),
                "coverage_pct": _safe_float(entry.get("coverage_pct"), default=None),
                "met": entry.get("met"),
                "deficit": _safe_float(entry.get("deficit"), default=None),
            }
        )
    rows.sort(
        key=lambda row: (
            0 if row.get("met") is False else 1,
            row.get("coverage_pct") if row.get("coverage_pct") is not None else 999999,
            str(row.get("id") or ""),
        )
    )
    return rows


def _failed_assertions(prefix: str, payload: dict[str, Any] | None) -> list[str]:
    rows: list[str] = []
    flags = payload.get("pass") if isinstance(payload, dict) and isinstance(payload.get("pass"), dict) else {}
    for key in sorted(flags.keys()):
        if flags.get(key) is False:
            rows.append(f"{prefix}.{key}")
    return rows


def _section_unavailable(section_id: str, title: str) -> dict[str, Any]:
    return {
        "id": section_id,
        "title": title,
        "available": False,
        "status": "unavailable",
        "accepted": False,
        "generated_at": None,
        "source_path": None,
        "summary": "No evidence available",
    }


def _build_kpi_section(payload: dict[str, Any] | None, source_path: str | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _section_unavailable("kpi_readiness", "30d KPI Readiness")
    report = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    readiness = report.get("readiness") if isinstance(report.get("readiness"), dict) else {}
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    coverage_rows = _build_sample_rows(evidence)
    checks = [compact for compact in (_compact_check(row if isinstance(row, dict) else {}) for row in list(report.get("checks") or [])) if compact]
    blocking_checks = [
        row
        for row in checks
        if row.get("required") is True and row.get("status") in {"fail", "unknown"}
    ]
    blocking_checks.sort(
        key=lambda row: (
            0 if row.get("status") == "fail" else 1,
            str(row.get("id") or ""),
        )
    )
    readiness_status = str(readiness.get("status") or "unavailable").strip().lower() or "unavailable"
    if readiness_status == "insufficient_data":
        status = "warning"
    elif readiness_status in {"healthy", "warning", "critical"}:
        status = readiness_status
    else:
        status = "unavailable"
    worst_coverage = min(
        (_safe_float(row.get("coverage_pct"), default=0.0) or 0.0 for row in coverage_rows),
        default=None,
    )
    met_count = sum(1 for row in coverage_rows if row.get("met") is True)
    return {
        "id": "kpi_readiness",
        "title": "30d KPI Readiness",
        "available": True,
        "status": status,
        "accepted": readiness_status == "healthy",
        "generated_at": _normalize_timestamp(payload.get("generated_at_utc") or report.get("generated_at")),
        "source_path": source_path,
        "source_name": _display_name(source_path),
        "summary": readiness_status,
        "readiness_status": readiness_status,
        "required_checks_total": _safe_int(readiness.get("required_checks_total")),
        "pass_count": _safe_int(readiness.get("pass_count")),
        "fail_count": _safe_int(readiness.get("fail_count")),
        "unknown_count": _safe_int(readiness.get("unknown_count")),
        "sample_coverage": {
            "met_count": met_count,
            "total": len(coverage_rows),
            "worst_pct": worst_coverage,
        },
        "details": {
            "blocking_checks": blocking_checks[:5],
            "sample_gaps": [row for row in coverage_rows if row.get("met") is not True][:5],
        },
    }


def _build_vendor_section(payload: dict[str, Any] | None, source_path: str | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _section_unavailable("vendor_support", "Vendor Support")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    readiness = summary.get("readiness") if isinstance(summary.get("readiness"), dict) else {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    coverage_pct = _safe_float(summary.get("coverage_pct"), default=0.0) or 0.0
    partial_count = _safe_int(readiness.get("partial"))
    none_count = _safe_int(readiness.get("none"))
    weakest_device_types: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        by_type = row.get("by_type") if isinstance(row.get("by_type"), dict) else {}
        weakest_device_types.append(
            {
                "device_type": str(row.get("device_type") or "").strip(),
                "readiness": str(row.get("readiness") or "none").strip().lower() or "none",
                "readiness_score": _safe_int(row.get("readiness_score")),
                "capabilities": sorted(str(key) for key in by_type.keys()),
                "driver_modes": [str(item) for item in list(row.get("driver_modes") or []) if str(item).strip()],
                "fixture_groups": [str(item) for item in list(row.get("fixture_groups") or []) if str(item).strip()],
            }
        )
    weakest_device_types = [
        row
        for row in weakest_device_types
        if row.get("device_type")
    ]
    weakest_device_types.sort(
        key=lambda row: (
            _VENDOR_READINESS_RANK.get(str(row.get("readiness") or "none"), 0),
            _safe_int(row.get("readiness_score")),
            str(row.get("device_type") or ""),
        )
    )
    if coverage_pct < 100.0 or none_count > 0:
        status = "critical"
    elif partial_count > 0:
        status = "warning"
    else:
        status = "healthy"
    return {
        "id": "vendor_support",
        "title": "Vendor Support",
        "available": True,
        "status": status,
        "accepted": coverage_pct >= 100.0 and partial_count == 0 and none_count == 0,
        "generated_at": _normalize_timestamp(payload.get("generated_at") or payload.get("source_report_generated_at")),
        "source_path": source_path,
        "source_name": _display_name(source_path),
        "summary": f"{_safe_int(summary.get('covered_device_types'))}/{_safe_int(summary.get('total_supported_device_types'))} covered",
        "coverage_pct": coverage_pct,
        "covered_device_types": _safe_int(summary.get("covered_device_types")),
        "total_supported_device_types": _safe_int(summary.get("total_supported_device_types")),
        "readiness": {
            "full": _safe_int(readiness.get("full")),
            "extended": _safe_int(readiness.get("extended")),
            "basic": _safe_int(readiness.get("basic")),
            "partial": partial_count,
            "none": none_count,
        },
        "details": {
            "weakest_device_types": weakest_device_types[:6],
        },
    }


def _build_synthetic_section(payload: dict[str, Any] | None, source_path: str | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _section_unavailable("synthetic_validation", "Synthetic Validation")
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    scenario_catalog = payload.get("scenario_catalog") if isinstance(payload.get("scenario_catalog"), dict) else {}
    soak_matrix = payload.get("soak_matrix") if isinstance(payload.get("soak_matrix"), dict) else {}
    eve_plan = payload.get("eve_plan") if isinstance(payload.get("eve_plan"), dict) else {}
    overall_pass = bool(summary.get("overall_pass") if "overall_pass" in summary else payload.get("overall_pass"))
    scenario_count = _safe_int(
        summary.get("checked_fixture_scenarios")
        if "checked_fixture_scenarios" in summary
        else (((payload.get("scenario_catalog") or {}).get("summary") or {}).get("scenario_count"))
    )
    soak_runs = _safe_int(
        summary.get("executed_soak_runs")
        if "executed_soak_runs" in summary
        else (((payload.get("soak_matrix") or {}).get("summary") or {}).get("run_count"))
    )
    total_events = _safe_int(
        summary.get("total_processed_events")
        if "total_processed_events" in summary
        else (((payload.get("soak_matrix") or {}).get("summary") or {}).get("total_processed_events"))
    )
    scenarios: list[dict[str, Any]] = []
    for row in list(scenario_catalog.get("scenarios") or []):
        if not isinstance(row, dict):
            continue
        counts = row.get("counts") if isinstance(row.get("counts"), dict) else {}
        severities = row.get("severities") if isinstance(row.get("severities"), dict) else {}
        scenarios.append(
            {
                "name": str(row.get("name") or "").strip(),
                "devices": _safe_int(counts.get("devices")),
                "links": _safe_int(counts.get("links")),
                "events": _safe_int(counts.get("events")),
                "critical": _safe_int(severities.get("critical")),
                "warning": _safe_int(severities.get("warning")),
                "focus_areas": [str(item) for item in list(row.get("focus_areas") or []) if str(item).strip()][:4],
                "protocols": [str(item) for item in list(row.get("protocols") or []) if str(item).strip()][:4],
            }
        )
    failed_assertions = (
        _failed_assertions("manifest", manifest)
        + _failed_assertions("scenario_catalog", scenario_catalog)
        + _failed_assertions("soak_matrix", soak_matrix)
        + _failed_assertions("eve_plan", eve_plan)
    )
    catalog_summary = scenario_catalog.get("summary") if isinstance(scenario_catalog.get("summary"), dict) else {}
    return {
        "id": "synthetic_validation",
        "title": "Synthetic Validation",
        "available": True,
        "status": "healthy" if overall_pass else "critical",
        "accepted": overall_pass,
        "generated_at": _normalize_timestamp(payload.get("generated_at")),
        "source_path": source_path,
        "source_name": _display_name(source_path),
        "summary": "pass" if overall_pass else "fail",
        "profile": str(payload.get("profile") or "").strip() or None,
        "overall_pass": overall_pass,
        "scenario_count": scenario_count,
        "soak_runs": soak_runs,
        "total_processed_events": total_events,
        "details": {
            "scenarios": scenarios[:6],
            "soak_summary": {
                "max_duplicate_ratio": _safe_float(((soak_matrix.get("summary") or {}).get("max_duplicate_ratio")), default=None),
                "max_queue_depth": _safe_int(((soak_matrix.get("summary") or {}).get("max_queue_depth"))),
                "max_throughput_eps": _safe_float(((soak_matrix.get("summary") or {}).get("max_throughput_eps")), default=None),
            },
            "focus_areas": [str(item) for item in list(catalog_summary.get("focus_areas_present") or []) if str(item).strip()][:8],
            "protocol_coverage": [str(item) for item in list(catalog_summary.get("protocols_present") or []) if str(item).strip()][:8],
            "digital_twin_vendors": [str(item) for item in list(manifest.get("digital_twin_vendors") or []) if str(item).strip()][:12],
            "first_wave_vendors": [str(item) for item in list(eve_plan.get("first_wave_vendors") or []) if str(item).strip()][:8],
            "failed_assertions": failed_assertions[:8],
        },
    }


def _build_northbound_section(payload: dict[str, Any] | None, source_path: str | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return _section_unavailable("northbound_soak", "Northbound Soak")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    last_record = payload.get("last_record") if isinstance(payload.get("last_record"), dict) else {}
    run_status = str(payload.get("status") or "unavailable").strip().lower() or "unavailable"
    success_rate = _safe_float(summary.get("success_rate_pct"), default=None)
    failure_count = _safe_int(summary.get("failure_count"))
    started_at = _normalize_timestamp(payload.get("started_at_utc"))
    generated_at = _normalize_timestamp(payload.get("generated_at_utc") or payload.get("started_at_utc"))
    expected_finish_at = _normalize_timestamp(payload.get("expected_finish_utc"))
    expected_finish_dt = _parse_normalized_datetime(expected_finish_at)
    generated_dt = _parse_normalized_datetime(generated_at)
    stale_seconds = None
    is_stale_running = False
    if run_status == "running" and expected_finish_dt is not None:
        current_dt = _utc_now()
        if current_dt > expected_finish_dt:
            stale_seconds = int((current_dt - expected_finish_dt).total_seconds())
            is_stale_running = True
    report_age_seconds = None
    if generated_dt is not None:
        report_age_seconds = int(max(0.0, (_utc_now() - generated_dt).total_seconds()))
    remaining_seconds = _safe_int(summary.get("remaining_seconds"))
    if run_status == "running" and is_stale_running:
        status = "warning" if failure_count <= 0 and (success_rate or 0.0) >= 95.0 else "critical"
        accepted = False
        remaining_seconds = 0
        summary_label = "stale_running"
    elif run_status == "running":
        status = "in_progress"
        accepted = False
        summary_label = run_status
    elif run_status == "completed":
        accepted = (success_rate or 0.0) >= 95.0 and failure_count <= 5
        status = "healthy" if accepted else "critical"
        summary_label = run_status
    elif run_status in {"healthy", "warning", "critical"}:
        status = run_status
        accepted = run_status == "healthy"
        summary_label = run_status
    else:
        status = "critical"
        accepted = False
        summary_label = run_status
    return {
        "id": "northbound_soak",
        "title": "Northbound Soak",
        "available": True,
        "status": status,
        "accepted": accepted,
        "generated_at": generated_at,
        "source_path": source_path,
        "source_name": _display_name(source_path),
        "summary": summary_label,
        "run_status": run_status,
        "stale": is_stale_running,
        "total_attempts": _safe_int(summary.get("total_attempts")),
        "success_rate_pct": success_rate,
        "failure_count": failure_count,
        "remaining_seconds": remaining_seconds,
        "details": {
            "last_record": {
                "mode": str(last_record.get("mode") or "").strip() or None,
                "timestamp": _normalize_timestamp(last_record.get("timestamp")),
                "latency_ms": _safe_float(last_record.get("latency_ms"), default=None),
                "http_status": _safe_int(last_record.get("http_status")),
                "attempts": _safe_int(last_record.get("attempts")),
            },
            "window": {
                "started_at": started_at,
                "expected_finish_at": expected_finish_at,
                "elapsed_seconds": _safe_int(summary.get("elapsed_seconds")),
                "remaining_seconds": remaining_seconds,
                "reported_remaining_seconds": _safe_int(summary.get("remaining_seconds")),
                "report_age_seconds": report_age_seconds,
                "stale": is_stale_running,
                "stale_seconds": stale_seconds,
            },
        },
    }


def _build_northbound_probe_detail(payload: dict[str, Any] | None, source_path: str | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    last_record = payload.get("last_record") if isinstance(payload.get("last_record"), dict) else {}
    run_status = str(payload.get("status") or "unavailable").strip().lower() or "unavailable"
    success_rate = _safe_float(summary.get("success_rate_pct"), default=None)
    failure_count = _safe_int(summary.get("failure_count"))
    started_at = _normalize_timestamp(payload.get("started_at_utc"))
    generated_at = _normalize_timestamp(payload.get("generated_at_utc") or payload.get("started_at_utc"))
    duration_seconds = _safe_int(summary.get("duration_seconds"))
    remaining_seconds = _safe_int(summary.get("remaining_seconds"))
    if run_status == "running":
        status = "in_progress"
        summary_label = run_status
    elif run_status in {"pass", "healthy"}:
        status = "healthy"
        summary_label = "pass" if run_status == "pass" else run_status
    elif run_status in {"fail", "critical"}:
        status = "critical"
        summary_label = "fail" if run_status == "fail" else run_status
    elif run_status == "completed":
        status = "healthy" if (success_rate or 0.0) >= 95.0 and failure_count <= 5 else "critical"
        summary_label = run_status
    elif run_status == "warning":
        status = "warning"
        summary_label = run_status
    else:
        status = "critical"
        summary_label = run_status
    return {
        "id": "northbound_probe",
        "title": "Northbound Probe",
        "available": True,
        "status": status,
        "accepted": False,
        "generated_at": generated_at,
        "source_path": source_path,
        "source_name": _display_name(source_path),
        "summary": summary_label,
        "run_status": run_status,
        "total_attempts": _safe_int(summary.get("total_attempts")),
        "success_rate_pct": success_rate,
        "failure_count": failure_count,
        "remaining_seconds": remaining_seconds,
        "details": {
            "last_record": {
                "mode": str(last_record.get("mode") or "").strip() or None,
                "timestamp": _normalize_timestamp(last_record.get("timestamp")),
                "latency_ms": _safe_float(last_record.get("latency_ms"), default=None),
                "http_status": _safe_int(last_record.get("http_status")),
                "attempts": _safe_int(last_record.get("attempts")),
            },
            "window": {
                "started_at": started_at,
                "expected_finish_at": None,
                "elapsed_seconds": duration_seconds,
                "remaining_seconds": remaining_seconds,
                "reported_remaining_seconds": remaining_seconds,
                "report_age_seconds": None,
                "stale": False,
                "stale_seconds": None,
            },
        },
    }


def _merge_northbound_section(
    soak_payload: dict[str, Any] | None,
    soak_source_path: str | None,
    probe_payload: dict[str, Any] | None,
    probe_source_path: str | None,
) -> dict[str, Any]:
    soak_section = _build_northbound_section(soak_payload, soak_source_path) if isinstance(soak_payload, dict) else None
    probe_detail = _build_northbound_probe_detail(probe_payload, probe_source_path)
    if soak_section is None:
        if probe_detail is None:
            return _section_unavailable("northbound_soak", "Northbound Soak")
        status = str(probe_detail.get("status") or "warning")
        if status == "healthy":
            status = "warning"
        summary = "probe_only_running" if probe_detail.get("status") == "in_progress" else "probe_only"
        return {
            "id": "northbound_soak",
            "title": "Northbound Soak",
            "available": True,
            "status": status,
            "accepted": False,
            "generated_at": probe_detail.get("generated_at"),
            "source_path": probe_detail.get("source_path"),
            "source_name": probe_detail.get("source_name"),
            "summary": summary,
            "run_status": probe_detail.get("run_status"),
            "stale": False,
            "total_attempts": probe_detail.get("total_attempts"),
            "success_rate_pct": probe_detail.get("success_rate_pct"),
            "failure_count": probe_detail.get("failure_count"),
            "remaining_seconds": probe_detail.get("remaining_seconds"),
            "details": {
                **copy.deepcopy(probe_detail.get("details") or {}),
                "probe": probe_detail,
            },
        }

    if probe_detail is not None:
        soak_section.setdefault("details", {})
        soak_section["details"]["probe"] = probe_detail
        if soak_section.get("summary") == "stale_running" and probe_detail.get("status") == "healthy":
            soak_section["summary"] = "stale_running_probe_healthy"
    return soak_section


def _build_discovery_hinting_section() -> dict[str, Any]:
    try:
        from app.services.discovery_hint_sync_service import DiscoveryHintSyncService

        db = SessionLocal()
    except Exception:
        return _section_unavailable("discovery_hinting", "Discovery Hinting")

    try:
        status_summary = DiscoveryHintSyncService.build_status_summary(db, benchmark_limit=250)
    except Exception:
        return _section_unavailable("discovery_hinting", "Discovery Hinting")
    finally:
        db.close()

    sync = status_summary.get("sync") if isinstance(status_summary.get("sync"), dict) else {}
    rules = status_summary.get("rules") if isinstance(status_summary.get("rules"), dict) else {}
    benchmark = status_summary.get("benchmark") if isinstance(status_summary.get("benchmark"), dict) else {}
    benchmark_summary = benchmark.get("summary") if isinstance(benchmark.get("summary"), dict) else {}

    active_rules = _safe_int(rules.get("active"))
    total_rules = _safe_int(rules.get("total"))
    total_events = _safe_int(benchmark_summary.get("total"))
    success_count = _safe_int(benchmark_summary.get("success"))
    false_positive_count = _safe_int(benchmark_summary.get("false_positive"))
    unknown_after_hint = _safe_int(benchmark_summary.get("unknown_after_hint"))
    success_rate_pct = _safe_float(benchmark_summary.get("success_rate_pct"), default=0.0) or 0.0
    false_positive_rate_pct = _safe_float(benchmark_summary.get("false_positive_rate_pct"), default=0.0) or 0.0
    sync_enabled = bool(sync.get("enabled"))
    last_pull_status_raw = str(sync.get("last_pull_status") or "").strip()
    last_push_status_raw = str(sync.get("last_push_status") or "").strip()
    last_pull_status = last_pull_status_raw or "idle"
    last_push_status = last_push_status_raw or "idle"
    pull_failed = last_pull_status.lower().startswith(("failed", "error"))
    push_failed = last_push_status.lower().startswith(("failed", "error"))
    last_pull_at = _normalize_timestamp(sync.get("last_pull_at"))
    last_push_at = _normalize_timestamp(sync.get("last_push_at"))
    generated_at = last_pull_at or last_push_at or _now_iso()

    has_runtime_data = bool(
        sync_enabled
        or total_rules > 0
        or total_events > 0
        or bool(last_pull_status_raw)
        or bool(last_push_status_raw)
    )
    if not has_runtime_data:
        return _section_unavailable("discovery_hinting", "Discovery Hinting")

    if pull_failed or push_failed or (total_events > 0 and (success_rate_pct < 50.0 or false_positive_rate_pct > 25.0)):
        status = "critical"
    elif total_events <= 0 or active_rules <= 0 or success_rate_pct < 70.0 or false_positive_rate_pct > 15.0:
        status = "warning"
    else:
        status = "healthy"

    accepted = (
        status == "healthy"
        and total_events > 0
        and active_rules > 0
    )
    summary_label = (
        f"{success_count}/{total_events} successful hints"
        if total_events > 0
        else "runtime summary only"
    )
    return {
        "id": "discovery_hinting",
        "title": "Discovery Hinting",
        "available": True,
        "status": status,
        "accepted": accepted,
        "generated_at": generated_at,
        "source_path": "runtime:discovery_hinting",
        "source_name": "runtime discovery hinting",
        "summary": summary_label,
        "sync_enabled": sync_enabled,
        "active_rules": active_rules,
        "total_rules": total_rules,
        "success_count": success_count,
        "total_events": total_events,
        "false_positive_count": false_positive_count,
        "unknown_after_hint": unknown_after_hint,
        "success_rate_pct": success_rate_pct,
        "false_positive_rate_pct": false_positive_rate_pct,
        "details": {
            "sync": {
                "enabled": sync_enabled,
                "rule_version": str(sync.get("rule_version") or rules.get("version") or "").strip() or None,
                "last_pull_at": last_pull_at,
                "last_push_at": last_push_at,
                "last_pull_status": last_pull_status,
                "last_push_status": last_push_status,
                "pull_interval_seconds": _safe_int(sync.get("pull_interval_seconds")),
                "push_interval_seconds": _safe_int(sync.get("push_interval_seconds")),
            },
            "benchmark": {
                "total": total_events,
                "success": success_count,
                "false_positive": false_positive_count,
                "unknown_after_hint": unknown_after_hint,
                "success_rate_pct": success_rate_pct,
                "false_positive_rate_pct": false_positive_rate_pct,
            },
            "top_vendors": list(benchmark.get("by_vendor") or [])[:5],
            "top_drivers": list(benchmark.get("by_driver") or [])[:5],
        },
    }


def build_release_evidence_summary() -> dict[str, Any]:
    kpi_payload, kpi_source = _read_first_json(REPORT_SOURCE_CANDIDATES["kpi_readiness"])
    vendor_payload, vendor_source = _read_first_json(REPORT_SOURCE_CANDIDATES["vendor_support"])
    synthetic_payload, synthetic_source = _read_first_json(REPORT_SOURCE_CANDIDATES["synthetic_validation"])
    northbound_payload, northbound_source = _read_first_json(REPORT_SOURCE_CANDIDATES["northbound_soak"])
    northbound_probe_payload, northbound_probe_source = _read_first_json(REPORT_SOURCE_CANDIDATES["northbound_probe"])

    sections = {
        "kpi_readiness": _build_kpi_section(kpi_payload, kpi_source),
        "vendor_support": _build_vendor_section(vendor_payload, vendor_source),
        "discovery_hinting": _build_discovery_hinting_section(),
        "synthetic_validation": _build_synthetic_section(synthetic_payload, synthetic_source),
        "northbound_soak": _merge_northbound_section(
            northbound_payload,
            northbound_source,
            northbound_probe_payload,
            northbound_probe_source,
        ),
    }
    rows = list(sections.values())
    available_rows = [row for row in rows if row.get("available")]
    blocking = [row["id"] for row in available_rows if row.get("status") == "critical"]
    warning = [row["id"] for row in available_rows if row.get("status") == "warning"]
    in_progress = [row["id"] for row in available_rows if row.get("status") == "in_progress"]
    if blocking:
        overall_status = "critical"
    elif warning:
        overall_status = "warning"
    elif in_progress:
        overall_status = "in_progress"
    elif available_rows:
        overall_status = "healthy"
    else:
        overall_status = "unavailable"
    summary = {
        "overall_status": overall_status,
        "accepted_gates": sum(1 for row in available_rows if row.get("accepted") is True),
        "available_gates": len(available_rows),
        "total_gates": len(rows),
        "blocking_gates": blocking,
        "warning_gates": warning,
        "in_progress_gates": in_progress,
    }
    return {
        "generated_at": _now_iso(),
        "summary": summary,
        "sections": sections,
    }


def mirror_release_evidence_assets() -> dict[str, list[str]]:
    copied_reports: list[str] = []
    copied_runbooks: list[str] = []

    for filename, candidates in REPORT_MIRROR_SPECS.items():
        src = _first_existing(candidates)
        if not src:
            continue
        dst = REPORT_CACHE_DIR / filename
        if _copy_asset(src, dst):
            copied_reports.append(_display_path(dst))

    for filename, src in RUNBOOK_MIRROR_SPECS.items():
        if not src.exists():
            continue
        dst = RUNBOOK_CACHE_DIR / filename
        if _copy_asset(src, dst):
            copied_runbooks.append(_display_path(dst))

    return {
        "reports": copied_reports,
        "runbooks": copied_runbooks,
    }


def write_release_evidence_cache(payload: dict[str, Any], path: Path | None = None) -> Path:
    target = path or RELEASE_EVIDENCE_CACHE_PATH
    return _write_json(target, payload)


def get_release_evidence_snapshot(refresh: bool = False) -> dict[str, Any]:
    if not refresh:
        cached = _read_json(RELEASE_EVIDENCE_CACHE_PATH)
        if isinstance(cached, dict):
            cached.setdefault("summary", {})
            cached["source"] = "cache"
            return cached

    payload = build_release_evidence_summary()
    if payload.get("summary", {}).get("available_gates", 0) > 0:
        write_release_evidence_cache(payload)
        payload["source"] = "generated"
        return payload

    cached = _read_json(RELEASE_EVIDENCE_CACHE_PATH)
    if isinstance(cached, dict):
        cached.setdefault("summary", {})
        cached["source"] = "cache_stale"
        return cached

    payload["source"] = "unavailable"
    return payload


def build_release_evidence_bundle(refresh: bool = False) -> bytes:
    if refresh:
        mirror_release_evidence_assets()

    snapshot = get_release_evidence_snapshot(refresh=bool(refresh))
    manifest = {
        "generated_at": _now_iso(),
        "summary": snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {},
        "source": snapshot.get("source"),
        "files": [],
    }

    bundle_entries: list[tuple[Path, str]] = []
    if RELEASE_EVIDENCE_CACHE_PATH.exists():
        bundle_entries.append((RELEASE_EVIDENCE_CACHE_PATH, "release-evidence.latest.json"))

    for path in sorted(REPORT_CACHE_DIR.glob("*.json")):
        if path == RELEASE_EVIDENCE_CACHE_PATH:
            continue
        bundle_entries.append((path, f"reports/{path.name}"))
    for path in sorted(REPORT_CACHE_DIR.glob("*.md")):
        bundle_entries.append((path, f"reports/{path.name}"))
    for path in sorted(RUNBOOK_CACHE_DIR.glob("*.md")):
        bundle_entries.append((path, f"runbooks/{path.name}"))

    manifest["files"] = [arcname for _, arcname in bundle_entries]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for src, arcname in bundle_entries:
            try:
                zf.write(src, arcname=arcname)
            except Exception:
                continue
    return buf.getvalue()


def summarize_release_status(status: str) -> int:
    return _STATUS_RANK.get(str(status or "unavailable").strip().lower(), _STATUS_RANK["unavailable"])


def _run_refresh_command(
    cmd: list[str],
    *,
    stage: str,
    timeout_seconds: int = RELEASE_EVIDENCE_REFRESH_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    started_at = _now_iso()
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(BACKEND_ROOT),
            env=dict(os.environ),
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_seconds,
        )
    except subprocess.CalledProcessError as exc:
        raise ReleaseEvidenceRefreshError(
            stage=stage,
            message=str(exc),
            returncode=int(exc.returncode),
            output_tail=_tail_text("\n".join(filter(None, [exc.stdout, exc.stderr]))),
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise ReleaseEvidenceRefreshError(
            stage=stage,
            message=f"{stage} timed out after {timeout_seconds}s",
            output_tail=_tail_text("\n".join(filter(None, [str(exc.stdout or ""), str(exc.stderr or "")]))),
        ) from exc
    return {
        "stage": stage,
        "command": [Path(str(part)).name if idx == 0 else str(part) for idx, part in enumerate(cmd)],
        "started_at": started_at,
        "finished_at": _now_iso(),
        "returncode": int(completed.returncode),
        "output_tail": _tail_text("\n".join(filter(None, [completed.stdout, completed.stderr]))),
    }


def _build_refresh_step_skip(stage: str, reason: str, message: str) -> dict[str, Any]:
    now = _now_iso()
    return {
        "stage": stage,
        "skipped": True,
        "reason": reason,
        "started_at": now,
        "finished_at": now,
        "returncode": None,
        "output_tail": _tail_text(message),
    }


def _initial_refresh_stage(*, profile: str, include_synthetic: bool, include_northbound_probe: bool) -> str:
    if str(profile or "").strip().lower() == "local":
        return "ops_kpi_sample_collection"
    if include_synthetic:
        return "synthetic_validation"
    if include_northbound_probe:
        return "northbound_probe"
    return "kpi_readiness_export"


def _build_ops_kpi_sample_collection_command(profile: str) -> list[str]:
    return [
        sys.executable,
        str(OPS_KPI_SAMPLE_COLLECTION_SCRIPT),
        "--profile",
        str(profile or "local"),
    ]


def _build_kpi_readiness_export_command() -> list[str]:
    report_dir = PROJECT_ROOT / "docs" / "reports"
    return [
        sys.executable,
        str(KPI_READINESS_EXPORT_SCRIPT),
        "--direct-db",
        "--require-sample-minimums",
        "--output-dir",
        str(report_dir),
        "--filename-prefix",
        "kpi-readiness-30d",
        "--latest-json-path",
        str(report_dir / "kpi-readiness-30d-latest.json"),
        "--latest-md-path",
        str(report_dir / "kpi-readiness-30d-latest.md"),
    ]


def _build_northbound_probe_command(profile: str) -> tuple[list[str] | None, int, dict[str, Any] | None]:
    runtime = get_release_evidence_northbound_probe_runtime()
    execution_mode = str(runtime.get("execution_mode") or "").strip().lower()
    if not runtime.get("auth_configured") and execution_mode != "direct_db":
        return (
            None,
            0,
            _build_refresh_step_skip(
                "northbound_probe",
                "missing_runtime",
                "Northbound probe skipped: configure auth or ensure direct-db runtime is available.",
            ),
        )

    spec = NORTHBOUND_PROBE_PROFILE_SPECS.get(profile) or NORTHBOUND_PROBE_PROFILE_SPECS[RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE]
    report_dir = PROJECT_ROOT / "docs" / "reports"
    cmd = [
        sys.executable,
        str(NORTHBOUND_SOAK_PROBE_SCRIPT),
        "--base-url",
        str(runtime.get("base_url") or "http://localhost:8000"),
        "--duration-hours",
        str(spec.get("duration_hours", 0.005)),
        "--interval-seconds",
        str(spec.get("interval_seconds", 2.0)),
        "--modes",
        "jira,servicenow,splunk,elastic",
        "--use-local-receiver",
        "--local-receiver-host",
        "localhost",
        "--local-receiver-port",
        "18080",
        "--local-receiver-fail-every",
        "0",
        "--local-receiver-enforce-signature",
        "--webhook-secret",
        "soak-secret",
        "--output-dir",
        str(report_dir),
        "--filename-prefix",
        NORTHBOUND_PROBE_FILENAME_PREFIX,
        "--latest-json-path",
        str(report_dir / "northbound-soak-probe.latest.json"),
        "--latest-md-path",
        str(report_dir / "northbound-soak-probe.latest.md"),
        "--checkpoint-interval-seconds",
        "5",
        "--progress-log-path",
        str(report_dir / "northbound-soak-probe.progress.log"),
    ]
    if execution_mode == "direct_db":
        cmd.append("--direct-db")
    else:
        auth_mode = str(runtime.get("auth_mode") or "")
        if auth_mode == "token":
            cmd.extend(["--token", _read_env_text(NORTHBOUND_PROBE_TOKEN_ENV)])
        else:
            cmd.extend(
                [
                    "--login-username",
                    _read_env_text(NORTHBOUND_PROBE_LOGIN_USERNAME_ENV),
                    "--login-password",
                    str(os.getenv(NORTHBOUND_PROBE_LOGIN_PASSWORD_ENV, "") or ""),
                ]
            )
    timeout_seconds = int(spec.get("timeout_seconds", RELEASE_EVIDENCE_REFRESH_TIMEOUT_SECONDS))
    return cmd, timeout_seconds, None


def run_release_evidence_refresh(
    profile: str = RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE,
    include_synthetic: bool = True,
    include_northbound_probe: bool = False,
    on_stage: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    normalized_profile = str(profile or RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE).strip().lower() or RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE
    if normalized_profile not in RELEASE_EVIDENCE_REFRESH_PROFILES:
        raise ValueError(f"Unsupported release evidence refresh profile: {normalized_profile}")

    steps: list[dict[str, Any]] = []
    if normalized_profile == "local":
        if on_stage:
            on_stage("ops_kpi_sample_collection")
        steps.append(
            _run_refresh_command(
                _build_ops_kpi_sample_collection_command(normalized_profile),
                stage="ops_kpi_sample_collection",
            )
        )
    if include_synthetic:
        if on_stage:
            on_stage("synthetic_validation")
        steps.append(
            _run_refresh_command(
                [sys.executable, str(SYNTHETIC_VALIDATION_SCRIPT), "--profile", normalized_profile, "--fail-on-unhealthy"],
                stage="synthetic_validation",
            )
        )
    if include_northbound_probe:
        if on_stage:
            on_stage("northbound_probe")
        northbound_cmd, northbound_timeout_seconds, northbound_skip = _build_northbound_probe_command(normalized_profile)
        if northbound_skip is not None:
            steps.append(northbound_skip)
        elif northbound_cmd is not None:
            steps.append(
                _run_refresh_command(
                    northbound_cmd,
                    stage="northbound_probe",
                    timeout_seconds=northbound_timeout_seconds,
                )
            )
    if on_stage:
        on_stage("kpi_readiness_export")
    steps.append(
        _run_refresh_command(
            _build_kpi_readiness_export_command(),
            stage="kpi_readiness_export",
        )
    )
    if on_stage:
        on_stage("release_evidence_cache")
    steps.append(
        _run_refresh_command(
            [sys.executable, str(RELEASE_EVIDENCE_CACHE_SCRIPT)],
            stage="release_evidence_cache",
        )
    )
    snapshot = get_release_evidence_snapshot(refresh=False)
    summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
    return {
        "profile": normalized_profile,
        "include_synthetic": bool(include_synthetic),
        "include_northbound_probe": bool(include_northbound_probe),
        "steps": steps,
        "summary": {
            "overall_status": str(summary.get("overall_status") or "unavailable"),
            "accepted_gates": _safe_int(summary.get("accepted_gates")),
            "available_gates": _safe_int(summary.get("available_gates")),
            "total_gates": _safe_int(summary.get("total_gates")),
        },
    }


def _emit_refresh_state(
    state: dict[str, Any],
    *,
    on_state: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    normalized = persist_release_evidence_refresh_status(state)
    if on_state:
        on_state(copy.deepcopy(normalized))
    return normalized


def _run_release_evidence_refresh_locked(
    *,
    profile: str,
    include_synthetic: bool,
    include_northbound_probe: bool,
    trigger_source: str,
    on_state: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    started_at_monotonic = time.monotonic()
    started_at_iso = _now_iso()
    current_state = _emit_refresh_state(
        {
            "status": "running",
            "stage": _initial_refresh_stage(
                profile=profile,
                include_synthetic=bool(include_synthetic),
                include_northbound_probe=bool(include_northbound_probe),
            ),
            "profile": profile,
            "include_synthetic": bool(include_synthetic),
            "include_northbound_probe": bool(include_northbound_probe),
            "started_at": started_at_iso,
            "finished_at": None,
            "duration_seconds": None,
            "trigger_source": trigger_source,
            "error": None,
            "steps": [],
            "output_tail": None,
        },
        on_state=on_state,
    )

    try:
        result = run_release_evidence_refresh(
            profile=profile,
            include_synthetic=include_synthetic,
            include_northbound_probe=include_northbound_probe,
            on_stage=lambda stage: _emit_refresh_state(
                {
                    **current_state,
                    "status": "running",
                    "stage": stage,
                },
                on_state=on_state,
            ),
        )
        steps = result.get("steps") if isinstance(result.get("steps"), list) else []
        output_tail = _tail_text("\n\n".join(str(step.get("output_tail") or "") for step in steps))
        final_state = _emit_refresh_state(
            {
                **current_state,
                "status": "completed",
                "stage": "completed",
                "finished_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - started_at_monotonic, 2),
                "last_success_at": _now_iso(),
                "last_summary": result.get("summary") if isinstance(result.get("summary"), dict) else None,
                "steps": steps,
                "output_tail": output_tail,
                "error": None,
            },
            on_state=on_state,
        )
        return {
            "started": True,
            "reason": "completed",
            "refresh": final_state,
            "result": result,
        }
    except ReleaseEvidenceRefreshError as exc:
        failed_state = _emit_refresh_state(
            {
                **current_state,
                "status": "failed",
                "stage": exc.stage,
                "finished_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - started_at_monotonic, 2),
                "error": {
                    "stage": exc.stage,
                    "message": str(exc),
                    "returncode": int(exc.returncode) if exc.returncode is not None else None,
                },
                "output_tail": exc.output_tail,
            },
            on_state=on_state,
        )
        return {
            "started": True,
            "reason": "failed",
            "refresh": failed_state,
            "error": failed_state.get("error"),
        }
    except Exception as exc:
        failed_state = _emit_refresh_state(
            {
                **current_state,
                "status": "failed",
                "stage": "failed",
                "finished_at": _now_iso(),
                "duration_seconds": round(time.monotonic() - started_at_monotonic, 2),
                "error": {
                    "stage": "failed",
                    "message": str(exc),
                },
            },
            on_state=on_state,
        )
        return {
            "started": True,
            "reason": "failed",
            "refresh": failed_state,
            "error": failed_state.get("error"),
        }


def run_release_evidence_refresh_blocking(
    *,
    profile: str = RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE,
    include_synthetic: bool = True,
    include_northbound_probe: bool = False,
    trigger_source: str = "scheduler",
) -> dict[str, Any]:
    normalized_profile = str(profile or RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE).strip().lower() or RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE
    if normalized_profile not in RELEASE_EVIDENCE_REFRESH_PROFILES:
        raise ValueError(f"Unsupported release evidence refresh profile: {normalized_profile}")

    if not _claim_release_evidence_refresh_lock():
        return {
            "started": False,
            "reason": "already_running",
            "refresh": get_release_evidence_refresh_status(),
        }

    try:
        return _run_release_evidence_refresh_locked(
            profile=normalized_profile,
            include_synthetic=bool(include_synthetic),
            include_northbound_probe=bool(include_northbound_probe),
            trigger_source=trigger_source,
        )
    finally:
        _release_evidence_refresh_lock()


class ReleaseEvidenceRefreshRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state: dict[str, Any] = load_release_evidence_refresh_status() or _default_refresh_state()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def _update(self, **fields: Any) -> dict[str, Any]:
        with self._lock:
            self._state = _normalize_refresh_state({**self._state, **fields})
            snapshot = copy.deepcopy(self._state)
        persist_release_evidence_refresh_status(snapshot)
        return snapshot

    def _sync_from_state(self, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._state = _normalize_refresh_state(state)
            return copy.deepcopy(self._state)

    def start(
        self,
        *,
        profile: str = RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE,
        include_synthetic: bool = True,
        include_northbound_probe: bool = False,
        trigger_source: str = "api",
    ) -> dict[str, Any]:
        normalized_profile = str(profile or RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE).strip().lower() or RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE
        if normalized_profile not in RELEASE_EVIDENCE_REFRESH_PROFILES:
            raise ValueError(f"Unsupported release evidence refresh profile: {normalized_profile}")

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return {
                    "started": False,
                    "reason": "already_running",
                    "refresh": copy.deepcopy(self._state),
                }
        if not _claim_release_evidence_refresh_lock():
            return {
                "started": False,
                "reason": "already_running",
                "refresh": get_release_evidence_refresh_status(),
            }

        queued_state = self._update(
            status="queued",
            stage=_initial_refresh_stage(
                include_synthetic=bool(include_synthetic),
                include_northbound_probe=bool(include_northbound_probe),
            ),
            profile=normalized_profile,
            include_synthetic=bool(include_synthetic),
            include_northbound_probe=bool(include_northbound_probe),
            started_at=_now_iso(),
            finished_at=None,
            duration_seconds=None,
            trigger_source=trigger_source,
            error=None,
            steps=[],
            output_tail=None,
        )
        try:
            thread = threading.Thread(
                target=self._run,
                kwargs={
                    "profile": normalized_profile,
                    "include_synthetic": bool(include_synthetic),
                    "include_northbound_probe": bool(include_northbound_probe),
                    "trigger_source": trigger_source,
                    "started_at_iso": queued_state.get("started_at"),
                },
                name="release-evidence-refresh",
                daemon=True,
            )
        except Exception:
            _release_evidence_refresh_lock()
            raise
        with self._lock:
            self._thread = thread
        thread.start()
        return {
            "started": True,
            "reason": "started",
            "refresh": queued_state,
        }

    def _run(
        self,
        *,
        profile: str,
        include_synthetic: bool,
        include_northbound_probe: bool,
        trigger_source: str,
        started_at_iso: str | None,
    ) -> None:
        try:
            _run_release_evidence_refresh_locked(
                profile=profile,
                include_synthetic=include_synthetic,
                include_northbound_probe=include_northbound_probe,
                trigger_source=trigger_source,
                on_state=self._sync_from_state,
            )
        finally:
            _release_evidence_refresh_lock()
            with self._lock:
                if self._state.get("started_at") == started_at_iso and self._thread is not None:
                    self._thread = None


_release_evidence_refresh_runner = ReleaseEvidenceRefreshRunner()


def get_release_evidence_refresh_status() -> dict[str, Any]:
    return load_release_evidence_refresh_status() or _release_evidence_refresh_runner.snapshot()


def start_release_evidence_refresh(
    *,
    profile: str = RELEASE_EVIDENCE_REFRESH_DEFAULT_PROFILE,
    include_synthetic: bool = True,
    include_northbound_probe: bool = False,
    trigger_source: str = "api",
) -> dict[str, Any]:
    return _release_evidence_refresh_runner.start(
        profile=profile,
        include_synthetic=include_synthetic,
        include_northbound_probe=include_northbound_probe,
        trigger_source=trigger_source,
    )
