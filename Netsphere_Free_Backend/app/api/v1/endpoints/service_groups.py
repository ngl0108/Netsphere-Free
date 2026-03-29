from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.cloud import CloudResource
from app.models.device import Device
from app.models.service_group import ServiceGroup
from app.models.user import User
from app.schemas.service_group import (
    ServiceGroupCatalogResponse,
    ServiceGroupCreate,
    ServiceGroupDetailResponse,
    ServiceGroupResponse,
    ServiceGroupUpdate,
)
from app.services.service_group_service import ServiceGroupService
from app.services.source_of_truth_service import SourceOfTruthService

router = APIRouter()


@router.get("/", response_model=list[ServiceGroupResponse])
def list_service_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    rows = ServiceGroupService.list_groups(db)
    health_map = ServiceGroupService.build_group_health_map(db, rows)
    return [ServiceGroupService.serialize_group_summary(row, health=health_map.get(int(row.id))) for row in rows]


@router.get("/catalog", response_model=ServiceGroupCatalogResponse)
def get_service_group_catalog(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    return ServiceGroupService.build_catalog(db)


@router.get("/{group_id}", response_model=ServiceGroupDetailResponse)
def get_service_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    row = ServiceGroupService.get_group(db, group_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Service group not found")
    health_map = ServiceGroupService.build_group_health_map(db, [row])
    return ServiceGroupService.serialize_group_detail(row, health=health_map.get(int(row.id)))


@router.post("/", response_model=ServiceGroupDetailResponse)
def create_service_group(
    payload: ServiceGroupCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    try:
        group = ServiceGroupService.create_group(db, payload.model_dump())
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Service group name already exists")
    SourceOfTruthService.record_event(
        db,
        asset_kind="service_group",
        asset_key=f"group:{int(group.id)}",
        asset_name=str(group.name or ""),
        action="created",
        summary=f"Service group '{group.name}' was created.",
        actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
        actor_role=str(current_user.role or "").strip() or None,
        details={"group_id": int(group.id), "criticality": str(group.criticality or "standard")},
    )
    health_map = ServiceGroupService.build_group_health_map(db, [group])
    return ServiceGroupService.serialize_group_detail(group, health=health_map.get(int(group.id)))


@router.put("/{group_id}", response_model=ServiceGroupDetailResponse)
def update_service_group(
    group_id: int,
    payload: ServiceGroupUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    group = ServiceGroupService.get_group(db, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Service group not found")
    before_name = str(group.name or "")
    changes = {key: value for key, value in payload.model_dump().items() if value is not None}
    try:
        updated = ServiceGroupService.update_group(db, group, changes)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Service group name already exists")
    if changes:
        SourceOfTruthService.record_event(
            db,
            asset_kind="service_group",
            asset_key=f"group:{int(updated.id)}",
            asset_name=str(updated.name or ""),
            action="updated",
            summary=f"Service group '{before_name}' was updated.",
            actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
            actor_role=str(current_user.role or "").strip() or None,
            details={"group_id": int(updated.id), "changed_fields": sorted(changes.keys())},
        )
    health_map = ServiceGroupService.build_group_health_map(db, [updated])
    return ServiceGroupService.serialize_group_detail(updated, health=health_map.get(int(updated.id)))


@router.delete("/{group_id}")
def delete_service_group(
    group_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    group = ServiceGroupService.get_group(db, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Service group not found")
    group_name = str(group.name or "")
    ServiceGroupService.delete_group(db, group)
    SourceOfTruthService.record_event(
        db,
        asset_kind="service_group",
        asset_key=f"group:{int(group_id)}",
        asset_name=group_name,
        action="deleted",
        summary=f"Service group '{group_name}' was deleted.",
        actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
        actor_role=str(current_user.role or "").strip() or None,
        details={"group_id": int(group_id)},
    )
    return {"message": "Service group deleted"}


@router.post("/{group_id}/members/device/{device_id}", response_model=ServiceGroupDetailResponse)
def add_device_to_service_group(
    group_id: int,
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    group = ServiceGroupService.get_group(db, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Service group not found")
    device = db.query(Device).filter(Device.id == device_id).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    updated = ServiceGroupService.add_device_member(db, group=group, device=device)
    SourceOfTruthService.record_event(
        db,
        asset_kind="service_group",
        asset_key=f"group:{int(group.id)}",
        asset_name=str(group.name or ""),
        action="member_added",
        summary=f"Device '{device.name}' was added to service group '{group.name}'.",
        actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
        actor_role=str(current_user.role or "").strip() or None,
        details={"group_id": int(group.id), "device_id": int(device.id), "member_type": "device"},
    )
    health_map = ServiceGroupService.build_group_health_map(db, [updated])
    return ServiceGroupService.serialize_group_detail(updated, health=health_map.get(int(updated.id)))


@router.post("/{group_id}/members/cloud/{cloud_resource_id}", response_model=ServiceGroupDetailResponse)
def add_cloud_resource_to_service_group(
    group_id: int,
    cloud_resource_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    group = ServiceGroupService.get_group(db, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Service group not found")
    cloud_resource = db.query(CloudResource).filter(CloudResource.id == cloud_resource_id).first()
    if cloud_resource is None:
        raise HTTPException(status_code=404, detail="Cloud resource not found")
    updated = ServiceGroupService.add_cloud_resource_member(db, group=group, cloud_resource=cloud_resource)
    resource_name = str(cloud_resource.name or cloud_resource.resource_id or "Cloud Resource")
    SourceOfTruthService.record_event(
        db,
        asset_kind="service_group",
        asset_key=f"group:{int(group.id)}",
        asset_name=str(group.name or ""),
        action="member_added",
        summary=f"Cloud resource '{resource_name}' was added to service group '{group.name}'.",
        actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
        actor_role=str(current_user.role or "").strip() or None,
        details={"group_id": int(group.id), "cloud_resource_id": int(cloud_resource.id), "member_type": "cloud_resource"},
    )
    health_map = ServiceGroupService.build_group_health_map(db, [updated])
    return ServiceGroupService.serialize_group_detail(updated, health=health_map.get(int(updated.id)))


@router.delete("/{group_id}/members/{member_id}", response_model=ServiceGroupDetailResponse)
def remove_service_group_member(
    group_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    group = ServiceGroupService.get_group(db, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Service group not found")
    existing = next((row for row in list(group.members or []) if int(row.id) == int(member_id)), None)
    try:
        updated = ServiceGroupService.remove_member(db, group=group, member_id=member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Service group member not found")
    if existing is not None:
        member_type = str(existing.member_type or "").strip().lower()
        removed_name = None
        if member_type == "device" and existing.device is not None:
            removed_name = str(existing.device.name or "")
        elif member_type == "cloud_resource" and existing.cloud_resource is not None:
            removed_name = str(existing.cloud_resource.name or existing.cloud_resource.resource_id or "")
        SourceOfTruthService.record_event(
            db,
            asset_kind="service_group",
            asset_key=f"group:{int(group.id)}",
            asset_name=str(group.name or ""),
            action="member_removed",
            summary=f"Member '{removed_name or member_type}' was removed from service group '{group.name}'.",
            actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
            actor_role=str(current_user.role or "").strip() or None,
            details={"group_id": int(group.id), "member_id": int(member_id), "member_type": member_type or None},
        )
    health_map = ServiceGroupService.build_group_health_map(db, [updated])
    return ServiceGroupService.serialize_group_detail(updated, health=health_map.get(int(updated.id)))
