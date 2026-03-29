from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ServiceGroupBase(BaseModel):
    name: str
    description: Optional[str] = None
    criticality: str = "standard"
    owner_team: Optional[str] = None
    color: str = "#0ea5e9"
    is_active: bool = True


class ServiceGroupCreate(ServiceGroupBase):
    pass


class ServiceGroupUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    criticality: Optional[str] = None
    owner_team: Optional[str] = None
    color: Optional[str] = None
    is_active: Optional[bool] = None


class ServiceGroupMemberResponse(BaseModel):
    id: int
    member_type: str
    role_label: Optional[str] = None
    display_name: str
    subtitle: Optional[str] = None
    status: Optional[str] = None
    provider: Optional[str] = None
    region: Optional[str] = None
    resource_type: Optional[str] = None
    state: Optional[str] = None
    device_id: Optional[int] = None
    cloud_resource_id: Optional[int] = None
    resource_id: Optional[str] = None
    created_at: Optional[datetime] = None


class ServiceGroupHealthSummary(BaseModel):
    health_score: int = 100
    health_status: str = "healthy"
    active_issue_count: int = 0
    critical_issue_count: int = 0
    offline_device_count: int = 0
    managed_device_count: int = 0
    discovered_only_device_count: int = 0
    member_device_count: int = 0
    member_cloud_count: int = 0


class ServiceGroupResponse(ServiceGroupBase):
    id: int
    device_count: int = 0
    cloud_resource_count: int = 0
    member_count: int = 0
    health: ServiceGroupHealthSummary = Field(default_factory=ServiceGroupHealthSummary)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ServiceGroupDetailResponse(ServiceGroupResponse):
    members: list[ServiceGroupMemberResponse] = Field(default_factory=list)


class ServiceGroupCatalogDeviceResponse(BaseModel):
    id: int
    name: str
    ip_address: str
    role: Optional[str] = None
    status: Optional[str] = None
    management_state: Optional[str] = None


class ServiceGroupCatalogCloudResourceResponse(BaseModel):
    id: int
    account_id: int
    account_name: str
    provider: str
    resource_id: str
    resource_type: str
    name: Optional[str] = None
    region: Optional[str] = None
    state: Optional[str] = None


class ServiceGroupCatalogResponse(BaseModel):
    devices: list[ServiceGroupCatalogDeviceResponse] = Field(default_factory=list)
    cloud_resources: list[ServiceGroupCatalogCloudResourceResponse] = Field(default_factory=list)


class ServiceGroupMemberCreateResponse(BaseModel):
    service_group: ServiceGroupDetailResponse
