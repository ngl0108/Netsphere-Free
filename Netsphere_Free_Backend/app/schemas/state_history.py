from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.source_of_truth import (
    SourceOfTruthCoverageBlock,
    SourceOfTruthDistributionBlock,
)


class StateHistorySnapshotCreateRequest(BaseModel):
    label: Optional[str] = None
    note: Optional[str] = None


class StateHistoryMetricBlock(BaseModel):
    devices_total: int = 0
    managed_devices: int = 0
    discovered_only_devices: int = 0
    online_devices: int = 0
    offline_devices: int = 0
    cloud_accounts_total: int = 0
    cloud_resources_total: int = 0
    service_groups_total: int = 0
    high_criticality_groups: int = 0
    monitoring_profile_assignments_total: int = 0
    active_issues_total: int = 0
    critical_issues_total: int = 0
    open_actions_total: int = 0
    investigating_actions_total: int = 0
    mitigated_actions_total: int = 0
    resolved_actions_total: int = 0
    pending_approvals_total: int = 0
    approved_approvals_total: int = 0
    rejected_approvals_total: int = 0
    evidence_ready_approvals_total: int = 0
    asset_changes_7d_total: int = 0


class StateHistoryHighlightItem(BaseModel):
    key: str
    value: Optional[str] = None
    count: Optional[int] = None


class StateHistorySnapshotResponse(BaseModel):
    event_log_id: int = 0
    event_id: str
    source: str
    severity: str = "info"
    generated_at: datetime
    label: Optional[str] = None
    note: Optional[str] = None
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    metrics: StateHistoryMetricBlock
    coverage: SourceOfTruthCoverageBlock
    distributions: SourceOfTruthDistributionBlock
    highlights: list[StateHistoryHighlightItem] = Field(default_factory=list)


class StateHistoryCompareCard(BaseModel):
    key: str
    title: str
    before: str
    current: str
    delta: str
    status: str
    tone: str
    recommendation: Optional[str] = None


class StateHistoryCompareSummary(BaseModel):
    result: str
    changed_cards: int = 0
    improved_cards: int = 0
    review_cards: int = 0
    steady_cards: int = 0


class StateHistoryCompareResponse(BaseModel):
    baseline: StateHistorySnapshotResponse
    current: StateHistorySnapshotResponse
    summary: StateHistoryCompareSummary
    cards: list[StateHistoryCompareCard] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
