from sqlalchemy import Boolean, Column, DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.db.session import Base


class DiscoveryHintTelemetryEvent(Base):
    __tablename__ = "discovery_hint_telemetry_events"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, nullable=False, index=True)
    target_ip = Column(String, nullable=True, index=True)
    mac = Column(String, nullable=True, index=True)
    oui_prefix = Column(String, nullable=True, index=True)
    raw_vendor = Column(String, nullable=True)
    normalized_vendor = Column(String, nullable=True, index=True)

    seed_device_id = Column(Integer, nullable=True, index=True)
    seed_ip = Column(String, nullable=True)
    seed_vendor = Column(String, nullable=True)
    local_interface = Column(String, nullable=True)
    neighbor_name = Column(String, nullable=True)
    neighbor_mgmt_ip = Column(String, nullable=True)

    chosen_driver = Column(String, nullable=True, index=True)
    final_driver = Column(String, nullable=True, index=True)
    success = Column(Boolean, default=False, nullable=False, index=True)
    failure_reason = Column(Text, nullable=True)

    candidate_summary = Column(JSON, nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class DiscoveryHintRule(Base):
    __tablename__ = "discovery_hint_rules"

    id = Column(Integer, primary_key=True, index=True)
    rule_key = Column(String, nullable=False, unique=True, index=True)
    vendor_family = Column(String, nullable=True, index=True)
    match_conditions = Column(JSON, nullable=False)
    driver_overrides = Column(JSON, nullable=False)
    score_bonus = Column(Float, default=0.0, nullable=False)
    evidence_count = Column(Integer, default=0, nullable=False)
    source = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())


class DiscoveryHintVendorAlias(Base):
    __tablename__ = "discovery_hint_vendor_aliases"

    id = Column(Integer, primary_key=True, index=True)
    raw_alias_key = Column(String, nullable=False, unique=True, index=True)
    raw_alias = Column(String, nullable=False)
    vendor_family = Column(String, nullable=False, index=True)
    source = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
