import difflib
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from app.db.session import get_db
from app.models.device import ConfigBackup
from app.api import deps
from app.models.user import User

router = APIRouter()


class ConfigBackupResponse(BaseModel):
    id: int
    raw_config: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("/history/{device_id}", response_model=List[ConfigBackupResponse])
def get_config_history(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return db.query(ConfigBackup).filter(ConfigBackup.device_id == device_id).order_by(
        ConfigBackup.created_at.desc()).all()


@router.get("/diff/{backup_id_a}/{backup_id_b}")
def compare_backups(
    backup_id_a: int,
    backup_id_b: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    b_a = db.query(ConfigBackup).filter(ConfigBackup.id == backup_id_a).first()
    b_b = db.query(ConfigBackup).filter(ConfigBackup.id == backup_id_b).first()

    if not b_a or not b_b: raise HTTPException(404, "Backup not found")

    diff = difflib.unified_diff(
        b_a.raw_config.splitlines(),
        b_b.raw_config.splitlines(),
        fromfile=f"Ver {b_a.id}", tofile=f"Ver {b_b.id}", lineterm=""
    )
    return {"diff_lines": list(diff)}
