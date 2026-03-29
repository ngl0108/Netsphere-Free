from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.services.change_execution_service import ChangeExecutionService


class ApprovalExecutionService:
    @staticmethod
    def _normalize_request_type(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def bind_approved_execution(
        db: Session,
        *,
        approval_id: int | None,
        expected_request_type: str,
        execution_id: str | None,
    ) -> str | None:
        normalized_exec_id = str(execution_id or "").strip() or None
        if approval_id is None:
            return normalized_exec_id

        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == int(approval_id)).first()
        if not req:
            raise HTTPException(status_code=404, detail=f"approval_id={int(approval_id)} not found")

        expected_type = ApprovalExecutionService._normalize_request_type(expected_request_type)
        actual_type = ApprovalExecutionService._normalize_request_type(req.request_type)
        if actual_type != expected_type:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"approval_id={int(approval_id)} is request_type={actual_type or 'unknown'}, "
                    f"expected={expected_type}"
                ),
            )

        status = ApprovalExecutionService._normalize_request_type(req.status)
        if status != "approved":
            raise HTTPException(
                status_code=409,
                detail=f"approval_id={int(approval_id)} must be approved before execution (status={status or 'unknown'})",
            )

        payload = dict(req.payload or {})
        payload_exec_id = str(payload.get("execution_id") or "").strip() or None
        resolved_exec_id = normalized_exec_id or payload_exec_id
        if payload_exec_id and normalized_exec_id and payload_exec_id != normalized_exec_id:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"approval_id={int(approval_id)} is already bound to execution_id={payload_exec_id}. "
                    "Use the same execution_id for retries."
                ),
            )

        if not resolved_exec_id:
            resolved_exec_id = ChangeExecutionService.make_fingerprint(
                f"approval_{expected_type}_execution",
                {
                    "approval_id": int(approval_id),
                    "request_type": expected_type,
                },
            )

        payload["approval_id"] = int(approval_id)
        payload["execution_id"] = str(resolved_exec_id)
        trace = payload.get("execution_trace")
        if not isinstance(trace, dict):
            trace = {}
        trace["approval_id"] = int(approval_id)
        trace["execution_id"] = str(resolved_exec_id)
        payload["execution_trace"] = trace
        current_status = ApprovalExecutionService._normalize_request_type(payload.get("execution_status"))
        if current_status in {"", "proposed"}:
            payload["execution_status"] = "bound"
        req.payload = payload
        db.add(req)
        db.commit()
        db.refresh(req)

        return str(resolved_exec_id)

    @staticmethod
    def _infer_status_from_result(result: dict[str, Any]) -> str:
        summary_obj = result.get("summary")
        if isinstance(summary_obj, dict):
            failed = int(summary_obj.get("failed") or 0)
            success = int(summary_obj.get("success") or 0)
            skipped = int(summary_obj.get("skipped") or 0)
            if failed > 0:
                return "failed"
            if success > 0:
                return "success"
            if skipped > 0:
                return "skipped"
        elif isinstance(summary_obj, list):
            failed = 0
            success = 0
            skipped = 0
            for row in summary_obj:
                st = str((row or {}).get("status") or "").strip().lower()
                if st in {"success", "ok", "dry_run"}:
                    success += 1
                elif st.startswith("skipped"):
                    skipped += 1
                else:
                    failed += 1
            if failed > 0:
                return "failed"
            if success > 0:
                return "success"
            if skipped > 0:
                return "skipped"

        fallback_status = str(result.get("status") or "").strip().lower()
        if fallback_status in {"ok", "success", "executed"}:
            return "success"
        if fallback_status in {"failed", "error"}:
            return "failed"
        if fallback_status in {"skipped", "noop"}:
            return "skipped"
        return "executed"

    @staticmethod
    def _summarize_result(result: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        summary_obj = result.get("summary")
        if isinstance(summary_obj, dict):
            out["summary"] = dict(summary_obj)
        elif isinstance(summary_obj, list):
            rows = list(summary_obj)
            failed = 0
            success = 0
            skipped = 0
            for row in rows:
                st = str((row or {}).get("status") or "").strip().lower()
                if st in {"success", "ok", "dry_run"}:
                    success += 1
                elif st.startswith("skipped"):
                    skipped += 1
                else:
                    failed += 1
            out["summary"] = {
                "total": len(rows),
                "success": int(success),
                "failed": int(failed),
                "skipped": int(skipped),
            }

        execution_obj = result.get("execution")
        if isinstance(execution_obj, dict):
            out["execution"] = {
                "waves_total": int(execution_obj.get("waves_total") or 0),
                "waves_executed": int(execution_obj.get("waves_executed") or 0),
                "halted": bool(execution_obj.get("halted")),
                "halted_wave": execution_obj.get("halted_wave"),
            }

        if result.get("approval_id") is not None:
            out["approval_id"] = int(result.get("approval_id"))
        if str(result.get("execution_id") or "").strip():
            out["execution_id"] = str(result.get("execution_id")).strip()
        return out

    @staticmethod
    def finalize_approval_execution(
        db: Session,
        *,
        approval_id: int | None,
        execution_id: str | None,
        result: dict[str, Any] | None,
    ) -> None:
        if approval_id is None:
            return

        req = db.query(ApprovalRequest).filter(ApprovalRequest.id == int(approval_id)).first()
        if not req:
            return

        payload = dict(req.payload or {})
        payload_exec_id = str(payload.get("execution_id") or "").strip() or None
        normalized_exec_id = str(execution_id or "").strip() or payload_exec_id
        if payload_exec_id and normalized_exec_id and payload_exec_id != normalized_exec_id:
            return

        payload["approval_id"] = int(approval_id)
        if normalized_exec_id:
            payload["execution_id"] = str(normalized_exec_id)
        trace = payload.get("execution_trace")
        if not isinstance(trace, dict):
            trace = {}
        trace["approval_id"] = int(approval_id)
        if normalized_exec_id:
            trace["execution_id"] = str(normalized_exec_id)
        payload["execution_trace"] = trace

        result_obj = dict(result or {})
        payload["execution_status"] = ApprovalExecutionService._infer_status_from_result(result_obj)
        payload["execution_result_summary"] = ApprovalExecutionService._summarize_result(result_obj)
        payload["executed_at"] = datetime.now().isoformat()
        req.payload = payload
        db.add(req)
        db.commit()
        db.refresh(req)
