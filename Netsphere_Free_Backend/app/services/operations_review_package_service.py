from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.approval import ApprovalRequest
from app.models.device import Device, Issue
from app.services.issue_approval_context_service import IssueApprovalContextService
from app.services.issue_sop_service import IssueSopService
from app.services.known_error_service import KnownErrorService
from app.services.operation_action_service import OperationActionService
from app.services.preventive_check_service import PreventiveCheckService
from app.services.release_evidence_service import get_release_evidence_snapshot
from app.services.report_export_service import (
    build_operations_review_markdown,
    build_operations_review_pdf,
)
from app.services.service_group_service import ServiceGroupService
from app.services.state_history_service import StateHistoryService


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        if getattr(value, "tzinfo", None) is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default)


def _serialize_approval_request(row: ApprovalRequest) -> dict[str, Any]:
    payload = dict(getattr(row, "payload", None) or {})
    execution_status = str(payload.get("execution_status") or "").strip().lower() or None
    return {
        "id": int(getattr(row, "id", 0) or 0),
        "title": str(getattr(row, "title", "") or ""),
        "request_type": str(getattr(row, "request_type", "") or ""),
        "status": str(getattr(row, "status", "") or "pending"),
        "execution_status": execution_status,
        "created_at": getattr(row, "created_at", None).isoformat() if getattr(row, "created_at", None) else None,
        "decided_at": getattr(row, "decided_at", None).isoformat() if getattr(row, "decided_at", None) else None,
        "requester_name": str(getattr(getattr(row, "requester", None), "username", None) or getattr(getattr(row, "requester", None), "email", None) or "operator"),
        "approver_name": str(getattr(getattr(row, "approver", None), "username", None) or getattr(getattr(row, "approver", None), "email", None) or "") or None,
        "has_evidence": bool(payload.get("execution_result") or payload.get("execution_trace")),
        "rollback_on_failure": bool(payload.get("rollback_on_failure")),
        "rollback_attempted": bool((payload.get("execution_result") or {}).get("rollback_attempted")),
    }


