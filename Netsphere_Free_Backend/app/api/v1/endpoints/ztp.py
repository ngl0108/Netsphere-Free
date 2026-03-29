from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from typing import Dict, Any, Optional, List
import os
import logging
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.ztp_queue import ZtpQueue, ZtpStatus
from app.models.device import Device, Link, Site, ConfigTemplate, ConfigBackup
from app.schemas.ztp import (
    ZtpRegisterRequest,
    ZtpApproveRequest,
    ZtpStageRequest,
    ZtpQueueResponse,
    ZtpStatsResponse,
)
from datetime import datetime, timezone, timedelta
from app.services.audit_service import AuditService
from app.services.ztp_service import ZtpService
from app.services.device_support_policy_service import DeviceSupportPolicyService
from app.api import deps
from app.models.user import User

router = APIRouter()
logger = logging.getLogger(__name__)


def _serialize_queue_item(item: ZtpQueue) -> Dict[str, Any]:
    return {
        "id": item.id,
        "serial_number": item.serial_number,
        "platform": item.platform,
        "software_version": item.software_version,
        "ip_address": item.ip_address,
        "hostname": item.hostname,
        "status": item.status,
        "device_type": item.device_type,
        "assigned_site_id": item.assigned_site_id,
        "assigned_site_name": item.assigned_site.name if item.assigned_site else None,
        "assigned_template_id": item.assigned_template_id,
        "assigned_template_name": item.assigned_template.name if item.assigned_template else None,
        "target_hostname": item.target_hostname,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
        "provisioned_at": item.provisioned_at,
        "last_message": item.last_message,
        "detected_uplink_name": item.detected_uplink_name,
        "detected_uplink_port": item.detected_uplink_port,
        "suggested_device_id": item.suggested_device_id,
        "suggestion_reason": item.suggestion_reason,
    }


def _has_device_backup(db: Session, device_id: int) -> bool:
    row = (
        db.query(ConfigBackup.id)
        .filter(ConfigBackup.device_id == int(device_id))
        .order_by(ConfigBackup.created_at.desc(), ConfigBackup.id.desc())
        .first()
    )
    return bool(row)


def _pick_auto_template(db: Session, candidate_dev: Device) -> Optional[ConfigTemplate]:
    hints = [
        str(getattr(candidate_dev, "device_type", "") or "").strip(),
        str(getattr(candidate_dev, "role", "") or "").strip(),
        str(getattr(candidate_dev, "model", "") or "").strip(),
    ]
    for hint in hints:
        if not hint:
            continue
        tpl = (
            db.query(ConfigTemplate)
            .filter(
                or_(
                    ConfigTemplate.name.ilike(f"%{hint}%"),
                    ConfigTemplate.category.ilike(f"%{hint}%"),
                )
            )
            .order_by(ConfigTemplate.last_updated.desc(), ConfigTemplate.id.desc())
            .first()
        )
        if tpl:
            return tpl

    total_templates = int(db.query(ConfigTemplate).count())
    if total_templates == 1:
        return db.query(ConfigTemplate).order_by(ConfigTemplate.id.asc()).first()
    return None


