from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from datetime import datetime, timedelta
import json
import math
from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.compliance import ComplianceStandard, ComplianceRule
from app.models.device import Device, ComplianceReport, ConfigBackup, EventLog
from app.models.settings import SystemSetting
from app.services.compliance_service import ComplianceEngine
from app.services.change_execution_service import ChangeExecutionService
from app.services.change_policy_service import ChangePolicyService
from app.services.approval_execution_service import ApprovalExecutionService
from app.services.device_support_policy_service import DeviceSupportPolicyService
from pydantic import BaseModel, ConfigDict

router = APIRouter()

# --- Pydantic Schemas ---

class RuleBase(BaseModel):
    name: str
    description: Optional[str] = None
    severity: str = "medium"
    check_type: str = "simple_match"
    pattern: str
    remediation: Optional[str] = None

class RuleCreate(RuleBase):
    pass

class RuleResponse(RuleBase):
    id: int
    standard_id: int
    model_config = ConfigDict(from_attributes=True)

class StandardBase(BaseModel):
    name: str
    description: Optional[str] = None
    device_family: str = "cisco_ios"

class StandardCreate(StandardBase):
    pass

class StandardResponse(StandardBase):
    id: int
    rules: List[RuleResponse] = []
    model_config = ConfigDict(from_attributes=True)

class ScanRequest(BaseModel):
    device_ids: List[int]
    standard_id: Optional[int] = None


class DriftRemediateRequest(BaseModel):
    save_pre_backup: bool = True
    pre_check_commands: List[str] = []
    prepare_device_snapshot: bool = True
    rollback_on_failure: bool = True
    post_check_enabled: bool = True
    post_check_commands: List[str] = []
    canary_count: int = 0
    wave_size: int = 0
    stop_on_wave_failure: bool = True
    inter_wave_delay_seconds: float = 0.0
    require_drift_gate: bool = True
    idempotency_key: Optional[str] = None
    approval_id: Optional[int] = None
    execution_id: Optional[str] = None


class DriftRemediateBatchRequest(DriftRemediateRequest):
    device_ids: List[int]


def _enforce_compliance_approval_policy(
    *,
    db: Session,
    target_ids: List[int],
    approval_id: Optional[int],
) -> None:
    normalized_ids = ChangeExecutionService._normalize_device_ids(list(target_ids or []))
    if not ChangePolicyService.requires_compliance_remediate_approval(
        db,
        target_count=len(normalized_ids),
        approval_id=(int(approval_id) if approval_id is not None else None),
    ):
        return

    if ChangePolicyService.config_drift_approval_enabled(db):
        detail = "Approval required for config drift remediation. Submit an approval request first."
    else:
        max_direct = ChangePolicyService.compliance_direct_max_devices(db)
        detail = (
            f"Approval required for config drift remediation targeting {len(normalized_ids)} devices "
            f"(direct max: {max_direct}). Submit an approval request first."
        )
    raise HTTPException(status_code=409, detail=detail)


def _resolve_compliance_execution_id(
    *,
    db: Session,
    req: DriftRemediateRequest | DriftRemediateBatchRequest,
    target_ids: List[int],
    approval_id: Optional[int],
) -> str:
    normalized_ids = ChangeExecutionService._normalize_device_ids(list(target_ids or []))
    execution_id = str(req.execution_id or "").strip()
    if not execution_id:
        execution_id = ChangeExecutionService.make_fingerprint(
            "compliance_drift_remediate",
            {
                "device_ids": normalized_ids,
                "save_pre_backup": bool(req.save_pre_backup),
                "pre_check_commands": list(req.pre_check_commands or []),
                "prepare_device_snapshot": bool(req.prepare_device_snapshot),
                "rollback_on_failure": bool(req.rollback_on_failure),
                "post_check_enabled": bool(req.post_check_enabled),
                "post_check_commands": list(req.post_check_commands or []),
                "canary_count": int(req.canary_count or 0),
                "wave_size": int(req.wave_size or 0),
                "stop_on_wave_failure": bool(req.stop_on_wave_failure),
                "inter_wave_delay_seconds": float(req.inter_wave_delay_seconds or 0.0),
                "require_drift_gate": bool(req.require_drift_gate),
                "approval_id": int(approval_id) if approval_id is not None else None,
            },
        )
    return str(
        ApprovalExecutionService.bind_approved_execution(
            db,
            approval_id=(int(approval_id) if approval_id is not None else None),
            expected_request_type="config_drift_remediate",
            execution_id=execution_id,
        )
        or execution_id
    )


