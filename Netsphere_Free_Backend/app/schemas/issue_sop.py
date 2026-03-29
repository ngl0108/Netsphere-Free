from __future__ import annotations

from pydantic import BaseModel, Field


class IssueSopStepResponse(BaseModel):
    id: str
    title: str
    description: str
    source_type: str
    status_hint: str = "recommended"
    action_label: str | None = None
    source_title: str | None = None


class IssueSopSummaryResponse(BaseModel):
    available: bool = False
    readiness_status: str = "limited_context"
    step_count: int = 0
    primary_title: str | None = None
    active_action_count: int = 0
    knowledge_match_count: int = 0


class IssueSopResponse(BaseModel):
    issue_id: int
    readiness_status: str = "limited_context"
    summary: str
    recommended_owner: str | None = None
    reasons: list[str] = Field(default_factory=list)
    steps: list[IssueSopStepResponse] = Field(default_factory=list)
    active_action_count: int = 0
    matched_known_error_count: int = 0
    top_known_error_title: str | None = None

