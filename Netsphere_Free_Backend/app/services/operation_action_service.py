from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy.orm import Session

from app.models.device import Issue
from app.models.operation_action import OperationAction


class OperationActionService:
    ACTIVE_STATUSES = {"open", "investigating", "mitigated"}
    VALID_STATUSES = {"open", "investigating", "mitigated", "resolved"}
    VALID_SEVERITIES = {"info", "warning", "critical"}

    @classmethod
    def _now(cls) -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _normalize_status(cls, value: Any, *, default: str = "open") -> str:
        normalized = str(value or default).strip().lower() or default
        if normalized not in cls.VALID_STATUSES:
            return default
        return normalized

    @classmethod
    def _normalize_severity(cls, value: Any, *, default: str = "warning") -> str:
        normalized = str(value or default).strip().lower() or default
        if normalized not in cls.VALID_SEVERITIES:
            return default
        return normalized

    @classmethod
    def _timeline_entry(
        cls,
        *,
        event: str,
        actor: str,
        status: str,
        note: str | None = None,
        assignee_name: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": str(event or "updated"),
            "actor": str(actor or "system"),
            "status": cls._normalize_status(status),
            "note": str(note or "").strip() or None,
            "assignee_name": str(assignee_name or "").strip() or None,
            "at": cls._now().isoformat(),
        }

    @classmethod
    def serialize(cls, row: OperationAction) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "issue_id": int(row.issue_id),
            "device_id": int(row.device_id) if row.device_id is not None else None,
            "source_type": str(row.source_type or "issue"),
            "title": str(row.title or ""),
            "summary": str(row.summary or "").strip() or None,
            "severity": cls._normalize_severity(getattr(row, "severity", None), default="warning"),
            "status": cls._normalize_status(getattr(row, "status", None), default="open"),
            "assignee_name": str(row.assignee_name or "").strip() or None,
            "created_by": str(row.created_by or "").strip() or None,
            "updated_by": str(row.updated_by or "").strip() or None,
            "latest_note": str(row.latest_note or "").strip() or None,
            "timeline": list(getattr(row, "timeline", None) or []),
            "created_at": getattr(row, "created_at", None),
            "updated_at": getattr(row, "updated_at", None),
            "resolved_at": getattr(row, "resolved_at", None),
        }

    @classmethod
    def list_for_issue(cls, db: Session, issue_id: int) -> list[dict[str, Any]]:
        rows = (
            db.query(OperationAction)
            .filter(OperationAction.issue_id == int(issue_id))
            .order_by(OperationAction.updated_at.desc(), OperationAction.id.desc())
            .all()
        )
        return [cls.serialize(row) for row in rows]

    @classmethod
    def get(cls, db: Session, action_id: int) -> OperationAction | None:
        return db.query(OperationAction).filter(OperationAction.id == int(action_id)).first()

    @classmethod
    def create_for_issue(
        cls,
        db: Session,
        *,
        issue: Issue,
        payload: dict[str, Any],
        actor: str,
    ) -> OperationAction:
        title = str(payload.get("title") or issue.title or "").strip() or f"Issue #{int(issue.id)} action"
        summary = str(payload.get("summary") or issue.description or "").strip() or None
        assignee_name = str(payload.get("assignee_name") or "").strip() or None
        note = str(payload.get("note") or "").strip() or None
        row = OperationAction(
            issue_id=int(issue.id),
            device_id=int(issue.device_id) if getattr(issue, "device_id", None) is not None else None,
            source_type="issue",
            title=title,
            summary=summary,
            severity=cls._normalize_severity(getattr(issue, "severity", None), default="warning"),
            status="open",
            assignee_name=assignee_name,
            created_by=str(actor or "operator"),
            updated_by=str(actor or "operator"),
            latest_note=note,
            timeline=[
                cls._timeline_entry(
                    event="created",
                    actor=str(actor or "operator"),
                    status="open",
                    note=note,
                    assignee_name=assignee_name,
                )
            ],
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @classmethod
    def update(
        cls,
        db: Session,
        *,
        row: OperationAction,
        payload: dict[str, Any],
        actor: str,
    ) -> OperationAction:
        next_status = cls._normalize_status(payload.get("status"), default=str(row.status or "open"))
        assignee_name = (
            str(payload.get("assignee_name")).strip()
            if payload.get("assignee_name") is not None
            else str(row.assignee_name or "").strip()
        ) or None
        note = str(payload.get("note") or "").strip() or None

        current_status = cls._normalize_status(getattr(row, "status", None), default="open")
        timeline = list(getattr(row, "timeline", None) or [])
        event = "updated"
        if next_status != current_status:
            event = "status_changed"
        elif payload.get("assignee_name") is not None:
            event = "reassigned"
        elif note:
            event = "noted"

        row.status = next_status
        row.assignee_name = assignee_name
        row.updated_by = str(actor or "operator")
        if note:
            row.latest_note = note
        if next_status == "resolved":
            row.resolved_at = cls._now()
        elif current_status == "resolved" and next_status != "resolved":
            row.resolved_at = None
        timeline.append(
            cls._timeline_entry(
                event=event,
                actor=str(actor or "operator"),
                status=next_status,
                note=note,
                assignee_name=assignee_name,
            )
        )
        row.timeline = timeline
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @classmethod
    def summarize_rows(cls, rows: Iterable[OperationAction]) -> dict[str, Any]:
        summary = {
            "total": 0,
            "open": 0,
            "investigating": 0,
            "mitigated": 0,
            "resolved": 0,
            "has_active": False,
            "latest_status": None,
            "latest_action_id": None,
            "latest_title": None,
            "latest_assignee_name": None,
            "latest_note": None,
            "latest_updated_at": None,
        }
        latest_row: OperationAction | None = None
        for row in list(rows or []):
            summary["total"] += 1
            status = cls._normalize_status(getattr(row, "status", None), default="open")
            summary[status] = int(summary.get(status) or 0) + 1
            if status in cls.ACTIVE_STATUSES:
                summary["has_active"] = True
            if latest_row is None:
                latest_row = row
                continue
            latest_ts = getattr(latest_row, "updated_at", None) or getattr(latest_row, "created_at", None)
            row_ts = getattr(row, "updated_at", None) or getattr(row, "created_at", None)
            if row_ts and latest_ts and row_ts >= latest_ts:
                latest_row = row
        if latest_row is not None:
            summary["latest_status"] = cls._normalize_status(getattr(latest_row, "status", None), default="open")
            summary["latest_action_id"] = int(getattr(latest_row, "id", 0) or 0) or None
            summary["latest_title"] = str(getattr(latest_row, "title", "") or "").strip() or None
            summary["latest_assignee_name"] = str(getattr(latest_row, "assignee_name", "") or "").strip() or None
            summary["latest_note"] = str(getattr(latest_row, "latest_note", "") or "").strip() or None
            latest_updated_at = getattr(latest_row, "updated_at", None) or getattr(latest_row, "created_at", None)
            summary["latest_updated_at"] = latest_updated_at.isoformat() if latest_updated_at else None
        return summary

    @classmethod
    def build_issue_summary_map(cls, db: Session, issue_ids: list[int]) -> dict[int, dict[str, Any]]:
        ids = [int(v) for v in list(issue_ids or []) if int(v or 0) > 0]
        if not ids:
            return {}
        rows = (
            db.query(OperationAction)
            .filter(OperationAction.issue_id.in_(ids))
            .order_by(OperationAction.updated_at.desc(), OperationAction.id.desc())
            .all()
        )
        grouped: dict[int, list[OperationAction]] = {}
        for row in rows:
            key = int(getattr(row, "issue_id", 0) or 0)
            if key <= 0:
                continue
            grouped.setdefault(key, []).append(row)
        return {issue_id: cls.summarize_rows(grouped.get(issue_id) or []) for issue_id in ids}
