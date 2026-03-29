from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class OperationActionCreate(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    assignee_name: Optional[str] = None
    note: Optional[str] = None


class OperationActionUpdate(BaseModel):
    status: Optional[str] = None
    assignee_name: Optional[str] = None
    note: Optional[str] = None


class OperationActionResponse(BaseModel):
    id: int
    issue_id: int
    device_id: Optional[int] = None
    source_type: str
    title: str
    summary: Optional[str] = None
    severity: str
    status: str
    assignee_name: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    latest_note: Optional[str] = None
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class OperationActionSummaryResponse(BaseModel):
    total: int = 0
    open: int = 0
    investigating: int = 0
    mitigated: int = 0
    resolved: int = 0
    has_active: bool = False
    latest_status: Optional[str] = None
    latest_action_id: Optional[int] = None
    latest_title: Optional[str] = None
    latest_assignee_name: Optional[str] = None
    latest_note: Optional[str] = None
    latest_updated_at: Optional[datetime] = None
