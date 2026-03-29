from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.db.session import Base


class AssetChangeEvent(Base):
    __tablename__ = "asset_change_events"

    id = Column(Integer, primary_key=True, index=True)
    asset_kind = Column(String, nullable=False, index=True)
    asset_key = Column(String, nullable=False, index=True)
    asset_name = Column(String, nullable=True)
    action = Column(String, nullable=False, index=True)
    summary = Column(Text, nullable=False)
    actor_name = Column(String, nullable=True)
    actor_role = Column(String, nullable=True)
    details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
