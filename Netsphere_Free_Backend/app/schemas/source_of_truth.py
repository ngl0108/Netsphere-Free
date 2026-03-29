from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SourceOfTruthMetricBlock(BaseModel):
    devices_total: int = 0
    managed_devices: int = 0
    discovered_only_devices: int = 0
    online_devices: int = 0
    offline_devices: int = 0
    cloud_accounts_total: int = 0
    cloud_resources_total: int = 0
    service_groups_total: int = 0
    service_group_members_total: int = 0


class SourceOfTruthCoverageBlock(BaseModel):
    devices_with_site: int = 0
    devices_with_hostname: int = 0
    devices_with_serial: int = 0
    devices_with_monitoring_profile: int = 0
    service_groups_with_owner: int = 0
    service_groups_with_devices: int = 0
    service_groups_with_cloud_resources: int = 0
    cloud_resources_mapped_to_services: int = 0


class SourceOfTruthDistributionItem(BaseModel):
    key: str
    count: int


class SourceOfTruthDistributionBlock(BaseModel):
    device_roles: list[SourceOfTruthDistributionItem] = Field(default_factory=list)
    device_types: list[SourceOfTruthDistributionItem] = Field(default_factory=list)
    cloud_providers: list[SourceOfTruthDistributionItem] = Field(default_factory=list)


class SourceOfTruthChangeEventResponse(BaseModel):
    id: int
    asset_kind: str
    asset_key: str
    asset_name: Optional[str] = None
    action: str
    summary: str
    actor_name: Optional[str] = None
    actor_role: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class SourceOfTruthSummaryResponse(BaseModel):
    generated_at: datetime
    metrics: SourceOfTruthMetricBlock
    coverage: SourceOfTruthCoverageBlock
    distributions: SourceOfTruthDistributionBlock
    recent_changes: list[SourceOfTruthChangeEventResponse] = Field(default_factory=list)
