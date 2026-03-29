from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.services.support_bundle_service import SupportBundleService
import io


router = APIRouter()


@router.get("/bundle")
def download_support_bundle(
    days: int = 7,
    limit_per_table: int = 5000,
    include_app_log: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    data = SupportBundleService.build_zip(
        db,
        days=days,
        limit_per_table=limit_per_table,
        include_app_log=include_app_log,
    )
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"support_bundle_{ts}.zip"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/restore")
async def restore_support_bundle(
    bundle: UploadFile = File(...),
    apply: bool = Form(True),
    restore_settings: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    _ = current_user
    if not bundle:
        raise HTTPException(status_code=400, detail="bundle file is required")

    content = await bundle.read()
    try:
        return SupportBundleService.restore_from_zip(
            db,
            data=content,
            apply=bool(apply),
            restore_settings=bool(restore_settings),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
