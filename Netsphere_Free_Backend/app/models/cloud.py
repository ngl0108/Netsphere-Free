from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class CloudAccount(Base):
    __tablename__ = "cloud_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    credentials = Column(JSON, nullable=False) 
    
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    sync_status = Column(String, nullable=True)
    sync_message = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Resources discovered from this account
    resources = relationship("CloudResource", back_populates="account", cascade="all, delete-orphan")

class CloudResource(Base):
    __tablename__ = "cloud_resources"
    
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("cloud_accounts.id"), nullable=False)
    
    resource_id = Column(String, index=True, nullable=False) # vpc-xxxx, vnet-xxxx
    resource_type = Column(String, nullable=False)
    name = Column(String, nullable=True)
    region = Column(String, nullable=True)
    
    cidr_block = Column(String, nullable=True)
    resource_metadata = Column(JSON, nullable=True)
    state = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    account = relationship("CloudAccount", back_populates="resources")
