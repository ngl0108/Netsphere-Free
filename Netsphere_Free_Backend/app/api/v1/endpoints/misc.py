from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from typing import List, Dict, Any, Optional
import random
import json
import math
import bisect
from datetime import datetime, timedelta

from app.db.session import get_db
from app.api import deps
# [수정] Issue, ComplianceReport, SystemMetric 모델 추가 임포트
from app.models.device import Site, FirmwareImage, Policy, Device, ConfigTemplate, Issue, ComplianceReport, SystemMetric, EventLog
from app.models.settings import SystemSetting
from app.models.user import User
from app.services.closed_loop_service import ClosedLoopService
from app.services.issue_approval_context_service import IssueApprovalContextService
from app.services.issue_sop_service import IssueSopService
from app.services.known_error_service import KnownErrorService
from app.services.operation_action_service import OperationActionService
from app.services.service_group_service import ServiceGroupService
from app.services.state_history_service import StateHistoryService
from app.schemas.device import (
    SiteResponse, FirmwareImageResponse, PolicyResponse, UserResponse,
    Token, UserLogin, DashboardStats
)

router = APIRouter()


def _safe_parse_json_payload(raw: Any) -> Optional[Dict[str, Any]]:
    if isinstance(raw, dict):
        return raw
    try:
        obj = json.loads(str(raw or ""))
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _safe_int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _is_closed_loop_kpi_event(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if str(payload.get("status") or "").strip().lower() != "ok":
        return False
    if bool(payload.get("dry_run")):
        return False
    return True


def _load_latest_metric_map(db: Session, device_ids: List[int]) -> Dict[int, Any]:
    ids = [int(v) for v in list(device_ids or []) if int(v or 0) > 0]
    if not ids:
        return {}
    rows = (
        db.query(
            SystemMetric.device_id,
            SystemMetric.cpu_usage,
            SystemMetric.memory_usage,
            SystemMetric.traffic_in,
            SystemMetric.traffic_out,
            SystemMetric.timestamp,
        )
        .filter(SystemMetric.device_id.in_(ids))
        .order_by(SystemMetric.device_id.asc(), SystemMetric.timestamp.desc())
        .all()
    )
    out: Dict[int, Any] = {}
    for row in rows:
        device_id = int(getattr(row, "device_id", 0) or 0)
        if device_id > 0 and device_id not in out:
            out[device_id] = row
    return out


def _build_active_issue_stats(rows: List[Issue]) -> Dict[str, Any]:
    by_device: Dict[str, int] = {}
    by_category: Dict[str, int] = {}
    by_severity: Dict[str, int] = {}
    for issue in list(rows or []):
        device_id = int(getattr(issue, "device_id", 0) or 0)
        category = str(getattr(issue, "category", "system") or "system").strip().lower() or "system"
        severity = str(getattr(issue, "severity", "info") or "info").strip().lower() or "info"
        if device_id > 0:
            key = str(device_id)
            by_device[key] = int(by_device.get(key) or 0) + 1
        by_category[category] = int(by_category.get(category) or 0) + 1
        by_severity[severity] = int(by_severity.get(severity) or 0) + 1
    return {
        "total": len(list(rows or [])),
        "by_device": by_device,
        "by_category": by_category,
        "by_severity": by_severity,
    }


def _compact_issue_automation(preview: Dict[str, Any]) -> Dict[str, Any]:
    body = preview if isinstance(preview, dict) else {}
    return {
        "engine_enabled": bool(body.get("engine_enabled")),
        "auto_execute_enabled": bool(body.get("auto_execute_enabled")),
        "direct_change_actions_enabled": bool(body.get("direct_change_actions_enabled")),
        "rules_total": int(body.get("rules_total") or 0),
        "matched_rules": int(body.get("matched_rules") or 0),
        "ready_rules": int(body.get("ready_rules") or 0),
        "approval_rules": int(body.get("approval_rules") or 0),
        "blocked_rules": int(body.get("blocked_rules") or 0),
        "disabled_rules": int(body.get("disabled_rules") or 0),
        "can_run": bool(body.get("can_run")),
        "primary_status": str(body.get("primary_status") or "no_match"),
        "next_action": str(body.get("next_action") or ""),
        "primary_action": body.get("primary_action") if isinstance(body.get("primary_action"), dict) else None,
    }


def _build_issue_cloud_scope(issue: Issue) -> Optional[Dict[str, Any]]:
    device = getattr(issue, "device", None)
    if not device or str(getattr(device, "device_type", "") or "").strip().lower() != "cloud_virtual":
        return None

    variables = getattr(device, "variables", None)
    if not isinstance(variables, dict):
        return None
    cloud = variables.get("cloud")
    if not isinstance(cloud, dict):
        return None
    refs = [row for row in list(cloud.get("refs") or []) if isinstance(row, dict)]
    if not refs:
        return None

    priority = {
        "virtual_machine": 1,
        "instance": 1,
        "vm": 1,
        "load_balancer": 2,
        "vpn_connection": 3,
        "vpn_tunnel": 3,
        "transit_gateway": 4,
        "tgw_attachment": 4,
        "subnet": 5,
        "vpc": 6,
        "vnet": 6,
        "network": 6,
        "route_table": 7,
        "security_group": 8,
        "nsg": 8,
        "firewall": 8,
        "acl": 8,
    }
    resource_type_labels = {
        "virtual_machine": "VM",
        "instance": "Instance",
        "vm": "VM",
        "load_balancer": "Load Balancer",
        "vpn_connection": "VPN",
        "vpn_tunnel": "VPN Tunnel",
        "transit_gateway": "Transit Gateway",
        "tgw_attachment": "TGW Attachment",
        "subnet": "Subnet",
        "vpc": "VPC",
        "vnet": "VNet",
        "network": "Network",
        "route_table": "Route Table",
        "security_group": "Security Group",
        "nsg": "NSG",
        "firewall": "Firewall",
        "acl": "ACL",
    }

    def _ref_sort_key(ref: Dict[str, Any]) -> tuple[int, int]:
        rt = str(ref.get("resource_type") or "").strip().lower()
        has_name = 0 if str(ref.get("name") or "").strip() else 1
        return int(priority.get(rt, 99)), has_name

    best_ref = min(refs, key=_ref_sort_key)
    provider = str(best_ref.get("provider") or refs[0].get("provider") or "").strip().lower()
    region = str(best_ref.get("region") or refs[0].get("region") or "").strip()
    account_name = str(best_ref.get("account_name") or refs[0].get("account_name") or "").strip() or None
    account_id = _safe_int_or_none(best_ref.get("account_id") or refs[0].get("account_id"))
    resource_type = str(best_ref.get("resource_type") or "").strip().lower() or None
    resource_types = sorted(
        {
            str(row.get("resource_type") or "").strip().lower()
            for row in refs
            if str(row.get("resource_type") or "").strip()
        }
    )
    resource_name = str(best_ref.get("name") or "").strip() or None
    resource_id = str(best_ref.get("resource_id") or "").strip() or None
    resource_type_label = resource_type_labels.get(
        resource_type or "",
        resource_type.replace("_", " ").title() if resource_type else None,
    )

    return {
        "provider": provider or None,
        "account_id": account_id,
        "account_name": account_name,
        "region": region or None,
        "resource_type": resource_type,
        "resource_type_label": resource_type_label,
        "resource_types": resource_types,
        "resource_name": resource_name,
        "resource_id": resource_id,
        "ref_count": len(refs),
        "can_create_intent": bool(provider and (account_id is not None or region or resource_type or resource_name or resource_id)),
    }


@router.get("/dashboard/stats")
def get_dashboard_stats(
    site_id: int = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    # 1. Device Filtering
    device_query = db.query(Device)
    if site_id:
        device_query = device_query.filter(Device.site_id == site_id)
    
    all_devices = device_query.all()
    target_ids = [d.id for d in all_devices]
    total_devices = len(all_devices)
    
    # Counts
    total_sites = db.query(Site).count()
    total_policies = db.query(Policy).count()
    if site_id:
        total_policies = db.query(Policy).filter(Policy.site_id == site_id).count()

    total_images = db.query(FirmwareImage).count() # Global Image
    
    # [FIX] Filter compliance count by target devices (respecting site_id)
    compliant_cnt = 0
    if target_ids:
        compliant_cnt = db.query(ComplianceReport).filter(
            ComplianceReport.status == 'compliant',
            ComplianceReport.device_id.in_(target_ids)
        ).count()

    online_cnt = 0
    alert_cnt = 0
    total_aps = 0
    total_clients = 0

    for dev in all_devices:
        status_text = str(dev.status or "offline").lower().strip()
        if status_text in ['online', 'reachable', 'up']:
            online_cnt += 1
        elif status_text in ['alert', 'warning', 'degraded']:
            alert_cnt += 1

        # [Wireless Aggregate]
        if dev.latest_parsed_data and isinstance(dev.latest_parsed_data, dict):
            w_data = dev.latest_parsed_data
            wireless_nested = w_data.get("wireless", {}) if isinstance(w_data.get("wireless"), dict) else {}
            
            c_count = w_data.get("total_clients")
            if c_count is None:
                c_count = wireless_nested.get("total_clients", 0)
            total_clients += int(c_count or 0)
            
            ap_list = wireless_nested.get("ap_list", [])
            if ap_list and isinstance(ap_list, list):
                total_aps += sum(1 for ap in ap_list if str(ap.get("status", "")).lower() in ('up', 'online', 'registered', 'reg'))
            elif "up_aps" in wireless_nested:
                total_aps += wireless_nested.get("up_aps", 0)
            elif "up_aps" in w_data:
                total_aps += w_data.get("up_aps", 0)

    offline_cnt = total_devices - (online_cnt + alert_cnt)
    if offline_cnt < 0: offline_cnt = 0

    # Health Score
    current_health_score = 0
    if total_devices > 0:
        score = ((online_cnt - (alert_cnt * 0.5)) / total_devices) * 100
        current_health_score = int(max(0, min(100, score)))

    # Traffic Trend (Real Data)
    traffic_trend = []
    if target_ids:
        ten_mins_ago = datetime.now() - timedelta(minutes=10)
        metrics = db.query(SystemMetric)\
            .filter(SystemMetric.device_id.in_(target_ids))\
            .filter(SystemMetric.timestamp >= ten_mins_ago)\
            .order_by(SystemMetric.timestamp.asc())\
            .all()
        
        trend_map = {} 
        for m in metrics:
            t_str = m.timestamp.strftime("%H:%M")
            if t_str not in trend_map: trend_map[t_str] = {"in": 0, "out": 0}
            trend_map[t_str]["in"] += (m.traffic_in or 0)
            trend_map[t_str]["out"] += (m.traffic_out or 0)
        
        start_dt = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=9)
        for i in range(10):
            curr = start_dt + timedelta(minutes=i)
            key = curr.strftime("%H:%M")
            val = trend_map.get(key, {"in": 0, "out": 0})
            traffic_trend.append({"time": key, "in": val["in"], "out": val["out"]})
    else:
        now = datetime.now()
        for i in range(10):
            t = now - timedelta(minutes=(9 - i))
            traffic_trend.append({"time": t.strftime("%H:%M"), "in": 0, "out": 0})

    # Issues
    issue_query = (
        db.query(Issue)
        .options(joinedload(Issue.device).joinedload(Device.site_obj))
        .filter(Issue.status == 'active')
    )
    if target_ids:
        issue_query = issue_query.filter(Issue.device_id.in_(target_ids))
    recent_issues = issue_query.order_by(Issue.created_at.desc()).limit(10).all()
    
    issues_data = []
    for issue in recent_issues:
        issues_data.append({
            "id": issue.id,
            "title": issue.title,
            "device": issue.device.name if issue.device else "System",
            "device_id": int(issue.device_id) if getattr(issue, "device_id", None) is not None else None,
            "site_id": int(issue.device.site_id) if issue.device and getattr(issue.device, "site_id", None) is not None else None,
            "site_name": issue.device.site_obj.name if issue.device and getattr(issue.device, "site_obj", None) else None,
            "severity": issue.severity,
            "category": issue.category or "system",
            "time": issue.created_at.isoformat()
        })

    service_group_rows = ServiceGroupService.list_groups(db)
    service_group_health_map = ServiceGroupService.build_group_health_map(db, service_group_rows)
    if site_id:
        target_id_set = {int(row_id) for row_id in target_ids}
        filtered_service_groups = []
        for group in service_group_rows:
            members = list(getattr(group, "members", []) or [])
            if any(
                str(getattr(member, "member_type", "")) == "device"
                and int(getattr(member, "device_id", 0) or 0) in target_id_set
                for member in members
            ):
                filtered_service_groups.append(group)
    else:
        filtered_service_groups = service_group_rows

    service_group_items = []
    for group in filtered_service_groups:
        health = dict(service_group_health_map.get(int(group.id)) or {})
        service_group_items.append(
            {
                "id": int(group.id),
                "name": str(group.name or ""),
                "criticality": str(group.criticality or "standard"),
                "owner_team": str(group.owner_team or "").strip() or None,
                "health_score": int(health.get("health_score") or 0),
                "health_status": str(health.get("health_status") or "review"),
                "active_issue_count": int(health.get("active_issue_count") or 0),
                "offline_device_count": int(health.get("offline_device_count") or 0),
                "managed_device_count": int(health.get("managed_device_count") or 0),
                "discovered_only_device_count": int(health.get("discovered_only_device_count") or 0),
            }
        )
    service_group_items.sort(
        key=lambda row: (
            {"critical": 0, "degraded": 1, "review": 2, "healthy": 3}.get(str(row.get("health_status") or "review"), 4),
            str(row.get("name") or "").lower(),
        )
    )
    service_group_total = len(service_group_items)
    service_group_review = sum(
        1
        for row in service_group_items
        if str(row.get("health_status") or "").strip().lower() in {"degraded", "critical", "review"}
    )
    service_group_critical = sum(
        1 for row in service_group_items if str(row.get("health_status") or "").strip().lower() == "critical"
    )
    service_group_avg_health = (
        int(round(sum(int(row.get("health_score") or 0) for row in service_group_items) / service_group_total))
        if service_group_total > 0
        else 0
    )
    state_history_summary = StateHistoryService.build_review_summary(db, limit=12)

    def _setting_float_change(key: str, default: float) -> float:
        try:
            row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if not row or row.value is None:
                return float(default)
            return float(str(row.value).strip())
        except Exception:
            return float(default)

    change_min_success_rate = _setting_float_change("ops_alerts_min_change_success_rate_pct", 98.0)
    change_max_failure_rate = _setting_float_change("ops_alerts_max_change_failure_rate_pct", 1.0)
    change_max_rollback_p95_ms = _setting_float_change("ops_alerts_max_change_rollback_p95_ms", 180000.0)
    change_min_trace_coverage = _setting_float_change("ops_alerts_min_change_trace_coverage_pct", 100.0)

    # Change execution KPI (Compliance drift remediation rollback/post-check)
    change_kpi = {
        "window_days": 30,
        "status": "idle",
        "change_success_rate_pct": 100.0,
        "change_failure_rate_pct": 0.0,
        "rollback_p95_ms": None,
        "rollback_success_rate_pct": 100.0,
        "approval_execution_trace_coverage_pct": 100.0,
        "alerts": [],
        "failure_causes": [],
        "targets": {
            "min_success_rate_pct": float(change_min_success_rate),
            "max_failure_rate_pct": float(change_max_failure_rate),
            "max_rollback_p95_ms": int(change_max_rollback_p95_ms),
            "min_trace_coverage_pct": float(change_min_trace_coverage),
        },
        "totals": {
            "events": 0,
            "success": 0,
            "failed": 0,
            "post_check_failures": 0,
            "rollback_attempted": 0,
            "rollback_success": 0,
            "approval_context_events": 0,
            "approval_traced": 0,
        },
    }
    try:
        since_kpi = datetime.now() - timedelta(days=30)
        kpi_query = db.query(EventLog).filter(
            EventLog.event_id.in_(["CONFIG_DRIFT_REMEDIATION_KPI", "CHANGE_EXECUTION_KPI"]),
            EventLog.timestamp >= since_kpi,
        )
        if site_id:
            kpi_query = kpi_query.join(Device, Device.id == EventLog.device_id).filter(Device.site_id == site_id)
        kpi_rows = kpi_query.limit(5000).all()

        parsed = []
        for row in kpi_rows:
            try:
                obj = json.loads(str(row.message or ""))
                if isinstance(obj, dict):
                    parsed.append(obj)
            except Exception:
                continue

        durations = []
        failure_causes = {}
        total_events = len(parsed)
        ok_cnt = 0
        failed_cnt = 0
        post_check_fail_cnt = 0
        rollback_attempted_cnt = 0
        rollback_success_cnt = 0
        approval_context_cnt = 0
        traced_cnt = 0

        for p in parsed:
            st = str(p.get("status") or "").strip().lower()
            if st == "ok":
                ok_cnt += 1
            else:
                failed_cnt += 1
                cause = str(p.get("failure_cause") or "unknown").strip() or "unknown"
                failure_causes[cause] = int(failure_causes.get(cause, 0)) + 1

            if bool(p.get("post_check_failed")):
                post_check_fail_cnt += 1
            if bool(p.get("rollback_attempted")):
                rollback_attempted_cnt += 1
                if bool(p.get("rollback_success")):
                    rollback_success_cnt += 1
            if bool(p.get("post_check_failed")) and bool(p.get("rollback_attempted")):
                try:
                    dur = p.get("rollback_duration_ms")
                    if dur is not None:
                        durations.append(int(dur))
                except Exception:
                    pass
            if p.get("approval_id") is not None:
                approval_context_cnt += 1
                if str(p.get("execution_id") or "").strip():
                    traced_cnt += 1

        rollback_p95 = None
        if durations:
            s = sorted(int(v) for v in durations)
            idx = min(len(s) - 1, max(0, int(math.ceil(len(s) * 0.95) - 1)))
            rollback_p95 = int(s[idx])
        change_success_rate = 100.0 if total_events == 0 else round((ok_cnt / total_events) * 100.0, 2)
        change_failure_rate = 0.0 if total_events == 0 else round((failed_cnt / total_events) * 100.0, 2)
        trace_coverage_pct = (
            100.0
            if approval_context_cnt == 0
            else round((traced_cnt / approval_context_cnt) * 100.0, 2)
        )
        alerts = []
        if total_events > 0:
            if change_success_rate < float(change_min_success_rate):
                alerts.append(
                    {
                        "code": "change_success_rate_low",
                        "title": "Change success rate is below target",
                        "value": float(change_success_rate),
                        "threshold": float(change_min_success_rate),
                    }
                )
            if change_failure_rate > float(change_max_failure_rate):
                alerts.append(
                    {
                        "code": "change_failure_rate_high",
                        "title": "Change failure rate is above target",
                        "value": float(change_failure_rate),
                        "threshold": float(change_max_failure_rate),
                    }
                )
            if rollback_p95 is not None and float(rollback_p95) > float(change_max_rollback_p95_ms):
                alerts.append(
                    {
                        "code": "change_rollback_p95_high",
                        "title": "Rollback P95 is above target",
                        "value": float(rollback_p95),
                        "threshold": float(change_max_rollback_p95_ms),
                    }
                )
            if trace_coverage_pct < float(change_min_trace_coverage):
                alerts.append(
                    {
                        "code": "change_trace_coverage_low",
                        "title": "Approval trace coverage is below target",
                        "value": float(trace_coverage_pct),
                        "threshold": float(change_min_trace_coverage),
                    }
                )
        change_status = "idle"
        if total_events > 0:
            if len(alerts) >= 2:
                change_status = "critical"
            elif alerts:
                change_status = "warning"
            else:
                change_status = "healthy"

        change_kpi = {
            "window_days": 30,
            "status": change_status,
            "change_success_rate_pct": float(change_success_rate),
            "change_failure_rate_pct": float(change_failure_rate),
            "rollback_p95_ms": rollback_p95,
            "rollback_success_rate_pct": 100.0 if rollback_attempted_cnt == 0 else round((rollback_success_cnt / rollback_attempted_cnt) * 100.0, 2),
            "approval_execution_trace_coverage_pct": float(trace_coverage_pct),
            "alerts": alerts,
            "failure_causes": sorted(
                [{"cause": k, "count": int(v)} for k, v in failure_causes.items()],
                key=lambda x: x["count"],
                reverse=True,
            )[:10],
            "targets": {
                "min_success_rate_pct": float(change_min_success_rate),
                "max_failure_rate_pct": float(change_max_failure_rate),
                "max_rollback_p95_ms": int(change_max_rollback_p95_ms),
                "min_trace_coverage_pct": float(change_min_trace_coverage),
            },
            "totals": {
                "events": int(total_events),
                "success": int(ok_cnt),
                "failed": int(failed_cnt),
                "post_check_failures": int(post_check_fail_cnt),
                "rollback_attempted": int(rollback_attempted_cnt),
                "rollback_success": int(rollback_success_cnt),
                "approval_context_events": int(approval_context_cnt),
                "approval_traced": int(traced_cnt),
            },
        }
    except Exception:
        pass

    # Closed-loop KPI (rule evaluation cycle / trigger / execution)
    def _setting_float(key: str, default: float) -> float:
        try:
            row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if not row or row.value is None:
                return float(default)
            return float(str(row.value).strip())
        except Exception:
            return float(default)

    def _setting_int(key: str, default: int) -> int:
        try:
            row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if not row or row.value is None:
                return int(default)
            return int(float(str(row.value).strip()))
        except Exception:
            return int(default)

    def _setting_bool(key: str, default: bool) -> bool:
        try:
            row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if not row or row.value is None:
                return bool(default)
            raw = str(row.value).strip().lower()
            if raw in {"1", "true", "yes", "y", "on"}:
                return True
            if raw in {"0", "false", "no", "n", "off"}:
                return False
            return bool(default)
        except Exception:
            return bool(default)

    closed_loop_engine_enabled = _setting_bool("closed_loop_engine_enabled", False)
    closed_loop_min_execute_per_trigger = _setting_float(
        "ops_alerts_min_closed_loop_execute_per_trigger_pct",
        30.0,
    )
    closed_loop_max_blocked_per_trigger = _setting_float(
        "ops_alerts_max_closed_loop_blocked_per_trigger_pct",
        70.0,
    )
    closed_loop_max_approval_per_execution = _setting_float(
        "ops_alerts_max_closed_loop_approvals_per_execution_pct",
        100.0,
    )
    closed_loop_min_cycles_30d = _setting_int("ops_alerts_min_closed_loop_cycles_30d", 1)

    closed_loop_kpi = {
        "window_days": 30,
        "engine_enabled": bool(closed_loop_engine_enabled),
        "status": "disabled" if not closed_loop_engine_enabled else "healthy",
        "alerts_count": 0,
        "alerts": [],
        "execute_per_trigger_pct": 0.0,
        "blocked_per_trigger_pct": 0.0,
        "approvals_per_execution_pct": 0.0,
        "avg_triggered_per_cycle": 0.0,
        "avg_executed_per_cycle": 0.0,
        "totals": {
            "cycles": 0,
            "triggered": 0,
            "executed": 0,
            "blocked": 0,
            "approvals_opened": 0,
        },
        "thresholds": {
            "min_execute_per_trigger_pct": float(closed_loop_min_execute_per_trigger),
            "max_blocked_per_trigger_pct": float(closed_loop_max_blocked_per_trigger),
            "max_approvals_per_execution_pct": float(closed_loop_max_approval_per_execution),
            "min_cycles_30d": int(closed_loop_min_cycles_30d),
        },
    }
    try:
        since_loop = datetime.now() - timedelta(days=30)
        loop_query = db.query(EventLog).filter(
            EventLog.event_id == "CLOSED_LOOP_EVAL_SUMMARY",
            EventLog.timestamp >= since_loop,
        )
        if site_id:
            loop_query = loop_query.filter(EventLog.device_id.is_(None))

        loop_rows = loop_query.limit(5000).all()
        cycles = 0
        triggered_total = 0
        executed_total = 0
        blocked_total = 0
        approvals_opened_total = 0

        for row in loop_rows:
            try:
                payload = json.loads(str(row.message or ""))
            except Exception:
                continue
            if not _is_closed_loop_kpi_event(payload):
                continue
            cycles += 1
            triggered_total += int(payload.get("triggered") or 0)
            executed_total += int(payload.get("executed") or 0)
            blocked_total += int(payload.get("blocked") or 0)
            approvals_opened_total += int(payload.get("approvals_opened") or 0)

        execute_per_trigger = (
            round((executed_total / triggered_total) * 100.0, 2)
            if triggered_total > 0
            else 0.0
        )
        blocked_per_trigger = (
            round((blocked_total / triggered_total) * 100.0, 2)
            if triggered_total > 0
            else 0.0
        )
        approvals_per_execution = (
            round((approvals_opened_total / executed_total) * 100.0, 2)
            if executed_total > 0
            else 0.0
        )
        avg_triggered = round((triggered_total / cycles), 2) if cycles > 0 else 0.0
        avg_executed = round((executed_total / cycles), 2) if cycles > 0 else 0.0

        loop_alerts: List[Dict[str, Any]] = []
        loop_status = "healthy"
        if closed_loop_engine_enabled:
            if cycles < int(closed_loop_min_cycles_30d):
                loop_alerts.append(
                    {
                        "code": "closed_loop_cycles_low",
                        "severity": "critical",
                        "title": "Closed-loop cycle count is below minimum",
                        "value": int(cycles),
                        "threshold": int(closed_loop_min_cycles_30d),
                        "guidance": "Check Celery beat/worker health and closed-loop scheduler configuration.",
                    }
                )
            if execute_per_trigger < float(closed_loop_min_execute_per_trigger):
                loop_alerts.append(
                    {
                        "code": "closed_loop_execute_rate_low",
                        "severity": "warning",
                        "title": "Execute/Trigger rate is below threshold",
                        "value": float(execute_per_trigger),
                        "threshold": float(closed_loop_min_execute_per_trigger),
                        "guidance": "Review rule conditions, cooldown/rate-limit, and action policy.",
                    }
                )
            if blocked_per_trigger > float(closed_loop_max_blocked_per_trigger):
                loop_alerts.append(
                    {
                        "code": "closed_loop_blocked_rate_high",
                        "severity": "warning",
                        "title": "Blocked/Trigger rate is above threshold",
                        "value": float(blocked_per_trigger),
                        "threshold": float(closed_loop_max_blocked_per_trigger),
                        "guidance": "Tune cooldown/rate-limit defaults or reduce overly strict rules.",
                    }
                )
            if approvals_per_execution > float(closed_loop_max_approval_per_execution):
                loop_alerts.append(
                    {
                        "code": "closed_loop_approval_ratio_high",
                        "severity": "warning",
                        "title": "Approvals/Execution ratio is above threshold",
                        "value": float(approvals_per_execution),
                        "threshold": float(closed_loop_max_approval_per_execution),
                        "guidance": "Rebalance auto-execution policy and approval requirements.",
                    }
                )
            if any(str(a.get("severity")) == "critical" for a in loop_alerts):
                loop_status = "critical"
            elif loop_alerts:
                loop_status = "warning"
            else:
                loop_status = "healthy"

        closed_loop_kpi = {
            "window_days": 30,
            "engine_enabled": bool(closed_loop_engine_enabled),
            "status": loop_status if closed_loop_engine_enabled else "disabled",
            "alerts_count": len(loop_alerts),
            "alerts": loop_alerts,
            "execute_per_trigger_pct": execute_per_trigger,
            "blocked_per_trigger_pct": blocked_per_trigger,
            "approvals_per_execution_pct": approvals_per_execution,
            "avg_triggered_per_cycle": avg_triggered,
            "avg_executed_per_cycle": avg_executed,
            "totals": {
                "cycles": int(cycles),
                "triggered": int(triggered_total),
                "executed": int(executed_total),
                "blocked": int(blocked_total),
                "approvals_opened": int(approvals_opened_total),
            },
            "thresholds": {
                "min_execute_per_trigger_pct": float(closed_loop_min_execute_per_trigger),
                "max_blocked_per_trigger_pct": float(closed_loop_max_blocked_per_trigger),
                "max_approvals_per_execution_pct": float(closed_loop_max_approval_per_execution),
                "min_cycles_30d": int(closed_loop_min_cycles_30d),
            },
        }
    except Exception:
        pass

    # Northbound webhook delivery KPI (ITSM/SIEM connector delivery health)
    northbound_kpi = {
        "window_days": 30,
        "status": "idle",
        "success_rate_pct": 100.0,
        "avg_attempts": 0.0,
        "p95_attempts": 0,
        "failure_causes": [],
        "modes": [],
        "totals": {
            "deliveries": 0,
            "success": 0,
            "failed": 0,
            "failed_24h": 0,
        },
    }
    try:
        now_dt = datetime.now()
        since_nb = now_dt - timedelta(days=30)
        since_24h = now_dt - timedelta(hours=24)
        nb_rows = (
            db.query(EventLog)
            .filter(
                EventLog.event_id == "NORTHBOUND_WEBHOOK_DELIVERY",
                EventLog.timestamp >= since_nb,
            )
            .order_by(EventLog.timestamp.desc())
            .limit(5000)
            .all()
        )

        deliveries = 0
        success = 0
        failed = 0
        failed_24h = 0
        attempts_values = []
        mode_counts = {}
        failure_counts = {}

        for row in nb_rows:
            try:
                payload = json.loads(str(row.message or ""))
            except Exception:
                continue
            if not isinstance(payload, dict):
                continue

            deliveries += 1
            status_text = str(payload.get("status") or "").strip().lower()
            is_success = status_text == "ok"
            if is_success:
                success += 1
            else:
                failed += 1
                if getattr(row, "timestamp", None) is not None and row.timestamp >= since_24h:
                    failed_24h += 1
                cause = str(payload.get("failure_cause") or "unknown").strip().lower() or "unknown"
                failure_counts[cause] = int(failure_counts.get(cause, 0)) + 1

            try:
                attempts_values.append(max(1, int(payload.get("attempts") or 1)))
            except Exception:
                attempts_values.append(1)

            mode = str(payload.get("mode") or "generic").strip().lower() or "generic"
            mode_counts[mode] = int(mode_counts.get(mode, 0)) + 1

        success_rate = 100.0 if deliveries == 0 else round((success / deliveries) * 100.0, 2)
        avg_attempts = round((sum(attempts_values) / len(attempts_values)), 2) if attempts_values else 0.0
        p95_attempts = 0
        if attempts_values:
            seq = sorted(int(v) for v in attempts_values)
            idx = min(len(seq) - 1, max(0, int(math.ceil(len(seq) * 0.95) - 1)))
            p95_attempts = int(seq[idx])

        status = "idle"
        if deliveries > 0:
            if success_rate < 80.0 or failed_24h > 20:
                status = "critical"
            elif success_rate < 95.0 or p95_attempts > 3 or failed_24h > 5:
                status = "warning"
            else:
                status = "healthy"

        northbound_kpi = {
            "window_days": 30,
            "status": status,
            "success_rate_pct": float(success_rate),
            "avg_attempts": float(avg_attempts),
            "p95_attempts": int(p95_attempts),
            "failure_causes": sorted(
                [{"cause": k, "count": int(v)} for k, v in failure_counts.items()],
                key=lambda x: x["count"],
                reverse=True,
            )[:10],
            "modes": sorted(
                [{"mode": k, "count": int(v)} for k, v in mode_counts.items()],
                key=lambda x: x["count"],
                reverse=True,
            )[:10],
            "totals": {
                "deliveries": int(deliveries),
                "success": int(success),
                "failed": int(failed),
                "failed_24h": int(failed_24h),
            },
        }
    except Exception:
        pass

    autonomy_min_auto_action_rate = _setting_float("ops_alerts_min_auto_action_rate_pct", 60.0)
    autonomy_max_operator_intervention_rate = _setting_float("ops_alerts_max_operator_intervention_rate_pct", 40.0)

    # Autonomy KPI (MTTD/MTTR + auto action rate)
    autonomy_kpi = {
        "window_days": 30,
        "status": "idle",
        "mttd_seconds": None,
        "mttd_p95_seconds": None,
        "mttr_seconds": None,
        "mttr_p95_seconds": None,
        "auto_action_rate_pct": 0.0,
        "operator_intervention_rate_pct": 0.0,
        "mttd_signal_coverage_pct": 0.0,
        "mttr_coverage_pct": 0.0,
        "targets": {
            "min_auto_action_rate_pct": float(autonomy_min_auto_action_rate),
            "max_operator_intervention_rate_pct": float(autonomy_max_operator_intervention_rate),
        },
        "trend_7d": [],
        "totals": {
            "issues_created": 0,
            "issues_resolved": 0,
            "mttd_samples": 0,
            "mttr_samples": 0,
            "actions_executed": 0,
            "actions_auto": 0,
            "actions_manual": 0,
        },
    }
    try:
        now_dt = datetime.now()
        since_autonomy = now_dt - timedelta(days=30)
        mttd_lookback_seconds = 6 * 3600

        issue_query = db.query(Issue).filter(Issue.created_at >= since_autonomy)
        if site_id:
            issue_query = issue_query.join(Device, Device.id == Issue.device_id).filter(Device.site_id == site_id)
        issue_rows = issue_query.order_by(Issue.created_at.desc()).limit(5000).all()

        issues_created = int(len(issue_rows))
        issues_resolved = 0
        mttr_samples: List[int] = []
        for issue in issue_rows:
            created_at = getattr(issue, "created_at", None)
            resolved_at = getattr(issue, "resolved_at", None)
            if created_at is None or resolved_at is None:
                continue
            try:
                dur = int((resolved_at - created_at).total_seconds())
                if dur >= 0:
                    issues_resolved += 1
                    mttr_samples.append(dur)
            except Exception:
                continue

        event_ts_by_device: Dict[int, List[float]] = {}
        if target_ids:
            event_rows = (
                db.query(EventLog.device_id, EventLog.timestamp, EventLog.severity)
                .filter(
                    EventLog.device_id.in_(target_ids),
                    EventLog.timestamp >= (since_autonomy - timedelta(seconds=mttd_lookback_seconds)),
                )
                .limit(20000)
                .all()
            )
            for dev_id, ts, sev in event_rows:
                if dev_id is None or ts is None:
                    continue
                sev_text = str(sev or "").strip().lower()
                if sev_text not in {"warning", "critical"}:
                    continue
                try:
                    ts_epoch = float(ts.timestamp())
                except Exception:
                    continue
                event_ts_by_device.setdefault(int(dev_id), []).append(ts_epoch)
            for ts_values in event_ts_by_device.values():
                ts_values.sort()

        mttd_samples: List[int] = []
        for issue in issue_rows:
            dev_id = getattr(issue, "device_id", None)
            created_at = getattr(issue, "created_at", None)
            if dev_id is None or created_at is None:
                continue
            ts_values = event_ts_by_device.get(int(dev_id))
            if not ts_values:
                continue
            try:
                created_epoch = float(created_at.timestamp())
            except Exception:
                continue
            idx = bisect.bisect_right(ts_values, created_epoch) - 1
            if idx < 0:
                continue
            delay = int(created_epoch - ts_values[idx])
            if delay < 0 or delay > int(mttd_lookback_seconds):
                continue
            mttd_samples.append(delay)

        def _percentile_int(values, pct):
            if not values:
                return None
            seq = sorted(int(v) for v in values)
            idx = min(len(seq) - 1, max(0, int(math.ceil(len(seq) * float(pct)) - 1)))
            return int(seq[idx])

        mttd_avg = None
        if mttd_samples:
            mttd_avg = round(sum(mttd_samples) / len(mttd_samples), 2)
        mttr_avg = None
        if mttr_samples:
            mttr_avg = round(sum(mttr_samples) / len(mttr_samples), 2)

        mttd_coverage = 100.0 if issues_created == 0 else round((len(mttd_samples) / issues_created) * 100.0, 2)
        mttr_coverage = 100.0 if issues_resolved == 0 else round((len(mttr_samples) / issues_resolved) * 100.0, 2)

        # 7-day trend for dashboard quick-read
        day_keys: List[str] = [
            (now_dt - timedelta(days=offset)).strftime("%Y-%m-%d")
            for offset in range(6, -1, -1)
        ]
        trend_7d: Dict[str, Dict[str, Any]] = {
            key: {
                "date": key,
                "issues_created": 0,
                "issues_resolved": 0,
                "actions_executed": 0,
                "actions_auto": 0,
                "actions_manual": 0,
            }
            for key in day_keys
        }
        for issue in issue_rows:
            created_at = getattr(issue, "created_at", None)
            if created_at is not None:
                k = created_at.strftime("%Y-%m-%d")
                if k in trend_7d:
                    trend_7d[k]["issues_created"] += 1
            resolved_at = getattr(issue, "resolved_at", None)
            if resolved_at is not None:
                k = resolved_at.strftime("%Y-%m-%d")
                if k in trend_7d:
                    trend_7d[k]["issues_resolved"] += 1

        loop_trend_query = db.query(EventLog).filter(
            EventLog.event_id == "CLOSED_LOOP_EVAL_SUMMARY",
            EventLog.timestamp >= (now_dt - timedelta(days=6)),
        )
        if site_id:
            loop_trend_query = loop_trend_query.filter(EventLog.device_id.is_(None))
        loop_trend_rows = loop_trend_query.limit(2000).all()
        for row in loop_trend_rows:
            ts = getattr(row, "timestamp", None)
            if ts is None:
                continue
            k = ts.strftime("%Y-%m-%d")
            if k not in trend_7d:
                continue
            try:
                payload = json.loads(str(row.message or ""))
            except Exception:
                continue
            if not _is_closed_loop_kpi_event(payload):
                continue
            executed_day = int(payload.get("executed") or 0)
            approvals_day = int(payload.get("approvals_opened") or 0)
            auto_day = max(0, executed_day - approvals_day)
            manual_day = min(executed_day, max(0, approvals_day))
            trend_7d[k]["actions_executed"] += int(executed_day)
            trend_7d[k]["actions_auto"] += int(auto_day)
            trend_7d[k]["actions_manual"] += int(manual_day)

        trend_rows: List[Dict[str, Any]] = []
        for k in day_keys:
            row = trend_7d[k]
            total_actions = int(row["actions_auto"] + row["actions_manual"])
            auto_pct = 0.0
            operator_pct = 0.0
            if total_actions > 0:
                auto_pct = round((row["actions_auto"] / total_actions) * 100.0, 2)
                operator_pct = round((row["actions_manual"] / total_actions) * 100.0, 2)
            trend_rows.append(
                {
                    "date": k,
                    "issues_created": int(row["issues_created"]),
                    "issues_resolved": int(row["issues_resolved"]),
                    "actions_executed": int(row["actions_executed"]),
                    "actions_auto": int(row["actions_auto"]),
                    "actions_manual": int(row["actions_manual"]),
                    "auto_action_rate_pct": float(auto_pct),
                    "operator_intervention_rate_pct": float(operator_pct),
                }
            )

        closed_loop_totals = closed_loop_kpi.get("totals") if isinstance(closed_loop_kpi, dict) else {}
        if not isinstance(closed_loop_totals, dict):
            closed_loop_totals = {}
        actions_executed = int(closed_loop_totals.get("executed") or 0)
        approvals_opened = int(closed_loop_totals.get("approvals_opened") or 0)
        actions_auto = max(0, actions_executed - approvals_opened)
        actions_manual = min(actions_executed, max(0, approvals_opened))
        action_total = int(actions_auto + actions_manual)

        auto_rate = 0.0
        operator_rate = 0.0
        if action_total > 0:
            auto_rate = round((actions_auto / action_total) * 100.0, 2)
            operator_rate = round((actions_manual / action_total) * 100.0, 2)

        status_text = "idle"
        if issues_created > 0 or action_total > 0:
            status_text = "healthy"
            if auto_rate < float(autonomy_min_auto_action_rate) or operator_rate > float(autonomy_max_operator_intervention_rate):
                status_text = "warning"

        autonomy_kpi = {
            "window_days": 30,
            "status": status_text,
            "mttd_seconds": mttd_avg,
            "mttd_p95_seconds": _percentile_int(mttd_samples, 0.95),
            "mttr_seconds": mttr_avg,
            "mttr_p95_seconds": _percentile_int(mttr_samples, 0.95),
            "auto_action_rate_pct": float(auto_rate),
            "operator_intervention_rate_pct": float(operator_rate),
            "mttd_signal_coverage_pct": float(mttd_coverage),
            "mttr_coverage_pct": float(mttr_coverage),
            "targets": {
                "min_auto_action_rate_pct": float(autonomy_min_auto_action_rate),
                "max_operator_intervention_rate_pct": float(autonomy_max_operator_intervention_rate),
            },
            "trend_7d": trend_rows,
            "totals": {
                "issues_created": int(issues_created),
                "issues_resolved": int(issues_resolved),
                "mttd_samples": int(len(mttd_samples)),
                "mttr_samples": int(len(mttr_samples)),
                "actions_executed": int(actions_executed),
                "actions_auto": int(actions_auto),
                "actions_manual": int(actions_manual),
            },
        }
    except Exception:
        pass

    final_data = {
        "counts": {
            "sites": total_sites,
            "devices": total_devices,
            "online": online_cnt,
            "offline": offline_cnt,
            "alert": alert_cnt,
            "policies": total_policies,
            "images": total_images,
            "wireless_aps": total_aps,
            "wireless_clients": total_clients,
            "compliant": compliant_cnt
        },
        "health_score": current_health_score,
        "issues": issues_data,
        "trafficTrend": traffic_trend,
        "service_groups": {
            "total": int(service_group_total),
            "review": int(service_group_review),
            "critical": int(service_group_critical),
            "average_health_score": int(service_group_avg_health),
            "items": service_group_items[:5],
        },
        "state_history": state_history_summary,
        "change_kpi": change_kpi,
        "closed_loop_kpi": closed_loop_kpi,
        "northbound_kpi": northbound_kpi,
        "autonomy_kpi": autonomy_kpi,
    }

    return JSONResponse(content=final_data)


@router.get("/dashboard/change-traces")
def get_dashboard_change_traces(
    days: int = Query(30, ge=1, le=365),
    site_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="ok|failed"),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    since = datetime.now() - timedelta(days=int(days))
    query = (
        db.query(EventLog)
        .filter(EventLog.event_id.in_(["CONFIG_DRIFT_REMEDIATION_KPI", "CHANGE_EXECUTION_KPI"]))
        .filter(EventLog.timestamp >= since)
    )
    if site_id is not None:
        query = query.join(Device, Device.id == EventLog.device_id).filter(Device.site_id == int(site_id))

    raw_status_filter = str(status or "").strip().lower()
    status_filter = raw_status_filter if raw_status_filter in {"ok", "failed"} else None

    sample_cap = min(20000, max(1000, int(offset) + int(limit) * 20))
    rows = query.order_by(EventLog.timestamp.desc()).limit(sample_cap).all()

    items: List[Dict[str, Any]] = []
    approval_context_events = 0
    approval_traced = 0

    for row in rows:
        payload = _safe_parse_json_payload(getattr(row, "message", None))
        if not payload:
            continue

        approval_id = _safe_int_or_none(payload.get("approval_id"))
        execution_raw = payload.get("execution_id")
        execution_id = str(execution_raw).strip() if execution_raw is not None else ""

        has_trace_context = approval_id is not None or bool(execution_id)
        if not has_trace_context:
            continue

        if approval_id is not None:
            approval_context_events += 1
            if execution_id:
                approval_traced += 1

        normalized_status = str(payload.get("status") or "").strip().lower()
        if normalized_status == "success":
            normalized_status = "ok"
        elif normalized_status not in {"ok", "failed"}:
            normalized_status = "failed" if str(payload.get("failure_cause") or "").strip() else "ok"

        if status_filter and normalized_status != status_filter:
            continue

        event_id = str(getattr(row, "event_id", "") or "").strip()
        default_change_type = "compliance_drift" if event_id == "CONFIG_DRIFT_REMEDIATION_KPI" else "change_execution"
        change_type = str(payload.get("change_type") or default_change_type).strip().lower() or default_change_type

        row_timestamp = getattr(row, "timestamp", None)
        timestamp_iso = row_timestamp.isoformat() if row_timestamp is not None else None

        items.append(
            {
                "event_id": event_id,
                "timestamp": timestamp_iso,
                "source": str(getattr(row, "source", "") or "").strip() or None,
                "device_id": _safe_int_or_none(getattr(row, "device_id", None)),
                "approval_id": approval_id,
                "execution_id": execution_id or None,
                "traced": bool(approval_id is not None and execution_id),
                "status": normalized_status,
                "change_type": change_type,
                "wave": _safe_int_or_none(payload.get("wave")),
                "failure_cause": str(payload.get("failure_cause") or "").strip().lower() or None,
                "post_check_failed": bool(payload.get("post_check_failed")),
                "rollback_attempted": bool(payload.get("rollback_attempted")),
                "rollback_success": bool(payload.get("rollback_success")),
            }
        )

    total = len(items)
    start = min(int(offset), total)
    end = min(total, start + int(limit))
    trace_coverage_pct = 100.0 if approval_context_events == 0 else round((approval_traced / approval_context_events) * 100.0, 2)

    return {
        "window_days": int(days),
        "site_id": int(site_id) if site_id is not None else None,
        "status": status_filter,
        "total": int(total),
        "offset": int(start),
        "limit": int(limit),
        "summary": {
            "approval_context_events": int(approval_context_events),
            "approval_traced": int(approval_traced),
            "trace_coverage_pct": float(trace_coverage_pct),
        },
        "items": items[start:end],
    }


# ----------------------------------------------------------------
# [NEW] 3. 알람(Issue) 센터 API (새로 추가된 부분)
# ----------------------------------------------------------------
@router.get("/issues/active")
def get_active_issues(
    category: str = Query(None, description="Filter by category: device, security, system, config, performance"),
    severity: str = Query(None, description="Filter by severity: critical, warning, info"),
    is_read: bool = Query(None, description="Filter by read status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    """
    해결되지 않은(active) 이슈 목록을 반환합니다.
    Device 정보를 조인해서 장비 이름도 같이 보냅니다.
    """
    query = db.query(Issue).options(joinedload(Issue.device).joinedload(Device.site_obj)) \
        .filter(Issue.status == 'active')
    
    # Apply filters
    if category:
        query = query.filter(Issue.category == category)
    if severity:
        query = query.filter(Issue.severity == severity)
    if is_read is not None:
        query = query.filter(Issue.is_read == is_read)
    
    issues = query.order_by(Issue.created_at.desc()).all()
    action_summary_map = OperationActionService.build_issue_summary_map(
        db,
        [int(issue.id) for issue in issues if int(getattr(issue, "id", 0) or 0) > 0],
    )
    approval_summary_map = IssueApprovalContextService.build_issue_summary_map(db, issues)
    knowledge_summary_map = KnownErrorService.build_issue_summary_map(db, issues, limit=3)
    sop_summary_map = IssueSopService.build_issue_summary_map(db, issues)
    service_impact_summary_map = ServiceGroupService.build_issue_service_impact_summary_map(db, issues)
    active_issue_stats = _build_active_issue_stats(
        db.query(Issue).options(joinedload(Issue.device).joinedload(Device.site_obj)).filter(Issue.status == 'active').all()
    )
    latest_metric_map = _load_latest_metric_map(
        db,
        [int(issue.device_id) for issue in issues if int(getattr(issue, "device_id", 0) or 0) > 0],
    )

    result = []
    for issue in issues:
        preview = ClosedLoopService.preview_issue_automation(
            db,
            issue,
            latest_metric=latest_metric_map.get(int(issue.device_id or 0)),
            issue_stats=active_issue_stats,
        )
        result.append({
            "id": issue.id,
            "title": issue.title,
            "device": issue.device.name if issue.device else "System",
            "device_id": issue.device_id,
            "site_id": int(issue.device.site_id) if issue.device and getattr(issue.device, "site_id", None) is not None else None,
            "site_name": issue.device.site_obj.name if issue.device and getattr(issue.device, "site_obj", None) else None,
            "message": issue.description,
            "severity": issue.severity,
            "category": issue.category or "system",
            "is_read": issue.is_read,
            "created_at": issue.created_at.isoformat(),
            "status": issue.status,
            "automation": _compact_issue_automation(preview),
            "action_summary": action_summary_map.get(int(issue.id)) or OperationActionService.summarize_rows([]),
            "approval_summary": approval_summary_map.get(int(issue.id)) or {"total": 0, "pending": 0, "approved": 0, "rejected": 0, "latest_status": None, "latest_approval_id": None, "evidence_ready_count": 0, "rollback_tracked_count": 0},
            "knowledge_summary": knowledge_summary_map.get(int(issue.id)) or {"recommendation_count": 0, "top_title": None},
            "sop_summary": sop_summary_map.get(int(issue.id)) or {"available": False, "readiness_status": "limited_context", "step_count": 0, "primary_title": None, "active_action_count": 0, "knowledge_match_count": 0},
            "service_impact_summary": service_impact_summary_map.get(int(issue.id)) or {
                "count": 0,
                "primary_group_id": None,
                "primary_name": None,
                "highest_criticality": None,
                "matched_member_count": 0,
                "primary_health_score": None,
                "primary_health_status": None,
                "review_group_count": 0,
                "critical_group_count": 0,
            },
            "cloud_scope": _build_issue_cloud_scope(issue),
        })

    return result


@router.get("/issues/{issue_id}/automation")
def get_issue_automation_preview(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    issue = db.query(Issue).options(joinedload(Issue.device)).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    active_issue_stats = _build_active_issue_stats(
        db.query(Issue).filter(Issue.status == 'active').all()
    )
    latest_metric = _load_latest_metric_map(
        db,
        [int(issue.device_id or 0)] if int(getattr(issue, "device_id", 0) or 0) > 0 else [],
    ).get(int(issue.device_id or 0))
    preview = ClosedLoopService.preview_issue_automation(
        db,
        issue,
        latest_metric=latest_metric,
        issue_stats=active_issue_stats,
    )
    return {
        "issue_id": int(issue.id),
        "issue_title": str(issue.title or ""),
        "automation": preview,
    }


@router.post("/issues/{issue_id}/automation/run")
def run_issue_automation(
    issue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    issue = db.query(Issue).options(joinedload(Issue.device)).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    if str(issue.status or "").strip().lower() != "active":
        raise HTTPException(status_code=400, detail="Issue automation only supports active issues")
    if not ClosedLoopService.engine_enabled(db):
        raise HTTPException(status_code=403, detail="Closed-loop engine is disabled")

    active_issue_stats = _build_active_issue_stats(
        db.query(Issue).filter(Issue.status == 'active').all()
    )
    latest_metric = _load_latest_metric_map(
        db,
        [int(issue.device_id or 0)] if int(getattr(issue, "device_id", 0) or 0) > 0 else [],
    ).get(int(issue.device_id or 0))
    preview = ClosedLoopService.preview_issue_automation(
        db,
        issue,
        latest_metric=latest_metric,
        issue_stats=active_issue_stats,
    )
    if not bool(preview.get("can_run")):
        raise HTTPException(status_code=409, detail=str(preview.get("next_action") or "Issue automation is not ready"))

    signals = ClosedLoopService.build_issue_signal_snapshot(
        issue,
        latest_metric=latest_metric,
        issue_stats=active_issue_stats,
    )
    result = ClosedLoopService.evaluate(
        db,
        signals=signals,
        actor_user=current_user,
        dry_run=False,
    )
    ClosedLoopService.emit_evaluation_summary(
        db,
        result=result,
        dry_run=False,
        source="issue_automation",
        site_id=getattr(issue.device, "site_id", None) if getattr(issue, "device", None) is not None else None,
        device_id=int(issue.device_id) if int(getattr(issue, "device_id", 0) or 0) > 0 else None,
        issue_id=int(issue.id),
        snapshot_summary=(signals.get("summary") if isinstance(signals, dict) else {}) or {},
        commit=True,
    )
    return {
        "issue_id": int(issue.id),
        "issue_title": str(issue.title or ""),
        "automation": _compact_issue_automation(preview),
        "result": result,
    }


@router.get("/issues/unread-count")
def get_unread_count(db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    """
    읽지 않은 active 이슈 개수를 반환합니다.
    """
    count = db.query(Issue).filter(
        Issue.status == 'active',
        Issue.is_read == False
    ).count()
    return {"unread_count": count}


@router.put("/issues/{issue_id}/read")
def mark_issue_as_read(issue_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_operator)):
    """
    특정 이슈를 읽음 처리합니다.
    """
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    
    issue.is_read = True
    db.commit()
    return {"message": "Issue marked as read"}


@router.put("/issues/read-all")
def mark_all_as_read(db: Session = Depends(get_db), current_user: User = Depends(deps.require_operator)):
    """
    모든 Active 이슈를 읽음 처리합니다.
    """
    db.query(Issue).filter(Issue.status == 'active', Issue.is_read == False).update(
        {"is_read": True},
        synchronize_session=False
    )
    db.commit()
    return {"message": "All issues marked as read"}


@router.put("/issues/{issue_id}/resolve")
def resolve_issue(issue_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_operator)):
    """
    특정 이슈를 'resolved' 상태로 변경하여 목록에서 제거합니다.
    """
    issue = db.query(Issue).filter(Issue.id == issue_id).first()
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")

    issue.status = "resolved"
    issue.resolved_at = datetime.now()
    issue.is_read = True
    db.commit()

    return {"message": "Issue resolved successfully"}


@router.post("/issues/resolve-all")
def resolve_all_issues(db: Session = Depends(get_db), current_user: User = Depends(deps.require_operator)):
    """
    모든 Active 이슈를 한 번에 해결 처리합니다.
    """
    db.query(Issue).filter(Issue.status == 'active').update(
        {"status": "resolved", "resolved_at": datetime.now(), "is_read": True},
        synchronize_session=False
    )
    db.commit()
    return {"message": "All issues resolved"}
