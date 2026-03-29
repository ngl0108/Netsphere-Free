from sqlalchemy import Column, Integer, String, Text, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from app.db.session import Base

class ComplianceStandard(Base):
    """
    보안 규정/표준 그룹 (예: "CIS Benchmark Level 1", "Corporate Basic Policy")
    """
    __tablename__ = "compliance_standards"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    device_family = Column(String, default="cisco_ios")  # cisco_ios, cisco_nxos, etc.
    
    created_at = Column(String, nullable=True) # ISO format date string for simplicity or DateTime
    
    rules = relationship("ComplianceRule", back_populates="standard", cascade="all, delete-orphan")


class ComplianceRule(Base):
    """
    개별 감사 규칙 (예: "Check 'service password-encryption' exists")
    """
    __tablename__ = "compliance_rules"
    id = Column(Integer, primary_key=True, index=True)
    standard_id = Column(Integer, ForeignKey("compliance_standards.id"), index=True)
    
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    severity = Column(String, default="medium") # critical, high, medium, low
    
    # Check Logic
    # - simple_match: pattern string must exist in config
    # - absent_match: pattern string must NOT exist in config
    # - regex_match: pattern regex must match
    check_type = Column(String, default="simple_match") 
    
    pattern = Column(Text, nullable=False) # The string or regex to look for
    
    remediation = Column(Text, nullable=True) # Guide or command to fix custom info
    
    standard = relationship("ComplianceStandard", back_populates="rules")
