from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api import deps
from app.db.session import get_db
from app.models.device import Device, Issue
from app.models.user import User
from app.schemas.issue_approval_context import IssueApprovalContextResponse
from app.services.issue_approval_context_service import IssueApprovalContextService

router = APIRouter()


@router.get("/issues/{issue_id}/approval-context", response_model=IssueApprovalContextResponse)
def get_issue_approval_context(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    issue = (
        db.query(Issue)
        .options(joinedload(Issue.device).joinedload(Device.site_obj))
        .filter(Issue.id == int(issue_id))
        .first()
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return IssueApprovalContextService.build_issue_approval_context(db, issue)
