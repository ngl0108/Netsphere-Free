import random
import re
import hashlib
from datetime import datetime, timedelta
from typing import List, Any, Optional, Dict, Tuple
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import func, and_
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.api import deps
from app.models.device import Device, Link, Site, Policy, FirmwareImage, Interface, ConfigBackup, SystemMetric, \
    EventLog, Issue, ConfigTemplate
from app.models.user import User # [FIX] Dedicated user model
from app.schemas.device import DeviceCreate, DeviceResponse, DeviceDetailResponse, DeviceUpdate
from app.models.device_inventory import DeviceInventoryItem
from app.models.cloud import CloudAccount, CloudResource
from app.services.template_service import TemplateRenderer
from app.db.session import SessionLocal
from app.services.audit_service import AuditService
from app.services.cloud_account_readiness_service import CloudAccountReadinessService
from app.services.cloud_credentials_service import decrypt_credentials_for_runtime
from app.services.cloud_intent_execution_service import CloudIntentExecutionService
from app.models.settings import SystemSetting
from app.services.device_sync_service import DeviceSyncService
from app.services.capability_profile_service import CapabilityProfileService
from app.services.device_support_policy_service import DeviceSupportPolicyService
from app.services.license_policy_service import LicensePolicyService, LicensePolicyViolation
from app.services.monitoring_profile_service import MonitoringProfileService
from app.services.preview_managed_node_service import PreviewManagedNodeService
from app.services.service_group_service import ServiceGroupService
from app.services.source_of_truth_service import SourceOfTruthService

router = APIRouter()


def _serialize_device_payload(device: Device, schema_cls, db: Session | None = None):
    payload = schema_cls.model_validate(device).model_dump()
    if payload.get("snmp_community"):
        payload["snmp_community"] = "********"
    payload["management_state"] = str(getattr(device, "management_state", "managed") or "managed")
    payload["management_reason"] = getattr(device, "management_reason", None)
    payload["managed_since"] = getattr(device, "managed_since", None)
    payload["management_priority_score"] = float(getattr(device, "management_priority_score", 0.0) or 0.0)
    payload["is_managed"] = PreviewManagedNodeService.is_managed_device(device)
    summary = MonitoringProfileService.build_device_summary(db, device) if db else None
    payload["monitoring_profile"] = summary.model_dump() if summary else None
    return payload


