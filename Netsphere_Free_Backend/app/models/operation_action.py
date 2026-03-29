from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class OperationAction(Base):
    __tablename__ = "operation_actions"
    __table_args__ = (
        Index("ix_operation_actions_issue_status", "issue_id", "status"),
        Index("ix_operation_actions_status_updated", "status", "updated_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    issue_id = Column(Integer, ForeignKey("issues.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True, index=True)
    source_type = Column(String, default="issue", nullable=False)
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    severity = Column(String, default="warning", nullable=False)
    status = Column(String, default="open", nullable=False)
    assignee_name = Column(String, nullable=True)
    created_by = Column(String, nullable=True)
    updated_by = Column(String, nullable=True)
    latest_note = Column(Text, nullable=True)
    timeline = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    issue = relationship("Issue", back_populates="actions")
    device = relationship("Device", back_populates="operation_actions")
