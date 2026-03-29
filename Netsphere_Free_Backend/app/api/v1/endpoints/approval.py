from typing import List, Optional, Any
import io
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.approval import ApprovalRequest
from app.models.user import User
from app.api import deps
from app.services.change_execution_service import ChangeExecutionService
from app.services.approval_evidence_service import ApprovalEvidenceService
from app.services.service_group_service import ServiceGroupService
from app.schemas.approval_service_impact import ApprovalServiceImpactResponse
from pydantic import BaseModel, ConfigDict

router = APIRouter()

# --- Pydantic Schemas ---

class ApprovalRequestBase(BaseModel):
    title: str
    description: Optional[str] = None
    request_type: str = "config_deploy"
    payload: Optional[dict] = None # JSON Payload

class ApprovalCreate(ApprovalRequestBase):
    requester_comment: Optional[str] = None

class ApprovalDecision(BaseModel):
    approver_comment: Optional[str] = None

class ApprovalResponse(ApprovalRequestBase):
    id: int
    requester_id: int
    approver_id: Optional[int] = None
    status: str
    requester_comment: Optional[str] = None
    approver_comment: Optional[str] = None
    created_at: datetime
    decided_at: Optional[datetime] = None
    
    requester_name: Optional[str] = None # For UI convenience
    approver_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# --- Endpoints ---

def _persist_payload(req: ApprovalRequest, payload: dict, db: Session) -> None:
    req.payload = dict(payload or {})
    db.commit()
    db.refresh(req)


