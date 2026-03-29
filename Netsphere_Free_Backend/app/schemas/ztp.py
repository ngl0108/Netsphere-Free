from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from enum import Enum


class ZtpStatusEnum(str, Enum):
    NEW = "new"
    READY = "ready"
    PROVISIONING = "provisioning"
    COMPLETED = "completed"
    ERROR = "error"


# ====================================================================
# Request Schemas
# ====================================================================
class ZtpApproveRequest(BaseModel):
    """관리자가 ZTP Queue 항목을 승인할 때 보내는 데이터"""
    site_id: Optional[int] = Field(None, description="할당할 사이트 ID")
    template_id: Optional[int] = Field(None, description="적용할 설정 템플릿 ID")
    target_hostname: Optional[str] = Field(None, description="개통 후 호스트네임")
    
    # [RMA] 교체 대상 장비 ID (이 값이 있으면 위 정보들을 해당 장비에서 가져옴)
    swap_with_device_id: Optional[int] = Field(None, description="교체할 기존 장비 ID (RMA)")


class ZtpRegisterRequest(BaseModel):
    """장비가 ZTP 서버에 자동 등록할 때 전송하는 데이터"""
    serial_number: str = Field(..., description="장비 시리얼 번호")
    model: Optional[str] = Field(None, description="장비 모델명")
    ip_address: Optional[str] = Field(None, description="장비 IP 주소")
    uplink_info: Optional[dict] = Field(None, description="업링크 정보 (CDP/LLDP)")



class ZtpStageRequest(BaseModel):
    """수동으로 장비를 ZTP Queue에 미리 등록 (RMA 등)"""
    serial_number: str = Field(..., description="장비 시리얼 번호")
    site_id: int
    template_id: int
    target_hostname: str


# ====================================================================
# Response Schemas
# ====================================================================
class ZtpQueueResponse(BaseModel):
    id: int
    serial_number: str
    platform: Optional[str] = None
    software_version: Optional[str] = None
    ip_address: Optional[str] = None
    hostname: Optional[str] = None
    status: ZtpStatusEnum
    device_type: Optional[str] = "cisco_ios"  # [NEW] Multi-vendor support
    
    assigned_site_id: Optional[int] = None
    assigned_site_name: Optional[str] = None
    assigned_template_id: Optional[int] = None
    assigned_template_name: Optional[str] = None
    target_hostname: Optional[str] = None
    
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    provisioned_at: Optional[datetime] = None
    last_message: Optional[str] = None

    # [RMA Logic] Suggestion
    detected_uplink_name: Optional[str] = None
    detected_uplink_port: Optional[str] = None
    suggested_device_id: Optional[int] = None
    suggestion_reason: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ZtpStatsResponse(BaseModel):
    """ZTP 대시보드 통계"""
    total_queued: int
    pending_approval: int  # status == 'new'
    ready_to_provision: int  # status == 'ready'
    in_progress: int  # status == 'provisioning'
    completed_today: int
    errors: int
