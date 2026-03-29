from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class PreventiveCheckTemplate(Base):
    __tablename__ = "preventive_check_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    target_scope = Column(JSON, nullable=False, default=dict)
    checks = Column(JSON, nullable=False, default=list)
    schedule = Column(JSON, nullable=False, default=dict)
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    runs = relationship(
        "PreventiveCheckRun",
        back_populates="template",
        cascade="all, delete-orphan",
    )


class PreventiveCheckRun(Base):
    __tablename__ = "preventive_check_runs"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("preventive_check_templates.id"), nullable=False, index=True)
    status = Column(String, default="queued", nullable=False, index=True)
    execution_mode = Column(String, default="manual", nullable=False)
    triggered_by = Column(String, nullable=True)
    summary = Column(JSON, nullable=False, default=dict)
    findings = Column(JSON, nullable=False, default=list)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    template = relationship("PreventiveCheckTemplate", back_populates="runs")
