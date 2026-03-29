from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, timezone
from typing import List
import os
import secrets
from pydantic import BaseModel, EmailStr

from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.core import security, config
from app.api import deps
from app.services.password_policy_service import PasswordPolicyService
from app.services.session_service import SessionService
from app.services.email_service import EmailService
from app.services.mfa_service import MfaService
from app.services.audit_service import AuditService
from app.services.email_verification_service import EmailVerificationService
from app.services.preview_edition_service import PreviewEditionService

router = APIRouter()


def _auth_http_exception(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
) -> HTTPException:
    payload = {"code": str(code), "message": str(message)}
    if details:
        payload["details"] = details
    headers = {"WWW-Authenticate": "Bearer"} if int(status_code) == int(status.HTTP_401_UNAUTHORIZED) else None
    return HTTPException(status_code=int(status_code), detail=payload, headers=headers)

class MfaVerifyRequest(BaseModel):
    challenge_id: int
    otp: str


class ProfileUpdateRequest(BaseModel):
    email: str | None = None
    mfa_enabled: bool | None = None


class EmailVerifySendResponse(BaseModel):
    challenge_id: int
    message: str


class EmailVerifyRequest(BaseModel):
    challenge_id: int
    otp: str


class InitialAdminStatusResponse(BaseModel):
    enabled: bool
    initial_admin_required: bool
    deployment_role: str


class InitialAdminCreateRequest(BaseModel):
    username: str = "admin"
    password: str
    full_name: str | None = None
    email: EmailStr | None = None


def _issue_access_token(
    *,
    db: Session,
    user: User,
    request: Request,
    action: str,
    resource_name: str,
) -> dict:
    access_token_expires = timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    jti = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc) + access_token_expires
    SessionService.create(
        db,
        user_id=int(user.id),
        jti=jti,
        expires_at=expires_at,
        ip=getattr(getattr(request, "client", None), "host", None),
        user_agent=request.headers.get("User-Agent"),
    )
    db.commit()
    access_token = security.create_access_token(
        data={"sub": user.username, "uid": user.id, "jti": jti},
        expires_delta=access_token_expires,
    )
    try:
        AuditService.log(
            db=db,
            user=user,
            action=action,
            resource_type="auth",
            resource_name=resource_name,
            details="Access token issued",
            status="success",
            ip=getattr(getattr(request, "client", None), "host", None),
        )
    except Exception:
        pass
    return {"access_token": access_token, "token_type": "bearer"}


def _refresh_reason_to_error(reason: str) -> tuple[str, str, dict]:
    key = str(reason or "").strip().lower()
    mapping = {
        "missing_session": ("AUTH_SESSION_MISSING", "Session record is missing. Please sign in again.", {"reason": "missing_session", "force_logout": True}),
        "session_user_mismatch": ("AUTH_SESSION_MISMATCH", "Session mismatch detected. Please sign in again.", {"reason": "session_user_mismatch", "force_logout": True}),
        "revoked": ("AUTH_SESSION_REVOKED", "Session has been revoked. Please sign in again.", {"reason": "revoked", "force_logout": True}),
        "expired": ("AUTH_SESSION_EXPIRED", "Session has expired. Please sign in again.", {"reason": "expired", "force_logout": True}),
        "idle_timeout": ("AUTH_SESSION_IDLE_TIMEOUT", "Session timed out due to inactivity. Please sign in again.", {"reason": "idle_timeout", "force_logout": True}),
    }
    return mapping.get(key, ("AUTH_UNAUTHORIZED", "Authentication failed. Please sign in again.", {"reason": key or "unknown", "force_logout": True}))


