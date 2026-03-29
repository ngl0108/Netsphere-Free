from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db.session import Base


class PreviewCollectorRegistration(Base):
    __tablename__ = "preview_collector_registrations"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    collector_id = Column(String, unique=True, index=True, nullable=False)
    label = Column(String, nullable=False)
    issued_to = Column(String, nullable=True)
    notes = Column(String, nullable=True)
    token_hash = Column(String, nullable=False)
    token_hint = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
