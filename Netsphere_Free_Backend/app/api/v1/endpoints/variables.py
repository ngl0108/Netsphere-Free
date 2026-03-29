from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Literal, Dict, Any
from pydantic import BaseModel
from app.db.session import get_db
from app.models.device import Site, Device
from app.api import deps
from app.models.user import User
from app.services.variable_context_service import resolve_device_context, upsert_setting_json

router = APIRouter()

class VariableUpdate(BaseModel):
    variables: Dict[str, Any]

@router.put("/{target_type}/{target_id}")
def update_variables(
    target_type: Literal["site", "device"],
    target_id: int,
    var_in: VariableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    if target_type == "site":
        item = db.query(Site).filter(Site.id == target_id).first()
    else:
        item = db.query(Device).filter(Device.id == target_id).first()

    if not item:
        raise HTTPException(404, detail="Target not found")

    item.variables = var_in.variables
    # SQLAlchemy JSON 변경 감지 강제
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(item, "variables")

    db.commit()
    return {"status": "success", "variables": item.variables}


@router.put("/global")
def update_global_variables(
    var_in: VariableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin),
):
    upsert_setting_json(db, "vars_global", var_in.variables, description="Global template variables", category="variables")
    return {"status": "success", "variables": var_in.variables}


@router.put("/role/{role_key}")
def update_role_variables(
    role_key: str,
    var_in: VariableUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_admin),
):
    key = f"vars_role_{str(role_key or '').strip()}"
    upsert_setting_json(db, key, var_in.variables, description=f"Role variables for {role_key}", category="variables")
    return {"status": "success", "role": role_key, "variables": var_in.variables}


@router.get("/context/device/{device_id}")
def get_device_context(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    dev = db.query(Device).filter(Device.id == device_id).first()
    if not dev:
        raise HTTPException(404, detail="Device not found")
    ctx = resolve_device_context(db, dev)
    return {"variables": ctx.merged, "sources": ctx.sources}
