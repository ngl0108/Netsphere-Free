from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api import deps
from app.db.session import get_db
from app.models.device import Issue
from app.models.user import User
from app.schemas.issue_sop import IssueSopResponse
from app.services.issue_sop_service import IssueSopService

router = APIRouter()


@router.get("/issues/{issue_id}/sop", response_model=IssueSopResponse)
def get_issue_sop(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    issue = (
        db.query(Issue)
        .options(joinedload(Issue.device))
        .filter(Issue.id == int(issue_id))
        .first()
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return IssueSopService.build_issue_sop(db, issue)
