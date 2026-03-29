from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base
import enum

class JobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

class UpgradeJob(Base):
    """
    SWIM Upgrade Job
    Tracks the progress of installing a specific firmware image onto a device.
    """
    __tablename__ = "upgrade_jobs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Target Device & Image
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    image_id = Column(Integer, ForeignKey("firmware_images.id"), nullable=False)
    
    # Status Tracking
    status = Column(String, default=JobStatus.PENDING.value)
    progress_percent = Column(Integer, default=0)
    current_stage = Column(String, default="queued") # e.g. "transferring_file", "verifying_checksum"
    
    # Logs needed for debugging failed jobs
    logs = Column(Text, nullable=True) 
    error_message = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    device = relationship("Device")
    image = relationship("FirmwareImage")
