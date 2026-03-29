from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class User(Base):
    __tablename__ = "users"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(String, default="viewer") # admin, editor, viewer
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True), nullable=True)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    password_changed_at = Column(DateTime(timezone=True), nullable=True)
    
    # [Security] First Run Wizard Fields
    eula_accepted = Column(Boolean, default=False)
    must_change_password = Column(Boolean, default=True) # Forced change for new users

    mfa_enabled = Column(Boolean, default=False)
    email_verified = Column(Boolean, default=False)
    
    # Relationship to Device (Device owner)
    devices = relationship("Device", back_populates="owner")
    password_history = relationship("UserPasswordHistory", back_populates="user", cascade="all, delete-orphan")
    
    # SaaS Tenant
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)
    tenant = relationship("Tenant", back_populates="users")

from app.models import device as _device
from app.models import user_password_history as _user_password_history
from app.models import tenant as _tenant
