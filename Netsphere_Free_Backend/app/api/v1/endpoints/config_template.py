from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel, ConfigDict
from app.db.session import get_db
from app.models.device import ConfigTemplate, Device
from app.api import deps
from app.models.user import User
from app.services.template_service import TemplateRenderer
from app.services.ssh_service import DeviceConnection, DeviceInfo
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.services.variable_context_service import resolve_device_context
from difflib import unified_diff
from app.db.session import SessionLocal
from app.models.device import ConfigBackup
import uuid
import time
from app.services.post_check_service import resolve_post_check_commands, resolve_pre_check_commands
from app.services.change_execution_service import ChangeExecutionService
from app.services.change_policy_service import ChangePolicyService
from app.services.approval_execution_service import ApprovalExecutionService
from app.services.device_support_policy_service import DeviceSupportPolicyService

router = APIRouter()
# Reload Trigger

_DIFF_PREVIEW_LIMIT = 120


def _build_diff_summary(before_text: str, after_text: str, diff_lines: List[str]) -> Dict[str, Any]:
    added = 0
    removed = 0
    context = 0
    for line in list(diff_lines or []):
        if line.startswith(("---", "+++", "@@")):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
        else:
            context += 1
    preview = list(diff_lines[:_DIFF_PREVIEW_LIMIT])
    return {
        "has_changes": bool(added or removed),
        "before_lines": len(str(before_text or "").splitlines()),
        "after_lines": len(str(after_text or "").splitlines()),
        "added_lines": int(added),
        "removed_lines": int(removed),
        "changed_lines_estimate": int(max(added, removed)),
        "context_lines": int(context),
        "total_diff_lines": len(list(diff_lines or [])),
        "preview": preview,
        "preview_truncated": len(list(diff_lines or [])) > len(preview),
    }


def _build_text_diff(before_text: str, after_text: str) -> Dict[str, Any]:
    diff_lines = list(
        unified_diff(
            str(before_text or "").splitlines(),
            str(after_text or "").splitlines(),
            fromfile="current",
            tofile="rendered",
            lineterm="",
        )
    )
    return {
        "diff_lines": diff_lines,
        "diff_summary": _build_diff_summary(str(before_text or ""), str(after_text or ""), diff_lines),
    }


def _looks_like_cli_error(output: str) -> bool:
    t = (output or "").lower()
    return any(
        s in t
        for s in (
            "% invalid",
            "invalid input",
            "unknown command",
            "unrecognized command",
            "ambiguous command",
            "incomplete command",
            "error:",
            "syntax error",
        )
    )


def _default_post_check_commands(device_type: str) -> List[str]:
    dt = str(device_type or "").lower()
    if "juniper" in dt or "junos" in dt:
        return ["show system uptime", "show system alarms", "show chassis alarms"]
    if "huawei" in dt:
        return ["display clock", "display version"]
    return ["show clock", "show version"]


def _run_post_check(conn: DeviceConnection, device_type: str, commands: List[str]) -> Dict[str, Any]:
    tried = []
    for cmd in commands:
        try:
            out = conn.send_command(cmd, read_timeout=20)
        except Exception as e:
            tried.append({"command": cmd, "ok": False, "error": f"{type(e).__name__}: {e}"})
            continue
        ok = bool(out) and not _looks_like_cli_error(out)
        if ok:
            return {"ok": True, "command": cmd, "output": out, "tried": tried}
        tried.append({"command": cmd, "ok": False, "output": out})
    return {"ok": False, "command": None, "output": None, "tried": tried}


def _run_pre_check(conn: DeviceConnection, commands: List[str]) -> Dict[str, Any]:
    rows = []
    all_ok = True
    for cmd in commands:
        c = str(cmd or "").strip()
        if not c:
            continue
        try:
            out = conn.send_command(c, read_timeout=20)
            ok = bool(out) and not _looks_like_cli_error(out)
            rows.append({"command": c, "ok": ok, "output": out})
            if not ok:
                all_ok = False
        except Exception as e:
            all_ok = False
            rows.append({"command": c, "ok": False, "error": f"{type(e).__name__}: {e}"})
    return {"ok": all_ok, "rows": rows}


