from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MonitoringProfileBase(BaseModel):
    key: str
    name: str
    description: Optional[str] = None
    management_scope: str = "managed"
    telemetry_mode: str = "hybrid"
    polling_interval_override: Optional[int] = None
    status_interval_override: Optional[int] = None
    priority: int = 100
    is_active: bool = True
    match_device_types: List[str] = Field(default_factory=list)
    match_roles: List[str] = Field(default_factory=list)
    match_vendor_patterns: List[str] = Field(default_factory=list)
    match_model_patterns: List[str] = Field(default_factory=list)
    match_site_ids: List[int] = Field(default_factory=list)
    dashboard_tags: List[str] = Field(default_factory=list)


class MonitoringProfileCreate(MonitoringProfileBase):
    pass


class MonitoringProfileUpdate(BaseModel):
    key: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    management_scope: Optional[str] = None
    telemetry_mode: Optional[str] = None
    polling_interval_override: Optional[int] = None
    status_interval_override: Optional[int] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    match_device_types: Optional[List[str]] = None
    match_roles: Optional[List[str]] = None
    match_vendor_patterns: Optional[List[str]] = None
    match_model_patterns: Optional[List[str]] = None
    match_site_ids: Optional[List[int]] = None
    dashboard_tags: Optional[List[str]] = None


class MonitoringProfileResponse(MonitoringProfileBase):
    id: int
    assigned_devices: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MonitoringProfileAssignmentRequest(BaseModel):
    profile_id: int


class MonitoringProfileDeviceSummary(BaseModel):
    profile_id: int
    key: str
    name: str
    assignment_source: str
    confidence: float
    management_scope: str
    telemetry_mode: str
    polling_interval_override: Optional[int] = None
    status_interval_override: Optional[int] = None
    dashboard_tags: List[str] = Field(default_factory=list)
    recommendation_reasons: List[str] = Field(default_factory=list)
    activation_state: str = "active"
    policy_summary: Dict[str, Any] = Field(default_factory=dict)


class MonitoringProfileRecommendationResponse(BaseModel):
    device_id: int
    recommendation: Optional[MonitoringProfileDeviceSummary] = None


class MonitoringProfileCatalogResponse(BaseModel):
    profiles: List[MonitoringProfileResponse] = Field(default_factory=list)
    coverage: Dict[str, Any] = Field(default_factory=dict)