def _ensure_execution_trace(payload: dict, approval_id: int, execution_id: str) -> dict:
    out = dict(payload or {})
    out["approval_id"] = int(approval_id)
    out["execution_id"] = str(execution_id)
    trace = out.get("execution_trace")
    if not isinstance(trace, dict):
        trace = {}
    trace["approval_id"] = int(approval_id)
    trace["execution_id"] = str(execution_id)
    out["execution_trace"] = trace
    return out


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    t = str(value).strip().lower()
    if t in {"1", "true", "yes", "y", "on"}:
        return True
    if t in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _dispatch_approved_execution(
    req: ApprovalRequest,
    current_user: User,
    db: Session,
) -> None:
    request_type = str(req.request_type or "").strip().lower()
    payload = dict(req.payload or {})

    if request_type not in {"config_drift_remediate", "template_deploy", "fabric_deploy", "cloud_bootstrap", "intent_apply"}:
        return

    execution_id = str(payload.get("execution_id") or "").strip()
    if not execution_id:
        execution_id = ChangeExecutionService.make_fingerprint(
            f"approval_{request_type}",
            {
                "approval_id": int(req.id),
                "request_type": request_type,
                "template_id": payload.get("template_id"),
                "spine_ids": payload.get("spine_ids"),
                "leaf_ids": payload.get("leaf_ids"),
                "device_id": payload.get("device_id"),
                "device_ids": payload.get("device_ids"),
            },
        )
    payload = _ensure_execution_trace(payload, int(req.id), execution_id)
    payload["execution_status"] = "dispatching"
    _persist_payload(req, payload, db)

    if request_type == "config_drift_remediate":
        try:
            from app.tasks.compliance import run_config_drift_remediation_for_approval

            if hasattr(run_config_drift_remediation_for_approval, "apply_async"):
                r = run_config_drift_remediation_for_approval.apply_async(
                    args=[req.id, execution_id],
                    queue="maintenance",
                )
                payload["execution_status"] = "queued"
                payload["job_id"] = r.id
                payload["execution_task_id"] = r.id
            else:
                result = run_config_drift_remediation_for_approval(req.id, execution_id=execution_id)
                payload["execution_status"] = "executed"
                payload["execution_result"] = result
            _persist_payload(req, payload, db)
            return
        except Exception as e:
            payload["execution_status"] = "dispatch_failed"
            payload["dispatch_error"] = f"{type(e).__name__}: {e}"
            _persist_payload(req, payload, db)
            return

    if request_type == "template_deploy":
        try:
            from app.api.v1.endpoints.config_template import (
                TemplateDeployRequest,
                deploy_template,
            )

            template_id = _to_int(payload.get("template_id"), 0)
            device_ids = [_to_int(x, 0) for x in list(payload.get("device_ids") or [])]
            device_ids = [x for x in device_ids if x > 0]
            if template_id <= 0:
                raise ValueError("template_id is required")
            if not device_ids:
                raise ValueError("device_ids is required")

            deploy_req = TemplateDeployRequest(
                device_ids=device_ids,
                variables=dict(payload.get("variables") or {}),
                save_pre_backup=_to_bool(payload.get("save_pre_backup"), True),
                rollback_on_failure=_to_bool(payload.get("rollback_on_failure"), True),
                prepare_device_snapshot=_to_bool(payload.get("prepare_device_snapshot"), True),
                pre_check_commands=[str(x) for x in list(payload.get("pre_check_commands") or []) if str(x).strip()],
                post_check_enabled=_to_bool(payload.get("post_check_enabled"), True),
                post_check_commands=[str(x) for x in list(payload.get("post_check_commands") or []) if str(x).strip()],
                canary_count=_to_int(payload.get("canary_count"), 0),
                wave_size=_to_int(payload.get("wave_size"), 0),
                stop_on_wave_failure=_to_bool(payload.get("stop_on_wave_failure"), True),
                inter_wave_delay_seconds=_to_float(payload.get("inter_wave_delay_seconds"), 0.0),
                idempotency_key=str(payload.get("idempotency_key") or "").strip() or None,
                approval_id=int(req.id),
                execution_id=execution_id,
            )
            result = deploy_template(
                template_id=template_id,
                req=deploy_req,
                db=db,
                current_user=current_user,
            )
            payload["execution_status"] = "executed"
            payload["execution_result"] = result
            _persist_payload(req, payload, db)
            return
        except Exception as e:
            payload["execution_status"] = "dispatch_failed"
            payload["dispatch_error"] = f"{type(e).__name__}: {e}"
            _persist_payload(req, payload, db)
            return

    if request_type == "fabric_deploy":
        try:
            from app.services.fabric_service import FabricService

            spine_ids = [_to_int(x, 0) for x in list(payload.get("spine_ids") or [])]
            leaf_ids = [_to_int(x, 0) for x in list(payload.get("leaf_ids") or [])]
            spine_ids = [x for x in spine_ids if x > 0]
            leaf_ids = [x for x in leaf_ids if x > 0]
            if not spine_ids:
                raise ValueError("spine_ids is required")
            if not leaf_ids:
                raise ValueError("leaf_ids is required")
            verify_cmds = [str(x) for x in list(payload.get("verify_commands") or []) if str(x).strip()]
            if not verify_cmds:
                verify_cmds = ["show bgp summary", "show nve peers"]

            result = FabricService(db).execute_deploy(
                spines=spine_ids,
                leafs=leaf_ids,
                asn_base=_to_int(payload.get("asn"), 65000),
                vni_base=_to_int(payload.get("vni_base"), 10000),
                dry_run=_to_bool(payload.get("dry_run"), True),
                pre_check_commands=[str(x) for x in list(payload.get("pre_check_commands") or []) if str(x).strip()],
                verify_commands=verify_cmds,
                rollback_on_error=_to_bool(payload.get("rollback_on_error"), True),
                canary_count=_to_int(payload.get("canary_count"), 0),
                wave_size=_to_int(payload.get("wave_size"), 0),
                stop_on_wave_failure=_to_bool(payload.get("stop_on_wave_failure"), True),
                inter_wave_delay_seconds=_to_float(payload.get("inter_wave_delay_seconds"), 0.0),
                idempotency_key=str(payload.get("idempotency_key") or "").strip() or None,
                approval_id=int(req.id),
                execution_id=execution_id,
            )
            payload["execution_status"] = "executed"
            payload["execution_result"] = result
            _persist_payload(req, payload, db)
            return
        except Exception as e:
            payload["execution_status"] = "dispatch_failed"
            payload["dispatch_error"] = f"{type(e).__name__}: {e}"
            _persist_payload(req, payload, db)
            return

    if request_type == "cloud_bootstrap":
        try:
            from app.schemas.cloud import CloudBootstrapRunRequest
            from app.services.cloud_bootstrap_service import CloudBootstrapService

            account_ids = [_to_int(x, 0) for x in list(payload.get("account_ids") or [])]
            account_ids = [x for x in account_ids if x > 0]
            regions = [str(x).strip() for x in list(payload.get("regions") or []) if str(x).strip()]
            resource_ids = [str(x).strip() for x in list(payload.get("resource_ids") or []) if str(x).strip()]
            bootstrap_req = CloudBootstrapRunRequest(
                account_ids=account_ids or None,
                regions=regions or None,
                resource_ids=resource_ids or None,
                dry_run=_to_bool(payload.get("dry_run"), True),
                pre_check_enabled=_to_bool(payload.get("pre_check_enabled"), True),
                post_check_enabled=_to_bool(payload.get("post_check_enabled"), True),
                rollback_on_failure=_to_bool(payload.get("rollback_on_failure"), True),
                canary_count=_to_int(payload.get("canary_count"), 0),
                wave_size=_to_int(payload.get("wave_size"), 0),
                stop_on_wave_failure=_to_bool(payload.get("stop_on_wave_failure"), True),
                inter_wave_delay_seconds=_to_float(payload.get("inter_wave_delay_seconds"), 0.0),
                idempotency_key=str(payload.get("idempotency_key") or "").strip() or None,
                force=_to_bool(payload.get("force"), False),
                approval_id=int(req.id),
                execution_id=str(execution_id or "").strip() or None,
                script_template=str(payload.get("script_template") or "").strip() or None,
                context=dict(payload.get("context") or {}),
            )
            result = CloudBootstrapService.run(
                db,
                tenant_id=getattr(current_user, "tenant_id", None),
                owner_id=int(current_user.id),
                req=bootstrap_req,
            )
            payload["execution_status"] = "executed"
            payload["execution_result"] = result.model_dump() if hasattr(result, "model_dump") else result
            _persist_payload(req, payload, db)
            return
        except Exception as e:
            payload["execution_status"] = "dispatch_failed"
            payload["dispatch_error"] = f"{type(e).__name__}: {e}"
            _persist_payload(req, payload, db)
            return

    if request_type == "intent_apply":
        try:
            from app.services.intent_service import IntentService

            live_payload = dict(payload or {})
            live_payload["dry_run"] = _to_bool(live_payload.get("dry_run"), False)
            live_payload["approval_id"] = int(req.id)
            live_payload["execution_id"] = execution_id

            result = IntentService.apply_intent(
                db,
                live_payload,
                actor_user=current_user,
            )
            status_text = str(result.get("status") or "").strip().lower()
            payload["execution_status"] = "executed" if status_text in {"applied", "dry_run", "skipped_idempotent"} else "failed"
            payload["execution_result"] = result
            _persist_payload(req, payload, db)
            return
        except Exception as e:
            payload["execution_status"] = "dispatch_failed"
            payload["dispatch_error"] = f"{type(e).__name__}: {e}"
            _persist_payload(req, payload, db)
            return