def _compact_support_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    rollback_strategy = policy.get("rollback_strategy") if isinstance(policy.get("rollback_strategy"), dict) else {}
    return {
        "tier": policy.get("tier"),
        "readiness": policy.get("readiness"),
        "fallback_mode": policy.get("fallback_mode"),
        "capability_read_only": bool(policy.get("capability_read_only")),
        "reasons": list(policy.get("reasons") or []),
        "features": dict(policy.get("features") or {}),
        "rollback_strategy": {
            "supported": bool(rollback_strategy.get("supported")),
            "mode": rollback_strategy.get("mode"),
            "label": rollback_strategy.get("label"),
        },
    }


def _resolve_effective_post_check_commands(
    db: Session,
    device: Device,
    requested_commands: List[str] | None = None,
) -> List[str]:
    explicit = [str(c or "").strip() for c in list(requested_commands or []) if str(c or "").strip()]
    if explicit:
        return explicit
    resolved = resolve_post_check_commands(db, device) or []
    if resolved:
        return [str(c or "").strip() for c in resolved if str(c or "").strip()]
    return _default_post_check_commands(getattr(device, "device_type", ""))


def _build_device_change_guard(
    db: Session,
    device: Device,
    *,
    requested_post_check_commands: List[str] | None = None,
    rollback_on_failure: bool = True,
    post_check_enabled: bool = True,
) -> Dict[str, Any]:
    support_policy = DeviceSupportPolicyService.evaluate_device(db, device)
    pre_check_commands = resolve_pre_check_commands(db, device) or []
    post_check_commands = (
        _resolve_effective_post_check_commands(db, device, requested_post_check_commands)
        if bool(post_check_enabled)
        else []
    )
    features = dict(support_policy.get("features") or {})
    deploy_allowed = bool(features.get("config"))
    rollback_supported = bool(features.get("rollback"))
    blocked_reasons: List[str] = []
    if not deploy_allowed:
        blocked_reasons.append("config_not_supported")
    if bool(rollback_on_failure) and not rollback_supported:
        blocked_reasons.append("rollback_not_supported")
    if bool(support_policy.get("capability_read_only")):
        blocked_reasons.append("capability_read_only")
    blocked_reasons.extend([str(x) for x in list(support_policy.get("reasons") or []) if str(x or "").strip()])
    return {
        "device_id": int(device.id),
        "device_name": device.name,
        "ip_address": device.ip_address,
        "support_policy": _compact_support_policy(support_policy),
        "pre_check_commands": [str(c) for c in pre_check_commands],
        "post_check_commands": [str(c) for c in post_check_commands],
        "deploy_allowed": bool(deploy_allowed),
        "rollback_supported": bool(rollback_supported),
        "blocked_reasons": list(dict.fromkeys(blocked_reasons)),
    }


def _build_template_change_plan(
    db: Session,
    devices: List[Device],
    *,
    approval_id: int | None,
    rollback_on_failure: bool,
    canary_count: int,
    wave_size: int,
    stop_on_wave_failure: bool,
    inter_wave_delay_seconds: float,
) -> Dict[str, Any]:
    ordered_ids = [int(getattr(d, "id")) for d in list(devices or []) if getattr(d, "id", None) is not None]
    blocked_config = DeviceSupportPolicyService.collect_blocked_devices(db, devices=devices, feature="config")
    blocked_rollback = (
        DeviceSupportPolicyService.collect_blocked_devices(db, devices=devices, feature="rollback")
        if bool(rollback_on_failure)
        else []
    )
    direct_max = ChangePolicyService.template_direct_max_devices(db)
    requires_approval = ChangePolicyService.requires_template_approval(
        db,
        target_count=len(ordered_ids),
        approval_id=approval_id,
    )
    waves = ChangeExecutionService.build_waves(
        ordered_ids,
        wave_size=int(wave_size or 0),
        canary_count=int(canary_count or 0),
    )

    if blocked_config:
        route = "blocked"
        reason = "Some selected devices do not support config deployment under the current support policy."
    elif blocked_rollback:
        route = "blocked"
        reason = "Rollback-on-failure is enabled, but some selected devices do not support rollback."
    elif requires_approval:
        route = "approval"
        reason = f"Target count ({len(ordered_ids)}) exceeds the direct deployment threshold ({direct_max})."
    else:
        route = "direct"
        reason = f"Target count ({len(ordered_ids)}) is within the direct deployment threshold ({direct_max})."

    return {
        "route": route,
        "reason": reason,
        "requires_approval": bool(requires_approval),
        "approval_bound": approval_id is not None,
        "target_count": len(ordered_ids),
        "direct_max_devices": int(direct_max),
        "rollback_on_failure": bool(rollback_on_failure),
        "blocked_config_devices": blocked_config,
        "blocked_rollback_devices": blocked_rollback,
        "rollout": {
            "canary_count": int(canary_count or 0),
            "wave_size": int(wave_size or 0),
            "waves_total": len(waves),
            "stop_on_wave_failure": bool(stop_on_wave_failure),
            "inter_wave_delay_seconds": float(inter_wave_delay_seconds or 0.0),
        },
        "summary": {
            "config_supported": max(0, len(ordered_ids) - len(blocked_config)),
            "rollback_supported": max(0, len(ordered_ids) - len(blocked_rollback)),
            "blocked_config": len(blocked_config),
            "blocked_rollback": len(blocked_rollback),
        },
    }


