from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core import security
from app.models.user import User
from app.models.user_session import UserSession
from app.services.session_service import SessionService


def _error_body(payload: dict) -> dict:
    assert isinstance(payload, dict)
    assert payload.get("success") is False
    err = payload.get("error")
    assert isinstance(err, dict)
    return err


def test_auth_error_contract_not_authenticated(client):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == 401
    err = _error_body(res.json())
    assert str(err.get("code") or "") == "AUTH_NOT_AUTHENTICATED"


def test_auth_error_contract_login_invalid_credentials(client):
    res = client.post(
        "/api/v1/auth/login",
        data={"username": "unknown-user", "password": "bad-pass"},
    )
    assert res.status_code == 401
    err = _error_body(res.json())
    assert str(err.get("code") or "") == "AUTH_CREDENTIALS_INVALID"


def test_auth_error_contract_invalid_token(client):
    res = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalid.token"})
    assert res.status_code == 401
    err = _error_body(res.json())
    assert str(err.get("code") or "") == "AUTH_TOKEN_INVALID"
    details = err.get("details") or {}
    assert str(details.get("force_logout")).lower() in {"true", "1"}


def test_auth_error_contract_revoked_session(client, db):
    user = User(
        username="contract-user",
        email="contract-user@example.com",
        hashed_password=security.get_password_hash("contract-pass"),
        full_name="Contract User",
        is_active=True,
        role="viewer",
    )
    db.add(user)
    db.commit()

    jti = "contract-jti-revoked"
    token = security.create_access_token({"sub": user.username, "uid": int(user.id), "jti": jti})
    SessionService.create(db, user_id=int(user.id), jti=str(jti), expires_at=datetime.now(timezone.utc) + timedelta(minutes=30))
    db.commit()
    SessionService.revoke(db, user_id=int(user.id), jti=str(jti))
    db.commit()

    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    err = _error_body(res.json())
    assert str(err.get("code") or "") == "AUTH_SESSION_REVOKED"
    details = err.get("details") or {}
    assert str(details.get("reason") or "") == "revoked"


def _success_body(payload: dict) -> dict:
    if isinstance(payload, dict) and payload.get("success") is True and isinstance(payload.get("data"), dict):
        return payload.get("data") or {}
    return payload if isinstance(payload, dict) else {}


def test_auth_refresh_success(client, db):
    user = User(
        username="refresh-user",
        email="refresh-user@example.com",
        hashed_password=security.get_password_hash("refresh-pass"),
        full_name="Refresh User",
        is_active=True,
        role="viewer",
    )
    db.add(user)
    db.commit()

    now = datetime.now(timezone.utc)
    old_jti = "contract-jti-refresh"
    token = security.create_access_token(
        {"sub": user.username, "uid": int(user.id), "jti": old_jti},
        expires_delta=timedelta(minutes=10),
    )
    SessionService.create(
        db,
        user_id=int(user.id),
        jti=str(old_jti),
        expires_at=now + timedelta(minutes=10),
    )
    db.commit()

    res = client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = _success_body(res.json())
    assert str(body.get("token_type") or "").lower() == "bearer"
    assert str(body.get("access_token") or "").strip()

    old_session = db.query(UserSession).filter(UserSession.jti == str(old_jti)).first()
    assert old_session is not None
    assert old_session.revoked_at is not None


def test_auth_refresh_expired_beyond_grace(client, db):
    user = User(
        username="refresh-expired-user",
        email="refresh-expired-user@example.com",
        hashed_password=security.get_password_hash("refresh-pass"),
        full_name="Refresh Expired User",
        is_active=True,
        role="viewer",
    )
    db.add(user)
    db.commit()

    old_jti = "contract-jti-refresh-expired"
    token = security.create_access_token(
        {"sub": user.username, "uid": int(user.id), "jti": old_jti},
        expires_delta=timedelta(seconds=-10),
    )
    SessionService.create(
        db,
        user_id=int(user.id),
        jti=str(old_jti),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db.commit()

    res = client.post("/api/v1/auth/refresh", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401
    err = _error_body(res.json())
    assert str(err.get("code") or "") == "AUTH_SESSION_EXPIRED"
