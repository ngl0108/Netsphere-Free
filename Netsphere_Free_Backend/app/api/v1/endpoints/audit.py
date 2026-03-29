from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.audit_service import AuditService
from typing import Optional
from app.api import deps
from app.models.user import User
from app.services.audit_chain_service import AuditChainService

router = APIRouter()

@router.get("/")
def read_audit_logs(
    skip: int = 0, 
    limit: int = 100, 
    action: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    """
    Get audit logs with optional filtering.
    """
    return AuditService.get_logs_serialized(db, skip, limit, filter_action=action)


@router.get("/verify-chain")
def verify_audit_chain(
    days: int = 30,
    limit: int = 20000,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    return AuditChainService.verify_chain(db, days=days, limit=limit)


@router.post("/seal-chain")
def seal_audit_chain(
    days: int = 365,
    limit: int = 200000,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    return AuditChainService.backfill_chain(db, days=days, limit=limit)