def _enforce_compliance_support_policy(
    *,
    db: Session,
    target_ids: List[int],
    rollback_on_failure: bool,
) -> None:
    devices = db.query(Device).filter(Device.id.in_(list(target_ids or []))).all() if target_ids else []
    blocked_config = DeviceSupportPolicyService.collect_blocked_devices(
        db,
        devices=devices,
        feature="config",
    )
    if blocked_config:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEVICE_SUPPORT_BLOCKED",
                "message": "Config drift remediation blocked for unsupported devices.",
                "details": {"feature": "config", "blocked_devices": blocked_config},
            },
        )
    if bool(rollback_on_failure):
        blocked_rollback = DeviceSupportPolicyService.collect_blocked_devices(
            db,
            devices=devices,
            feature="rollback",
        )
        if blocked_rollback:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ROLLBACK_STRATEGY_UNSUPPORTED",
                    "message": "Rollback-on-failure is blocked for devices without supported rollback strategy.",
                    "details": {
                        "feature": "rollback",
                        "blocked_devices": blocked_rollback,
                        "hint": "Disable rollback_on_failure or target rollback-supported vendors only.",
                    },
                },
            )


def _normalize_report_payload(report: ComplianceReport) -> Dict[str, Any]:
    raw_details = getattr(report, "details", None)
    if raw_details is None:
        raw_details = getattr(report, "diff_content", None)
    details = ComplianceEngine.normalize_report_details(raw_details)
    return {
        "device_id": report.device_id,
        "device_name": report.device.name if report.device else None,
        "status": report.status,
        "score": report.match_percentage,
        "last_checked": report.last_checked,
        "summary": details.get("summary") or {},
        "standards": details.get("standards") or {},
        "violations": details.get("violations") or [],
        "automation": details.get("automation") or {},
        "details": details,
    }

# --- Endpoints ---

@router.get("/standards", response_model=List[StandardResponse])
def get_standards(db: Session = Depends(get_db)):
    return db.query(ComplianceStandard).options(joinedload(ComplianceStandard.rules)).all()

@router.post("/standards", response_model=StandardResponse)
def create_standard(standard: StandardCreate, db: Session = Depends(get_db)):
    db_std = ComplianceStandard(**standard.dict())
    db.add(db_std)
    db.commit()
    db.refresh(db_std)
    return db_std

@router.delete("/standards/{id}")
def delete_standard(id: int, db: Session = Depends(get_db)):
    std = db.query(ComplianceStandard).filter(ComplianceStandard.id == id).first()
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")
    db.delete(std)
    db.commit()
    return {"message": "Standard deleted"}

@router.post("/standards/{id}/rules", response_model=RuleResponse)
def add_rule(id: int, rule: RuleCreate, db: Session = Depends(get_db)):
    std = db.query(ComplianceStandard).filter(ComplianceStandard.id == id).first()
    if not std:
        raise HTTPException(status_code=404, detail="Standard not found")
    
    db_rule = ComplianceRule(**rule.dict(), standard_id=id)
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule

@router.delete("/rules/{id}")
def delete_rule(id: int, db: Session = Depends(get_db)):
    rule = db.query(ComplianceRule).filter(ComplianceRule.id == id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"message": "Rule deleted"}

@router.post("/scan")
def run_compliance_scan(request: ScanRequest, db: Session = Depends(get_db)):
    """
    선택된 장비들에 대해 컴플라이언스 스캔을 실행합니다.
    """
    from app.tasks.compliance import run_compliance_scan_task

    try:
        r = run_compliance_scan_task.apply_async(
            args=[request.device_ids, request.standard_id],
            queue="maintenance",
        )
        return {"job_id": r.id, "status": "queued"}
    except Exception:
        engine = ComplianceEngine(db)
        results = []
        for dev_id in request.device_ids:
            try:
                res = engine.run_rule_scan(dev_id, request.standard_id)
                results.append(res)
            except Exception as e:
                results.append({"device_id": dev_id, "error": str(e)})
        return {"job_id": None, "status": "executed", "results": results}

