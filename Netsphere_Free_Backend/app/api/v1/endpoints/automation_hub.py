from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta
import json
from sqlalchemy import func

from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.device import Device, ConfigTemplate, Policy
from app.services.template_service import TemplateRenderer
from app.services.ssh_service import DeviceConnection, DeviceInfo
from app.services.policy_translator import PolicyTranslator
from app.services.audit_service import AuditService
from app.models.audit import AuditLog
from app.services.discovery_service import DiscoveryService
from app.tasks.discovery_dispatch import dispatch_discovery_scan, dispatch_neighbor_crawl

router = APIRouter()


class TrackRequest(BaseModel):
    event: str
    variant: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


@router.post("/track", dependencies=[Depends(deps.get_current_user)])
def track_event(req: TrackRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.get_current_user)):
    AuditService.log(
        db=db,
        user=current_user,
        action="AUTO_HUB_VIEW",
        resource_type="AutomationHub",
        resource_name="track",
        details={"event": req.event, "variant": req.variant, "meta": req.meta},
        status="success",
    )
    return {"ok": True, "event": req.event, "variant": req.variant}


class FeedbackRequest(BaseModel):
    rating: int
    comment: Optional[str] = None
    variant: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


@router.post("/feedback")
def submit_feedback(req: FeedbackRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.require_operator)):
    AuditService.log(
        db=db,
        user=current_user,
        action="AUTO_HUB_FEEDBACK",
        resource_type="AutomationHub",
        resource_name="feedback",
        details={"rating": int(req.rating), "comment": req.comment, "variant": req.variant, "meta": req.meta},
        status="success",
    )
    return {"ok": True}


@router.get("/usage")
def get_usage(days: int = 14, db: Session = Depends(get_db), current_user: User = Depends(deps.require_operator)):
    days_n = max(1, min(int(days), 365))
    since = datetime.utcnow() - timedelta(days=days_n)
    rows = (
        db.query(AuditLog.action, func.count(AuditLog.id))
        .filter(AuditLog.resource_type == "AutomationHub")
        .filter(AuditLog.timestamp >= since)
        .group_by(AuditLog.action)
        .all()
    )
    counts_by_action = {a: int(c) for a, c in rows}

    logs = (
        db.query(AuditLog)
        .filter(AuditLog.resource_type == "AutomationHub")
        .filter(AuditLog.timestamp >= since)
        .order_by(AuditLog.timestamp.desc())
        .limit(5000)
        .all()
    )
    by_variant: Dict[str, int] = {}
    by_module: Dict[str, int] = {}
    for l in logs:
        details = l.details or ""
        try:
            obj = json.loads(details) if details else {}
        except Exception:
            obj = {}
        v = obj.get("variant")
        if v:
            by_variant[str(v)] = by_variant.get(str(v), 0) + 1
        m = obj.get("module")
        if m:
            by_module[str(m)] = by_module.get(str(m), 0) + 1
    return {"days": days_n, "counts_by_action": counts_by_action, "counts_by_variant": by_variant, "counts_by_module": by_module}


class TemplateRunRequest(BaseModel):
    template_id: int
    device_ids: List[int]
    variables: Dict[str, Any] = {}
    meta: Optional[Dict[str, Any]] = None


class DiscoveryRunRequest(BaseModel):
    mode: Optional[str] = None
    cidr: Optional[str] = None
    seed_device_id: Optional[int] = None
    seed_ip: Optional[str] = None
    max_depth: Optional[int] = 2
    site_id: Optional[int] = None
    snmp_profile_id: Optional[int] = None
    community: Optional[str] = "public"
    snmp_version: Optional[str] = "v2c"
    snmp_port: Optional[int] = 161
    snmp_v3_username: Optional[str] = None
    snmp_v3_security_level: Optional[str] = None
    snmp_v3_auth_proto: Optional[str] = None
    snmp_v3_auth_key: Optional[str] = None
    snmp_v3_priv_proto: Optional[str] = None
    snmp_v3_priv_key: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


