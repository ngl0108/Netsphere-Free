from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Enum as SqlEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base
import enum


class ZtpStatus(str, enum.Enum):
    """ZTP Queue Status"""
    NEW = "new"                 # 새로 발견됨, 사용자 승인 대기
    READY = "ready"             # 템플릿 할당 완료, 장비 재연결 대기
    PROVISIONING = "provisioning"  # 설정 전송 중
    COMPLETED = "completed"     # 프로비저닝 완료
    ERROR = "error"             # 오류 발생


class ZtpQueue(Base):
    """
    ZTP Staging Queue: 아직 완전히 개통되지 않은 장비들의 대기열.
    다양한 벤더의 장비를 지원합니다 (Cisco PnP, Juniper ZTP 등).
    """
    __tablename__ = "ztp_queue"

    id = Column(Integer, primary_key=True, index=True)
    serial_number = Column(String, unique=True, index=True, nullable=False)
    platform = Column(String, nullable=True)  # e.g., C9300-24P, EX4300, DCS-7050
    software_version = Column(String, nullable=True)
    ip_address = Column(String, nullable=True)  # ZTP 요청 시 Source IP
    hostname = Column(String, nullable=True)  # 장비가 보내온 hostname (초기값)

    status = Column(String, default=ZtpStatus.NEW.value)
    
    # [NEW] 벤더/장비 타입 (multi-vendor support)
    device_type = Column(String, default="cisco_ios")  # cisco_ios, juniper_junos, arista_eos

    # 관리자가 승인 시 할당하는 정보
    assigned_site_id = Column(Integer, ForeignKey("sites.id"), nullable=True)
    assigned_template_id = Column(Integer, ForeignKey("config_templates.id"), nullable=True)
    target_hostname = Column(String, nullable=True)  # 개통 후 적용할 호스트네임

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    provisioned_at = Column(DateTime(timezone=True), nullable=True)

    # [RMA Logic] Uplink Detection & Suggestion
    detected_uplink_name = Column(String, nullable=True)  # 감지된 상단 장비명 (LLDP/CDP)
    detected_uplink_port = Column(String, nullable=True)  # 감지된 상단 포트
    detected_uplink_ip = Column(String, nullable=True)    # 감지된 상단 IP

    suggested_device_id = Column(Integer, ForeignKey("devices.id"), nullable=True) # 추천 교체 대상 (구 장비)
    suggestion_reason = Column(String, nullable=True)     # 추천 사유 (e.g. "Matched Location")
    # Relationships
    assigned_site = relationship("Site")
    assigned_template = relationship("ConfigTemplate")

    # 프로비저닝 결과 로그 (디버깅용)
    last_message = Column(Text, nullable=True)

