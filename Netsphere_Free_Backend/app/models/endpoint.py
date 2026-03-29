from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class Endpoint(Base):
    __tablename__ = "endpoints"

    id = Column(Integer, primary_key=True, index=True)
    mac_address = Column(String, nullable=False, unique=True, index=True)
    ip_address = Column(String, nullable=True, index=True)
    hostname = Column(String, nullable=True)
    vendor = Column(String, nullable=True)
    endpoint_type = Column(String, nullable=True)  # pc, ap, phone, printer, unknown

    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())

    attachments = relationship("EndpointAttachment", back_populates="endpoint", cascade="all, delete-orphan")


class EndpointAttachment(Base):
    __tablename__ = "endpoint_attachments"

    id = Column(Integer, primary_key=True, index=True)
    endpoint_id = Column(Integer, ForeignKey("endpoints.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    interface_name = Column(String, nullable=False, index=True)
    vlan = Column(String, nullable=True)

    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())

    endpoint = relationship("Endpoint", back_populates="attachments")