@router.post("/discovery")
def run_discovery(
    req: DiscoveryRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    mode = str(req.mode or "").lower()
    has_seed = req.seed_device_id is not None or bool(str(req.seed_ip or "").strip())
    is_crawl = mode in {"seed", "crawl", "neighbor"} or has_seed
    is_scan = bool(str(req.cidr or "").strip())

    if is_crawl:
        seed_ip = str(req.seed_ip or "").strip()
        seed_device_id = req.seed_device_id
        if not seed_ip and seed_device_id is None:
            raise HTTPException(status_code=400, detail="seed_device_id or seed_ip is required")
        cidr = f"seedip:{seed_ip}" if seed_ip else f"seed:{seed_device_id}"
        service = DiscoveryService(db)
        job = service.create_scan_job(
            cidr,
            req.community or "public",
            site_id=req.site_id,
            snmp_profile_id=req.snmp_profile_id,
            snmp_version=req.snmp_version or "v2c",
            snmp_port=req.snmp_port or 161,
            snmp_v3_username=req.snmp_v3_username,
            snmp_v3_security_level=req.snmp_v3_security_level,
            snmp_v3_auth_proto=req.snmp_v3_auth_proto,
            snmp_v3_auth_key=req.snmp_v3_auth_key,
            snmp_v3_priv_proto=req.snmp_v3_priv_proto,
            snmp_v3_priv_key=req.snmp_v3_priv_key,
        )
        dispatch = dispatch_neighbor_crawl(
            job.id,
            seed_device_id=seed_device_id,
            seed_ip=seed_ip or None,
            max_depth=int(req.max_depth or 2),
            idempotency_key=f"automation-hub:crawl:{job.id}",
        )
        if dispatch.get("status") not in {"enqueued", "skipped"}:
            service._append_job_log(job, f"Queue dispatch failed: {dispatch.get('reason')}")
            job.status = "failed"
            db.commit()
            raise HTTPException(status_code=503, detail="Neighbor crawl worker queue unavailable")

        AuditService.log(
            db=db,
            user=current_user,
            action="AUTO_HUB_DISCOVERY",
            resource_type="AutomationHub",
            resource_name="discovery:crawl",
            details={"module": "discovery", "variant": (req.meta or {}).get("variant") if isinstance(req.meta, dict) else None, "mode": "crawl", "seed_device_id": seed_device_id, "seed_ip": seed_ip},
            status="success",
        )
        return {
            "id": job.id,
            "cidr": job.cidr,
            "status": job.status,
            "logs": job.logs,
            "created_at": str(job.created_at),
        }

    if not is_scan:
        raise HTTPException(status_code=400, detail="cidr is required")

    service = DiscoveryService(db)
    job = service.create_scan_job(
        str(req.cidr).strip(),
        req.community or "public",
        site_id=req.site_id,
        snmp_profile_id=req.snmp_profile_id,
        snmp_version=req.snmp_version or "v2c",
        snmp_port=req.snmp_port or 161,
        snmp_v3_username=req.snmp_v3_username,
        snmp_v3_security_level=req.snmp_v3_security_level,
        snmp_v3_auth_proto=req.snmp_v3_auth_proto,
        snmp_v3_auth_key=req.snmp_v3_auth_key,
        snmp_v3_priv_proto=req.snmp_v3_priv_proto,
        snmp_v3_priv_key=req.snmp_v3_priv_key,
    )
    dispatch = dispatch_discovery_scan(job.id, idempotency_key=f"automation-hub:scan:{job.id}")
    if dispatch.get("status") not in {"enqueued", "skipped"}:
        service._append_job_log(job, f"Queue dispatch failed: {dispatch.get('reason')}")
        job.status = "failed"
        db.commit()
        raise HTTPException(status_code=503, detail="Discovery worker queue unavailable")

    AuditService.log(
        db=db,
        user=current_user,
        action="AUTO_HUB_DISCOVERY",
        resource_type="AutomationHub",
        resource_name="discovery:scan",
        details={"module": "discovery", "variant": (req.meta or {}).get("variant") if isinstance(req.meta, dict) else None, "mode": "scan", "cidr": str(req.cidr).strip()},
        status="success",
    )
    return {
        "id": job.id,
        "cidr": job.cidr,
        "status": job.status,
        "logs": job.logs,
        "created_at": str(job.created_at),
    }


def _deploy_template_worker(target: Dict[str, Any], template_content: str):
    dev_id = target["dev_id"]
    try:
        config_text = TemplateRenderer.render(template_content, target["context"])
        info = DeviceInfo(**target["device_info_args"])
        conn = DeviceConnection(info)
        if conn.connect():
            output = conn.send_config_set(config_text.splitlines())
            conn.disconnect()
            return {"device_id": dev_id, "status": "success", "output": output}
        return {"device_id": dev_id, "status": "failed", "error": f"Connection Failed: {conn.last_error}"}
    except Exception as e:
        return {"device_id": dev_id, "status": "error", "error": str(e)}


@router.post("/template")
def run_template(
    req: TemplateRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin),
):
    template = db.query(ConfigTemplate).filter(ConfigTemplate.id == req.template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    targets = []
    for dev_id in req.device_ids:
        dev = db.query(Device).filter(Device.id == dev_id).first()
        if not dev:
            continue
        context = dev.variables or {}
        context.update({"device": {"name": dev.name, "ip": dev.ip_address}, "_dev_id": dev.id})
        context.update(req.variables or {})
        dev_args = {
            "host": dev.ip_address,
            "username": dev.ssh_username,
            "password": dev.ssh_password,
            "secret": dev.enable_password,
            "port": dev.ssh_port or 22,
            "device_type": dev.device_type or "cisco_ios",
        }
        targets.append({"dev_id": dev.id, "context": context, "device_info_args": dev_args})

    if not targets:
        raise HTTPException(status_code=400, detail="No target devices")

    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_map = {executor.submit(_deploy_template_worker, t, template.content): t["dev_id"] for t in targets}
        for fut in as_completed(future_map):
            results.append(fut.result())

    AuditService.log(
        db=db,
        user=current_user,
        action="AUTO_HUB_TEMPLATE",
        resource_type="AutomationHub",
        resource_name=f"template:{req.template_id}",
        details={"module": "template", "variant": (req.meta or {}).get("variant") if isinstance(req.meta, dict) else None, "devices": len(req.device_ids)},
        status="success",
    )
    return {"results": results}


class AclEnforceRequest(BaseModel):
    policy_id: int
    device_ids: List[int]
    meta: Optional[Dict[str, Any]] = None


@router.post("/acl-enforce")
def acl_enforce(
    req: AclEnforceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin),
):
    policy = db.query(Policy).filter(Policy.id == req.policy_id).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    results = []
    for d_id in req.device_ids:
        dev = db.query(Device).filter(Device.id == d_id).first()
        if not dev:
            continue
        translated = PolicyTranslator.translate_or_fallback(policy, dev.device_type)
        commands = translated["commands"]
        if not translated["supported"]:
            results.append(
                {
                    "device_id": dev.id,
                    "device_name": dev.name,
                    "status": "manual_approval_required",
                    "message": translated["message"],
                    "mode": translated["mode"],
                    "plugin": translated["plugin"],
                }
            )
            continue
        try:
            info = DeviceInfo(
                host=dev.ip_address,
                username=dev.ssh_username,
                password=dev.ssh_password,
                secret=dev.enable_password,
                port=dev.ssh_port or 22,
                device_type=dev.device_type,
            )
            conn = DeviceConnection(info)
            if conn.connect():
                output = conn.driver.push_config(commands)
                conn.disconnect()
                results.append(
                    {
                        "device_id": dev.id,
                        "device_name": dev.name,
                        "status": "success",
                        "message": f"Policy '{policy.name}' deployed successfully",
                        "output": output,
                    }
                )
            else:
                results.append({"device_id": dev.id, "device_name": dev.name, "status": "failed", "message": f"Connection failed: {conn.last_error}"})
        except Exception as e:
            results.append({"device_id": dev.id, "device_name": dev.name, "status": "error", "message": str(e)})

    AuditService.log(
        db=db,
        user=current_user,
        action="AUTO_HUB_ACL",
        resource_type="AutomationHub",
        resource_name=f"acl:{req.policy_id}",
        details={"module": "acl-enforce", "variant": (req.meta or {}).get("variant") if isinstance(req.meta, dict) else None, "devices": len(req.device_ids)},
        status="success",
    )
    return {"results": results}


