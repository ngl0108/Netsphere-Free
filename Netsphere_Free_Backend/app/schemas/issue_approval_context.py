from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class IssueApprovalContextItem(BaseModel):
    id: int
    title: str
    request_type: str
    request_type_label: str
    status: str
    execution_status: Optional[str] = None
    requester_name: Optional[str] = None
    approver_name: Optional[str] = None
    created_at: Optional[datetime] = None
    decided_at: Optional[datetime] = None
    has_evidence: bool = False
    rollback_on_failure: bool = False
    rollback_attempted: bool = False
    rollback_success: bool = False
    post_check_failed: bool = False
    scope_summary: Optional[str] = None
    top_cause: Optional[str] = None


class IssueApprovalContextSummary(BaseModel):
    total: int = 0
    pending: int = 0
    approved: int = 0
    rejected: int = 0
    latest_status: Optional[str] = None
    latest_approval_id: Optional[int] = None
    evidence_ready_count: int = 0
    rollback_tracked_count: int = 0


class IssueApprovalContextResponse(BaseModel):
    issue_id: int
    summary: IssueApprovalContextSummary = Field(default_factory=IssueApprovalContextSummary)
    items: list[IssueApprovalContextItem] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)
    cloud_scope: dict[str, Any] | None = None
