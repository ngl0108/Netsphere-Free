from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
import shutil
import os
import hashlib
from datetime import datetime

from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.device import FirmwareImage
from app.schemas.device import FirmwareImageResponse

router = APIRouter()

UPLOAD_DIR = "firmware_storage"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.get("", response_model=List[FirmwareImageResponse])
def get_images(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """List all available firmware images."""
    return db.query(FirmwareImage).all()

@router.post("", response_model=FirmwareImageResponse)
def upload_image(
    version: str = Form(...),
    device_family: str = Form(...),
    is_golden: bool = Form(False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    """Upload a new firmware image (Editor/Admin)."""
    file_location = os.path.join(UPLOAD_DIR, file.filename)
    
    if os.path.exists(file_location):
        raise HTTPException(status_code=400, detail="File already exists")

    try:
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    file_size = os.path.getsize(file_location)
    md5_hash = hashlib.md5()
    with open(file_location, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            md5_hash.update(byte_block)
    checksum = md5_hash.hexdigest()

    new_image = FirmwareImage(
        version=version,
        filename=file.filename,
        device_family=device_family,
        md5_checksum=checksum,
        size_bytes=file_size,
        release_date=datetime.now(),
        is_golden=is_golden,
        supported_models=[]
    )
    db.add(new_image)
    db.commit()
    db.refresh(new_image)
    
    return new_image

@router.delete("/{image_id}")
def delete_image(
    image_id: int, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    """Delete a firmware image (Admin only)."""
    image = db.query(FirmwareImage).filter(FirmwareImage.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    
    file_path = os.path.join(UPLOAD_DIR, image.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        
    db.delete(image)
    db.commit()
    
    return {"message": "Image deleted"}


# ================================================================
# SWIM Deployment Endpoints
# ================================================================

from fastapi import BackgroundTasks
from app.schemas.device import ImageDeployRequest, UpgradeJobResponse
from app.services.image_upgrade_service import ImageUpgradeService
from app.models.image_job import UpgradeJob
from app.db.session import SessionLocal

def run_upgrade_job_task(job_id: int):
    """
    Background Task Wrapper:
    Creates a new DB session for the long-running upgrade process.
    """
    db = SessionLocal()
    try:
        service = ImageUpgradeService(db)
        service.process_job(job_id)
    finally:
        db.close()

@router.post("/{image_id}/deploy", response_model=List[UpgradeJobResponse])
def deploy_image(
    image_id: int,
    request: ImageDeployRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    """
    Deploy firmware to multiple devices.
    Creates background jobs for each device.
    """
    # Verify image exists
    image = db.query(FirmwareImage).filter(FirmwareImage.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    service = ImageUpgradeService(db)
    jobs = service.create_jobs(image_id, request.device_ids)
    
    # Launch background tasks
    for job in jobs:
        background_tasks.add_task(run_upgrade_job_task, job.id)
        
    return jobs

@router.get("/jobs", response_model=List[UpgradeJobResponse])
def get_upgrade_jobs(
    device_id: int = None,
    image_id: int = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """List upgrade jobs with optional filtering."""
    query = db.query(UpgradeJob)
    if device_id:
        query = query.filter(UpgradeJob.device_id == device_id)
    if image_id:
        query = query.filter(UpgradeJob.image_id == image_id)
    
    return query.order_by(UpgradeJob.created_at.desc()).all()