def _derive_failure_cause(row: Dict[str, Any]) -> str | None:
    status = str(row.get("status") or "").strip().lower()
    if status == "precheck_failed":
        return "pre_check_failed"
    if status == "postcheck_failed":
        rollback = row.get("rollback") if isinstance(row.get("rollback"), dict) else {}
        if rollback.get("attempted") and not rollback.get("success"):
            return "post_check_failed_rollback_failed"
        return "post_check_failed"
    if status.startswith("skipped"):
        return status
    if status == "success":
        return None
    rollback = row.get("rollback") if isinstance(row.get("rollback"), dict) else {}
    if rollback.get("attempted") and not rollback.get("success"):
        return "rollback_failed"
    return "execution_failed"


def _summarize_template_deploy_results(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    totals = {
        "total": len(list(rows or [])),
        "success": 0,
        "failed": 0,
        "precheck_failed": 0,
        "postcheck_failed": 0,
        "skipped": 0,
        "rollback_attempted": 0,
        "rollback_success": 0,
        "rollback_failed": 0,
    }
    for row in list(rows or []):
        status = str(row.get("status") or "").strip().lower()
        if status == "success":
            totals["success"] += 1
        elif status == "precheck_failed":
            totals["precheck_failed"] += 1
            totals["failed"] += 1
        elif status == "postcheck_failed":
            totals["postcheck_failed"] += 1
            totals["failed"] += 1
        elif status.startswith("skipped"):
            totals["skipped"] += 1
        else:
            totals["failed"] += 1

        rollback = row.get("rollback") if isinstance(row.get("rollback"), dict) else {}
        if rollback.get("attempted"):
            totals["rollback_attempted"] += 1
            if rollback.get("success"):
                totals["rollback_success"] += 1
            else:
                totals["rollback_failed"] += 1
    return totals

def _deploy_worker(target: Dict[str, Any], template_content: str, opts: Dict[str, Any]):
    """
    Worker function for parallel deployment.
    target dict contains: dev_id, device_info_args, context
    """
    dev_id = target['dev_id']
    try:
        # 1. Render Template
        config_text = TemplateRenderer.render(template_content, target['context'])

        # 2. Connection Info
        info = DeviceInfo(**target['device_info_args'])
        
        # 3. Connect & Push
        conn = DeviceConnection(info)
        if conn.connect():
            backup_id = None
            backup_error = None
            rollback_prepared = False
            rollback_ref = None
            post_check = None
            pre_check = {"ok": True, "rows": []}

            pre_commands = [str(c or "").strip() for c in list(opts.get("pre_check_commands") or []) if str(c or "").strip()]
            if pre_commands:
                pre_check = _run_pre_check(conn, pre_commands)
                if not pre_check.get("ok"):
                    conn.disconnect()
                    return {
                        "id": dev_id,
                        "status": "precheck_failed",
                        "error": "Pre-check failed before deployment",
                        "backup_id": backup_id,
                        "backup_error": backup_error,
                        "rollback_prepared": rollback_prepared,
                        "rollback_ref": rollback_ref,
                        "pre_check": pre_check,
                        "post_check": post_check,
                    }

            if opts.get("save_pre_backup", True):
                db_local = SessionLocal()
                try:
                    running = conn.get_running_config()
                    b = ConfigBackup(device_id=dev_id, raw_config=running, is_golden=False)
                    db_local.add(b)
                    db_local.commit()
                    db_local.refresh(b)
                    backup_id = int(b.id)
                except Exception as e:
                    try:
                        db_local.rollback()
                    except Exception:
                        pass
                    backup_error = f"{type(e).__name__}: {e}"
                finally:
                    db_local.close()

            if opts.get("prepare_device_snapshot", True):
                snap_name = f"rollback_{dev_id}_{uuid.uuid4().hex[:10]}"
                try:
                    if hasattr(conn.driver, "prepare_rollback"):
                        ok = bool(conn.driver.prepare_rollback(snap_name))
                        rollback_prepared = ok
                        rollback_ref = getattr(conn.driver, "_rollback_ref", None) or snap_name
                except Exception:
                    rollback_prepared = False
                    rollback_ref = None

            try:
                output = conn.send_config_set(config_text.splitlines())
                if opts.get("post_check_enabled", True):
                    commands = opts.get("post_check_commands") or []
                    if not commands:
                        db_local = SessionLocal()
                        try:
                            dev = db_local.query(Device).filter(Device.id == dev_id).first()
                            if dev:
                                commands = resolve_post_check_commands(db_local, dev) or []
                        finally:
                            db_local.close()
                    if not commands:
                        commands = _default_post_check_commands(info.device_type)
                    post_check = _run_post_check(conn, info.device_type, list(commands))
                    if not post_check.get("ok"):
                        raise Exception("Post-check failed")
                conn.disconnect()
                return {
                    "id": dev_id,
                    "status": "success",
                    "output": output,
                    "backup_id": backup_id,
                    "backup_error": backup_error,
                    "rollback_prepared": rollback_prepared,
                    "rollback_ref": rollback_ref,
                    "pre_check": pre_check,
                    "post_check": post_check,
                }
            except Exception as e:
                deploy_error = str(e)
                rollback_attempted = False
                rollback_success = False
                rollback_output = None
                rollback_error = None
                rollback_duration_ms = None

                if opts.get("rollback_on_failure", True):
                    rollback_attempted = True
                    rb_started = time.perf_counter()
                    try:
                        if hasattr(conn.driver, "rollback"):
                            rollback_success = bool(conn.driver.rollback())
                        else:
                            rollback_success = False
                        rollback_output = "rollback executed" if rollback_success else "rollback not executed"
                    except Exception as re:
                        rollback_error = f"{type(re).__name__}: {re}"
                        rollback_success = False
                    finally:
                        rollback_duration_ms = int((time.perf_counter() - rb_started) * 1000)

                conn.disconnect()
                failure_status = "postcheck_failed" if (isinstance(post_check, dict) and not bool(post_check.get("ok", True))) else "failed"
                return {
                    "id": dev_id,
                    "status": failure_status,
                    "error": deploy_error,
                    "backup_id": backup_id,
                    "backup_error": backup_error,
                    "rollback_attempted": rollback_attempted,
                    "rollback_success": rollback_success,
                    "rollback_duration_ms": rollback_duration_ms,
                    "rollback_output": rollback_output,
                    "rollback_error": rollback_error,
                    "rollback_prepared": rollback_prepared,
                    "rollback_ref": rollback_ref,
                    "pre_check": pre_check,
                    "post_check": post_check,
                }
        else:
            return {"id": dev_id, "status": "failed", "error": f"Connection Failed: {conn.last_error}"}

    except Exception as e:
        return {"id": dev_id, "status": "failed", "error": str(e)}


# --- Schemas ---
class ConfigTemplateCreate(BaseModel):
    name: str
    category: str = "Switching"
    content: str
    tags: str = "v1.0"


class ConfigTemplateResponse(ConfigTemplateCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class TemplatePreviewRequest(BaseModel):
    device_id: int
    template_content: str
    variables: Dict[str, Any] = {}


class TemplateDeployRequest(BaseModel):
    device_ids: List[int]
    variables: Dict[str, Any] = {}
    save_pre_backup: bool = True
    rollback_on_failure: bool = True
    prepare_device_snapshot: bool = True
    pre_check_commands: List[str] = []
    post_check_enabled: bool = True
    post_check_commands: List[str] = []
    canary_count: int = 0
    wave_size: int = 0
    stop_on_wave_failure: bool = True
    inter_wave_delay_seconds: float = 0.0
    idempotency_key: str | None = None
    approval_id: int | None = None
    execution_id: str | None = None


class TemplateDryRunRequest(BaseModel):
    device_ids: List[int]
    variables: Dict[str, Any] = {}
    include_rendered: bool = False
    rollback_on_failure: bool = True
    post_check_enabled: bool = True
    post_check_commands: List[str] = []
    canary_count: int = 0
    wave_size: int = 0
    stop_on_wave_failure: bool = True
    inter_wave_delay_seconds: float = 0.0


# --- Endpoints ---

@router.get("/", response_model=List[ConfigTemplateResponse])
def get_templates(db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    return db.query(ConfigTemplate).all()


@router.post("/", response_model=ConfigTemplateResponse)
def create_template(template: ConfigTemplateCreate, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    db_obj = ConfigTemplate(**template.model_dump())
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.put("/{template_id}", response_model=ConfigTemplateResponse)
def update_template(template_id: int, template_in: ConfigTemplateCreate, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    db_obj = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Template not found")
    
    for key, value in template_in.model_dump().items():
        setattr(db_obj, key, value)
    
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj


@router.delete("/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    db_obj = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not db_obj:
        raise HTTPException(status_code=404, detail="Template not found")
    
    db.delete(db_obj)
    db.commit()
    return {"message": "Template deleted successfully"}


@router.post("/validate")
def validate_template(req: TemplatePreviewRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    """
    Check for missing variables without rendering
    """
    device = db.query(Device).filter(Device.id == req.device_id).first()
    if not device: raise HTTPException(404, "Device not found")

    ctx = resolve_device_context(db, device, extra=req.variables).merged
    
    missing = TemplateRenderer.validate_context(req.template_content, ctx)
    return {
        "valid": len(missing) == 0,
        "missing_variables": missing
    }

@router.post("/preview")
def preview_template(req: TemplatePreviewRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    device = db.query(Device).filter(Device.id == req.device_id).first()
    if not device: raise HTTPException(404, "Device not found")

    ctx = resolve_device_context(db, device, extra=req.variables).merged

    # Validation Check
    missing = TemplateRenderer.validate_context(req.template_content, ctx)
    if missing:
        raise HTTPException(400, f"Missing variables: {', '.join(missing)}")

    rendered = TemplateRenderer.render(req.template_content, ctx)
    return {"rendered_config": rendered}


@router.post("/{template_id}/deploy")
def deploy_template(template_id: int, req: TemplateDeployRequest, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    template = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not template: raise HTTPException(404, "Template not found")

    target_rows = db.query(Device).filter(Device.id.in_(list(req.device_ids or []))).all()
    by_id = {int(d.id): d for d in target_rows}
    ordered_rows = [by_id[int(did)] for did in list(req.device_ids or []) if int(did) in by_id]
    approval_id = int(req.approval_id) if req.approval_id is not None else None
    change_plan = _build_template_change_plan(
        db,
        ordered_rows,
        approval_id=approval_id,
        rollback_on_failure=bool(req.rollback_on_failure),
        canary_count=int(req.canary_count or 0),
        wave_size=int(req.wave_size or 0),
        stop_on_wave_failure=bool(req.stop_on_wave_failure),
        inter_wave_delay_seconds=float(req.inter_wave_delay_seconds or 0.0),
    )

    blocked_config = DeviceSupportPolicyService.collect_blocked_devices(
        db,
        devices=ordered_rows,
        feature="config",
    )
    if blocked_config:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEVICE_SUPPORT_BLOCKED",
                "message": "Template deploy blocked for unsupported devices.",
                "details": {"feature": "config", "blocked_devices": blocked_config},
                "change_plan": change_plan,
            },
        )

    if bool(req.rollback_on_failure):
        blocked_rollback = DeviceSupportPolicyService.collect_blocked_devices(
            db,
            devices=ordered_rows,
            feature="rollback",
        )
        if blocked_rollback:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ROLLBACK_STRATEGY_UNSUPPORTED",
                    "message": "Rollback-on-failure is blocked for devices without supported rollback strategy.",
                    "details": {
                        "feature": "rollback",
                        "blocked_devices": blocked_rollback,
                        "hint": "Disable rollback_on_failure for this batch or target rollback-supported vendors only.",
                    },
                    "change_plan": change_plan,
                },
            )

    # 1. Prepare Target List (Main Thread)
    targets = []
    for dev in ordered_rows:

        # Context Preparation
        context = resolve_device_context(db, dev, extra=req.variables).merged
        context.update({"_dev_id": dev.id})

        # Device Info
        dev_args = {
            "host": dev.ip_address,
            "username": dev.ssh_username,
            "password": dev.ssh_password,
            "secret": dev.enable_password,
            "port": dev.ssh_port or 22,
            "device_type": dev.device_type or 'cisco_ios'
        }

        targets.append({
            "dev_id": dev.id,
            "context": context,
            "device_info_args": dev_args
        })

    ordered_device_ids = [int(t["dev_id"]) for t in targets]
    if ChangePolicyService.requires_template_approval(
        db,
        target_count=len(ordered_device_ids),
        approval_id=approval_id,
    ):
        max_direct = ChangePolicyService.template_direct_max_devices(db)
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Approval required for template deploy targeting {len(ordered_device_ids)} devices "
                    f"(direct max: {max_direct}). Submit an approval request first."
                ),
                "change_plan": change_plan,
            },
        )
    execution_id = str(req.execution_id or "").strip()
    if not execution_id:
        execution_id = ChangeExecutionService.make_fingerprint(
            "template_deploy_execution",
            {
                "template_id": int(template_id),
                "device_ids": ordered_device_ids,
                "approval_id": approval_id,
                "wave_size": int(req.wave_size or 0),
                "canary_count": int(req.canary_count or 0),
            },
        )
    execution_id = ApprovalExecutionService.bind_approved_execution(
        db,
        approval_id=approval_id,
        expected_request_type="template_deploy",
        execution_id=execution_id,
    )

    waves = ChangeExecutionService.build_waves(
        ordered_device_ids,
        wave_size=int(req.wave_size or 0),
        canary_count=int(req.canary_count or 0),
    )

    idemp_key = str(req.idempotency_key or "").strip()
    if not idemp_key:
        idemp_key = ChangeExecutionService.make_fingerprint(
            "template_deploy",
            {
                "template_id": int(template_id),
                "device_ids": ordered_device_ids,
                "variables": req.variables or {},
                "save_pre_backup": bool(req.save_pre_backup),
                "rollback_on_failure": bool(req.rollback_on_failure),
                "prepare_device_snapshot": bool(req.prepare_device_snapshot),
                "pre_check_commands": list(req.pre_check_commands or []),
                "post_check_enabled": bool(req.post_check_enabled),
                "post_check_commands": list(req.post_check_commands or []),
                "wave_size": int(req.wave_size or 0),
                "canary_count": int(req.canary_count or 0),
            },
        )
    if not ChangeExecutionService.claim_idempotency("template_deploy", idemp_key, ttl_seconds=45, db=db):
        skipped = []
        for wave_no, wave in enumerate(waves, start=1):
            for dev_id in wave:
                dev = by_id.get(int(dev_id))
                skipped.append(
                    {
                        "id": int(dev_id),
                        "device_id": int(dev_id),
                        "device_name": getattr(dev, "name", None),
                        "ip_address": getattr(dev, "ip_address", None),
                        "status": "skipped_idempotent",
                        "error": "Duplicate deployment request blocked",
                        "wave": int(wave_no),
                        "approval_id": approval_id,
                        "execution_id": execution_id,
                    }
                )
        return {
            "summary": skipped,
            "totals": _summarize_template_deploy_results(skipped),
            "execution": {
                "waves_total": len(waves),
                "waves_executed": 0,
                "halted": False,
                "halted_wave": None,
                "idempotency_key": idemp_key,
                "approval_id": approval_id,
                "execution_id": execution_id,
            },
            "change_plan": change_plan,
            "approval_id": approval_id,
            "execution_id": execution_id,
        }

    target_by_id = {int(t["dev_id"]): t for t in targets}
    worker_opts = {
        "save_pre_backup": bool(req.save_pre_backup),
        "rollback_on_failure": bool(req.rollback_on_failure),
        "prepare_device_snapshot": bool(req.prepare_device_snapshot),
        "pre_check_commands": list(req.pre_check_commands or []),
        "post_check_enabled": bool(req.post_check_enabled),
        "post_check_commands": list(req.post_check_commands or []),
    }

    def _run_wave(wave_device_ids: List[int], wave_no: int) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        if not wave_device_ids:
            return rows
        max_workers = max(1, min(20, len(wave_device_ids)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_deploy_worker, target_by_id[int(did)], template.content, worker_opts): int(did)
                for did in wave_device_ids
                if int(did) in target_by_id
            }
            for future in as_completed(future_map):
                dev_id = int(future_map[future])
                try:
                    res = dict(future.result() or {})
                except Exception as e:
                    res = {"id": dev_id, "status": "failed", "error": str(e)}
                res["wave"] = int(wave_no)
                rows.append(res)
        rows.sort(key=lambda r: int(r.get("id") or 0))
        return rows

    wave_out = ChangeExecutionService.execute_wave_batches(
        waves,
        _run_wave,
        stop_on_wave_failure=bool(req.stop_on_wave_failure),
        inter_wave_delay_seconds=float(req.inter_wave_delay_seconds or 0.0),
    )
    results = list(wave_out.get("results") or [])
    normalized_results: List[Dict[str, Any]] = []
    for row in results:
        did = int(row.get("id") or row.get("device_id") or 0)
        dev = by_id.get(did)
        support_summary = _compact_support_policy(DeviceSupportPolicyService.evaluate_device(db, dev)) if dev else {}
        pre_check = row.get("pre_check") if isinstance(row.get("pre_check"), dict) else {"ok": True, "rows": []}
        post_check = row.get("post_check") if isinstance(row.get("post_check"), dict) else None
        rollback = {
            "attempted": bool(row.get("rollback_attempted")),
            "success": bool(row.get("rollback_success")),
            "duration_ms": row.get("rollback_duration_ms"),
            "prepared": bool(row.get("rollback_prepared")),
            "ref": row.get("rollback_ref"),
            "output": row.get("rollback_output"),
            "error": row.get("rollback_error"),
        }
        backup = {
            "id": row.get("backup_id"),
            "error": row.get("backup_error"),
        }
        normalized = dict(row or {})
        normalized.setdefault("id", did)
        normalized.setdefault("device_id", did)
        normalized["device_name"] = getattr(dev, "name", None)
        normalized["ip_address"] = getattr(dev, "ip_address", None)
        normalized["approval_id"] = approval_id
        normalized["execution_id"] = execution_id
        normalized["support_policy"] = support_summary
        normalized["pre_check"] = pre_check
        normalized["post_check"] = post_check
        normalized["rollback"] = rollback
        normalized["backup"] = backup
        normalized["failure_cause"] = _derive_failure_cause(normalized)
        normalized_results.append(normalized)
    try:
        ChangeExecutionService.emit_change_kpi_events(
            db,
            rows=normalized_results,
            change_type="template_deploy",
            source="Template",
            default_approval_id=approval_id,
            default_execution_id=execution_id,
            commit=True,
        )
    except Exception:
        pass
    execution = dict(wave_out.get("execution") or {})
    execution["idempotency_key"] = idemp_key
    execution["approval_id"] = approval_id
    execution["execution_id"] = execution_id
    out = {
        "summary": normalized_results,
        "totals": _summarize_template_deploy_results(normalized_results),
        "execution": execution,
        "change_plan": change_plan,
        "approval_id": approval_id,
        "execution_id": execution_id,
    }
    ApprovalExecutionService.finalize_approval_execution(
        db,
        approval_id=approval_id,
        execution_id=execution_id,
        result=out,
    )
    return out


@router.post("/{template_id}/dry-run")
def dry_run_template(
    template_id: int,
    req: TemplateDryRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    template = db.query(ConfigTemplate).filter(ConfigTemplate.id == template_id).first()
    if not template:
        raise HTTPException(404, "Template not found")

    target_rows = db.query(Device).filter(Device.id.in_(list(req.device_ids or []))).all()
    by_id = {int(d.id): d for d in target_rows}
    ordered_rows = [by_id[int(did)] for did in list(req.device_ids or []) if int(did) in by_id]
    change_plan = _build_template_change_plan(
        db,
        ordered_rows,
        approval_id=None,
        rollback_on_failure=bool(req.rollback_on_failure),
        canary_count=int(req.canary_count or 0),
        wave_size=int(req.wave_size or 0),
        stop_on_wave_failure=bool(req.stop_on_wave_failure),
        inter_wave_delay_seconds=float(req.inter_wave_delay_seconds or 0.0),
    )

    results = []
    requested_post_check_commands = list(req.post_check_commands or []) if bool(req.post_check_enabled) else []
    for dev_id in req.device_ids:
        dev = db.query(Device).filter(Device.id == dev_id).first()
        if not dev:
            continue
        guard = _build_device_change_guard(
            db,
            dev,
            requested_post_check_commands=requested_post_check_commands,
            rollback_on_failure=bool(req.rollback_on_failure),
            post_check_enabled=bool(req.post_check_enabled),
        )

        ctx = resolve_device_context(db, dev, extra=req.variables).merged
        missing = TemplateRenderer.validate_context(template.content, ctx)
        if missing:
            results.append(
                {
                    "device_id": dev.id,
                    "device_name": dev.name,
                    "status": "missing_variables",
                    "missing_variables": missing,
                    "support_policy": guard["support_policy"],
                    "pre_check_commands": guard["pre_check_commands"],
                    "post_check_commands": guard["post_check_commands"],
                    "change_guard": {
                        "deploy_allowed": guard["deploy_allowed"],
                        "rollback_supported": guard["rollback_supported"],
                        "blocked_reasons": guard["blocked_reasons"],
                    },
                    "diff_lines": [],
                    "diff_summary": {
                        "has_changes": False,
                        "before_lines": 0,
                        "after_lines": 0,
                        "added_lines": 0,
                        "removed_lines": 0,
                        "changed_lines_estimate": 0,
                        "context_lines": 0,
                        "total_diff_lines": 0,
                        "preview": [],
                        "preview_truncated": False,
                    },
                }
            )
            continue

        rendered = TemplateRenderer.render(template.content, ctx)
        latest = (
            db.query(ConfigBackup)
            .filter(ConfigBackup.device_id == dev.id)
            .order_by(ConfigBackup.created_at.desc())
            .first()
        )
        old = (latest.raw_config or "") if latest else ""
        diff_payload = _build_text_diff(old, rendered)

        payload = {
            "device_id": dev.id,
            "device_name": dev.name,
            "ip_address": dev.ip_address,
            "status": "ok",
            "missing_variables": [],
            "support_policy": guard["support_policy"],
            "pre_check_commands": guard["pre_check_commands"],
            "post_check_commands": guard["post_check_commands"],
            "change_guard": {
                "deploy_allowed": guard["deploy_allowed"],
                "rollback_supported": guard["rollback_supported"],
                "blocked_reasons": guard["blocked_reasons"],
            },
            "diff_lines": diff_payload["diff_lines"],
            "diff_summary": diff_payload["diff_summary"],
        }
        if req.include_rendered:
            payload["rendered_config"] = rendered
        results.append(payload)

    return {
        "summary": results,
        "change_plan": change_plan,
        "totals": {
            "total": len(results),
            "ok": sum(1 for row in results if str(row.get("status") or "").strip().lower() == "ok"),
            "missing_variables": sum(1 for row in results if str(row.get("status") or "").strip().lower() == "missing_variables"),
        },
    }
