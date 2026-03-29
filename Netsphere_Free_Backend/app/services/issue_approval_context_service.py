from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy.orm import Session, joinedload

from app.models.approval import ApprovalRequest
from app.models.device import Device, Issue


class IssueApprovalContextService:
    REQUEST_TYPE_LABELS = {
        "config_drift_remediate": "Drift Remediate",
        "template_deploy": "Template Deploy",
        "fabric_deploy": "Fabric Deploy",
        "cloud_bootstrap": "Cloud Bootstrap",
        "intent_apply": "Cloud Intent",
    }

    @staticmethod
    def _normalize_status(value: Any, *, default: str = "pending") -> str:
        text = str(value or default).strip().lower().replace(" ", "_")
        return text or default

    @staticmethod
    def _normalize_request_type(value: Any) -> str:
        text = str(value or "").strip().lower()
        return text or "generic"

    @classmethod
    def _request_type_label(cls, value: Any) -> str:
        key = cls._normalize_request_type(value)
        if key in cls.REQUEST_TYPE_LABELS:
            return cls.REQUEST_TYPE_LABELS[key]
        return key.replace("_", " ").title()

    @staticmethod
    def _safe_int_set(*values: Any) -> set[int]:
        out: set[int] = set()
        for value in values:
            if isinstance(value, (list, tuple, set)):
                for row in value:
                    try:
                        converted = int(row)
                    except Exception:
                        continue
                    if converted > 0:
                        out.add(converted)
                continue
            try:
                converted = int(value)
            except Exception:
                continue
            if converted > 0:
                out.add(converted)
        return out

    @staticmethod
    def _safe_text_set(*values: Any) -> set[str]:
        out: set[str] = set()
        for value in values:
            if isinstance(value, (list, tuple, set)):
                for row in value:
                    text = str(row or "").strip()
                    if text:
                        out.add(text)
                continue
            text = str(value or "").strip()
            if text:
                out.add(text)
        return out

    @classmethod
    def _issue_cloud_scope(cls, issue: Issue) -> dict[str, Any] | None:
        device = getattr(issue, "device", None)
        if device is None or str(getattr(device, "device_type", "") or "").strip().lower() != "cloud_virtual":
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
        account_ids = cls._safe_int_set([row.get("account_id") for row in refs])
        resource_ids = cls._safe_text_set([row.get("resource_id") for row in refs])
        regions = cls._safe_text_set([row.get("region") for row in refs])
        providers = cls._safe_text_set([str(row.get("provider") or "").strip().lower() for row in refs])
        return {
            "account_ids": account_ids,
            "resource_ids": resource_ids,
            "regions": regions,
            "providers": providers,
        }

    @classmethod
    def _payload_device_ids(cls, payload: dict[str, Any]) -> set[int]:
        return cls._safe_int_set(
            payload.get("device_id"),
            payload.get("device_ids"),
            payload.get("spine_ids"),
            payload.get("leaf_ids"),
        )

    @classmethod
    def _payload_account_ids(cls, payload: dict[str, Any]) -> set[int]:
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        normalized_intent = payload.get("normalized_intent") if isinstance(payload.get("normalized_intent"), dict) else {}
        return cls._safe_int_set(
            payload.get("account_id"),
            payload.get("account_ids"),
            context.get("account_id"),
            context.get("account_ids"),
            normalized_intent.get("account_id"),
            normalized_intent.get("account_ids"),
        )

    @classmethod
    def _payload_resource_ids(cls, payload: dict[str, Any]) -> set[str]:
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        normalized_intent = payload.get("normalized_intent") if isinstance(payload.get("normalized_intent"), dict) else {}
        return cls._safe_text_set(
            payload.get("resource_id"),
            payload.get("resource_ids"),
            context.get("resource_id"),
            context.get("resource_ids"),
            normalized_intent.get("resource_id"),
            normalized_intent.get("resource_ids"),
        )

    @classmethod
    def _payload_regions(cls, payload: dict[str, Any]) -> set[str]:
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        normalized_intent = payload.get("normalized_intent") if isinstance(payload.get("normalized_intent"), dict) else {}
        return cls._safe_text_set(
            payload.get("region"),
            payload.get("regions"),
            context.get("region"),
            context.get("regions"),
            normalized_intent.get("region"),
            normalized_intent.get("regions"),
        )

    @classmethod
    def _payload_providers(cls, payload: dict[str, Any]) -> set[str]:
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        normalized_intent = payload.get("normalized_intent") if isinstance(payload.get("normalized_intent"), dict) else {}
        return {
            str(value).strip().lower()
            for value in cls._safe_text_set(
                payload.get("provider"),
                context.get("provider"),
                normalized_intent.get("provider"),
            )
            if str(value).strip()
        }

    @classmethod
    def _execution_rows(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        execution_result = payload.get("execution_result")
        if not isinstance(execution_result, dict):
            return []
        summary = execution_result.get("summary")
        if isinstance(summary, list):
            return [row for row in summary if isinstance(row, dict)]
        results = execution_result.get("results")
        if isinstance(results, list):
            return [row for row in results if isinstance(row, dict)]
        execution_actions = execution_result.get("execution_actions")
        if isinstance(execution_actions, dict) and isinstance(execution_actions.get("results"), list):
            return [row for row in execution_actions.get("results") if isinstance(row, dict)]
        return []

    @classmethod
    def _serialize_scope_summary(cls, req: ApprovalRequest, payload: dict[str, Any]) -> str | None:
        request_type_label = cls._request_type_label(getattr(req, "request_type", None))
        device_count = len(cls._payload_device_ids(payload))
        account_count = len(cls._payload_account_ids(payload))
        resource_count = len(cls._payload_resource_ids(payload))
        if device_count > 0:
            return f"{request_type_label} · {device_count} device{'s' if device_count != 1 else ''}"
        if resource_count > 0:
            return f"{request_type_label} · {resource_count} resource{'s' if resource_count != 1 else ''}"
        if account_count > 0:
            return f"{request_type_label} · {account_count} account{'s' if account_count != 1 else ''}"
        return request_type_label

    @classmethod
    def _serialize_item(cls, req: ApprovalRequest) -> dict[str, Any]:
        payload = dict(getattr(req, "payload", None) or {})
        rows = cls._execution_rows(payload)
        rollback_attempted = False
        rollback_success = False
        post_check_failed = False
        top_cause = None
        for row in rows:
            row_status = cls._normalize_status(row.get("status") or (row.get("result") or {}).get("status"), default="unknown")
            if bool(row.get("rollback_attempted")) or bool((row.get("result") or {}).get("rollback_attempted")):
                rollback_attempted = True
            if bool(row.get("rollback_success")) or bool((row.get("result") or {}).get("rollback_success")):
                rollback_success = True
            if row_status in {"postcheck_failed", "post_check_failed"} or bool(row.get("post_check_failed")) or bool((row.get("result") or {}).get("post_check_failed")):
                post_check_failed = True
            if top_cause is None:
                candidate = str(row.get("failure_cause") or (row.get("result") or {}).get("failure_cause") or "").strip().lower()
                if candidate:
                    top_cause = candidate
        has_evidence = bool(payload.get("execution_result") or payload.get("execution_trace"))
        return {
            "id": int(req.id),
            "title": str(req.title or ""),
            "request_type": cls._normalize_request_type(getattr(req, "request_type", None)),
            "request_type_label": cls._request_type_label(getattr(req, "request_type", None)),
            "status": cls._normalize_status(getattr(req, "status", None)),
            "execution_status": cls._normalize_status(payload.get("execution_status"), default="pending") if payload else None,
            "requester_name": getattr(req.requester, "username", None),
            "approver_name": getattr(req.approver, "username", None),
            "created_at": getattr(req, "created_at", None),
            "decided_at": getattr(req, "decided_at", None),
            "has_evidence": bool(has_evidence),
            "rollback_on_failure": bool(payload.get("rollback_on_failure")),
            "rollback_attempted": bool(rollback_attempted),
            "rollback_success": bool(rollback_success),
            "post_check_failed": bool(post_check_failed),
            "scope_summary": cls._serialize_scope_summary(req, payload),
            "top_cause": top_cause,
        }

    @classmethod
    def _matches_issue(cls, issue: Issue, req: ApprovalRequest) -> tuple[bool, list[str]]:
        payload = dict(getattr(req, "payload", None) or {})
        reasons: list[str] = []
        issue_device_id = int(getattr(issue, "device_id", 0) or 0)
        if issue_device_id > 0 and issue_device_id in cls._payload_device_ids(payload):
            reasons.append("device_scope_match")

        cloud_scope = cls._issue_cloud_scope(issue)
        if cloud_scope:
            payload_resource_ids = cls._payload_resource_ids(payload)
            payload_account_ids = cls._payload_account_ids(payload)
            payload_regions = cls._payload_regions(payload)
            payload_providers = cls._payload_providers(payload)
            if cloud_scope["resource_ids"] & payload_resource_ids:
                reasons.append("cloud_resource_match")
            elif cloud_scope["account_ids"] & payload_account_ids:
                reasons.append("cloud_account_match")
            elif cloud_scope["regions"] & payload_regions and (
                not cloud_scope["providers"] or not payload_providers or cloud_scope["providers"] & payload_providers
            ):
                reasons.append("cloud_region_match")

        return (len(reasons) > 0), reasons

    @classmethod
    def _query_requests(cls, db: Session) -> list[ApprovalRequest]:
        return (
            db.query(ApprovalRequest)
            .options(joinedload(ApprovalRequest.requester), joinedload(ApprovalRequest.approver))
            .order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
            .limit(400)
            .all()
        )

    @classmethod
    def build_issue_approval_context(cls, db: Session, issue: Issue, *, limit: int = 6) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        match_reasons: set[str] = set()
        for req in cls._query_requests(db):
            matched, reasons = cls._matches_issue(issue, req)
            if not matched:
                continue
            match_reasons.update(reasons)
            items.append(cls._serialize_item(req))
            if len(items) >= int(limit):
                break
        summary = cls.summarize_items(items)
        return {
            "issue_id": int(getattr(issue, "id", 0) or 0),
            "summary": summary,
            "items": items,
            "match_reasons": sorted(match_reasons),
            "cloud_scope": cls._issue_cloud_scope(issue),
        }

    @classmethod
    def summarize_items(cls, items: Iterable[dict[str, Any]]) -> dict[str, Any]:
        summary = {
            "total": 0,
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "latest_status": None,
            "latest_approval_id": None,
            "evidence_ready_count": 0,
            "rollback_tracked_count": 0,
        }
        latest_item: dict[str, Any] | None = None
        for item in list(items or []):
            summary["total"] += 1
            status = cls._normalize_status(item.get("status"), default="pending")
            if status in {"pending", "approved", "rejected"}:
                summary[status] = int(summary.get(status) or 0) + 1
            if bool(item.get("has_evidence")):
                summary["evidence_ready_count"] += 1
            if bool(item.get("rollback_on_failure")) or bool(item.get("rollback_attempted")):
                summary["rollback_tracked_count"] += 1
            latest_item = latest_item or item
        if latest_item:
            summary["latest_status"] = cls._normalize_status(latest_item.get("status"), default="pending")
            summary["latest_approval_id"] = int(latest_item.get("id") or 0) or None
        return summary

    @classmethod
    def build_issue_summary_map(cls, db: Session, issues: Iterable[Issue], *, limit: int = 6) -> dict[int, dict[str, Any]]:
        rows = cls._query_requests(db)
        out: dict[int, dict[str, Any]] = {}
        for issue in list(issues or []):
            items: list[dict[str, Any]] = []
            for req in rows:
                matched, _ = cls._matches_issue(issue, req)
                if not matched:
                    continue
                items.append(cls._serialize_item(req))
                if len(items) >= int(limit):
                    break
            issue_id = int(getattr(issue, "id", 0) or 0)
            if issue_id > 0:
                out[issue_id] = cls.summarize_items(items)
        return out
