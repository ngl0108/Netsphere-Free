import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.topology import TopologyChangeEvent


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def publish_topology_event(
    db: Optional[Session],
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
    *,
    site_id: Optional[int] = None,
    device_id: Optional[int] = None,
    persist: bool = True,
    realtime: bool = True,
    commit: bool = False,
) -> None:
    data = payload if isinstance(payload, dict) else {}
    event_name = str(event_type or "").strip()
    if not event_name:
        return

    if realtime:
        try:
            from app.services.realtime_event_bus import realtime_event_bus

            realtime_event_bus.publish(event_name, data)
        except Exception:
            pass

    if not persist or db is None:
        return

    try:
        row = TopologyChangeEvent(
            site_id=_safe_int(site_id),
            device_id=_safe_int(device_id),
            event_type=event_name,
            payload_json=json.dumps(data, ensure_ascii=False, default=str),
        )
        db.add(row)
        if commit:
            db.commit()
    except Exception:
        if commit:
            try:
                db.rollback()
            except Exception:
                pass
