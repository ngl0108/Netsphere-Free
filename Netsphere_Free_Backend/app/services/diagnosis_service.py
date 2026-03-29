from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models.device import Device, Issue, SystemMetric
from app.services.path_trace_service import PathTraceService


@dataclass(frozen=True)
class OneClickDiagnosisOptions:
    include_show_commands: bool = True
    show_timeout_sec: int = 12
    max_show_devices: int = 2
    recent_issue_minutes: int = 60


def _now_utc(now: Optional[datetime]) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _ping_once(ip_address: str, timeout_ms: int = 1000) -> bool:
    if not ip_address:
        return False
    is_windows = platform.system().lower() == "windows"
    count_flag = "-n" if is_windows else "-c"
    timeout_flag = "-w" if is_windows else "-W"
    timeout_val = str(int(timeout_ms)) if is_windows else str(max(1, int(timeout_ms / 1000)))
    cmd = ["ping", count_flag, "1", timeout_flag, timeout_val, str(ip_address)]
    try:
        return subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0
    except Exception:
        return False


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_protocol(value: Any) -> str:
    return str(value or "").strip().upper()


def _normalize_layer(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_severity(value: Any, default: str = "info") -> str:
    sev = str(value or default).strip().lower()
    if sev in {"critical", "warning", "info"}:
        return sev
    if sev in {"healthy", "ok", "success"}:
        return "info"
    return default


def _severity_rank(value: Any) -> int:
    sev = _normalize_severity(value)
    return {"critical": 3, "warning": 2, "info": 1}.get(sev, 0)


def _clamp_confidence(value: Any, default: float = 0.65) -> float:
    try:
        num = float(value)
    except Exception:
        return float(default)
    return max(0.0, min(1.0, num))


def _unique_strings(values: List[Any], limit: int = 6) -> List[str]:
    out: List[str] = []
    seen = set()
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= int(limit):
            break
    return out


def _safe_iso(ts: Any) -> Optional[str]:
    if ts is None:
        return None
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        else:
            ts = ts.astimezone(timezone.utc)
        return ts.isoformat()
    return str(ts)


def _root_cause_label(value: Any) -> str:
    text = str(value or "").strip().replace("_", " ")
    return text[:1].upper() + text[1:] if text else "Unknown"


def _load_latest_metrics(
    db: Session,
    device_ids: List[int],
    since_ts: datetime,
) -> Dict[int, Dict[str, Any]]:
    ids = [int(x) for x in device_ids if str(x).isdigit()]
    if not ids:
        return {}

    subq = (
        db.query(SystemMetric.device_id.label("device_id"), func.max(SystemMetric.timestamp).label("ts"))
        .filter(SystemMetric.device_id.in_(ids))
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
            SystemMetric.timestamp,
        )
        .join(subq, and_(SystemMetric.device_id == subq.c.device_id, SystemMetric.timestamp == subq.c.ts))
        .all()
    )

    out: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        out[int(row.device_id)] = {
            "cpu_usage": float(row.cpu_usage or 0.0),
            "memory_usage": float(row.memory_usage or 0.0),
            "traffic_in": float(row.traffic_in or 0.0),
            "traffic_out": float(row.traffic_out or 0.0),
            "timestamp": _safe_iso(row.timestamp),
        }
    return out


def _score_device_health(
    ping_ok: bool,
    critical_issues: int,
    warning_issues: int,
    info_issues: int,
    cpu_usage: float,
    memory_usage: float,
) -> Tuple[int, str, List[str], str]:
    score = 100
    notes: List[str] = []
    primary_signal = "healthy"

    if not ping_ok:
        score -= 55
        notes.append("Management reachability failed during diagnosis.")
        primary_signal = "reachability"
    if critical_issues > 0:
        score -= min(45, critical_issues * 18)
        notes.append(f"{critical_issues} critical issue(s) active in the recent window.")
        if primary_signal == "healthy":
            primary_signal = "active_critical_issue"
    if warning_issues > 0:
        score -= min(24, warning_issues * 8)
        notes.append(f"{warning_issues} warning issue(s) active in the recent window.")
        if primary_signal == "healthy":
            primary_signal = "active_warning_issue"
    if info_issues > 0:
        score -= min(8, info_issues * 2)
    if cpu_usage >= 90:
        score -= 14
        notes.append(f"CPU usage is high at {cpu_usage:.1f}%.")
        if primary_signal == "healthy":
            primary_signal = "cpu_high"
    elif cpu_usage >= 75:
        score -= 7
        notes.append(f"CPU usage is elevated at {cpu_usage:.1f}%.")
        if primary_signal == "healthy":
            primary_signal = "cpu_elevated"
    if memory_usage >= 90:
        score -= 14
        notes.append(f"Memory usage is high at {memory_usage:.1f}%.")
        if primary_signal == "healthy":
            primary_signal = "memory_high"
    elif memory_usage >= 75:
        score -= 7
        notes.append(f"Memory usage is elevated at {memory_usage:.1f}%.")
        if primary_signal == "healthy":
            primary_signal = "memory_elevated"

    score = max(0, min(100, int(round(score))))
    if not ping_ok or critical_issues > 0 or score < 45:
        risk_level = "critical"
    elif warning_issues > 0 or score < 75:
        risk_level = "warning"
    else:
        risk_level = "healthy"
    return score, risk_level, notes[:4], primary_signal


