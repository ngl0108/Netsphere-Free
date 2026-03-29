from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel

from app.db.session import get_db
from app.api import deps
from app.models.device import Device
from app.models.user import User
from app.services.fabric_service import FabricService
from app.services.change_policy_service import ChangePolicyService
from app.services.change_execution_service import ChangeExecutionService
from app.services.approval_execution_service import ApprovalExecutionService
from app.services.device_support_policy_service import DeviceSupportPolicyService

router = APIRouter()

class FabricGenerateRequest(BaseModel):
    spine_ids: List[int]
    leaf_ids: List[int]
    asn: int = 65000
    vni_base: int = 10000


class FabricDeployRequest(BaseModel):
    spine_ids: List[int]
    leaf_ids: List[int]
    asn: int = 65000
    vni_base: int = 10000
    dry_run: bool = True
    pre_check_commands: List[str] = []
    verify_commands: List[str] = ["show bgp summary", "show nve peers"]
    rollback_on_error: bool = True
    canary_count: int = 0
    wave_size: int = 0
    stop_on_wave_failure: bool = True
    inter_wave_delay_seconds: float = 0.0
    idempotency_key: str | None = None
    approval_id: int | None = None
    execution_id: str | None = None

@router.post("/generate")
def generate_fabric_config(
    request: FabricGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    """
    Generate BGP EVPN (VXLAN) Configuration for Spine-Leaf Fabric.
    """
    service = FabricService(db)
    try:
        configs = service.generate_fabric_config(
            spines=request.spine_ids,
            leafs=request.leaf_ids,
            asn_base=request.asn,
            vni_base=request.vni_base,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return configs


@router.post("/deploy")
def deploy_fabric_config(
    request: FabricDeployRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin),
):
    """
    Fabric deploy execution engine with dry-run, validation, verify and rollback.
    """
    service = FabricService(db)
    target_ids = ChangeExecutionService._normalize_device_ids([*(request.spine_ids or []), *(request.leaf_ids or [])])
    target_devices = db.query(Device).filter(Device.id.in_(target_ids)).all() if target_ids else []

    blocked_config = DeviceSupportPolicyService.collect_blocked_devices(
        db,
        devices=target_devices,
        feature="config",
    )
    if blocked_config:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEVICE_SUPPORT_BLOCKED",
                "message": "Fabric deploy blocked for unsupported devices.",
                "details": {"feature": "config", "blocked_devices": blocked_config},
            },
        )
    if bool(request.rollback_on_error):
        blocked_rollback = DeviceSupportPolicyService.collect_blocked_devices(
            db,
            devices=target_devices,
            feature="rollback",
        )
        if blocked_rollback:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ROLLBACK_STRATEGY_UNSUPPORTED",
                    "message": "Rollback-on-error is blocked for devices without supported rollback strategy.",
                    "details": {
                        "feature": "rollback",
                        "blocked_devices": blocked_rollback,
                        "hint": "Disable rollback_on_error or target rollback-supported vendors only.",
                    },
                },
            )

    approval_id = int(request.approval_id) if request.approval_id is not None else None
    if ChangePolicyService.requires_fabric_live_approval(
        db,
        dry_run=bool(request.dry_run),
        approval_id=approval_id,
    ):
        raise HTTPException(
            status_code=409,
            detail="Approval required for live fabric deploy. Use dry_run or submit an approval request first.",
        )
    execution_id = str(request.execution_id or "").strip()
    if not execution_id:
        execution_id = ChangeExecutionService.make_fingerprint(
            "fabric_deploy_execution",
            {
                "spine_ids": list(request.spine_ids or []),
                "leaf_ids": list(request.leaf_ids or []),
                "asn_base": int(request.asn or 65000),
                "vni_base": int(request.vni_base or 10000),
                "approval_id": approval_id,
                "wave_size": int(request.wave_size or 0),
                "canary_count": int(request.canary_count or 0),
            },
        )
    execution_id = ApprovalExecutionService.bind_approved_execution(
        db,
        approval_id=approval_id,
        expected_request_type="fabric_deploy",
        execution_id=execution_id,
    )
    try:
        out = service.execute_deploy(
            spines=request.spine_ids,
            leafs=request.leaf_ids,
            asn_base=request.asn,
            vni_base=request.vni_base,
            dry_run=bool(request.dry_run),
            pre_check_commands=list(request.pre_check_commands or []),
            verify_commands=list(request.verify_commands or []),
            rollback_on_error=bool(request.rollback_on_error),
            canary_count=int(request.canary_count or 0),
            wave_size=int(request.wave_size or 0),
            stop_on_wave_failure=bool(request.stop_on_wave_failure),
            inter_wave_delay_seconds=float(request.inter_wave_delay_seconds or 0.0),
            idempotency_key=(str(request.idempotency_key).strip() if request.idempotency_key else None),
            approval_id=approval_id,
            execution_id=execution_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ApprovalExecutionService.finalize_approval_execution(
        db,
        approval_id=approval_id,
        execution_id=execution_id,
        result=dict(out or {}),
    )
    return out
