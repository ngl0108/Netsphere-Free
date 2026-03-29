from sqlalchemy import Column, DateTime, String
from sqlalchemy.sql import func
from app.db.session import Base


class HaLease(Base):
    __tablename__ = "ha_leases"
    __table_args__ = {"extend_existing": True}

    key = Column(String, primary_key=True)
    owner_id = Column(String, nullable=False, index=True)
    acquired_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_renewed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
