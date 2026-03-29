from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.approval import ApprovalRequest
from app.models.asset_change_event import AssetChangeEvent
from app.models.device import EventLog, Issue
from app.models.monitoring_profile import MonitoringProfileAssignment
from app.models.operation_action import OperationAction
from app.models.service_group import ServiceGroup
from app.schemas.source_of_truth import (
    SourceOfTruthCoverageBlock,
    SourceOfTruthDistributionBlock,
)
from app.schemas.state_history import (
    StateHistoryCompareCard,
    StateHistoryCompareResponse,
    StateHistoryCompareSummary,
    StateHistoryHighlightItem,
    StateHistoryMetricBlock,
    StateHistorySnapshotResponse,
)
from app.services.source_of_truth_service import SourceOfTruthService


class StateHistoryService:
    SNAPSHOT_EVENT_ID = "OPS_STATE_HISTORY_SNAPSHOT"
    SNAPSHOT_SOURCE = "StateHistory"

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _to_json_dict(raw: Any) -> dict[str, Any]:
        if isinstance(raw, dict):
            return dict(raw)
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except Exception:
            return int(default)

    @staticmethod
    def _status_count(rows: list[Any], attr: str, expected: str) -> int:
        normalized = str(expected or "").strip().lower()
        return sum(1 for row in rows if str(getattr(row, attr, "") or "").strip().lower() == normalized)

    @classmethod
    def _build_payload(
        cls,
        db: Session,
        *,
        label: Optional[str] = None,
        note: Optional[str] = None,
        actor_name: Optional[str] = None,
        actor_role: Optional[str] = None,
    ) -> dict[str, Any]:
        sot = SourceOfTruthService.build_summary(db)
        metrics = sot.metrics.model_dump()
        coverage = sot.coverage.model_dump()
        distributions = sot.distributions.model_dump()

        actions = db.query(OperationAction).order_by(OperationAction.id.asc()).all()
        approvals = db.query(ApprovalRequest).order_by(ApprovalRequest.id.asc()).all()

        active_issues = db.query(Issue).filter(Issue.status == "active").all()
        critical_issues_total = sum(
            1 for row in active_issues if str(getattr(row, "severity", "") or "").strip().lower() == "critical"
        )
        evidence_ready_approvals_total = 0
        for approval in approvals:
            payload = approval.payload if isinstance(approval.payload, dict) else {}
            if payload.get("execution_result") or payload.get("execution_trace"):
                evidence_ready_approvals_total += 1

        metrics_block = {
            **metrics,
            "high_criticality_groups": cls._safe_int(
                db.query(ServiceGroup)
                .filter(ServiceGroup.criticality.in_(["high", "critical"]))
                .count()
            ),
            "monitoring_profile_assignments_total": cls._safe_int(
                db.query(MonitoringProfileAssignment).count()
            ),
            "active_issues_total": cls._safe_int(len(active_issues)),
            "critical_issues_total": cls._safe_int(critical_issues_total),
            "open_actions_total": cls._status_count(actions, "status", "open"),
            "investigating_actions_total": cls._status_count(actions, "status", "investigating"),
            "mitigated_actions_total": cls._status_count(actions, "status", "mitigated"),
            "resolved_actions_total": cls._status_count(actions, "status", "resolved"),
            "pending_approvals_total": cls._status_count(approvals, "status", "pending"),
            "approved_approvals_total": cls._status_count(approvals, "status", "approved"),
            "rejected_approvals_total": cls._status_count(approvals, "status", "rejected"),
            "evidence_ready_approvals_total": cls._safe_int(evidence_ready_approvals_total),
            "asset_changes_7d_total": cls._safe_int(
                db.query(AssetChangeEvent)
                .filter(AssetChangeEvent.created_at >= (cls._utcnow() - timedelta(days=7)))
                .count()
            ),
        }

        top_role = (distributions.get("device_roles") or [{}])[0] if distributions.get("device_roles") else {}
        top_provider = (
            (distributions.get("cloud_providers") or [{}])[0] if distributions.get("cloud_providers") else {}
        )
        top_type = (distributions.get("device_types") or [{}])[0] if distributions.get("device_types") else {}
        highlights = [
            {
                "key": "top_device_role",
                "value": str(top_role.get("key") or "unspecified"),
                "count": cls._safe_int(top_role.get("count")),
            },
            {
                "key": "top_device_type",
                "value": str(top_type.get("key") or "unspecified"),
                "count": cls._safe_int(top_type.get("count")),
            },
            {
                "key": "top_cloud_provider",
                "value": str(top_provider.get("key") or "unknown"),
                "count": cls._safe_int(top_provider.get("count")),
            },
        ]

        return {
            "generated_at": cls._utcnow().isoformat(),
            "label": str(label or "").strip() or None,
            "note": str(note or "").strip() or None,
            "actor_name": str(actor_name or "").strip() or None,
            "actor_role": str(actor_role or "").strip() or None,
            "metrics": metrics_block,
            "coverage": coverage,
            "distributions": distributions,
            "highlights": highlights,
        }

    @classmethod
    def _serialize_payload(
        cls,
        payload: dict[str, Any],
        *,
        event_log_id: int = 0,
        event_id: str | None = None,
        source: str | None = None,
        severity: str | None = None,
    ) -> StateHistorySnapshotResponse:
        generated_at_raw = payload.get("generated_at")
        generated_at = cls._utcnow()
        if isinstance(generated_at_raw, str) and generated_at_raw.strip():
            try:
                generated_at = datetime.fromisoformat(generated_at_raw.replace("Z", "+00:00"))
            except Exception:
                generated_at = cls._utcnow()

        return StateHistorySnapshotResponse(
            event_log_id=int(event_log_id or 0),
            event_id=str(event_id or cls.SNAPSHOT_EVENT_ID),
            source=str(source or cls.SNAPSHOT_SOURCE),
            severity=str(severity or "info"),
            generated_at=generated_at,
            label=str(payload.get("label") or "").strip() or None,
            note=str(payload.get("note") or "").strip() or None,
            actor_name=str(payload.get("actor_name") or "").strip() or None,
            actor_role=str(payload.get("actor_role") or "").strip() or None,
            metrics=StateHistoryMetricBlock(**dict(payload.get("metrics") or {})),
            coverage=SourceOfTruthCoverageBlock(**dict(payload.get("coverage") or {})),
            distributions=SourceOfTruthDistributionBlock(**dict(payload.get("distributions") or {})),
            highlights=[
                StateHistoryHighlightItem(
                    key=str(item.get("key") or ""),
                    value=str(item.get("value") or "").strip() or None,
                    count=cls._safe_int(item.get("count")) if item.get("count") is not None else None,
                )
                for item in list(payload.get("highlights") or [])
                if isinstance(item, dict) and str(item.get("key") or "").strip()
            ],
        )

    @classmethod
    def build_current_snapshot(cls, db: Session) -> StateHistorySnapshotResponse:
        payload = cls._build_payload(db, label="Current state")
        return cls._serialize_payload(payload, event_id=cls.SNAPSHOT_EVENT_ID, source="runtime/current", severity="info")

    @classmethod
    def create_snapshot(
        cls,
        db: Session,
        *,
        label: Optional[str] = None,
        note: Optional[str] = None,
        actor_name: Optional[str] = None,
        actor_role: Optional[str] = None,
        commit: bool = True,
    ) -> StateHistorySnapshotResponse:
        payload = cls._build_payload(
            db,
            label=label or "Manual snapshot",
            note=note,
            actor_name=actor_name,
            actor_role=actor_role,
        )
        row = EventLog(
            device_id=None,
            severity="info",
            event_id=cls.SNAPSHOT_EVENT_ID,
            message=json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
            source=cls.SNAPSHOT_SOURCE,
            timestamp=cls._utcnow(),
        )
        db.add(row)
        db.flush()
        if commit:
            db.commit()
            db.refresh(row)
        return cls._serialize_payload(
            payload,
            event_log_id=int(row.id or 0),
            event_id=str(row.event_id or cls.SNAPSHOT_EVENT_ID),
            source=str(row.source or cls.SNAPSHOT_SOURCE),
            severity=str(row.severity or "info"),
        )

    @classmethod
    def list_snapshots(cls, db: Session, *, limit: int = 12) -> list[StateHistorySnapshotResponse]:
        rows = (
            db.query(EventLog)
            .filter(EventLog.event_id == cls.SNAPSHOT_EVENT_ID)
            .order_by(EventLog.timestamp.desc(), EventLog.id.desc())
            .limit(max(1, int(limit)))
            .all()
        )
        snapshots: list[StateHistorySnapshotResponse] = []
        for row in rows:
            payload = cls._to_json_dict(row.message)
            if not payload:
                continue
            snapshots.append(
                cls._serialize_payload(
                    payload,
                    event_log_id=int(getattr(row, "id", 0) or 0),
                    event_id=str(getattr(row, "event_id", "") or cls.SNAPSHOT_EVENT_ID),
                    source=str(getattr(row, "source", "") or cls.SNAPSHOT_SOURCE),
                    severity=str(getattr(row, "severity", "") or "info"),
                )
            )
        return snapshots

    @classmethod
    def get_snapshot(cls, db: Session, snapshot_id: int) -> Optional[StateHistorySnapshotResponse]:
        row = (
            db.query(EventLog)
            .filter(EventLog.id == int(snapshot_id), EventLog.event_id == cls.SNAPSHOT_EVENT_ID)
            .first()
        )
        if row is None:
            return None
        payload = cls._to_json_dict(row.message)
        if not payload:
            return None
        return cls._serialize_payload(
            payload,
            event_log_id=int(getattr(row, "id", 0) or 0),
            event_id=str(getattr(row, "event_id", "") or cls.SNAPSHOT_EVENT_ID),
            source=str(getattr(row, "source", "") or cls.SNAPSHOT_SOURCE),
            severity=str(getattr(row, "severity", "") or "info"),
        )

    @classmethod
    def _build_compare_cards(
        cls,
        before: StateHistorySnapshotResponse,
        current: StateHistorySnapshotResponse,
    ) -> list[StateHistoryCompareCard]:
        before_metrics = before.metrics
        current_metrics = current.metrics
        before_coverage = before.coverage
        current_coverage = current.coverage

        before_profile_ratio = (
            (before_coverage.devices_with_monitoring_profile / before_metrics.devices_total)
            if before_metrics.devices_total > 0
            else 0.0
        )
        current_profile_ratio = (
            (current_coverage.devices_with_monitoring_profile / current_metrics.devices_total)
            if current_metrics.devices_total > 0
            else 0.0
        )

        before_service_ratio = (
            (before_coverage.cloud_resources_mapped_to_services / before_metrics.cloud_resources_total)
            if before_metrics.cloud_resources_total > 0
            else 0.0
        )
        current_service_ratio = (
            (current_coverage.cloud_resources_mapped_to_services / current_metrics.cloud_resources_total)
            if current_metrics.cloud_resources_total > 0
            else 0.0
        )

        cards: list[StateHistoryCompareCard] = []

        devices_delta = current_metrics.devices_total - before_metrics.devices_total
        cloud_delta = current_metrics.cloud_resources_total - before_metrics.cloud_resources_total
        cards.append(
            StateHistoryCompareCard(
                key="asset_baseline",
                title="Asset Baseline",
                before=f"{before_metrics.devices_total} devices / {before_metrics.cloud_resources_total} cloud / {before_metrics.service_groups_total} services",
                current=f"{current_metrics.devices_total} devices / {current_metrics.cloud_resources_total} cloud / {current_metrics.service_groups_total} services",
                delta=f"devices {devices_delta:+d}, cloud {cloud_delta:+d}",
                status="steady" if devices_delta == 0 and cloud_delta == 0 else "changed",
                tone="info",
                recommendation="Capture a new snapshot after major discovery or onboarding changes.",
            )
        )

        managed_delta = current_metrics.managed_devices - before_metrics.managed_devices
        discovered_delta = current_metrics.discovered_only_devices - before_metrics.discovered_only_devices
        mgmt_status = "steady"
        mgmt_tone = "info"
        if managed_delta > 0:
            mgmt_status = "improved"
            mgmt_tone = "good"
        elif managed_delta < 0:
            mgmt_status = "review"
            mgmt_tone = "warn"
        cards.append(
            StateHistoryCompareCard(
                key="management_posture",
                title="Management Posture",
                before=f"{before_metrics.managed_devices} managed / {before_metrics.discovered_only_devices} discovered only",
                current=f"{current_metrics.managed_devices} managed / {current_metrics.discovered_only_devices} discovered only",
                delta=f"managed {managed_delta:+d}, discovered only {discovered_delta:+d}",
                status=mgmt_status,
                tone=mgmt_tone,
                recommendation="Review managed slots if discovered-only assets keep growing beyond the current operational boundary.",
            )
        )

        profile_ratio_delta = current_profile_ratio - before_profile_ratio
        profile_status = "steady"
        profile_tone = "info"
        if profile_ratio_delta > 0.001:
            profile_status = "improved"
            profile_tone = "good"
        elif profile_ratio_delta < -0.001:
            profile_status = "review"
            profile_tone = "warn"
        cards.append(
            StateHistoryCompareCard(
                key="monitoring_coverage",
                title="Monitoring Coverage",
                before=f"{before_coverage.devices_with_monitoring_profile} assets aligned ({round(before_profile_ratio * 100)}%)",
                current=f"{current_coverage.devices_with_monitoring_profile} assets aligned ({round(current_profile_ratio * 100)}%)",
                delta=f"coverage {(profile_ratio_delta * 100):+.0f} pts",
                status=profile_status,
                tone=profile_tone,
                recommendation="Keep profile coverage aligned so newly managed assets inherit the right telemetry posture immediately.",
            )
        )

        service_ratio_delta = current_service_ratio - before_service_ratio
        service_status = "steady"
        service_tone = "info"
        if service_ratio_delta > 0.001 or current_coverage.service_groups_with_owner > before_coverage.service_groups_with_owner:
            service_status = "improved"
            service_tone = "good"
        elif service_ratio_delta < -0.001:
            service_status = "review"
            service_tone = "warn"
        cards.append(
            StateHistoryCompareCard(
                key="service_mapping",
                title="Service Mapping",
                before=f"{before_coverage.cloud_resources_mapped_to_services} mapped cloud resources / {before_coverage.service_groups_with_owner} groups with owner",
                current=f"{current_coverage.cloud_resources_mapped_to_services} mapped cloud resources / {current_coverage.service_groups_with_owner} groups with owner",
                delta=f"mapping {(service_ratio_delta * 100):+.0f} pts",
                status=service_status,
                tone=service_tone,
                recommendation="Add owners and service mappings so alerts, approvals, and reports stay tied to business context.",
            )
        )

        before_pressure = before_metrics.active_issues_total + before_metrics.open_actions_total + before_metrics.investigating_actions_total
        current_pressure = current_metrics.active_issues_total + current_metrics.open_actions_total + current_metrics.investigating_actions_total
        pressure_delta = current_pressure - before_pressure
        pressure_status = "steady"
        pressure_tone = "info"
        if pressure_delta < 0:
            pressure_status = "improved"
            pressure_tone = "good"
        elif pressure_delta > 0:
            pressure_status = "review"
            pressure_tone = "warn"
        cards.append(
            StateHistoryCompareCard(
                key="operations_pressure",
                title="Operations Pressure",
                before=f"{before_metrics.active_issues_total} active issues / {before_metrics.open_actions_total + before_metrics.investigating_actions_total} open actions",
                current=f"{current_metrics.active_issues_total} active issues / {current_metrics.open_actions_total + current_metrics.investigating_actions_total} open actions",
                delta=f"pressure {pressure_delta:+d}",
                status=pressure_status,
                tone=pressure_tone,
                recommendation="Use this delta as a quick handoff signal after changes, incidents, or preventive reviews.",
            )
        )

        pending_delta = current_metrics.pending_approvals_total - before_metrics.pending_approvals_total
        evidence_delta = current_metrics.evidence_ready_approvals_total - before_metrics.evidence_ready_approvals_total
        approval_status = "steady"
        approval_tone = "info"
        if pending_delta > 0 and evidence_delta <= 0:
            approval_status = "review"
            approval_tone = "warn"
        elif evidence_delta > 0:
            approval_status = "improved"
            approval_tone = "good"
        cards.append(
            StateHistoryCompareCard(
                key="change_queue",
                title="Change Queue",
                before=f"{before_metrics.pending_approvals_total} pending approvals / {before_metrics.evidence_ready_approvals_total} evidence-ready",
                current=f"{current_metrics.pending_approvals_total} pending approvals / {current_metrics.evidence_ready_approvals_total} evidence-ready",
                delta=f"pending {pending_delta:+d}, evidence {evidence_delta:+d}",
                status=approval_status,
                tone=approval_tone,
                recommendation="Keep evidence readiness ahead of pending volume so approval review does not become the bottleneck.",
            )
        )

        return cards

    @classmethod
    def compare_snapshot_to_current(cls, db: Session, snapshot_id: int) -> Optional[StateHistoryCompareResponse]:
        baseline = cls.get_snapshot(db, snapshot_id)
        if baseline is None:
            return None
        current = cls.build_current_snapshot(db)
        cards = cls._build_compare_cards(baseline, current)

        improved_cards = sum(1 for card in cards if card.status == "improved")
        review_cards = sum(1 for card in cards if card.status == "review")
        changed_cards = sum(1 for card in cards if card.status == "changed")
        steady_cards = sum(1 for card in cards if card.status == "steady")
        result = "steady"
        if review_cards > 0:
            result = "review"
        elif improved_cards > 0 and changed_cards == 0:
            result = "improved"
        elif improved_cards > 0 or changed_cards > 0:
            result = "changed"

        return StateHistoryCompareResponse(
            baseline=baseline,
            current=current,
            summary=StateHistoryCompareSummary(
                result=result,
                changed_cards=changed_cards,
                improved_cards=improved_cards,
                review_cards=review_cards,
                steady_cards=steady_cards,
            ),
            cards=cards,
            context={
                "baseline_label": baseline.label or baseline.generated_at.isoformat(),
                "current_label": current.label or current.generated_at.isoformat(),
            },
        )

    @classmethod
    def build_review_summary(cls, db: Session, *, limit: int = 12) -> dict[str, Any]:
        snapshots = cls.list_snapshots(db, limit=limit)
        latest = snapshots[0] if snapshots else None
        comparison = (
            cls.compare_snapshot_to_current(db, int(latest.event_log_id))
            if latest and int(getattr(latest, "event_log_id", 0) or 0) > 0
            else None
        )
        latest_age_hours: Optional[float] = None
        if latest and getattr(latest, "generated_at", None):
            latest_age_hours = round(
                max(0.0, (cls._utcnow() - latest.generated_at).total_seconds()) / 3600.0,
                2,
            )
        hotspot_cards = []
        if comparison:
            hotspot_cards = [
                {
                    "key": str(card.key or ""),
                    "title": str(card.title or ""),
                    "status": str(card.status or "steady"),
                    "tone": str(card.tone or "info"),
                    "delta": str(card.delta or ""),
                    "recommendation": str(card.recommendation or "").strip() or None,
                }
                for card in list(comparison.cards or [])
                if str(card.status or "").strip().lower() in {"review", "changed"}
            ][:3]
        return {
            "snapshot_count": len(snapshots),
            "latest_snapshot": (
                {
                    "event_log_id": int(latest.event_log_id or 0),
                    "label": str(latest.label or "").strip() or None,
                    "generated_at": latest.generated_at.isoformat() if latest.generated_at else None,
                    "age_hours": latest_age_hours,
                }
                if latest
                else None
            ),
            "latest_compare": (
                {
                    "result": str(comparison.summary.result or "steady"),
                    "changed_cards": int(comparison.summary.changed_cards or 0),
                    "improved_cards": int(comparison.summary.improved_cards or 0),
                    "review_cards": int(comparison.summary.review_cards or 0),
                    "steady_cards": int(comparison.summary.steady_cards or 0),
                    "baseline_label": str(comparison.context.get("baseline_label") or ""),
                    "current_label": str(comparison.context.get("current_label") or ""),
                }
                if comparison
                else None
            ),
            "review_hotspots": hotspot_cards,
        }