def _is_loopback_request(request: Request) -> bool:
    if (os.getenv("APP_ENV") or "").strip().lower() in {"test", "pytest"}:
        return True
    host = str(getattr(getattr(request, "client", None), "host", "") or "").strip().lower()
    forwarded = str(request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip().lower()
    candidates = {host, forwarded}
    candidates.discard("")
    return any(value in {"127.0.0.1", "::1", "localhost", "testclient"} for value in candidates)


@router.post("/login")
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """User login and JWT token generation."""
    client_ip = getattr(getattr(request, "client", None), "host", None)
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user:
        class MockUser:
            def __init__(self, username: str):
                self.id = None
                self.username = username
        AuditService.log(
            db=db,
            user=MockUser(username=form_data.username),
            action="LOGIN_FAILED",
            resource_type="auth",
            resource_name="/auth/login",
            details="Invalid credentials",
            status="failed",
            ip=client_ip,
        )
        raise _auth_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_CREDENTIALS_INVALID",
            message="Incorrect username or password",
        )

    if PasswordPolicyService.is_locked(user):
        AuditService.log(
            db=db,
            user=user,
            action="LOGIN_BLOCKED",
            resource_type="auth",
            resource_name="/auth/login",
            details="Account locked",
            status="failed",
            ip=client_ip,
        )
        raise _auth_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="AUTH_ACCOUNT_LOCKED",
            message="Account is locked. Try again later.",
            details={"reason": "account_locked"},
        )
    
    if not user.is_active:
         AuditService.log(
             db=db,
             user=user,
             action="LOGIN_BLOCKED",
             resource_type="auth",
             resource_name="/auth/login",
             details="Inactive user",
             status="failed",
             ip=client_ip,
         )
         raise _auth_http_exception(
             status_code=status.HTTP_403_FORBIDDEN,
             code="AUTH_USER_INACTIVE",
             message="Inactive user",
             details={"reason": "user_inactive"},
         )

    if not security.verify_password(form_data.password, user.hashed_password):
        locked = PasswordPolicyService.register_failed_login(db, user)
        db.commit()
        AuditService.log(
            db=db,
            user=user,
            action="LOGIN_FAILED",
            resource_type="auth",
            resource_name="/auth/login",
            details="Invalid credentials",
            status="failed",
            ip=client_ip,
        )
        if locked:
            raise _auth_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="AUTH_ACCOUNT_LOCKED",
                message="Account is locked due to too many failed attempts.",
                details={"reason": "too_many_failed_attempts"},
            )
        raise _auth_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_CREDENTIALS_INVALID",
            message="Incorrect username or password",
        )

    if (
        MfaService.is_enabled(db)
        and user.username != "system"
        and bool(getattr(user, "mfa_enabled", False))
    ):
        if not getattr(user, "email", None):
            raise _auth_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="AUTH_MFA_EMAIL_NOT_CONFIGURED",
                message="2FA is enabled for this user but email is not configured",
            )
        if not bool(getattr(user, "email_verified", False)):
            raise _auth_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="AUTH_EMAIL_NOT_VERIFIED",
                message="Email verification is required before using 2FA",
            )
        ch, otp = MfaService.create_email_challenge(db, user=user)
        send_res = EmailService.send_email(
            db,
            to_email=str(user.email),
            subject="[NetSphere] Login verification code",
            content=f"Your verification code is: {otp}\n\nThis code expires soon. If you did not attempt to log in, ignore this email.",
        )
        db.commit()
        if not send_res.get("success"):
            raise _auth_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="AUTH_OTP_DELIVERY_FAILED",
                message=send_res.get("error") or "Failed to send OTP email",
            )
        AuditService.log(
            db=db,
            user=user,
            action="LOGIN_OTP_CHALLENGE",
            resource_type="auth",
            resource_name="/auth/login",
            details={"delivery": "email", "challenge_id": int(ch.id)},
            status="success",
            ip=client_ip,
        )
        return {"mfa_required": True, "delivery": "email", "challenge_id": int(ch.id)}

    PasswordPolicyService.register_success_login(db, user)
    db.commit()

    return _issue_access_token(
        db=db,
        user=user,
        request=request,
        action="LOGIN_SUCCESS",
        resource_name="/auth/login",
    )

@router.post("/login/verify-otp")
def verify_login_otp(req: MfaVerifyRequest, request: Request, db: Session = Depends(get_db)):
    client_ip = getattr(getattr(request, "client", None), "host", None)
    ok, user, reason, changed = MfaService.verify(db, challenge_id=int(req.challenge_id), otp=str(req.otp))
    if changed:
        db.commit()
    if not ok or not user:
        class MockUser:
            def __init__(self):
                self.id = None
                self.username = "anonymous"
        AuditService.log(
            db=db,
            user=MockUser(),
            action="OTP_FAILED",
            resource_type="auth",
            resource_name="/auth/login/verify-otp",
            details={"challenge_id": int(req.challenge_id), "reason": reason},
            status="failed",
            ip=client_ip,
        )
        raise _auth_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_OTP_INVALID",
            message="Invalid verification code",
        )

    if PasswordPolicyService.is_locked(user):
        raise _auth_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="AUTH_ACCOUNT_LOCKED",
            message="Account is locked. Try again later.",
            details={"reason": "account_locked"},
        )
    if not user.is_active:
        raise _auth_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="AUTH_USER_INACTIVE",
            message="Inactive user",
            details={"reason": "user_inactive"},
        )

    PasswordPolicyService.register_success_login(db, user)

    return _issue_access_token(
        db=db,
        user=user,
        request=request,
        action="OTP_SUCCESS",
        resource_name="/auth/login/verify-otp",
    )


