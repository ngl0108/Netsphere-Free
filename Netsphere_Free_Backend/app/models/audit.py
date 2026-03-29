from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.db.session import Base

class AuditLog(Base):
    """
    운영 감사 로그 (Audit Trail)
    누가, 언제, 무엇을, 어떻게 변경했는지 기록.
    """
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Who
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    username = Column(String, nullable=True) # 유저가 삭제되어도 남도록 스냅샷
    ip_address = Column(String, nullable=True)
    
    # What
    action = Column(String, nullable=False, index=True) # e.g. "CREATE", "UPDATE", "DEPLOY", "DELETE"
    resource_type = Column(String, nullable=True)       # e.g. "Device", "Template", "User"
    resource_name = Column(String, nullable=True)       # e.g. "Switch-01"
    
    # Detail
    details = Column(Text, nullable=True) # JSON or Text description of changes
    status = Column(String, default="success") # success, failure

    chain_prev_hash = Column(String, nullable=True, index=True)
    chain_hash = Column(String, nullable=True, index=True)
    chain_alg = Column(String, nullable=True)
    chain_version = Column(Integer, default=1)
    
    # When
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
