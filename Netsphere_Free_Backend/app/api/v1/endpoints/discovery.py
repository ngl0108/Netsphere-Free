import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from app.db.session import get_db
from app.api import deps
from app.models.user import User
from app.services.discovery_service import DiscoveryService
from app.db.session import SessionLocal
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.tasks.discovery_dispatch import dispatch_discovery_scan, dispatch_neighbor_crawl
from app.tasks.device_sync import enqueue_ssh_sync_batch, schedule_ssh_sync_batch
from app.tasks.topology_dispatch import dispatch_topology_refresh
from app.models.settings import SystemSetting
from app.models.topology import TopologySnapshot
from app.models.topology_candidate import TopologyNeighborCandidate
from app.models.device import Device
from app.services.capability_profile_service import CapabilityProfileService
from app.services.license_policy_service import LicensePolicyViolation

router = APIRouter()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

# --- Pydantic Schemas ---

class ScanRequest(BaseModel):
    cidr: str
    site_id: Optional[int] = None
    snmp_profile_id: Optional[int] = None
    community: str = "public"
    snmp_version: str = "v2c"
    snmp_port: int = 161
    snmp_v3_username: Optional[str] = None
    snmp_v3_security_level: Optional[str] = None
    snmp_v3_auth_proto: Optional[str] = None
    snmp_v3_auth_key: Optional[str] = None
    snmp_v3_priv_proto: Optional[str] = None
    snmp_v3_priv_key: Optional[str] = None


class CrawlRequest(BaseModel):
    seed_device_id: Optional[int] = None
    seed_ip: Optional[str] = None
    max_depth: int = 2
    site_id: Optional[int] = None
    snmp_profile_id: Optional[int] = None
    community: str = "public"
    snmp_version: str = "v2c"
    snmp_port: int = 161
    snmp_v3_username: Optional[str] = None
    snmp_v3_security_level: Optional[str] = None
    snmp_v3_auth_proto: Optional[str] = None
    snmp_v3_auth_key: Optional[str] = None
    snmp_v3_priv_proto: Optional[str] = None
    snmp_v3_priv_key: Optional[str] = None

class JobResponse(BaseModel):
    id: int
    cidr: str
    status: str
    progress: int = 0 # percent
    logs: str
    created_at: str

class DeviceResponse(BaseModel):
    id: int
    ip_address: str
    hostname: Optional[str]
    vendor: Optional[str]
    model: Optional[str] = None
    os_version: Optional[str] = None
    device_type: Optional[str] = None
    status: str # new, existing, approved
    snmp_status: str
    vendor_confidence: Optional[float] = 0.0
    chassis_candidate: Optional[bool] = False
    matched_device_id: Optional[int] = None
    issues: Optional[List[Dict[str, Any]]] = None
    evidence: Optional[Dict[str, Any]] = None

# --- Endpoints ---