def _clean_ip_value(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "/" in raw:
        raw = raw.split("/", 1)[0].strip()
    return raw


def _safe_int_value(value: Any) -> Optional[int]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return int(raw)
    except Exception:
        return None


def _normalize_l3_neighbor_rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _normalize_string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        vals = [str(x or "").strip() for x in value]
        return [x for x in vals if x]
    raw = str(value or "").strip()
    return [raw] if raw else []


def _normalize_overlay_rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in value:
        if isinstance(row, dict):
            out.append(row)
    return out


def _normalize_overlay_vni_rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: List[Dict[str, Any]] = []
    for row in value:
        if isinstance(row, dict):
            out.append(row)
            continue
        vni = _safe_int_value(row)
        if vni is not None:
            out.append({"vni": vni})
    return out


def _overlay_peer_ip(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    for key in ("peer_ip", "neighbor_ip", "remote_vtep_ip", "vtep_ip", "peer", "remote_ip"):
        ip = _clean_ip_value(row.get(key))
        if ip:
            return ip
    return ""


def _overlay_vni_value(row: Any) -> Optional[int]:
    if not isinstance(row, dict):
        return None
    for key in ("vni", "vni_id", "vnid", "id"):
        vni = _safe_int_value(row.get(key))
        if vni is not None:
            return vni
    return None


def _overlay_vni_numbers(row: Any) -> List[int]:
    if not isinstance(row, dict):
        return []
    vals: List[int] = []
    for key in ("vnis", "vni_list", "advertised_vnis", "vni_ids"):
        raw = row.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            vni = _safe_int_value(item if not isinstance(item, dict) else _overlay_vni_value(item))
            if vni is not None and vni not in vals:
                vals.append(vni)
    single = _overlay_vni_value(row)
    if single is not None and single not in vals:
        vals.append(single)
    return vals


def _overlay_vni_type(row: Any) -> str:
    raw = str((row or {}).get("type") or (row or {}).get("kind") or (row or {}).get("mode") or "").strip().lower()
    if any(token in raw for token in ("l3", "irb", "vrf", "svi")):
        return "l3"
    if raw:
        return "l2"
    if str((row or {}).get("vrf") or "").strip():
        return "l3"
    return "l2"


def _overlay_transport_value(overlay_meta: Optional[Dict[str, Any]], *rows: Any) -> str:
    candidates: List[str] = []
    if isinstance(overlay_meta, dict):
        for key in ("transport", "control_plane", "replication_mode"):
            val = str(overlay_meta.get(key) or "").strip()
            if val:
                candidates.append(val)
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("transport", "control_plane", "replication_mode", "address_family"):
            val = str(row.get(key) or "").strip()
            if val:
                candidates.append(val)
    for val in candidates:
        low = val.lower()
        if "evpn" in low:
            return "evpn"
        if "ingress" in low:
            return "ingress_replication"
        if "multicast" in low:
            return "multicast"
    return "vxlan"


def _normalize_overlay_state(*values: Any) -> str:
    seen = [str(v or "").strip().lower() for v in values if str(v or "").strip()]
    if not seen:
        return "unknown"
    healthy_tokens = ("up", "established", "full", "ready", "active", "learn")
    degraded_tokens = ("init", "connect", "partial", "degraded", "probe")
    down_tokens = ("down", "idle", "error", "fail", "inactive", "shutdown", "hold")

    if any(any(token in value for token in healthy_tokens) or value.isdigit() for value in seen):
        return "up"
    if any(any(token in value for token in degraded_tokens) for value in seen):
        return "degraded"
    if any(any(token in value for token in down_tokens) for value in seen):
        return "down"
    return "degraded"


def _extract_overlay_meta(parsed_data: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(parsed_data, dict):
        return None

    candidates: List[Dict[str, Any]] = []
    for key in ("overlay", "vxlan_overlay", "fabric_overlay", "evpn_overlay", "vxlan", "evpn"):
        value = parsed_data.get(key)
        if isinstance(value, dict):
            candidates.append(value)

    merged: Dict[str, Any] = {}
    for candidate in candidates:
        for key, value in candidate.items():
            if key not in merged or not merged.get(key):
                merged[key] = value

    for key in ("vxlan_peers", "nve_peers", "overlay_peers", "vtep_peers", "evpn_neighbors", "evpn_peers", "vnis", "vni_list", "nve_interface", "nve_interfaces", "local_vtep_ip", "local_vtep_ips", "source_interface"):
        if key not in merged and key in parsed_data:
            merged[key] = parsed_data.get(key)

    vxlan_peers = []
    for key in ("vxlan_peers", "nve_peers", "overlay_peers", "vtep_peers"):
        vxlan_peers.extend(_normalize_overlay_rows(merged.get(key)))

    evpn_neighbors = []
    for key in ("evpn_neighbors", "evpn_peers"):
        evpn_neighbors.extend(_normalize_overlay_rows(merged.get(key)))

    vnis = []
    for key in ("vnis", "vni_list"):
        vnis.extend(_normalize_overlay_vni_rows(merged.get(key)))

    local_vtep_ips = []
    for key in ("local_vtep_ips", "local_vtep_ip", "vtep_ip", "source_ip"):
        for value in _normalize_string_list(merged.get(key)):
            ip = _clean_ip_value(value)
            if ip and ip not in local_vtep_ips:
                local_vtep_ips.append(ip)

    nve_interfaces = []
    for key in ("nve_interfaces", "nve_interface", "source_interface"):
        for value in _normalize_string_list(merged.get(key)):
            if value not in nve_interfaces:
                nve_interfaces.append(value)

    if not vxlan_peers and not evpn_neighbors and not vnis and not local_vtep_ips and not nve_interfaces:
        return None

    return {
        "vxlan_peers": vxlan_peers,
        "evpn_neighbors": evpn_neighbors,
        "vnis": vnis,
        "local_vtep_ips": local_vtep_ips,
        "nve_interfaces": nve_interfaces,
        "transport": _overlay_transport_value(merged),
    }


def _build_overlay_vni_map(overlay_meta: Optional[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    if not isinstance(overlay_meta, dict):
        return out
    for row in _normalize_overlay_vni_rows(overlay_meta.get("vnis")):
        vni = _overlay_vni_value(row)
        if vni is None:
            continue
        existing = out.get(vni) or {
            "vni": vni,
            "type": _overlay_vni_type(row),
            "state": _normalize_overlay_state(row.get("state"), row.get("status")),
            "vrf": str(row.get("vrf") or "").strip() or None,
            "bridge_domain": str(row.get("bridge_domain") or row.get("bd") or "").strip() or None,
        }
        if not existing.get("vrf"):
            existing["vrf"] = str(row.get("vrf") or "").strip() or None
        if not existing.get("bridge_domain"):
            existing["bridge_domain"] = str(row.get("bridge_domain") or row.get("bd") or "").strip() or None
        existing["state"] = _normalize_overlay_state(existing.get("state"), row.get("state"), row.get("status"))
        out[vni] = existing
    return out


def _match_overlay_peer_rows(
    parsed_data: Any,
    peer_ip_candidates: set[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    overlay_meta = _extract_overlay_meta(parsed_data)
    if not overlay_meta:
        return None, None, None

    vxlan_row = None
    evpn_row = None
    for row in overlay_meta.get("vxlan_peers") or []:
        peer_ip = _overlay_peer_ip(row)
        if peer_ip and peer_ip in peer_ip_candidates:
            vxlan_row = row
            break
    for row in overlay_meta.get("evpn_neighbors") or []:
        peer_ip = _overlay_peer_ip(row)
        if peer_ip and peer_ip in peer_ip_candidates:
            evpn_row = row
            break
    return overlay_meta, vxlan_row, evpn_row


def _build_node_overlay_summary(parsed_data: Any) -> Optional[Dict[str, Any]]:
    overlay_meta = _extract_overlay_meta(parsed_data)
    if not overlay_meta:
        return None

    vxlan_peers = overlay_meta.get("vxlan_peers") or []
    evpn_neighbors = overlay_meta.get("evpn_neighbors") or []
    vni_map = _build_overlay_vni_map(overlay_meta)

    peer_state_by_ip: Dict[str, List[str]] = {}
    for row in vxlan_peers:
        peer_ip = _overlay_peer_ip(row)
        if not peer_ip:
            continue
        peer_state_by_ip.setdefault(peer_ip, []).append(str(row.get("state") or row.get("status") or ""))
    for row in evpn_neighbors:
        peer_ip = _overlay_peer_ip(row)
        if not peer_ip:
            continue
        peer_state_by_ip.setdefault(peer_ip, []).append(str(row.get("state") or row.get("status") or ""))

    healthy = 0
    degraded = 0
    for values in peer_state_by_ip.values():
        normalized = _normalize_overlay_state(*values)
        if normalized == "up":
            healthy += 1
        else:
            degraded += 1

    l2_vnis = 0
    l3_vnis = 0
    for row in vni_map.values():
        if _overlay_vni_type(row) == "l3":
            l3_vnis += 1
        else:
            l2_vnis += 1

    peer_ips = sorted(peer_state_by_ip.keys())
    transports = sorted(
        {
            str(val).upper().replace("_", " ")
            for val in [_overlay_transport_value(overlay_meta), *[row.get("transport") for row in vxlan_peers], *[row.get("address_family") for row in evpn_neighbors]]
            if str(val or "").strip()
        }
    )

    return {
        "peer_counts": {
            "total": int(len(peer_state_by_ip)),
            "vxlan": int(len({_overlay_peer_ip(row) for row in vxlan_peers if _overlay_peer_ip(row)})),
            "evpn": int(len({_overlay_peer_ip(row) for row in evpn_neighbors if _overlay_peer_ip(row)})),
        },
        "vni_counts": {
            "total": int(len(vni_map)),
            "l2": int(l2_vnis),
            "l3": int(l3_vnis),
        },
        "state_counts": {
            "healthy": int(healthy),
            "degraded": int(degraded),
        },
        "local_vtep_ips": overlay_meta.get("local_vtep_ips") or [],
        "nve_interfaces": overlay_meta.get("nve_interfaces") or [],
        "peer_ips": peer_ips[:32],
        "transports": transports,
    }

def _build_device_ip_candidates(devices: List[Device], interface_rows: List[Tuple[int, Optional[str]]]) -> Dict[int, set[str]]:
    out: Dict[int, set[str]] = {}
    for dev in devices:
        vals = out.setdefault(int(dev.id), set())
        ip = _clean_ip_value(getattr(dev, "ip_address", None))
        if ip:
            vals.add(ip)
        overlay_meta = _extract_overlay_meta(getattr(dev, "latest_parsed_data", None))
        if overlay_meta:
            for overlay_ip in overlay_meta.get("local_vtep_ips") or []:
                ip = _clean_ip_value(overlay_ip)
                if ip:
                    vals.add(ip)
    for device_id, ip_address in interface_rows:
        if device_id is None:
            continue
        ip = _clean_ip_value(ip_address)
        if not ip:
            continue
        out.setdefault(int(device_id), set()).add(ip)
    return out


def _build_node_l3_summary(parsed_data: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(parsed_data, dict):
        return None

    l3 = parsed_data.get("l3_routing")
    if not isinstance(l3, dict):
        return None

    ospf_neighbors = _normalize_l3_neighbor_rows(l3.get("ospf_neighbors"))
    bgp_neighbors = _normalize_l3_neighbor_rows(l3.get("bgp_neighbors"))
    if not ospf_neighbors and not bgp_neighbors:
        return None

    local_asns = sorted(
        {
            asn
            for asn in (_safe_int_value(n.get("local_as")) for n in bgp_neighbors)
            if asn is not None
        }
    )
    peer_asns = sorted(
        {
            asn
            for asn in (_safe_int_value(n.get("remote_as")) for n in bgp_neighbors)
            if asn is not None
        }
    )
    areas = sorted({str(n.get("area") or "").strip() for n in ospf_neighbors if str(n.get("area") or "").strip()})
    peer_router_ids = sorted({str(n.get("neighbor_id") or "").strip() for n in ospf_neighbors if str(n.get("neighbor_id") or "").strip()})
    peer_ips = sorted(
        {
            ip
            for ip in (_clean_ip_value(n.get("neighbor_ip")) for n in (ospf_neighbors + bgp_neighbors))
            if ip
        }
    )

    bgp_established = 0
    bgp_degraded = 0
    ospf_full = 0
    ospf_degraded = 0

    for neighbor in bgp_neighbors:
        state = str(neighbor.get("state") or "").strip().lower()
        if state and ("established" in state or state.isdigit()):
            bgp_established += 1
        else:
            bgp_degraded += 1

    for neighbor in ospf_neighbors:
        state = str(neighbor.get("state") or "").strip().upper()
        if "FULL" in state:
            ospf_full += 1
        else:
            ospf_degraded += 1

    return {
        "peer_counts": {
            "total": int(len(ospf_neighbors) + len(bgp_neighbors)),
            "ospf": int(len(ospf_neighbors)),
            "bgp": int(len(bgp_neighbors)),
        },
        "state_counts": {
            "healthy": int(bgp_established + ospf_full),
            "degraded": int(bgp_degraded + ospf_degraded),
            "bgp_established": int(bgp_established),
            "ospf_full": int(ospf_full),
        },
        "protocols": [proto for proto, rows in (("OSPF", ospf_neighbors), ("BGP", bgp_neighbors)) if rows],
        "local_asns": local_asns,
        "peer_asns": peer_asns,
        "areas": areas,
        "peer_router_ids": peer_router_ids,
        "peer_ips": peer_ips[:32],
    }


def _match_bgp_neighbor(
    parsed_data: Any,
    peer_ip_candidates: set[str],
) -> Optional[Dict[str, Any]]:
    if not isinstance(parsed_data, dict):
        return None
    l3 = parsed_data.get("l3_routing")
    if not isinstance(l3, dict):
        return None
    for row in _normalize_l3_neighbor_rows(l3.get("bgp_neighbors")):
        neighbor_ip = _clean_ip_value(row.get("neighbor_ip"))
        if neighbor_ip and neighbor_ip in peer_ip_candidates:
            return row
    return None


def _match_ospf_neighbor(
    parsed_data: Any,
    peer_ip_candidates: set[str],
    local_interface_name: str,
) -> Optional[Dict[str, Any]]:
    if not isinstance(parsed_data, dict):
        return None
    l3 = parsed_data.get("l3_routing")
    if not isinstance(l3, dict):
        return None

    norm_local = str(local_interface_name or "").strip().lower()
    fallback = None
    for row in _normalize_l3_neighbor_rows(l3.get("ospf_neighbors")):
        neighbor_ip = _clean_ip_value(row.get("neighbor_ip"))
        neighbor_id = _clean_ip_value(row.get("neighbor_id"))
        row_interface = str(row.get("interface") or "").strip().lower()
        if norm_local and row_interface and row_interface == norm_local:
            return row
        if neighbor_ip and neighbor_ip in peer_ip_candidates:
            if not fallback:
                fallback = row
        elif neighbor_id and neighbor_id in peer_ip_candidates:
            if not fallback:
                fallback = row
    return fallback


def _build_l3_link_detail(
    *,
    protocol: str,
    source_device: Optional[Device],
    target_device: Optional[Device],
    meta_by_id: Dict[int, Dict[str, Any]],
    ip_candidates_by_device_id: Dict[int, set[str]],
    source_interface_name: str,
    target_interface_name: str,
) -> Optional[Dict[str, Any]]:
    if not source_device or not target_device:
        return None

    src_meta = meta_by_id.get(int(source_device.id), {}) if source_device.id is not None else {}
    dst_meta = meta_by_id.get(int(target_device.id), {}) if target_device.id is not None else {}
    src_ips = ip_candidates_by_device_id.get(int(source_device.id), set())
    dst_ips = ip_candidates_by_device_id.get(int(target_device.id), set())
    proto = str(protocol or "").strip().upper()

    if proto == "BGP":
        src_row = _match_bgp_neighbor(src_meta, dst_ips)
        dst_row = _match_bgp_neighbor(dst_meta, src_ips)
        if not src_row and not dst_row:
            return None

        src_local_as = _safe_int_value((src_row or {}).get("local_as"))
        src_remote_as = _safe_int_value((src_row or {}).get("remote_as"))
        dst_local_as = _safe_int_value((dst_row or {}).get("local_as"))
        dst_remote_as = _safe_int_value((dst_row or {}).get("remote_as"))
        source_as = src_local_as or dst_remote_as
        target_as = dst_local_as or src_remote_as

        relationship = "unknown"
        if source_as is not None and target_as is not None:
            relationship = "ibgp" if source_as == target_as else "ebgp"

        state = str((src_row or {}).get("state") or (dst_row or {}).get("state") or "").strip()
        normalized_state = state.lower() if state else "unknown"
        if normalized_state and ("established" in normalized_state or normalized_state.isdigit()):
            normalized_state = "established"

        return {
            "layer": "l3",
            "protocol": "BGP",
            "state": normalized_state,
            "relationship": relationship,
            "prefixes_received": _safe_int_value((src_row or {}).get("prefixes_received"))
            or _safe_int_value((dst_row or {}).get("prefixes_received")),
            "uptime": str((src_row or {}).get("uptime") or (dst_row or {}).get("uptime") or "").strip() or None,
            "source": {
                "device_id": int(source_device.id),
                "device_name": str(source_device.name or source_device.hostname or source_device.id),
                "neighbor_ip": _clean_ip_value((src_row or {}).get("neighbor_ip")),
                "local_as": source_as,
                "remote_as": src_remote_as or target_as,
            },
            "target": {
                "device_id": int(target_device.id),
                "device_name": str(target_device.name or target_device.hostname or target_device.id),
                "neighbor_ip": _clean_ip_value((dst_row or {}).get("neighbor_ip")),
                "local_as": target_as,
                "remote_as": dst_remote_as or source_as,
            },
        }

    if proto == "OSPF":
        src_row = _match_ospf_neighbor(src_meta, dst_ips, source_interface_name)
        dst_row = _match_ospf_neighbor(dst_meta, src_ips, target_interface_name)
        if not src_row and not dst_row:
            return None

        state = str((src_row or {}).get("state") or (dst_row or {}).get("state") or "").strip()
        normalized_state = state.lower() if state else "unknown"
        if "FULL" in state.upper():
            normalized_state = "full"

        return {
            "layer": "l3",
            "protocol": "OSPF",
            "state": normalized_state,
            "area": str((src_row or {}).get("area") or (dst_row or {}).get("area") or "").strip() or None,
            "source": {
                "device_id": int(source_device.id),
                "device_name": str(source_device.name or source_device.hostname or source_device.id),
                "neighbor_ip": _clean_ip_value((src_row or {}).get("neighbor_ip")),
                "neighbor_id": str((src_row or {}).get("neighbor_id") or "").strip() or None,
                "interface": str((src_row or {}).get("interface") or source_interface_name or "").strip() or None,
                "priority": _safe_int_value((src_row or {}).get("priority")),
            },
            "target": {
                "device_id": int(target_device.id),
                "device_name": str(target_device.name or target_device.hostname or target_device.id),
                "neighbor_ip": _clean_ip_value((dst_row or {}).get("neighbor_ip")),
                "neighbor_id": str((dst_row or {}).get("neighbor_id") or "").strip() or None,
                "interface": str((dst_row or {}).get("interface") or target_interface_name or "").strip() or None,
                "priority": _safe_int_value((dst_row or {}).get("priority")),
            },
        }

    return None


def _build_overlay_link_detail(
    *,
    source_device: Optional[Device],
    target_device: Optional[Device],
    meta_by_id: Dict[int, Dict[str, Any]],
    ip_candidates_by_device_id: Dict[int, set[str]],
) -> Optional[Dict[str, Any]]:
    if not source_device or not target_device:
        return None

    src_meta = meta_by_id.get(int(source_device.id), {}) if source_device.id is not None else {}
    dst_meta = meta_by_id.get(int(target_device.id), {}) if target_device.id is not None else {}
    src_ips = ip_candidates_by_device_id.get(int(source_device.id), set())
    dst_ips = ip_candidates_by_device_id.get(int(target_device.id), set())

    src_overlay, src_vxlan_row, src_evpn_row = _match_overlay_peer_rows(src_meta, dst_ips)
    dst_overlay, dst_vxlan_row, dst_evpn_row = _match_overlay_peer_rows(dst_meta, src_ips)
    if not src_overlay and not dst_overlay:
        return None
    if not src_vxlan_row and not src_evpn_row and not dst_vxlan_row and not dst_evpn_row:
        return None

    src_vni_map = _build_overlay_vni_map(src_overlay)
    dst_vni_map = _build_overlay_vni_map(dst_overlay)

    src_row_vnis = set(_overlay_vni_numbers(src_vxlan_row) + _overlay_vni_numbers(src_evpn_row))
    dst_row_vnis = set(_overlay_vni_numbers(dst_vxlan_row) + _overlay_vni_numbers(dst_evpn_row))
    shared_vnis = src_row_vnis & dst_row_vnis
    if not shared_vnis and src_vni_map and dst_vni_map:
        shared_vnis = set(src_vni_map.keys()) & set(dst_vni_map.keys())

    selected_vnis = shared_vnis or src_row_vnis or dst_row_vnis or set(src_vni_map.keys()) or set(dst_vni_map.keys())
    normalized_vnis = []
    for vni in sorted(selected_vnis):
        row = src_vni_map.get(vni) or dst_vni_map.get(vni) or {"vni": vni}
        normalized_vnis.append(
            {
                "vni": int(vni),
                "type": _overlay_vni_type(row),
                "state": _normalize_overlay_state(row.get("state"), row.get("status")),
                "vrf": str(row.get("vrf") or "").strip() or None,
                "bridge_domain": str(row.get("bridge_domain") or row.get("bd") or "").strip() or None,
            }
        )

    src_local_vtep = _clean_ip_value((src_vxlan_row or {}).get("local_vtep_ip")) or (
        (src_overlay or {}).get("local_vtep_ips") or [None]
    )[0]
    dst_local_vtep = _clean_ip_value((dst_vxlan_row or {}).get("local_vtep_ip")) or (
        (dst_overlay or {}).get("local_vtep_ips") or [None]
    )[0]
    src_nve = str((src_vxlan_row or {}).get("interface") or (src_vxlan_row or {}).get("nve_interface") or ((src_overlay or {}).get("nve_interfaces") or [None])[0] or "").strip() or None
    dst_nve = str((dst_vxlan_row or {}).get("interface") or (dst_vxlan_row or {}).get("nve_interface") or ((dst_overlay or {}).get("nve_interfaces") or [None])[0] or "").strip() or None

    transport = _overlay_transport_value(src_overlay, src_vxlan_row, src_evpn_row, dst_overlay, dst_vxlan_row, dst_evpn_row)
    state = _normalize_overlay_state(
        (src_vxlan_row or {}).get("state"),
        (src_evpn_row or {}).get("state"),
        (dst_vxlan_row or {}).get("state"),
        (dst_evpn_row or {}).get("state"),
    )

    src_as = _safe_int_value((src_evpn_row or {}).get("local_as")) or _safe_int_value((dst_evpn_row or {}).get("remote_as"))
    dst_as = _safe_int_value((dst_evpn_row or {}).get("local_as")) or _safe_int_value((src_evpn_row or {}).get("remote_as"))
    relationship = None
    if src_as is not None and dst_as is not None:
        relationship = "ibgp" if src_as == dst_as else "ebgp"

    return {
        "layer": "overlay",
        "protocol": "VXLAN",
        "state": state,
        "transport": transport,
        "encapsulation": "vxlan",
        "vni_count": int(len(normalized_vnis)),
        "vnis": normalized_vnis[:24],
        "source": {
            "device_id": int(source_device.id),
            "device_name": str(source_device.name or source_device.hostname or source_device.id),
            "peer_ip": _overlay_peer_ip(src_vxlan_row) or _overlay_peer_ip(src_evpn_row),
            "local_vtep_ip": _clean_ip_value(src_local_vtep),
            "nve_interface": src_nve,
            "local_as": src_as,
        },
        "target": {
            "device_id": int(target_device.id),
            "device_name": str(target_device.name or target_device.hostname or target_device.id),
            "peer_ip": _overlay_peer_ip(dst_vxlan_row) or _overlay_peer_ip(dst_evpn_row),
            "local_vtep_ip": _clean_ip_value(dst_local_vtep),
            "nve_interface": dst_nve,
            "local_as": dst_as,
        },
        "evpn": {
            "state": _normalize_overlay_state((src_evpn_row or {}).get("state"), (dst_evpn_row or {}).get("state")),
            "relationship": relationship,
            "source_as": src_as,
            "target_as": dst_as,
        } if src_evpn_row or dst_evpn_row else None,
    }


def _format_l3_link_label(protocol: str, detail: Optional[Dict[str, Any]], src_port: str, dst_port: str) -> str:
    proto = str(protocol or "").strip().upper()
    if not detail:
        return f"{src_port}<->{dst_port}"

    if proto == "BGP":
        source_as = detail.get("source", {}).get("local_as")
        target_as = detail.get("target", {}).get("local_as")
        parts = []
        if source_as is not None and target_as is not None:
            parts.append(f"AS{source_as}<->AS{target_as}")
        relationship = str(detail.get("relationship") or "").strip()
        if relationship:
            parts.append(relationship.upper())
        state = str(detail.get("state") or "").strip()
        if state:
            parts.append(state.upper())
        return " / ".join(parts) or "BGP session"

    if proto == "OSPF":
        parts = []
        state = str(detail.get("state") or "").strip()
        if state:
            parts.append(state.upper())
        area = str(detail.get("area") or "").strip()
        if area:
            parts.append(f"area {area}")
        if src_port or dst_port:
            parts.append(f"{src_port or '?'}<->{dst_port or '?'}")
        return " / ".join(parts) or "OSPF adjacency"

    return f"{src_port}<->{dst_port}"


def _format_overlay_link_label(detail: Optional[Dict[str, Any]], src_port: str, dst_port: str) -> str:
    if not detail:
        return f"{src_port or 'nve'}<->{dst_port or 'nve'}"

    parts = []
    transport = str(detail.get("transport") or "").strip()
    if transport:
        parts.append(transport.upper().replace("_", " "))
    vni_count = _safe_int_value(detail.get("vni_count"))
    if vni_count:
        parts.append(f"{vni_count} VNI")
    state = str(detail.get("state") or "").strip()
    if state:
        parts.append(state.upper())

    src_if = str(detail.get("source", {}).get("nve_interface") or src_port or "").strip() or "nve"
    dst_if = str(detail.get("target", {}).get("nve_interface") or dst_port or "").strip() or "nve"
    parts.append(f"{src_if}<->{dst_if}")
    return " / ".join(parts) or "VXLAN overlay"


def _infer_overlay_edges(
    *,
    devices: List[Device],
    device_by_id: Dict[int, Device],
    meta_by_id: Dict[int, Dict[str, Any]],
    ip_candidates_by_device_id: Dict[int, set[str]],
) -> List[Dict[str, Any]]:
    ip_to_device_ids: Dict[str, List[int]] = {}
    for device_id, candidates in ip_candidates_by_device_id.items():
        for ip in candidates:
            if not ip:
                continue
            ids = ip_to_device_ids.setdefault(ip, [])
            if int(device_id) not in ids:
                ids.append(int(device_id))

    overlay_edges: List[Dict[str, Any]] = []
    seen_pairs = set()
    for source_device in devices:
        if source_device.id is None:
            continue
        source_meta = _extract_overlay_meta(meta_by_id.get(int(source_device.id)))
        if not source_meta:
            continue
        peer_ips = sorted(
            {
                ip
                for ip in (
                    [_overlay_peer_ip(row) for row in source_meta.get("vxlan_peers") or []]
                    + [_overlay_peer_ip(row) for row in source_meta.get("evpn_neighbors") or []]
                )
                if ip
            }
        )
        for peer_ip in peer_ips:
            target_ids = ip_to_device_ids.get(peer_ip) or []
            for target_id in target_ids:
                if int(target_id) == int(source_device.id):
                    continue
                pair = tuple(sorted([int(source_device.id), int(target_id)]))
                if pair in seen_pairs:
                    continue
                target_device = device_by_id.get(int(target_id))
                if not target_device:
                    continue
                detail = _build_overlay_link_detail(
                    source_device=source_device,
                    target_device=target_device,
                    meta_by_id=meta_by_id,
                    ip_candidates_by_device_id=ip_candidates_by_device_id,
                )
                if not detail:
                    continue
                seen_pairs.add(pair)
                state = str(detail.get("state") or "unknown").strip().lower()
                if state == "up":
                    status = "active"
                elif state == "down":
                    status = "down"
                else:
                    status = "degraded"
                confidence = 0.95 if detail.get("source", {}).get("peer_ip") and detail.get("target", {}).get("peer_ip") else 0.82
                overlay_edges.append(
                    {
                        "id": f"overlay-{source_device.id}-{target_id}",
                        "source": str(source_device.id),
                        "target": str(target_id),
                        "src_port": str(detail.get("source", {}).get("nve_interface") or ""),
                        "dst_port": str(detail.get("target", {}).get("nve_interface") or ""),
                        "label": _format_overlay_link_label(detail, "", ""),
                        "status": status,
                        "protocol": "VXLAN",
                        "layer": "overlay",
                        "confidence": confidence,
                        "discovery_source": "overlay_parsed_data",
                        "first_seen": None,
                        "last_seen": None,
                        "l3": None,
                        "overlay": detail,
                        "evidence": {
                            "protocol": "VXLAN",
                            "discovery_source": "overlay_parsed_data",
                            "confidence": confidence,
                            "quality": "high" if confidence >= 0.9 else "medium",
                            "is_stale": False,
                            "age_seconds": 0,
                            "layer": "overlay",
                            "overlay": detail,
                        },
                        "traffic": {
                            "src_in_bps": 0.0,
                            "src_out_bps": 0.0,
                            "dst_in_bps": 0.0,
                            "dst_out_bps": 0.0,
                            "fwd_bps": 0.0,
                            "rev_bps": 0.0,
                            "ts": 0.0,
                        },
                    }
                )
                break
    return overlay_edges


# --------------------------------------------------------------------------
# [Dashboard] 대시보드 통계
# --------------------------------------------------------------------------
@router.get("/stats")
def read_dashboard_stats(
    site_id: int = Query(None),
    db: Session = Depends(get_db), 
    current_user: User = Depends(deps.require_viewer)
):
    """
    모든 장비 데이터를 가져와서 통계를 냅니다. site_id가 있으면 해당 사이트 장비만 보여줍니다.
    """
    # 1. Device Filtering
    device_query = db.query(Device.id, Device.status, Device.latest_parsed_data)
    if site_id:
        device_query = device_query.filter(Device.site_id == site_id)
    
    device_rows = device_query.all()
    total = len(device_rows)

    online_cnt = 0
    alert_cnt = 0
    total_aps = 0
    total_clients = 0

    # 2. Aggregate Stats (Status & Wireless)
    for _dev_id, dev_status, latest_parsed_data in device_rows:
        status_text = str(dev_status or "offline").lower().strip()

        # [Service = Device Reachability]
        if status_text in ['online', 'reachable', 'up']:
            online_cnt += 1
        elif status_text in ['alert', 'warning', 'degraded']:
            alert_cnt += 1

        # [Wireless Aggregate]
        if latest_parsed_data and isinstance(latest_parsed_data, dict):
            w_data = latest_parsed_data
            wireless_nested = w_data.get("wireless", {}) if isinstance(w_data.get("wireless"), dict) else {}
            
            # Clients
            c_count = w_data.get("total_clients") 
            if c_count is None:
                c_count = wireless_nested.get("total_clients", 0)
            total_clients += int(c_count or 0)
            
            # APs
            ap_list = wireless_nested.get("ap_list", [])
            if ap_list and isinstance(ap_list, list):
                total_aps += sum(1 for ap in ap_list if str(ap.get("status", "")).lower() in ('up', 'online', 'registered', 'reg'))
            elif "up_aps" in wireless_nested:
                total_aps += wireless_nested.get("up_aps", 0)
            elif "up_aps" in w_data:
                total_aps += w_data.get("up_aps", 0)

    offline_cnt = total - (online_cnt + alert_cnt)
    if offline_cnt < 0: offline_cnt = 0

    health_score = 0
    if total > 0:
        score = ((online_cnt - (alert_cnt * 0.5)) / total) * 100
        health_score = int(max(0, min(100, score)))

    # 3. Traffic Trend (Real Data)
    # 최근 10분간의 데이터 조회하여 분 단위 합산
    traffic_trend = []
    
    if total > 0:
        ten_mins_ago = datetime.now() - timedelta(minutes=10)
        dialect_name = db.bind.dialect.name if db.bind else ""
        if dialect_name == "sqlite":
            time_bucket = func.strftime("%H:%M", SystemMetric.timestamp)
        else:
            time_bucket = func.to_char(SystemMetric.timestamp, "HH24:MI")

        metric_query = db.query(
            time_bucket.label("t"),
            func.sum(SystemMetric.traffic_in).label("in_sum"),
            func.sum(SystemMetric.traffic_out).label("out_sum")
        ).filter(SystemMetric.timestamp >= ten_mins_ago)

        if site_id:
            metric_query = metric_query.join(Device, Device.id == SystemMetric.device_id).filter(Device.site_id == site_id)

        metrics = metric_query.group_by("t").order_by("t").all()

        trend_map = {}

        for m in metrics:
            t_str = m.t
            trend_map[t_str] = {
                "in": float(m.in_sum or 0),
                "out": float(m.out_sum or 0)
            }
        
        # 맵을 리스트로 변환
        # 데이터가 아예 없으면 빈 그래프가 나오므로, 현재 시간까지 빈 포인트 채워주기 (UX)
        start_dt = datetime.now().replace(second=0, microsecond=0) - timedelta(minutes=9)
        for i in range(10):
            curr = start_dt + timedelta(minutes=i)
            key = curr.strftime("%H:%M")
            val = trend_map.get(key, {"in": 0, "out": 0})
            traffic_trend.append({
                "time": key,
                "in": val["in"], # BPS
                "out": val["out"]
            })
    else:
        # 장비가 하나도 없어도 빈 그래프 표시
        now = datetime.now()
        for i in range(10):
            t = now - timedelta(minutes=(9 - i))
            traffic_trend.append({"time": t.strftime("%H:%M"), "in": 0, "out": 0})

    # Fetch recent issues (Filtered by site device)
    issue_query = db.query(Issue).filter(Issue.status == 'active')
    if site_id:
        issue_query = issue_query.join(Device, Device.id == Issue.device_id).filter(Device.site_id == site_id)
    
    recent_issues = issue_query.order_by(Issue.created_at.desc()).limit(10).all()
    
    service_impact_summary_map = ServiceGroupService.build_issue_service_impact_summary_map(db, recent_issues)

    issues_data = []
    for issue in recent_issues:
        issues_data.append({
            "id": issue.id,
            "title": issue.title,
            "device": issue.device.name if issue.device else "System",
            "device_id": issue.device_id,
            "site_id": int(issue.device.site_id) if issue.device and getattr(issue.device, "site_id", None) is not None else None,
            "site_name": issue.device.site_obj.name if issue.device and getattr(issue.device, "site_obj", None) else None,
            "severity": issue.severity,
            "time": issue.created_at.isoformat(),
            "service_impact_summary": service_impact_summary_map.get(int(issue.id)) or {
                "count": 0,
                "primary_group_id": None,
                "primary_name": None,
                "highest_criticality": None,
                "matched_member_count": 0,
                "primary_health_score": None,
                "primary_health_status": None,
                "review_group_count": 0,
                "critical_group_count": 0,
            },
        })

    # 카운트 쿼리도 필터 적용
    sites_count = db.query(Site).count() # Site 수는 전체 보여주는 게 맞음 (필터링해도)
    policy_query = db.query(Policy)
    if site_id: policy_query = policy_query.filter(Policy.site_id == site_id)
    
    final_data = {
        "counts": {
            "devices": total,
            "online": online_cnt,
            "offline": offline_cnt,
            "alert": alert_cnt,
            "sites": sites_count,
            "policies": policy_query.count(),
            "images": db.query(FirmwareImage).count(),
            "wireless_aps": total_aps,
            "wireless_clients": total_clients,
            "licenses": "Valid",
            "compliant": 0
        },
        "health_score": health_score,
        "trafficTrend": traffic_trend,
        "issues": issues_data
    }

    return JSONResponse(content=final_data)


@router.get("/wireless/overview")
def get_wireless_overview(db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    """
    전체 장비 중 무선 데이터를 포함한 장비(WLC)들의 통합 정보를 반환합니다.
    """
    wlc_devices = db.query(Device).filter(Device.latest_parsed_data.isnot(None)).all()
    
    all_aps = []
    all_wlans = []
    total_clients = 0
    
    for dev in wlc_devices:
        parsed = dev.latest_parsed_data
        wireless = parsed.get("wireless")
        if not wireless:
            continue
            
        total_clients += wireless.get("total_clients", 0)
        
        # WLANs 합치기 (중복 제거 필요할 수 있으나 여기서는 단순 나열)
        for wl in wireless.get("wlan_summary", []):
            all_wlans.append({
                **wl,
                "wlc_name": dev.name,
                "wlc_ip": dev.ip_address
            })
            
        # APs 합치기
        for ap in wireless.get("ap_list", []):
            all_aps.append({
                **ap,
                "wlc_name": dev.name,
                "wlc_ip": dev.ip_address
            })
            
    return {
        "summary": {
            "total_wlc": len(wlc_devices),
            "total_aps": len(all_aps),
            "total_wlans": len(all_wlans),
            "total_clients": total_clients
        },
        "wlans": all_wlans,
        "aps": all_aps
    }


# --------------------------------------------------------------------------
# [Helper] 유틸리티
# --------------------------------------------------------------------------
class VlanDeployRequest(BaseModel):
    device_ids: List[int]
    vlan_id: int
    vlan_name: str


def parse_uptime_seconds(uptime_value) -> str:
    """
    Parses uptime which can be numeric seconds or a Cisco-style string.
    Returns standardized format: Xd Xh Xm
    """
    if not uptime_value: 
        return "0d 0h 0m"
    
    # CASE 1: Already a formatted string if parsed by some TextFSM templates
    if isinstance(uptime_value, str) and ('day' in uptime_value or 'hour' in uptime_value):
        return uptime_value

    try:
        # CASE 2: Numeric value (seconds or centiseconds)
        val = float(uptime_value)
        # Handle SNMP-style centiseconds (common in some Cisco outputs)
        if val > 10000000: 
            val = val / 100
        
        td = timedelta(seconds=val)
        return f"{td.days}d {td.seconds // 3600}h {(td.seconds % 3600) // 60}m"
    except (ValueError, TypeError):
        # CASE 3: Unknown string format, return as is
        return str(uptime_value)


# --------------------------------------------------------------------------
# [Analytics] 분석 데이터
# --------------------------------------------------------------------------
@router.get("/analytics")
def get_analytics_data(time_range: str = Query("24h", alias="range"), db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    now = datetime.now()
    delta = timedelta(hours=1) if time_range == "1h" else timedelta(days=7) if time_range == "7d" else timedelta(
        hours=24)
    start_time = now - delta
    metrics = db.query(SystemMetric).filter(SystemMetric.timestamp >= start_time).order_by(
        SystemMetric.timestamp.asc()).all()

    resource_data = []
    if metrics:
        step = max(1, len(metrics) // 50)
        for i in range(0, len(metrics), step):
            m = metrics[i]
            fmt = "%H:%M" if time_range in ["1h", "24h"] else "%m/%d"
            resource_data.append({"time": m.timestamp.strftime(fmt), "cpu": m.cpu_usage, "memory": m.memory_usage})

    top_devices_query = db.query(Device).filter(Device.status == 'online').all()
    
    # [Optimized] Bulk query for latest metrics using Subquery or IN
    if top_devices_query:
        d_ids = [d.id for d in top_devices_query]
        # Get latest metric for each device
        subq = (
            db.query(
                SystemMetric.device_id,
                func.max(SystemMetric.timestamp).label("max_ts")
            )
            .filter(SystemMetric.device_id.in_(d_ids))
            .group_by(SystemMetric.device_id)
            .subquery()
        )
        
        latest_metrics = (
            db.query(SystemMetric)
            .join(subq, and_(
                SystemMetric.device_id == subq.c.device_id,
                SystemMetric.timestamp == subq.c.max_ts
            ))
            .all()
        )
        
        # Map by device_id
        metric_map = {m.device_id: m for m in latest_metrics}
    else:
        metric_map = {}

    device_stats = []
    for dev in top_devices_query:
        last_metric = metric_map.get(dev.id)
        if last_metric:
            device_stats.append(
                {"name": dev.name, "usage": last_metric.cpu_usage, "location": dev.location or "Unknown"})

    return {"resourceTrend": resource_data,
            "topDevices": sorted(device_stats, key=lambda x: x['usage'], reverse=True)[:5], "trafficTrend": []}


# --------------------------------------------------------------------------
# [Topology] 토폴로지 데이터 (수정됨: site_id 포함)
# --------------------------------------------------------------------------
@router.get("/topology/links")
def get_topology_links(
    snapshot_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    if snapshot_id is not None:
        import json
        from fastapi import HTTPException
        from app.models.topology import TopologySnapshot

        snap = db.query(TopologySnapshot).filter(TopologySnapshot.id == snapshot_id).first()
        if not snap:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        try:
            nodes = json.loads(snap.nodes_json or "[]")
        except Exception:
            nodes = []
        try:
            links = json.loads(snap.links_json or "[]")
        except Exception:
            links = []
        return {"nodes": nodes, "links": links, "snapshot_id": int(snap.id)}
    from datetime import datetime, timedelta
    from app.models.endpoint import Endpoint, EndpointAttachment
    from app.services.snmp_service import SnmpManager
    from sqlalchemy.orm import load_only
    now = datetime.now()

    def _iso_or_none(value: Any) -> Optional[str]:
        if value is None:
            return None
        try:
            return value.isoformat()
        except Exception:
            raw = str(value or "").strip()
            return raw or None

    PreviewManagedNodeService.reconcile_managed_devices(db)

    devices = (
        db.query(Device)
        .options(
            load_only(
                Device.id,
                Device.name,
                Device.hostname,
                Device.ip_address,
                Device.device_type,
                Device.model,
                Device.os_version,
                Device.status,
                Device.site_id,
                Device.latest_parsed_data,
                Device.variables,
                Device.management_state,
                Device.management_reason,
                Device.managed_since,
                Device.management_priority_score,
            )
        )
        .all()
    )
    sites = db.query(Site.id, Site.name).all()
    site_map = {sid: name for sid, name in sites}
    meta_by_id = {d.id: (d.latest_parsed_data or {}) for d in devices}
    device_by_id = {d.id: d for d in devices}
    device_ids = [d.id for d in devices if d.id is not None]
    interface_rows = []
    if device_ids:
        interface_rows = (
            db.query(Interface.device_id, Interface.ip_address)
            .filter(Interface.device_id.in_(device_ids))
            .all()
        )
    ip_candidates_by_device_id = _build_device_ip_candidates(devices, interface_rows)

    metric_by_device_id = {}
    if devices:
        ids = [d.id for d in devices]
        latest_ts = (
            db.query(SystemMetric.device_id.label("device_id"), func.max(SystemMetric.timestamp).label("max_ts"))
            .filter(SystemMetric.device_id.in_(ids))
            .group_by(SystemMetric.device_id)
            .subquery()
        )
        latest_rows = (
            db.query(SystemMetric)
            .join(latest_ts, and_(SystemMetric.device_id == latest_ts.c.device_id, SystemMetric.timestamp == latest_ts.c.max_ts))
            .all()
        )
        metric_by_device_id = {m.device_id: m for m in latest_rows if m and m.device_id is not None}
    
    nodes = []
    cloud_virtual_refs: Dict[str, Dict[str, Any]] = {}
    for d in devices:
        # [Hierarchy Logic]
        # Tier 0: Core/Router (Nexus, 9500, Router, Backbone)
        # Tier 1: Distribution/L3 Aggregation (9300, 3850, 4500, 6500, 9400, EX4, etc.)
        # Tier 2: Access/L2 (9200, 2960, C1000, etc.)
        # Tier 3: Endpoint (AP)

        dev_type = str(d.device_type or "").lower()
        model = str(d.model or "").lower()
        hostname = str(d.name or "").lower()
        
        tier = 2 # Default to Access
        role = "access"

        cloud_meta = None
        label = d.name
        site_name = site_map.get(d.site_id, "Default Site")

        if dev_type == "cloud_virtual":
            tier = 1
            role = "cloud"
            site_name = "Cloud"
            vars_ = d.variables if isinstance(d.variables, dict) else {}
            cloud = vars_.get("cloud") if isinstance(vars_.get("cloud"), dict) else {}
            refs = cloud.get("refs") if isinstance(cloud.get("refs"), list) else []
            first = refs[0] if refs and isinstance(refs[0], dict) else {}
            ref_priority = {
                "virtual_machine": 1,
                "instance": 1,
                "vm": 1,
                "load_balancer": 2,
                "vpn_connection": 3,
                "vpn_tunnel": 3,
                "transit_gateway": 4,
                "tgw_attachment": 4,
                "subnet": 5,
                "vpc": 6,
                "vnet": 6,
                "network": 6,
                "route_table": 7,
                "security_group": 8,
            }
            resource_type_labels = {
                "virtual_machine": "VM",
                "instance": "Instance",
                "vm": "VM",
                "load_balancer": "Load Balancer",
                "vpn_connection": "VPN",
                "vpn_tunnel": "VPN Tunnel",
                "transit_gateway": "Transit Gateway",
                "tgw_attachment": "TGW Attachment",
                "subnet": "Subnet",
                "vpc": "VPC",
                "vnet": "VNet",
                "network": "Network",
                "route_table": "Route Table",
                "security_group": "Security Group",
            }

            def _ref_sort_key(ref: dict) -> tuple[int, int]:
                rt = str((ref or {}).get("resource_type") or "").strip().lower()
                has_name = 0 if str((ref or {}).get("name") or "").strip() else 1
                return int(ref_priority.get(rt, 99)), has_name

            best_ref = min([r for r in refs if isinstance(r, dict)], key=_ref_sort_key, default=first)
            provider = (first.get("provider") or "cloud").strip().lower()
            region = (first.get("region") or "").strip()
            account_id_raw = first.get("account_id")
            try:
                account_id = int(account_id_raw) if account_id_raw is not None and str(account_id_raw).strip() != "" else None
            except Exception:
                account_id = None
            account_name = str(first.get("account_name") or "").strip() or None
            resource_type = str(best_ref.get("resource_type") or "").strip().lower()
            resource_id = str(best_ref.get("resource_id") or "").strip() or None
            resource_name = str(best_ref.get("name") or "").strip() or None
            resource_type_label = resource_type_labels.get(
                resource_type,
                (resource_type.replace("_", " ").title() if resource_type else None),
            )
            sanitized_refs: List[Dict[str, Any]] = []
            for ref in refs:
                if not isinstance(ref, dict):
                    continue
                ref_resource_type = str(ref.get("resource_type") or "").strip().lower() or None
                sanitized_refs.append(
                    {
                        "provider": str(ref.get("provider") or provider or "cloud").strip().lower() or "cloud",
                        "account_id": _safe_int_value(ref.get("account_id")),
                        "account_name": str(ref.get("account_name") or "").strip() or None,
                        "region": str(ref.get("region") or "").strip() or None,
                        "resource_type": ref_resource_type,
                        "resource_type_label": resource_type_labels.get(
                            ref_resource_type or "",
                            (ref_resource_type.replace("_", " ").title() if ref_resource_type else None),
                        ),
                        "resource_id": str(ref.get("resource_id") or "").strip() or None,
                        "resource_name": str(ref.get("name") or "").strip() or None,
                    }
                )
            ip_intel = first.get("ip_intel") if isinstance(first.get("ip_intel"), dict) else None
            inferred_from = first.get("inferred_from") if isinstance(first.get("inferred_from"), dict) else None
            cloud_meta = {
                "kind": "virtual_peer",
                "provider": provider or "cloud",
                "account_id": account_id,
                "account_name": account_name,
                "region": region,
                "resource_type": resource_type or None,
                "resource_type_label": resource_type_label,
                "resource_id": resource_id,
                "resource_name": resource_name,
                "resource_count": len(refs),
                "asn": (ip_intel or {}).get("asn") if ip_intel else None,
                "as_name": (ip_intel or {}).get("as_name") if ip_intel else None,
                "org_name": (ip_intel or {}).get("org_name") if ip_intel else None,
                "source": (ip_intel or {}).get("source") if ip_intel else None,
                "inferred_from": inferred_from,
                "refs": sanitized_refs[:8],
                "ref_resource_types": sorted(
                    {
                        str(row.get("resource_type") or "").strip().lower()
                        for row in sanitized_refs
                        if str(row.get("resource_type") or "").strip()
                    }
                ),
            }
            provider_label = str(provider or "cloud").upper()
            default_label = f"{provider_label}{(' ' + region) if region else ''} {d.ip_address}".strip()
            label = resource_name or resource_id or default_label
            cloud_virtual_refs[str(d.id)] = {
                "account_id": account_id,
                "account_name": account_name,
                "provider": provider or "cloud",
                "region": region,
                "resource_type": resource_type or None,
                "resource_id": resource_id,
                "refs": [r for r in refs if isinstance(r, dict)],
            }

        # Keep cloud virtual devices as role=cloud. Non-cloud devices follow role inference below.
        if dev_type != "cloud_virtual":
            # 1. CORE / SPINE (Tier 0)
            # Check for specific high-end models or explicit "core"/"spine" in hostname/type
            if (any(k in model for k in ["nexus", "9500", "9600", "n7k", "n9k", "asr", "isr", "mx", "ptx", "ne40", "ce128"]) or \
               any(k in dev_type for k in ["router", "core", "spine", "gateway"]) or \
               "core" in hostname or "spine" in hostname):
                tier = 0
                role = "core"

            # 2. DISTRIBUTION / L3 AGGREGATION (Tier 1)
            # Check for L3 switches or explicit "dist"/"agg" in hostname
            elif (any(k in model for k in ["9300", "9400", "9410", "9500", "9600", "3850", "3650", "4500", "6500", "6800", "cat9k", "ex4", "ex3", "qfx", "s67", "7050", "7280", "c3850", "c3650", "c93", "c94", "c95", "c96", "c36", "c38"]) or \
                 "dist" in hostname or "agg" in hostname or "l3" in hostname):
                tier = 1
                role = "distribution"

            # 3. SECURITY / FIREWALL (Tier 1)
            elif (any(k in dev_type for k in ["firewall", "security", "utm", "fw"]) or \
                 any(k in model for k in ["forti", "palo", "asa", "srx", "check", "firepower", "pa-", "fg-"])):
                tier = 1
                role = "security"

            # 4. WIRELESS CONTROLLER (Tier 1)
            elif (any(k in dev_type for k in ["wlc", "controller", "wireless"]) or \
                 any(k in model for k in ["9800", "5508", "2504", "5520", "8540", "ac6", "vwlc"])):
                tier = 1
                role = "wlc"

            # 5. ACCESS POINTS (Tier 3)
            elif any(k in dev_type for k in ["ap", "access point"]) or \
                 any(k in model for k in ["air-", "cap", "iap", "mr", "nap", "wap"]):
                tier = 3
                role = "access_point"

            # 6. DOMESTIC / KOREA VENDORS (Tier 2) - Highlight
            elif any(k in dev_type for k in ["dasan", "ubiquoss", "handream", "piolink"]) or \
                 any(k in model for k in ["v2", "v6", "v8", "e5", "h3", "h4"]): # Common domestic model prefixes if needed, but risky. Sticking to vendor check mainly.
                tier = 2
                role = "access_domestic"
                
            # 7. Explicit L2/Access Models (Fail-safe, though they would fall through anyway)
            elif any(k in model for k in ["2960", "9200", "1000", "c2960", "c9200", "c1000", "sf300", "sg300"]):
                tier = 2
                role = "access"

            # [Default] Access Layer (Tier 2)
            else:
                tier = 2
                role = "access"
        
        # [Check Metrics for Healthmap]
        latest_metric = metric_by_device_id.get(d.id)
        cpu = latest_metric.cpu_usage if latest_metric else 0
        mem = latest_metric.memory_usage if latest_metric else 0
        
        # [Unified Health Score Calculation]
        # Base: 100 - max(cpu, memory)
        # WLC Penalty: If AP down ratio > 10%, subtract additional points
        base_health = 100 - max(cpu or 0, mem or 0)
        
        # Wireless specific metrics
        wireless_data = {}
        ap_penalty = 0
        if d.latest_parsed_data and isinstance(d.latest_parsed_data, dict):
            w = d.latest_parsed_data.get("wireless", {})
            if w:
                total_aps = w.get("total_aps", 0) or 0
                down_aps = w.get("down_aps", 0) or 0
                clients = w.get("total_clients", 0) or 0
                wireless_data = {
                    "total_aps": total_aps,
                    "down_aps": down_aps,
                    "up_aps": total_aps - down_aps,
                    "clients": clients
                }
                # AP Down Penalty: If >10% APs are down, reduce health score
                if total_aps > 0:
                    down_ratio = (down_aps / total_aps) * 100
                    if down_ratio > 50:
                        ap_penalty = 30  # Critical
                    elif down_ratio > 20:
                        ap_penalty = 15  # Warning
                    elif down_ratio > 10:
                        ap_penalty = 5   # Minor
        
        health_score = max(0, min(100, base_health - ap_penalty))
        
        nodes.append({
            "id": str(d.id),
            "label": label,
            "ip": d.ip_address,
            "type": d.device_type,
            "hostname": d.hostname,
            "model": d.model,
            "os_version": d.os_version,
            "status": str(d.status or "offline").lower(),
            "site_id": d.site_id,
            "site_name": site_name,
            "tier": tier,   # [NEW] For Dagre Ranking
            "role": role,   # [NEW] For Visual Grouping/Coloring
            "management_state": str(getattr(d, "management_state", "managed") or "managed"),
            "management_reason": getattr(d, "management_reason", None),
            "managed_since": _iso_or_none(getattr(d, "managed_since", None)),
            "management_priority_score": float(getattr(d, "management_priority_score", 0.0) or 0.0),
            "is_managed": PreviewManagedNodeService.is_managed_device(d),
            "cloud": cloud_meta,
            "l3": _build_node_l3_summary(d.latest_parsed_data),
            "overlay": _build_node_overlay_summary(d.latest_parsed_data),
            "evidence": {"type": "cloud_peer", **(cloud_meta or {})} if cloud_meta else None,
            "metrics": {
                "cpu": cpu,
                "memory": mem,
                "health_score": health_score,
                "traffic_in": latest_metric.traffic_in if latest_metric else 0,
                "traffic_out": latest_metric.traffic_out if latest_metric else 0,
                **wireless_data  # Spread wireless metrics if available
            }
        })

    cloud_hierarchy_nodes: List[Dict[str, Any]] = []
    cloud_hierarchy_edges: List[Dict[str, Any]] = []
    cloud_edge_seen = set()

    infra_types = {"vpc", "vnet", "network", "subnet"}
    vm_types = {"virtual_machine", "instance", "vm"}

    resource_type_labels = {
        "virtual_machine": "VM",
        "instance": "Instance",
        "vm": "VM",
        "subnet": "Subnet",
        "vpc": "VPC",
        "vnet": "VNet",
        "network": "Network",
    }

    def _provider_group(raw: Optional[str]) -> str:
        p = str(raw or "").strip().lower()
        if p in {"ncp", "naver_cloud"}:
            return "naver"
        if p in {"aws", "azure", "gcp", "naver"}:
            return p
        return p or "cloud"

    def _to_int(raw: Any) -> Optional[int]:
        if raw is None:
            return None
        s = str(raw).strip()
        if not s:
            return None
        try:
            return int(s)
        except Exception:
            return None

    def _resource_aliases(value: Any) -> List[str]:
        raw = str(value or "").strip()
        if not raw:
            return []
        base = raw.rstrip("/").strip()
        aliases = {base.lower()}
        if "/" in base:
            aliases.add(base.split("/")[-1].strip().lower())
        if ":" in base:
            aliases.add(base.split(":")[-1].strip().lower())
        return [a for a in aliases if a]

    def _resource_type_label(rt: Optional[str]) -> Optional[str]:
        key = str(rt or "").strip().lower()
        if not key:
            return None
        return resource_type_labels.get(key, key.replace("_", " ").title())

    def _metadata_reference_aliases(meta: Any) -> set[str]:
        aliases: set[str] = set()
        if not isinstance(meta, dict):
            return aliases

        scalar_keys = (
            "vpc_id",
            "vnet_id",
            "network",
            "subnet_id",
            "subnetwork",
            "subnet_no",
            "vpc_no",
            "network_security_group",
            "network_acl_no",
            "vpn_gateway_id",
            "customer_gateway_id",
            "tgw_id",
            "resource_id",
        )
        list_keys = (
            "vnet_ids",
            "subnet_ids",
            "subnetworks",
            "networks",
            "security_group_ids",
        )

        for key in scalar_keys:
            for alias in _resource_aliases(meta.get(key)):
                aliases.add(alias)

        for key in list_keys:
            raw_vals = meta.get(key)
            if not isinstance(raw_vals, list):
                continue
            for item in raw_vals:
                for alias in _resource_aliases(item):
                    aliases.add(alias)

        associations = meta.get("associations")
        if isinstance(associations, list):
            for row in associations:
                if not isinstance(row, dict):
                    continue
                for alias in _resource_aliases(row.get("subnet_id")):
                    aliases.add(alias)

        return aliases

    def _resource_stub(row: CloudResource) -> Dict[str, Any]:
        return {
            "resource_id": str(getattr(row, "resource_id", "") or "").strip() or None,
            "resource_name": str(getattr(row, "name", "") or "").strip() or None,
            "resource_type": str(getattr(row, "resource_type", "") or "").strip().lower() or None,
            "resource_type_label": _resource_type_label(getattr(row, "resource_type", None)),
            "region": str(getattr(row, "region", "") or "").strip() or None,
            "state": str(getattr(row, "state", "") or "").strip() or None,
        }

    def _security_rule_count(meta: Any) -> int:
        if not isinstance(meta, dict):
            return 0
        total = 0
        for key in ("inbound_rules", "outbound_rules", "security_rule_count", "default_security_rule_count"):
            value = _safe_int_value(meta.get(key))
            if value is not None:
                total += int(value)
        return total

    def _cloud_resource_state(raw: Any) -> str:
        text = str(raw or "").strip().lower()
        if not text:
            return "offline"

        token = text.split(":", 1)[0].strip() if ":" in text else text
        token = token.split()[0].strip() if token else text

        online_tokens = {
            "running",
            "run",
            "available",
            "active",
            "up",
            "succeeded",
            "ready",
            "ok",
            "online",
        }
        offline_tokens = {
            "stopped",
            "stop",
            "terminated",
            "terminate",
            "deleting",
            "deleted",
            "failed",
            "fail",
            "down",
            "error",
            "offline",
        }

        if token in online_tokens or any(word in text for word in ("운영중", "실행중", "running", "online")):
            return "online"
        if token in offline_tokens or any(word in text for word in ("정지", "중지", "stopped", "offline")):
            return "offline"
        return "offline"

    def _cloud_resource_state_normalized(raw: Any) -> str:
        text = str(raw or "").strip().lower()
        if not text:
            return "offline"

        token = text.split(":", 1)[0].strip() if ":" in text else text
        token = token.split()[0].strip() if token else text

        online_tokens = {
            "running",
            "run",
            "available",
            "active",
            "up",
            "succeeded",
            "ready",
            "ok",
            "online",
        }
        offline_tokens = {
            "stopped",
            "stop",
            "terminated",
            "terminate",
            "deleting",
            "deleted",
            "failed",
            "fail",
            "down",
            "error",
            "offline",
            "shuttingdown",
            "shutting-down",
        }

        if token in online_tokens or "running" in text or "online" in text:
            return "online"
        if token in offline_tokens or "stopped" in text or "offline" in text:
            return "offline"
        return "offline"

    def _append_cloud_edge(source_id: Optional[str], target_id: Optional[str], *, label: str, relation: str) -> None:
        src = str(source_id or "").strip()
        dst = str(target_id or "").strip()
        if not src or not dst or src == dst:
            return
        key = tuple(sorted([src, dst]) + [label])
        if key in cloud_edge_seen:
            return
        cloud_edge_seen.add(key)
        cloud_hierarchy_edges.append(
            {
                "source": src,
                "target": dst,
                "src_port": relation,
                "dst_port": relation,
                "label": label,
                "status": "active",
                "protocol": "CLOUD",
                "confidence": 1.0,
                "discovery_source": "cloud_inventory",
                "first_seen": None,
                "last_seen": None,
                "evidence": {
                    "protocol": "CLOUD",
                    "discovery_source": "cloud_inventory",
                    "confidence": 1.0,
                    "quality": "high",
                    "is_stale": False,
                    "age_seconds": 0,
                },
                "traffic": {
                    "src_in_bps": 0.0,
                    "src_out_bps": 0.0,
                    "dst_in_bps": 0.0,
                    "dst_out_bps": 0.0,
                    "fwd_bps": 0.0,
                    "rev_bps": 0.0,
                    "ts": 0,
                },
            }
        )

    infra_nodes_by_account_alias: Dict[Tuple[int, str], str] = {}
    infra_nodes_by_global_alias: Dict[str, str] = {}
    vm_nodes_by_account_alias: Dict[Tuple[int, str], str] = {}
    vm_nodes_by_global_alias: Dict[str, str] = {}
    vm_rows_by_account_alias: Dict[Tuple[int, str], Tuple[CloudResource, CloudAccount]] = {}
    vm_rows_by_global_alias: Dict[str, Tuple[CloudResource, CloudAccount]] = {}

    def _lookup_vm_node(account_id: Optional[int], candidate: Any) -> Optional[str]:
        aliases = _resource_aliases(candidate)
        if not aliases:
            return None
        for alias in aliases:
            if account_id is not None:
                by_acc = vm_nodes_by_account_alias.get((int(account_id), alias))
                if by_acc:
                    return by_acc
            by_global = vm_nodes_by_global_alias.get(alias)
            if by_global:
                return by_global
        return None

    def _cloud_resource_ip(meta: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(meta, dict):
            return None
        for key in ("private_ip", "public_ip"):
            raw = str(meta.get(key) or "").strip()
            if raw:
                return raw
        for key in ("private_ips", "public_ips"):
            values = meta.get(key)
            if isinstance(values, list):
                for item in values:
                    raw = str(item or "").strip()
                    if raw:
                        return raw
        return None

    cloud_q = db.query(CloudResource, CloudAccount).join(CloudAccount, CloudAccount.id == CloudResource.account_id)
    tenant_id = getattr(current_user, "tenant_id", None) if current_user is not None else None
    if tenant_id is not None:
        cloud_q = cloud_q.filter(CloudAccount.tenant_id == tenant_id)
    cloud_rows = cloud_q.all()
    global_cloud_execution_readiness = CloudIntentExecutionService.execution_readiness()
    account_execution_readiness: Dict[int, Dict[str, Any]] = {}
    for _res, acc in cloud_rows:
        account_pk = int(getattr(acc, "id"))
        if account_pk in account_execution_readiness:
            continue
        runtime_credentials = decrypt_credentials_for_runtime(getattr(acc, "provider", None), getattr(acc, "credentials", None) or {})
        account_execution_readiness[account_pk] = CloudAccountReadinessService.build(
            getattr(acc, "provider", None),
            runtime_credentials,
            global_execution_readiness=global_cloud_execution_readiness,
        )
    account_resource_rows: Dict[int, List[Tuple[CloudResource, CloudAccount]]] = {}
    for res, acc in cloud_rows:
        account_resource_rows.setdefault(int(getattr(acc, "id")), []).append((res, acc))

    connectivity_types = {
        "load_balancer",
        "vpn_gateway",
        "vpn_connection",
        "vpn_tunnel",
        "customer_gateway",
        "transit_gateway",
        "tgw_attachment",
    }

    def _build_cloud_operational_summary(
        account_id: int,
        resource_type: str,
        resource_id: str,
        region: str,
        metadata: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        rows = account_resource_rows.get(int(account_id), [])
        scope_aliases: set[str] = set(_resource_aliases(resource_id))
        scope_aliases.update(_metadata_reference_aliases(metadata))
        direct_security_aliases: set[str] = set()
        if isinstance(metadata, dict):
            for alias in _resource_aliases(metadata.get("network_security_group")):
                direct_security_aliases.add(alias)
            for alias in _resource_aliases(metadata.get("network_acl_no")):
                direct_security_aliases.add(alias)
            for sg_id in list(metadata.get("security_group_ids") or []):
                for alias in _resource_aliases(sg_id):
                    direct_security_aliases.add(alias)

        route_refs: List[Dict[str, Any]] = []
        security_refs: List[Dict[str, Any]] = []
        connectivity_refs: List[Dict[str, Any]] = []
        route_seen: set[str] = set()
        security_seen: set[str] = set()
        connectivity_seen: set[str] = set()
        matched_direct_security_aliases: set[str] = set()
        routes_total = 0
        security_rules_total = 0

        same_region_resources = 0
        for row, _acc in rows:
            row_region = str(getattr(row, "region", "") or "").strip()
            if region and row_region and row_region == region:
                same_region_resources += 1

            row_type = str(getattr(row, "resource_type", "") or "").strip().lower()
            row_meta = getattr(row, "resource_metadata", None) if isinstance(getattr(row, "resource_metadata", None), dict) else {}
            row_id = str(getattr(row, "resource_id", "") or "").strip()
            row_aliases = set(_resource_aliases(row_id))
            row_aliases.update(_metadata_reference_aliases(row_meta))
            overlap = bool(scope_aliases & row_aliases)

            if row_type == "route_table" and overlap:
                key = row_id or f"route_table:{len(route_refs)}"
                if key not in route_seen:
                    route_seen.add(key)
                    route_refs.append(_resource_stub(row))
                routes_total += len(list((row_meta or {}).get("routes") or []))
                continue

            security_direct = bool(direct_security_aliases & set(_resource_aliases(row_id)))
            security_scoped = overlap and row_type == "security_group"
            if row_type == "security_group" and (security_direct or security_scoped):
                if security_direct:
                    matched_direct_security_aliases.update(set(_resource_aliases(row_id)) & direct_security_aliases)
                key = row_id or f"security_group:{len(security_refs)}"
                if key not in security_seen:
                    security_seen.add(key)
                    security_refs.append(_resource_stub(row))
                security_rules_total += _security_rule_count(row_meta)
                continue

            if row_type in connectivity_types and overlap:
                key = row_id or f"{row_type}:{len(connectivity_refs)}"
                if key not in connectivity_seen:
                    connectivity_seen.add(key)
                    connectivity_refs.append(_resource_stub(row))

        return {
            "account_resources": len(rows),
            "region_resources": int(same_region_resources),
            "route_tables": len(route_refs),
            "routes": int(routes_total),
            "security_policies": len(security_refs) + len(direct_security_aliases - matched_direct_security_aliases),
            "security_rules": int(security_rules_total),
            "connectivity_objects": len(connectivity_refs),
            "attached_security_refs": sorted(list(direct_security_aliases)),
            "route_refs": route_refs[:5],
            "security_refs": security_refs[:5],
            "connectivity_refs": connectivity_refs[:5],
        }

    for res, acc in cloud_rows:
        account_id = int(getattr(acc, "id"))
        resource_id = str(getattr(res, "resource_id", "") or "").strip()
        resource_type = str(getattr(res, "resource_type", "") or "").strip().lower()
        if not resource_id or not resource_type:
            continue

        metadata = getattr(res, "resource_metadata", None) if isinstance(getattr(res, "resource_metadata", None), dict) else {}

        if resource_type in vm_types:
            for alias in _resource_aliases(resource_id):
                vm_rows_by_account_alias[(account_id, alias)] = (res, acc)
                vm_rows_by_global_alias.setdefault(alias, (res, acc))
        if resource_type in infra_types or resource_type in vm_types:
            seed = f"{account_id}:{resource_type}:{resource_id}"
            digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
            node_id = f"cr-{account_id}-{resource_type}-{digest}"

            provider = _provider_group(getattr(acc, "provider", None))
            account_name = str(getattr(acc, "name", "") or "").strip() or None
            region = str(getattr(res, "region", "") or "").strip()
            cidr = str(getattr(res, "cidr_block", "") or "").strip()
            raw_state = str(getattr(res, "state", "") or "").strip().lower()
            state = _cloud_resource_state_normalized(raw_state)
            resource_name = str(getattr(res, "name", "") or "").strip() or None
            type_label = _resource_type_label(resource_type)
            label = resource_name or resource_id
            primary_ip = _cloud_resource_ip(metadata)
            operational_summary = _build_cloud_operational_summary(
                account_id=account_id,
                resource_type=resource_type,
                resource_id=resource_id,
                region=region,
                metadata=metadata,
            )

            cloud_meta = {
                "kind": "inventory_resource",
                "provider": provider or "cloud",
                "account_id": account_id,
                "account_name": account_name,
                "cloud_resource_id": int(getattr(res, "id")),
                "last_synced_at": _iso_or_none(getattr(acc, "last_synced_at", None)),
                "sync_status": str(getattr(acc, "sync_status", "") or "").strip() or None,
                "sync_message": str(getattr(acc, "sync_message", "") or "").strip() or None,
                "region": region,
                "resource_type": resource_type,
                "resource_type_label": type_label,
                "resource_id": resource_id,
                "resource_name": resource_name,
                "provider_state": raw_state or None,
                "resource_count": 1,
                "asn": None,
                "as_name": None,
                "org_name": None,
                "source": "cloud_inventory",
                "inferred_from": None,
                "refs": [],
                "ref_resource_types": [resource_type] if resource_type else [],
                "operational_summary": operational_summary,
                "execution_readiness": account_execution_readiness.get(account_id, {}),
            }

            cloud_hierarchy_nodes.append(
                {
                    "id": node_id,
                    "label": label,
                    "ip": primary_ip or cidr or resource_id,
                    "type": f"cloud_{resource_type}",
                    "hostname": resource_name or resource_id,
                    "model": type_label,
                    "os_version": "",
                    "status": state,
                    "site_id": None,
                    "site_name": "Cloud",
                    "tier": 0 if resource_type in {"vpc", "vnet", "network"} else (2 if resource_type in vm_types else 1),
                    "role": "cloud",
                    "cloud": cloud_meta,
                    "evidence": {"type": "cloud_peer", **cloud_meta},
                    "metrics": {
                        "cpu": 0,
                        "memory": 0,
                        "health_score": 100,
                        "traffic_in": 0,
                        "traffic_out": 0,
                    },
                }
            )

            for alias in _resource_aliases(resource_id):
                if resource_type in infra_types:
                    infra_nodes_by_account_alias[(account_id, alias)] = node_id
                    infra_nodes_by_global_alias.setdefault(alias, node_id)
                if resource_type in vm_types:
                    vm_nodes_by_account_alias[(account_id, alias)] = node_id
                    vm_nodes_by_global_alias.setdefault(alias, node_id)

        if resource_type not in infra_types and resource_type not in vm_types:
            continue

    def _lookup_infra_node(account_id: Optional[int], candidate: Any) -> Optional[str]:
        aliases = _resource_aliases(candidate)
        if not aliases:
            return None
        for alias in aliases:
            if account_id is not None:
                by_acc = infra_nodes_by_account_alias.get((int(account_id), alias))
                if by_acc:
                    return by_acc
            by_global = infra_nodes_by_global_alias.get(alias)
            if by_global:
                return by_global
        return None

    for res, acc in cloud_rows:
        resource_type = str(getattr(res, "resource_type", "") or "").strip().lower()
        if resource_type != "subnet":
            continue
        account_id = int(getattr(acc, "id"))
        child_node = _lookup_infra_node(account_id, getattr(res, "resource_id", None))
        if not child_node:
            continue
        meta = getattr(res, "resource_metadata", None) if isinstance(getattr(res, "resource_metadata", None), dict) else {}
        parent_candidates = [
            meta.get("vpc_id") if isinstance(meta, dict) else None,
            meta.get("vnet_id") if isinstance(meta, dict) else None,
            meta.get("network") if isinstance(meta, dict) else None,
        ]
        for parent_ref in parent_candidates:
            parent_node = _lookup_infra_node(account_id, parent_ref)
            if parent_node:
                _append_cloud_edge(parent_node, child_node, label="contains", relation="hierarchy")
                break

    for res, acc in cloud_rows:
        resource_type = str(getattr(res, "resource_type", "") or "").strip().lower()
        if resource_type not in vm_types:
            continue
        account_id = int(getattr(acc, "id"))
        child_node = _lookup_vm_node(account_id, getattr(res, "resource_id", None))
        if not child_node:
            continue
        meta = getattr(res, "resource_metadata", None) if isinstance(getattr(res, "resource_metadata", None), dict) else {}
        parent_candidates: List[Any] = [
            meta.get("subnet_id") if isinstance(meta, dict) else None,
            meta.get("subnetwork") if isinstance(meta, dict) else None,
            meta.get("subnet") if isinstance(meta, dict) else None,
            meta.get("subnet_no") if isinstance(meta, dict) else None,
            meta.get("vpc_id") if isinstance(meta, dict) else None,
            meta.get("vnet_id") if isinstance(meta, dict) else None,
            meta.get("network") if isinstance(meta, dict) else None,
            meta.get("vpc_no") if isinstance(meta, dict) else None,
        ]
        if isinstance(meta, dict):
            for key in ("subnet_ids", "vnet_ids"):
                values = meta.get(key)
                if isinstance(values, list):
                    parent_candidates.extend(values)
        for parent_ref in parent_candidates:
            parent_node = _lookup_infra_node(account_id, parent_ref)
            if parent_node:
                _append_cloud_edge(parent_node, child_node, label="contains", relation="hierarchy")
                break

    for device_id, ctx in cloud_virtual_refs.items():
        refs = ctx.get("refs") if isinstance(ctx.get("refs"), list) else []
        account_id = _to_int(ctx.get("account_id"))

        parent_node_id = None
        vm_node_id = None
        parent_candidates: List[Tuple[Optional[int], Any]] = []

        direct_vm_candidates: List[Tuple[Optional[int], str]] = []
        ctx_rt = str(ctx.get("resource_type") or "").strip().lower()
        ctx_rid = str(ctx.get("resource_id") or "").strip()
        if ctx_rt in vm_types and ctx_rid:
            direct_vm_candidates.append((account_id, ctx_rid))

        for ref in refs:
            if not isinstance(ref, dict):
                continue
            rt = str(ref.get("resource_type") or "").strip().lower()
            rid = str(ref.get("resource_id") or "").strip()
            ref_acc = _to_int(ref.get("account_id"))
            if rt in vm_types and rid:
                direct_vm_candidates.append((ref_acc if ref_acc is not None else account_id, rid))
            if rt in {"subnet", "vpc", "vnet", "network"} and rid:
                parent_candidates.append((ref_acc if ref_acc is not None else account_id, rid))

        vm_match = None
        for cand_acc, cand_rid in direct_vm_candidates:
            if vm_node_id is None:
                vm_node_id = _lookup_vm_node(cand_acc, cand_rid)
            aliases = _resource_aliases(cand_rid)
            for alias in aliases:
                if cand_acc is not None:
                    vm_match = vm_rows_by_account_alias.get((int(cand_acc), alias))
                    if vm_match:
                        break
                vm_match = vm_rows_by_global_alias.get(alias)
                if vm_match:
                    break
            if vm_match:
                break

        if vm_match is not None:
            vm_res, vm_acc = vm_match
            vm_meta = vm_res.resource_metadata if isinstance(vm_res.resource_metadata, dict) else {}
            vm_acc_id = int(getattr(vm_acc, "id"))
            parent_candidates = [
                (vm_acc_id, vm_meta.get("subnet_id")),
                (vm_acc_id, vm_meta.get("subnetwork")),
                (vm_acc_id, vm_meta.get("subnet")),
                (vm_acc_id, vm_meta.get("subnet_no")),
                (vm_acc_id, vm_meta.get("vpc_id")),
                (vm_acc_id, vm_meta.get("vnet_id")),
                (vm_acc_id, vm_meta.get("network")),
                (vm_acc_id, vm_meta.get("vpc_no")),
                *parent_candidates,
            ]
            subnet_ids = vm_meta.get("subnet_ids")
            if isinstance(subnet_ids, list):
                parent_candidates = [(vm_acc_id, item) for item in subnet_ids] + parent_candidates
            vnet_ids = vm_meta.get("vnet_ids")
            if isinstance(vnet_ids, list):
                parent_candidates = [(vm_acc_id, item) for item in vnet_ids] + parent_candidates

        for cand_acc, cand_ref in parent_candidates:
            parent_node_id = _lookup_infra_node(cand_acc, cand_ref)
            if parent_node_id:
                break

        if vm_node_id:
            _append_cloud_edge(vm_node_id, str(device_id), label="observed", relation="telemetry")
        elif parent_node_id:
            _append_cloud_edge(parent_node_id, str(device_id), label="attached", relation="membership")

    if cloud_hierarchy_nodes:
        nodes.extend(cloud_hierarchy_nodes)

    links = (
        db.query(Link)
        .options(
            load_only(
                Link.source_device_id,
                Link.target_device_id,
                Link.source_interface_name,
                Link.target_interface_name,
                Link.status,
                Link.protocol,
                Link.confidence,
                Link.discovery_source,
                Link.first_seen,
                Link.last_seen,
            )
        )
        .filter(Link.target_device_id.isnot(None))
        .all()
    )
    edges = []
    overlay_protocols = {"VXLAN", "EVPN", "NVE", "OVERLAY"}
    for l in links:
        src_port_raw = str(l.source_interface_name or "")
        dst_port_raw = str(l.target_interface_name or "")
        src_port = SnmpManager.normalize_interface_name(src_port_raw)
        dst_port = SnmpManager.normalize_interface_name(dst_port_raw)
        protocol = str(l.protocol or "LLDP").strip().upper() or "LLDP"
        overlay_detail = _build_overlay_link_detail(
            source_device=device_by_id.get(l.source_device_id),
            target_device=device_by_id.get(l.target_device_id),
            meta_by_id=meta_by_id,
            ip_candidates_by_device_id=ip_candidates_by_device_id,
        ) if protocol in overlay_protocols else None
        layer = "overlay" if protocol in overlay_protocols else ("l3" if protocol in {"OSPF", "BGP"} else "l2")
        l3_detail = _build_l3_link_detail(
            protocol=protocol,
            source_device=device_by_id.get(l.source_device_id),
            target_device=device_by_id.get(l.target_device_id),
            meta_by_id=meta_by_id,
            ip_candidates_by_device_id=ip_candidates_by_device_id,
            source_interface_name=src_port_raw,
            target_interface_name=dst_port_raw,
        )

        src_meta = meta_by_id.get(l.source_device_id, {}) if l.source_device_id else {}
        dst_meta = meta_by_id.get(l.target_device_id, {}) if l.target_device_id else {}
        src_if_state = src_meta.get("if_traffic_state", {}) if isinstance(src_meta, dict) else {}
        dst_if_state = dst_meta.get("if_traffic_state", {}) if isinstance(dst_meta, dict) else {}

        src_entry = src_if_state.get(src_port, {}) if isinstance(src_if_state, dict) and src_port else {}
        dst_entry = dst_if_state.get(dst_port, {}) if isinstance(dst_if_state, dict) and dst_port else {}

        src_in_bps = float(src_entry.get("in_bps", 0.0) or 0.0) if isinstance(src_entry, dict) else 0.0
        src_out_bps = float(src_entry.get("out_bps", 0.0) or 0.0) if isinstance(src_entry, dict) else 0.0
        dst_in_bps = float(dst_entry.get("in_bps", 0.0) or 0.0) if isinstance(dst_entry, dict) else 0.0
        dst_out_bps = float(dst_entry.get("out_bps", 0.0) or 0.0) if isinstance(dst_entry, dict) else 0.0

        fwd_bps = max(0.0, min(src_out_bps, dst_in_bps))
        rev_bps = max(0.0, min(dst_out_bps, src_in_bps))
        confidence = float(l.confidence or 0.0)
        age_sec = None
        if getattr(l, "last_seen", None):
            try:
                age_sec = max(0, int((now - l.last_seen.replace(tzinfo=None)).total_seconds()))
            except Exception:
                age_sec = None

        if confidence >= 0.9:
            quality = "high"
        elif confidence >= 0.7:
            quality = "medium"
        else:
            quality = "low"

        edges.append({
            "id": l.id,
            "source": str(l.source_device_id),
            "target": str(l.target_device_id),
            "src_port": src_port_raw,
            "dst_port": dst_port_raw,
            "label": _format_overlay_link_label(overlay_detail, src_port_raw, dst_port_raw) if layer == "overlay" else _format_l3_link_label(protocol, l3_detail, src_port_raw, dst_port_raw),
            "status": "active" if str(l.status) in ["up", "active"] else ("degraded" if str(l.status) == "degraded" else "down"),
            "protocol": protocol,
            "layer": layer,
            "confidence": confidence,
            "discovery_source": str(l.discovery_source or ""),
            "first_seen": l.first_seen.isoformat() if getattr(l, "first_seen", None) else None,
            "last_seen": l.last_seen.isoformat() if getattr(l, "last_seen", None) else None,
            "l3": l3_detail,
            "overlay": overlay_detail,
            "evidence": {
                "protocol": protocol,
                "discovery_source": str(l.discovery_source or ""),
                "confidence": confidence,
                "quality": quality,
                "is_stale": bool(age_sec is not None and age_sec > 86400),
                "age_seconds": age_sec,
                "layer": layer,
                "l3": l3_detail,
                "overlay": overlay_detail,
            },
            "traffic": {
                "src_in_bps": src_in_bps,
                "src_out_bps": src_out_bps,
                "dst_in_bps": dst_in_bps,
                "dst_out_bps": dst_out_bps,
                "fwd_bps": fwd_bps,
                "rev_bps": rev_bps,
                "ts": max(float(src_entry.get("ts", 0) or 0), float(dst_entry.get("ts", 0) or 0)) if isinstance(src_entry, dict) or isinstance(dst_entry, dict) else 0
            }
        })

    existing_overlay_pairs = {
        tuple(sorted([int(l.source_device_id), int(l.target_device_id)]))
        for l in links
        if l.source_device_id is not None and l.target_device_id is not None and str(l.protocol or "").strip().upper() in overlay_protocols
    }
    inferred_overlay_edges = _infer_overlay_edges(
        devices=devices,
        device_by_id=device_by_id,
        meta_by_id=meta_by_id,
        ip_candidates_by_device_id=ip_candidates_by_device_id,
    )
    for edge in inferred_overlay_edges:
        try:
            pair = tuple(sorted([int(edge.get("source")), int(edge.get("target"))]))
        except Exception:
            pair = None
        if pair and pair in existing_overlay_pairs:
            continue
        if pair:
            existing_overlay_pairs.add(pair)
        edges.append(edge)

    cutoff = now - timedelta(hours=24)
    endpoint_nodes = {}
    endpoint_edges = []

    def _is_private_mac(mac: str) -> bool:
        s = re.sub(r"[^0-9a-fA-F]", "", str(mac or ""))
        if len(s) < 2:
            return False
        try:
            first = int(s[0:2], 16)
        except Exception:
            return False
        return (first & 0x02) == 0x02
    atts = (
        db.query(
            EndpointAttachment.device_id,
            EndpointAttachment.interface_name,
            EndpointAttachment.last_seen,
            EndpointAttachment.vlan,
            Endpoint.id,
            Endpoint.mac_address,
            Endpoint.ip_address,
            Endpoint.hostname,
            Endpoint.vendor,
            Endpoint.endpoint_type,
            Endpoint.last_seen.label("ep_last_seen"),
        )
        .join(Endpoint, Endpoint.id == EndpointAttachment.endpoint_id)
        .filter(EndpointAttachment.last_seen >= cutoff)
        .all()
    )
    device_map = {d.id: d for d in devices}
    by_port = {}
    for (
        att_device_id,
        att_interface_name,
        att_last_seen,
        att_vlan,
        ep_id,
        ep_mac,
        ep_ip,
        ep_hostname,
        ep_vendor,
        ep_type,
        ep_last_seen,
    ) in atts:
        by_port.setdefault((att_device_id, att_interface_name), []).append(
            (att_device_id, att_interface_name, att_last_seen, att_vlan, ep_id, ep_mac, ep_ip, ep_hostname, ep_vendor, ep_type, ep_last_seen)
        )

    def _safe_port_id(port: str) -> str:
        return re.sub(r"[^a-zA-Z0-9]+", "_", str(port or "")).strip("_")

    for (device_id, interface_name), rows in by_port.items():
        dev = device_map.get(device_id)
        if not dev:
            continue

        if len(rows) > 1:
            group_id = f"epg-{device_id}-{_safe_port_id(interface_name)}"
            private_count = 0
            types = set()
            vendors = set()
            for _row in rows:
                _ep_mac = _row[5]
                _ep_vendor = _row[8]
                _ep_type = _row[9]
                if _is_private_mac(_ep_mac):
                    private_count += 1
                if _ep_type:
                    types.add(_ep_type)
                if _ep_vendor:
                    vendors.add(_ep_vendor)

            label = f"{interface_name} ({len(rows)} endpoints)"
            if private_count:
                label = f"{label} · {private_count} private"

            endpoint_nodes[group_id] = {
                "id": group_id,
                "label": label,
                "ip": interface_name,
                "type": "endpoint_group",
                "status": "online",
                "site_id": dev.site_id,
                "site_name": site_map.get(dev.site_id, "Default Site"),
                "tier": 3,
                "role": "endpoint_group",
                "metrics": {"health_score": 100},
                "device_id": device_id,
                "count": len(rows),
                "private_count": private_count,
                "endpoint_types": sorted(list(types)),
                "vendors": sorted(list(vendors)),
                "port": interface_name,
            }

            endpoint_edges.append(
                {
                    "source": str(device_id),
                    "target": group_id,
                    "src_port": interface_name,
                    "dst_port": "endpoints",
                    "label": f"{interface_name}<->endpoints",
                    "status": "active",
                }
            )
            continue

        (
            att_device_id,
            att_interface_name,
            att_last_seen,
            att_vlan,
            ep_id,
            ep_mac,
            ep_ip,
            ep_hostname,
            ep_vendor,
            ep_type,
            ep_last_seen,
        ) = rows[0]
        dev = device_map.get(att_device_id)
        if not dev:
            continue
        ep_node_id = f"ep-{ep_id}"
        if ep_node_id not in endpoint_nodes:
            private_mac = _is_private_mac(ep_mac)
            label = ep_hostname or ep_ip or ep_mac
            if private_mac:
                label = f"{label} (Private MAC)"
            status = "online" if ep_last_seen and ep_last_seen >= now - timedelta(minutes=30) else "offline"
            endpoint_nodes[ep_node_id] = {
                "id": ep_node_id,
                "label": label,
                "ip": ep_ip or ep_mac,
                "type": "endpoint",
                "status": status,
                "site_id": dev.site_id,
                "site_name": site_map.get(dev.site_id, "Default Site"),
                "tier": 3,
                "role": "endpoint",
                "metrics": {"health_score": 100},
                "private_mac": private_mac,
                "endpoint_type": ep_type,
                "vendor": ep_vendor,
            }

        endpoint_edges.append(
            {
                "source": str(att_device_id),
                "target": ep_node_id,
                "src_port": att_interface_name,
                "dst_port": ep_mac,
                "label": f"{att_interface_name}<->{ep_mac}",
                "status": "active",
            }
        )

    if cloud_hierarchy_edges:
        edges.extend(cloud_hierarchy_edges)

    nodes.extend(list(endpoint_nodes.values()))
    edges.extend(endpoint_edges)

    node_index: Dict[str, Dict[str, Any]] = {
        str(node.get("id")): node for node in nodes if node.get("id") is not None
    }
    hybrid_stats: Dict[str, Dict[str, Any]] = {}

    for node_id, node in node_index.items():
        cloud_meta = node.get("cloud") if isinstance(node.get("cloud"), dict) else {}
        provider = str(cloud_meta.get("provider") or "").strip().lower()
        account_id = _safe_int_value(cloud_meta.get("account_id"))
        account_name = str(cloud_meta.get("account_name") or "").strip()
        region = str(cloud_meta.get("region") or "").strip()
        hybrid_stats[node_id] = {
            "role": "cloud" if str(node.get("role") or "") == "cloud" else "onprem",
            "kind": cloud_meta.get("kind"),
            "hybrid_links": 0,
            "peer_links": 0,
            "inventory_links": 0,
            "providers": {provider} if provider else set(),
            "accounts": {str(account_id)} if account_id is not None else set(),
            "account_names": {account_name} if account_name else set(),
            "regions": {region} if region else set(),
        }

    for edge in edges:
        src = str(edge.get("source") or "").strip()
        dst = str(edge.get("target") or "").strip()
        src_node = node_index.get(src)
        dst_node = node_index.get(dst)
        if not src_node or not dst_node:
            continue

        src_cloud = str(src_node.get("role") or "") == "cloud"
        dst_cloud = str(dst_node.get("role") or "") == "cloud"
        protocol = str(edge.get("protocol") or "").strip().upper()
        layer = str(edge.get("layer") or "").strip().lower()

        if not (src_cloud or dst_cloud or protocol == "CLOUD" or layer == "hybrid"):
            continue

        src_cloud_meta = src_node.get("cloud") if src_cloud and isinstance(src_node.get("cloud"), dict) else {}
        dst_cloud_meta = dst_node.get("cloud") if dst_cloud and isinstance(dst_node.get("cloud"), dict) else {}
        cloud_meta = src_cloud_meta or dst_cloud_meta or {}
        is_inventory = protocol == "CLOUD" or layer == "hybrid"
        kind = "inventory" if is_inventory else "cloud_peer"
        if kind == "inventory":
            relationship = "cloud_to_cloud" if src_cloud and dst_cloud else "cloud_attachment"
        elif src_cloud and dst_cloud:
            relationship = "cloud_to_cloud"
        else:
            relationship = "cloud_to_onprem"

        peer_node = None
        if not (src_cloud and dst_cloud):
            peer_node = dst_node if src_cloud else (src_node if dst_cloud else None)

        hybrid_meta = {
            "kind": kind,
            "scope": "cloud_inventory" if kind == "inventory" else "hybrid_peer",
            "relationship": relationship,
            "cloud_node_id": src if src_cloud else (dst if dst_cloud else None),
            "peer_node_id": dst if src_cloud else (src if dst_cloud else None),
            "provider": cloud_meta.get("provider"),
            "account_id": _safe_int_value(cloud_meta.get("account_id")),
            "account_name": cloud_meta.get("account_name"),
            "region": cloud_meta.get("region"),
            "resource_type": cloud_meta.get("resource_type"),
            "resource_type_label": cloud_meta.get("resource_type_label"),
            "resource_id": cloud_meta.get("resource_id"),
            "resource_name": cloud_meta.get("resource_name"),
            "cloud_kind": cloud_meta.get("kind"),
            "source": cloud_meta.get("source"),
            "peer_label": peer_node.get("label") if isinstance(peer_node, dict) else None,
            "peer_role": peer_node.get("role") if isinstance(peer_node, dict) else None,
        }
        edge["hybrid"] = hybrid_meta
        if kind == "inventory":
            edge["layer"] = "hybrid"

        evidence = edge.get("evidence")
        if isinstance(evidence, dict):
            evidence["hybrid"] = hybrid_meta
            if kind == "inventory":
                evidence["layer"] = "hybrid"

        for node_id in {src, dst}:
            stat = hybrid_stats.get(node_id)
            if stat is None:
                continue
            stat["hybrid_links"] += 1
            if kind == "inventory":
                stat["inventory_links"] += 1
            else:
                stat["peer_links"] += 1
            provider = str(hybrid_meta.get("provider") or "").strip().lower()
            account_id = hybrid_meta.get("account_id")
            account_name = str(hybrid_meta.get("account_name") or "").strip()
            region = str(hybrid_meta.get("region") or "").strip()
            if provider:
                stat["providers"].add(provider)
            if account_id is not None:
                stat["accounts"].add(str(account_id))
            if account_name:
                stat["account_names"].add(account_name)
            if region:
                stat["regions"].add(region)

    for node_id, node in node_index.items():
        stat = hybrid_stats.get(node_id) or {}
        node["hybrid"] = {
            "role": stat.get("role") or ("cloud" if str(node.get("role") or "") == "cloud" else "onprem"),
            "kind": stat.get("kind"),
            "connected": bool(stat.get("hybrid_links")),
            "hybrid_links": int(stat.get("hybrid_links") or 0),
            "peer_links": int(stat.get("peer_links") or 0),
            "inventory_links": int(stat.get("inventory_links") or 0),
            "providers": sorted(list(stat.get("providers") or [])),
            "accounts": sorted(list(stat.get("accounts") or [])),
            "account_names": sorted(list(stat.get("account_names") or [])),
            "regions": sorted(list(stat.get("regions") or [])),
        }

    return {"nodes": nodes, "links": edges}


@router.get("/topology/endpoint-group")
def get_endpoint_group_details(
    device_id: int,
    port: str,
    hours: int = 24,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    from datetime import datetime, timedelta
    from app.models.endpoint import Endpoint, EndpointAttachment
    import re

    def _is_private_mac(mac: str) -> bool:
        s = re.sub(r"[^0-9a-fA-F]", "", str(mac or ""))
        if len(s) < 2:
            return False
        try:
            first = int(s[0:2], 16)
        except Exception:
            return False
        return (first & 0x02) == 0x02

    cutoff = datetime.now() - timedelta(hours=max(1, min(int(hours or 24), 168)))
    rows = (
        db.query(EndpointAttachment, Endpoint)
        .join(Endpoint, Endpoint.id == EndpointAttachment.endpoint_id)
        .filter(EndpointAttachment.device_id == device_id)
        .filter(EndpointAttachment.interface_name == port)
        .filter(EndpointAttachment.last_seen >= cutoff)
        .order_by(EndpointAttachment.last_seen.desc())
        .all()
    )

    items = []
    for att, ep in rows:
        items.append(
            {
                "endpoint_id": ep.id,
                "mac_address": ep.mac_address,
                "ip_address": ep.ip_address,
                "hostname": ep.hostname,
                "vendor": ep.vendor,
                "endpoint_type": ep.endpoint_type,
                "private_mac": _is_private_mac(ep.mac_address),
                "vlan": att.vlan,
                "last_seen": att.last_seen.isoformat() if getattr(att, "last_seen", None) else None,
            }
        )

    return {"device_id": device_id, "port": port, "count": len(items), "endpoints": items}


@router.get("/topology/trace")
def trace_path(source_id: int, target_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    links = db.query(Link).all()
    graph = {}
    for l in links:
        if not l.source_device_id or not l.target_device_id: continue
        graph.setdefault(l.source_device_id, []).append(l.target_device_id)
        graph.setdefault(l.target_device_id, []).append(l.source_device_id)

    queue = [[source_id]];
    visited = {source_id};
    found_path = []
    while queue:
        path = queue.pop(0);
        node = path[-1]
        if node == target_id: found_path = path; break
        if node in graph:
            for neighbor in graph[node]:
                if neighbor not in visited: visited.add(neighbor); new_path = list(path); new_path.append(
                    neighbor); queue.append(new_path)

    if not found_path: return {"status": "failed", "message": "No path found", "path_nodes": [], "path_links": []}

    highlight_links = []
    for i in range(len(found_path) - 1):
        src = found_path[i];
        dst = found_path[i + 1]
        link_obj = db.query(Link).filter(((Link.source_device_id == src) & (Link.target_device_id == dst)) | (
                (Link.source_device_id == dst) & (Link.target_device_id == src))).first()
        if link_obj: highlight_links.append(
            {"source": str(src), "target": str(dst), "status": link_obj.status, "speed": link_obj.link_speed})

    return {"status": "success", "path_nodes": [str(n) for n in found_path], "path_links": highlight_links}


# --------------------------------------------------------------------------
# [Action] 장비 동기화 (Sync)
# --------------------------------------------------------------------------
@router.post("/{device_id}/sync")
def sync_device(
        device_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(deps.require_operator)
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(404, "Device not found")
    try:
        PreviewManagedNodeService.assert_managed_for_feature(db, device, feature="device sync")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=exc.args[0] if exc.args else {"message": "Managed node required"})
    if not DeviceSupportPolicyService.is_feature_allowed(db, device=device, feature="sync"):
        return {"status": "skipped", "message": "vendor_support_policy_blocked"}
    if not CapabilityProfileService.allow_auto_action(db, device, "sync"):
        return {"status": "skipped", "message": "capability_policy_blocked"}
    result = DeviceSyncService.sync_device(db, device_id)
    if result.get("status") == "not_found":
        raise HTTPException(404, "Device not found")
    return result


# --------------------------------------------------------------------------
# [Action] VLAN 배포
# --------------------------------------------------------------------------
@router.post("/Netsphere_Free_Deploy/vlan")
def deploy_vlan_bulk(req: VlanDeployRequest, db: Session = Depends(get_db),
                     current_user: User = Depends(deps.require_network_admin)):
    target_devices = db.query(Device).filter(Device.id.in_(list(req.device_ids or []))).all()
    blocked = DeviceSupportPolicyService.collect_blocked_devices(db, devices=target_devices, feature="config")
    if blocked:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEVICE_SUPPORT_BLOCKED",
                "message": "VLAN deploy blocked for unsupported devices.",
                "details": {"feature": "config", "blocked_devices": blocked},
            },
        )

    from app.tasks.config import deploy_vlan_bulk_task

    try:
        r = deploy_vlan_bulk_task.apply_async(
            args=[req.device_ids, req.vlan_id, req.vlan_name],
            queue="ssh",
        )
        return {"job_id": r.id, "status": "queued"}
    except Exception:
        from app.services.ssh_service import DeviceConnection, DeviceInfo

        vlan_template = "vlan {{ vlan_id }}\n name {{ vlan_name }}\nexit"
        summary = []
        
        # [Optimized] Bulk fetch devices
        devices = db.query(Device).filter(Device.id.in_(req.device_ids)).all()
        device_map = {d.id: d for d in devices}
        
        for d_id in req.device_ids:
            dev = device_map.get(d_id)
            if not dev:
                summary.append({"id": d_id, "name": None, "status": "not_found"})
                continue
            conn = DeviceConnection(
                DeviceInfo(
                    host=dev.ip_address,
                    username=dev.ssh_username,
                    password=dev.ssh_password,
                    secret=dev.enable_password,
                    port=getattr(dev, "ssh_port", 22) or 22,
                    device_type=dev.device_type or "cisco_ios",
                )
            )
            if conn.connect():
                res = conn.deploy_config_template(vlan_template, req.model_dump())
                summary.append({"id": d_id, "name": dev.name, "status": "success" if res.get("success") else "failed"})
                conn.disconnect()
            else:
                summary.append({"id": d_id, "name": dev.name, "status": "failed"})
        return {"job_id": None, "status": "executed", "result": {"summary": summary}}


# --------------------------------------------------------------------------
# CRUD 엔드포인트
# --------------------------------------------------------------------------
@router.get("/", response_model=List[DeviceResponse])
def read_devices(
    skip: int = 0, 
    limit: int = 100, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer)
):
    """Return the current device inventory."""
    devices = db.query(Device).offset(skip).limit(limit).all()

    out = []
    for d in devices:
        d.status = str(d.status or "offline").lower()
        out.append(_serialize_device_payload(d, DeviceResponse, db))
    return out


@router.get("/managed-summary")
def get_managed_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_viewer),
):
    PreviewManagedNodeService.reconcile_managed_devices(db)
    return PreviewManagedNodeService.summarize(db)


@router.post("/{device_id}/manage")
def promote_device_to_managed(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(404, "Device not found")
    try:
        summary = PreviewManagedNodeService.promote_device_to_managed(db, device)
    except ValueError:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "MANAGED_NODE_LIMIT_REACHED",
                "message": "NetSphere Free manages up to 50 nodes.",
                "details": PreviewManagedNodeService.summarize(db),
            },
        )
    SourceOfTruthService.record_event(
        db,
        asset_kind="device",
        asset_key=f"device:{int(device.id)}",
        asset_name=str(device.name or ""),
        action="management_promoted",
        summary=f"Device '{device.name}' was promoted to managed monitoring.",
        actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
        actor_role=str(current_user.role or "").strip() or None,
        details={"device_id": int(device.id), "management_state": str(device.management_state or "managed")},
    )
    return {"device": _serialize_device_payload(device, DeviceResponse, db), "summary": summary}


@router.post("/{device_id}/release-management")
def release_device_management(
    device_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin),
):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(404, "Device not found")
    summary = PreviewManagedNodeService.release_managed_slot(db, device)
    SourceOfTruthService.record_event(
        db,
        asset_kind="device",
        asset_key=f"device:{int(device.id)}",
        asset_name=str(device.name or ""),
        action="management_released",
        summary=f"Device '{device.name}' was moved to discovered-only monitoring.",
        actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
        actor_role=str(current_user.role or "").strip() or None,
        details={"device_id": int(device.id), "management_state": str(device.management_state or "discovered_only")},
    )
    return {"device": _serialize_device_payload(device, DeviceResponse, db), "summary": summary}


@router.get("/{device_id}", response_model=DeviceDetailResponse)
def read_device_detail(device_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(deps.require_viewer)):
    PreviewManagedNodeService.reconcile_managed_devices(db)
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device: raise HTTPException(404, "Device not found")
    device.status = str(device.status or "offline").lower()
    return _serialize_device_payload(device, DeviceDetailResponse, db)


@router.get("/{device_id}/inventory")
def read_device_inventory(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(404, "Device not found")
    items = (
        db.query(DeviceInventoryItem)
        .filter(DeviceInventoryItem.device_id == device_id)
        .order_by(DeviceInventoryItem.class_id.asc().nulls_last(), DeviceInventoryItem.ent_physical_index.asc())
        .all()
    )
    return [
        {
            "ent_physical_index": i.ent_physical_index,
            "parent_index": i.parent_index,
            "class_id": i.class_id,
            "class_name": i.class_name,
            "name": i.name,
            "description": i.description,
            "model_name": i.model_name,
            "serial_number": i.serial_number,
            "mfg_name": i.mfg_name,
            "hardware_rev": i.hardware_rev,
            "firmware_rev": i.firmware_rev,
            "software_rev": i.software_rev,
            "is_fru": i.is_fru,
            "last_seen": i.last_seen.isoformat() if i.last_seen else None,
        }
        for i in items
    ]


@router.get("/{device_id}/inventory/export")
def export_device_inventory(device_id: int, format: str = Query("xlsx"), db: Session = Depends(get_db), current_user: User = Depends(deps.require_viewer)):
    import io

    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(404, "Device not found")
    if format not in {"xlsx", "pdf"}:
        raise HTTPException(400, "Invalid format")

    items = (
        db.query(DeviceInventoryItem)
        .filter(DeviceInventoryItem.device_id == device_id)
        .order_by(DeviceInventoryItem.class_id.asc().nulls_last(), DeviceInventoryItem.ent_physical_index.asc())
        .all()
    )

    from app.services.report_export_service import build_inventory_xlsx, build_inventory_pdf

    if format == "pdf":
        data = build_inventory_pdf(device.name, items)
        media = "application/pdf"
        filename = f"inventory_{device.id}.pdf"
    else:
        data = build_inventory_xlsx(device.name, items)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"inventory_{device.id}.xlsx"

    return StreamingResponse(
        io.BytesIO(data),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/", response_model=DeviceResponse)
def create_device(
    device_in: DeviceCreate, 
    background_tasks: BackgroundTasks, 
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_network_admin)
):
    try:
        LicensePolicyService.assert_can_add_devices(
            db,
            source="manual_device_create",
        )
    except LicensePolicyViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc))


    if db.query(Device).filter(Device.name == device_in.name).first(): raise HTTPException(400, "Exists")
    
    # Exclude non-model fields
    data = device_in.model_dump(exclude={'auto_provision_template_id'})
    def _get_setting_value(key: str) -> str:
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        return setting.value if setting and setting.value and setting.value != "********" else ""

    default_ssh_password = _get_setting_value("default_ssh_password")
    default_ssh_username = _get_setting_value("default_ssh_username")
    default_enable_password = _get_setting_value("default_enable_password")
    default_snmp_community = _get_setting_value("default_snmp_community")

    if data.get("ssh_username") in (None, "", "admin") and default_ssh_username:
        data["ssh_username"] = default_ssh_username
    if data.get("ssh_password") in (None, "") and default_ssh_password:
        data["ssh_password"] = default_ssh_password
    if data.get("enable_password") in (None, "") and default_enable_password:
        data["enable_password"] = default_enable_password
    if (not data.get("snmp_community") or data.get("snmp_community") == "public") and default_snmp_community:
        data["snmp_community"] = default_snmp_community

    support = DeviceSupportPolicyService.evaluate_metadata(
        db,
        device_type=str(data.get("device_type") or ""),
        os_version=str(data.get("os_version") or ""),
        model=str(data.get("model") or ""),
        site_id=data.get("site_id"),
        hostname=str(data.get("hostname") or data.get("name") or ""),
    )
    if not bool((support.get("features") or {}).get("discovery", True)):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DEVICE_SUPPORT_BLOCKED",
                "message": "Manual device onboarding is blocked for this vendor tier.",
                "details": {
                    "feature": "discovery",
                    "device_name": str(data.get("name") or ""),
                    "device_type": str(data.get("device_type") or ""),
                    "tier": support.get("tier"),
                    "fallback_mode": support.get("fallback_mode"),
                    "reasons": list(support.get("reasons") or []),
                },
            },
        )
    variables = dict(data.get("variables") or {})
    variables["support_policy"] = {
        "tier": support.get("tier"),
        "fallback_mode": support.get("fallback_mode"),
        "features": support.get("features"),
        "reasons": support.get("reasons"),
    }
    data["variables"] = variables

    new_device = Device(**data, status="unknown", owner_id=current_user.id)
    db.add(new_device);
    db.commit();
    PreviewManagedNodeService.reconcile_managed_devices(db)
    MonitoringProfileService.ensure_assignment(db, new_device, commit=True)
    db.refresh(new_device)
    
    # Auto Provision
    if device_in.auto_provision_template_id:
        background_tasks.add_task(run_auto_provision, new_device.id, device_in.auto_provision_template_id)

    if DeviceSupportPolicyService.is_feature_allowed(db, device=new_device, feature="sync") and CapabilityProfileService.allow_auto_action(db, new_device, "sync"):
        from app.tasks.device_sync import dispatch_device_sync
        dispatch_device_sync(
            new_device.id,
            idempotency_key=f"device-create:{new_device.id}",
        )
    try:
        from app.tasks.monitoring import burst_monitor_devices, monitor_all_devices
        burst_monitor_devices.delay([new_device.id], 3, 5)
        monitor_all_devices.delay()
    except Exception:
        pass
    
    # [Audit]
    AuditService.log(db, current_user, "CREATE", "Device", new_device.name, details=f"Created device {new_device.name} ({new_device.ip_address})")
    
    return _serialize_device_payload(new_device, DeviceResponse, db)


@router.put("/{device_id}", response_model=DeviceResponse)
def update_device(device_id: int, device_in: DeviceUpdate, db: Session = Depends(get_db),
                  current_user: User = Depends(deps.require_network_admin)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device: raise HTTPException(404, "Device not found")
    for k, v in device_in.model_dump(exclude_unset=True).items():
        if k in {"ssh_password", "enable_password", "snmp_v3_auth_key", "snmp_v3_priv_key"} and v == "********":
            continue
        setattr(device, k, v)

    support = DeviceSupportPolicyService.evaluate_device(db, device)
    variables = dict(getattr(device, "variables", None) or {})
    variables["support_policy"] = {
        "tier": support.get("tier"),
        "fallback_mode": support.get("fallback_mode"),
        "features": support.get("features"),
        "reasons": support.get("reasons"),
    }
    device.variables = variables
    db.add(device);
    db.commit();
    MonitoringProfileService.ensure_assignment(db, device, commit=True)
    db.refresh(device)
    
    # [Audit]
    AuditService.log(db, current_user, "UPDATE", "Device", device.name, details=f"Updated properties for device {device.name}")
    
    return _serialize_device_payload(device, DeviceResponse, db)


@router.delete("/{device_id}")
def delete_device(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(deps.require_network_admin)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device: raise HTTPException(404, "Device not found")
    
    dev_name = device.name
    db.delete(device)
    db.commit()
    
    # [Audit]
    AuditService.log(db, current_user, "DELETE", "Device", dev_name, details=f"Deleted device {dev_name}")
    
    return {"message": "Deleted"}
