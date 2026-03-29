from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, JSON, Float, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base
from app.db.encrypted_types import EncryptedString

class DiscoveryJob(Base):
    """
    네트워크 스캔 작업 (Discovery Job)
    """
    __tablename__ = "discovery_jobs"

    id = Column(Integer, primary_key=True, index=True)
    cidr = Column(String, nullable=False)  # Example: "192.168.1.0/24"
    status = Column(String, default="pending")  # pending, running, completed, failed
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True)
    snmp_profile_id = Column(Integer, ForeignKey("snmp_credential_profiles.id"), nullable=True)
    snmp_community = Column(EncryptedString, nullable=True)
    snmp_version = Column(String, default="v2c", nullable=False)
    snmp_port = Column(Integer, default=161, nullable=False)
    snmp_v3_username = Column(String, nullable=True)
    snmp_v3_security_level = Column(String, nullable=True)
    snmp_v3_auth_proto = Column(String, nullable=True)
    snmp_v3_auth_key = Column(EncryptedString, nullable=True)
    snmp_v3_priv_proto = Column(String, nullable=True)
    snmp_v3_priv_key = Column(EncryptedString, nullable=True)
    
    total_ips = Column(Integer, default=0)
    scanned_ips = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    logs = Column(Text, default="")  # 실시간 로그 저장 (매우 간단한 형태) or JSON
    
    results = relationship("DiscoveredDevice", back_populates="job", cascade="all, delete-orphan")


class DiscoveredDevice(Base):
    """
    스캔으로 발견된 장비 (임시 저장소)
    """
    __tablename__ = "discovered_devices"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("discovery_jobs.id"))
    
    ip_address = Column(String, nullable=False)
    hostname = Column(String, nullable=True) # DNS or SNMP sysName
    mac_address = Column(String, nullable=True)
    vendor = Column(String, nullable=True)   # Cisco, Juniper, etc.
    model = Column(String, nullable=True)
    os_version = Column(String, nullable=True)
    
    snmp_status = Column(String, default="unknown") # reachable, unreachable
    device_type = Column(String, default="unknown") # switch, router, firewall, etc.
    sys_object_id = Column(String, nullable=True)
    sys_descr = Column(Text, nullable=True)
    vendor_confidence = Column(Float, default=0.0)
    chassis_candidate = Column(Boolean, default=False)
    issues = Column(JSON, nullable=True)
    evidence = Column(JSON, nullable=True)

    # 이미 인벤토리에 있는지 여부 (매칭되는 Device ID)
    matched_device_id = Column(Integer, nullable=True) 
    status = Column(String, default="new") # new, existing, approved, ignored

    job = relationship("DiscoveryJob", back_populates="results")