@router.get("/reports")
def get_reports(device_id: int = Query(None), db: Session = Depends(get_db)):
    """
    컴플라이언스 리포트를 조회합니다.
    """
    query = db.query(ComplianceReport).options(joinedload(ComplianceReport.device))
    if device_id:
        query = query.filter(ComplianceReport.device_id == device_id)
        
    reports = query.all()
    
    # JSON 응답 구성
    output = []
    for r in reports:
        output.append({
            "device_id": r.device_id,
            "device_name": r.device.name,
            "status": r.status,
            "score": r.match_percentage,
            "last_checked": r.last_checked,
            "details": r.diff_content # 임시로 diff_content에 JSON string 저장된 것 반환
        })
        
    return output


@router.get("/reports/export")
def export_reports(format: str = Query("xlsx"), device_id: int = Query(None), db: Session = Depends(get_db)):
    import io
    if format not in {"xlsx", "pdf"}:
        raise HTTPException(status_code=400, detail="Invalid format")

    query = db.query(ComplianceReport).options(joinedload(ComplianceReport.device))
    if device_id:
        query = query.filter(ComplianceReport.device_id == device_id)
    reports = query.all()

    payload = []
    for r in reports:
        payload.append(
            {
                "device_id": r.device_id,
                "device_name": r.device.name if r.device else None,
                "status": r.status,
                "score": r.match_percentage,
                "last_checked": r.last_checked.isoformat() if getattr(r, "last_checked", None) else None,
                "details": r.details if getattr(r, "details", None) else r.diff_content,
            }
        )

    from app.services.report_export_service import build_compliance_xlsx, build_compliance_pdf

    if format == "pdf":
        data = build_compliance_pdf(payload)
        media = "application/pdf"
        filename = "compliance_reports.pdf"
    else:
        data = build_compliance_xlsx(payload)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "compliance_reports.xlsx"

    return StreamingResponse(
        io.BytesIO(data),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename=\"{filename}\"'},
    )

# --- Config Drift Endpoints ---

@router.get("/drift/backups/{device_id}")
def get_device_backups(device_id: int, db: Session = Depends(get_db)):
    """
    Get config backups for a device to select a Golden Config.
    """
    backups = db.query(ConfigBackup).filter(ConfigBackup.device_id == device_id)\
        .order_by(ConfigBackup.created_at.desc()).limit(20).all()
        
    return [
        {
            "id": b.id,
            "created_at": b.created_at,
            "is_golden": b.is_golden,
            "size": len(b.raw_config) if b.raw_config else 0
        }
        for b in backups
    ]

