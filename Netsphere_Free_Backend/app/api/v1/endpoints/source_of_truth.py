from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.schemas.source_of_truth import SourceOfTruthSummaryResponse
from app.services.source_of_truth_service import SourceOfTruthService

router = APIRouter()


@router.get("/summary", response_model=SourceOfTruthSummaryResponse)
def get_source_of_truth_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    _ = current_user
    return SourceOfTruthService.build_summary(db)
