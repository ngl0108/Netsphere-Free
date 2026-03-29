from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.services.license_service import LicenseService


router = APIRouter()


class LicenseInstallRequest(BaseModel):
    license_jwt: str


class LicenseRevokeRequest(BaseModel):
    jti: str | None = None
    reason: str = "manual_revoke"
    installed_license: bool = True


@router.get("/status")
def get_license_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return LicenseService.get_status(db)


@router.post("/install")
def install_license(
    req: LicenseInstallRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    try:
        return LicenseService.install(db, req.license_jwt)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/install")
def uninstall_license(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    return LicenseService.uninstall(db)


@router.get("/revocations")
def list_license_revocations(
    current_user: User = Depends(deps.require_super_admin),
):
    return LicenseService.list_revocations()


@router.post("/revoke")
def revoke_license(
    req: LicenseRevokeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    try:
        actor = str(getattr(current_user, "username", None) or "admin")
        if bool(req.installed_license):
            return LicenseService.revoke_installed_license(db, reason=req.reason, revoked_by=actor)
        return LicenseService.revoke_jti(str(req.jti or "").strip(), reason=req.reason, revoked_by=actor)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/revoke/{jti}")
def unrevoke_license(
    jti: str,
    current_user: User = Depends(deps.require_super_admin),
):
    try:
        return LicenseService.unrevoke_jti(jti)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
