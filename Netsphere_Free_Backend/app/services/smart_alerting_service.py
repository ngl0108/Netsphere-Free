from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models.device import ConfigBackup, Device, Issue, Link, SystemMetric
from app.services.realtime_event_bus import realtime_event_bus


@dataclass(frozen=True)
class DynamicThresholdConfig:
    baseline_days: int = 7
    exclude_recent_minutes: int = 10
    cpu_spike_ratio: float = 0.30
    cpu_min_abs: float = 50.0
    mem_spike_ratio: float = 0.30
    mem_min_abs: float = 60.0
    traffic_drop_ratio: float = 0.50
    traffic_min_abs_bps: float = 200_000.0


def _now_utc(now: Optional[datetime]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _severity_rank(s: str) -> int:
    v = str(s or "").lower()
    if v == "critical":
        return 3
    if v == "warning":
        return 2
    return 1


def _extract_iface_tokens(titles: Iterable[str]) -> List[str]:
    out: List[str] = []
    for t in titles:
        s = str(t or "")
        if s.startswith("Interface Errors (") or s.startswith("Interface Drops ("):
            left = s.find("(")
            right = s.rfind(")")
            if left != -1 and right != -1 and right > left + 1:
                token = s[left + 1 : right].strip()
                if token and token not in out:
                    out.append(token)
    return out


def _build_recommended_actions(
    device_id: int,
    device_name: str,
    titles: List[str],
    interfaces: List[str],
) -> List[str]:
    cmds: List[str] = []
    has_bgp = any(str(t).startswith("BGP Neighbor Down:") for t in titles)
    has_ospf = any(str(t).startswith("OSPF Neighbor Down:") for t in titles)
    has_link = any("Link" in str(t) and "Down" in str(t) for t in titles)
    has_degraded = any(str(t).startswith("Interface Errors (") or str(t).startswith("Interface Drops (") for t in titles)

    cmds.append("확인 우선순위:")
    if has_link or has_degraded:
        if interfaces:
            for ifn in interfaces[:5]:
                cmds.append(f"- (Cisco/Arista) show interfaces {ifn} | i line|error|discard|crc|drop")
                cmds.append(f"- (Cisco/Arista) show interfaces {ifn} counters errors")
                cmds.append(f"- (Junos) show interfaces {ifn} extensive")
        cmds.append("- (Cisco/Arista) show lldp neighbors")
        cmds.append("- (Cisco/Arista) show cdp neighbors detail")
        cmds.append("- (Junos) show lldp neighbors detail")

    if has_bgp:
        cmds.append("- (Cisco/Arista) show ip bgp summary")
        cmds.append("- (Cisco/Arista) show ip bgp neighbors")
        cmds.append("- (Junos) show bgp summary")
        cmds.append("- (Junos) show bgp neighbor")

    if has_ospf:
        cmds.append("- (Cisco/Arista) show ip ospf neighbor")
        cmds.append("- (Junos) show ospf neighbor")

    cmds.append("- 최근 변경 확인(설정/로그):")
    cmds.append(f"- Config history: /api/v1/config/history/{device_id}")
    cmds.append("- Audit logs: /api/v1/audit/?action=all&limit=100")
    cmds.append("- Event logs: /api/v1/logs/recent?days=1&severity=all&limit=500")
    cmds.append(f"- 장비 화면: /devices/{device_id}")
    cmds.append(f"- Root Cause: {device_name}")
    return cmds


def _create_issue_if_not_exists(
    db: Session,
    device_id: int,
    title: str,
    description: str,
    severity: str,
    category: str,
    source: str,
    now: datetime,
) -> bool:
    existing = (
        db.query(Issue)
        .filter(Issue.device_id == device_id, Issue.title == title, Issue.status == "active")
        .first()
    )
    if existing:
        return False
    issue = Issue(
        device_id=device_id,
        title=title,
        description=description,
        severity=severity,
        status="active",
        category=category,
    )
    db.add(issue)
    db.flush()
    try:
        realtime_event_bus.publish(
            "issue_update",
            {
                "device_id": int(device_id),
                "title": str(title),
                "severity": str(severity),
                "status": "active",
                "description": str(description),
                "ts": now.isoformat(),
                "source": str(source),
            },
        )
    except Exception:
        pass
    return True


def _load_baselines(
    db: Session,
    start_ts: datetime,
    end_ts: datetime,
) -> Dict[int, Dict[str, float]]:
    rows = (
        db.query(
            SystemMetric.device_id.label("device_id"),
            func.avg(SystemMetric.cpu_usage).label("avg_cpu"),
            func.avg(SystemMetric.memory_usage).label("avg_mem"),
            func.avg(SystemMetric.traffic_in).label("avg_in"),
            func.avg(SystemMetric.traffic_out).label("avg_out"),
        )
        .filter(and_(SystemMetric.timestamp >= start_ts, SystemMetric.timestamp < end_ts))
        .group_by(SystemMetric.device_id)
        .all()
    )
    out: Dict[int, Dict[str, float]] = {}
    for r in rows:
        out[int(r.device_id)] = {
            "avg_cpu": float(r.avg_cpu or 0.0),
            "avg_mem": float(r.avg_mem or 0.0),
            "avg_in": float(r.avg_in or 0.0),
            "avg_out": float(r.avg_out or 0.0),
        }
    return out


def _load_latest_metrics(
    db: Session,
    since_ts: datetime,
) -> List[Tuple[int, float, float, float, float]]:
    subq = (
        db.query(SystemMetric.device_id.label("device_id"), func.max(SystemMetric.timestamp).label("ts"))
        .filter(SystemMetric.timestamp >= since_ts)
        .group_by(SystemMetric.device_id)
        .subquery()
    )
    rows = (
        db.query(
            SystemMetric.device_id,
            SystemMetric.cpu_usage,
            SystemMetric.memory_usage,
            SystemMetric.traffic_in,
            SystemMetric.traffic_out,
        )
        .join(subq, and_(SystemMetric.device_id == subq.c.device_id, SystemMetric.timestamp == subq.c.ts))
        .all()
    )
    return [(int(r.device_id), float(r.cpu_usage or 0.0), float(r.memory_usage or 0.0), float(r.traffic_in or 0.0), float(r.traffic_out or 0.0)) for r in rows]


def run_dynamic_threshold_alerts(
    db: Session,
    cfg: DynamicThresholdConfig | None = None,
    now: datetime | None = None,
) -> Dict[str, int]:
    cfg = cfg or DynamicThresholdConfig()
    now_dt = _now_utc(now)

    baseline_start = now_dt - timedelta(days=int(cfg.baseline_days))
    baseline_end = now_dt - timedelta(minutes=int(cfg.exclude_recent_minutes))
    if baseline_end <= baseline_start:
        baseline_end = now_dt - timedelta(minutes=1)

    baselines = _load_baselines(db, baseline_start, baseline_end)
    latest_rows = _load_latest_metrics(db, now_dt - timedelta(minutes=5))
    device_names = {int(d.id): str(d.name or d.hostname or d.ip_address or d.id) for d in db.query(Device.id, Device.name, Device.hostname, Device.ip_address).all()}

    created = 0
    evaluated = 0

    for device_id, cpu, mem, tin, tout in latest_rows:
        evaluated += 1
        b = baselines.get(device_id)
        if not b:
            continue

        name = device_names.get(device_id, str(device_id))
        avg_cpu = float(b.get("avg_cpu", 0.0))
        avg_mem = float(b.get("avg_mem", 0.0))
        avg_traffic = float(b.get("avg_in", 0.0)) + float(b.get("avg_out", 0.0))
        cur_traffic = float(tin) + float(tout)

        if avg_cpu > 0 and cpu >= float(cfg.cpu_min_abs) and cpu >= avg_cpu * (1.0 + float(cfg.cpu_spike_ratio)):
            ok = _create_issue_if_not_exists(
                db,
                device_id,
                f"Dynamic CPU Spike: {name}",
                f"cpu={cpu:.1f}% baseline_avg={avg_cpu:.1f}% ratio={cfg.cpu_spike_ratio:.2f}",
                "warning",
                "performance",
                "dynamic_threshold",
                now_dt,
            )
            if ok:
                created += 1

        if avg_mem > 0 and mem >= float(cfg.mem_min_abs) and mem >= avg_mem * (1.0 + float(cfg.mem_spike_ratio)):
            ok = _create_issue_if_not_exists(
                db,
                device_id,
                f"Dynamic Memory Spike: {name}",
                f"mem={mem:.1f}% baseline_avg={avg_mem:.1f}% ratio={cfg.mem_spike_ratio:.2f}",
                "warning",
                "performance",
                "dynamic_threshold",
                now_dt,
            )
            if ok:
                created += 1

        if avg_traffic >= float(cfg.traffic_min_abs_bps) and cur_traffic <= avg_traffic * (1.0 - float(cfg.traffic_drop_ratio)):
            ok = _create_issue_if_not_exists(
                db,
                device_id,
                f"Dynamic Traffic Drop: {name}",
                f"traffic={cur_traffic:.0f}bps baseline_avg={avg_traffic:.0f}bps ratio={cfg.traffic_drop_ratio:.2f}",
                "warning",
                "performance",
                "dynamic_threshold",
                now_dt,
            )
            if ok:
                created += 1

    return {"evaluated": evaluated, "created": created}


def run_alert_correlation(
    db: Session,
    now: datetime | None = None,
    window_minutes: int = 15,
) -> Dict[str, int]:
    now_dt = _now_utc(now)
    window_start = now_dt - timedelta(minutes=int(window_minutes))

    issues = (
        db.query(Issue)
        .filter(Issue.status == "active", Issue.created_at >= window_start)
        .all()
    )

    by_device: Dict[int, List[Issue]] = {}
    for i in issues:
        if i.device_id is None:
            continue
        by_device.setdefault(int(i.device_id), []).append(i)

    device_names = {int(d.id): str(d.name or d.hostname or d.ip_address or d.id) for d in db.query(Device.id, Device.name, Device.hostname, Device.ip_address).all()}

    created = 0
    evaluated = 0

    for device_id, items in by_device.items():
        evaluated += 1
        titles = [str(x.title or "") for x in items]
        has_routing = any(t.startswith("BGP Neighbor Down:") or t.startswith("OSPF Neighbor Down:") for t in titles)
        iface_issues = [t for t in titles if t.startswith("Interface Errors (") or t.startswith("Interface Drops (")]
        has_degraded = len(iface_issues) > 0
        has_traffic_drop = any(t.startswith("Dynamic Traffic Drop:") for t in titles)
        has_device_down = any(t.startswith("Device Unreachable") for t in titles)

        has_link_down = (
            db.query(Link.id)
            .filter(
                Link.last_seen >= window_start,
                Link.status.in_(["down", "inactive"]),
                (Link.source_device_id == device_id) | (Link.target_device_id == device_id),
            )
            .first()
            is not None
        )

        if not (has_routing and has_degraded and (has_link_down or has_traffic_drop or has_device_down)):
            continue

        severity = "info"
        max_rank = 0
        for it in items:
            r = _severity_rank(it.severity)
            if r > max_rank:
                max_rank = r
                severity = it.severity or "info"

        name = device_names.get(device_id, str(device_id))
        title = f"Root Cause Suspected: {name}"
        lines = ["Signals:"]
        for it in sorted(items, key=lambda x: (x.created_at or now_dt), reverse=True)[:20]:
            lines.append(f"- [{it.severity}] {it.title} (id={it.id})")

        backups = (
            db.query(ConfigBackup.id, ConfigBackup.created_at)
            .filter(ConfigBackup.device_id == device_id)
            .order_by(ConfigBackup.created_at.desc())
            .limit(2)
            .all()
        )
        if len(backups) == 2:
            new_id = int(backups[0].id)
            old_id = int(backups[1].id)
            lines.append("")
            lines.append("Recent config diff:")
            lines.append(f"- /api/v1/config/diff/{old_id}/{new_id}")

        if has_link_down:
            lines.append("")
            lines.append("Link signal:")
            lines.append("- Link status down/inactive detected (최근 window 내)")

        interfaces = _extract_iface_tokens(titles)
        lines.append("")
        lines.append("Recommended actions:")
        lines.extend(_build_recommended_actions(device_id, name, titles, interfaces))

        desc = "\n".join(lines)

        ok = _create_issue_if_not_exists(
            db,
            device_id,
            title,
            desc,
            "critical" if _severity_rank(severity) >= 3 else "warning",
            "system",
            "correlation",
            now_dt,
        )
        if ok:
            created += 1

    return {"evaluated": evaluated, "created": created}
