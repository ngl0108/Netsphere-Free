import asyncio
import json
import ipaddress
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.models.topology import TopologyLayout, TopologyChangeEvent
from app.models.device import Device, Site
from app.schemas.topology import TopologyLayoutCreate, TopologyLayoutResponse
from app.services.path_trace_service import PathTraceService
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.topology_candidate import TopologyNeighborCandidate
from app.services.candidate_recommendation_service import CandidateRecommendationService
from app.services.realtime_event_bus import realtime_event_bus
from app.services.topology_event_service import publish_topology_event
from app.services.topology_snapshot_service import TopologySnapshotService

router = APIRouter()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


_CANDIDATE_BACKLOG_STATUSES = {"unmatched", "low_confidence"}
_CANDIDATE_RESOLVED_STATUSES = {"promoted", "ignored", "approved"}
_CANDIDATE_REASON_LABELS = {
    "ip_match": "IP match found",
    "name_exact": "Exact hostname match",
    "name_normalized": "Normalized hostname match",
    "name_prefix": "Prefix hostname match",
    "ambiguous_name_exact": "Multiple exact hostname matches",
    "ambiguous_name_normalized": "Multiple normalized hostname matches",
    "ambiguous_name_prefix": "Multiple prefix hostname matches",
    "missing_neighbor_identity": "Neighbor identity missing",
    "missing_mgmt_ip": "Management IP missing",
    "not_found": "No inventory match",
    "weak": "Weak match evidence",
    "manual": "Manual action",
    "noise": "Noise candidate",
    "unknown": "Unknown reason",
}