@router.post("/scan", response_model=JobResponse)
def start_scan(
    request: ScanRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    service = DiscoveryService(db)
    
    # 1. Create Job (Sync)
    job = service.create_scan_job(
        request.cidr,
        request.community,
        site_id=request.site_id,
        snmp_profile_id=request.snmp_profile_id,
        snmp_version=request.snmp_version,
        snmp_port=request.snmp_port,
        snmp_v3_username=request.snmp_v3_username,
        snmp_v3_security_level=request.snmp_v3_security_level,
        snmp_v3_auth_proto=request.snmp_v3_auth_proto,
        snmp_v3_auth_key=request.snmp_v3_auth_key,
        snmp_v3_priv_proto=request.snmp_v3_priv_proto,
        snmp_v3_priv_key=request.snmp_v3_priv_key,
    )
    
    # Celery-only execution path. No local background fallback.
    dispatch = dispatch_discovery_scan(job.id, idempotency_key=f"scan:{job.id}")
    if dispatch.get("status") not in {"enqueued", "skipped"}:
        service._append_job_log(job, f"Queue dispatch failed: {dispatch.get('reason')}")
        job.status = "failed"
        db.commit()
        raise HTTPException(status_code=503, detail="Discovery worker queue unavailable")
    
    return {
        "id": job.id,
        "cidr": job.cidr,
        "status": job.status,
        "logs": job.logs,
        "created_at": str(job.created_at)
    }


@router.post("/crawl", response_model=JobResponse)
def start_neighbor_crawl(
    request: CrawlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    service = DiscoveryService(db)
    seed_ip = str(request.seed_ip or "").strip()
    seed_device_id = request.seed_device_id
    if not seed_ip and seed_device_id is None:
        raise HTTPException(status_code=400, detail="seed_device_id or seed_ip is required")
    cidr = f"seedip:{seed_ip}" if seed_ip else f"seed:{seed_device_id}"
    job = service.create_scan_job(
        cidr,
        request.community,
        site_id=request.site_id,
        snmp_profile_id=request.snmp_profile_id,
        snmp_version=request.snmp_version,
        snmp_port=request.snmp_port,
        snmp_v3_username=request.snmp_v3_username,
        snmp_v3_security_level=request.snmp_v3_security_level,
        snmp_v3_auth_proto=request.snmp_v3_auth_proto,
        snmp_v3_auth_key=request.snmp_v3_auth_key,
        snmp_v3_priv_proto=request.snmp_v3_priv_proto,
        snmp_v3_priv_key=request.snmp_v3_priv_key,
    )

    # Celery-only execution path. No local background fallback.
    dispatch = dispatch_neighbor_crawl(
        job.id,
        seed_device_id=seed_device_id,
        seed_ip=seed_ip,
        max_depth=int(request.max_depth or 2),
        idempotency_key=f"crawl:{job.id}",
    )
    if dispatch.get("status") not in {"enqueued", "skipped"}:
        service._append_job_log(job, f"Queue dispatch failed: {dispatch.get('reason')}")
        job.status = "failed"
        db.commit()
        raise HTTPException(status_code=503, detail="Neighbor crawl worker queue unavailable")

    return {
        "id": job.id,
        "cidr": job.cidr,
        "status": job.status,
        "logs": job.logs,
        "created_at": str(job.created_at),
    }

@router.get("/jobs/{id}")
def get_job_status(id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    job = db.query(DiscoveryJob).filter(DiscoveryJob.id == id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Calculate progress
    progress = 0
    if job.total_ips > 0:
        progress = int((job.scanned_ips / job.total_ips) * 100)
    elif job.status == 'completed':
        progress = 100
        
    return {
        "id": job.id,
        "cidr": job.cidr,
        "status": job.status,
        "progress": progress,
        "logs": job.logs,
        "created_at": str(job.created_at)
    }

@router.get("/jobs/{id}/results", response_model=List[DeviceResponse])
def get_job_results(id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    results = db.query(DiscoveredDevice).filter(DiscoveredDevice.job_id == id).all()
    return [
        {
            "id": r.id,
            "ip_address": r.ip_address,
            "hostname": r.hostname,
            "vendor": r.vendor,
            "model": r.model,
            "os_version": r.os_version,
            "device_type": r.device_type,
            "status": r.status,
            "snmp_status": r.snmp_status,
            "vendor_confidence": getattr(r, "vendor_confidence", 0.0),
            "chassis_candidate": getattr(r, "chassis_candidate", False),
            "matched_device_id": getattr(r, "matched_device_id", None),
            "issues": getattr(r, "issues", None),
            "evidence": getattr(r, "evidence", None),
        }
        for r in results
    ]


@router.get("/jobs/{id}/kpi")
def get_job_kpi(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    job = db.query(DiscoveryJob).filter(DiscoveryJob.id == id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    rows = db.query(DiscoveredDevice).filter(DiscoveredDevice.job_id == id).all()
    total = len(rows)
    approved = sum(1 for r in rows if str(getattr(r, "status", "") or "").lower() == "approved")
    existing = sum(1 for r in rows if str(getattr(r, "status", "") or "").lower() == "existing")
    ignored = sum(1 for r in rows if str(getattr(r, "status", "") or "").lower() == "ignored")

    auto_reflected = approved + existing
    auto_reflection_rate = round((auto_reflected / total) * 100.0, 2) if total > 0 else 0.0

    reviewed = approved + ignored
    false_positive_rate = round((ignored / reviewed) * 100.0, 2) if reviewed > 0 else 0.0

    first_snapshot = (
        db.query(TopologySnapshot)
        .filter(TopologySnapshot.job_id == id)
        .order_by(TopologySnapshot.created_at.asc(), TopologySnapshot.id.asc())
        .first()
    )

    first_map_seconds = None
    if first_snapshot and getattr(job, "created_at", None) and getattr(first_snapshot, "created_at", None):
        try:
            first_map_seconds = int((first_snapshot.created_at - job.created_at).total_seconds())
        except Exception:
            first_map_seconds = None

    try:
        threshold_row = db.query(SystemSetting).filter(SystemSetting.key == "topology_candidate_low_confidence_threshold").first()
        raw_threshold = threshold_row.value if threshold_row and threshold_row.value else "0.7"
        low_conf_threshold = float(raw_threshold)
    except Exception:
        low_conf_threshold = 0.7

    low_conf_candidates = (
        db.query(TopologyNeighborCandidate)
        .filter(TopologyNeighborCandidate.discovery_job_id == id)
        .filter(TopologyNeighborCandidate.confidence < float(low_conf_threshold))
        .count()
    )
    low_conf_reason_rows = (
        db.query(TopologyNeighborCandidate.reason, func.count(TopologyNeighborCandidate.id))
        .filter(TopologyNeighborCandidate.discovery_job_id == id)
        .filter(TopologyNeighborCandidate.confidence < float(low_conf_threshold))
        .group_by(TopologyNeighborCandidate.reason)
        .order_by(func.count(TopologyNeighborCandidate.id).desc(), TopologyNeighborCandidate.reason.asc())
        .limit(5)
        .all()
    )
    low_conf_top_reasons = []
    for reason, count in low_conf_reason_rows:
        r = str(reason or "").strip() or "unknown"
        low_conf_top_reasons.append({"reason": r, "count": int(count or 0)})
    low_conf_rate = round((float(low_conf_candidates) / float(total)) * 100.0, 2) if total > 0 else 0.0

    return {
        "job_id": int(job.id),
        "status": str(job.status or ""),
        "totals": {
            "discovered": total,
            "approved": approved,
            "existing": existing,
            "ignored": ignored,
            "auto_reflected": auto_reflected,
            "low_confidence_candidates": int(low_conf_candidates),
        },
        "kpi": {
            "first_map_seconds": first_map_seconds,
            "auto_reflection_rate_pct": auto_reflection_rate,
            "false_positive_rate_pct": false_positive_rate,
            "low_confidence_rate_pct": low_conf_rate,
            "low_confidence_top_reasons": low_conf_top_reasons,
        },
        "first_snapshot": {
            "id": int(first_snapshot.id) if first_snapshot else None,
            "created_at": str(first_snapshot.created_at) if first_snapshot and first_snapshot.created_at else None,
        },
    }


@router.get("/kpi/summary")
def get_kpi_summary(
    days: int = 7,
    limit: int = 100,
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
    if limit > 500:
        limit = 500

    since = _utc_now() - timedelta(days=int(days))
    jobs_query = db.query(DiscoveryJob).filter(DiscoveryJob.created_at >= since)
    if site_id is not None:
        jobs_query = jobs_query.filter(DiscoveryJob.site_id == site_id)
    jobs = jobs_query.order_by(DiscoveryJob.created_at.desc(), DiscoveryJob.id.desc()).limit(limit).all()
    job_ids = [int(j.id) for j in jobs]

    if not job_ids:
        return {
            "window_days": int(days),
            "site_id": int(site_id) if site_id is not None else None,
            "jobs_count": 0,
            "kpi": {
                "first_map_seconds_avg": None,
                "first_map_seconds_median": None,
                "first_map_seconds_p95": None,
                "auto_reflection_rate_pct": 0.0,
                "false_positive_rate_pct": 0.0,
                "low_confidence_rate_pct": 0.0,
            },
            "totals": {
                "discovered": 0,
                "approved": 0,
                "existing": 0,
                "ignored": 0,
                "auto_reflected": 0,
                "reviewed": 0,
                "low_confidence_candidates": 0,
            },
            "jobs": [],
        }

    status_rows = (
        db.query(
            DiscoveredDevice.job_id,
            DiscoveredDevice.status,
            func.count(DiscoveredDevice.id).label("cnt"),
        )
        .filter(DiscoveredDevice.job_id.in_(job_ids))
        .group_by(DiscoveredDevice.job_id, DiscoveredDevice.status)
        .all()
    )
    by_job_status: Dict[int, Dict[str, int]] = {}
    for jid, st, cnt in status_rows:
        d = by_job_status.setdefault(int(jid), {})
        key = str(st or "").strip().lower() or "unknown"
        d[key] = d.get(key, 0) + int(cnt or 0)

    first_snaps = (
        db.query(TopologySnapshot)
        .filter(TopologySnapshot.job_id.in_(job_ids))
        .order_by(TopologySnapshot.job_id.asc(), TopologySnapshot.created_at.asc(), TopologySnapshot.id.asc())
        .all()
    )
    first_snap_by_job: Dict[int, TopologySnapshot] = {}
    for s in first_snaps:
        jid = int(getattr(s, "job_id", 0) or 0)
        if jid and jid not in first_snap_by_job:
            first_snap_by_job[jid] = s

    try:
        threshold_row = db.query(SystemSetting).filter(SystemSetting.key == "topology_candidate_low_confidence_threshold").first()
        low_conf_threshold = float(threshold_row.value) if threshold_row and threshold_row.value else 0.7
    except Exception:
        low_conf_threshold = 0.7

    low_conf_rows = (
        db.query(
            TopologyNeighborCandidate.discovery_job_id,
            func.count(TopologyNeighborCandidate.id).label("cnt"),
        )
        .filter(TopologyNeighborCandidate.discovery_job_id.in_(job_ids))
        .filter(TopologyNeighborCandidate.confidence < float(low_conf_threshold))
        .group_by(TopologyNeighborCandidate.discovery_job_id)
        .all()
    )
    low_conf_by_job = {int(jid): int(cnt or 0) for jid, cnt in low_conf_rows}

    totals = {
        "discovered": 0,
        "approved": 0,
        "existing": 0,
        "ignored": 0,
        "auto_reflected": 0,
        "reviewed": 0,
        "low_confidence_candidates": 0,
    }
    first_map_samples: List[int] = []
    out_jobs = []

    for j in jobs:
        jid = int(j.id)
        st = by_job_status.get(jid, {})
        discovered = int(sum(st.values()))
        approved = int(st.get("approved", 0))
        existing = int(st.get("existing", 0))
        ignored = int(st.get("ignored", 0))
        auto_reflected = approved + existing
        reviewed = approved + ignored
        low_conf = int(low_conf_by_job.get(jid, 0))

        first_map_seconds = None
        first_snap = first_snap_by_job.get(jid)
        if first_snap and getattr(j, "created_at", None) and getattr(first_snap, "created_at", None):
            try:
                first_map_seconds = int((first_snap.created_at - j.created_at).total_seconds())
                if first_map_seconds >= 0:
                    first_map_samples.append(first_map_seconds)
            except Exception:
                first_map_seconds = None

        totals["discovered"] += discovered
        totals["approved"] += approved
        totals["existing"] += existing
        totals["ignored"] += ignored
        totals["auto_reflected"] += auto_reflected
        totals["reviewed"] += reviewed
        totals["low_confidence_candidates"] += low_conf

        out_jobs.append(
            {
                "job_id": jid,
                "status": str(j.status or ""),
                "created_at": str(j.created_at) if j.created_at else None,
                "completed_at": str(j.completed_at) if j.completed_at else None,
                "totals": {
                    "discovered": discovered,
                    "approved": approved,
                    "existing": existing,
                    "ignored": ignored,
                    "auto_reflected": auto_reflected,
                    "reviewed": reviewed,
                    "low_confidence_candidates": low_conf,
                },
                "kpi": {
                    "first_map_seconds": first_map_seconds,
                    "auto_reflection_rate_pct": round((auto_reflected / discovered) * 100.0, 2) if discovered > 0 else 0.0,
                    "false_positive_rate_pct": round((ignored / reviewed) * 100.0, 2) if reviewed > 0 else 0.0,
                    "low_confidence_rate_pct": round((low_conf / discovered) * 100.0, 2) if discovered > 0 else 0.0,
                },
            }
        )

    first_map_avg = None
    first_map_median = None
    first_map_p95 = None
    if first_map_samples:
        s = sorted(first_map_samples)
        n = len(s)
        first_map_avg = round(sum(s) / n, 2)
        first_map_median = s[n // 2] if (n % 2 == 1) else round((s[(n // 2) - 1] + s[n // 2]) / 2, 2)
        p95_idx = min(n - 1, max(0, int((n - 1) * 0.95)))
        first_map_p95 = s[p95_idx]

    discovered_total = int(totals["discovered"])
    reviewed_total = int(totals["reviewed"])
    summary_kpi = {
        "first_map_seconds_avg": first_map_avg,
        "first_map_seconds_median": first_map_median,
        "first_map_seconds_p95": first_map_p95,
        "auto_reflection_rate_pct": round((totals["auto_reflected"] / discovered_total) * 100.0, 2) if discovered_total > 0 else 0.0,
        "false_positive_rate_pct": round((totals["ignored"] / reviewed_total) * 100.0, 2) if reviewed_total > 0 else 0.0,
        "low_confidence_rate_pct": round((totals["low_confidence_candidates"] / discovered_total) * 100.0, 2) if discovered_total > 0 else 0.0,
    }

    return {
        "window_days": int(days),
        "site_id": int(site_id) if site_id is not None else None,
        "jobs_count": len(jobs),
        "kpi": summary_kpi,
        "totals": totals,
        "jobs": out_jobs,
    }


@router.get("/kpi/alerts")
def get_kpi_alerts(
    days: int = 7,
    limit: int = 100,
    site_id: Optional[int] = None,
    min_auto_reflection_pct: float = 70.0,
    max_false_positive_pct: float = 20.0,
    max_low_confidence_rate_pct: float = 30.0,
    max_candidate_backlog: int = 100,
    max_stale_backlog_24h: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    summary = get_kpi_summary(
        days=days,
        limit=limit,
        site_id=site_id,
        db=db,
        current_user=current_user,
    )

    now = _utc_now()
    stale_cutoff = now - timedelta(hours=24)

    q = db.query(TopologyNeighborCandidate)
    if site_id is not None:
        q = q.join(Device, Device.id == TopologyNeighborCandidate.source_device_id).filter(Device.site_id == site_id)

    candidate_rows = q.all()
    backlog_statuses = {"low_confidence", "unmatched"}
    backlog_total = 0
    stale_backlog_24h = 0
    for row in candidate_rows:
        st = str(getattr(row, "status", "") or "").strip().lower()
        if st not in backlog_statuses:
            continue
        backlog_total += 1
        last_seen = getattr(row, "last_seen", None)
        if last_seen is not None:
            try:
                if getattr(last_seen, "tzinfo", None) is None:
                    last_seen = last_seen.replace(tzinfo=timezone.utc)
                if last_seen < stale_cutoff:
                    stale_backlog_24h += 1
            except Exception:
                continue

    kpi = summary.get("kpi", {}) if isinstance(summary, dict) else {}
    jobs_count = int(summary.get("jobs_count", 0)) if isinstance(summary, dict) else 0

    alerts: List[Dict[str, Any]] = []

    def _add_alert(code: str, severity: str, title: str, value: float, threshold: float, guidance: str) -> None:
        alerts.append(
            {
                "code": code,
                "severity": severity,
                "title": title,
                "value": value,
                "threshold": threshold,
                "guidance": guidance,
            }
        )

    if jobs_count == 0:
        _add_alert(
            code="no_recent_discovery_jobs",
            severity="warning",
            title="No recent discovery jobs",
            value=0,
            threshold=1,
            guidance="Run Plug & Scan or seed crawl to refresh KPI baselines.",
        )
    else:
        auto_reflection = float(kpi.get("auto_reflection_rate_pct", 0.0) or 0.0)
        false_positive = float(kpi.get("false_positive_rate_pct", 0.0) or 0.0)
        low_conf_rate = float(kpi.get("low_confidence_rate_pct", 0.0) or 0.0)

        if auto_reflection < float(min_auto_reflection_pct):
            _add_alert(
                code="low_auto_reflection_rate",
                severity="warning",
                title="Auto reflection rate is below target",
                value=round(auto_reflection, 2),
                threshold=float(min_auto_reflection_pct),
                guidance="Review auto-approve policy and discovery credential/profile quality.",
            )
        if false_positive > float(max_false_positive_pct):
            _add_alert(
                code="high_false_positive_rate",
                severity="warning",
                title="False positive rate is above threshold",
                value=round(false_positive, 2),
                threshold=float(max_false_positive_pct),
                guidance="Check scope include/exclude CIDR and vendor confidence threshold.",
            )
        if low_conf_rate > float(max_low_confidence_rate_pct):
            _add_alert(
                code="high_low_confidence_rate",
                severity="warning",
                title="Low-confidence candidate rate is high",
                value=round(low_conf_rate, 2),
                threshold=float(max_low_confidence_rate_pct),
                guidance="Review LLDP/CDP quality and candidate matching heuristics.",
            )

    if backlog_total > int(max_candidate_backlog):
        _add_alert(
            code="candidate_backlog_over_limit",
            severity="critical",
            title="Candidate backlog is above limit",
            value=float(backlog_total),
            threshold=float(max_candidate_backlog),
            guidance="Open Topology candidate queue and process low-confidence/unmatched links.",
        )
    if stale_backlog_24h > int(max_stale_backlog_24h):
        _add_alert(
            code="stale_candidate_backlog",
            severity="warning",
            title="Stale backlog older than 24h is above limit",
            value=float(stale_backlog_24h),
            threshold=float(max_stale_backlog_24h),
            guidance="Prioritize old backlog and tune auto-approve/candidate thresholds.",
        )

    if any(str(a.get("severity")) == "critical" for a in alerts):
        status = "critical"
    elif alerts:
        status = "warning"
    else:
        status = "healthy"

    return {
        "window_days": int(days),
        "site_id": int(site_id) if site_id is not None else None,
        "status": status,
        "alerts_count": len(alerts),
        "alerts": alerts,
        "metrics": {
            "jobs_count": jobs_count,
            "auto_reflection_rate_pct": float(kpi.get("auto_reflection_rate_pct", 0.0) or 0.0),
            "false_positive_rate_pct": float(kpi.get("false_positive_rate_pct", 0.0) or 0.0),
            "low_confidence_rate_pct": float(kpi.get("low_confidence_rate_pct", 0.0) or 0.0),
            "candidate_backlog_total": int(backlog_total),
            "stale_backlog_24h": int(stale_backlog_24h),
        },
    }

def _get_stream_user(db: Session, request: Request, access_token: str | None) -> User:
    token = str(access_token or "").strip()
    if not token:
        auth = str(request.headers.get("authorization", "") or "").strip()
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return deps.get_current_user(request=request, db=db, token=token)


@router.get("/jobs/{id}/stream")
async def stream_job_results(
    id: int,
    request: Request,
    access_token: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    _ = _get_stream_user(db, request, access_token)

    async def event_generator():
        last_id = 0
        while True:
            db = SessionLocal()
            try:
                job = db.query(DiscoveryJob).filter(DiscoveryJob.id == id).first()
                if not job:
                    payload = json.dumps({"error": "Job not found"}, ensure_ascii=False)
                    yield f"event: error\ndata: {payload}\n\n"
                    return

                rows = (
                    db.query(DiscoveredDevice)
                    .filter(DiscoveredDevice.job_id == id, DiscoveredDevice.id > last_id)
                    .order_by(DiscoveredDevice.id.asc())
                    .limit(200)
                    .all()
                )

                for r in rows:
                    data = {
                        "id": r.id,
                        "ip_address": r.ip_address,
                        "hostname": r.hostname,
                        "vendor": r.vendor,
                        "model": r.model,
                        "os_version": r.os_version,
                        "device_type": r.device_type,
                        "status": r.status,
                        "snmp_status": r.snmp_status,
                        "vendor_confidence": getattr(r, "vendor_confidence", 0.0),
                        "chassis_candidate": getattr(r, "chassis_candidate", False),
                        "matched_device_id": getattr(r, "matched_device_id", None),
                        "issues": getattr(r, "issues", None),
                        "evidence": getattr(r, "evidence", None),
                    }
                    last_id = r.id
                    yield f"event: device\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

                total = int(getattr(job, "total_ips", 0) or 0)
                scanned = int(getattr(job, "scanned_ips", 0) or 0)
                pct = int((scanned / total) * 100) if total > 0 else (100 if job.status == "completed" else 0)
                progress_data = {"status": job.status, "scanned_ips": scanned, "total_ips": total, "progress": pct}
                yield f"event: progress\ndata: {json.dumps(progress_data, ensure_ascii=False)}\n\n"

                if job.status in ("completed", "failed") and not rows:
                    yield f"event: done\ndata: {json.dumps({'status': job.status}, ensure_ascii=False)}\n\n"
                    return
            finally:
                db.close()

            await asyncio.sleep(0.8)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@router.post("/approve/{id}")
def approve_device(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    service = DiscoveryService(db)
    discovered = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == id).first()
    if not discovered:
        raise HTTPException(status_code=404, detail="Discovered device not found")
    try:
        device = service.approve_device(id)
    except LicensePolicyViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    if not device:
        raise HTTPException(status_code=404, detail="Discovered device not found")

    try:
        if CapabilityProfileService.allow_auto_action(db, device, "topology"):
            dispatch_topology_refresh(
                device.id,
                discovery_job_id=discovered.job_id,
                max_depth=2,
                idempotency_key=f"discovery-approve:{discovered.job_id}:{device.id}:topology",
            )
    except Exception:
        pass

    try:
        def _get_setting_value(key: str) -> str:
            setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            return setting.value if setting and setting.value and setting.value != "********" else ""

        enabled = (_get_setting_value("auto_sync_enabled") or "true").strip().lower() in ("true", "1", "yes", "y", "on")
        interval = float(_get_setting_value("auto_sync_interval_seconds") or 3)
        jitter = float(_get_setting_value("auto_sync_jitter_seconds") or 0.5)

        if enabled and CapabilityProfileService.allow_auto_action(db, device, "sync"):
            schedule_ssh_sync_batch(
                [device.id],
                interval,
                jitter,
                f"discovery-approve:{discovered.job_id}",
            )
        else:
            from app.tasks.device_sync import dispatch_device_sync
            if CapabilityProfileService.allow_auto_action(db, device, "sync"):
                dispatch_device_sync(device.id, idempotency_key=f"discovery-approve:{discovered.job_id}:{device.id}")
    except Exception:
        from app.tasks.device_sync import dispatch_device_sync
        if CapabilityProfileService.allow_auto_action(db, device, "sync"):
            dispatch_device_sync(device.id, idempotency_key=f"discovery-approve:{discovered.job_id}:{device.id}")

    try:
        from app.tasks.monitoring import burst_monitor_devices
        burst_monitor_devices.delay([device.id], 3, 5)
    except Exception:
        pass

    return {"message": "Device approved", "device_id": device.id}


@router.post("/ignore/{id}")
def ignore_device(id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_operator)):
    discovered = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == id).first()
    if not discovered:
        raise HTTPException(status_code=404, detail="Discovered device not found")
    discovered.status = "ignored"
    db.commit()
    return {"message": "Device ignored"}


@router.post("/jobs/{id}/approve-all")
def approve_all_new_devices(
    id: int,
    policy: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    service = DiscoveryService(db)
    if policy:
        return service.auto_approve_job(id)

    discovered_list = db.query(DiscoveredDevice).filter(
        DiscoveredDevice.job_id == id,
        DiscoveredDevice.status == "new",
    ).all()

    approved_ids = []
    skipped = 0
    for discovered in discovered_list:
        try:
            device = service.approve_device(discovered.id)
            if device:
                approved_ids.append(device.id)
        except Exception:
            skipped += 1

    for device_id in approved_ids:
        try:
            dev = db.query(Device).filter(Device.id == device_id).first()
            if dev and CapabilityProfileService.allow_auto_action(db, dev, "topology"):
                dispatch_topology_refresh(
                    device_id,
                    discovery_job_id=id,
                    max_depth=2,
                    idempotency_key=f"discovery-approve-all:{id}:{device_id}:topology",
                )
        except Exception:
            pass

    try:
        def _get_setting_value(key: str) -> str:
            setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            return setting.value if setting and setting.value and setting.value != "********" else ""

        enabled = (_get_setting_value("auto_sync_enabled") or "true").strip().lower() in ("true", "1", "yes", "y", "on")
        interval = float(_get_setting_value("auto_sync_interval_seconds") or 3)
        jitter = float(_get_setting_value("auto_sync_jitter_seconds") or 0.5)

        allowed_sync_ids = []
        for device_id in approved_ids:
            dev = db.query(Device).filter(Device.id == device_id).first()
            if dev and CapabilityProfileService.allow_auto_action(db, dev, "sync"):
                allowed_sync_ids.append(device_id)

        if enabled and allowed_sync_ids:
            schedule_ssh_sync_batch(
                allowed_sync_ids,
                interval,
                jitter,
                f"discovery-approve-all:{id}",
            )
        elif allowed_sync_ids:
            from app.tasks.device_sync import dispatch_device_sync
            for device_id in allowed_sync_ids:
                dispatch_device_sync(device_id, idempotency_key=f"discovery-approve-all:{id}:{device_id}")
    except Exception:
        allowed_sync_ids = []
        for device_id in approved_ids:
            dev = db.query(Device).filter(Device.id == device_id).first()
            if dev and CapabilityProfileService.allow_auto_action(db, dev, "sync"):
                allowed_sync_ids.append(device_id)
        if allowed_sync_ids:
            from app.tasks.device_sync import dispatch_device_sync
            for device_id in allowed_sync_ids:
                dispatch_device_sync(device_id, idempotency_key=f"discovery-approve-all:{id}:{device_id}")

    try:
        from app.tasks.monitoring import burst_monitor_devices
        if approved_ids:
            burst_monitor_devices.delay(approved_ids, 3, 5)
    except Exception:
        pass

    return {"approved_count": len(approved_ids), "skipped_count": skipped, "device_ids": approved_ids}
