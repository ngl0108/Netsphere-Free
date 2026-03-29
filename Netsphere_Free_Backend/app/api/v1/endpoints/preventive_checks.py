import io
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.preventive_check import PreventiveCheckTemplate
from app.models.user import User
from app.services.preventive_check_service import PreventiveCheckService

router = APIRouter()


class PreventiveCheckTemplateBase(BaseModel):
    name: str
    description: Optional[str] = None
    target_scope: dict[str, Any] = Field(default_factory=dict)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    schedule: dict[str, Any] = Field(default_factory=dict)
    is_enabled: bool = True


class PreventiveCheckTemplateCreate(PreventiveCheckTemplateBase):
    pass


class PreventiveCheckTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    target_scope: Optional[dict[str, Any]] = None
    checks: Optional[list[dict[str, Any]]] = None
    schedule: Optional[dict[str, Any]] = None
    is_enabled: Optional[bool] = None


class PreventiveCheckTemplateResponse(PreventiveCheckTemplateBase):
    id: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    next_run_at: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class PreventiveCheckRunResponse(BaseModel):
    id: int
    template_id: int
    template_name: str = ""
    status: str
    execution_mode: str = "manual"
    triggered_by: str = ""
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    summary: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)


def _serialize_run_or_404(db: Session, run_id: int) -> dict[str, Any]:
    run = PreventiveCheckService.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Preventive check run not found")
    return PreventiveCheckService.serialize_run(run)


@router.get("/summary")
def get_preventive_check_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    return PreventiveCheckService.build_summary(db)


@router.get("/templates", response_model=list[PreventiveCheckTemplateResponse])
def list_preventive_check_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    return PreventiveCheckService.list_templates(db)


@router.post("/templates", response_model=PreventiveCheckTemplateResponse)
def create_preventive_check_template(
    payload: PreventiveCheckTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    try:
        return PreventiveCheckService.save_template(db, template=None, payload=payload.model_dump())
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Preventive check template name already exists")


@router.put("/templates/{template_id}", response_model=PreventiveCheckTemplateResponse)
def update_preventive_check_template(
    template_id: int,
    payload: PreventiveCheckTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    template = PreventiveCheckService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Preventive check template not found")
    merged = {
        "name": payload.name if payload.name is not None else template.name,
        "description": payload.description if payload.description is not None else template.description,
        "target_scope": payload.target_scope if payload.target_scope is not None else template.target_scope,
        "checks": payload.checks if payload.checks is not None else template.checks,
        "schedule": payload.schedule if payload.schedule is not None else template.schedule,
        "is_enabled": payload.is_enabled if payload.is_enabled is not None else template.is_enabled,
    }
    try:
        return PreventiveCheckService.save_template(db, template=template, payload=merged)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Preventive check template name already exists")


@router.delete("/templates/{template_id}")
def delete_preventive_check_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    try:
        PreventiveCheckService.delete_template(db, template_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Preventive check template not found")
    return {"message": "Preventive check template deleted"}


@router.get("/runs", response_model=list[PreventiveCheckRunResponse])
def list_preventive_check_runs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    return PreventiveCheckService.list_runs(db, limit=limit)


@router.get("/runs/{run_id}", response_model=PreventiveCheckRunResponse)
def get_preventive_check_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    return _serialize_run_or_404(db, run_id)


@router.post("/templates/{template_id}/run", response_model=PreventiveCheckRunResponse)
def run_preventive_check_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    template = PreventiveCheckService.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Preventive check template not found")
    return PreventiveCheckService.run_template(
        db,
        template=template,
        triggered_by=str(getattr(current_user, "username", "") or "operator"),
        execution_mode="manual",
    )


@router.get("/runs/{run_id}/export")
def export_preventive_check_run(
    run_id: int,
    format: str = Query(default="csv"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    normalized = str(format or "").strip().lower()
    run = PreventiveCheckService.get_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Preventive check run not found")
    body: bytes
    if normalized == "csv":
        body = PreventiveCheckService.export_run_csv(run).encode("utf-8")
        filename = f"preventive_check_run_{run_id}.csv"
        media_type = "text/csv; charset=utf-8"
    elif normalized in {"md", "markdown"}:
        body = PreventiveCheckService.export_run_markdown(run).encode("utf-8")
        filename = f"preventive_check_run_{run_id}.md"
        media_type = "text/markdown; charset=utf-8"
    elif normalized == "json":
        body = PreventiveCheckService.export_run_json(run).encode("utf-8")
        filename = f"preventive_check_run_{run_id}.json"
        media_type = "application/json; charset=utf-8"
    elif normalized == "pdf":
        body = PreventiveCheckService.export_run_pdf(run)
        filename = f"preventive_check_run_{run_id}.pdf"
        media_type = "application/pdf"
    else:
        raise HTTPException(status_code=400, detail="Supported export formats: csv, md, json, pdf")
    return StreamingResponse(
        io.BytesIO(body),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
