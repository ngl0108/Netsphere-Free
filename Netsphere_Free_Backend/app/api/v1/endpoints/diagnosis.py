import ipaddress
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.device import Device
from app.models.user import User
from app.services.diagnosis_service import OneClickDiagnosisOptions, OneClickDiagnosisService
from app.services.preview_managed_node_service import PreviewManagedNodeService

router = APIRouter()


class OneClickDiagnosisRequest(BaseModel):
    src_ip: str
    dst_ip: str
    include_show_commands: bool = True


@router.post("/one-click")
def one_click_diagnosis(
    req: OneClickDiagnosisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
) -> Dict[str, Any]:
    try:
        ipaddress.ip_address(req.src_ip)
    except ValueError:
        raise HTTPException(status_code=422, detail={"message": "Invalid src_ip", "field": "src_ip"})
    try:
        ipaddress.ip_address(req.dst_ip)
    except ValueError:
        raise HTTPException(status_code=422, detail={"message": "Invalid dst_ip", "field": "dst_ip"})

    if PreviewManagedNodeService.is_preview_managed_quota_enabled(db):
        candidate_devices = (
            db.query(Device)
            .filter(Device.ip_address.in_([req.src_ip, req.dst_ip]))
            .all()
        )
        for device in candidate_devices:
            try:
                PreviewManagedNodeService.assert_managed_for_feature(db, device, feature="diagnosis")
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=exc.args[0] if exc.args else {"message": "Managed node required"})

    service = OneClickDiagnosisService(db)
    options = OneClickDiagnosisOptions(include_show_commands=bool(req.include_show_commands))
    result = service.run(req.src_ip, req.dst_ip, options=options)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail={"message": str(result.get("error")), "result": result})
    return result