@router.post("/refresh")
def refresh_access_token(
    request: Request,
    token: str = Depends(deps.oauth2_scheme),
    db: Session = Depends(get_db),
):
    payload = security.decode_access_token_allow_expired(token)
    if not payload:
        raise _auth_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_TOKEN_INVALID",
            message="Invalid access token",
            details={"reason": "token_decode_failed", "force_logout": True},
        )

    username = payload.get("sub")
    jti = payload.get("jti")
    uid_raw = payload.get("uid")
    try:
        uid = int(uid_raw)
    except Exception:
        uid = None

    if not username or not jti or uid is None:
        raise _auth_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_TOKEN_INVALID",
            message="Access token is missing required claims",
            details={"reason": "token_claims_missing", "force_logout": True},
        )

    user = db.query(User).filter(User.id == uid, User.username == str(username)).first()
    if not user:
        raise _auth_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_USER_NOT_FOUND",
            message="Authenticated user does not exist",
            details={"reason": "user_not_found", "force_logout": True},
        )
    if not bool(getattr(user, "is_active", False)):
        raise _auth_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="AUTH_USER_INACTIVE",
            message="Inactive user",
            details={"reason": "user_inactive"},
        )

    ok, reason = SessionService.validate_for_refresh(
        db,
        user_id=int(user.id),
        jti=str(jti),
        grace_seconds=int(config.ACCESS_TOKEN_REFRESH_GRACE_SECONDS),
    )
    if not ok:
        db.commit()
        code, message, details = _refresh_reason_to_error(reason)
        raise _auth_http_exception(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=code,
            message=message,
            details=details,
        )

    SessionService.revoke(db, user_id=int(user.id), jti=str(jti))
    return _issue_access_token(
        db=db,
        user=user,
        request=request,
        action="TOKEN_REFRESH",
        resource_name="/auth/refresh",
    )

@router.post("/logout")
def logout(
    current_user: User = Depends(deps.get_current_user),
    token: str = Depends(deps.oauth2_scheme),
    db: Session = Depends(get_db),
):
    payload = security.decode_access_token(token) or {}
    jti = payload.get("jti")
    if jti:
        SessionService.revoke(db, user_id=int(current_user.id), jti=str(jti))
        db.commit()
    try:
        AuditService.log(
            db=db,
            user=current_user,
            action="LOGOUT",
            resource_type="auth",
            resource_name="/auth/logout",
            details="Logout",
            status="success",
        )
    except Exception:
        pass
    return {"message": "Logged out"}


