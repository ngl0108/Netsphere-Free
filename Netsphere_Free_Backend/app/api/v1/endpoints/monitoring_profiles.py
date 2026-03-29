from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.device import Device
from app.models.monitoring_profile import MonitoringProfile
from app.models.user import User
from app.schemas.monitoring_profile import (
    MonitoringProfileAssignmentRequest,
    MonitoringProfileCatalogResponse,
    MonitoringProfileRecommendationResponse,
    MonitoringProfileResponse,
    MonitoringProfileCreate,
    MonitoringProfileUpdate,
)
from app.services.monitoring_profile_service import MonitoringProfileService
from app.services.source_of_truth_service import SourceOfTruthService

router = APIRouter()


@router.get("/", response_model=list[MonitoringProfileResponse])
def list_monitoring_profiles(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    catalog = MonitoringProfileService.build_catalog(db)
    return catalog["profiles"]


@router.get("/catalog", response_model=MonitoringProfileCatalogResponse)
def get_monitoring_profile_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    return MonitoringProfileService.build_catalog(db)


@router.post("/", response_model=MonitoringProfileResponse)
def create_monitoring_profile(
    payload: MonitoringProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin),
):
    try:
        row = MonitoringProfileService.create_profile(db, payload.model_dump())
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Monitoring profile key or name already exists")
    catalog = MonitoringProfileService.build_catalog(db)
    created = next((item for item in catalog["profiles"] if int(item["id"]) == int(row.id)), None)
    return created or row


@router.put("/{profile_id}", response_model=MonitoringProfileResponse)
def update_monitoring_profile(
    profile_id: int,
    payload: MonitoringProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin),
):
    profile = MonitoringProfileService.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Monitoring profile not found")
    changes = {key: value for key, value in payload.model_dump().items() if value is not None}
    try:
        row = MonitoringProfileService.update_profile(db, profile, changes)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Monitoring profile key or name already exists")
    catalog = MonitoringProfileService.build_catalog(db)
    updated = next((item for item in catalog["profiles"] if int(item["id"]) == int(row.id)), None)
    return updated or row


@router.delete("/{profile_id}")
def delete_monitoring_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin),
):
    profile = MonitoringProfileService.get_profile(db, profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Monitoring profile not found")
    MonitoringProfileService.delete_profile(db, profile)
    return {"message": "Monitoring profile deleted"}


@router.get("/devices/{device_id}/recommendation", response_model=MonitoringProfileRecommendationResponse)
def get_device_monitoring_profile_recommendation(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    device = db.query(Device).filter(Device.id == int(device_id)).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    summary = MonitoringProfileService.build_device_summary(db, device)
    return {"device_id": int(device.id), "recommendation": summary}


@router.post("/devices/{device_id}/assign", response_model=MonitoringProfileRecommendationResponse)
def assign_monitoring_profile_to_device(
    device_id: int,
    payload: MonitoringProfileAssignmentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    device = db.query(Device).filter(Device.id == int(device_id)).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    profile = MonitoringProfileService.get_profile(db, int(payload.profile_id))
    if profile is None:
        raise HTTPException(status_code=404, detail="Monitoring profile not found")
    MonitoringProfileService.assign_profile(db, device=device, profile=profile)
    SourceOfTruthService.record_event(
        db,
        asset_kind="device",
        asset_key=f"device:{int(device.id)}",
        asset_name=str(device.name or ""),
        action="profile_assigned",
        summary=f"Monitoring profile '{profile.name}' was assigned to device '{device.name}'.",
        actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
        actor_role=str(current_user.role or "").strip() or None,
        details={"device_id": int(device.id), "profile_id": int(profile.id), "profile_key": str(profile.key or "")},
    )
    return {"device_id": int(device.id), "recommendation": MonitoringProfileService.build_device_summary(db, device)}


@router.post("/devices/{device_id}/recompute", response_model=MonitoringProfileRecommendationResponse)
def recompute_monitoring_profile_for_device(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    device = db.query(Device).filter(Device.id == int(device_id)).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    before = MonitoringProfileService.build_device_summary(db, device)
    MonitoringProfileService.ensure_assignment(db, device, commit=True)
    after = MonitoringProfileService.build_device_summary(db, device)
    if after is not None and (
        before is None
        or int(after.profile_id) != int(before.profile_id)
        or str(after.assignment_source or "") != str(before.assignment_source or "")
    ):
        SourceOfTruthService.record_event(
            db,
            asset_kind="device",
            asset_key=f"device:{int(device.id)}",
            asset_name=str(device.name or ""),
            action="profile_recomputed",
            summary=f"Monitoring profile recommendation changed for device '{device.name}'.",
            actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
            actor_role=str(current_user.role or "").strip() or None,
            details={
                "device_id": int(device.id),
                "previous_profile_key": str(before.key or "") if before else None,
                "new_profile_key": str(after.key or ""),
                "assignment_source": str(after.assignment_source or ""),
            },
        )
    return {"device_id": int(device.id), "recommendation": after}
