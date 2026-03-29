from __future__ import annotations

from typing import Callable, Dict, List, Optional
import os

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.discovery_hint_learning import DiscoveryHintTelemetryEvent


class DiscoveryHintTelemetryService:
    _session_factory: Optional[Callable[[], Session]] = None

    @classmethod
    def _persistence_enabled(cls) -> bool:
        app_env = str(os.getenv("APP_ENV") or "").strip().lower()
        if app_env in {"test", "pytest"} and cls._session_factory is None:
            return False
        raw = os.getenv("DISCOVERY_HINT_TELEMETRY_PERSIST", "true")
        return str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    @classmethod
    def _get_session_factory(cls) -> Callable[[], Session]:
        return cls._session_factory or SessionLocal

    @classmethod
    def set_session_factory_for_tests(cls, factory: Optional[Callable[[], Session]]) -> None:
        cls._session_factory = factory

    @classmethod
    def clear_for_tests(cls) -> None:
        if not cls._persistence_enabled():
            return
        db = cls._get_session_factory()()
        try:
            db.query(DiscoveryHintTelemetryEvent).delete(synchronize_session=False)
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    @classmethod
    def record_event(cls, payload: Dict[str, object] | None) -> Optional[int]:
        if not cls._persistence_enabled() or not isinstance(payload, dict) or not payload:
            return None
        db = cls._get_session_factory()()
        try:
            row = DiscoveryHintTelemetryEvent(
                event_type=str(payload.get("event_type") or "unknown").strip() or "unknown",
                target_ip=str(payload.get("target_ip") or "").strip() or None,
                mac=str(payload.get("mac") or "").strip() or None,
                oui_prefix=str(payload.get("oui_prefix") or "").strip() or None,
                raw_vendor=str(payload.get("raw_vendor") or "").strip() or None,
                normalized_vendor=str(payload.get("normalized_vendor") or "").strip() or None,
                seed_device_id=payload.get("seed_device_id"),
                seed_ip=str(payload.get("seed_ip") or "").strip() or None,
                seed_vendor=str(payload.get("seed_vendor") or "").strip() or None,
                local_interface=str(payload.get("local_interface") or "").strip() or None,
                neighbor_name=str(payload.get("neighbor_name") or "").strip() or None,
                neighbor_mgmt_ip=str(payload.get("neighbor_mgmt_ip") or "").strip() or None,
                chosen_driver=str(payload.get("chosen_driver") or "").strip() or None,
                final_driver=str(payload.get("final_driver") or "").strip() or None,
                success=bool(payload.get("success") or False),
                failure_reason=str(payload.get("failure_reason") or "").strip() or None,
                candidate_summary=list(payload.get("candidates") or []),
                payload=dict(payload),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return int(row.id)
        except Exception:
            db.rollback()
            return None
        finally:
            db.close()

    @classmethod
    def record_events(cls, payloads: List[Dict[str, object]] | None) -> Dict[str, object]:
        items = [payload for payload in (payloads or []) if isinstance(payload, dict) and payload]
        inserted_ids: List[int] = []
        for payload in items:
            row_id = cls.record_event(payload)
            if isinstance(row_id, int):
                inserted_ids.append(row_id)
        return {
            "accepted": len(items),
            "ingested": len(inserted_ids),
            "ids": inserted_ids,
        }

    @classmethod
    def list_recent(cls, limit: int = 50, *, include_payload: bool = False) -> List[Dict[str, object]]:
        if not cls._persistence_enabled():
            return []
        db = cls._get_session_factory()()
        try:
            rows = (
                db.query(DiscoveryHintTelemetryEvent)
                .order_by(DiscoveryHintTelemetryEvent.id.desc())
                .limit(max(1, min(int(limit or 50), 500)))
                .all()
            )
            return [
                {
                    "id": int(row.id),
                    "event_type": row.event_type,
                    "target_ip": row.target_ip,
                    "mac": row.mac,
                    "oui_prefix": row.oui_prefix,
                    "normalized_vendor": row.normalized_vendor,
                    "chosen_driver": row.chosen_driver,
                    "final_driver": row.final_driver,
                    "success": bool(row.success),
                    "failure_reason": row.failure_reason,
                    "created_at": row.created_at,
                    "candidate_summary": list(row.candidate_summary or []),
                    "payload": dict(row.payload or {}) if include_payload else None,
                }
                for row in rows
            ]
        finally:
            db.close()

    @classmethod
    def list_since_id(
        cls,
        *,
        last_event_id: int = 0,
        limit: int = 100,
        include_payload: bool = True,
    ) -> List[Dict[str, object]]:
        if not cls._persistence_enabled():
            return []
        db = cls._get_session_factory()()
        try:
            rows = (
                db.query(DiscoveryHintTelemetryEvent)
                .filter(DiscoveryHintTelemetryEvent.id > int(last_event_id or 0))
                .order_by(DiscoveryHintTelemetryEvent.id.asc())
                .limit(max(1, min(int(limit or 100), 1000)))
                .all()
            )
            return [
                {
                    "id": int(row.id),
                    "event_type": row.event_type,
                    "target_ip": row.target_ip,
                    "mac": row.mac,
                    "oui_prefix": row.oui_prefix,
                    "raw_vendor": row.raw_vendor,
                    "normalized_vendor": row.normalized_vendor,
                    "seed_device_id": row.seed_device_id,
                    "seed_ip": row.seed_ip,
                    "seed_vendor": row.seed_vendor,
                    "local_interface": row.local_interface,
                    "neighbor_name": row.neighbor_name,
                    "neighbor_mgmt_ip": row.neighbor_mgmt_ip,
                    "chosen_driver": row.chosen_driver,
                    "final_driver": row.final_driver,
                    "success": bool(row.success),
                    "failure_reason": row.failure_reason,
                    "candidate_summary": list(row.candidate_summary or []),
                    "created_at": row.created_at,
                    "payload": dict(row.payload or {}) if include_payload else None,
                }
                for row in rows
            ]
        finally:
            db.close()
