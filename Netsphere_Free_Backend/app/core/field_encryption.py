import base64
import hashlib
import os
from functools import lru_cache
import logging

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)
_DEFAULT_SECRET_KEY = "CHANGE_THIS_TO_A_SECURE_SECRET_KEY_IN_PRODUCTION"


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _normalize_field_key(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    try:
        Fernet(s.encode("utf-8"))
        return s
    except Exception:
        return _derive_fernet_key(s).decode("utf-8")


def make_fernet(raw_key: str) -> Fernet:
    key = _normalize_field_key(raw_key)
    if not key:
        raise ValueError("FIELD_ENCRYPTION_KEY is empty")
    return Fernet(key.encode("utf-8"))


@lru_cache(maxsize=1)
def get_fernet() -> Fernet:
    raw_key = os.getenv("FIELD_ENCRYPTION_KEY") or ""
    if raw_key.strip():
        return make_fernet(raw_key)

    secret_key = os.getenv("SECRET_KEY") or _DEFAULT_SECRET_KEY
    if secret_key == _DEFAULT_SECRET_KEY:
        raise RuntimeError("SECRET_KEY 또는 FIELD_ENCRYPTION_KEY를 반드시 설정해야 합니다.")

    app_env = (os.getenv("APP_ENV") or "").strip().lower()
    if app_env in {"prod", "production"}:
        allow = (os.getenv("ALLOW_DERIVED_FIELD_ENCRYPTION_KEY") or "").strip().lower() in {"1", "true", "yes"}
        if not allow:
            raise RuntimeError("APP_ENV=production에서는 FIELD_ENCRYPTION_KEY를 반드시 설정해야 합니다.")
        logger.warning("FIELD_ENCRYPTION_KEY is not set; deriving field encryption key from SECRET_KEY")

    key = _derive_fernet_key(secret_key).decode("utf-8")
    return Fernet(key.encode("utf-8"))
