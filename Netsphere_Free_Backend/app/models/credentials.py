from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func

from app.db.session import Base
from app.db.encrypted_types import EncryptedString


class SnmpCredentialProfile(Base):
    __tablename__ = "snmp_credential_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True, index=True)

    snmp_version = Column(String, default="v2c", nullable=False)
    snmp_port = Column(Integer, default=161, nullable=False)
    snmp_community = Column(EncryptedString, nullable=True)

    snmp_v3_username = Column(String, nullable=True)
    snmp_v3_security_level = Column(String, nullable=True)
    snmp_v3_auth_proto = Column(String, nullable=True)
    snmp_v3_auth_key = Column(EncryptedString, nullable=True)
    snmp_v3_priv_proto = Column(String, nullable=True)
    snmp_v3_priv_key = Column(EncryptedString, nullable=True)

    ssh_username = Column(String, nullable=True)
    ssh_password = Column(EncryptedString, nullable=True)
    ssh_port = Column(Integer, nullable=True)
    enable_password = Column(EncryptedString, nullable=True)
    device_type = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