class FaultToleranceRequest(BaseModel):
    visual_deploy_job_id: int
    device_ids: List[int] = []
    save_backup: bool = False
    meta: Optional[Dict[str, Any]] = None


@router.post("/fault-tolerance")
def fault_tolerance(
    req: FaultToleranceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    from app.api.v1.endpoints.visual_config import rollback_deploy_job, RollbackRequest

    rb = RollbackRequest(device_ids=req.device_ids or None, save_backup=bool(req.save_backup))
    out = rollback_deploy_job(req.visual_deploy_job_id, rb, db, current_user)
    AuditService.log(
        db=db,
        user=current_user,
        action="AUTO_HUB_FT",
        resource_type="AutomationHub",
        resource_name=f"fault-tolerance:{req.visual_deploy_job_id}",
        details={"module": "fault-tolerance", "variant": (req.meta or {}).get("variant") if isinstance(req.meta, dict) else None},
        status="success",
    )
    return out


class QosAutoscaleRequest(BaseModel):
    device_ids: List[int]
    threshold_bps: float
    current_bps: float
    scale_up_template_id: int
    scale_down_template_id: int
    variables: Dict[str, Any] = {}
    meta: Optional[Dict[str, Any]] = None


@router.post("/qos-autoscale")
def qos_autoscale(
    req: QosAutoscaleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin),
):
    chosen = req.scale_up_template_id if float(req.current_bps) > float(req.threshold_bps) else req.scale_down_template_id
    action = "scale_up" if chosen == req.scale_up_template_id else "scale_down"

    tpl_req = TemplateRunRequest(template_id=chosen, device_ids=req.device_ids, variables=req.variables or {}, meta=req.meta)
    out = run_template(tpl_req, db, current_user)
    AuditService.log(
        db=db,
        user=current_user,
        action="AUTO_HUB_QOS",
        resource_type="AutomationHub",
        resource_name=f"qos:{chosen}",
        details={"module": "qos-autoscale", "variant": (req.meta or {}).get("variant") if isinstance(req.meta, dict) else None, "action": action},
        status="success",
    )
    return {"action": action, "template_id": chosen, "deploy": out}
