from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.sql import func

from app.db.session import Base


class DiscoveryHintCacheEntry(Base):
    __tablename__ = "discovery_hint_cache"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, nullable=False, unique=True, index=True)
    mac_address = Column(String, nullable=True, index=True)

    seed_device_id = Column(Integer, nullable=True, index=True)
    seed_ip = Column(String, nullable=True)
    seed_vendor = Column(String, nullable=True)

    local_interface = Column(String, nullable=True)
    arp_interface = Column(String, nullable=True)
    vlan = Column(String, nullable=True)

    neighbor_name = Column(String, nullable=True)
    neighbor_mgmt_ip = Column(String, nullable=True)
    remote_interface = Column(String, nullable=True)
    protocol = Column(String, nullable=True)
    sources = Column(JSON, nullable=True)

    observed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ttl_expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), nullable=True, onupdate=func.now())
