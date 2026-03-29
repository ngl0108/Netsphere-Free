from __future__ import annotations

from pydantic import BaseModel, Field


class IssueServiceImpactMemberResponse(BaseModel):
    member_type: str
    member_id: int
    display_name: str
    role_label: str | None = None


class IssueServiceImpactGroupResponse(BaseModel):
    id: int
    name: str
    criticality: str
    owner_team: str | None = None
    color: str
    health_score: int = 100
    health_status: str = "healthy"
    active_issue_count: int = 0
    offline_device_count: int = 0
    discovered_only_device_count: int = 0
    matched_member_count: int = 0
    matched_members: list[IssueServiceImpactMemberResponse] = Field(default_factory=list)


class IssueServiceImpactSummaryResponse(BaseModel):
    count: int = 0
    primary_name: str | None = None
    highest_criticality: str | None = None
    matched_member_count: int = 0
    primary_health_score: int | None = None
    primary_health_status: str | None = None
    review_group_count: int = 0
    critical_group_count: int = 0


class IssueServiceImpactResponse(BaseModel):
    issue_id: int
    groups: list[IssueServiceImpactGroupResponse] = Field(default_factory=list)
