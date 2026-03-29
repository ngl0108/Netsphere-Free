from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.device import EventLog


class ApprovalEvidenceService:
    KPI_EVENT_IDS = {"CONFIG_DRIFT_REMEDIATION_KPI", "CHANGE_EXECUTION_KPI"}

    @staticmethod
    def _safe_json(value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        try:
            parsed = json.loads(str(value or ""))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _normalize_status(value: Any) -> str:
        text = str(value or "").strip().lower().replace(" ", "_")
        return text or "unknown"

    @staticmethod
    def _serialize_request(req: ApprovalRequest) -> Dict[str, Any]:
        return {
            "id": int(req.id),
            "title": str(req.title or ""),
            "description": str(req.description or ""),
            "request_type": str(req.request_type or ""),
            "status": str(req.status or ""),
            "requester_id": int(req.requester_id),
            "requester_name": getattr(req.requester, "username", None),
            "approver_id": int(req.approver_id) if req.approver_id is not None else None,
            "approver_name": getattr(req.approver, "username", None),
            "requester_comment": str(req.requester_comment or ""),
            "approver_comment": str(req.approver_comment or ""),
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "updated_at": req.updated_at.isoformat() if req.updated_at else None,
            "decided_at": req.decided_at.isoformat() if req.decided_at else None,
            "payload": dict(req.payload or {}),
        }

    @staticmethod
    def _extract_execution_diagnostics(summary_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        precheck_failed = 0
        postcheck_failed = 0
        rollback_attempted = 0
        rollback_success = 0
        failure_causes: Dict[str, int] = {}

        for row in summary_rows:
            status = ApprovalEvidenceService._normalize_status(
                row.get("status") or row.get("result", {}).get("status")
            )
            if status in {"precheck_failed", "pre_check_failed"}:
                precheck_failed += 1
            if status in {"postcheck_failed", "post_check_failed"}:
                postcheck_failed += 1

            if bool(row.get("post_check_failed")) or bool(row.get("result", {}).get("post_check_failed")):
                if status not in {"postcheck_failed", "post_check_failed"}:
                    postcheck_failed += 1

            if bool(row.get("rollback_attempted")) or bool(row.get("result", {}).get("rollback_attempted")):
                rollback_attempted += 1
            if bool(row.get("rollback_success")) or bool(row.get("result", {}).get("rollback_success")):
                rollback_success += 1

            cause = ApprovalEvidenceService._normalize_status(
                row.get("failure_cause") or row.get("result", {}).get("failure_cause")
            )
            if cause and cause != "unknown":
                failure_causes[cause] = int(failure_causes.get(cause) or 0) + 1

        top_causes = sorted(
            [{"cause": key, "count": int(count)} for key, count in failure_causes.items()],
            key=lambda item: item["count"],
            reverse=True,
        )[:5]
        return {
            "precheck_failed": int(precheck_failed),
            "postcheck_failed": int(postcheck_failed),
            "rollback_attempted": int(rollback_attempted),
            "rollback_success": int(rollback_success),
            "top_causes": top_causes,
        }

    @staticmethod
    def _build_trace_rows(db: Session, req: ApprovalRequest) -> List[Dict[str, Any]]:
        payload = dict(req.payload or {})
        approval_id = int(req.id)
        execution_id = str(payload.get("execution_id") or "").strip()
        rows = (
            db.query(EventLog)
            .filter(EventLog.event_id.in_(ApprovalEvidenceService.KPI_EVENT_IDS))
            .order_by(EventLog.timestamp.desc())
            .limit(5000)
            .all()
        )
        items: List[Dict[str, Any]] = []
        for row in rows:
            parsed = ApprovalEvidenceService._safe_json(getattr(row, "message", None))
            if not parsed:
                continue
            parsed_approval_id = parsed.get("approval_id")
            parsed_execution_id = str(parsed.get("execution_id") or "").strip()
            if parsed_approval_id != approval_id and (not execution_id or parsed_execution_id != execution_id):
                continue
            items.append(
                {
                    "event_log_id": int(row.id),
                    "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                    "event_id": str(row.event_id or ""),
                    "device_id": int(row.device_id) if row.device_id is not None else None,
                    "source": str(row.source or ""),
                    "severity": str(row.severity or ""),
                    "payload": parsed,
                }
            )
        return items

    @staticmethod
    def build_package(db: Session, req: ApprovalRequest) -> bytes:
        request_json = ApprovalEvidenceService._serialize_request(req)
        payload = dict(req.payload or {})
        execution_result = payload.get("execution_result")
        summary_rows = execution_result.get("summary") if isinstance(execution_result, dict) and isinstance(execution_result.get("summary"), list) else []
        diagnostics = ApprovalEvidenceService._extract_execution_diagnostics(summary_rows)
        trace_rows = ApprovalEvidenceService._build_trace_rows(db, req)
        summary = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "approval_id": int(req.id),
            "request_type": str(req.request_type or ""),
            "approval_status": str(req.status or ""),
            "execution_status": str(payload.get("execution_status") or ""),
            "job_id": str(payload.get("job_id") or ""),
            "execution_id": str(payload.get("execution_id") or ""),
            "trace_count": len(trace_rows),
            "diagnostics": diagnostics,
        }

        readme = (
            "NetSphere Approval Evidence Package\n"
            "=================================\n\n"
            "This bundle captures the approval request, execution summary, and linked KPI traces.\n"
            "Use it for operator review, rollback evidence, and support handoff.\n"
        )

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("README.txt", readme)
            zf.writestr("approval-request.json", json.dumps(request_json, ensure_ascii=False, indent=2, default=str))
            zf.writestr("approval-summary.json", json.dumps(summary, ensure_ascii=False, indent=2, default=str))
            zf.writestr("change-traces.json", json.dumps(trace_rows, ensure_ascii=False, indent=2, default=str))
            if execution_result is not None:
                zf.writestr("execution-result.json", json.dumps(execution_result, ensure_ascii=False, indent=2, default=str))
            if isinstance(payload.get("execution_trace"), dict):
                zf.writestr(
                    "execution-trace.json",
                    json.dumps(payload.get("execution_trace"), ensure_ascii=False, indent=2, default=str),
                )
        return buffer.getvalue()
