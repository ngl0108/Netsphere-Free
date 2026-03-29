from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class KnownErrorCreate(BaseModel):
    title: Optional[str] = None
    symptom_pattern: Optional[str] = None
    category: Optional[str] = None
    severity_hint: Optional[str] = None
    device_type_scope: Optional[str] = None
    vendor_scope: Optional[str] = None
    root_cause: Optional[str] = None
    workaround: Optional[str] = None
    sop_summary: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    is_enabled: bool = True


class KnownErrorUpdate(BaseModel):
    title: Optional[str] = None
    symptom_pattern: Optional[str] = None
    category: Optional[str] = None
    severity_hint: Optional[str] = None
    device_type_scope: Optional[str] = None
    vendor_scope: Optional[str] = None
    root_cause: Optional[str] = None
    workaround: Optional[str] = None
    sop_summary: Optional[str] = None
    tags: Optional[list[str]] = None
    is_enabled: Optional[bool] = None


class KnownErrorResponse(BaseModel):
    id: int
    title: str
    symptom_pattern: Optional[str] = None
    category: Optional[str] = None
    severity_hint: Optional[str] = None
    device_type_scope: Optional[str] = None
    vendor_scope: Optional[str] = None
    root_cause: Optional[str] = None
    workaround: Optional[str] = None
    sop_summary: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    is_enabled: bool = True
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    times_matched: int = 0
    last_matched_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class KnownErrorRecommendationResponse(KnownErrorResponse):
    match_score: float = 0.0
    match_reasons: list[str] = Field(default_factory=list)


class KnownErrorSummaryResponse(BaseModel):
    recommendation_count: int = 0
    top_title: Optional[str] = None
