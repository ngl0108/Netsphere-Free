from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()
from app.models.settings import SystemSetting # [FIX] Register for create_all