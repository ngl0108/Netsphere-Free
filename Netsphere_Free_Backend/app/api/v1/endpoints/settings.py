import json

from pathlib import Path
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from pydantic import BaseModel, ConfigDict

from app.db.session import get_db
from app.api import deps
from app.models.device import EventLog
from app.models.user import User
from app.models.settings import SystemSetting
from app.services.capability_profile_service import CapabilityProfileService
from app.services.device_support_policy_service import DeviceSupportPolicyService
from app.services.email_service import EmailService
from app.services.preview_edition_service import PreviewEditionService
from app.services.vendor_parser_benchmark_service import (
    DEFAULT_VENDOR_FIXTURES_ROOT,
    build_vendor_capability_matrix,
    load_vendor_fixture_cases,
    run_vendor_parser_benchmark,
    write_vendor_capability_matrix_report,
)

router = APIRouter()
REPO_ROOT = Path(__file__).resolve().parents[5]
VENDOR_MATRIX_JSON_PATH = REPO_ROOT / "docs" / "reports" / "vendor-support-matrix.latest.json"

class SettingSchema(BaseModel):
    key: str
    value: str
    description: str = None
    category: str = "General"
    model_config = ConfigDict(from_attributes=True)

class EmailTestRequest(BaseModel):
    to_email: str

class WebhookTestRequest(BaseModel):
    event_type: str = "test"
    title: str = "Test Webhook"
    message: str = "This is a test webhook from NetSphere."

class SettingUpdate(BaseModel):
    settings: Dict[str, Any]


class WebhookReplayRequest(BaseModel):
    reason: str | None = None


def _normalize_capability_profile_value(raw_value: Any) -> str:
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            raise HTTPException(status_code=400, detail="capability_profile_json must be a non-empty JSON string.")
        try:
            parsed = json.loads(text)
        except Exception:
            raise HTTPException(status_code=400, detail="capability_profile_json is not valid JSON.")
    elif isinstance(raw_value, dict):
        parsed = raw_value
    else:
        raise HTTPException(status_code=400, detail="capability_profile_json must be JSON object or JSON string.")

    normalized = CapabilityProfileService.normalize_profile(parsed)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def _normalize_vendor_support_policy_value(raw_value: Any) -> str:
    try:
        return DeviceSupportPolicyService.normalize_policy_json(raw_value)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"vendor_support_policy_json is not valid policy JSON: {exc}",
        )


def _parse_event_payload(raw_value: Any) -> Dict[str, Any]:
    try:
        parsed = json.loads(str(raw_value or ""))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


