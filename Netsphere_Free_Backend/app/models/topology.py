from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class TopologyLayout(Base):
    __tablename__ = "topology_layout"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False, default="Default Layout")
    data = Column(JSON, nullable=False)  # Stores node positions, sizes, etc.
    is_shared = Column(Boolean, default=False)  # Allow sharing with other users (future)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationship (User model needs backref to access layouts if needed)
    user = relationship("User", backref="layouts")


class TopologySnapshot(Base):
    __tablename__ = "topology_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, nullable=True, index=True)
    job_id = Column(Integer, nullable=True, index=True)
    label = Column(String(255), nullable=True)

    node_count = Column(Integer, nullable=False, default=0)
    link_count = Column(Integer, nullable=False, default=0)

    nodes_json = Column(Text, nullable=False, default="[]")
    links_json = Column(Text, nullable=False, default="[]")
    metadata_json = Column(Text, nullable=False, default="{}")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class TopologyChangeEvent(Base):
    __tablename__ = "topology_change_events"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, nullable=True, index=True)
    device_id = Column(Integer, nullable=True, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