@router.get("/queue", response_model=List[ZtpQueueResponse])
def list_queue(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q = db.query(ZtpQueue)
    if status:
        status_norm = str(status).strip().lower()
        q = q.filter(func.lower(ZtpQueue.status) == status_norm)
    rows = q.order_by(ZtpQueue.created_at.desc(), ZtpQueue.id.desc()).all()
    return [_serialize_queue_item(r) for r in rows]


@router.get("/stats", response_model=ZtpStatsResponse)
def get_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    now = datetime.now(timezone.utc)
    today_start = datetime(year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc)
    tomorrow_start = today_start + timedelta(days=1)
    return {
        "total_queued": int(db.query(ZtpQueue).count()),
        "pending_approval": int(db.query(ZtpQueue).filter(ZtpQueue.status == ZtpStatus.NEW.value).count()),
        "ready_to_provision": int(db.query(ZtpQueue).filter(ZtpQueue.status == ZtpStatus.READY.value).count()),
        "in_progress": int(db.query(ZtpQueue).filter(ZtpQueue.status == ZtpStatus.PROVISIONING.value).count()),
        "completed_today": int(
            db.query(ZtpQueue)
            .filter(ZtpQueue.status == ZtpStatus.COMPLETED.value)
            .filter(ZtpQueue.provisioned_at != None)  # noqa: E711
            .filter(ZtpQueue.provisioned_at >= today_start)
            .filter(ZtpQueue.provisioned_at < tomorrow_start)
            .count()
        ),
        "errors": int(db.query(ZtpQueue).filter(ZtpQueue.status == ZtpStatus.ERROR.value).count()),
    }


@router.post("/queue/stage", response_model=ZtpQueueResponse)
def stage_device(
    payload: ZtpStageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin),
):
    serial = str(payload.serial_number or "").strip()
    if not serial:
        raise HTTPException(status_code=400, detail="serial_number is required")

    site = db.query(Site).filter(Site.id == int(payload.site_id)).first()
    if not site:
        raise HTTPException(status_code=404, detail="site not found")
    template = db.query(ConfigTemplate).filter(ConfigTemplate.id == int(payload.template_id)).first()
    if not template:
        raise HTTPException(status_code=404, detail="template not found")

    q_item = db.query(ZtpQueue).filter(ZtpQueue.serial_number == serial).first()
    if not q_item:
        q_item = ZtpQueue(serial_number=serial, status=ZtpStatus.NEW.value, platform=None)
        db.add(q_item)

    q_item.assigned_site_id = int(site.id)
    q_item.assigned_template_id = int(template.id)
    q_item.target_hostname = str(payload.target_hostname or "").strip() or None
    q_item.status = ZtpStatus.READY.value
    q_item.last_message = "Staged by operator. Waiting for device registration."
    db.commit()
    db.refresh(q_item)

    AuditService.log(
        db,
        current_user,
        "CREATE",
        "ZTP",
        q_item.serial_number,
        details=f"Staged serial={q_item.serial_number} site={q_item.assigned_site_id} template={q_item.assigned_template_id}",
    )
    return _serialize_queue_item(q_item)


@router.get("/boot", response_class=PlainTextResponse)
def get_boot_script(request: Request):
    """
    Serves the Python bootstrap script (ztp_boot.py).
    Dynamically injects the Server IP/Port based on the request host.
    """
    # Host header includes port (e.g., 192.168.1.100:8000)
    host_header = request.headers.get("host", "127.0.0.1:8000")
    if ":" in host_header:
        server_ip, server_port = host_header.split(":")
    else:
        server_ip, server_port = host_header, "80"

    file_path = os.path.join("app", "templates", "ztp_boot.py")
    
    if not os.path.exists(file_path):
        return "# [Error] ztp_boot.py template not found on server."

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Inject Server Info
    content = content.replace("{{ server_ip }}", server_ip)
    content = content.replace("{{ server_port }}", server_port)
    
    return content

