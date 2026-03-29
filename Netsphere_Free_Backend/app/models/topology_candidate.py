from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Float
from sqlalchemy.sql import func

from app.db.session import Base


class TopologyNeighborCandidate(Base):
    __tablename__ = "topology_neighbor_candidates"

    id = Column(Integer, primary_key=True, index=True)
    discovery_job_id = Column(Integer, ForeignKey("discovery_jobs.id"), nullable=True)
    source_device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)

    neighbor_name = Column(String, nullable=False)
    mgmt_ip = Column(String, nullable=True)
    local_interface = Column(String, nullable=True)
    remote_interface = Column(String, nullable=True)

    protocol = Column(String, default="UNKNOWN")
    confidence = Column(Float, default=0.3)
    reason = Column(String, nullable=True)
    status = Column(String, default="unmatched")

    first_seen = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
