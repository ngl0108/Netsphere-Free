from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class ServiceGroup(Base):
    __tablename__ = "service_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    criticality = Column(String, default="standard", nullable=False)
    owner_team = Column(String, nullable=True)
    color = Column(String, default="#0ea5e9", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    members = relationship(
        "ServiceGroupMember",
        back_populates="service_group",
        cascade="all, delete-orphan",
    )


class ServiceGroupMember(Base):
    __tablename__ = "service_group_members"

    id = Column(Integer, primary_key=True, index=True)
    service_group_id = Column(Integer, ForeignKey("service_groups.id"), nullable=False, index=True)
    member_type = Column(String, nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True, index=True)
    cloud_resource_id = Column(Integer, ForeignKey("cloud_resources.id"), nullable=True, index=True)
    role_label = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    service_group = relationship("ServiceGroup", back_populates="members")
    device = relationship("Device")
    cloud_resource = relationship("CloudResource")