@router.get("/general")
def get_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """Get system settings. Any authenticated user can view."""
    defaults = {
        "hostname": "NetSphere-Controller",
        "contact_email": "admin@local.net",
        "product_setup_completed": "false",
        "product_edition": "preview" if str(__import__("os").getenv("NETSPHERE_EDITION", "")).strip().lower() == "preview" else "enterprise",
        "product_operating_mode": "multicloud_full",
        "product_cloud_scope": "none",
        "product_cloud_providers": "",
        "preview_capture_enabled": "true" if str(__import__("os").getenv("NETSPHERE_EDITION", "")).strip().lower() == "preview" else "false",
        "preview_contribution_upload_enabled": "true" if str(__import__("os").getenv("NETSPHERE_EDITION", "")).strip().lower() == "preview" else "false",
        "preview_contribution_opt_in_required": "true" if str(__import__("os").getenv("NETSPHERE_EDITION", "")).strip().lower() == "preview" else "false",
        "preview_contribution_participation": "unset",
        "preview_contribution_participation_recorded_at": "",
        "preview_contribution_participation_actor": "",
        "preview_contribution_locked": "false",
        "preview_contribution_change_requires_reset": "false",
        "preview_contribution_scope": PreviewEditionService.DEFAULT_CONTRIBUTION_SCOPE,
        "preview_contribution_require_consent": "true",
        "preview_allow_device_capture": "true",
        "preview_collection_allowed_commands_json": json.dumps(PreviewEditionService.DEFAULT_ALLOWED_COMMANDS, ensure_ascii=False, separators=(",", ":")),
        "preview_contribution_storage_dir": "preview_contributions",
        "preview_deployment_role": str(__import__("os").getenv("PREVIEW_DEPLOYMENT_ROLE", "standalone") or "standalone"),
        "preview_upload_target_mode": str(__import__("os").getenv("PREVIEW_UPLOAD_TARGET_MODE", "") or ""),
        "preview_remote_upload_url": str(__import__("os").getenv("PREVIEW_REMOTE_UPLOAD_URL", "") or ""),
        "preview_remote_upload_client_id": str(__import__("os").getenv("PREVIEW_REMOTE_UPLOAD_CLIENT_ID", "") or ""),
        "preview_remote_upload_token": "",
        "preview_remote_upload_timeout_seconds": str(__import__("os").getenv("PREVIEW_REMOTE_UPLOAD_TIMEOUT_SECONDS", "10") or "10"),
        "preview_accept_remote_uploads": str(__import__("os").getenv("PREVIEW_ACCEPT_REMOTE_UPLOADS", "false") or "false"),
        "preview_local_embedded_execution": str(__import__("os").getenv("PREVIEW_LOCAL_EMBEDDED_EXECUTION", "false") or "false"),
        "preview_self_registration_enabled": "true" if str(__import__("os").getenv("NETSPHERE_EDITION", "")).strip().lower() == "preview" else "false",
        "preview_installation_id": "",
        "preview_remote_upload_registered_at": "",
        "preview_remote_upload_registration_source": "",
        "preview_remote_upload_registration_state": "",
        "preview_remote_upload_registration_error": "",
        "backup_retention_days": "30",
        "log_level": "INFO",
        "session_timeout": "30",
        "max_concurrent_sessions": "0",
        "max_login_attempts": "5",
        "lockout_minutes": "15",
        "enable_2fa": "false",
        "mfa_otp_ttl_seconds": "300",
        "mfa_otp_length": "6",
        "mfa_otp_max_attempts": "5",
        "email_verify_otp_ttl_seconds": "600",
        "email_verify_otp_length": "6",
        "email_verify_otp_max_attempts": "5",
        "email_verify_resend_cooldown_seconds": "60",
        "ha_enabled": "false",
        "ha_node_id": "",
        "ha_lease_key": "netsphere-controller",
        "ha_lease_ttl_seconds": "15",
        "ha_lease_renew_interval_seconds": "5",
        "ha_standby_readonly": "true",
        "ha_leader_url": "",
        "password_min_length": "10",
        "password_required_classes": "3",
        "password_forbid_username": "true",
        "password_history_count": "5",
        "password_expire_days": "0",
        "audit_chain_enabled": "true",
        "audit_hmac_key": "",
        "audit_forward_syslog_enabled": "false",
        "audit_forward_syslog_host": "",
        "audit_forward_syslog_port": "514",
        "pii_masking_enabled": "false",
        "pii_mask_ip": "true",
        "pii_mask_mac": "true",
        "pii_mask_phone": "true",
        "pii_mask_email": "true",
        "webhook_enabled": "false",
        "webhook_url": "",
        "webhook_secret": "",
        "webhook_timeout_seconds": "5",
        "webhook_delivery_mode": "generic",
        "webhook_auth_type": "none",
        "webhook_auth_token": "",
        "webhook_auth_header_name": "Authorization",
        "webhook_jira_project_key": "",
        "webhook_jira_issue_type": "Task",
        "webhook_servicenow_table": "incident",
        "webhook_elastic_index": "netsphere-events",
        "webhook_retry_attempts": "3",
        "webhook_retry_backoff_seconds": "1",
        "webhook_retry_max_backoff_seconds": "8",
        "webhook_retry_jitter_seconds": "0.2",
        "webhook_retry_on_4xx": "false",
        "smtp_host": "smtp.gmail.com",
        "smtp_port": "587",
        "smtp_user": "",
        "smtp_password": "",
        "smtp_from": "admin@netsphere.com",
        "default_snmp_community": "public",
        "default_ssh_username": "admin",
        "default_ssh_password": "",
        "default_enable_password": "",
        "auto_sync_enabled": "true",
        "auto_sync_interval_seconds": "3",
        "auto_sync_jitter_seconds": "0.5",
        "cloud_auto_sync_enabled": "true",
        "cloud_auto_sync_interval_seconds": "30",
        "cloud_auto_sync_include_hybrid_build": "true",
        "cloud_auto_sync_include_hybrid_infer": "true",
        "cloud_auto_sync_enrich_inferred": "true",
        "cloud_auto_sync_preflight": "false",
        "change_policy_template_direct_max_devices": "3",
        "change_policy_compliance_direct_max_devices": "3",
        "change_policy_fabric_live_requires_approval": "true",
        "change_policy_cloud_bootstrap_live_requires_approval": "true",
        "intent_engine_enabled": "false",
        "intent_apply_requires_approval": "true",
        "intent_apply_execute_actions": "false",
        "intent_max_auto_apply_risk_score": "30",
        "intent_northbound_policy_enabled": "false",
        "intent_northbound_max_auto_publish_risk_score": "30",
        "closed_loop_engine_enabled": "false",
        "closed_loop_auto_execute_enabled": "false",
        "closed_loop_execute_change_actions": "false",
        "closed_loop_default_cooldown_seconds": "300",
        "closed_loop_default_max_actions_per_hour": "12",
        "closed_loop_rules_json": "[]",
        "capability_profile_json": '{"default":{"allowed_protocols":["snmp","ssh","gnmi"],"auto_reflection":{"approval":true,"topology":true,"sync":true},"read_only":false},"sites":{},"device_types":{}}',
        "vendor_support_policy_json": json.dumps(DeviceSupportPolicyService.DEFAULT_POLICY, ensure_ascii=False, separators=(",", ":")),
        "discovery_scope_include_cidrs": "",
        "discovery_scope_exclude_cidrs": "",
        "discovery_prefer_private": "true",
        "neighbor_crawl_scope_include_cidrs": "",
        "neighbor_crawl_scope_exclude_cidrs": "",
        "neighbor_crawl_prefer_private": "true",
        "auto_discovery_enabled": "false",
        "auto_discovery_interval_seconds": "1800",
        "auto_discovery_mode": "cidr",
        "auto_discovery_cidr": "192.168.1.0/24",
        "auto_discovery_seed_ip": "",
        "auto_discovery_seed_device_id": "",
        "auto_discovery_max_depth": "2",
        "auto_discovery_site_id": "",
        "auto_discovery_snmp_profile_id": "",
        "auto_discovery_snmp_version": "v2c",
        "auto_discovery_snmp_port": "161",
        "auto_discovery_refresh_topology": "true",
        "auto_topology_refresh_max_depth": "2",
        "auto_topology_refresh_max_devices": "200",
        "auto_topology_refresh_min_interval_seconds": "0.05",
        "topology_candidate_low_confidence_threshold": "0.7",
        "auto_discovery_last_run_at": "",
        "auto_discovery_last_job_id": "",
        "auto_discovery_last_job_cidr": "",
        "auto_discovery_last_error": "",
        "auto_topology_last_run_at": "",
        "auto_topology_last_job_id": "",
        "auto_topology_last_targets": "",
        "auto_topology_last_enqueued_ok": "",
        "auto_topology_last_enqueued_fail": "",
        "auto_topology_last_error": "",
        "auto_approve_enabled": "true",
        "auto_approve_min_vendor_confidence": "0.8",
        "parser_low_confidence_threshold": "0.45",
        "auto_approve_require_snmp_reachable": "true",
        "auto_approve_block_severities": "error",
        "auto_approve_trigger_topology": "true",
        "auto_approve_topology_depth": "2",
        "auto_approve_trigger_sync": "false",
        "auto_approve_trigger_monitoring": "false",
        "ops_alerts_min_auto_reflection_pct": "70",
        "ops_alerts_max_false_positive_pct": "20",
        "ops_alerts_max_low_confidence_rate_pct": "30",
        "ops_alerts_max_candidate_backlog": "100",
        "ops_alerts_max_stale_backlog_24h": "20",
        "ops_alerts_min_closed_loop_execute_per_trigger_pct": "30",
        "ops_alerts_max_closed_loop_blocked_per_trigger_pct": "70",
        "ops_alerts_max_closed_loop_approvals_per_execution_pct": "100",
        "ops_alerts_min_closed_loop_cycles_30d": "1",
        "ops_alerts_min_auto_action_rate_pct": "60",
        "ops_alerts_max_operator_intervention_rate_pct": "40",
        "ops_alerts_min_change_success_rate_pct": "98",
        "ops_alerts_max_change_failure_rate_pct": "1",
        "ops_alerts_max_change_rollback_p95_ms": "180000",
        "ops_alerts_min_change_trace_coverage_pct": "100",
        "ops_kpi_snapshot_enabled": "true",
        "ops_kpi_snapshot_require_sample_minimums": "true",
        "ops_kpi_snapshot_site_id": "",
        "ops_kpi_snapshot_discovery_days": "30",
        "ops_kpi_snapshot_discovery_limit": "300",
        "ops_kpi_snapshot_sample_min_discovery_jobs": "30",
        "ops_kpi_snapshot_sample_min_change_events": "60",
        "ops_kpi_snapshot_sample_min_northbound_deliveries": "500",
        "ops_kpi_snapshot_sample_min_autonomy_issues_created": "20",
        "ops_kpi_snapshot_sample_min_autonomy_actions_executed": "20",
        "release_evidence_refresh_enabled": "true",
        "release_evidence_refresh_profile": "ci",
        "release_evidence_refresh_include_synthetic": "false",
        "release_evidence_refresh_include_northbound_probe": "false",
        "config_drift_enabled": "true",
        "config_drift_approval_enabled": "false",
        "topology_snapshot_auto_enabled": "true",
        "topology_snapshot_auto_scope": "site",
        "topology_snapshot_auto_interval_minutes": "60",
        "topology_snapshot_auto_change_threshold_links": "10",
        "topology_snapshot_auto_on_discovery_job_complete": "true",
        "topology_snapshot_auto_on_topology_refresh": "false",
        "config_replace_vendor_dasan_nos": '{"file_systems":["flash:","bootflash:","disk0:"],"replace_commands":["configure replace {path} force","configuration replace {path} force"],"save_commands":["write memory","copy running-config startup-config"],"copy_command_template":"copy terminal: {path}"}',
        "config_replace_vendor_ubiquoss_l2": '{"file_systems":["flash:","bootflash:","disk0:"],"replace_commands":["configure replace {path} force","configuration replace {path} force"],"save_commands":["write memory","copy running-config startup-config"],"copy_command_template":"copy terminal: {path}"}',
        "config_replace_vendor_ubiquoss_l3": '{"file_systems":["flash:","bootflash:","disk0:"],"replace_commands":["configure replace {path} force","configuration replace {path} force"],"save_commands":["write memory","copy running-config startup-config"],"copy_command_template":"copy terminal: {path}"}',
        "config_replace_vendor_soltech_switch": '{"file_systems":["flash:","bootflash:","disk0:"],"replace_commands":["configure replace {path} force","configuration replace {path} force"],"save_commands":["write memory","copy running-config startup-config"],"copy_command_template":"copy terminal: {path}"}',
        "config_replace_vendor_coreedge_switch": '{"file_systems":["flash:","bootflash:","disk0:"],"replace_commands":["configure replace {path} force","configuration replace {path} force"],"save_commands":["write memory","copy running-config startup-config"],"copy_command_template":"copy terminal: {path}"}',
        "config_replace_vendor_nst_switch": '{"file_systems":["flash:","bootflash:","disk0:"],"replace_commands":["configure replace {path} force","configuration replace {path} force"],"save_commands":["write memory","copy running-config startup-config"],"copy_command_template":"copy terminal: {path}"}',
        "post_check_role_core": '["show ip bgp summary","show bgp summary","display bgp peer","show ip ospf neighbor","show ospf neighbor","display ospf peer","show lldp neighbors","show lldp neighbors detail","show clock","display clock","show version","display version","show system uptime"]',
        "post_check_role_distribution": '["show ip bgp summary","show bgp summary","display bgp peer","show ip ospf neighbor","show ospf neighbor","display ospf peer","show lldp neighbors","show clock","display clock","show version","display version","show system uptime"]',
        "post_check_role_access": '["show interfaces status","show interface status","show interfaces terse","display interface brief","show lldp neighbors","show clock","display clock","show version","display version","show system uptime"]',
        "post_check_role_edge": '["show ip route 0.0.0.0","show route 0.0.0.0","display ip routing-table 0.0.0.0","show lldp neighbors","show clock","display clock","show version","display version","show system uptime"]',
        "post_check_role_firewall": '["get system status","show system info","show clock","display clock","show version","display version","show system uptime"]',
    }
    
    settings = db.query(SystemSetting).all()
    existing_keys = {s.key for s in settings}
    
    for k, v in defaults.items():
        if k not in existing_keys:
            category = "General"
            description = "Default setting"
            if k.startswith("post_check_"):
                category = "post_check"
                description = "Default post-check profile"
            new_setting = SystemSetting(key=k, value=v, description=description, category=category)
            db.add(new_setting)
            db.commit()
    
    all_settings = db.query(SystemSetting).all()
    # Mask smtp password for safety
    result = {s.key: s.value for s in all_settings}
    if "smtp_password" in result and result["smtp_password"]:
        result["smtp_password"] = "********"
    if "default_ssh_password" in result and result["default_ssh_password"]:
        result["default_ssh_password"] = "********"
    if "default_enable_password" in result and result["default_enable_password"]:
        result["default_enable_password"] = "********"
    if "audit_hmac_key" in result and result["audit_hmac_key"]:
        result["audit_hmac_key"] = "********"
    if "webhook_secret" in result and result["webhook_secret"]:
        result["webhook_secret"] = "********"
    if "webhook_auth_token" in result and result["webhook_auth_token"]:
        result["webhook_auth_token"] = "********"
    if "preview_remote_upload_token" in result and result["preview_remote_upload_token"]:
        result["preview_remote_upload_token"] = "********"
    if "preview_intake_token" in result and result["preview_intake_token"]:
        result["preview_intake_token"] = "********"
    
    return result

