from sqlalchemy import Column, Integer, Text, DateTime
from sqlalchemy.sql import func

from app.db.session import Base


class LicenseState(Base):
    __tablename__ = "license_state"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, index=True)
    license_jwt = Column(Text, nullable=True)
    installed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

