from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.services.audit_service import AuditService
from app.services.closed_loop_service import ClosedLoopService
from app.services.cloud_intent_execution_service import CloudIntentExecutionService
from app.services.intent_service import IntentService


router = APIRouter()


class IntentRequest(BaseModel):
    intent_type: str
    name: str
    spec: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True
    idempotency_key: Optional[str] = None
    approval_id: Optional[int] = None
    execution_id: Optional[str] = None


class ClosedLoopRulesRequest(BaseModel):
    rules: List[Dict[str, Any]] = Field(default_factory=list)


class ClosedLoopEvaluateRequest(BaseModel):
    signals: Dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = True
    use_signal_snapshot: bool = False
    site_id: Optional[int] = None
    device_id: Optional[int] = None


def _ensure_enabled(db: Session) -> None:
    if IntentService.is_enabled(db):
        return
    raise HTTPException(
        status_code=403,
        detail="Intent engine is disabled. Enable 'intent_engine_enabled' in Settings first.",
    )


def _ensure_closed_loop_enabled(db: Session) -> None:
    if ClosedLoopService.engine_enabled(db):
        return
    raise HTTPException(
        status_code=403,
        detail="Closed-loop engine is disabled. Enable 'closed_loop_engine_enabled' in Settings first.",
    )


@router.get("/status")
def get_intent_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return {
        "enabled": IntentService.is_enabled(db),
        "apply_requires_approval": IntentService.apply_requires_approval(db),
        "apply_execute_actions_enabled": IntentService.apply_execute_actions_enabled(db),
        "max_auto_apply_risk_score": IntentService.max_auto_apply_risk_score(db),
        "northbound_policy_enabled": IntentService.northbound_policy_enabled(db),
        "northbound_max_auto_publish_risk_score": IntentService.northbound_max_auto_publish_risk_score(db),
        "cloud_execution_live_apply_enabled": CloudIntentExecutionService.live_apply_enabled(),
        "cloud_execution_mode": CloudIntentExecutionService.execution_mode(),
        "cloud_state_backend": CloudIntentExecutionService.state_backend(),
        "cloud_state_prefix": CloudIntentExecutionService.state_prefix(),
        "cloud_execution_readiness": CloudIntentExecutionService.execution_readiness(),
        "supported_intents": IntentService.supported_intents(),
    }


