from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text, Index
from sqlalchemy.sql import func

from app.db.session import Base


class KnownErrorEntry(Base):
    __tablename__ = "known_error_entries"
    __table_args__ = (
        Index("ix_known_error_entries_category_enabled", "category", "is_enabled"),
        Index("ix_known_error_entries_device_type_enabled", "device_type_scope", "is_enabled"),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False, index=True)
    symptom_pattern = Column(Text, nullable=True)
    category = Column(String, nullable=True, index=True)
    severity_hint = Column(String, nullable=True)
    device_type_scope = Column(String, nullable=True, index=True)
    vendor_scope = Column(String, nullable=True, index=True)
    root_cause = Column(Text, nullable=True)
    workaround = Column(Text, nullable=True)
    sop_summary = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_by = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)
    times_matched = Column(Integer, default=0, nullable=False)
    last_matched_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
