from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.schemas.device import SiteResponse, SiteCreate, SiteUpdate
from app.models.device import Site, SiteVlan, Device, ComplianceReport
from app.services.compliance_service import ComplianceEngine

router = APIRouter()

# --------------------------------------------------------------------------
# [Local Schemas]
# --------------------------------------------------------------------------
class SiteVlanCreate(BaseModel):
    vlan_id: int
    name: str
    subnet: Optional[str] = None
    description: Optional[str] = None

class AssignDevicesRequest(BaseModel):
    device_ids: List[int]

class ComplianceCheckRequest(BaseModel):
    device_id: int
    template_content: str

# --------------------------------------------------------------------------
# [API] 사이트 기본 CRUD
# --------------------------------------------------------------------------

@router.get("/", response_model=List[SiteResponse])
def read_sites(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """Read all sites."""
    return db.query(Site).all()

@router.post("/", response_model=SiteResponse)
def create_site(
    site_in: SiteCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    """Create a new site (Admin only)."""
    if db.query(Site).filter(Site.name == site_in.name).first():
        raise HTTPException(status_code=400, detail="Site name already exists.")

    new_site = Site(**site_in.dict())
    db.add(new_site)
    db.commit()
    db.refresh(new_site)
    return new_site

@router.put("/{site_id}", response_model=SiteResponse)
def update_site(
    site_id: int, 
    site_in: SiteUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    """Update a site (Editor/Admin)."""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    for k, v in site_in.dict(exclude_unset=True).items():
        setattr(site, k, v)

    db.add(site)
    db.commit()
    db.refresh(site)
    return site

@router.delete("/{site_id}")
def delete_site(
    site_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    """Delete a site (Admin only)."""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    linked_devices = db.query(Device).filter(Device.site_id == site_id).count()
    if linked_devices > 0:
        raise HTTPException(status_code=400, detail=f"Cannot delete site. {linked_devices} devices are linked.")

    db.delete(site)
    db.commit()
    return {"message": "Site deleted successfully"}

# --------------------------------------------------------------------------
# [API] 장비 할당 및 조회
# --------------------------------------------------------------------------

@router.get("/unassigned/devices")
def get_unassigned_devices(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """Get devices not assigned to any site."""
    return db.query(Device).filter(Device.site_id == None).all()

@router.get("/{site_id}/devices")
def get_site_devices(
    site_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """Get devices assigned to a specific site."""
    return db.query(Device).filter(Device.site_id == site_id).all()

@router.post("/{site_id}/devices")
def assign_devices_to_site(
    site_id: int,
    req: AssignDevicesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    """Assign devices to a site (Editor/Admin)."""
    site = db.query(Site).filter(Site.id == site_id).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    db.query(Device).filter(Device.id.in_(req.device_ids)).update(
        {"site_id": site_id},
        synchronize_session=False
    )
    db.commit()
    return {"message": "Devices assigned successfully"}

# --------------------------------------------------------------------------
# [API] 사이트 정책 (VLAN Policy)
# --------------------------------------------------------------------------

@router.get("/{site_id}/vlans")
def get_site_vlans(
    site_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """Get VLANs defined for a site."""
    return db.query(SiteVlan).filter(SiteVlan.site_id == site_id).all()

@router.post("/{site_id}/vlans")
def create_site_vlan(
    site_id: int, 
    vlan: SiteVlanCreate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    """Create a VLAN for a site (Editor/Admin)."""
    new_vlan = SiteVlan(site_id=site_id, **vlan.dict())
    db.add(new_vlan)
    db.commit()
    return new_vlan

# --------------------------------------------------------------------------
# [API] 규정 준수 (Compliance)
# --------------------------------------------------------------------------

@router.post("/compliance/check")
def run_compliance_check(
    req: ComplianceCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator)
):
    """Run compliance check (Editor/Admin)."""
    engine = ComplianceEngine(db)
    result = engine.check_compliance(req.device_id, req.template_content)
    return result

@router.get("/compliance/{device_id}")
def get_compliance_report(
    device_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """Get compliance report for a device."""
    report = db.query(ComplianceReport).filter(ComplianceReport.device_id == device_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report