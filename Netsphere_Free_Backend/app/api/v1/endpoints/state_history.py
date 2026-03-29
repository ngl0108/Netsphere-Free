from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.schemas.state_history import (
    StateHistoryCompareResponse,
    StateHistorySnapshotCreateRequest,
    StateHistorySnapshotResponse,
)
from app.services.state_history_service import StateHistoryService

router = APIRouter()


@router.get("/current", response_model=StateHistorySnapshotResponse)
def get_current_state_snapshot(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    _ = current_user
    return StateHistoryService.build_current_snapshot(db)


@router.get("/snapshots", response_model=list[StateHistorySnapshotResponse])
def list_state_snapshots(
    limit: int = Query(default=12, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    _ = current_user
    return StateHistoryService.list_snapshots(db, limit=limit)


@router.post("/snapshots", response_model=StateHistorySnapshotResponse)
def create_state_snapshot(
    payload: StateHistorySnapshotCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    actor_name = str(current_user.full_name or current_user.username or "").strip() or None
    actor_role = str(current_user.role or "").strip() or None
    return StateHistoryService.create_snapshot(
        db,
        label=payload.label,
        note=payload.note,
        actor_name=actor_name,
        actor_role=actor_role,
    )


@router.get("/compare/{snapshot_id}", response_model=StateHistoryCompareResponse)
def compare_snapshot_to_current(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    _ = current_user
    comparison = StateHistoryService.compare_snapshot_to_current(db, snapshot_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="State snapshot not found")
    return comparison
