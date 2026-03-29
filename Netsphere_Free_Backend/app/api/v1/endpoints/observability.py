from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.device import Device, InterfaceMetric, SystemMetric
from app.services.preview_managed_node_service import PreviewManagedNodeService

router = APIRouter()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _preview_managed_devices(db: Session):
    devices = db.query(Device).all()
    if PreviewManagedNodeService.is_preview_managed_quota_enabled(db):
        PreviewManagedNodeService.reconcile_managed_devices(db)
        return [device for device in devices if PreviewManagedNodeService.is_managed_device(device)]
    return devices


def _assert_observability_allowed(db: Session, device: Device | None, *, feature: str):
    try:
        PreviewManagedNodeService.assert_managed_for_feature(db, device, feature=feature)
    except PermissionError as exc:
        detail = exc.args[0] if exc.args else {"message": "Managed node required"}
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail=detail)


@router.get("/summary", dependencies=[Depends(deps.get_current_user)])
def get_observability_summary(db: Session = Depends(get_db)):
    devices = _preview_managed_devices(db)
    device_ids = [int(device.id) for device in devices]
    total = len(devices)
    online = sum(1 for device in devices if str(device.status or "").lower() == "online")
    offline = max(int(total) - int(online), 0)

    latest_metrics = []
    if device_ids:
        latest_ts = (
            db.query(SystemMetric.device_id, func.max(SystemMetric.timestamp).label("ts"))
            .filter(SystemMetric.device_id.in_(device_ids))
            .group_by(SystemMetric.device_id)
            .subquery()
        )
        latest_metrics = (
            db.query(SystemMetric)
            .join(
                latest_ts,
                (SystemMetric.device_id == latest_ts.c.device_id)
                & (SystemMetric.timestamp == latest_ts.c.ts),
            )
            .all()
        )
    metrics_by_device_id = {m.device_id: m for m in latest_metrics}

    enriched = []
    for d in devices:
        m = metrics_by_device_id.get(d.id)
        enriched.append(
            {
                "device_id": d.id,
                "name": d.name,
                "ip": d.ip_address,
                "status": d.status,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "cpu": float(getattr(m, "cpu_usage", 0.0) or 0.0) if m else 0.0,
                "memory": float(getattr(m, "memory_usage", 0.0) or 0.0) if m else 0.0,
                "traffic_in_bps": float(getattr(m, "traffic_in", 0.0) or 0.0) if m else 0.0,
                "traffic_out_bps": float(getattr(m, "traffic_out", 0.0) or 0.0) if m else 0.0,
            }
        )

    top_cpu = sorted(enriched, key=lambda x: x.get("cpu", 0.0), reverse=True)[:5]
    top_memory = sorted(enriched, key=lambda x: x.get("memory", 0.0), reverse=True)[:5]

    return {
        "counts": {"devices": int(total), "online": int(online), "offline": int(offline)},
        "top_cpu": top_cpu,
        "top_memory": top_memory,
    }


@router.get("/devices", dependencies=[Depends(deps.get_current_user)])
def list_observability_devices(db: Session = Depends(get_db)):
    devices = sorted(_preview_managed_devices(db), key=lambda device: str(device.name or "").lower())
    device_ids = [int(device.id) for device in devices]
    latest_metrics = []
    if device_ids:
        latest_ts = (
            db.query(SystemMetric.device_id, func.max(SystemMetric.timestamp).label("ts"))
            .filter(SystemMetric.device_id.in_(device_ids))
            .group_by(SystemMetric.device_id)
            .subquery()
        )
        latest_metrics = (
            db.query(SystemMetric)
            .join(
                latest_ts,
                (SystemMetric.device_id == latest_ts.c.device_id)
                & (SystemMetric.timestamp == latest_ts.c.ts),
            )
            .all()
        )
    metrics_by_device_id = {m.device_id: m for m in latest_metrics}
    out = []
    for d in devices:
        m = metrics_by_device_id.get(d.id)
        variables = d.variables if isinstance(d.variables, dict) else {}
        raw_tags = variables.get("tags") if isinstance(variables, dict) else None
        tags = []
        if isinstance(raw_tags, list):
            tags = [str(x) for x in raw_tags if x is not None and str(x).strip()]
        elif isinstance(raw_tags, str) and raw_tags.strip():
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        out.append(
            {
                "id": d.id,
                "name": d.name,
                "ip": d.ip_address,
                "site_id": d.site_id,
                "device_type": d.device_type,
                "role": d.role,
                "tags": tags,
                "status": d.status,
                "reachability_status": d.reachability_status,
                "last_seen": d.last_seen.isoformat() if d.last_seen else None,
                "cpu": float(getattr(m, "cpu_usage", 0.0) or 0.0) if m else 0.0,
                "memory": float(getattr(m, "memory_usage", 0.0) or 0.0) if m else 0.0,
                "traffic_in_bps": float(getattr(m, "traffic_in", 0.0) or 0.0) if m else 0.0,
                "traffic_out_bps": float(getattr(m, "traffic_out", 0.0) or 0.0) if m else 0.0,
                "latest_ts": m.timestamp.isoformat() if m and m.timestamp else None,
            }
        )
    return out