@router.put("/general")
def update_settings(
    update: SettingUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin)
):
    """Update system settings (Admin only)."""
    updated_count = 0
    for key, value in update.settings.items():
        # Prevent updating with masked value
        if key in ["smtp_password", "default_ssh_password", "default_enable_password", "audit_hmac_key", "webhook_secret", "webhook_auth_token", "preview_remote_upload_token", "preview_intake_token"] and value == "********":
            continue

        if key == CapabilityProfileService.SETTING_KEY:
            value = _normalize_capability_profile_value(value)
        elif key == DeviceSupportPolicyService.SETTING_KEY:
            value = _normalize_vendor_support_policy_value(value)

        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting:
            setting.value = str(value)
            updated_count += 1
        else:
            new_setting = SystemSetting(key=key, value=str(value))
            db.add(new_setting)
            updated_count += 1
            
    db.commit()
    return {"message": "Settings updated", "count": updated_count}



@router.get("/capability-profile")
def get_capability_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return CapabilityProfileService.get_profile(db)


@router.get("/capability-profile/effective")
def get_effective_capability_profile(
    site_id: int | None = None,
    device_type: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return CapabilityProfileService.get_effective_policy(db, site_id=site_id, device_type=device_type)


@router.get("/vendor-support-matrix")
def get_vendor_support_matrix(
    refresh: bool = False,
    group: str | None = None,
    current_user: User = Depends(deps.require_viewer),
):
    if not refresh and not group and VENDOR_MATRIX_JSON_PATH.exists():
        try:
            payload = json.loads(VENDOR_MATRIX_JSON_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                payload["source"] = "cached"
                return payload
        except Exception:
            pass

    try:
        cases = load_vendor_fixture_cases(DEFAULT_VENDOR_FIXTURES_ROOT)
        if group and str(group).strip():
            allowed_groups = {x.strip().lower() for x in str(group).split(",") if x.strip()}
            cases = [c for c in cases if str(getattr(c, "fixture_group", "default")).lower() in allowed_groups]
        report = run_vendor_parser_benchmark(cases)
        matrix = build_vendor_capability_matrix(report)
        matrix["source"] = "generated"
        if not group:
            write_vendor_capability_matrix_report(matrix, VENDOR_MATRIX_JSON_PATH)
        return matrix
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to build vendor support matrix: {exc}")


@router.post("/test-email")
def test_email(
    req: EmailTestRequest, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin)
):
    """Send a test email (Admin only)."""
    result = EmailService.send_email(
        db, 
        to_email=req.to_email, 
        subject="[NetSphere] Test Email", 
        content="This is a test email from your SDN Controller. Notification system is working!"
    )
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    return {"message": "Email sent successfully"}


@router.post("/test-webhook")
def test_webhook(
    req: WebhookTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    return _run_webhook_test(req=req, db=db)


@router.post("/test-webhook-connector")
def test_webhook_connector(
    req: WebhookTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    return _run_webhook_test(req=req, db=db)


def _run_webhook_test(*, req: WebhookTestRequest, db: Session):
    from app.services.webhook_service import WebhookService

    result = WebhookService.send(
        db,
        event_type=req.event_type,
        title=req.title,
        message=req.message,
        severity="info",
        source="netmanager",
        data={"kind": "settings_test"},
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error") or "webhook failed")
    return {
        "message": "Webhook sent successfully",
        "result": {
            "mode": result.get("mode"),
            "status_code": result.get("status_code"),
            "attempts": result.get("attempts"),
            "delivery_id": result.get("delivery_id"),
        },
    }


@router.get("/webhook-deliveries")
def list_webhook_deliveries(
    status: str | None = None,
    days: int = 7,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    _ = current_user
    safe_limit = max(1, min(int(limit or 50), 200))
    safe_days = max(1, min(int(days or 7), 90))
    since = datetime.utcnow() - timedelta(days=safe_days)

    rows = (
        db.query(EventLog)
        .filter(EventLog.event_id == "NORTHBOUND_WEBHOOK_DELIVERY")
        .filter(EventLog.timestamp >= since)
        .order_by(EventLog.timestamp.desc())
        .limit(safe_limit * 5)
        .all()
    )

    normalized_status = str(status or "").strip().lower()
    status_filter = normalized_status if normalized_status in {"ok", "failed"} else None
    items: List[Dict[str, Any]] = []
    for row in rows:
        payload = _parse_event_payload(getattr(row, "message", None))
        if not payload:
            continue
        row_status = str(payload.get("status") or "").strip().lower() or "unknown"
        if status_filter and row_status != status_filter:
            continue
        replay = payload.get("replay") if isinstance(payload.get("replay"), dict) else {}
        items.append(
            {
                "event_log_id": int(row.id),
                "delivery_id": str(payload.get("delivery_id") or ""),
                "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                "status": row_status,
                "mode": str(payload.get("mode") or ""),
                "event_type": str(payload.get("event_type") or ""),
                "attempts": int(payload.get("attempts") or 0),
                "retry_attempts": int(payload.get("retry_attempts") or 0),
                "status_code": int(payload.get("status_code")) if payload.get("status_code") is not None else None,
                "failure_cause": str(payload.get("failure_cause") or "").strip() or None,
                "error": str(payload.get("error") or "").strip() or None,
                "target_host": str(payload.get("target_host") or "").strip() or None,
                "target_path": str(payload.get("target_path") or "").strip() or None,
                "replay_available": bool(replay),
                "title": str(replay.get("title") or "").strip() or None,
                "severity": str(replay.get("severity") or "").strip() or None,
                "source": str(replay.get("source") or "").strip() or None,
            }
        )
        if len(items) >= safe_limit:
            break

    return {
        "window_days": safe_days,
        "status": status_filter,
        "total": len(items),
        "items": items,
    }


@router.post("/webhook-deliveries/{delivery_id}/retry")
def retry_webhook_delivery(
    delivery_id: str,
    req: WebhookReplayRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_super_admin),
):
    _ = current_user
    from app.services.webhook_service import WebhookService

    target = None
    rows = (
        db.query(EventLog)
        .filter(EventLog.event_id == "NORTHBOUND_WEBHOOK_DELIVERY")
        .order_by(EventLog.timestamp.desc())
        .limit(500)
        .all()
    )
    for row in rows:
        payload = _parse_event_payload(getattr(row, "message", None))
        if str(payload.get("delivery_id") or "").strip() != str(delivery_id or "").strip():
            continue
        target = payload
        break

    if not target:
        raise HTTPException(status_code=404, detail="Webhook delivery not found")

    replay = target.get("replay") if isinstance(target.get("replay"), dict) else None
    if not replay:
        raise HTTPException(status_code=400, detail="This delivery does not include replay metadata")

    result = WebhookService.send(
        db,
        event_type=str(replay.get("event_type") or "retry"),
        title=str(replay.get("title") or "Retried Webhook"),
        message=str(replay.get("message") or ""),
        severity=str(replay.get("severity") or "info"),
        source=str(replay.get("source") or "netmanager"),
        data=dict(replay.get("data") or {}) | {"replay_of_delivery_id": str(delivery_id), "retry_reason": str(req.reason or "").strip()},
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error") or "webhook retry failed")

    return {
        "message": "Webhook delivery retried successfully",
        "result": {
            "mode": result.get("mode"),
            "status_code": result.get("status_code"),
            "attempts": result.get("attempts"),
            "delivery_id": result.get("delivery_id"),
            "replayed_delivery_id": str(delivery_id),
        },
    }