@router.post("/register")
def register_device(payload: ZtpRegisterRequest, db: Session = Depends(get_db)):
    """
    Receives registration request.
    Creates/Updates ZtpQueue entry.
    Matches topology for RMA suggestion.
    """
    uplink = payload.uplink_info or {}
    logger.info(
        "ZTP register request serial=%s uplink_name=%s uplink_port=%s",
        payload.serial_number,
        uplink.get("name"),
        uplink.get("port"),
    )

    # 1. ZTP Queue Entry
    queue_item = db.query(ZtpQueue).filter(ZtpQueue.serial_number == payload.serial_number).first()
    if not queue_item:
        queue_item = ZtpQueue(
            serial_number=payload.serial_number,
            status=ZtpStatus.NEW.value,
            platform=payload.model
        )
        db.add(queue_item)
    
    # Update Basic Info
    queue_item.ip_address = payload.ip_address
    queue_item.platform = payload.model
    
    # 2. RMA / Topology Matching
    uplink = payload.uplink_info
    if uplink and uplink.get('name') and uplink.get('port'):
        u_name = uplink['name']
        u_port = uplink['port']
        
        queue_item.detected_uplink_name = u_name
        queue_item.detected_uplink_port = u_port
        queue_item.detected_uplink_ip = uplink.get('ip')

        # Find Link (Topology Match)
        # Search for a Link where Target == UplinkDevice AND TargetPort == UplinkPort
        # Note: Name matching might need normalization (Gi1/0/1 vs GigabitEthernet1/0/1)
        # For now, using naive like matching or exact match
        
        # Uplink Device
        uplink_dev = db.query(Device).filter(Device.name.ilike(f"%{u_name}%")).first()
        
        if uplink_dev:
            # Find the link connected to this uplink port
            # We are looking for the 'Source' device (the one that was here before)
            # Link Direction: Source(Downlink) -> Target(Uplink)
            
            # Case 1: Link is Source->Target (Downlink->Uplink)
            link = db.query(Link).filter(
                Link.target_device_id == uplink_dev.id,
                Link.target_interface_name.ilike(f"%{u_port}%")
            ).first()
            
            candidate_dev = link.source_device if link else None
            
            if candidate_dev:
                logger.info("ZTP RMA candidate found device=%s status=%s", candidate_dev.name, candidate_dev.status)
                
                # Check if authorized for auto-replacement
                if candidate_dev.status == 'replace_pending':
                    queue_item.suggested_device_id = candidate_dev.id
                    queue_item.assigned_site_id = candidate_dev.site_id
                    queue_item.target_hostname = candidate_dev.hostname or candidate_dev.name

                    has_backup = _has_device_backup(db, candidate_dev.id)
                    auto_template = _pick_auto_template(db, candidate_dev)

                    if has_backup:
                        queue_item.status = ZtpStatus.READY.value
                        queue_item.suggestion_reason = "Auto-Matched (Replace Pending, backup)"
                        queue_item.last_message = "Auto-assigned from replace_pending candidate using latest backup."
                    elif auto_template:
                        queue_item.assigned_template_id = int(auto_template.id)
                        queue_item.status = ZtpStatus.READY.value
                        queue_item.suggestion_reason = f"Auto-Matched (Replace Pending, template={auto_template.name})"
                        queue_item.last_message = "Auto-assigned from replace_pending candidate using matched template."
                    else:
                        queue_item.suggestion_reason = "Auto-Matched (Replace Pending, approval required)"
                        queue_item.last_message = "Matched replace_pending candidate but no backup/template found; manual approval required."
                else:
                    queue_item.suggested_device_id = candidate_dev.id
                    queue_item.suggestion_reason = f"Topology Match: Connected to {u_name} on {u_port}"
            else:
                queue_item.suggestion_reason = f"Uplink found ({u_name}), but no previous device mapped to port {u_port}"
        else:
             queue_item.suggestion_reason = f"Uplink device '{u_name}' not found in inventory"

    db.commit()
    db.refresh(queue_item)

    support = DeviceSupportPolicyService.evaluate_metadata(
        db,
        site_id=getattr(queue_item, "assigned_site_id", None),
        device_type=str(getattr(queue_item, "device_type", "") or "unknown"),
        os_version=str(getattr(queue_item, "software_version", "") or payload.model or ""),
        model=str(getattr(queue_item, "platform", "") or payload.model or ""),
        hostname=str(getattr(queue_item, "target_hostname", "") or getattr(queue_item, "hostname", "") or ""),
    )
    if not bool((support.get("features") or {}).get("ztp", False)):
        queue_item.status = ZtpStatus.NEW.value
        queue_item.last_message = (
            f"ZTP blocked by vendor support policy (tier={support.get('tier')}, "
            f"fallback={support.get('fallback_mode')}). Manual read-only onboarding only."
        )
        db.commit()
        return {
            "action": "wait",
            "status": queue_item.status,
            "message": queue_item.last_message,
        }

    # 3. Determine Response Action
    if queue_item.status in {ZtpStatus.READY.value, ZtpStatus.PROVISIONING.value} and (
        queue_item.assigned_template_id or queue_item.suggested_device_id
    ):
        cfg = ZtpService(db).generate_day0_config(queue_item)
        if cfg:
            if queue_item.status != ZtpStatus.PROVISIONING.value:
                queue_item.status = ZtpStatus.PROVISIONING.value
                queue_item.last_message = "Provisioning started"
                db.commit()
                db.refresh(queue_item)
            return {
                "action": "configure",
                "config_content": cfg,
            }
    
    return {
        "action": "wait", 
        "status": queue_item.status,
        "message": "Registered in Queue. Waiting for approval."
    }

