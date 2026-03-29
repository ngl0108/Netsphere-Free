from datetime import datetime, timedelta
from typing import Optional, Union
import secrets
import jwt # [FIX] python-jose -> PyJWT
from passlib.context import CryptContext
from app.core import config

JWTError = jwt.PyJWTError # [FIX] Compatibility for auth endpoints

def _build_pwd_context() -> CryptContext:
    try:
        from passlib.handlers.argon2 import argon2 as argon2_handler
        has_argon2 = bool(argon2_handler.has_backend())
    except Exception:
        has_argon2 = False
    schemes = ["argon2", "bcrypt"] if has_argon2 else ["bcrypt"]
    return CryptContext(schemes=schemes, deprecated="auto")


pwd_context = _build_pwd_context()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    now = datetime.utcnow()
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    if "jti" not in to_encode:
        to_encode["jti"] = secrets.token_urlsafe(16)
    to_encode.update({"iat": int(now.timestamp()), "exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
        if not isinstance(payload, dict):
            return None
        return payload
    except jwt.PyJWTError:
        return None


def decode_access_token_allow_expired(token: str) -> Optional[dict]:
    """Decode JWT while keeping signature validation but ignoring exp for refresh flows."""
    try:
        payload = jwt.decode(
            token,
            config.SECRET_KEY,
            algorithms=[config.ALGORITHM],
            options={"verify_exp": False},
        )
        if not isinstance(payload, dict):
            return None
        return payload
    except jwt.PyJWTError:
        return None