def build_operations_review_snapshot(
    db: Session,
    *,
    preventive_run_limit: int = 6,
    approval_limit: int = 6,
    issue_limit: int = 6,
    group_limit: int = 6,
    refresh_release_evidence: bool = False,
) -> dict[str, Any]:
    preventive_summary = PreventiveCheckService.build_summary(db)
    recent_runs = PreventiveCheckService.list_runs(db, limit=int(preventive_run_limit))

    approval_rows = (
        db.query(ApprovalRequest)
        .options(joinedload(ApprovalRequest.requester), joinedload(ApprovalRequest.approver))
        .order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
        .limit(int(approval_limit))
        .all()
    )
    approvals = [_serialize_approval_request(row) for row in approval_rows]
    approval_summary = IssueApprovalContextService.summarize_items(approvals)

    all_groups = [ServiceGroupService.serialize_group_summary(row) for row in ServiceGroupService.list_groups(db)]
    all_groups.sort(
        key=lambda row: (
            -int(ServiceGroupService.CRITICALITY_RANK.get(str(row.get("criticality") or "standard"), 1)),
            -int(row.get("member_count") or 0),
            str(row.get("name") or "").lower(),
        )
    )
    groups = all_groups[: max(1, int(group_limit))]

    issue_scan_limit = max(int(issue_limit) * 5, 30)
    issue_rows = (
        db.query(Issue)
        .options(joinedload(Issue.device).joinedload(Device.site_obj))
        .filter(Issue.status == "active")
        .order_by(Issue.created_at.desc(), Issue.id.desc())
        .limit(int(issue_scan_limit))
        .all()
    )
    action_summary_map = OperationActionService.build_issue_summary_map(
        db,
        [int(issue.id) for issue in issue_rows if int(getattr(issue, "id", 0) or 0) > 0],
    )
    approval_summary_map = IssueApprovalContextService.build_issue_summary_map(db, issue_rows)
    knowledge_summary_map = KnownErrorService.build_issue_summary_map(db, issue_rows, limit=3)
    sop_summary_map = IssueSopService.build_issue_summary_map(db, issue_rows)
    service_impact_summary_map = ServiceGroupService.build_issue_service_impact_summary_map(db, issue_rows)

    service_issues: list[dict[str, Any]] = []
    for issue in issue_rows:
        issue_id = int(getattr(issue, "id", 0) or 0)
        service_summary = service_impact_summary_map.get(issue_id) or {
            "count": 0,
            "primary_name": None,
            "highest_criticality": None,
            "matched_member_count": 0,
        }
        if int(service_summary.get("count") or 0) <= 0:
            continue
        service_issues.append(
            {
                "id": issue_id,
                "title": str(getattr(issue, "title", "") or ""),
                "severity": str(getattr(issue, "severity", "") or "info"),
                "category": str(getattr(issue, "category", "") or "system"),
                "status": str(getattr(issue, "status", "") or "active"),
                "created_at": getattr(issue, "created_at", None).isoformat() if getattr(issue, "created_at", None) else None,
                "device_name": str(getattr(getattr(issue, "device", None), "name", None) or "System"),
                "site_name": str(getattr(getattr(getattr(issue, "device", None), "site_obj", None), "name", None) or "") or None,
                "service_impact_summary": service_summary,
                "action_summary": action_summary_map.get(issue_id) or OperationActionService.summarize_rows([]),
                "approval_summary": approval_summary_map.get(issue_id) or {
                    "total": 0,
                    "pending": 0,
                    "approved": 0,
                    "rejected": 0,
                    "latest_status": None,
                    "latest_approval_id": None,
                    "evidence_ready_count": 0,
                    "rollback_tracked_count": 0,
                },
                "knowledge_summary": knowledge_summary_map.get(issue_id) or {"recommendation_count": 0, "top_title": None},
                "sop_summary": sop_summary_map.get(issue_id) or {
                    "available": False,
                    "readiness_status": "limited_context",
                    "step_count": 0,
                    "primary_title": None,
                    "active_action_count": 0,
                    "knowledge_match_count": 0,
                },
            }
        )
        if len(service_issues) >= int(issue_limit):
            break

    action_continuity_summary = {
        "issues_in_scope": len(service_issues),
        "with_active_actions": 0,
        "with_assignee": 0,
        "with_knowledge": 0,
        "with_sop_ready": 0,
        "with_approvals": 0,
        "with_evidence_ready": 0,
        "with_rollback_tracked": 0,
        "limited_context": 0,
    }
    action_continuity_items: list[dict[str, Any]] = []
    for issue in service_issues:
        service_summary = dict(issue.get("service_impact_summary") or {})
        action_summary = dict(issue.get("action_summary") or {})
        approval_ctx = dict(issue.get("approval_summary") or {})
        knowledge_summary = dict(issue.get("knowledge_summary") or {})
        sop_summary = dict(issue.get("sop_summary") or {})
        if bool(action_summary.get("has_active")):
            action_continuity_summary["with_active_actions"] += 1
        if str(action_summary.get("latest_assignee_name") or "").strip():
            action_continuity_summary["with_assignee"] += 1
        if int(knowledge_summary.get("recommendation_count") or 0) > 0:
            action_continuity_summary["with_knowledge"] += 1
        if str(sop_summary.get("readiness_status") or "").strip().lower() == "ready":
            action_continuity_summary["with_sop_ready"] += 1
        if int(approval_ctx.get("total") or 0) > 0:
            action_continuity_summary["with_approvals"] += 1
        if int(approval_ctx.get("evidence_ready_count") or 0) > 0:
            action_continuity_summary["with_evidence_ready"] += 1
        if int(approval_ctx.get("rollback_tracked_count") or 0) > 0:
            action_continuity_summary["with_rollback_tracked"] += 1
        if not bool(action_summary.get("has_active")) and int(knowledge_summary.get("recommendation_count") or 0) <= 0:
            action_continuity_summary["limited_context"] += 1
        action_continuity_items.append(
            {
                "id": int(issue.get("id") or 0),
                "title": str(issue.get("title") or ""),
                "severity": str(issue.get("severity") or "info"),
                "device_name": str(issue.get("device_name") or "System"),
                "site_name": str(issue.get("site_name") or "") or None,
                "primary_service": str(service_summary.get("primary_name") or "") or None,
                "service_group_count": int(service_summary.get("count") or 0),
                "matched_member_count": int(service_summary.get("matched_member_count") or 0),
                "action_status": str(action_summary.get("latest_status") or "open"),
                "action_total": int(action_summary.get("total") or 0),
                "action_owner": str(action_summary.get("latest_assignee_name") or "") or None,
                "action_note": str(action_summary.get("latest_note") or "") or None,
                "action_updated_at": action_summary.get("latest_updated_at"),
                "knowledge_matches": int(knowledge_summary.get("recommendation_count") or 0),
                "top_knowledge_title": str(knowledge_summary.get("top_title") or "") or None,
                "sop_status": str(sop_summary.get("readiness_status") or "limited_context"),
                "sop_step_count": int(sop_summary.get("step_count") or 0),
                "approval_total": int(approval_ctx.get("total") or 0),
                "evidence_ready_count": int(approval_ctx.get("evidence_ready_count") or 0),
                "rollback_tracked_count": int(approval_ctx.get("rollback_tracked_count") or 0),
            }
        )

    follow_up_summary = {
        "total": len(action_continuity_items),
        "needs_action": 0,
        "needs_owner": 0,
        "needs_knowledge": 0,
        "needs_evidence": 0,
        "ready_for_handoff": 0,
    }
    follow_up_items: list[dict[str, Any]] = []
    for item in action_continuity_items:
        recommended_step = "review_and_handoff"
        step_label = "Review the latest note and complete the handoff."
        priority = "normal"
        reason = "continuity_ready"
        if int(item.get("action_total") or 0) <= 0:
            recommended_step = "create_action"
            step_label = "Create an action and assign an operator before remediation continues."
            priority = "critical"
            reason = "no_action_context"
            follow_up_summary["needs_action"] += 1
        elif not str(item.get("action_owner") or "").strip():
            recommended_step = "assign_owner"
            step_label = "Assign an owner to the active action so the service issue has a clear control point."
            priority = "elevated"
            reason = "missing_owner"
            follow_up_summary["needs_owner"] += 1
        elif int(item.get("knowledge_matches") or 0) <= 0:
            recommended_step = "capture_knowledge"
            step_label = "Capture or link reusable operating knowledge before the next recurrence."
            priority = "elevated"
            reason = "missing_knowledge"
            follow_up_summary["needs_knowledge"] += 1
        elif int(item.get("approval_total") or 0) > 0 and int(item.get("evidence_ready_count") or 0) <= 0:
            recommended_step = "capture_evidence"
            step_label = "Linked approvals exist, but evidence is not ready yet. Record evidence before handoff."
            priority = "elevated"
            reason = "missing_evidence"
            follow_up_summary["needs_evidence"] += 1
        else:
            follow_up_summary["ready_for_handoff"] += 1
        follow_up_items.append(
            {
                **item,
                "recommended_step": recommended_step,
                "step_label": step_label,
                "priority": priority,
                "reason": reason,
            }
        )

    release_evidence = get_release_evidence_snapshot(refresh=bool(refresh_release_evidence))
    release_summary = dict(release_evidence.get("summary") or {}) if isinstance(release_evidence, dict) else {}
    release_sections = []
    if isinstance(release_evidence, dict) and isinstance(release_evidence.get("sections"), dict):
        release_sections = list(release_evidence["sections"].values())[:5]
    state_history = StateHistoryService.build_review_summary(db, limit=12)

    return {
        "generated_at": _utc_now().isoformat(),
        "preventive_checks": {
            "summary": preventive_summary,
            "recent_runs": recent_runs,
        },
        "approvals": {
            "summary": approval_summary,
            "items": approvals,
        },
        "service_groups": {
            "items": groups,
            "total": len(all_groups),
        },
        "service_issues": {
            "items": service_issues,
            "total": len(service_issues),
        },
        "action_continuity": {
            "summary": action_continuity_summary,
            "items": action_continuity_items,
        },
        "follow_up_agenda": {
            "summary": follow_up_summary,
            "items": follow_up_items,
        },
        "release_evidence": {
            "summary": release_summary,
            "sections": release_sections,
        },
        "state_history": state_history,
    }


