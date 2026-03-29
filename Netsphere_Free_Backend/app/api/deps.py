from datetime import datetime, timedelta, timezone
import logging
from typing import Generator, List, Optional
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.core import config, security
from app.services.password_policy_service import PasswordPolicyService
from app.services.preview_edition_service import PreviewEditionService
from app.services.session_service import SessionService

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
logger = logging.getLogger("uvicorn")


def _auth_exception(
    *,
    status_code: int,
    code: str,
    message: str,
    reason: Optional[str] = None,
    retryable: Optional[bool] = None,
    force_logout: Optional[bool] = None,
) -> HTTPException:
    details = {}
    if reason:
        details["reason"] = str(reason)
    if retryable is not None:
        details["retryable"] = bool(retryable)
    if force_logout is not None:
        details["force_logout"] = bool(force_logout)

    payload = {"code": str(code), "message": str(message)}
    if details:
        payload["details"] = details

    headers = {"WWW-Authenticate": "Bearer"} if int(status_code) == int(status.HTTP_401_UNAUTHORIZED) else None
    return HTTPException(status_code=int(status_code), detail=payload, headers=headers)


def _session_reason_to_error(reason: str) -> tuple[str, str, bool, bool]:
    key = str(reason or "").strip().lower()
    mapping = {
        "missing_session": ("AUTH_SESSION_MISSING", "Session record is missing. Please retry.", True, False),
        "session_user_mismatch": ("AUTH_SESSION_MISMATCH", "Session mismatch detected. Please sign in again.", False, True),
        "revoked": ("AUTH_SESSION_REVOKED", "Session has been revoked. Please sign in again.", False, True),
        "expired": ("AUTH_SESSION_EXPIRED", "Session has expired. Please sign in again.", False, True),
        "idle_timeout": ("AUTH_SESSION_IDLE_TIMEOUT", "Session timed out due to inactivity. Please sign in again.", False, True),
    }
    return mapping.get(key, ("AUTH_UNAUTHORIZED", "Authentication failed. Please sign in again.", False, True))

def get_db() -> Generator:
    """Dependency for getting DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """
    Mandatory authentication dependency for ALL endpoints.
    Ensures the user is logged in and active.
    """
    payload = security.decode_access_token(token)
    if not payload:
        raise _auth_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_TOKEN_INVALID",
            message="Invalid access token",
            reason="token_decode_failed",
            retryable=False,
            force_logout=True,
        )
    username: str = payload.get("sub")
    jti: str = payload.get("jti")
    if not username or not jti:
        raise _auth_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_TOKEN_INVALID",
            message="Access token is missing required claims",
            reason="token_claims_missing",
            retryable=False,
            force_logout=True,
        )
    
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise _auth_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_USER_NOT_FOUND",
            message="Authenticated user does not exist",
            reason="user_not_found",
            retryable=False,
            force_logout=True,
        )
    
    if not user.is_active:
            raise _auth_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="AUTH_USER_INACTIVE",
                message="Inactive user",
                reason="user_inactive",
            )

    if PasswordPolicyService.is_locked(user):
        raise _auth_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="AUTH_ACCOUNT_LOCKED",
            message="Account is locked",
            reason="account_locked",
        )

    # [SaaS] Tenant Check
    # If user belongs to a tenant, ensure tenant is active
    if user.tenant_id:
        if not user.tenant or not user.tenant.is_active:
             raise _auth_exception(
                 status_code=status.HTTP_403_FORBIDDEN,
                 code="AUTH_TENANT_INACTIVE",
                 message="Tenant is inactive or suspended",
                 reason="tenant_inactive",
             )

    ok, reason, changed = SessionService.validate_and_touch(db, user_id=int(user.id), jti=str(jti))
    if not ok and reason == "missing_session":
        # Recover rare DB/session-drift case: token is valid but session row is missing.
        expires_at = None
        exp = payload.get("exp")
        if isinstance(exp, (int, float)):
            try:
                expires_at = datetime.fromtimestamp(float(exp), tz=timezone.utc)
            except Exception:
                expires_at = None
        if not expires_at:
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
        SessionService.create(
            db,
            user_id=int(user.id),
            jti=str(jti),
            expires_at=expires_at,
            ip=getattr(getattr(request, "client", None), "host", None),
            user_agent=request.headers.get("User-Agent"),
        )
        db.commit()
        ok, reason, changed = SessionService.validate_and_touch(db, user_id=int(user.id), jti=str(jti))
    if changed:
        db.commit()
    if not ok:
        code, message, retryable, force_logout = _session_reason_to_error(reason)
        logger.warning(
            "auth_session_validation_failed user=%s uid=%s reason=%s path=%s",
            username,
            getattr(user, "id", None),
            reason,
            str(getattr(getattr(request, "url", None), "path", "")),
        )
        raise _auth_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=code,
            message=message,
            reason=reason,
            retryable=retryable,
            force_logout=force_logout,
        )

    prev_must_change = bool(getattr(user, "must_change_password", False))
    PasswordPolicyService.apply_password_expiry(db, user)
    if bool(getattr(user, "must_change_password", False)) != prev_must_change:
        db.commit()
    return user

def get_current_tenant_user(current_user: User = Depends(get_current_user)) -> User:
    """
    SaaS: Ensures user is in a tenant context.
    Returns the user object, but validates tenant association.
    """
    if not current_user.tenant_id:
        # If system admin (no tenant), allow access or block?
        # For now, if role is admin, allow system-wide access.
        # If standard user, require tenant.
        if current_user.role == "admin":
            return current_user
        raise _auth_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="AUTH_TENANT_REQUIRED",
            message="User is not assigned to any organization (tenant)",
            reason="tenant_required",
        )
    return current_user

class RoleChecker:
    """
    Simplified 3-tier RBAC Role Checker.
    Roles: admin > operator > viewer
    """
    def __init__(self, allowed_roles: List[str]):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: User = Depends(get_current_user)):
        if current_user.role not in self.allowed_roles:
            raise _auth_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="AUTH_ROLE_FORBIDDEN",
                message=f"Access denied. Required roles: {self.allowed_roles}. Your role: {current_user.role}",
                reason="role_forbidden",
            )
        return current_user

# =============================================================================
# 3-Tier Role System (Simplified)
# =============================================================================
# 
# 1. Admin: Full system control (User Management, Delete, Settings, All Operations)
# 2. Operator: Device management, Config deployment, ZTP approval (No Delete, No User Mgmt)
# 3. Viewer: Read-only access to Dashboards, Topology, and Logs
#
# =============================================================================

# Admin: Can do everything
require_admin = RoleChecker(["admin"])

# Operator+: Can manage devices, deploy configs, approve ZTP
require_operator = RoleChecker(["admin", "operator"])

# Viewer+: Can view dashboards, logs, topology (all authenticated users)
require_viewer = RoleChecker(["admin", "operator", "viewer"])

# Aliases for backward compatibility (map old roles to new)
require_super_admin = require_admin  # super_admin -> admin
require_network_admin = require_operator  # network_admin -> operator


def enforce_preview_request_policy(
    request: Request,
    db: Session = Depends(get_db),
):
    if not PreviewEditionService.is_mutation_blocked(
        db,
        method=request.method,
        path=str(getattr(getattr(request, "url", None), "path", "")),
    ):
        return
    raise _auth_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="PREVIEW_EDITION_BLOCKED",
        message="This action is disabled in NetSphere Free.",
        reason="preview_policy_blocked",
    )