@router.patch("/me/profile", response_model=UserResponse)
def update_my_profile(
    payload: ProfileUpdateRequest,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    current_user = db.merge(current_user)

    if payload.email is not None:
        email = str(payload.email).strip()
        if email == "":
            email = None
        if email:
            existing = db.query(User).filter(User.email == email).first()
            if existing and int(existing.id) != int(current_user.id):
                raise HTTPException(status_code=400, detail="Email is already in use")
        if str(getattr(current_user, "email", "") or "") != str(email or ""):
            current_user.email_verified = False
        current_user.email = email

    if payload.mfa_enabled is not None:
        want = bool(payload.mfa_enabled)
        if want:
            if not MfaService.is_enabled(db):
                raise HTTPException(status_code=400, detail="2FA is not enabled on this system")
            if not getattr(current_user, "email", None):
                raise HTTPException(status_code=400, detail="Email is required to enable 2FA")
            if not bool(getattr(current_user, "email_verified", False)):
                raise HTTPException(status_code=400, detail="Email verification is required to enable 2FA")
        current_user.mfa_enabled = want

    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/me/email/send-verification", response_model=EmailVerifySendResponse)
def send_my_email_verification(
    request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    client_ip = getattr(getattr(request, "client", None), "host", None)
    current_user = db.merge(current_user)
    if not getattr(current_user, "email", None):
        raise HTTPException(status_code=400, detail="Email is not configured")

    retry_after = EmailVerificationService.get_retry_after_seconds(db, user_id=int(current_user.id))
    if retry_after > 0:
        AuditService.log(
            db=db,
            user=current_user,
            action="EMAIL_VERIFY_RATE_LIMIT",
            resource_type="auth",
            resource_name="/auth/me/email/send-verification",
            details={"retry_after_seconds": int(retry_after)},
            status="failed",
            ip=client_ip,
        )
        raise HTTPException(
            status_code=429,
            detail={"message": "Please wait before requesting another code", "retry_after_seconds": int(retry_after)},
        )

    ch, otp = EmailVerificationService.create(db, user=current_user)
    send_res = EmailService.send_email(
        db,
        to_email=str(current_user.email),
        subject="[NetSphere] Email verification code",
        content=f"Your verification code is: {otp}\n\nIf you did not request this, ignore this email.",
    )
    db.commit()
    if not send_res.get("success"):
        raise HTTPException(status_code=400, detail=send_res.get("error") or "Failed to send verification email")

    AuditService.log(
        db=db,
        user=current_user,
        action="EMAIL_VERIFY_SENT",
        resource_type="auth",
        resource_name="/auth/me/email/send-verification",
        details={"challenge_id": int(ch.id)},
        status="success",
        ip=client_ip,
    )
    return {"challenge_id": int(ch.id), "message": "Verification code sent"}


@router.post("/me/email/verify", response_model=UserResponse)
def verify_my_email(
    req: EmailVerifyRequest,
    request: Request,
    current_user: User = Depends(deps.get_current_user),
    db: Session = Depends(get_db),
):
    client_ip = getattr(getattr(request, "client", None), "host", None)
    current_user = db.merge(current_user)
    ok, user, reason, changed = EmailVerificationService.verify(
        db,
        user_id=int(current_user.id),
        challenge_id=int(req.challenge_id),
        otp=str(req.otp),
    )
    if changed:
        db.commit()
    if not ok or not user:
        AuditService.log(
            db=db,
            user=current_user,
            action="EMAIL_VERIFY_FAILED",
            resource_type="auth",
            resource_name="/auth/me/email/verify",
            details={"challenge_id": int(req.challenge_id), "reason": reason},
            status="failed",
            ip=client_ip,
        )
        raise HTTPException(status_code=400, detail="Invalid verification code")

    db.refresh(current_user)
    AuditService.log(
        db=db,
        user=current_user,
        action="EMAIL_VERIFY_SUCCESS",
        resource_type="auth",
        resource_name="/auth/me/email/verify",
        details="Email verified",
        status="success",
        ip=client_ip,
    )
    return current_user


@router.get("/bootstrap/status", response_model=InitialAdminStatusResponse)
def preview_initial_admin_status(db: Session = Depends(get_db)):
    policy = PreviewEditionService.get_policy(db)
    return InitialAdminStatusResponse(
        enabled=PreviewEditionService.initial_admin_allowed(db),
        initial_admin_required=PreviewEditionService.initial_admin_required(db),
        deployment_role=str(policy.get("deployment_role") or ""),
    )


@router.post("/bootstrap/initial-admin", response_model=UserResponse)
def create_preview_initial_admin(
    payload: InitialAdminCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if not _is_loopback_request(request):
        raise _auth_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="AUTH_BOOTSTRAP_LOCAL_ONLY",
            message="Initial admin setup is only allowed from the local host.",
        )
    if not PreviewEditionService.initial_admin_allowed(db):
        raise _auth_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="AUTH_BOOTSTRAP_DISABLED",
            message="Initial admin setup is not available for this deployment.",
        )
    if not PreviewEditionService.initial_admin_required(db):
        raise _auth_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="AUTH_BOOTSTRAP_NOT_REQUIRED",
            message="Initial admin setup is already completed.",
        )

    username = str(payload.username or "").strip()
    if not username:
        raise _auth_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="AUTH_BOOTSTRAP_USERNAME_REQUIRED",
            message="Username is required.",
        )
    if db.query(User).filter(User.username == username).first():
        raise _auth_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="AUTH_BOOTSTRAP_USERNAME_EXISTS",
            message="Username already exists.",
        )

    errors = PasswordPolicyService.validate_password(
        db,
        username=username,
        password=payload.password,
        current_user=None,
    )
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    new_user = User(
        username=username,
        email=payload.email,
        hashed_password=security.get_password_hash(payload.password),
        full_name=str(payload.full_name or "").strip() or "Preview Administrator",
        role="admin",
        is_active=True,
        must_change_password=False,
        eula_accepted=False,
        password_changed_at=datetime.now(timezone.utc),
        mfa_enabled=False,
        email_verified=False,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    PasswordPolicyService.record_password(db, new_user)
    db.commit()
    PreviewEditionService.mark_initial_admin_initialized(db, user=new_user)
    return new_user

@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(deps.get_current_user)):
    """Get current user information."""
    return current_user
