from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class MonitoringProfile(Base):
    __tablename__ = "monitoring_profiles"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(String, nullable=True)
    management_scope = Column(String, default="managed", nullable=False)
    telemetry_mode = Column(String, default="hybrid", nullable=False)
    polling_interval_override = Column(Integer, nullable=True)
    status_interval_override = Column(Integer, nullable=True)
    priority = Column(Integer, default=100, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    match_device_types = Column(JSON, default=list, nullable=False)
    match_roles = Column(JSON, default=list, nullable=False)
    match_vendor_patterns = Column(JSON, default=list, nullable=False)
    match_model_patterns = Column(JSON, default=list, nullable=False)
    match_site_ids = Column(JSON, default=list, nullable=False)
    dashboard_tags = Column(JSON, default=list, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    assignments = relationship(
        "MonitoringProfileAssignment",
        back_populates="profile",
        cascade="all, delete-orphan",
    )


class MonitoringProfileAssignment(Base):
    __tablename__ = "monitoring_profile_assignments"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, unique=True, index=True)
    profile_id = Column(Integer, ForeignKey("monitoring_profiles.id"), nullable=False, index=True)
    assignment_source = Column(String, default="auto", nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    recommendation_reasons = Column(JSON, default=list, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    device = relationship("Device")
    profile = relationship("MonitoringProfile", back_populates="assignments")
