from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.device import Device, Issue
from app.services.known_error_service import KnownErrorService
from app.services.operation_action_service import OperationActionService


class IssueSopService:
    @classmethod
    def _verification_step(cls, issue: Issue) -> str:
        category = str(getattr(issue, "category", "") or "").strip().lower()
        if category == "performance":
            return "Verify that packet loss, CRC counters, and related performance alarms have returned to normal."
        if category == "security":
            return "Verify containment status, confirm suspicious traffic has stopped, and ensure related alerts are cleared."
        if category == "config":
            return "Verify the intended configuration is applied, the diff is normalized, and follow-up alerts are cleared."
        if category == "system":
            return "Verify reachability, process health, and service status are stable before closing the incident."
        return "Verify the affected scope is stable, confirm the alert has cleared, and record the validation evidence."

    @classmethod
    def _action_recommendation(cls, active_actions: list[dict[str, Any]]) -> tuple[str, str, str | None]:
        if not active_actions:
            return (
                "Create and assign an action",
                "Open an action for this alert, assign an owner, and start investigation before making changes.",
                "Create Action",
            )
        primary = active_actions[0]
        status = str(primary.get("status") or "").strip().lower()
        owner = str(primary.get("assignee_name") or "").strip() or "the assigned operator"
        if status == "open":
            return (
                "Start investigation on the active action",
                f"Continue the active action with {owner} and move it into investigation before remediation.",
                "Start Investigation",
            )
        if status == "investigating":
            return (
                "Continue the active investigation",
                f"Use the active investigation owned by {owner} as the control point for remediation and evidence.",
                "Review Action",
            )
        if status == "mitigated":
            return (
                "Validate mitigation before resolution",
                f"The active action is already mitigated. Perform verification steps with {owner} and resolve only after evidence is recorded.",
                "Review Mitigation",
            )
        return (
            "Review the latest action context",
            f"Review the latest action owned by {owner} before applying additional remediation.",
            "Open Actions",
        )

    @classmethod
    def build_issue_sop(cls, db: Session, issue: Issue) -> dict[str, Any]:
        device = getattr(issue, "device", None)
        active_actions = OperationActionService.list_for_issue(db, int(getattr(issue, "id", 0) or 0))
        knowledge_rows = KnownErrorService.build_recommendations_for_issue(db, issue, limit=3)
        top_knowledge = knowledge_rows[0] if knowledge_rows else None

        steps: list[dict[str, Any]] = []
        reasons: list[str] = []
        recommended_owner = None

        if top_knowledge:
            reasons.append("known_error_match")
        if active_actions:
            reasons.append("active_action_context")
            recommended_owner = str(active_actions[0].get("assignee_name") or "").strip() or None
        if getattr(issue, "category", None):
            reasons.append("issue_category_context")

        steps.append(
            {
                "id": "assess-scope",
                "title": "Confirm affected scope",
                "description": (
                    f"Review the alert scope for {str(getattr(device, 'name', None) or 'the affected asset')}, "
                    f"confirm severity {str(getattr(issue, 'severity', 'warning') or 'warning').lower()}, "
                    "and capture the current symptoms before remediation."
                ),
                "source_type": "issue",
                "status_hint": "required",
                "action_label": "Review Alert",
                "source_title": str(getattr(issue, "title", "") or ""),
            }
        )

        action_title, action_description, action_label = cls._action_recommendation(active_actions)
        steps.append(
            {
                "id": "action-control",
                "title": action_title,
                "description": action_description,
                "source_type": "action",
                "status_hint": "recommended",
                "action_label": action_label,
                "source_title": str(active_actions[0].get("title") or "") if active_actions else None,
            }
        )

        if top_knowledge:
            if top_knowledge.get("root_cause"):
                steps.append(
                    {
                        "id": "root-cause-hypothesis",
                        "title": "Use the matched known error as the primary hypothesis",
                        "description": str(top_knowledge.get("root_cause") or ""),
                        "source_type": "known_error",
                        "status_hint": "recommended",
                        "action_label": "Open Known Errors",
                        "source_title": str(top_knowledge.get("title") or ""),
                    }
                )
            if top_knowledge.get("workaround"):
                steps.append(
                    {
                        "id": "apply-workaround",
                        "title": "Apply the recommended workaround",
                        "description": str(top_knowledge.get("workaround") or ""),
                        "source_type": "known_error",
                        "status_hint": "recommended",
                        "action_label": "Open Known Errors",
                        "source_title": str(top_knowledge.get("title") or ""),
                    }
                )
            if top_knowledge.get("sop_summary"):
                steps.append(
                    {
                        "id": "follow-runbook",
                        "title": "Follow the stored SOP or runbook guidance",
                        "description": str(top_knowledge.get("sop_summary") or ""),
                        "source_type": "known_error",
                        "status_hint": "recommended",
                        "action_label": "Open Known Errors",
                        "source_title": str(top_knowledge.get("title") or ""),
                    }
                )
        else:
            steps.append(
                {
                    "id": "collect-evidence",
                    "title": "Collect additional evidence for this issue",
                    "description": "No matched operating knowledge is available yet. Gather CLI output, topology context, and related alerts before attempting remediation.",
                    "source_type": "issue",
                    "status_hint": "recommended",
                    "action_label": "Open Topology",
                    "source_title": str(getattr(issue, "title", "") or ""),
                }
            )

        steps.append(
            {
                "id": "verify-recovery",
                "title": "Verify recovery and clear the alert condition",
                "description": cls._verification_step(issue),
                "source_type": "verification",
                "status_hint": "required",
                "action_label": "Open Observability",
                "source_title": str(getattr(issue, "category", "") or "verification"),
            }
        )
        steps.append(
            {
                "id": "record-evidence",
                "title": "Document evidence and close the loop",
                "description": "Update the active action, capture the final note, and store the remediation as a reusable known error entry when applicable.",
                "source_type": "evidence",
                "status_hint": "required",
                "action_label": "Save Known Error",
                "source_title": str(getattr(issue, "title", "") or ""),
            }
        )

        readiness_status = "ready" if top_knowledge or active_actions else "limited_context"
        summary = "A reusable SOP is ready for this alert." if readiness_status == "ready" else "A baseline SOP is available, but it still needs operator evidence and knowledge capture."
        return {
            "issue_id": int(getattr(issue, "id", 0) or 0),
            "readiness_status": readiness_status,
            "summary": summary,
            "recommended_owner": recommended_owner,
            "reasons": reasons,
            "steps": steps,
            "active_action_count": len(active_actions),
            "matched_known_error_count": len(knowledge_rows),
            "top_known_error_title": str(top_knowledge.get("title") or "") if top_knowledge else None,
        }

    @classmethod
    def build_issue_summary_map(cls, db: Session, issues: list[Issue]) -> dict[int, dict[str, Any]]:
        out: dict[int, dict[str, Any]] = {}
        for issue in list(issues or []):
            issue_id = int(getattr(issue, "id", 0) or 0)
            if issue_id <= 0:
                continue
            payload = cls.build_issue_sop(db, issue)
            out[issue_id] = {
                "available": True,
                "readiness_status": str(payload.get("readiness_status") or "limited_context"),
                "step_count": len(list(payload.get("steps") or [])),
                "primary_title": str(payload.get("top_known_error_title") or "") or str(getattr(issue, "title", "") or ""),
                "active_action_count": int(payload.get("active_action_count") or 0),
                "knowledge_match_count": int(payload.get("matched_known_error_count") or 0),
            }
        return out