@router.post("/", response_model=ApprovalResponse)
def create_request(
    req: ApprovalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """
    Submit a new approval request.
    """
    db_req = ApprovalRequest(
        **req.model_dump(exclude={"requester_name", "approver_name"}), # Create model kwargs
        requester_id=current_user.id,
        status="pending"
    )
    db.add(db_req)
    db.commit()
    db.refresh(db_req)
    
    # Return with name (manual population or relationship load)
    res = ApprovalResponse.model_validate(db_req)
    res.requester_name = current_user.username
    return res

@router.get("/", response_model=List[ApprovalResponse])
def get_requests(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """
    List approval requests. Filter by status if provided.
    """
    query = db.query(ApprovalRequest)
    
    if status:
        query = query.filter(ApprovalRequest.status == status)
        
    # Optional: Filter strictly for non-admins? usually admins can see all.
    # If standard user, maybe only see own requests?
    if current_user.role != "admin":
        query = query.filter(ApprovalRequest.requester_id == current_user.id)

    total = query.count()
    items = query.order_by(ApprovalRequest.created_at.desc()).offset(skip).limit(limit).all()

    # Populate names manually to avoid complex joins in Pydantic mapping issues
    result = []
    for item in items:
        resp = ApprovalResponse.model_validate(item)
        if item.requester: resp.requester_name = item.requester.username
        if item.approver: resp.approver_name = item.approver.username
        result.append(resp)
        
    return result

@router.get("/{id}", response_model=ApprovalResponse)
def get_request(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    # Check permission
    if current_user.role != "admin" and req.requester_id != current_user.id:
         raise HTTPException(status_code=403, detail="Not enough permissions")

    resp = ApprovalResponse.model_validate(req)
    if req.requester: resp.requester_name = req.requester.username
    if req.approver: resp.approver_name = req.approver.username
    return resp


@router.get("/{id}/service-impact", response_model=ApprovalServiceImpactResponse)
def get_request_service_impact(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if current_user.role != "admin" and req.requester_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    groups = ServiceGroupService.build_approval_service_impacts(db, req)
    return {
        "approval_id": int(req.id),
        "summary": ServiceGroupService.summarize_service_impacts(groups),
        "groups": groups,
    }


@router.get("/{id}/evidence-package")
def download_approval_evidence_package(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin),
):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    data = ApprovalEvidenceService.build_package(db, req)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"approval_evidence_{int(req.id)}_{ts}.zip"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.post("/{id}/approve", response_model=ApprovalResponse)
def approve_request(
    id: int,
    decision: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin)
):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    if req.status != "pending":
         raise HTTPException(status_code=400, detail="Request is already decided")

    req.status = "approved"
    req.approver_id = current_user.id
    req.approver_comment = decision.approver_comment
    req.decided_at = datetime.now()
    
    db.commit()
    db.refresh(req)
    
    payload = dict(req.payload or {})
    payload["approval_id"] = int(req.id)
    _persist_payload(req, payload, db)
    _dispatch_approved_execution(req=req, current_user=current_user, db=db)
    
    resp = ApprovalResponse.model_validate(req)
    if req.requester: resp.requester_name = req.requester.username
    if req.approver: resp.approver_name = req.approver.username
    return resp

@router.post("/{id}/reject", response_model=ApprovalResponse)
def reject_request(
    id: int,
    decision: ApprovalDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin)
):
    req = db.query(ApprovalRequest).filter(ApprovalRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    if req.status != "pending":
         raise HTTPException(status_code=400, detail="Request is already decided")

    req.status = "rejected"
    req.approver_id = current_user.id
    req.approver_comment = decision.approver_comment
    req.decided_at = datetime.now()
    
    db.commit()
    db.refresh(req)
    
    resp = ApprovalResponse.model_validate(req)
    if req.requester: resp.requester_name = req.requester.username
    if req.approver: resp.approver_name = req.approver.username
    return resp