@router.post("/me/accept-eula", response_model=UserResponse)
def accept_eula(current_user: User = Depends(deps.get_current_user), db: Session = Depends(get_db)):
    """User accepts EULA."""
    current_user = db.merge(current_user) # Fix: merge into current session
    current_user.eula_accepted = True
    db.commit()
    db.refresh(current_user)
    return current_user

@router.post("/me/change-password", response_model=UserResponse)
def change_password_me(
    new_password: str, 
    current_password: str,
    current_user: User = Depends(deps.get_current_user), 
    db: Session = Depends(get_db)
):
    """Change own password and clear 'must_change_password' flag."""
    current_user = db.merge(current_user) # Fix: merge into current session

    if not security.verify_password(current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect current password")

    errors = PasswordPolicyService.validate_password(
        db,
        username=current_user.username,
        password=new_password,
        current_user=current_user,
    )
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    
    current_user.hashed_password = security.get_password_hash(new_password)
    current_user.must_change_password = False
    current_user.password_changed_at = datetime.now(timezone.utc)
    PasswordPolicyService.record_password(db, current_user)
    db.commit()
    db.refresh(current_user)
    return current_user


# --- Administrative Endpoints (Admin Only) ---

@router.post("/users", response_model=UserResponse, dependencies=[Depends(deps.require_super_admin)])
def create_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """Create a new user (Admin only)."""
    db_user = db.query(User).filter(User.username == user_in.username).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")

    errors = PasswordPolicyService.validate_password(
        db,
        username=user_in.username,
        password=user_in.password,
        current_user=None,
    )
    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})
    
    hashed_password = security.get_password_hash(user_in.password)
    new_user = User(
        username=user_in.username,
        email=user_in.email,
        hashed_password=hashed_password,
        full_name=user_in.full_name,
        role=user_in.role,
        is_active=user_in.is_active,
        password_changed_at=datetime.now(timezone.utc),
        mfa_enabled=bool(getattr(user_in, "mfa_enabled", False) or False),
    )
    if new_user.mfa_enabled:
        if not MfaService.is_enabled(db):
            raise HTTPException(status_code=400, detail="2FA is not enabled on this system")
        if not new_user.email:
            raise HTTPException(status_code=400, detail="Email is required to enable 2FA")
        if not bool(getattr(new_user, "email_verified", False)):
            raise HTTPException(status_code=400, detail="Email must be verified to enable 2FA")
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    PasswordPolicyService.record_password(db, new_user)
    db.commit()
    return new_user

@router.get("/users", response_model=List[UserResponse], dependencies=[Depends(deps.require_super_admin)])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Read all users (Admin only)."""
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@router.put("/users/{user_id}", response_model=UserResponse, dependencies=[Depends(deps.require_super_admin)])
def update_user(user_id: int, user_in: UserUpdate, db: Session = Depends(get_db)):
    """Update a user (Admin only)."""
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    update_data = user_in.dict(exclude_unset=True)
    if "password" in update_data:
        raw_pw = update_data.pop("password")
        errors = PasswordPolicyService.validate_password(
            db,
            username=db_user.username,
            password=raw_pw,
            current_user=db_user,
        )
        if errors:
            raise HTTPException(status_code=400, detail={"errors": errors})
        update_data["hashed_password"] = security.get_password_hash(raw_pw)
        update_data["password_changed_at"] = datetime.now(timezone.utc)
        if "must_change_password" not in update_data:
            update_data["must_change_password"] = True

    if "mfa_enabled" in update_data:
        want = bool(update_data.get("mfa_enabled"))
        if want:
            if not MfaService.is_enabled(db):
                raise HTTPException(status_code=400, detail="2FA is not enabled on this system")
            email = update_data.get("email")
            effective_email = (email if email is not None else db_user.email) or None
            if not effective_email:
                raise HTTPException(status_code=400, detail="Email is required to enable 2FA")
            if not bool(getattr(db_user, "email_verified", False)):
                raise HTTPException(status_code=400, detail="Email must be verified to enable 2FA")
    
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    db.commit()
    db.refresh(db_user)
    if "hashed_password" in update_data:
        PasswordPolicyService.record_password(db, db_user)
        db.commit()
    return db_user

@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(deps.require_super_admin)])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """Delete a user (Admin only)."""
    db_user = db.query(User).filter(User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(db_user)
    db.commit()
    return None