@router.post("/validate")
def validate_intent(
    req: IntentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    _ensure_enabled(db)
    payload = req.model_dump()
    out = IntentService.validate_intent(db, payload)
    AuditService.log(
        db=db,
        user=current_user,
        action="INTENT_VALIDATE",
        resource_type="Intent",
        resource_name=f"{out.get('normalized_intent', {}).get('intent_type', 'unknown')}:{out.get('normalized_intent', {}).get('name', '')}",
        details={
            "intent_type": out.get("normalized_intent", {}).get("intent_type"),
            "valid": bool(out.get("valid")),
            "errors": len(out.get("errors") or []),
            "warnings": len(out.get("warnings") or []),
            "conflicts": len(out.get("conflicts") or []),
        },
        status="success" if bool(out.get("valid")) else "failed",
    )
    return out


@router.get("/closed-loop/status")
def get_closed_loop_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return ClosedLoopService.status(db)


@router.get("/closed-loop/rules")
def get_closed_loop_rules(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    rules = ClosedLoopService.get_rules(db)
    return {"count": len(rules), "rules": rules}


@router.put("/closed-loop/rules")
def put_closed_loop_rules(
    req: ClosedLoopRulesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin),
):
    try:
        out = ClosedLoopService.save_rules(db, list(req.rules or []))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    AuditService.log(
        db=db,
        user=current_user,
        action="INTENT_CLOSED_LOOP_RULES_SAVE",
        resource_type="ClosedLoop",
        resource_name="rules",
        details={"saved": int(out.get("saved") or 0)},
        status="success",
    )
    return out


@router.get("/closed-loop/rules/lint")
def get_closed_loop_rules_lint(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return ClosedLoopService.lint_saved_rules(db)


@router.post("/closed-loop/rules/lint")
def lint_closed_loop_rules(
    req: ClosedLoopRulesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    try:
        out = ClosedLoopService.lint_rules(list(req.rules or []))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    AuditService.log(
        db=db,
        user=current_user,
        action="INTENT_CLOSED_LOOP_RULES_LINT",
        resource_type="ClosedLoop",
        resource_name="rules",
        details={
            "rules_total": int(out.get("rules_total") or 0),
            "rules_enabled": int(out.get("rules_enabled") or 0),
            "conflicts_count": int(out.get("conflicts_count") or 0),
            "warnings_count": int(out.get("warnings_count") or 0),
        },
        status="success",
    )
    return out


@router.get("/closed-loop/snapshot")
def get_closed_loop_snapshot(
    site_id: Optional[int] = None,
    device_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return ClosedLoopService.build_signal_snapshot(db, site_id=site_id, device_id=device_id)


@router.post("/closed-loop/evaluate")
def evaluate_closed_loop(
    req: ClosedLoopEvaluateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    _ensure_closed_loop_enabled(db)
    signals: Dict[str, Any] = dict(req.signals or {})
    snapshot_meta: Optional[Dict[str, Any]] = None

    if bool(req.use_signal_snapshot):
        snapshot = ClosedLoopService.build_signal_snapshot(db, site_id=req.site_id, device_id=req.device_id)
        signals = snapshot
        snapshot_meta = {
            "site_id": req.site_id,
            "device_id": req.device_id,
            "devices_total": int((snapshot.get("summary") or {}).get("devices_total") or 0),
        }

    if not isinstance(signals, dict) or not signals:
        raise HTTPException(status_code=400, detail="signals must be a non-empty object")

    out = ClosedLoopService.evaluate(
        db,
        signals=signals,
        actor_user=current_user,
        dry_run=bool(req.dry_run),
    )
    ClosedLoopService.emit_evaluation_summary(
        db,
        result=out,
        dry_run=bool(req.dry_run),
        source="api",
        site_id=req.site_id,
        device_id=req.device_id,
        snapshot_summary=snapshot_meta or {},
        commit=True,
    )
    AuditService.log(
        db=db,
        user=current_user,
        action="INTENT_CLOSED_LOOP_EVALUATE",
        resource_type="ClosedLoop",
        resource_name="evaluate",
        details={
            "dry_run": bool(req.dry_run),
            "use_signal_snapshot": bool(req.use_signal_snapshot),
            "triggered": int(out.get("triggered") or 0),
            "executed": int(out.get("executed") or 0),
            "blocked": int(out.get("blocked") or 0),
            "snapshot": snapshot_meta,
        },
        status="success",
    )
    return out


@router.post("/simulate")
def simulate_intent(
    req: IntentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    _ensure_enabled(db)
    payload = req.model_dump()
    out = IntentService.simulate_intent(db, payload)
    validation = out.get("validation") if isinstance(out.get("validation"), dict) else {}
    normalized = validation.get("normalized_intent") if isinstance(validation.get("normalized_intent"), dict) else {}
    AuditService.log(
        db=db,
        user=current_user,
        action="INTENT_SIMULATE",
        resource_type="Intent",
        resource_name=f"{normalized.get('intent_type', 'unknown')}:{normalized.get('name', '')}",
        details={
            "intent_type": normalized.get("intent_type"),
            "valid": bool(validation.get("valid")),
            "risk_score": int(out.get("risk_score") or 0),
            "apply_eligible": bool(out.get("apply_eligible")),
            "warnings": len(validation.get("warnings") or []),
            "conflicts": len(validation.get("conflicts") or []),
        },
        status="success" if bool(validation.get("valid")) else "failed",
    )
    return out


@router.post("/apply")
def apply_intent(
    req: IntentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin),
):
    _ensure_enabled(db)
    payload = req.model_dump()
    out = IntentService.apply_intent(db, payload, actor_user=current_user)
    status_text = str(out.get("status") or "").strip().lower()
    AuditService.log(
        db=db,
        user=current_user,
        action="INTENT_APPLY",
        resource_type="Intent",
        resource_name=f"{str(req.intent_type or '').strip().lower()}:{str(req.name or '').strip()}",
        details={
            "status": status_text,
            "execution_id": out.get("execution_id"),
            "approval_id": out.get("approval_id"),
            "idempotency_key": req.idempotency_key,
            "dry_run": bool(req.dry_run),
        },
        status="success" if status_text in {"dry_run", "applied", "skipped_idempotent"} else "failed",
    )
    return out
