from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.core.field_encryption import get_fernet


class EncryptedString(TypeDecorator):
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        s = str(value)
        if s == "":
            return ""
        if s.startswith("enc:"):
            return s
        token = get_fernet().encrypt(s.encode("utf-8")).decode("utf-8")
        return f"enc:{token}"

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        s = str(value)
        if not s.startswith("enc:"):
            return s
        token = s[4:]
        try:
            return get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
        except Exception:
            return None