def _build_readme(snapshot: dict[str, Any]) -> str:
    generated_at = str(snapshot.get("generated_at") or "")
    preventive_summary = dict((snapshot.get("preventive_checks") or {}).get("summary") or {})
    approvals_summary = dict((snapshot.get("approvals") or {}).get("summary") or {})
    service_groups = dict(snapshot.get("service_groups") or {})
    action_continuity = dict(snapshot.get("action_continuity") or {})
    action_summary = dict(action_continuity.get("summary") or {})
    follow_up_agenda = dict(snapshot.get("follow_up_agenda") or {})
    follow_up_summary = dict(follow_up_agenda.get("summary") or {})
    release_summary = dict((snapshot.get("release_evidence") or {}).get("summary") or {})
    state_history = dict(snapshot.get("state_history") or {})
    state_compare = dict(state_history.get("latest_compare") or {})

    return "\n".join(
        [
            "NetSphere Operations Review Bundle",
            "=================================",
            "",
            f"Generated at: {generated_at}",
            "",
            "Included artifacts:",
            "- operations_review.json",
            "- operations_review.md",
            "- operations_review.pdf",
            "",
            f"Preventive templates: {int(preventive_summary.get('templates_total') or 0)}",
            f"Recent preventive runs: {int(preventive_summary.get('recent_runs_total') or 0)}",
            f"Recent approvals: {int(approvals_summary.get('total') or 0)}",
            f"Pending approvals: {int(approvals_summary.get('pending') or 0)}",
            f"Service groups reviewed: {int(service_groups.get('total') or 0)}",
            f"Issues with active actions: {int(action_summary.get('with_active_actions') or 0)}",
            f"Follow-up items ready for handoff: {int(follow_up_summary.get('ready_for_handoff') or 0)}",
            f"State snapshots stored: {int(state_history.get('snapshot_count') or 0)}",
            f"Latest state review result: {str(state_compare.get('result') or 'unavailable')}",
            f"Release overall status: {str(release_summary.get('overall_status') or 'unknown')}",
            "",
            "Recommended use:",
            "- weekly operating review",
            "- preventive maintenance review",
            "- public-sector operations handoff",
            "- audit and evidence briefing",
            "",
        ]
    )


def build_operations_review_bundle(
    db: Session,
    *,
    refresh_release_evidence: bool = False,
) -> bytes:
    snapshot = build_operations_review_snapshot(
        db,
        refresh_release_evidence=bool(refresh_release_evidence),
    )
    markdown = build_operations_review_markdown(snapshot)
    pdf = build_operations_review_pdf(snapshot)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("README.txt", _build_readme(snapshot))
        zf.writestr("operations_review.json", _json_dumps(snapshot))
        zf.writestr("operations_review.md", markdown)
        zf.writestr("operations_review.pdf", pdf)
    return buf.getvalue()