@router.post("/queue/{item_id}/approve")
def approve_device(item_id: int, payload: ZtpApproveRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    """
    Approve a ZTP queue item. 
    Can either assign manual Site/Template OR Swap with an existing device (RMA).
    """
    q_item = db.query(ZtpQueue).filter(ZtpQueue.id == item_id).first()
    if not q_item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    # [RMA Swap Logic]
    if payload.swap_with_device_id:
        old_dev = db.query(Device).filter(Device.id == payload.swap_with_device_id).first()
        if not old_dev:
            raise HTTPException(404, "Target device for swap not found")

        support = DeviceSupportPolicyService.evaluate_device(db, old_dev)
        if not bool((support.get("features") or {}).get("ztp", False)):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DEVICE_SUPPORT_BLOCKED",
                    "message": "ZTP approval is blocked for this vendor tier.",
                    "details": {
                        "device_id": int(old_dev.id),
                        "device_type": old_dev.device_type,
                        "tier": support.get("tier"),
                        "fallback_mode": support.get("fallback_mode"),
                    },
                },
            )
        
        logger.info("ZTP swapping old_device=%s new_serial=%s", old_dev.name, q_item.serial_number)
        
        # 1. Inherit Site & Basic Info
        q_item.assigned_site_id = old_dev.site_id
        q_item.target_hostname = old_dev.name # Re-use the old hostname
        
        # 2. Config Strategy:
        # Re-use the template assigned to the old device if available.
        # This ensures the new device gets the same role-based configuration.
        if hasattr(old_dev, 'auto_provision_template_id') and old_dev.auto_provision_template_id:
            q_item.assigned_template_id = old_dev.auto_provision_template_id
        else:
            # If no specific template was assigned, we leave it empty.
            # The admin can manually assign one later, or the device will just get basic reachability.
            q_item.assigned_template_id = None
        
        # 3. Retire Old Device
        # Rename old device to avoid collision
        old_name = old_dev.name
        old_dev.name = f"{old_name}_replaced_{datetime.now().strftime('%Y%m%d%H%M')}"
        old_dev.status = "decommissioned"
        
        
    else:
        if payload.site_id is None or payload.template_id is None:
            raise HTTPException(status_code=400, detail="site_id and template_id are required")
        site = db.query(Site).filter(Site.id == int(payload.site_id)).first()
        if not site:
            raise HTTPException(status_code=404, detail="site not found")
        template = db.query(ConfigTemplate).filter(ConfigTemplate.id == int(payload.template_id)).first()
        if not template:
            raise HTTPException(status_code=404, detail="template not found")
        # Standard Approval
        q_item.assigned_site_id = int(site.id)
        q_item.assigned_template_id = int(template.id)
        q_item.target_hostname = payload.target_hostname

    support = DeviceSupportPolicyService.evaluate_metadata(
        db,
        site_id=getattr(q_item, "assigned_site_id", None),
        device_type=str(getattr(q_item, "device_type", "") or "unknown"),
        os_version=str(getattr(q_item, "software_version", "") or ""),
        model=str(getattr(q_item, "platform", "") or ""),
        hostname=str(getattr(q_item, "target_hostname", "") or getattr(q_item, "hostname", "") or ""),
    )
    if not bool((support.get("features") or {}).get("ztp", False)):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEVICE_SUPPORT_BLOCKED",
                "message": "ZTP approval is blocked for this vendor tier.",
                "details": {
                    "serial_number": q_item.serial_number,
                    "device_type": q_item.device_type,
                    "tier": support.get("tier"),
                    "fallback_mode": support.get("fallback_mode"),
                },
            },
        )

    q_item.status = ZtpStatus.READY.value
    q_item.last_message = "Approved and ready for provisioning."
    db.commit()
    
    # [Audit]
    audit_msg = f"Approved device {q_item.serial_number} as {q_item.target_hostname}"
    if payload.swap_with_device_id:
        audit_msg += " (RMA Swap)"
        
    AuditService.log(db, current_user, "APPROVE", "ZTP", q_item.serial_number, details=audit_msg)
    
    return {"message": "Device approved. Ready for provisioning."}


@router.post("/queue/{item_id}/retry", response_model=ZtpQueueResponse)
def retry_queue_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q_item = db.query(ZtpQueue).filter(ZtpQueue.id == item_id).first()
    if not q_item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    q_item.status = ZtpStatus.NEW.value
    q_item.last_message = "Retry requested by operator."
    db.commit()
    db.refresh(q_item)
    AuditService.log(db, current_user, "RETRY", "ZTP", q_item.serial_number, details="Retry queue item")
    return _serialize_queue_item(q_item)


@router.delete("/queue/{item_id}")
def delete_queue_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    q_item = db.query(ZtpQueue).filter(ZtpQueue.id == item_id).first()
    if not q_item:
        raise HTTPException(status_code=404, detail="Queue item not found")
    serial = q_item.serial_number
    db.delete(q_item)
    db.commit()
    AuditService.log(db, current_user, "DELETE", "ZTP", serial, details="Deleted queue item")
    return {"status": "ok", "deleted_id": item_id}
