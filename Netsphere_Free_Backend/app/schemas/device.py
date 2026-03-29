from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime

# [FIX] Late import to register User model with SQLAlchemy mapper
# This avoids circular import while ensuring relationship resolution
from app.models.user import User


# ================================================================
# SWIM Schemas
# ================================================================
class ImageDeployRequest(BaseModel):
    device_ids: List[int]

class UpgradeJobResponse(BaseModel):
    id: int
    device_id: int
    image_id: int
    status: str
    progress_percent: int
    current_stage: str
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# 1. 공통 스키마
# --------------------------------------------------------------------------
class SiteResponse(BaseModel):
    id: int
    name: str
    type: str
    parent_id: Optional[int]
    latitude: Optional[float]
    longitude: Optional[float]
    address: Optional[str]
    # 사이트 변수 (JSON)
    variables: Optional[Dict[str, Any]] = None
    snmp_profile_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class SiteCreate(BaseModel):
    name: str
    type: str = "Building"
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class SiteUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    snmp_profile_id: Optional[int] = None


# --------------------------------------------------------------------------
# 2. 기타 스키마 (펌웨어, 정책 등)
# --------------------------------------------------------------------------
class FirmwareImageResponse(BaseModel):
    id: int
    version: str
    filename: str
    device_family: str
    is_golden: bool
    size_bytes: int
    release_date: Optional[datetime]
    supported_models: Optional[List[str]]

    model_config = ConfigDict(from_attributes=True)


class PolicyRuleResponse(BaseModel):
    id: int
    priority: int
    action: str
    match_conditions: Dict[str, Any]
    action_params: Optional[Dict[str, Any]]

    model_config = ConfigDict(from_attributes=True)


class PolicyRuleCreate(BaseModel):
    priority: int
    action: str
    match_conditions: Dict[str, Any]
    action_params: Optional[Dict[str, Any]] = None


class PolicyResponse(BaseModel):
    id: int
    name: str
    type: str
    description: Optional[str]
    auto_remediate: bool # [NEW]
    rules: List[PolicyRuleResponse] = []

    model_config = ConfigDict(from_attributes=True)


# [NEW] 정책 업데이트 스키마 추가
class PolicyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    auto_remediate: Optional[bool] = None # [NEW]
    rules: Optional[List[PolicyRuleCreate]] = None

class PolicyCreate(BaseModel):
    name: str
    type: str = "QoS"
    description: str = None
    auto_remediate: bool = False # [NEW]
    site_id: int = None
    rules: List[PolicyRuleCreate] = []


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    full_name: Optional[str]
    role: str
    is_active: bool
    last_login: Optional[datetime]
    mfa_enabled: Optional[bool] = None
    email_verified: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class TaskResponse(BaseModel):
    id: str
    name: str
    status: str
    progress: int
    started_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SiteVlanCreate(BaseModel):
    vlan_id: int
    name: str
    subnet: Optional[str] = None
    description: Optional[str] = None


class SiteVlanResponse(SiteVlanCreate):
    id: int
    site_id: int

    model_config = ConfigDict(from_attributes=True)


class ComplianceCheckRequest(BaseModel):
    device_id: int
    template_content: str


class ComplianceReportResponse(BaseModel):
    id: int
    device_id: int
    status: str
    match_percentage: float
    standard_id: Optional[int]
    diff_content: Optional[str]
    last_checked: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


class UserLogin(BaseModel):
    username: str
    password: str


# --------------------------------------------------------------------------
# 3. 대시보드 통계 스키마
# --------------------------------------------------------------------------
class DashboardStats(BaseModel):
    counts: Dict[str, Any]
    health_score: int
    trafficTrend: List[Dict[str, Any]]
    issues: List[Dict[str, Any]] = []

    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------
# 4. 장비 (Device) 및 설정 관련 스키마
# --------------------------------------------------------------------------
class ConfigTemplateBase(BaseModel):
    name: str
    category: str = "Switching"
    content: str
    tags: Optional[str] = "DRAFT"


class ConfigTemplateCreate(ConfigTemplateBase): pass


class ConfigTemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[str] = None


class ConfigTemplateResponse(ConfigTemplateBase):
    id: int
    version: str = "1.0"
    last_updated: datetime = datetime.now()
    author: str = "admin"

    model_config = ConfigDict(from_attributes=True)


class VariableUpdate(BaseModel): variables: dict


class VariableResponse(BaseModel): target_id: int; target_type: str; variables: dict


