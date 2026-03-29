from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.credentials import SnmpCredentialProfile
from app.models.device import Site

router = APIRouter()


class SnmpProfileCreate(BaseModel):
    name: str
    snmp_version: str = "v2c"
    snmp_port: int = 161
    snmp_community: Optional[str] = "public"
    snmp_v3_username: Optional[str] = None
    snmp_v3_security_level: Optional[str] = None
    snmp_v3_auth_proto: Optional[str] = None
    snmp_v3_auth_key: Optional[str] = None
    snmp_v3_priv_proto: Optional[str] = None
    snmp_v3_priv_key: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_password: Optional[str] = None
    ssh_port: Optional[int] = 22
    enable_password: Optional[str] = None
    device_type: Optional[str] = None


class SnmpProfileResponse(BaseModel):
    id: int
    name: str
    snmp_version: str
    snmp_port: int
    snmp_community: Optional[str] = None
    snmp_v3_username: Optional[str] = None
    snmp_v3_security_level: Optional[str] = None
    snmp_v3_auth_proto: Optional[str] = None
    snmp_v3_priv_proto: Optional[str] = None
    ssh_username: Optional[str] = None
    ssh_port: Optional[int] = None
    device_type: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AssignSiteProfileRequest(BaseModel):
    snmp_profile_id: Optional[int] = None


@router.get("/", response_model=List[SnmpProfileResponse])
def list_snmp_profiles(
    db: Session = Depends(get_db),
    current_user=Depends(deps.require_viewer),
):
    return db.query(SnmpCredentialProfile).order_by(SnmpCredentialProfile.id.asc()).all()


@router.post("/", response_model=SnmpProfileResponse)
def create_snmp_profile(
    req: SnmpProfileCreate,
    db: Session = Depends(get_db),
    current_user=Depends(deps.require_network_admin),
):
    exists = db.query(SnmpCredentialProfile).filter(SnmpCredentialProfile.name == req.name).first()
    if exists:
        raise HTTPException(status_code=400, detail="profile name already exists")
    p = SnmpCredentialProfile(**req.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.delete("/{profile_id}")
def delete_snmp_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(deps.require_network_admin),
):
    p = db.query(SnmpCredentialProfile).filter(SnmpCredentialProfile.id == profile_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="profile not found")
    used = db.query(Site).filter(Site.snmp_profile_id == profile_id).count()
    if used > 0:
        raise HTTPException(status_code=400, detail="profile is assigned to one or more sites")
    db.delete(p)
    db.commit()
    return {"status": "ok"}


@router.put("/sites/{site_id}")
def assign_site_snmp_profile(
    site_id: int,
    req: AssignSiteProfileRequest,
    db: Session = Depends(get_db),
    current_user=Depends(deps.require_network_admin),
):
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="site not found")
    if req.snmp_profile_id is not None:
        prof = db.query(SnmpCredentialProfile).filter(SnmpCredentialProfile.id == req.snmp_profile_id).first()
        if not prof:
            raise HTTPException(status_code=404, detail="profile not found")
    site.snmp_profile_id = req.snmp_profile_id
    db.commit()
    return {"status": "ok", "site_id": site_id, "snmp_profile_id": req.snmp_profile_id}