def _ensure_aware(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    aware = _ensure_aware(dt)
    return aware.isoformat() if aware else None


def _candidate_reason_meta(reason: Optional[str]) -> dict:
    raw = str(reason or "").strip()
    if not raw:
        return {
            "raw": "",
            "code": "unknown",
            "label": _CANDIDATE_REASON_LABELS["unknown"],
            "kind": "other",
            "detail": None,
        }

    code, _, tail = raw.partition(":")
    code = str(code or "").strip().lower() or "unknown"
    detail = str(tail or "").strip() or None

    if code.startswith("ambiguous_"):
        kind = "ambiguous"
    elif code.startswith("missing_"):
        kind = "missing_data"
    elif code in {"ip_match", "name_exact", "name_normalized", "name_prefix"}:
        kind = "match"
    elif code == "not_found":
        kind = "not_found"
    else:
        kind = "other"

    meta = {
        "raw": raw,
        "code": code,
        "label": _CANDIDATE_REASON_LABELS.get(code, raw),
        "kind": kind,
        "detail": detail,
    }
    if kind == "ambiguous" and detail:
        candidate_ids = []
        for part in detail.split(","):
            part = str(part or "").strip()
            if not part:
                continue
            try:
                candidate_ids.append(int(part))
            except Exception:
                continue
        if candidate_ids:
            meta["candidate_ids"] = candidate_ids
    return meta


def _candidate_priority_score(
    candidate: TopologyNeighborCandidate,
    reason_meta: dict,
    now: datetime,
) -> float:
    status = str(getattr(candidate, "status", "") or "").strip().lower()
    confidence = float(getattr(candidate, "confidence", 0.0) or 0.0)
    confidence = max(0.0, min(confidence, 1.0))
    last_seen = _ensure_aware(getattr(candidate, "last_seen", None))
    age_seconds = max(0.0, (now - last_seen).total_seconds()) if last_seen else 0.0
    age_hours = age_seconds / 3600.0
    backlog = status in _CANDIDATE_BACKLOG_STATUSES

    if status == "low_confidence":
        score = 78.0
    elif status == "unmatched":
        score = 70.0
    elif status in _CANDIDATE_RESOLVED_STATUSES:
        score = 8.0
    else:
        score = 24.0

    if backlog:
        score += min(age_hours * 1.6, 30.0)
        score += (1.0 - confidence) * 18.0
        if age_hours >= 24.0:
            score += 10.0
        if reason_meta.get("kind") == "ambiguous":
            score += 10.0
        elif reason_meta.get("code") == "not_found":
            score += 8.0
        elif reason_meta.get("code") == "missing_mgmt_ip":
            score -= 6.0
        elif reason_meta.get("code") == "missing_neighbor_identity":
            score -= 14.0

        protocol = str(getattr(candidate, "protocol", "") or "").strip().upper()
        if protocol in {"LLDP", "CDP"}:
            score += 5.0
        elif protocol == "FDB":
            score -= 4.0

        if str(getattr(candidate, "mgmt_ip", "") or "").strip():
            score += 4.0
        if getattr(candidate, "discovery_job_id", None) is not None:
            score += 3.0

    return round(max(score, 0.0), 2)


def _candidate_priority_band(score: float) -> str:
    if score >= 100.0:
        return "critical"
    if score >= 84.0:
        return "high"
    if score >= 58.0:
        return "medium"
    return "low"


def _candidate_next_action(
    candidate: TopologyNeighborCandidate,
    reason_meta: dict,
    actionable: bool,
) -> dict:
    if not actionable:
        return {"code": "needs_more_identity", "label": "Collect more neighbor identity"}

    code = str(reason_meta.get("code") or "").strip().lower()
    if reason_meta.get("kind") == "ambiguous":
        return {"code": "review_matches", "label": "Review competing matches"}
    if code == "missing_mgmt_ip":
        return {"code": "fill_mgmt_ip_or_use_suggestion", "label": "Fill management IP or use top suggestion"}
    if code == "not_found":
        return {"code": "promote_or_discover", "label": "Promote into discovery queue"}
    if code in {"ip_match", "name_exact", "name_normalized", "name_prefix"}:
        return {"code": "verify_and_promote", "label": "Verify and promote"}
    return {"code": "review_candidate", "label": "Review candidate details"}


def _serialize_candidate(
    candidate: TopologyNeighborCandidate,
    source_device: Optional[Device],
    site: Optional[Site],
    now: datetime,
) -> dict:
    last_seen = _ensure_aware(getattr(candidate, "last_seen", None))
    first_seen = _ensure_aware(getattr(candidate, "first_seen", None))
    age_seconds = int(max(0.0, (now - last_seen).total_seconds())) if last_seen else None
    status = str(getattr(candidate, "status", "") or "").strip().lower() or "unknown"
    reason_meta = _candidate_reason_meta(getattr(candidate, "reason", None))
    backlog = status in _CANDIDATE_BACKLOG_STATUSES
    actionable = backlog and bool(
        str(getattr(candidate, "neighbor_name", "") or "").strip()
        or str(getattr(candidate, "mgmt_ip", "") or "").strip()
    )
    priority_score = _candidate_priority_score(candidate, reason_meta, now)

    source_name = (
        getattr(source_device, "hostname", None)
        or getattr(source_device, "name", None)
        or (f"Device {getattr(candidate, 'source_device_id', '')}" if getattr(candidate, "source_device_id", None) else None)
    )
    next_action = _candidate_next_action(candidate, reason_meta, actionable)

    return {
        "id": candidate.id,
        "discovery_job_id": candidate.discovery_job_id,
        "source_device_id": candidate.source_device_id,
        "source_device_name": source_name,
        "source_device_ip": getattr(source_device, "ip_address", None),
        "site_id": getattr(source_device, "site_id", None),
        "site_name": getattr(site, "name", None),
        "neighbor_name": candidate.neighbor_name,
        "mgmt_ip": candidate.mgmt_ip,
        "local_interface": candidate.local_interface,
        "remote_interface": candidate.remote_interface,
        "protocol": candidate.protocol,
        "confidence": float(candidate.confidence or 0.0),
        "reason": candidate.reason,
        "reason_code": reason_meta.get("code"),
        "reason_meta": reason_meta,
        "status": candidate.status,
        "first_seen": _dt_to_iso(first_seen),
        "last_seen": _dt_to_iso(last_seen),
        "age_seconds": age_seconds,
        "stale": bool(backlog and age_seconds is not None and age_seconds >= 24 * 3600),
        "backlog": backlog,
        "actionable": actionable,
        "priority_score": priority_score,
        "priority_band": _candidate_priority_band(priority_score),
        "next_action": next_action,
        "_sort_last_seen": last_seen or datetime.min.replace(tzinfo=timezone.utc),
        "_sort_first_seen": first_seen or datetime.min.replace(tzinfo=timezone.utc),
    }


@router.get("/layout", response_model=Optional[TopologyLayoutResponse])
def get_user_layout(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """
    Get current user's saved topology layout.
    """
    layout = db.query(TopologyLayout).filter(
        TopologyLayout.user_id == current_user.id
    ).first()
    
    if not layout:
        # Check for a shared/default layout if user has none? (Optional)
        return None
        
    return layout

@router.post("/layout", response_model=TopologyLayoutResponse)
def save_user_layout(
    layout_in: TopologyLayoutCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator) # Only operators+ can save layouts? Or anyone?
):
    """
    Save or update user's topology layout.
    """
    existing_layout = db.query(TopologyLayout).filter(
        TopologyLayout.user_id == current_user.id
    ).first()

    if existing_layout:
        # Update existing
        existing_layout.data = layout_in.data
        existing_layout.updated_at = func.now()
        existing_layout.name = layout_in.name or existing_layout.name
        db.commit()
        db.refresh(existing_layout)
        return existing_layout
    else:
        # Create new
        new_layout = TopologyLayout(
            user_id=current_user.id,
            name=layout_in.name or "My Layout",
            data=layout_in.data,
            is_shared=layout_in.is_shared
        )
        db.add(new_layout)
        db.commit()
        db.refresh(new_layout)
        return new_layout

@router.delete("/layout")
def reset_user_layout(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator)
):
    """
    Delete user's saved layout (Reset).
    """
    db.query(TopologyLayout).filter(
        TopologyLayout.user_id == current_user.id
    ).delete()
    db.commit()
    return {"message": "Layout reset successfully"}