class DeviceBase(BaseModel):
    name: str = Field(..., description="Hostname")
    ip_address: str = Field(..., description="IP")
    device_type: Optional[str] = "cisco_ios"
    site_id: Optional[int] = None
    snmp_community: str = "public"
    snmp_version: str = "v2c"
    snmp_port: int = 161
    snmp_v3_username: Optional[str] = None
    snmp_v3_security_level: Optional[str] = None
    snmp_v3_auth_proto: Optional[str] = None
    snmp_v3_auth_key: Optional[str] = None
    snmp_v3_priv_proto: Optional[str] = None
    snmp_v3_priv_key: Optional[str] = None
    ssh_username: Optional[str] = "admin"
    ssh_password: Optional[str] = None
    ssh_port: Optional[int] = 22
    enable_password: Optional[str] = None
    polling_interval: int = 60
    status_interval: int = 60


class DeviceCreate(DeviceBase):
    auto_provision_template_id: Optional[int] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    device_type: Optional[str] = None  # [FIX] Allow device type editing
    site_id: Optional[int] = None
    location: Optional[str] = None
    snmp_community: Optional[str] = None
    snmp_version: Optional[str] = None
    snmp_port: Optional[int] = None
    snmp_v3_username: Optional[str] = None
    snmp_v3_security_level: Optional[str] = None
    snmp_v3_auth_proto: Optional[str] = None
    snmp_v3_auth_key: Optional[str] = None
    snmp_v3_priv_proto: Optional[str] = None
    snmp_v3_priv_key: Optional[str] = None
    enable_password: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_password: Optional[str] = None
    ssh_port: Optional[int] = None
    polling_interval: Optional[int] = None
    status_interval: Optional[int] = None


class InterfaceResponse(BaseModel):
    id: int
    name: str
    status: str
    admin_status: Optional[str]
    vlan: Optional[int]
    mode: Optional[str]
    is_poe: bool = False
    mac_address: Optional[str] = None
    description: Optional[str] = None
    ip_address: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class VlanResponse(BaseModel):
    vlan_id: int
    vlan_name: str
    ip_address: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class LinkResponse(BaseModel):
    id: int
    target_device_id: Optional[int]
    source_interface_name: Optional[str]
    target_interface_name: Optional[str]
    status: str
    link_speed: str

    model_config = ConfigDict(from_attributes=True)


# [수정] 메트릭 데이터에 Null 허용 (Optional + Default Value)
class MetricResponse(BaseModel):
    cpu_usage: float
    memory_usage: float
    temperature: Optional[float] = 0.0  # 수정: 값이 없으면 0.0 처리
    traffic_in: Optional[float] = 0.0   # 수정: 값이 없으면 0.0 처리
    traffic_out: Optional[float] = 0.0  # 수정: 값이 없으면 0.0 처리
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)


# [수정] 로그 데이터에 Null 허용
class LogResponse(BaseModel):
    id: int
    device_id: Optional[int] = None
    device: Optional[str] = None  # [NEW] Device name for frontend display
    severity: str
    event_id: Optional[str] = "SYSLOG"  # 수정: 값이 없으면 기본값
    message: str
    source: str
    timestamp: datetime

    # [NEW] Device 객체가 들어오면 자동으로 name 추출
    @field_validator('device', mode='before')
    @classmethod
    def extract_device_name(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            return v
        # Device 객체인 경우 name 속성 추출
        if hasattr(v, 'name'):
            return v.name
        return str(v)

    model_config = ConfigDict(from_attributes=True)


class IssueResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    severity: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ConfigBackupResponse(BaseModel):
    id: int
    raw_config: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DeviceResponse(BaseModel):
    id: int
    name: str
    hostname: Optional[str] = None
    ip_address: str
    device_type: str
    model: Optional[str] = "Unknown"
    serial_number: Optional[str] = None
    os_version: Optional[str] = None
    location: Optional[str]
    site_id: Optional[int]
    status: str
    reachability_status: Optional[str]
    uptime: Optional[str]
    snmp_community: Optional[str]
    snmp_version: Optional[str] = None
    snmp_port: Optional[int] = None
    snmp_v3_username: Optional[str] = None
    snmp_v3_security_level: Optional[str] = None
    snmp_v3_auth_proto: Optional[str] = None
    snmp_v3_priv_proto: Optional[str] = None
    ssh_username: Optional[str]
    ssh_port: Optional[int]
    polling_interval: Optional[int]
    status_interval: Optional[int]
    variables: Optional[Dict[str, Any]] = None  # 장비 변수 추가
    management_state: Optional[str] = "managed"
    management_reason: Optional[str] = None
    managed_since: Optional[datetime] = None
    management_priority_score: Optional[float] = 0.0
    is_managed: bool = True
    monitoring_profile: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class DeviceDetailResponse(DeviceResponse):
    latest_parsed_data: Optional[Dict[str, Any]] = None
    interfaces: List[InterfaceResponse] = []
    vlans: List[VlanResponse] = []
    metrics: List[MetricResponse] = []
    logs: List[LogResponse] = []
    config_backups: List[ConfigBackupResponse] = []
    source_links: List[LinkResponse] = []
    issues: List[IssueResponse] = []

    model_config = ConfigDict(from_attributes=True)
