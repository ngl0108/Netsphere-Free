from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models.device import Device, Issue
from app.models.known_error import KnownErrorEntry


class KnownErrorService:
    TOKEN_RE = re.compile(r"[a-z0-9_-]+", re.IGNORECASE)

    @classmethod
    def _now(cls) -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def _normalize_text(cls, value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @classmethod
    def _normalize_tags(cls, value: Any) -> list[str]:
        out: list[str] = []
        for raw in list(value or []):
            text = str(raw or "").strip()
            if not text:
                continue
            if text not in out:
                out.append(text)
        return out

    @classmethod
    def _tokenize(cls, value: Any) -> list[str]:
        text = str(value or "").strip().lower()
        if not text:
            return []
        return [token for token in cls.TOKEN_RE.findall(text) if len(token) >= 3]

    @classmethod
    def serialize(cls, row: KnownErrorEntry) -> dict[str, Any]:
        return {
            "id": int(row.id),
            "title": str(row.title or ""),
            "symptom_pattern": cls._normalize_text(getattr(row, "symptom_pattern", None)),
            "category": cls._normalize_text(getattr(row, "category", None)),
            "severity_hint": cls._normalize_text(getattr(row, "severity_hint", None)),
            "device_type_scope": cls._normalize_text(getattr(row, "device_type_scope", None)),
            "vendor_scope": cls._normalize_text(getattr(row, "vendor_scope", None)),
            "root_cause": cls._normalize_text(getattr(row, "root_cause", None)),
            "workaround": cls._normalize_text(getattr(row, "workaround", None)),
            "sop_summary": cls._normalize_text(getattr(row, "sop_summary", None)),
            "tags": cls._normalize_tags(getattr(row, "tags", None)),
            "is_enabled": bool(getattr(row, "is_enabled", True)),
            "created_by": cls._normalize_text(getattr(row, "created_by", None)),
            "updated_by": cls._normalize_text(getattr(row, "updated_by", None)),
            "times_matched": int(getattr(row, "times_matched", 0) or 0),
            "last_matched_at": getattr(row, "last_matched_at", None),
            "created_at": getattr(row, "created_at", None),
            "updated_at": getattr(row, "updated_at", None),
        }

    @classmethod
    def list_entries(cls, db: Session, limit: int = 100) -> list[dict[str, Any]]:
        rows = (
            db.query(KnownErrorEntry)
            .order_by(KnownErrorEntry.updated_at.desc(), KnownErrorEntry.id.desc())
            .limit(int(limit))
            .all()
        )
        return [cls.serialize(row) for row in rows]

    @classmethod
    def get_entry(cls, db: Session, entry_id: int) -> KnownErrorEntry | None:
        return db.query(KnownErrorEntry).filter(KnownErrorEntry.id == int(entry_id)).first()

    @classmethod
    def create_from_issue(
        cls,
        db: Session,
        *,
        issue: Issue,
        payload: dict[str, Any],
        actor: str,
    ) -> KnownErrorEntry:
        device = getattr(issue, "device", None)
        row = KnownErrorEntry(
            title=cls._normalize_text(payload.get("title")) or str(issue.title or f"Issue #{int(issue.id)}"),
            symptom_pattern=cls._normalize_text(payload.get("symptom_pattern")) or cls._normalize_text(issue.description),
            category=cls._normalize_text(payload.get("category")) or cls._normalize_text(issue.category),
            severity_hint=cls._normalize_text(payload.get("severity_hint")) or cls._normalize_text(issue.severity),
            device_type_scope=cls._normalize_text(payload.get("device_type_scope")) or cls._normalize_text(getattr(device, "device_type", None)),
            vendor_scope=cls._normalize_text(payload.get("vendor_scope")),
            root_cause=cls._normalize_text(payload.get("root_cause")),
            workaround=cls._normalize_text(payload.get("workaround")),
            sop_summary=cls._normalize_text(payload.get("sop_summary")),
            tags=cls._normalize_tags(payload.get("tags")),
            is_enabled=bool(payload.get("is_enabled", True)),
            created_by=str(actor or "operator"),
            updated_by=str(actor or "operator"),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @classmethod
    def update_entry(
        cls,
        db: Session,
        *,
        row: KnownErrorEntry,
        payload: dict[str, Any],
        actor: str,
    ) -> KnownErrorEntry:
        for field in (
            "title",
            "symptom_pattern",
            "category",
            "severity_hint",
            "device_type_scope",
            "vendor_scope",
            "root_cause",
            "workaround",
            "sop_summary",
        ):
            if field in payload and payload.get(field) is not None:
                setattr(row, field, cls._normalize_text(payload.get(field)))
        if "tags" in payload and payload.get("tags") is not None:
            row.tags = cls._normalize_tags(payload.get("tags"))
        if "is_enabled" in payload and payload.get("is_enabled") is not None:
            row.is_enabled = bool(payload.get("is_enabled"))
        row.updated_by = str(actor or "operator")
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    @classmethod
    def _match_score(cls, *, issue: Issue, device: Device | None, row: KnownErrorEntry) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []
        issue_category = str(getattr(issue, "category", "") or "").strip().lower()
        row_category = str(getattr(row, "category", "") or "").strip().lower()
        if row_category and row_category == issue_category:
            score += 3.0
            reasons.append("category_match")

        issue_severity = str(getattr(issue, "severity", "") or "").strip().lower()
        row_severity = str(getattr(row, "severity_hint", "") or "").strip().lower()
        if row_severity and row_severity == issue_severity:
            score += 1.0
            reasons.append("severity_match")

        issue_device_type = str(getattr(device, "device_type", "") or "").strip().lower()
        row_device_type = str(getattr(row, "device_type_scope", "") or "").strip().lower()
        if row_device_type and row_device_type == issue_device_type:
            score += 2.0
            reasons.append("device_type_match")

        issue_tokens = set(cls._tokenize(getattr(issue, "title", None)) + cls._tokenize(getattr(issue, "description", None)))
        row_tokens = set(cls._tokenize(getattr(row, "title", None)) + cls._tokenize(getattr(row, "symptom_pattern", None)))
        overlap = sorted(issue_tokens.intersection(row_tokens))
        if overlap:
            score += min(4.0, 1.0 + (0.5 * float(len(overlap))))
            reasons.append("keyword_overlap")

        if getattr(row, "times_matched", 0) and score > 0:
            score += min(1.5, float(getattr(row, "times_matched", 0)) * 0.05)
            reasons.append("historical_reuse")

        return score, reasons

    @classmethod
    def build_recommendations_for_issue(cls, db: Session, issue: Issue, limit: int = 5) -> list[dict[str, Any]]:
        device = getattr(issue, "device", None)
        rows = (
            db.query(KnownErrorEntry)
            .filter(KnownErrorEntry.is_enabled == True)
            .order_by(KnownErrorEntry.updated_at.desc(), KnownErrorEntry.id.desc())
            .limit(200)
            .all()
        )
        scored: list[dict[str, Any]] = []
        for row in rows:
            score, reasons = cls._match_score(issue=issue, device=device, row=row)
            if score <= 0:
                continue
            payload = cls.serialize(row)
            payload["match_score"] = round(float(score), 2)
            payload["match_reasons"] = reasons
            scored.append(payload)
        scored.sort(key=lambda item: (-float(item.get("match_score") or 0.0), -int(item.get("times_matched") or 0), int(item.get("id") or 0)))
        return scored[: max(1, int(limit))]

    @classmethod
    def build_issue_summary_map(cls, db: Session, issues: list[Issue], limit: int = 3) -> dict[int, dict[str, Any]]:
        out: dict[int, dict[str, Any]] = {}
        for issue in list(issues or []):
            issue_id = int(getattr(issue, "id", 0) or 0)
            if issue_id <= 0:
                continue
            recommendations = cls.build_recommendations_for_issue(db, issue, limit=limit)
            out[issue_id] = {
                "recommendation_count": len(recommendations),
                "top_title": str(recommendations[0].get("title") or "") if recommendations else None,
            }
        return out