@router.post("/drift/golden/{backup_id}")
def set_golden_config(backup_id: int, db: Session = Depends(get_db)):
    """
    Set a specific backup as the Golden Config.
    """
    engine = ComplianceEngine(db)
    result = engine.set_golden_config(backup_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.get("/drift/check/{device_id}")
def check_config_drift(device_id: int, db: Session = Depends(get_db)):
    """
    Perform an immediate Config Drift Check (Golden vs Running).
    """
    engine = ComplianceEngine(db)
    result = engine.check_config_drift(device_id)
    return result


@router.post("/drift/remediate/{device_id}")
def remediate_config_drift(
    device_id: int,
    req: DriftRemediateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    approval_id = int(req.approval_id) if req.approval_id is not None else None
    target_ids = [int(device_id)]
    _enforce_compliance_support_policy(
        db=db,
        target_ids=target_ids,
        rollback_on_failure=bool(req.rollback_on_failure),
    )
    _enforce_compliance_approval_policy(
        db=db,
        target_ids=target_ids,
        approval_id=approval_id,
    )
    execution_id = _resolve_compliance_execution_id(
        db=db,
        req=req,
        target_ids=target_ids,
        approval_id=approval_id,
    )

    engine = ComplianceEngine(db)
    batch = engine.remediate_config_drift_batch(
        target_ids,
        save_pre_backup=bool(req.save_pre_backup),
        pre_check_commands=list(req.pre_check_commands or []),
        prepare_device_snapshot=bool(req.prepare_device_snapshot),
        rollback_on_failure=bool(req.rollback_on_failure),
        post_check_enabled=bool(req.post_check_enabled),
        post_check_commands=list(req.post_check_commands or []),
        canary_count=int(req.canary_count or 0),
        wave_size=int(req.wave_size or 0),
        stop_on_wave_failure=bool(req.stop_on_wave_failure),
        inter_wave_delay_seconds=float(req.inter_wave_delay_seconds or 0.0),
        require_drift_gate=bool(req.require_drift_gate),
        idempotency_key=req.idempotency_key,
        approval_id=approval_id,
        execution_id=execution_id,
    )
    ApprovalExecutionService.finalize_approval_execution(
        db,
        approval_id=approval_id,
        execution_id=execution_id,
        result=dict(batch or {}),
    )
    summary = list(batch.get("summary") or [])
    first = dict(summary[0] or {}) if summary else {}
    out = dict(first.get("result") or {})
    if not out:
        out = {
            "status": first.get("status") or "unknown",
            "device_id": int(first.get("device_id") or device_id),
            "error": first.get("error"),
        }
    out["execution"] = dict(batch.get("execution") or {})
    out["approval_id"] = batch.get("approval_id")
    out["execution_id"] = batch.get("execution_id")
    out["wave"] = first.get("wave")
    return out


def _remediate_config_drift_batch_impl(
    req: DriftRemediateBatchRequest,
    db: Session = Depends(get_db),
):
    target_ids = ChangeExecutionService._normalize_device_ids(list(req.device_ids or []))
    _enforce_compliance_support_policy(
        db=db,
        target_ids=target_ids,
        rollback_on_failure=bool(req.rollback_on_failure),
    )
    approval_id = int(req.approval_id) if req.approval_id is not None else None
    _enforce_compliance_approval_policy(
        db=db,
        target_ids=target_ids,
        approval_id=approval_id,
    )
    execution_id = _resolve_compliance_execution_id(
        db=db,
        req=req,
        target_ids=target_ids,
        approval_id=approval_id,
    )

    engine = ComplianceEngine(db)
    out = engine.remediate_config_drift_batch(
        target_ids,
        save_pre_backup=bool(req.save_pre_backup),
        pre_check_commands=list(req.pre_check_commands or []),
        prepare_device_snapshot=bool(req.prepare_device_snapshot),
        rollback_on_failure=bool(req.rollback_on_failure),
        post_check_enabled=bool(req.post_check_enabled),
        post_check_commands=list(req.post_check_commands or []),
        canary_count=int(req.canary_count or 0),
        wave_size=int(req.wave_size or 0),
        stop_on_wave_failure=bool(req.stop_on_wave_failure),
        inter_wave_delay_seconds=float(req.inter_wave_delay_seconds or 0.0),
        require_drift_gate=bool(req.require_drift_gate),
        idempotency_key=req.idempotency_key,
        approval_id=approval_id,
        execution_id=execution_id,
    )
    ApprovalExecutionService.finalize_approval_execution(
        db,
        approval_id=approval_id,
        execution_id=execution_id,
        result=dict(out or {}),
    )
    return out


@router.post("/drift/remediate-batch")
def remediate_config_drift_batch(
    req: DriftRemediateBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    return _remediate_config_drift_batch_impl(req=req, db=db)


@router.post("/drift/remediate/batch", include_in_schema=False)
def remediate_config_drift_batch_legacy_alias(
    req: DriftRemediateBatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    return _remediate_config_drift_batch_impl(req=req, db=db)


def _safe_parse_json(raw: str) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(str(raw or ""))
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _p95(values: List[int]) -> Optional[int]:
    nums = sorted([int(v) for v in list(values or []) if v is not None])
    if not nums:
        return None
    idx = min(len(nums) - 1, max(0, int(math.ceil(len(nums) * 0.95) - 1)))
    return int(nums[idx])


@router.get("/drift/kpi/summary")
def get_drift_kpi_summary(
    days: int = Query(30, ge=1, le=365),
    site_id: Optional[int] = Query(None),
    limit: int = Query(5000, ge=10, le=20000),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    def _setting_float(key: str, default: float) -> float:
        try:
            row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if not row or row.value is None:
                return float(default)
            return float(str(row.value).strip())
        except Exception:
            return float(default)

    since = datetime.now() - timedelta(days=int(days))
    query = (
        db.query(EventLog)
        .filter(EventLog.event_id == "CONFIG_DRIFT_REMEDIATION_KPI")
        .filter(EventLog.timestamp >= since)
    )
    if site_id is not None:
        query = query.join(Device, Device.id == EventLog.device_id).filter(Device.site_id == int(site_id))
    rows = query.order_by(desc(EventLog.timestamp)).limit(int(limit)).all()

    parsed: List[Dict[str, Any]] = []
    for row in rows:
        payload = _safe_parse_json(row.message)
        if not payload:
            continue
        payload.setdefault("device_id", int(row.device_id) if row.device_id is not None else None)
        parsed.append(payload)

    rollback_ms: List[int] = []
    failure_causes: Dict[str, int] = {}
    total = len(parsed)
    success = 0
    failed = 0
    post_check_failures = 0
    rollback_attempted = 0
    rollback_success = 0
    approval_context_events = 0
    traced = 0

    for p in parsed:
        st = str(p.get("status") or "").strip().lower()
        if st == "ok":
            success += 1
        else:
            failed += 1
            cause = str(p.get("failure_cause") or "unknown").strip() or "unknown"
            failure_causes[cause] = int(failure_causes.get(cause, 0)) + 1

        if bool(p.get("post_check_failed")):
            post_check_failures += 1
        if bool(p.get("rollback_attempted")):
            rollback_attempted += 1
            if bool(p.get("rollback_success")):
                rollback_success += 1

        if bool(p.get("post_check_failed")) and bool(p.get("rollback_attempted")):
            dur = p.get("rollback_duration_ms")
            try:
                if dur is not None:
                    rollback_ms.append(int(dur))
            except Exception:
                pass

        if p.get("approval_id") is not None:
            approval_context_events += 1
            if str(p.get("execution_id") or "").strip():
                traced += 1

    trace_coverage = (
        100.0
        if approval_context_events == 0
        else round((traced / approval_context_events) * 100.0, 2)
    )
    success_rate = 100.0 if total == 0 else round((success / total) * 100.0, 2)
    failure_rate = 0.0 if total == 0 else round((failed / total) * 100.0, 2)
    rollback_success_rate = 100.0 if rollback_attempted == 0 else round((rollback_success / rollback_attempted) * 100.0, 2)
    rollback_p95 = _p95(rollback_ms)

    min_success_target = _setting_float("ops_alerts_min_change_success_rate_pct", 98.0)
    max_failure_target = _setting_float("ops_alerts_max_change_failure_rate_pct", 1.0)
    max_rollback_p95_target = _setting_float("ops_alerts_max_change_rollback_p95_ms", 180000.0)
    min_trace_target = _setting_float("ops_alerts_min_change_trace_coverage_pct", 100.0)
    alerts: List[Dict[str, Any]] = []
    if total > 0:
        if success_rate < float(min_success_target):
            alerts.append(
                {
                    "code": "change_success_rate_low",
                    "title": "Change success rate is below target",
                    "value": float(success_rate),
                    "threshold": float(min_success_target),
                }
            )
        if failure_rate > float(max_failure_target):
            alerts.append(
                {
                    "code": "change_failure_rate_high",
                    "title": "Change failure rate is above target",
                    "value": float(failure_rate),
                    "threshold": float(max_failure_target),
                }
            )
        if rollback_p95 is not None and float(rollback_p95) > float(max_rollback_p95_target):
            alerts.append(
                {
                    "code": "change_rollback_p95_high",
                    "title": "Rollback P95 is above target",
                    "value": float(rollback_p95),
                    "threshold": float(max_rollback_p95_target),
                }
            )
        if trace_coverage < float(min_trace_target):
            alerts.append(
                {
                    "code": "change_trace_coverage_low",
                    "title": "Approval trace coverage is below target",
                    "value": float(trace_coverage),
                    "threshold": float(min_trace_target),
                }
            )
    status = "idle"
    if total > 0:
        if len(alerts) >= 2:
            status = "critical"
        elif alerts:
            status = "warning"
        else:
            status = "healthy"

    top_causes = sorted(
        [{"cause": k, "count": int(v)} for k, v in failure_causes.items()],
        key=lambda x: x["count"],
        reverse=True,
    )[:10]

    return {
        "window_days": int(days),
        "site_id": int(site_id) if site_id is not None else None,
        "totals": {
            "events": int(total),
            "success": int(success),
            "failed": int(failed),
            "post_check_failures": int(post_check_failures),
            "rollback_attempted": int(rollback_attempted),
            "rollback_success": int(rollback_success),
            "approval_context_events": int(approval_context_events),
            "approval_traced": int(traced),
        },
        "kpi": {
            "status": status,
            "change_success_rate_pct": success_rate,
            "change_failure_rate_pct": failure_rate,
            "rollback_p95_ms": rollback_p95,
            "rollback_success_rate_pct": rollback_success_rate,
            "approval_execution_trace_coverage_pct": trace_coverage,
            "alerts": alerts,
            "targets": {
                "min_success_rate_pct": float(min_success_target),
                "max_failure_rate_pct": float(max_failure_target),
                "max_rollback_p95_ms": int(max_rollback_p95_target),
                "min_trace_coverage_pct": float(min_trace_target),
            },
        },
        "failure_causes": top_causes,
    }
