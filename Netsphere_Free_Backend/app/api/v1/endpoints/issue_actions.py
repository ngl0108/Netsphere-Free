from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.device import Issue
from app.models.operation_action import OperationAction
from app.models.user import User
from app.schemas.operation_action import (
    OperationActionCreate,
    OperationActionResponse,
    OperationActionUpdate,
)
from app.services.operation_action_service import OperationActionService

router = APIRouter()


@router.get("/issues/{issue_id}/actions", response_model=list[OperationActionResponse])
def list_issue_actions(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    issue = db.query(Issue).filter(Issue.id == int(issue_id)).first()
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return OperationActionService.list_for_issue(db, issue_id)


@router.post("/issues/{issue_id}/actions", response_model=OperationActionResponse)
def create_issue_action(
    issue_id: int,
    payload: OperationActionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    issue = db.query(Issue).filter(Issue.id == int(issue_id)).first()
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    row = OperationActionService.create_for_issue(
        db,
        issue=issue,
        payload=payload.model_dump(),
        actor=str(getattr(current_user, "username", "") or "operator"),
    )
    return OperationActionService.serialize(row)


@router.put("/actions/{action_id}", response_model=OperationActionResponse)
def update_issue_action(
    action_id: int,
    payload: OperationActionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    row = OperationActionService.get(db, action_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Operation action not found")
    updated = OperationActionService.update(
        db,
        row=row,
        payload=payload.model_dump(),
        actor=str(getattr(current_user, "username", "") or "operator"),
    )
    return OperationActionService.serialize(updated)


@router.get("/actions/active", response_model=list[OperationActionResponse])
def list_active_actions(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    normalized = str(status or "").strip().lower()
    rows = db.query(OperationAction)
    if normalized:
        rows = rows.filter(OperationAction.status == normalized)
    else:
        rows = rows.filter(OperationAction.status.in_(sorted(OperationActionService.ACTIVE_STATUSES)))
    rows = rows.order_by(OperationAction.updated_at.desc(), OperationAction.id.desc()).limit(100).all()
    return [OperationActionService.serialize(row) for row in rows]
