from sqlalchemy import Column, DateTime, Integer, String, Text, Index
from sqlalchemy.sql import func

from app.db.session import Base


class IpIntelCache(Base):
    __tablename__ = "ip_intel_cache"
    __table_args__ = (
        Index("ix_ip_intel_cache_ip", "ip", unique=True),
        Index("ix_ip_intel_cache_provider", "provider_guess"),
        Index("ix_ip_intel_cache_updated", "updated_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, nullable=False)
    provider_guess = Column(String, nullable=True)
    asn = Column(String, nullable=True)
    as_name = Column(String, nullable=True)
    org_name = Column(String, nullable=True)
    source = Column(String, nullable=True)
    raw_json = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

