from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text, Boolean, JSON, Index
from sqlalchemy.orm import relationship, backref
from sqlalchemy.sql import func
from app.db.session import Base
from app.db.encrypted_types import EncryptedString


# 1. 사이트 (Site)
class Site(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    type = Column(String, default="area")
    parent_id = Column(Integer, ForeignKey('sites.id'), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    address = Column(String, nullable=True)
    timezone = Column(String, default="Asia/Seoul")
    snmp_profile_id = Column(Integer, ForeignKey("snmp_credential_profiles.id"), nullable=True)

    # [설정 자동화] 사이트 공통 변수
    variables = Column(JSON, default={}, nullable=True)

    children = relationship("Site", backref=backref('parent', remote_side=[id]))
    devices = relationship("Device", back_populates="site_obj")
    policies = relationship("Policy", back_populates="site")
    vlans = relationship("SiteVlan", back_populates="site", cascade="all, delete-orphan")


# 2. 펌웨어 이미지
class FirmwareImage(Base):
    __tablename__ = "firmware_images"
    id = Column(Integer, primary_key=True, index=True)
    version = Column(String, nullable=False)
    filename = Column(String, nullable=False)
    device_family = Column(String, nullable=False)
    md5_checksum = Column(String, nullable=True)
    size_bytes = Column(Integer, default=0)
    release_date = Column(DateTime, nullable=True)
    is_golden = Column(Boolean, default=False)
    supported_models = Column(JSON, nullable=True)


# 3. 정책 (Policy)
class Policy(Base):
    __tablename__ = "policies"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    type = Column(String, default="QoS")
    description = Column(String, nullable=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True)
    site = relationship("Site", back_populates="policies")
    rules = relationship("PolicyRule", back_populates="policy", cascade="all, delete-orphan")
    auto_remediate = Column(Boolean, default=False) # [NEW] Auto-Remediation Flag
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PolicyRule(Base):
    __tablename__ = "policy_rules"
    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(Integer, ForeignKey("policies.id"))
    priority = Column(Integer, default=100)
    action = Column(String, default="permit")
    match_conditions = Column(JSON, nullable=False)
    action_params = Column(JSON, nullable=True)
    policy = relationship("Policy", back_populates="rules")


# User model is defined in app/models/user.py


# --- 장비 모델 (Device) ---
class Device(Base):
    __tablename__ = "devices"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    hostname = Column(String, index=True, nullable=True) # Actual hostname from device
    ip_address = Column(String, nullable=False)
    mac_address = Column(String, nullable=True)
    snmp_community = Column(EncryptedString, default="public", nullable=False)
    snmp_version = Column(String, default="v2c", nullable=False)
    snmp_port = Column(Integer, default=161, nullable=False)
    snmp_v3_username = Column(String, nullable=True)
    snmp_v3_security_level = Column(String, nullable=True)
    snmp_v3_auth_proto = Column(String, nullable=True)
    snmp_v3_auth_key = Column(EncryptedString, nullable=True)
    snmp_v3_priv_proto = Column(String, nullable=True)
    snmp_v3_priv_key = Column(EncryptedString, nullable=True)
    ssh_username = Column(String, nullable=True, default="admin")
    ssh_password = Column(EncryptedString, nullable=True)
    ssh_port = Column(Integer, default=22)
    enable_password = Column(EncryptedString, nullable=True)
    polling_interval = Column(Integer, default=60, nullable=False)
    status_interval = Column(Integer, default=60, nullable=False)
    model = Column(String, default="Unknown")
    os_version = Column(String, default="Unknown")
    serial_number = Column(String, nullable=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=True, index=True)
    location = Column(String, nullable=True)
    device_type = Column(String, default="cisco_ios")
    
    # [NEW] gNMI Telemetry
    gnmi_port = Column(Integer, default=57400)
    telemetry_mode = Column(String, default="hybrid") # hybrid, gnmi, snmp

    role = Column(String, default="access")
    status = Column(String, default="offline")
    reachability_status = Column(String, default="unreachable")
    uptime = Column(String, default="0d 0h 0m")
    last_seen = Column(DateTime(timezone=True), nullable=True)
    management_state = Column(String, default="managed", nullable=False, index=True)
    management_reason = Column(String, nullable=True)
    managed_since = Column(DateTime(timezone=True), nullable=True)
    management_priority_score = Column(Float, default=0.0, nullable=False)

    # [설정 자동화] 장비 전용 변수
    variables = Column(JSON, default={}, nullable=True)
    latest_parsed_data = Column(JSON, nullable=True)

    owner_id = Column(Integer, ForeignKey("users.id"), index=True)
    owner = relationship("User", back_populates="devices")

    # [SaaS] Tenant
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    tenant = relationship("Tenant", back_populates="devices")

    # Relationships
    site_obj = relationship("Site", back_populates="devices")
    interfaces = relationship("Interface", back_populates="device", cascade="all, delete-orphan")
    metrics = relationship("SystemMetric", back_populates="device", cascade="all, delete-orphan")
    logs = relationship("EventLog", back_populates="device", cascade="all, delete-orphan")
    vlans = relationship("DeviceVlan", back_populates="device", cascade="all, delete-orphan")

    # Config & Links
    config_backups = relationship("ConfigBackup", back_populates="device", cascade="all, delete-orphan")
    source_links = relationship("Link", foreign_keys="[Link.source_device_id]", back_populates="source_device",
                                cascade="all, delete-orphan")
    target_links = relationship("Link", foreign_keys="[Link.target_device_id]", back_populates="target_device",
                                cascade="all, delete-orphan")

    issues = relationship("Issue", back_populates="device", cascade="all, delete-orphan")
    operation_actions = relationship("OperationAction", back_populates="device", cascade="all, delete-orphan")
    compliance_report = relationship("ComplianceReport", uselist=False, back_populates="device",
                                     cascade="all, delete-orphan")


# --- 하위 모델들 ---
class Interface(Base):
    __tablename__ = "interfaces"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(String, default="down")
    admin_status = Column(String, default="up")
    vlan = Column(Integer, default=1)
    mode = Column(String, default="access")
    ip_address = Column(String, nullable=True)
    device = relationship("Device", back_populates="interfaces")


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (Index("ix_links_source_target", "source_device_id", "target_device_id"),)
    id = Column(Integer, primary_key=True, index=True)
    source_device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    target_device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    source_interface_name = Column(String)
    target_interface_name = Column(String)
    status = Column(String, default="active")
    link_speed = Column(String, default="10G")
    protocol = Column(String, default="UNKNOWN")
    confidence = Column(Float, default=0.5)
    discovery_source = Column(String, default="ssh_neighbors")
    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    source_device = relationship("Device", foreign_keys=[source_device_id], back_populates="source_links")
    target_device = relationship("Device", foreign_keys=[target_device_id], back_populates="target_links")


class DeviceVlan(Base):
    __tablename__ = "device_vlans"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    vlan_id = Column(Integer, nullable=False)
    vlan_name = Column(String, nullable=False)
    ip_address = Column(String, nullable=True)
    device = relationship("Device", back_populates="vlans")


class SystemMetric(Base):
    __tablename__ = "system_metrics"
    __table_args__ = (Index("ix_system_metrics_device_ts", "device_id", "timestamp"),)
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    cpu_usage = Column(Float, default=0.0)
    memory_usage = Column(Float, default=0.0)
    traffic_in = Column(Float, default=0.0)
    traffic_out = Column(Float, default=0.0)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    device = relationship("Device", back_populates="metrics")


class InterfaceMetric(Base):
    __tablename__ = "interface_metrics"
    __table_args__ = (
        Index("ix_interface_metrics_device_ts", "device_id", "timestamp"),
        Index("ix_interface_metrics_device_if_ts", "device_id", "interface_name", "timestamp"),
    )
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    interface_name = Column(String, nullable=False, index=True)

    traffic_in_bps = Column(Float, default=0.0)
    traffic_out_bps = Column(Float, default=0.0)
    in_errors_per_sec = Column(Float, default=0.0)
    out_errors_per_sec = Column(Float, default=0.0)
    in_discards_per_sec = Column(Float, default=0.0)
    out_discards_per_sec = Column(Float, default=0.0)

    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    device = relationship("Device")


class EventLog(Base):
    __tablename__ = "event_logs"
    __table_args__ = (Index("ix_event_logs_device_ts", "device_id", "timestamp"),)
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    severity = Column(String, default="info")
    event_id = Column(String, nullable=True)  # [NEW] Added for Syslog parsing
    message = Column(Text, nullable=False)
    source = Column(String, default="System")
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    device = relationship("Device", back_populates="logs")


class Issue(Base):
    __tablename__ = "issues"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    severity = Column(String, default="info")  # critical, warning, info
    status = Column(String, default="active")  # active, resolved
    category = Column(String, default="system")  # device, security, system, config, performance
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    device = relationship("Device", back_populates="issues")
    actions = relationship("OperationAction", back_populates="issue", cascade="all, delete-orphan")


class SiteVlan(Base):
    __tablename__ = "site_vlans"
    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False, index=True)
    vlan_id = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    subnet = Column(String, nullable=True)
    description = Column(String, nullable=True)
    site = relationship("Site", back_populates="vlans")


# --- [자동화 핵심 모델] ---

class ConfigTemplate(Base):
    __tablename__ = "config_templates"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    category = Column(String, default="Switching")
    content = Column(Text, nullable=False)
    version = Column(String, default="1.0")
    last_updated = Column(DateTime(timezone=True), server_default=func.now())
    author = Column(String, default="Admin")
    tags = Column(String, nullable=True)


class ConfigBackup(Base):
    __tablename__ = "config_backups"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    raw_config = Column(Text, nullable=True)
    is_golden = Column(Boolean, default=False)  # [NEW] Golden Config Flag
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    device = relationship("Device", back_populates="config_backups")


class ComplianceReport(Base):
    __tablename__ = "compliance_reports"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    status = Column(String, default="compliant")  # compliant, violation
    match_percentage = Column(Float, default=100.0)
    diff_content = Column(Text, nullable=True)  # HTML diff code or simplified text
    details = Column(JSON, nullable=True) # Detailed rule violation data
    last_checked = Column(DateTime(timezone=True), server_default=func.now())
    device = relationship("Device", back_populates="compliance_report")

# [FIX] Late import to register User model with SQLAlchemy mapper
# This avoids circular import while ensuring relationship resolution
from app.models.user import User
from app.models import operation_action as _operation_action
