from __future__ import annotations

from typing import Any, Dict, Set

from app.core.field_encryption import get_fernet

_ENC_PREFIX = "enc:"

_COMMON_SENSITIVE_KEYS: Set[str] = {
    "secret_key",
    "client_secret",
    "service_account_json",
    "shared_secret",
    "private_key",
    "session_token",
    "source_session_token",
    "external_id",
}

_PROVIDER_SENSITIVE_KEYS: Dict[str, Set[str]] = {
    "aws": {"access_key", "secret_key", "source_access_key", "source_secret_key", "session_token", "source_session_token", "external_id"},
    "azure": {"client_secret"},
    "gcp": {"service_account_json"},
    "naver": {"access_key", "secret_key"},
    "naver_cloud": {"access_key", "secret_key"},
    "ncp": {"access_key", "secret_key"},
}


def _normalize_provider(provider: str | None) -> str:
    return str(provider or "").strip().lower()


def sensitive_keys(provider: str | None) -> Set[str]:
    p = _normalize_provider(provider)
    return set(_COMMON_SENSITIVE_KEYS).union(_PROVIDER_SENSITIVE_KEYS.get(p, set()))


def _is_encrypted_token(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_ENC_PREFIX)


def _encrypt_scalar(value: Any) -> Any:
    if value in (None, "", "********"):
        return value
    if _is_encrypted_token(value):
        return value
    plain = str(value)
    token = get_fernet().encrypt(plain.encode("utf-8")).decode("utf-8")
    return f"{_ENC_PREFIX}{token}"


def _decrypt_scalar(value: Any) -> Any:
    if not _is_encrypted_token(value):
        return value
    token = str(value)[len(_ENC_PREFIX):]
    try:
        return get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return value


def encrypt_credentials_for_storage(provider: str | None, credentials: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(credentials, dict):
        return {}
    out = dict(credentials)
    for key in sensitive_keys(provider):
        if key in out:
            out[key] = _encrypt_scalar(out.get(key))
    return out


def decrypt_credentials_for_runtime(provider: str | None, credentials: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(credentials, dict):
        return {}
    out = dict(credentials)
    for key in sensitive_keys(provider):
        if key in out:
            out[key] = _decrypt_scalar(out.get(key))
    return out

