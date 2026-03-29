from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.api import deps
from app.db.session import get_db
from app.models.device import Issue
from app.models.user import User
from app.schemas.issue_service_impact import IssueServiceImpactResponse
from app.services.service_group_service import ServiceGroupService

router = APIRouter()


@router.get("/issues/{issue_id}/service-impact", response_model=IssueServiceImpactResponse)
def get_issue_service_impact(
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
    return {
        "issue_id": int(issue.id),
        "groups": ServiceGroupService.build_issue_service_impacts(db, issue),
    }