def _select_abnormal_hops(path_trace: Dict[str, Any], device_health: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    segments = path_trace.get("segments") or []
    out: List[Dict[str, Any]] = []

    for seg in segments:
        try:
            from_id = int(seg.get("from_id"))
        except Exception:
            continue
        link = seg.get("link") if isinstance(seg, dict) else None
        link_status = None
        if isinstance(link, dict):
            link_status = str(link.get("status") or "").lower()
        if link_status in {"down", "inactive", "degraded"}:
            out.append({"type": "link", "device_id": from_id, "segment": seg})
            continue
        health = device_health.get(from_id) or {}
        if health.get("ping_ok") is False:
            out.append({"type": "ping", "device_id": from_id, "segment": seg})
            continue
        if health.get("critical_issues", 0) > 0:
            out.append({"type": "issue", "device_id": from_id, "segment": seg})
            continue

    if not out:
        node_ids = path_trace.get("path_node_ids") or []
        for did in node_ids:
            try:
                did_i = int(did)
            except Exception:
                continue
            health = device_health.get(did_i) or {}
            if health.get("warning_issues", 0) > 0:
                out.append({"type": "issue", "device_id": did_i, "segment": None})
                break

    return out


def _issue_focus(issue: Optional[Dict[str, Any]], health: Dict[str, Any]) -> Tuple[str, str, List[str], float]:
    issue = issue or {}
    title = str(issue.get("title") or "").strip()
    description = str(issue.get("description") or "").strip()
    category = str(issue.get("category") or "").strip().lower()
    severity = _normalize_severity(issue.get("severity"), default="warning")
    text = " ".join([title, description, category]).lower()
    cpu_usage = float(health.get("cpu_usage") or 0.0)
    memory_usage = float(health.get("memory_usage") or 0.0)

    if "bgp" in text:
        return (
            "bgp_alarm",
            "BGP control-plane alarm is active",
            [
                "Verify BGP neighbor state and last reset cause.",
                "Check route lookup and next-hop reachability.",
                "Review recent routing-policy or peer configuration changes.",
            ],
            0.82 if severity == "critical" else 0.74,
        )
    if "ospf" in text:
        return (
            "ospf_alarm",
            "OSPF adjacency alarm is active",
            [
                "Check OSPF neighbor state and interface MTU/authentication settings.",
                "Verify interface counters and timer consistency.",
                "Review recent routing changes on the affected area.",
            ],
            0.8 if severity == "critical" else 0.72,
        )
    if category == "performance" or cpu_usage >= 85 or memory_usage >= 90:
        return (
            "performance_hotspot",
            "Device performance pressure is the likely issue driver",
            [
                "Inspect CPU and memory pressure around the event window.",
                "Check interface load and queue drops on the transit path.",
                "Review control-plane churn such as route flaps or spanning-tree events.",
            ],
            0.78 if max(cpu_usage, memory_usage) >= 90 else 0.68,
        )
    if category == "config":
        return (
            "config_drift",
            "Configuration drift or policy mismatch is likely involved",
            [
                "Review the most recent approved and running configuration delta.",
                "Validate route, VLAN, or interface policy against the golden baseline.",
                "Rollback or re-apply the intended change if the drift is confirmed.",
            ],
            0.72,
        )
    if category == "security":
        return (
            "security_event",
            "A security policy or threat signal is active on the device",
            [
                "Validate the security policy hit or block condition.",
                "Check whether the path impact is policy-driven rather than transport-driven.",
                "Review recent auth, NAC, or firewall enforcement changes.",
            ],
            0.7,
        )

    return (
        "active_alarm",
        "Recent active issues suggest the device is part of the fault domain",
        [
            "Review the active issues and correlate them with the traced path.",
            "Check interface, neighbor, and route state on the device.",
            "Review recent operational changes around the event window.",
        ],
        0.64 if severity == "warning" else 0.7,
    )


def _classify_abnormal_hop(
    item: Dict[str, Any],
    dev_by_id: Dict[int, Device],
    device_health: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    did = _safe_int(item.get("device_id"))
    dev = dev_by_id.get(did)
    health = device_health.get(did) or {}
    seg = item.get("segment") if isinstance(item, dict) else None
    seg = seg if isinstance(seg, dict) else {}
    link = seg.get("link") if isinstance(seg.get("link"), dict) else {}
    protocol = _normalize_protocol(seg.get("protocol") or link.get("protocol"))
    layer = _normalize_layer(seg.get("layer") or link.get("layer"))
    link_status = _normalize_status(link.get("status") or seg.get("status"))
    top_issue = (health.get("recent_issues") or [None])[0] if isinstance(health.get("recent_issues"), list) else None
    peer = dev_by_id.get(_safe_int(seg.get("to_id")))

    severity = "warning"
    confidence = 0.66
    root_cause = "unknown"
    title = "Path anomaly detected"
    summary = "The traced path contains a signal that deserves operator attention."
    next_actions: List[str] = [
        "Inspect the affected device and adjacent hop in the traced path.",
        "Correlate path-trace data with live interface and routing state.",
    ]

    item_type = str(item.get("type") or "").strip().lower()
    if item_type == "link":
        if protocol == "BGP":
            if link_status == "down":
                root_cause = "bgp_session_down"
                severity = "critical"
                confidence = 0.96
                title = "BGP adjacency is down"
                summary = "The traced path includes a BGP segment marked down."
            else:
                root_cause = "bgp_session_degraded"
                severity = "warning"
                confidence = 0.87
                title = "BGP adjacency is degraded"
                summary = "The traced path relies on a degraded BGP segment."
            next_actions = [
                "Verify BGP neighbor state and last reset cause.",
                "Check route lookup and next-hop reachability.",
                "Inspect interface counters and transport errors on both ends.",
            ]
        elif protocol == "OSPF":
            if link_status == "down":
                root_cause = "ospf_adjacency_down"
                severity = "critical"
                confidence = 0.94
                title = "OSPF adjacency is down"
                summary = "The traced path includes an OSPF adjacency marked down."
            else:
                root_cause = "ospf_adjacency_degraded"
                severity = "warning"
                confidence = 0.84
                title = "OSPF adjacency is degraded"
                summary = "The traced path relies on a degraded OSPF adjacency."
            next_actions = [
                "Check OSPF neighbor state and interface MTU/authentication settings.",
                "Verify hello and dead timer consistency.",
                "Inspect interface counters on the affected link.",
            ]
        else:
            if link_status == "down":
                root_cause = "link_down"
                severity = "critical"
                confidence = 0.93
                title = "Transit link is down"
                summary = "The traced path includes a transit link that is currently down."
            else:
                root_cause = "link_degraded"
                severity = "warning"
                confidence = 0.82
                title = "Transit link is degraded"
                summary = "The traced path includes a degraded transit link."
            next_actions = [
                "Check physical link state, optics, and interface error counters.",
                "Verify LLDP or CDP neighbor state on both ends.",
                "Review recent cabling or interface configuration changes.",
            ]
    elif item_type == "ping":
        root_cause = "device_unreachable"
        severity = "critical"
        confidence = 0.95
        title = "Device is unreachable"
        summary = "The device did not respond to management reachability checks during diagnosis."
        next_actions = [
            "Verify management reachability and control-plane health.",
            "Check whether upstream routing or ACL changes are blocking access.",
            "Inspect the adjacent transit hop for errors or state change.",
        ]
    elif item_type == "issue":
        root_cause, title, next_actions, confidence = _issue_focus(top_issue, health)
        severity = _normalize_severity((top_issue or {}).get("severity"), default="warning")
        summary = str((top_issue or {}).get("title") or title)

    evidence: List[Dict[str, Any]] = []
    if link_status:
        evidence.append(
            {
                "kind": "link_status",
                "label": "Link status",
                "value": link_status,
                "status": "critical" if link_status == "down" else "warning",
            }
        )
    if protocol:
        evidence.append({"kind": "protocol", "label": "Protocol", "value": protocol, "status": "info"})
    if layer:
        evidence.append({"kind": "layer", "label": "Layer", "value": layer, "status": "info"})
    ping_ok = health.get("ping_ok")
    if ping_ok is not None:
        evidence.append(
            {
                "kind": "reachability",
                "label": "Ping",
                "value": "reachable" if ping_ok else "failed",
                "status": "success" if ping_ok else "critical",
            }
        )
    critical_issues = _safe_int(health.get("critical_issues"))
    warning_issues = _safe_int(health.get("warning_issues"))
    if critical_issues > 0 or warning_issues > 0:
        evidence.append(
            {
                "kind": "issues",
                "label": "Recent issues",
                "value": f"critical={critical_issues}, warning={warning_issues}",
                "status": "critical" if critical_issues > 0 else "warning",
            }
        )
    if top_issue:
        evidence.append(
            {
                "kind": "issue_title",
                "label": "Top issue",
                "value": str(top_issue.get("title") or ""),
                "status": _normalize_severity(top_issue.get("severity"), default="warning"),
            }
        )
    cpu_usage = float(health.get("cpu_usage") or 0.0)
    if cpu_usage >= 75:
        evidence.append(
            {
                "kind": "cpu",
                "label": "CPU",
                "value": f"{cpu_usage:.1f}%",
                "status": "critical" if cpu_usage >= 90 else "warning",
            }
        )
    memory_usage = float(health.get("memory_usage") or 0.0)
    if memory_usage >= 75:
        evidence.append(
            {
                "kind": "memory",
                "label": "Memory",
                "value": f"{memory_usage:.1f}%",
                "status": "critical" if memory_usage >= 90 else "warning",
            }
        )

    segment_payload: Optional[Dict[str, Any]] = None
    if seg:
        segment_payload = {
            "hop": seg.get("hop"),
            "from_id": seg.get("from_id"),
            "to_id": seg.get("to_id"),
            "from_port": seg.get("from_port"),
            "to_port": seg.get("to_port"),
            "protocol": protocol or None,
            "layer": layer or None,
            "status": link_status or None,
            "link_id": link.get("id"),
            "peer_name": getattr(peer, "name", None),
        }

    return {
        "type": item_type or "unknown",
        "device_id": did,
        "device_name": getattr(dev, "name", None),
        "device_ip": getattr(dev, "ip_address", None),
        "root_cause": root_cause,
        "root_cause_label": _root_cause_label(root_cause),
        "severity": severity,
        "confidence": _clamp_confidence(confidence),
        "title": title,
        "summary": summary,
        "next_actions": _unique_strings(next_actions, limit=4),
        "segment": segment_payload,
        "evidence": evidence,
        "issue_refs": (health.get("recent_issues") or [])[:3],
    }


def _build_diagnosis_overview(path_trace: Dict[str, Any], abnormal: List[Dict[str, Any]]) -> Dict[str, Any]:
    path_summary = path_trace.get("summary") if isinstance(path_trace.get("summary"), dict) else {}
    path_health = _normalize_status(path_summary.get("health") or path_trace.get("status") or "unknown")
    warnings = [str(w) for w in (path_summary.get("warnings") or []) if str(w).strip()]

    if abnormal:
        primary = abnormal[0]
        actions = _unique_strings(
            list(primary.get("next_actions") or [])
            + [item.get("title") for item in abnormal[1:3]],
            limit=6,
        )
        return {
            "verdict": str(primary.get("root_cause") or "fault_detected"),
            "severity": _normalize_severity(primary.get("severity"), default="warning"),
            "confidence": _clamp_confidence(primary.get("confidence"), default=0.72),
            "headline": str(primary.get("title") or "Path anomaly detected"),
            "summary": str(primary.get("summary") or ""),
            "path_health": path_health or "unknown",
            "next_actions": actions,
            "affected_protocols": _unique_strings(
                [
                    (((item.get("segment") or {}) if isinstance(item.get("segment"), dict) else {}).get("protocol"))
                    for item in abnormal
                ]
            ),
            "affected_layers": _unique_strings(
                [
                    (((item.get("segment") or {}) if isinstance(item.get("segment"), dict) else {}).get("layer"))
                    for item in abnormal
                ]
            ),
            "warnings": warnings,
            "abnormal_count": len(abnormal),
            "focus_devices": _unique_strings([item.get("device_name") or item.get("device_ip") for item in abnormal], limit=4),
        }

    complete = bool(path_summary.get("complete"))
    if path_health in {"success", "healthy"} or complete:
        return {
            "verdict": "healthy",
            "severity": "info",
            "confidence": 0.78,
            "headline": "No abnormal hop detected in the traced path",
            "summary": "The trace completed without a clear fault signal from links, reachability, or active issues.",
            "path_health": path_health or "unknown",
            "next_actions": ["Review raw path details if the issue is intermittent or policy-related."],
            "affected_protocols": _unique_strings(path_summary.get("protocols") or []),
            "affected_layers": _unique_strings(path_summary.get("layers") or []),
            "warnings": warnings,
            "abnormal_count": 0,
            "focus_devices": [],
        }

    return {
        "verdict": "path_inconclusive",
        "severity": "warning",
        "confidence": 0.56,
        "headline": "Path trace completed without a definitive root cause",
        "summary": str(path_trace.get("message") or "The trace is partial or lacks a decisive fault signal."),
        "path_health": path_health or "unknown",
        "next_actions": [
            "Review raw path warnings and recent device issues.",
            "Collect show commands on the devices closest to the user impact.",
        ],
        "affected_protocols": _unique_strings(path_summary.get("protocols") or []),
        "affected_layers": _unique_strings(path_summary.get("layers") or []),
        "warnings": warnings,
        "abnormal_count": 0,
        "focus_devices": [],
    }


def _append_show_plan_item(
    plan: List[Dict[str, str]],
    seen: Set[str],
    command: str,
    area: str,
    purpose: str,
    priority: str = "secondary",
) -> None:
    cmd = str(command or "").strip()
    if not cmd:
        return
    key = cmd.lower()
    if key in seen:
        return
    seen.add(key)
    plan.append(
        {
            "command": cmd,
            "area": str(area or "general").strip().lower() or "general",
            "purpose": str(purpose or "").strip() or "Check device state",
            "priority": str(priority or "secondary").strip().lower() or "secondary",
        }
    )


def _build_show_plan(device: Device, abnormal: Optional[Dict[str, Any]], dst_ip: str) -> List[Dict[str, str]]:
    dev_type = str(getattr(device, "device_type", "") or "").lower()
    is_junos = "junos" in dev_type
    abnormal = abnormal if isinstance(abnormal, dict) else {}
    seg = abnormal.get("segment") if isinstance(abnormal.get("segment"), dict) else {}
    port = str(seg.get("from_port") or "").strip()
    protocol = _normalize_protocol(seg.get("protocol"))
    layer = _normalize_layer(seg.get("layer"))
    root_cause = str(abnormal.get("root_cause") or "").strip().lower()
    reasons = [str(abnormal.get("type") or "").strip().lower(), root_cause, protocol.lower(), layer]

    plan: List[Dict[str, str]] = []
    seen: Set[str] = set()
    if port:
        if is_junos:
            _append_show_plan_item(plan, seen, f"show interfaces {port} extensive", "interface", "Inspect interface state and counters.", "primary")
        else:
            _append_show_plan_item(plan, seen, f"show interfaces {port}", "interface", "Inspect interface state.", "primary")
            _append_show_plan_item(plan, seen, f"show interfaces {port} counters errors", "interface", "Inspect interface error counters.", "primary")

    if any(r for r in reasons if r in {"link", "ping", "issue", "link_down", "link_degraded"}):
        if is_junos:
            _append_show_plan_item(plan, seen, "show lldp neighbors detail", "neighbor", "Validate physical neighbor adjacency.", "secondary")
        else:
            _append_show_plan_item(plan, seen, "show lldp neighbors", "neighbor", "Validate LLDP neighbor state.", "secondary")
            _append_show_plan_item(plan, seen, "show cdp neighbors detail", "neighbor", "Validate Cisco neighbor state.", "secondary")

    route_cmd = f"show route {dst_ip}" if is_junos else f"show ip route {dst_ip}"
    _append_show_plan_item(plan, seen, route_cmd, "route", "Validate forwarding decision toward the destination.", "primary")

    if protocol == "BGP" or "bgp" in root_cause:
        _append_show_plan_item(
            plan,
            seen,
            "show bgp summary" if is_junos else "show ip bgp summary",
            "control_plane",
            "Inspect BGP session health on the device.",
            "primary",
        )
    if protocol == "OSPF" or "ospf" in root_cause:
        _append_show_plan_item(
            plan,
            seen,
            "show ospf neighbor" if is_junos else "show ip ospf neighbor",
            "control_plane",
            "Inspect OSPF adjacency health on the device.",
            "primary",
        )
    if "performance" in root_cause and not is_junos:
        _append_show_plan_item(plan, seen, "show processes cpu sorted", "performance", "Check CPU hotspots related to the event.", "secondary")
    if "config" in root_cause and not is_junos:
        _append_show_plan_item(plan, seen, "show running-config", "config", "Review the live configuration for drift.", "secondary")

    if not any(item.get("area") == "control_plane" for item in plan):
        _append_show_plan_item(
            plan,
            seen,
            "show bgp summary" if is_junos else "show ip bgp summary",
            "control_plane",
            "Check BGP summary if routing is part of the fault domain.",
            "secondary",
        )
        _append_show_plan_item(
            plan,
            seen,
            "show ospf neighbor" if is_junos else "show ip ospf neighbor",
            "control_plane",
            "Check OSPF summary if routing is part of the fault domain.",
            "secondary",
        )

    return plan[:8]


def _run_show_commands(device: Device, commands: List[str], timeout_sec: int) -> Dict[str, str]:
    if not commands:
        return {}
    if not getattr(device, "ssh_password", None):
        return {"_error": "ssh_password not set"}

    from app.services.ssh_service import DeviceConnection, DeviceInfo

    dev_info = DeviceInfo(
        host=device.ip_address,
        username=device.ssh_username or "admin",
        password=device.ssh_password,
        secret=device.enable_password,
        port=int(device.ssh_port or 22),
        device_type=device.device_type or "cisco_ios",
    )
    conn = DeviceConnection(dev_info)
    if not conn.connect():
        return {"_error": "ssh connect failed"}

    out: Dict[str, str] = {}
    try:
        for cmd in commands:
            t0 = time.monotonic()
            try:
                res = conn.send_command(cmd, read_timeout=int(timeout_sec))
            except Exception as exc:
                res = f"ERROR: {type(exc).__name__}: {exc}"
            dt = time.monotonic() - t0
            out[cmd] = f"{res}\n\n(elapsed={dt:.2f}s)"
    finally:
        try:
            conn.disconnect()
        except Exception:
            pass
    return out


class OneClickDiagnosisService:
    def __init__(self, db: Session):
        self.db = db

    def run(
        self,
        src_ip: str,
        dst_ip: str,
        options: Optional[OneClickDiagnosisOptions] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        options = options or OneClickDiagnosisOptions()
        now_dt = _now_utc(now)

        path_trace = PathTraceService(self.db).trace_path(src_ip, dst_ip)
        if isinstance(path_trace, dict) and path_trace.get("error"):
            return {"ok": False, "error": path_trace.get("error"), "path_trace": path_trace}

        node_ids = [int(x) for x in (path_trace.get("path_node_ids") or []) if str(x).isdigit()]
        devices = self.db.query(Device).filter(Device.id.in_(node_ids)).all() if node_ids else []
        dev_by_id = {int(d.id): d for d in devices}

        issue_since = now_dt - timedelta(minutes=int(options.recent_issue_minutes))
        latest_metrics = _load_latest_metrics(self.db, node_ids, now_dt - timedelta(hours=24))
        issues = (
            self.db.query(Issue)
            .filter(Issue.status == "active", Issue.created_at >= issue_since)
            .filter(Issue.device_id.in_(node_ids))
            .order_by(Issue.created_at.desc())
            .all()
        ) if node_ids else []

        issue_counts: Dict[int, Dict[str, int]] = {}
        recent_issue_map: Dict[int, List[Dict[str, Any]]] = {}
        for issue in issues:
            if issue.device_id is None:
                continue
            did = int(issue.device_id)
            counts = issue_counts.setdefault(did, {"critical": 0, "warning": 0, "info": 0})
            sev = _normalize_severity(issue.severity, default="info")
            counts[sev] += 1
            bucket = recent_issue_map.setdefault(did, [])
            if len(bucket) < 5:
                bucket.append(
                    {
                        "id": int(issue.id),
                        "title": str(issue.title or ""),
                        "description": str(issue.description or ""),
                        "severity": sev,
                        "category": str(issue.category or "system"),
                        "created_at": _safe_iso(issue.created_at),
                    }
                )

        device_health: Dict[int, Dict[str, Any]] = {}
        for did in node_ids:
            dev = dev_by_id.get(did)
            ip_address = dev.ip_address if dev else None
            ping_ok = _ping_once(ip_address) if ip_address else False
            counts = issue_counts.get(did) or {"critical": 0, "warning": 0, "info": 0}
            metric = latest_metrics.get(did) or {}
            cpu_usage = float(metric.get("cpu_usage") or 0.0)
            memory_usage = float(metric.get("memory_usage") or 0.0)
            health_score, risk_level, notes, primary_signal = _score_device_health(
                bool(ping_ok),
                int(counts.get("critical", 0)),
                int(counts.get("warning", 0)),
                int(counts.get("info", 0)),
                cpu_usage,
                memory_usage,
            )
            device_health[did] = {
                "device_id": did,
                "name": getattr(dev, "name", None),
                "ip_address": ip_address,
                "ping_ok": bool(ping_ok),
                "critical_issues": int(counts.get("critical", 0)),
                "warning_issues": int(counts.get("warning", 0)),
                "info_issues": int(counts.get("info", 0)),
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "traffic_in": float(metric.get("traffic_in") or 0.0),
                "traffic_out": float(metric.get("traffic_out") or 0.0),
                "metric_timestamp": metric.get("timestamp"),
                "health_score": health_score,
                "risk_level": risk_level,
                "notes": notes,
                "primary_signal": primary_signal,
                "recent_issues": recent_issue_map.get(did) or [],
            }

        abnormal = [_classify_abnormal_hop(item, dev_by_id, device_health) for item in _select_abnormal_hops(path_trace, device_health)]
        abnormal.sort(
            key=lambda item: (
                -_severity_rank(item.get("severity")),
                -float(item.get("confidence") or 0.0),
                _safe_int(((item.get("segment") or {}) if isinstance(item.get("segment"), dict) else {}).get("hop"), default=999),
            )
        )

        show_results: List[Dict[str, Any]] = []
        if options.include_show_commands and abnormal:
            picked: List[int] = []
            for item in abnormal:
                did = _safe_int(item.get("device_id"), default=-1)
                if did < 0 or did in picked:
                    continue
                picked.append(did)
                if len(picked) >= int(options.max_show_devices):
                    break

            for did in picked:
                dev = dev_by_id.get(int(did))
                if not dev:
                    continue
                focus = next((item for item in abnormal if _safe_int(item.get("device_id"), default=-1) == int(did)), None)
                plan = _build_show_plan(dev, focus, dst_ip)
                commands = [item.get("command") for item in plan if str(item.get("command") or "").strip()]
                outputs = _run_show_commands(dev, commands, int(options.show_timeout_sec))
                results = [{**item, "output": str(outputs.get(item.get("command")) or "")} for item in plan]
                if outputs.get("_error"):
                    results.insert(
                        0,
                        {
                            "command": "",
                            "area": "execution",
                            "purpose": "Show command collection failed.",
                            "priority": "primary",
                            "output": str(outputs.get("_error") or ""),
                        },
                    )
                show_results.append(
                    {
                        "device_id": int(did),
                        "device_name": dev.name,
                        "device_ip": dev.ip_address,
                        "reasons": [str(item.get("root_cause")) for item in abnormal if _safe_int(item.get("device_id"), default=-1) == int(did)],
                        "plan": plan,
                        "commands": commands,
                        "results": results,
                        "outputs": outputs,
                    }
                )

        diagnosis = _build_diagnosis_overview(path_trace, abnormal)
        summary = {
            "status": str(path_trace.get("status") or "unknown"),
            "mode": str(path_trace.get("mode") or "unknown"),
            "path_health": str(diagnosis.get("path_health") or "unknown"),
            "abnormal_count": len(abnormal),
            "show_collected": len(show_results),
            "severity": str(diagnosis.get("severity") or "info"),
            "confidence": float(diagnosis.get("confidence") or 0.0),
            "root_cause": str(diagnosis.get("verdict") or "unknown"),
        }

        return {
            "ok": True,
            "summary": summary,
            "diagnosis": diagnosis,
            "path_trace": path_trace,
            "device_health": [device_health[did] for did in node_ids if did in device_health],
            "abnormal": abnormal,
            "show": show_results,
            "ts": now_dt.isoformat(),
        }
