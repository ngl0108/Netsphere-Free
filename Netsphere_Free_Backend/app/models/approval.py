from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id = Column(Integer, primary_key=True, index=True)
    
    # Who
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=True) # 승인/거절한 사람
    
    # What
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    request_type = Column(String, default="config_deploy") # config_deploy, firmware_upgrade, etc.
    
    # Payload (실제 수행할 작업 데이터)
    # 예: { "device_ids": [1, 2], "command": "...", "blueprint_id": 5 }
    payload = Column(JSON, nullable=True) 
    
    # Status
    status = Column(String, default="pending") # pending, approved, rejected, cancelled
    
    # Comments & Audit
    requester_comment = Column(Text, nullable=True)
    approver_comment = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    decided_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    requester = relationship("User", foreign_keys=[requester_id])
    approver = relationship("User", foreign_keys=[approver_id])
