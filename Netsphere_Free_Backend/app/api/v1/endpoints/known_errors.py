from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.api import deps
from app.db.session import get_db
from app.models.device import Issue
from app.models.user import User
from app.schemas.known_error import (
    KnownErrorCreate,
    KnownErrorRecommendationResponse,
    KnownErrorResponse,
    KnownErrorUpdate,
)
from app.services.known_error_service import KnownErrorService

router = APIRouter()


@router.get("/knowledge", response_model=list[KnownErrorResponse])
def list_known_errors(
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return KnownErrorService.list_entries(db, limit=limit)


@router.get("/issues/{issue_id}/knowledge", response_model=list[KnownErrorRecommendationResponse])
def list_issue_known_error_recommendations(
    issue_id: int,
    limit: int = Query(default=5, ge=1, le=20),
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
    return KnownErrorService.build_recommendations_for_issue(db, issue, limit=limit)


@router.post("/issues/{issue_id}/knowledge", response_model=KnownErrorResponse)
def create_known_error_from_issue(
    issue_id: int,
    payload: KnownErrorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    issue = (
        db.query(Issue)
        .options(joinedload(Issue.device))
        .filter(Issue.id == int(issue_id))
        .first()
    )
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    row = KnownErrorService.create_from_issue(
        db,
        issue=issue,
        payload=payload.model_dump(),
        actor=str(getattr(current_user, "username", "") or "operator"),
    )
    return KnownErrorService.serialize(row)


@router.put("/knowledge/{entry_id}", response_model=KnownErrorResponse)
def update_known_error(
    entry_id: int,
    payload: KnownErrorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    row = KnownErrorService.get_entry(db, entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Known error entry not found")
    updated = KnownErrorService.update_entry(
        db,
        row=row,
        payload=payload.model_dump(),
        actor=str(getattr(current_user, "username", "") or "operator"),
    )
    return KnownErrorService.serialize(updated)
