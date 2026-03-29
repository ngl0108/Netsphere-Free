from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class DeviceInventoryItem(Base):
    __tablename__ = "device_inventory_items"
    __table_args__ = (
        UniqueConstraint("device_id", "ent_physical_index", name="uq_device_ent_physical_index"),
    )

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)

    ent_physical_index = Column(Integer, nullable=False, index=True)
    parent_index = Column(Integer, nullable=True, index=True)
    contained_in = Column(Integer, nullable=True)

    class_id = Column(Integer, nullable=True, index=True)
    class_name = Column(String, nullable=True, index=True)

    name = Column(String, nullable=True)
    description = Column(String, nullable=True)
    model_name = Column(String, nullable=True, index=True)
    serial_number = Column(String, nullable=True, index=True)
    mfg_name = Column(String, nullable=True)

    hardware_rev = Column(String, nullable=True)
    firmware_rev = Column(String, nullable=True)
    software_rev = Column(String, nullable=True)
    is_fru = Column(Boolean, nullable=True)

    last_seen = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    device = relationship("Device", backref="inventory_items")
