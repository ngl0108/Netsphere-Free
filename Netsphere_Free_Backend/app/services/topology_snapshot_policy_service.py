from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.device import Link
from app.models.settings import SystemSetting
from app.models.topology import TopologySnapshot
from app.services.topology_snapshot_service import TopologySnapshotService


class TopologySnapshotPolicyService:
    @staticmethod
    def _get_str(db: Session, key: str, default: str) -> str:
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if not row or row.value is None:
            return default
        return str(row.value)

    @staticmethod
    def _get_bool(db: Session, key: str, default: bool) -> bool:
        v = TopologySnapshotPolicyService._get_str(db, key, "true" if default else "false").strip().lower()
        return v in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _get_int(db: Session, key: str, default: int) -> int:
        try:
            return int(float(TopologySnapshotPolicyService._get_str(db, key, str(default)).strip()))
        except Exception:
            return int(default)

    @staticmethod
    def _get_float(db: Session, key: str, default: float) -> float:
        try:
            return float(TopologySnapshotPolicyService._get_str(db, key, str(default)).strip())
        except Exception:
            return float(default)

    @staticmethod
    def _latest_snapshot(db: Session, *, site_id: Optional[int]) -> Optional[TopologySnapshot]:
        q = db.query(TopologySnapshot)
        if site_id is None:
            q = q.filter(TopologySnapshot.site_id.is_(None))
        else:
            q = q.filter(TopologySnapshot.site_id == site_id)
        return q.order_by(desc(TopologySnapshot.created_at), desc(TopologySnapshot.id)).first()

    @staticmethod
    def _link_key(
        *,
        source: Any,
        src_port: Any,
        target: Any,
        dst_port: Any,
        protocol: Any,
    ) -> str:
        return "|".join(
            [
                str(source or ""),
                str(src_port or ""),
                str(target or ""),
                str(dst_port or ""),
                str(protocol or "LLDP").upper(),
            ]
        )

    @staticmethod
    def _current_link_map(db: Session, *, device_ids: Optional[list[int]]) -> Dict[str, str]:
        q = db.query(Link).filter(Link.target_device_id.isnot(None))
        if device_ids is not None:
            if not device_ids:
                return {}
            q = q.filter(Link.source_device_id.in_(device_ids), Link.target_device_id.in_(device_ids))

        out: Dict[str, str] = {}
        for l in q.all():
            key = TopologySnapshotPolicyService._link_key(
                source=l.source_device_id,
                src_port=l.source_interface_name,
                target=l.target_device_id,
                dst_port=l.target_interface_name,
                protocol=l.protocol,
            )
            out[key] = "active" if str(l.status) in {"up", "active"} else "down"
        return out

    @staticmethod
    def _snapshot_link_map(snapshot: TopologySnapshot) -> Dict[str, str]:
        try:
            links = json.loads(snapshot.links_json or "[]")
        except Exception:
            links = []
        if not isinstance(links, list):
            links = []
        out: Dict[str, str] = {}
        for l in links:
            if not isinstance(l, dict):
                continue
            key = TopologySnapshotPolicyService._link_key(
                source=l.get("source"),
                src_port=l.get("src_port"),
                target=l.get("target"),
                dst_port=l.get("dst_port"),
                protocol=l.get("protocol"),
            )
            out[key] = "active" if str(l.get("status")) in {"up", "active"} else "down"
        return out

    @staticmethod
    def _compute_link_delta(db: Session, *, site_id: Optional[int], baseline: Optional[TopologySnapshot]) -> Dict[str, int]:
        device_ids: Optional[list[int]]
        if site_id is None:
            device_ids = None
        else:
            from app.models.device import Device

            device_ids = [int(r[0]) for r in db.query(Device.id).filter(Device.site_id == site_id).all()]

        cur = TopologySnapshotPolicyService._current_link_map(db, device_ids=device_ids)
        base = TopologySnapshotPolicyService._snapshot_link_map(baseline) if baseline else {}

        cur_keys = set(cur.keys())
        base_keys = set(base.keys())

        added = len(cur_keys - base_keys)
        removed = len(base_keys - cur_keys)
        changed = 0
        for k in cur_keys & base_keys:
            if cur.get(k) != base.get(k):
                changed += 1
        return {"added": added, "removed": removed, "changed": changed, "total": added + removed + changed}

    @staticmethod
    def maybe_create_snapshot(
        db: Session,
        *,
        site_id: Optional[int],
        job_id: Optional[int],
        trigger: str,
    ) -> Optional[TopologySnapshot]:
        if not TopologySnapshotPolicyService._get_bool(db, "topology_snapshot_auto_enabled", True):
            return None

        scope = TopologySnapshotPolicyService._get_str(db, "topology_snapshot_auto_scope", "site").strip().lower()
        effective_site_id = None if scope == "global" else site_id

        interval_min = TopologySnapshotPolicyService._get_float(db, "topology_snapshot_auto_interval_minutes", 60.0)
        threshold = TopologySnapshotPolicyService._get_int(db, "topology_snapshot_auto_change_threshold_links", 10)

        last = TopologySnapshotPolicyService._latest_snapshot(db, site_id=effective_site_id)
        now = datetime.now(timezone.utc)

        delta = TopologySnapshotPolicyService._compute_link_delta(db, site_id=effective_site_id, baseline=last)
        over_threshold = threshold > 0 and delta.get("total", 0) >= threshold

        interval_elapsed = True
        if last and interval_min and interval_min > 0:
            last_ts = getattr(last, "created_at", None)
            if last_ts:
                if getattr(last_ts, "tzinfo", None) is None:
                    age = (datetime.utcnow() - last_ts).total_seconds()
                else:
                    age = (now - last_ts).total_seconds()
                interval_elapsed = age >= (interval_min * 60.0)

        should_create = (last is None) or over_threshold or interval_elapsed
        if not should_create:
            return None

        label = f"auto:{trigger}"
        metadata = {
            "trigger": trigger,
            "job_id": job_id,
            "scope": scope,
            "policy": {"interval_minutes": interval_min, "change_threshold_links": threshold},
            "delta": delta,
        }

        return TopologySnapshotService.create_snapshot(
            db,
            site_id=effective_site_id,
            job_id=job_id,
            label=label,
            metadata=metadata,
        )
