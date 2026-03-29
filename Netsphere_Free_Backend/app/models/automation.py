from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class AutomationRule(Base):
    __tablename__ = "automation_rules"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)
    
    # Trigger Condition
    # Types: 
    # - 'cpu': trigger_value (float)
    # - 'memory': trigger_value (float)
    # - 'interface_traffic_in': trigger_target (if_name), trigger_value (bps)
    # - 'interface_traffic_out': trigger_target (if_name), trigger_value (bps)
    # - 'interface_status': trigger_target (if_name), trigger_value (up/down)
    # - 'latency': trigger_value (ms)
    trigger_type = Column(String, nullable=False) 
    trigger_target = Column(String, nullable=True) # Interface name or specific metric key
    trigger_condition = Column(String, default=">=") # '>=', '<=', '==', '!='
    trigger_value = Column(String, nullable=False) # Value to compare against
    
    # Action
    # Types: 'workflow', 'template', 'webhook'
    action_type = Column(String, nullable=False) 
    action_id = Column(String, nullable=True) # Workflow ID or Template ID
    action_params = Column(JSON, nullable=True) # Parameters for the action (e.g. variables)
    
    # Scope (If null, applies to all compatible devices)
    target_device_ids = Column(JSON, nullable=True) # List[int]
    
    # Operational Settings
    enabled = Column(Boolean, default=True)
    cooldown_seconds = Column(Integer, default=300) # Minimum time between triggers
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
