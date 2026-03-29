from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, Text, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class VisualBlueprint(Base):
    __tablename__ = "visual_blueprints"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)

    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    current_version_id = Column(Integer, ForeignKey("visual_blueprint_versions.id"), nullable=True)

    versions = relationship(
        "VisualBlueprintVersion",
        back_populates="blueprint",
        cascade="all, delete-orphan",
        foreign_keys="VisualBlueprintVersion.blueprint_id",
    )
    current_version = relationship(
        "VisualBlueprintVersion",
        foreign_keys=[current_version_id],
        post_update=True,
    )


class VisualBlueprintVersion(Base):
    __tablename__ = "visual_blueprint_versions"

    id = Column(Integer, primary_key=True, index=True)
    blueprint_id = Column(Integer, ForeignKey("visual_blueprints.id"), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    graph_json = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    blueprint = relationship(
        "VisualBlueprint",
        back_populates="versions",
        foreign_keys=[blueprint_id],
    )


class VisualDeployJob(Base):
    __tablename__ = "visual_deploy_jobs"

    id = Column(Integer, primary_key=True, index=True)
    blueprint_id = Column(Integer, ForeignKey("visual_blueprints.id"), nullable=False, index=True)
    blueprint_version_id = Column(Integer, ForeignKey("visual_blueprint_versions.id"), nullable=False, index=True)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    status = Column(String, default="queued", index=True)  # queued|running|success|failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)

    target_device_ids = Column(JSON, nullable=False, default=list)
    summary = Column(JSON, nullable=True)

    results = relationship("VisualDeployResult", back_populates="job", cascade="all, delete-orphan")


class VisualDeployResult(Base):
    __tablename__ = "visual_deploy_results"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("visual_deploy_jobs.id"), nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)

    success = Column(Boolean, default=False)
    rendered_config = Column(Text, nullable=True)
    output_log = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("VisualDeployJob", back_populates="results")