@router.get("/devices/{device_id}/timeseries", dependencies=[Depends(deps.get_current_user)])
def get_device_timeseries(
    device_id: int,
    minutes: int = Query(360, ge=5, le=4320),
    limit: int = Query(720, ge=60, le=5000),
    db: Session = Depends(get_db),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail={"message": "Device not found"})
    _assert_observability_allowed(db, device, feature="observability")
    since = _utc_now() - timedelta(minutes=int(minutes))

    rows = (
        db.query(SystemMetric)
        .filter(SystemMetric.device_id == device_id, SystemMetric.timestamp >= since)
        .order_by(SystemMetric.timestamp.desc())
        .limit(int(limit))
        .all()
    )
    rows = list(reversed(rows))

    points = []
    for r in rows:
        ts = r.timestamp
        points.append(
            {
                "ts": ts.isoformat() if ts else None,
                "cpu": float(r.cpu_usage or 0.0),
                "memory": float(r.memory_usage or 0.0),
                "traffic_in_bps": float(r.traffic_in or 0.0),
                "traffic_out_bps": float(r.traffic_out or 0.0),
            }
        )

    return {
        "device": {
            "id": device.id,
            "name": device.name,
            "ip": device.ip_address,
            "status": device.status,
            "last_seen": device.last_seen.isoformat() if device and device.last_seen else None,
        }
        if device
        else None,
        "range": {"minutes": int(minutes)},
        "points": points,
    }


@router.get("/devices/{device_id}/interfaces", dependencies=[Depends(deps.get_current_user)])
def list_device_interfaces(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail={"message": "Device not found"})
    _assert_observability_allowed(db, device, feature="observability")
    latest_ts = (
        db.query(InterfaceMetric.interface_name, func.max(InterfaceMetric.timestamp).label("ts"))
        .filter(InterfaceMetric.device_id == device_id)
        .group_by(InterfaceMetric.interface_name)
        .subquery()
    )
    rows = (
        db.query(InterfaceMetric)
        .join(
            latest_ts,
            (InterfaceMetric.interface_name == latest_ts.c.interface_name)
            & (InterfaceMetric.timestamp == latest_ts.c.ts),
        )
        .order_by(InterfaceMetric.interface_name.asc())
        .all()
    )
    out = []
    for r in rows:
        out.append(
            {
                "interface": r.interface_name,
                "traffic_in_bps": float(r.traffic_in_bps or 0.0),
                "traffic_out_bps": float(r.traffic_out_bps or 0.0),
                "in_errors_per_sec": float(r.in_errors_per_sec or 0.0),
                "out_errors_per_sec": float(r.out_errors_per_sec or 0.0),
                "in_discards_per_sec": float(r.in_discards_per_sec or 0.0),
                "out_discards_per_sec": float(r.out_discards_per_sec or 0.0),
                "ts": r.timestamp.isoformat() if r.timestamp else None,
            }
        )
    return out


@router.get("/devices/{device_id}/interfaces/timeseries", dependencies=[Depends(deps.get_current_user)])
def get_interface_timeseries(
    device_id: int,
    name: str = Query(..., min_length=1),
    minutes: int = Query(360, ge=5, le=4320),
    limit: int = Query(720, ge=60, le=5000),
    db: Session = Depends(get_db),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail={"message": "Device not found"})
    _assert_observability_allowed(db, device, feature="observability")
    since = _utc_now() - timedelta(minutes=int(minutes))
    rows = (
        db.query(InterfaceMetric)
        .filter(
            InterfaceMetric.device_id == device_id,
            InterfaceMetric.interface_name == name,
            InterfaceMetric.timestamp >= since,
        )
        .order_by(InterfaceMetric.timestamp.desc())
        .limit(int(limit))
        .all()
    )
    rows = list(reversed(rows))
    points = []
    for r in rows:
        points.append(
            {
                "ts": r.timestamp.isoformat() if r.timestamp else None,
                "traffic_in_bps": float(r.traffic_in_bps or 0.0),
                "traffic_out_bps": float(r.traffic_out_bps or 0.0),
                "in_errors_per_sec": float(r.in_errors_per_sec or 0.0),
                "out_errors_per_sec": float(r.out_errors_per_sec or 0.0),
                "in_discards_per_sec": float(r.in_discards_per_sec or 0.0),
                "out_discards_per_sec": float(r.out_discards_per_sec or 0.0),
            }
        )
    return {"device_id": device_id, "interface": name, "range": {"minutes": int(minutes)}, "points": points}
