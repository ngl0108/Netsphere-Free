from sqlalchemy import Column, Integer, String, Text
from app.db.session import Base
from app.db.encrypted_types import EncryptedString

class SystemSetting(Base):
    __tablename__ = "system_settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value = Column(EncryptedString, nullable=False)
    description = Column(String, nullable=True)
    category = Column(String, default="General")