class PathTraceRequest(BaseModel):
    src_ip: str
    dst_ip: str


@router.post("/path-trace")
def path_trace(
    req: PathTraceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    try:
        ipaddress.ip_address(req.src_ip)
    except ValueError:
        raise HTTPException(status_code=422, detail={"message": "Invalid src_ip", "field": "src_ip"})
    try:
        ipaddress.ip_address(req.dst_ip)
    except ValueError:
        raise HTTPException(status_code=422, detail={"message": "Invalid dst_ip", "field": "dst_ip"})

    service = PathTraceService(db)
    result = service.trace_path(req.src_ip, req.dst_ip)
    if isinstance(result, dict) and result.get("error"):
        raise HTTPException(status_code=404, detail={"message": str(result.get("error")), "result": result})
    return result


@router.get("/stream")
async def stream_topology_events(
    request: Request,
    current_user: User = Depends(deps.require_viewer),
):
    _ = current_user
    q = realtime_event_bus.subscribe()

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.to_thread(q.get, True, 15.0)
                    yield f"event: {msg.event}\ndata: {json.dumps(msg.data, ensure_ascii=False)}\n\n"
                except Exception:
                    yield "event: ping\ndata: {}\n\n"
        finally:
            realtime_event_bus.unsubscribe(q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class SnapshotCreateRequest(BaseModel):
    site_id: Optional[int] = None
    job_id: Optional[int] = None
    label: Optional[str] = None
    metadata: Optional[dict] = None


@router.get("/snapshots")
def list_topology_snapshots(
    site_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    return TopologySnapshotService.list_snapshots(db, site_id=site_id, limit=limit)


@router.post("/snapshots")
def create_topology_snapshot(
    req: SnapshotCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    snap = TopologySnapshotService.create_snapshot(
        db,
        site_id=req.site_id,
        job_id=req.job_id,
        label=req.label,
        metadata=req.metadata or {},
    )
    return TopologySnapshotService.to_dict(snap)


@router.get("/snapshots/{snapshot_id}")
def get_topology_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    try:
        return TopologySnapshotService.get_snapshot_graph(db, snapshot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/diff")
def diff_topology_snapshots(
    snapshot_a: int,
    snapshot_b: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    try:
        return TopologySnapshotService.diff_snapshots(db, snapshot_a, snapshot_b)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/candidates")
def list_topology_candidates(
    job_id: Optional[int] = None,
    source_device_id: Optional[int] = None,
    site_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    order_by: str = "last_seen",
    order_dir: str = "desc",
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    _ = current_user
    query = (
        db.query(TopologyNeighborCandidate, Device, Site)
        .outerjoin(Device, Device.id == TopologyNeighborCandidate.source_device_id)
        .outerjoin(Site, Site.id == Device.site_id)
    )
    if site_id is not None:
        query = query.filter(Device.site_id == site_id)
    if job_id is not None:
        query = query.filter(TopologyNeighborCandidate.discovery_job_id == job_id)
    if source_device_id is not None:
        query = query.filter(TopologyNeighborCandidate.source_device_id == source_device_id)
    if status:
        query = query.filter(TopologyNeighborCandidate.status == status)
    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                TopologyNeighborCandidate.neighbor_name.ilike(like),
                TopologyNeighborCandidate.mgmt_ip.ilike(like),
                TopologyNeighborCandidate.reason.ilike(like),
                Device.name.ilike(like),
                Device.hostname.ilike(like),
                Device.ip_address.ilike(like),
                Site.name.ilike(like),
            )
        )

    if limit < 1:
        limit = 1
    if limit > 2000:
        limit = 2000

    rows = query.all()
    now = _utc_now()
    items = [_serialize_candidate(candidate, source_device, site, now) for candidate, source_device, site in rows]

    order_key = str(order_by or "last_seen").strip().lower()
    reverse = str(order_dir or "desc").strip().lower() != "asc"

    if order_key == "confidence":
        items.sort(key=lambda x: (float(x.get("confidence") or 0.0), float(x.get("priority_score") or 0.0)), reverse=reverse)
    elif order_key == "first_seen":
        items.sort(key=lambda x: (x.get("_sort_first_seen"), float(x.get("priority_score") or 0.0)), reverse=reverse)
    elif order_key == "priority":
        items.sort(
            key=lambda x: (
                float(x.get("priority_score") or 0.0),
                x.get("_sort_last_seen"),
                float(x.get("confidence") or 0.0),
            ),
            reverse=reverse,
        )
    else:
        items.sort(key=lambda x: (x.get("_sort_last_seen"), float(x.get("priority_score") or 0.0)), reverse=reverse)

    for item in items:
        item.pop("_sort_last_seen", None)
        item.pop("_sort_first_seen", None)

    return items[:limit]


@router.get("/candidates/summary")
def get_topology_candidate_summary(
    job_id: Optional[int] = None,
    source_device_id: Optional[int] = None,
    site_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    q = db.query(TopologyNeighborCandidate)
    if site_id is not None:
        q = q.join(Device, Device.id == TopologyNeighborCandidate.source_device_id).filter(Device.site_id == site_id)
    if job_id is not None:
        q = q.filter(TopologyNeighborCandidate.discovery_job_id == job_id)
    if source_device_id is not None:
        q = q.filter(TopologyNeighborCandidate.source_device_id == source_device_id)

    status_rows = (
        q.with_entities(
            TopologyNeighborCandidate.status,
            func.count(TopologyNeighborCandidate.id).label("cnt"),
        )
        .group_by(TopologyNeighborCandidate.status)
        .all()
    )
    by_status = {}
    for st, cnt in status_rows:
        key = str(st or "").strip().lower() or "unknown"
        by_status[key] = by_status.get(key, 0) + int(cnt or 0)

    total = int(sum(by_status.values()))
    backlog_unmatched = int(by_status.get("unmatched", 0))
    backlog_low_conf = int(by_status.get("low_confidence", 0))
    backlog_total = backlog_unmatched + backlog_low_conf
    resolved_promoted = int(by_status.get("promoted", 0))
    resolved_ignored = int(by_status.get("ignored", 0))
    resolved_total = resolved_promoted + resolved_ignored

    stale_since = _utc_now() - timedelta(hours=24)
    stale_backlog_24h = (
        q.filter(TopologyNeighborCandidate.status.in_(["unmatched", "low_confidence"]))
        .filter(TopologyNeighborCandidate.last_seen <= stale_since)
        .count()
    )
    resolved_24h = (
        q.filter(TopologyNeighborCandidate.status.in_(["promoted", "ignored"]))
        .filter(TopologyNeighborCandidate.last_seen >= stale_since)
        .count()
    )

    return {
        "scope": {
            "job_id": int(job_id) if job_id is not None else None,
            "source_device_id": int(source_device_id) if source_device_id is not None else None,
            "site_id": int(site_id) if site_id is not None else None,
        },
        "as_of": _utc_now().isoformat(),
        "totals": {
            "total": total,
            "backlog_total": backlog_total,
            "backlog_unmatched": backlog_unmatched,
            "backlog_low_confidence": backlog_low_conf,
            "resolved_total": resolved_total,
            "resolved_promoted": resolved_promoted,
            "resolved_ignored": resolved_ignored,
            "stale_backlog_24h": int(stale_backlog_24h or 0),
            "resolved_24h": int(resolved_24h or 0),
        },
        "kpi": {
            "backlog_ratio_pct": round((backlog_total / total) * 100.0, 2) if total > 0 else 0.0,
            "resolved_ratio_pct": round((resolved_total / total) * 100.0, 2) if total > 0 else 0.0,
            "low_confidence_share_pct": round((backlog_low_conf / backlog_total) * 100.0, 2) if backlog_total > 0 else 0.0,
        },
        "by_status": by_status,
    }


@router.get("/candidates/summary/trend")
def get_topology_candidate_summary_trend(
    days: int = 7,
    limit: int = 20,
    source_device_id: Optional[int] = None,
    site_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    if days < 1:
        days = 1
    if days > 90:
        days = 90
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    since = _utc_now() - timedelta(days=int(days))
    q = db.query(TopologyNeighborCandidate).filter(TopologyNeighborCandidate.last_seen >= since)
    if site_id is not None:
        q = q.join(Device, Device.id == TopologyNeighborCandidate.source_device_id).filter(Device.site_id == site_id)
    if source_device_id is not None:
        q = q.filter(TopologyNeighborCandidate.source_device_id == source_device_id)
    rows = q.all()

    def _dkey(dt):
        if dt is None:
            return _utc_now().date().isoformat()
        try:
            return dt.date().isoformat()
        except Exception:
            return str(dt)[:10]

    day_map = {}
    job_map = {}
    for r in rows:
        status = str(getattr(r, "status", "") or "").strip().lower() or "unknown"
        dkey = _dkey(getattr(r, "last_seen", None))
        day_bucket = day_map.setdefault(
            dkey,
            {"backlog_total": 0, "low_confidence": 0, "unmatched": 0, "resolved_total": 0, "promoted": 0, "ignored": 0},
        )
        if status == "low_confidence":
            day_bucket["backlog_total"] += 1
            day_bucket["low_confidence"] += 1
        elif status == "unmatched":
            day_bucket["backlog_total"] += 1
            day_bucket["unmatched"] += 1
        elif status == "promoted":
            day_bucket["resolved_total"] += 1
            day_bucket["promoted"] += 1
        elif status == "ignored":
            day_bucket["resolved_total"] += 1
            day_bucket["ignored"] += 1

        jid = getattr(r, "discovery_job_id", None)
        if jid is not None:
            jb = job_map.setdefault(
                int(jid),
                {
                    "job_id": int(jid),
                    "backlog_total": 0,
                    "low_confidence": 0,
                    "unmatched": 0,
                    "resolved_total": 0,
                    "promoted": 0,
                    "ignored": 0,
                    "last_seen": None,
                },
            )
            if status == "low_confidence":
                jb["backlog_total"] += 1
                jb["low_confidence"] += 1
            elif status == "unmatched":
                jb["backlog_total"] += 1
                jb["unmatched"] += 1
            elif status == "promoted":
                jb["resolved_total"] += 1
                jb["promoted"] += 1
            elif status == "ignored":
                jb["resolved_total"] += 1
                jb["ignored"] += 1
            lseen = getattr(r, "last_seen", None)
            if lseen and (jb["last_seen"] is None or lseen > jb["last_seen"]):
                jb["last_seen"] = lseen

    # Fill empty dates in window
    series = []
    for i in range(int(days)):
        d = (since.date() + timedelta(days=i)).isoformat()
        b = day_map.get(
            d,
            {"backlog_total": 0, "low_confidence": 0, "unmatched": 0, "resolved_total": 0, "promoted": 0, "ignored": 0},
        )
        series.append({"date": d, **b})

    jobs = sorted(
        job_map.values(),
        key=lambda x: (int(x.get("backlog_total", 0)), int(x.get("resolved_total", 0))),
        reverse=True,
    )[: int(limit)]
    for j in jobs:
        dt = j.get("last_seen")
        j["last_seen"] = dt.isoformat() if dt else None

    return {
        "window_days": int(days),
        "since": since.isoformat(),
        "source_device_id": int(source_device_id) if source_device_id is not None else None,
        "site_id": int(site_id) if site_id is not None else None,
        "series": series,
        "jobs": jobs,
    }


@router.get("/candidates/{candidate_id}/recommendations")
def candidate_recommendations(
    candidate_id: int,
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    cand = db.query(TopologyNeighborCandidate).filter(TopologyNeighborCandidate.id == candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return CandidateRecommendationService.recommend_for_candidate(db, cand, limit=limit)


class CandidatePromoteRequest(BaseModel):
    job_id: Optional[int] = None
    ip_address: Optional[str] = None
    hostname: Optional[str] = None


@router.post("/candidates/{candidate_id}/promote")
def promote_candidate_to_discovery(
    candidate_id: int,
    req: CandidatePromoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator)
):
    cand = db.query(TopologyNeighborCandidate).filter(TopologyNeighborCandidate.id == candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    job_id = req.job_id or cand.discovery_job_id
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id is required")

    job = db.query(DiscoveryJob).filter(DiscoveryJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Discovery job not found")

    ip_address = (req.ip_address or cand.mgmt_ip or "").strip()
    if not ip_address:
        raise HTTPException(status_code=400, detail="ip_address is required")

    hostname = (req.hostname or cand.neighbor_name or ip_address).strip()

    existing = db.query(DiscoveredDevice).filter(
        DiscoveredDevice.job_id == job_id,
        DiscoveredDevice.ip_address == ip_address,
    ).first()

    if existing:
        if not existing.hostname and hostname:
            existing.hostname = hostname
        if existing.status in ["ignored"]:
            existing.status = "new"
        discovered_id = existing.id
    else:
        discovered = DiscoveredDevice(
            job_id=job_id,
            ip_address=ip_address,
            hostname=hostname,
            vendor="Unknown",
            model=None,
            os_version=None,
            snmp_status="unknown",
            status="new",
            matched_device_id=None,
        )
        db.add(discovered)
        db.flush()
        discovered_id = discovered.id

    cand.mgmt_ip = ip_address
    cand.status = "promoted"
    source_device = db.query(Device).filter(Device.id == cand.source_device_id).first() if cand.source_device_id else None
    publish_topology_event(
        db,
        "topology_candidate_update",
        {
            "action": "promote",
            "candidate_ids": [int(cand.id)],
            "job_id": int(job_id),
            "source_device_id": int(cand.source_device_id) if cand.source_device_id is not None else None,
            "refresh_hint": "candidates",
        },
        site_id=getattr(source_device, "site_id", None),
        device_id=int(cand.source_device_id) if cand.source_device_id is not None else None,
        persist=True,
        realtime=True,
    )
    db.commit()

    return {"message": "Promoted to discovery", "discovered_id": discovered_id}


@router.post("/candidates/{candidate_id}/ignore")
def ignore_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator)
):
    cand = db.query(TopologyNeighborCandidate).filter(TopologyNeighborCandidate.id == candidate_id).first()
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")
    cand.status = "ignored"
    source_device = db.query(Device).filter(Device.id == cand.source_device_id).first() if cand.source_device_id else None
    publish_topology_event(
        db,
        "topology_candidate_update",
        {
            "action": "ignore",
            "candidate_ids": [int(cand.id)],
            "source_device_id": int(cand.source_device_id) if cand.source_device_id is not None else None,
            "refresh_hint": "candidates",
        },
        site_id=getattr(source_device, "site_id", None),
        device_id=int(cand.source_device_id) if cand.source_device_id is not None else None,
        persist=True,
        realtime=True,
    )
    db.commit()
    return {"message": "Candidate ignored"}


class BulkIgnoreRequest(BaseModel):
    candidate_ids: List[int]


@router.post("/candidates/bulk-ignore")
def bulk_ignore_candidates(
    req: BulkIgnoreRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator)
):
    if not req.candidate_ids:
        return {"ignored": 0}
    candidates = db.query(TopologyNeighborCandidate).filter(
        TopologyNeighborCandidate.id.in_(req.candidate_ids)
    ).all()
    ignored = db.query(TopologyNeighborCandidate).filter(
        TopologyNeighborCandidate.id.in_(req.candidate_ids)
    ).update({"status": "ignored"}, synchronize_session=False)
    source_device_ids = sorted({int(c.source_device_id) for c in candidates if getattr(c, "source_device_id", None) is not None})
    site_id = None
    if source_device_ids:
        site_id = db.query(Device.site_id).filter(Device.id == source_device_ids[0]).scalar()
    publish_topology_event(
        db,
        "topology_candidate_update",
        {
            "action": "bulk_ignore",
            "candidate_ids": [int(cid) for cid in req.candidate_ids],
            "source_device_ids": source_device_ids,
            "ignored": int(ignored or 0),
            "refresh_hint": "candidates",
        },
        site_id=site_id,
        device_id=source_device_ids[0] if source_device_ids else None,
        persist=True,
        realtime=True,
    )
    db.commit()
    return {"ignored": int(ignored or 0)}


class BulkPromoteItem(BaseModel):
    candidate_id: int
    ip_address: Optional[str] = None
    hostname: Optional[str] = None


class BulkPromoteRequest(BaseModel):
    job_id: int
    items: List[BulkPromoteItem]


@router.post("/candidates/bulk-promote")
def bulk_promote_candidates(
    req: BulkPromoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator)
):
    job = db.query(DiscoveryJob).filter(DiscoveryJob.id == req.job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Discovery job not found")

    promoted = 0
    created = 0
    updated = 0
    skipped = 0
    affected_candidate_ids = []
    affected_source_device_ids = set()

    for item in req.items or []:
        cand = db.query(TopologyNeighborCandidate).filter(TopologyNeighborCandidate.id == item.candidate_id).first()
        if not cand:
            skipped += 1
            continue
        affected_candidate_ids.append(int(cand.id))
        if cand.source_device_id is not None:
            affected_source_device_ids.add(int(cand.source_device_id))

        ip_address = (item.ip_address or cand.mgmt_ip or "").strip()
        if not ip_address:
            skipped += 1
            continue

        hostname = (item.hostname or cand.neighbor_name or ip_address).strip()

        existing = db.query(DiscoveredDevice).filter(
            DiscoveredDevice.job_id == req.job_id,
            DiscoveredDevice.ip_address == ip_address,
        ).first()

        if existing:
            if not existing.hostname and hostname:
                existing.hostname = hostname
                updated += 1
        else:
            discovered = DiscoveredDevice(
                job_id=req.job_id,
                ip_address=ip_address,
                hostname=hostname,
                vendor="Unknown",
                model=None,
                os_version=None,
                snmp_status="unknown",
                status="new",
                matched_device_id=None,
            )
            db.add(discovered)
            created += 1

        cand.mgmt_ip = ip_address
        cand.status = "promoted"
        promoted += 1

    site_id = None
    if affected_source_device_ids:
        site_id = db.query(Device.site_id).filter(Device.id == min(affected_source_device_ids)).scalar()
    publish_topology_event(
        db,
        "topology_candidate_update",
        {
            "action": "bulk_promote",
            "candidate_ids": affected_candidate_ids,
            "source_device_ids": sorted(affected_source_device_ids),
            "job_id": int(req.job_id),
            "promoted": int(promoted),
            "created": int(created),
            "updated": int(updated),
            "skipped": int(skipped),
            "refresh_hint": "candidates",
        },
        site_id=site_id,
        device_id=min(affected_source_device_ids) if affected_source_device_ids else None,
        persist=True,
        realtime=True,
    )
    db.commit()
    return {"promoted": promoted, "created": created, "updated": updated, "skipped": skipped}


@router.get("/events")
def list_topology_change_events(
    site_id: Optional[int] = None,
    device_id: Optional[int] = None,
    event_type: Optional[str] = None,
    source_device_id: Optional[int] = None,
    target_device_id: Optional[int] = None,
    protocol: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    if limit < 1:
        limit = 1
    if limit > 500:
        limit = 500

    q = db.query(TopologyChangeEvent)
    if site_id is not None:
        q = q.filter(TopologyChangeEvent.site_id == site_id)
    if device_id is not None:
        q = q.filter(TopologyChangeEvent.device_id == device_id)
    if event_type:
        q = q.filter(TopologyChangeEvent.event_type == event_type)

    rows = q.order_by(TopologyChangeEvent.created_at.desc()).limit(max(limit * 8, 200)).all()

    out = []
    protocol_u = str(protocol or "").strip().upper()
    for r in rows:
        try:
            payload = json.loads(r.payload_json or "{}")
            if not isinstance(payload, dict):
                payload = {}
        except Exception:
            payload = {}

        src = payload.get("device_id")
        dst = payload.get("neighbor_device_id")
        p = str(payload.get("protocol") or "").strip().upper()

        if source_device_id is not None or target_device_id is not None:
            s = int(src) if src is not None else None
            t = int(dst) if dst is not None else None
            pair_match = False
            if source_device_id is not None and target_device_id is not None:
                pair_match = (s == source_device_id and t == target_device_id) or (s == target_device_id and t == source_device_id)
            elif source_device_id is not None:
                pair_match = s == source_device_id or t == source_device_id
            else:
                pair_match = s == target_device_id or t == target_device_id
            if not pair_match:
                continue

        if protocol_u and p and p != protocol_u:
            continue

        out.append(
            {
                "id": int(r.id),
                "site_id": int(r.site_id) if r.site_id is not None else None,
                "device_id": int(r.device_id) if r.device_id is not None else None,
                "event_type": str(r.event_type or ""),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "payload": payload,
            }
        )
        if len(out) >= limit:
            break

    return out
