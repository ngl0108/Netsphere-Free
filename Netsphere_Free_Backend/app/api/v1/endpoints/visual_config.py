from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import SessionLocal, get_db
from app.models.device import ConfigBackup, Device
from app.models.user import User
from app.models.visual_config import VisualBlueprint, VisualBlueprintVersion, VisualDeployJob, VisualDeployResult
from app.services.audit_service import AuditService
from app.services.visual_config_compiler import compile_graph_to_ir
from app.services.visual_config_renderer import render_ir_to_commands, render_ir_to_rollback_commands
from app.services.ssh_service import DeviceConnection, DeviceInfo
from app.services.device_support_policy_service import DeviceSupportPolicyService


router = APIRouter()


class GraphPayload(BaseModel):
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    viewport: Optional[Dict[str, Any]] = None


class BlueprintCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    graph: Optional[GraphPayload] = None


class BlueprintUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class BlueprintResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    current_version: int
    graph: GraphPayload


class BlueprintListItem(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    current_version: int


class VersionCreateRequest(BaseModel):
    graph: GraphPayload


class PreviewResponseDevice(BaseModel):
    device_id: int
    name: Optional[str] = None
    ip_address: Optional[str] = None
    device_type: Optional[str] = None
    commands: List[str] = []


class PreviewResponse(BaseModel):
    errors: List[str] = []
    errors_by_node_id: Dict[str, List[str]] = {}
    devices: List[PreviewResponseDevice] = []


class DeployRequest(BaseModel):
    save_backup: bool = True


class DeployResultDevice(BaseModel):
    device_id: int
    name: Optional[str] = None
    ip_address: Optional[str] = None
    success: bool
    error: Optional[str] = None


class DeployResponse(BaseModel):
    job_id: int
    status: str
    results: List[DeployResultDevice] = []


class RollbackRequest(BaseModel):
    device_ids: Optional[List[int]] = None
    save_backup: bool = True


def _ensure_access(current_user: User, blueprint: VisualBlueprint) -> None:
    if current_user.role == "admin":
        return
    if blueprint.owner_id is None:
        raise HTTPException(status_code=403, detail="Access denied")
    if blueprint.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")


@router.get("/blueprints", response_model=List[BlueprintListItem])
def list_blueprints(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    q = db.query(VisualBlueprint)
    if current_user.role != "admin":
        q = q.filter(VisualBlueprint.owner_id == current_user.id)
    rows = q.order_by(VisualBlueprint.id.desc()).all()
    out = []
    for b in rows:
        cv = b.current_version.version if b.current_version else 0
        out.append({"id": b.id, "name": b.name, "description": b.description, "current_version": cv})
    return out


@router.post("/blueprints", response_model=BlueprintResponse)
def create_blueprint(
    req: BlueprintCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    graph = (req.graph.dict() if req.graph else GraphPayload().dict())
    blueprint = VisualBlueprint(name=req.name, description=req.description, owner_id=current_user.id)
    db.add(blueprint)
    db.flush()

    v = VisualBlueprintVersion(blueprint_id=blueprint.id, version=1, graph_json=graph)
    db.add(v)
    db.flush()

    blueprint.current_version_id = v.id
    db.commit()
    db.refresh(blueprint)
    db.refresh(v)

    return {
        "id": blueprint.id,
        "name": blueprint.name,
        "description": blueprint.description,
        "current_version": v.version,
        "graph": v.graph_json,
    }


@router.get("/blueprints/{blueprint_id}", response_model=BlueprintResponse)
def get_blueprint(
    blueprint_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    blueprint = db.query(VisualBlueprint).filter(VisualBlueprint.id == blueprint_id).first()
    if not blueprint:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    _ensure_access(current_user, blueprint)

    v = blueprint.current_version
    if not v:
        v = (
            db.query(VisualBlueprintVersion)
            .filter(VisualBlueprintVersion.blueprint_id == blueprint.id)
            .order_by(VisualBlueprintVersion.version.desc())
            .first()
        )
    if not v:
        graph = GraphPayload().dict()
        current_version = 0
    else:
        graph = v.graph_json
        current_version = int(v.version or 0)

    return {
        "id": blueprint.id,
        "name": blueprint.name,
        "description": blueprint.description,
        "current_version": current_version,
        "graph": graph,
    }


@router.put("/blueprints/{blueprint_id}", response_model=BlueprintListItem)
def update_blueprint(
    blueprint_id: int,
    req: BlueprintUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    blueprint = db.query(VisualBlueprint).filter(VisualBlueprint.id == blueprint_id).first()
    if not blueprint:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    _ensure_access(current_user, blueprint)

    if req.name is not None:
        blueprint.name = req.name
    if req.description is not None:
        blueprint.description = req.description

    db.commit()
    db.refresh(blueprint)
    cv = blueprint.current_version.version if blueprint.current_version else 0
    return {"id": blueprint.id, "name": blueprint.name, "description": blueprint.description, "current_version": cv}


@router.delete("/blueprints/{blueprint_id}")
def delete_blueprint(
    blueprint_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    blueprint = db.query(VisualBlueprint).filter(VisualBlueprint.id == blueprint_id).first()
    if not blueprint:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    _ensure_access(current_user, blueprint)

    db.delete(blueprint)
    db.commit()
    return {"message": "deleted"}


@router.post("/blueprints/{blueprint_id}/versions", response_model=BlueprintResponse)
def create_version(
    blueprint_id: int,
    req: VersionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    blueprint = db.query(VisualBlueprint).filter(VisualBlueprint.id == blueprint_id).first()
    if not blueprint:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    _ensure_access(current_user, blueprint)

    next_ver = (
        db.query(func.max(VisualBlueprintVersion.version))
        .filter(VisualBlueprintVersion.blueprint_id == blueprint_id)
        .scalar()
    )
    next_ver = int(next_ver or 0) + 1

    v = VisualBlueprintVersion(blueprint_id=blueprint_id, version=next_ver, graph_json=req.graph.dict())
    db.add(v)
    db.flush()

    blueprint.current_version_id = v.id
    db.commit()
    db.refresh(blueprint)
    db.refresh(v)

    return {
        "id": blueprint.id,
        "name": blueprint.name,
        "description": blueprint.description,
        "current_version": v.version,
        "graph": v.graph_json,
    }


@router.post("/blueprints/{blueprint_id}/preview", response_model=PreviewResponse)
def preview_blueprint(
    blueprint_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    blueprint = db.query(VisualBlueprint).filter(VisualBlueprint.id == blueprint_id).first()
    if not blueprint:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    _ensure_access(current_user, blueprint)

    v = blueprint.current_version
    if not v:
        raise HTTPException(status_code=400, detail="Blueprint has no version")

    graph = v.graph_json or {}
    compiled = compile_graph_to_ir(graph)
    if compiled.errors or compiled.errors_by_node_id:
        return {"errors": compiled.errors, "errors_by_node_id": compiled.errors_by_node_id, "devices": []}

    devices = db.query(Device).filter(Device.id.in_(compiled.device_ids)).all() if compiled.device_ids else []
    out = []
    for d in devices:
        cmds = render_ir_to_commands(compiled.ir, d.device_type or "cisco_ios")
        out.append(
            {
                "device_id": d.id,
                "name": d.name,
                "ip_address": d.ip_address,
                "device_type": d.device_type,
                "commands": cmds,
            }
        )

    return {"errors": [], "errors_by_node_id": {}, "devices": out}


def _deploy_worker(device_id: int, commands: List[str], save_backup: bool) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return {"device_id": device_id, "success": False, "error": "Device not found", "output_log": "", "rendered_config": "\n".join(commands)}
        if not device.ssh_password:
            return {"device_id": device_id, "success": False, "error": "SSH credentials missing", "output_log": "", "rendered_config": "\n".join(commands)}

        dev_info = DeviceInfo(
            host=device.ip_address,
            username=device.ssh_username or "admin",
            password=device.ssh_password,
            secret=device.enable_password,
            port=int(device.ssh_port or 22),
            device_type=device.device_type or "cisco_ios",
        )
        conn = DeviceConnection(dev_info)
        if not conn.connect():
            return {"device_id": device_id, "success": False, "error": f"Connection Failed: {conn.last_error}", "output_log": "", "rendered_config": "\n".join(commands)}

        try:
            if save_backup:
                try:
                    raw_config = conn.get_running_config()
                    db.add(ConfigBackup(device_id=device.id, raw_config=raw_config))
                    db.commit()
                except Exception:
                    db.rollback()

            output = conn.send_config_set(commands)
            return {"device_id": device_id, "success": True, "error": None, "output_log": output, "rendered_config": "\n".join(commands)}
        finally:
            conn.disconnect()
    except Exception as e:
        return {"device_id": device_id, "success": False, "error": str(e), "output_log": "", "rendered_config": "\n".join(commands)}
    finally:
        db.close()


@router.post("/blueprints/{blueprint_id}/deploy", response_model=DeployResponse)
def deploy_blueprint(
    blueprint_id: int,
    req: DeployRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    blueprint = db.query(VisualBlueprint).filter(VisualBlueprint.id == blueprint_id).first()
    if not blueprint:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    _ensure_access(current_user, blueprint)

    v = blueprint.current_version
    if not v:
        raise HTTPException(status_code=400, detail="Blueprint has no version")

    compiled = compile_graph_to_ir(v.graph_json or {})
    if compiled.errors or compiled.errors_by_node_id:
        raise HTTPException(
            status_code=400,
            detail={"errors": compiled.errors, "errors_by_node_id": compiled.errors_by_node_id},
        )

    target_ids = compiled.device_ids
    target_devices = db.query(Device).filter(Device.id.in_(target_ids)).all() if target_ids else []
    blocked_config = DeviceSupportPolicyService.collect_blocked_devices(
        db,
        devices=target_devices,
        feature="config",
    )
    if blocked_config:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEVICE_SUPPORT_BLOCKED",
                "message": "Visual config deploy blocked for unsupported devices.",
                "details": {"feature": "config", "blocked_devices": blocked_config},
            },
        )

    job = VisualDeployJob(
        blueprint_id=blueprint.id,
        blueprint_version_id=v.id,
        requested_by=current_user.id,
        status="running",
        target_device_ids=target_ids,
        summary={"type": "deploy"},
    )
    db.add(job)
    db.flush()

    devices = db.query(Device).filter(Device.id.in_(target_ids)).all() if target_ids else []
    devices_by_id = {d.id: d for d in devices}

    from concurrent.futures import ThreadPoolExecutor, as_completed

    futures = []
    results = []

    with ThreadPoolExecutor(max_workers=6) as ex:
        for device_id in target_ids:
            d = devices_by_id.get(device_id)
            dtype = d.device_type if d else "cisco_ios"
            commands = render_ir_to_commands(compiled.ir, dtype)
            futures.append(ex.submit(_deploy_worker, device_id, commands, bool(req.save_backup)))

        for f in as_completed(futures):
            results.append(f.result())

    ok = 0
    for r in results:
        device_id = int(r.get("device_id"))
        d = devices_by_id.get(device_id)
        db.add(
            VisualDeployResult(
                job_id=job.id,
                device_id=device_id,
                success=bool(r.get("success")),
                rendered_config=r.get("rendered_config") or "",
                output_log=r.get("output_log") or "",
                error=r.get("error"),
            )
        )
        if r.get("success"):
            ok += 1

    job.finished_at = datetime.utcnow()
    job.status = "success" if ok == len(target_ids) and len(target_ids) > 0 else "failed"
    job.summary = {"type": "deploy", "total": len(target_ids), "success": ok, "failed": len(target_ids) - ok}
    db.commit()
    db.refresh(job)

    resp_rows = []
    for r in sorted(results, key=lambda x: int(x.get("device_id", 0))):
        device_id = int(r.get("device_id"))
        d = devices_by_id.get(device_id)
        resp_rows.append(
            {
                "device_id": device_id,
                "name": d.name if d else None,
                "ip_address": d.ip_address if d else None,
                "success": bool(r.get("success")),
                "error": r.get("error"),
            }
        )

    AuditService.log(
        db,
        current_user,
        action="VC_DEPLOY",
        resource_type="VisualBlueprint",
        resource_name=blueprint.name,
        details={"job_id": job.id, "version_id": v.id, "summary": job.summary},
        status="success" if job.status == "success" else "failure",
    )

    return {"job_id": job.id, "status": job.status, "results": resp_rows}


class DeployJobResponse(BaseModel):
    id: int
    blueprint_id: int
    blueprint_version_id: int
    status: str
    created_at: datetime
    finished_at: Optional[datetime] = None
    target_device_ids: List[int] = []
    summary: Optional[Dict[str, Any]] = None


class DeployJobResultResponse(BaseModel):
    device_id: int
    success: bool
    error: Optional[str] = None
    rendered_config: Optional[str] = None
    output_log: Optional[str] = None


@router.get("/deploy-jobs/{job_id}")
def get_deploy_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    job = db.query(VisualDeployJob).filter(VisualDeployJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    blueprint = db.query(VisualBlueprint).filter(VisualBlueprint.id == job.blueprint_id).first()
    if not blueprint:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    _ensure_access(current_user, blueprint)

    results = db.query(VisualDeployResult).filter(VisualDeployResult.job_id == job.id).order_by(VisualDeployResult.device_id.asc()).all()
    return {
        "job": {
            "id": job.id,
            "blueprint_id": job.blueprint_id,
            "blueprint_version_id": job.blueprint_version_id,
            "status": job.status,
            "created_at": job.created_at,
            "finished_at": job.finished_at,
            "target_device_ids": job.target_device_ids or [],
            "summary": job.summary,
        },
        "results": [
            {
                "device_id": r.device_id,
                "success": r.success,
                "error": r.error,
                "rendered_config": r.rendered_config,
                "output_log": r.output_log,
            }
            for r in results
        ],
    }


@router.get("/blueprints/{blueprint_id}/deploy-jobs")
def list_deploy_jobs_for_blueprint(
    blueprint_id: int,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    blueprint = db.query(VisualBlueprint).filter(VisualBlueprint.id == blueprint_id).first()
    if not blueprint:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    _ensure_access(current_user, blueprint)

    rows = (
        db.query(VisualDeployJob)
        .filter(VisualDeployJob.blueprint_id == blueprint_id)
        .order_by(VisualDeployJob.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "status": r.status,
            "created_at": r.created_at,
            "finished_at": r.finished_at,
            "summary": r.summary,
            "target_device_ids": r.target_device_ids or [],
        }
        for r in rows
    ]


def _rollback_worker(device_id: int, device_type: str, ir: List[Dict[str, Any]], save_backup: bool) -> Dict[str, Any]:
    db = SessionLocal()
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return {"device_id": device_id, "success": False, "error": "Device not found", "output_log": "", "rendered_config": ""}
        if not device.ssh_password:
            return {"device_id": device_id, "success": False, "error": "SSH credentials missing", "output_log": "", "rendered_config": ""}

        dev_info = DeviceInfo(
            host=device.ip_address,
            username=device.ssh_username or "admin",
            password=device.ssh_password,
            secret=device.enable_password,
            port=int(device.ssh_port or 22),
            device_type=device.device_type or "cisco_ios",
        )
        conn = DeviceConnection(dev_info)
        if not conn.connect():
            return {"device_id": device_id, "success": False, "error": f"Connection Failed: {conn.last_error}", "output_log": "", "rendered_config": ""}

        try:
            if save_backup:
                try:
                    raw_config = conn.get_running_config()
                    db.add(ConfigBackup(device_id=device.id, raw_config=raw_config))
                    db.commit()
                except Exception:
                    db.rollback()

            if (device_type or "").lower().find("junos") >= 0 and hasattr(conn.driver, "rollback"):
                ok = conn.rollback()
                if ok:
                    return {"device_id": device_id, "success": True, "error": None, "output_log": "rollback executed", "rendered_config": ""}
                return {"device_id": device_id, "success": False, "error": conn.driver.last_error if hasattr(conn.driver, "last_error") else "rollback failed", "output_log": "", "rendered_config": ""}

            commands = render_ir_to_rollback_commands(ir, device_type or "cisco_ios")
            output = conn.send_config_set(commands)
            return {"device_id": device_id, "success": True, "error": None, "output_log": output, "rendered_config": "\n".join(commands)}
        finally:
            conn.disconnect()
    except Exception as e:
        return {"device_id": device_id, "success": False, "error": str(e), "output_log": "", "rendered_config": ""}
    finally:
        db.close()


@router.post("/deploy-jobs/{job_id}/rollback", response_model=DeployResponse)
def rollback_deploy_job(
    job_id: int,
    req: RollbackRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    src_job = db.query(VisualDeployJob).filter(VisualDeployJob.id == job_id).first()
    if not src_job:
        raise HTTPException(status_code=404, detail="Job not found")
    blueprint = db.query(VisualBlueprint).filter(VisualBlueprint.id == src_job.blueprint_id).first()
    if not blueprint:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    _ensure_access(current_user, blueprint)

    v = db.query(VisualBlueprintVersion).filter(VisualBlueprintVersion.id == src_job.blueprint_version_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="Blueprint version not found")

    compiled = compile_graph_to_ir(v.graph_json or {})
    if compiled.errors or compiled.errors_by_node_id:
        raise HTTPException(
            status_code=400,
            detail={"errors": compiled.errors, "errors_by_node_id": compiled.errors_by_node_id},
        )

    target_ids = list(src_job.target_device_ids or [])
    if req.device_ids:
        allow = set(int(x) for x in req.device_ids if x is not None)
        target_ids = [x for x in target_ids if int(x) in allow]

    if not target_ids:
        raise HTTPException(status_code=400, detail="No target devices")

    target_devices = db.query(Device).filter(Device.id.in_(target_ids)).all()
    blocked_rollback = DeviceSupportPolicyService.collect_blocked_devices(
        db,
        devices=target_devices,
        feature="rollback",
    )
    if blocked_rollback:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ROLLBACK_STRATEGY_UNSUPPORTED",
                "message": "Rollback blocked for devices without supported rollback strategy.",
                "details": {"feature": "rollback", "blocked_devices": blocked_rollback},
            },
        )

    rollback_job = VisualDeployJob(
        blueprint_id=blueprint.id,
        blueprint_version_id=v.id,
        requested_by=current_user.id,
        status="running",
        target_device_ids=target_ids,
        summary={"type": "rollback", "rollback_of_job_id": src_job.id},
    )
    db.add(rollback_job)
    db.flush()

    devices = db.query(Device).filter(Device.id.in_(target_ids)).all()
    devices_by_id = {d.id: d for d in devices}

    from concurrent.futures import ThreadPoolExecutor, as_completed

    futures = []
    results = []
    with ThreadPoolExecutor(max_workers=6) as ex:
        for device_id in target_ids:
            d = devices_by_id.get(device_id)
            dtype = d.device_type if d else "cisco_ios"
            futures.append(ex.submit(_rollback_worker, device_id, dtype, compiled.ir, bool(req.save_backup)))
        for f in as_completed(futures):
            results.append(f.result())

    ok = 0
    for r in results:
        device_id = int(r.get("device_id"))
        db.add(
            VisualDeployResult(
                job_id=rollback_job.id,
                device_id=device_id,
                success=bool(r.get("success")),
                rendered_config=r.get("rendered_config") or "",
                output_log=r.get("output_log") or "",
                error=r.get("error"),
            )
        )
        if r.get("success"):
            ok += 1

    rollback_job.finished_at = datetime.utcnow()
    rollback_job.status = "success" if ok == len(target_ids) else "failed"
    rollback_job.summary = {"type": "rollback", "rollback_of_job_id": src_job.id, "total": len(target_ids), "success": ok, "failed": len(target_ids) - ok}
    db.commit()
    db.refresh(rollback_job)

    resp_rows = []
    for r in sorted(results, key=lambda x: int(x.get("device_id", 0))):
        device_id = int(r.get("device_id"))
        d = devices_by_id.get(device_id)
        resp_rows.append(
            {
                "device_id": device_id,
                "name": d.name if d else None,
                "ip_address": d.ip_address if d else None,
                "success": bool(r.get("success")),
                "error": r.get("error"),
            }
        )

    AuditService.log(
        db,
        current_user,
        action="VC_ROLLBACK",
        resource_type="VisualBlueprint",
        resource_name=blueprint.name,
        details={"source_job_id": src_job.id, "rollback_job_id": rollback_job.id, "summary": rollback_job.summary},
        status="success" if rollback_job.status == "success" else "failure",
    )

    return {"job_id": rollback_job.id, "status": rollback_job.status, "results": resp_rows}
