from __future__ import annotations

from pydantic import BaseModel, Field


class ApprovalServiceImpactMemberResponse(BaseModel):
    member_type: str
    member_id: int
    display_name: str
    role_label: str | None = None
    match_reason: str | None = None


class ApprovalServiceImpactGroupResponse(BaseModel):
    id: int
    name: str
    criticality: str
    owner_team: str | None = None
    color: str
    matched_member_count: int = 0
    matched_members: list[ApprovalServiceImpactMemberResponse] = Field(default_factory=list)


class ApprovalServiceImpactSummaryResponse(BaseModel):
    count: int = 0
    primary_name: str | None = None
    highest_criticality: str | None = None
    matched_member_count: int = 0


class ApprovalServiceImpactResponse(BaseModel):
    approval_id: int
    summary: ApprovalServiceImpactSummaryResponse
    groups: list[ApprovalServiceImpactGroupResponse] = Field(default_factory=list)
