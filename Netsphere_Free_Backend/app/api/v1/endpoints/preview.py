from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.device import Device
from app.models.user import User
from app.services.preview_edition_service import PreviewEditionService


router = APIRouter()


class PreviewEntryInput(BaseModel):
    command: str
    raw_output: str = ""
    sanitized_output: str = ""
    model_config = ConfigDict(extra="ignore")


class PreviewSanitizeRequest(BaseModel):
    entries: List[PreviewEntryInput] = Field(default_factory=list)
    host_candidates: List[str] = Field(default_factory=list)


class PreviewCaptureRequest(BaseModel):
    commands: List[str] = Field(default_factory=list)


class PreviewContributionRequest(BaseModel):
    device_id: Optional[int] = None
    source: str = "manual"
    consent_confirmed: bool = False
    notes: str = ""
    device_context: Dict[str, Any] = Field(default_factory=dict)
    collector_context: Dict[str, Any] = Field(default_factory=dict)
    entries: List[PreviewEntryInput] = Field(default_factory=list)


class PreviewContributionConsentRequest(BaseModel):
    enabled: bool = False
    source: str = "manual"


class PreviewIntakeRegistrationCreateRequest(BaseModel):
    label: str
    issued_to: str = ""
    notes: str = ""


class PreviewIntakeRegistrationRotateRequest(BaseModel):
    notes: str = ""


class PreviewIntakeSelfEnrollRequest(BaseModel):
    installation_id: str
    requested_label: str = ""
    source: str = "collector_auto_enroll"
    consent_confirmed: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


@router.get("/policy")
def get_preview_policy(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return PreviewEditionService.get_policy(db)


@router.post("/sanitize")
def sanitize_preview_entries(
    request: PreviewSanitizeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    policy = PreviewEditionService.get_policy(db)
    try:
        commands = PreviewEditionService.ensure_commands_allowed(
            [entry.command for entry in request.entries],
            db=db,
            policy=policy,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    entries = []
    for idx, command in enumerate(commands):
        raw = request.entries[idx].raw_output if idx < len(request.entries) else ""
        entries.append(
            PreviewEditionService.sanitize_output(
                command=command,
                raw_output=raw,
                host_candidates=request.host_candidates,
            )
        )
    return {
        "policy": policy,
        "entries": entries,
    }


@router.post("/consent/contribution")
def update_preview_contribution_consent(
    request: PreviewContributionConsentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    try:
        return PreviewEditionService.set_upload_participation(
            db,
            user=current_user,
            enabled=request.enabled,
            source=request.source,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/devices/{device_id}/capture")
def capture_preview_device_outputs(
    device_id: int,
    request: PreviewCaptureRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    try:
        return PreviewEditionService.capture_device_outputs(
            db,
            device=device,
            commands=request.commands,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ConnectionError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/contributions")
def upload_preview_contribution(
    request: PreviewContributionRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):
    current_user: User | None = None
    collector_registration = None
    collector_id = str(http_request.headers.get("X-Preview-Collector-Id") or "").strip()
    intake_token = str(http_request.headers.get("X-Preview-Intake-Token") or "").strip()
    if intake_token:
        collector_registration = PreviewEditionService.authenticate_intake_registration(
            db,
            collector_id=collector_id,
            token=intake_token,
        )
        if collector_registration is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid preview intake credentials")
    else:
        auth_header = str(http_request.headers.get("authorization") or "").strip()
        if not auth_header.lower().startswith("bearer "):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        current_user = deps.get_current_user(
            request=http_request,
            db=db,
            token=auth_header.split(" ", 1)[1].strip(),
        )

    device = None
    if request.device_id is not None:
        device = db.query(Device).filter(Device.id == request.device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
    collector_context = dict(request.collector_context or {})
    if collector_registration is not None:
        collector_context["collector_id"] = str(collector_registration.collector_id or "")
        collector_context["registration_label"] = str(collector_registration.label or "")
    try:
        result = PreviewEditionService.persist_contribution(
            db,
            user=current_user,
            device=device,
            source=request.source,
            entries=[entry.model_dump() for entry in request.entries],
            notes=request.notes,
            consent_confirmed=request.consent_confirmed,
            device_context_override=request.device_context,
            collector_context=collector_context,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PreviewEditionService.RemoteUploadError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return result


@router.get("/contributions/recent")
def list_recent_preview_contributions(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin),
):
    return {
        "items": PreviewEditionService.list_recent_contributions(db, limit=limit),
    }


@router.get("/contributions/{contribution_id}")
def get_preview_contribution_record(
    contribution_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin),
):
    payload = PreviewEditionService.get_contribution_record(db, contribution_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Contribution record not found")
    return payload


@router.get("/intake-registrations")
def list_preview_intake_registrations(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    if not PreviewEditionService.is_preview_enabled(db):
        raise HTTPException(status_code=403, detail="Preview edition is not enabled")
    return {"items": PreviewEditionService.list_intake_registrations(db)}


@router.post("/intake-registrations")
def create_preview_intake_registration(
    request: PreviewIntakeRegistrationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    if not PreviewEditionService.is_preview_enabled(db):
        raise HTTPException(status_code=403, detail="Preview edition is not enabled")
    try:
        return PreviewEditionService.create_intake_registration(
            db,
            label=request.label,
            issued_to=request.issued_to,
            notes=request.notes,
            created_by=str(getattr(current_user, "username", "") or "").strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/intake-registrations/{collector_id}/rotate")
def rotate_preview_intake_registration(
    collector_id: str,
    request: PreviewIntakeRegistrationRotateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    if not PreviewEditionService.is_preview_enabled(db):
        raise HTTPException(status_code=403, detail="Preview edition is not enabled")
    try:
        return PreviewEditionService.rotate_intake_registration(
            db,
            collector_id=collector_id,
            notes=request.notes,
            rotated_by=str(getattr(current_user, "username", "") or "").strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/intake-registrations/{collector_id}/revoke")
def revoke_preview_intake_registration(
    collector_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    if not PreviewEditionService.is_preview_enabled(db):
        raise HTTPException(status_code=403, detail="Preview edition is not enabled")
    try:
        return PreviewEditionService.revoke_intake_registration(db, collector_id=collector_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/intake-enroll")
def self_enroll_preview_intake_registration(
    request: PreviewIntakeSelfEnrollRequest,
    db: Session = Depends(get_db),
):
    if not request.consent_confirmed:
        raise HTTPException(status_code=400, detail="Contribution consent is required for preview self-registration.")
    try:
        return PreviewEditionService.self_enroll_intake_registration(
            db,
            installation_id=request.installation_id,
            requested_label=request.requested_label,
            source=request.source,
            metadata=request.metadata,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
