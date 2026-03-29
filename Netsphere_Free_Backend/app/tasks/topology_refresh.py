try:
    from celery import shared_task
except ModuleNotFoundError:
    def shared_task(*args, **kwargs):
        def decorator(fn):
            return fn
        if args and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

from app.db.session import SessionLocal
from app.models.device import Device, Link
from app.models.discovery import DiscoveredDevice, DiscoveryJob
from app.models.topology_candidate import TopologyNeighborCandidate
from app.models.settings import SystemSetting
from app.services.ssh_service import DeviceConnection, DeviceInfo
from app.services.topology_link_service import TopologyLinkService
from app.services.topology_snapshot_policy_service import TopologySnapshotPolicyService
from app.services.topology_event_service import publish_topology_event
from app.services.snmp_service import SnmpManager
from app.services.snmp_l2_service import SnmpL2Service
from sqlalchemy.sql import func
import ipaddress


def _get_setting_value(db, key: str) -> str:
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not s or not s.value or s.value == "********":
        return ""
    return str(s.value)


def _parse_cidr_list(raw: str) -> list[str]:
    out = []
    for part in (raw or "").replace("\n", ",").split(","):
        s = part.strip()
        if s:
            out.append(s)
    return out


def _build_scope_checker(db):
    include_nets = []
    exclude_nets = []
    for c in _parse_cidr_list(_get_setting_value(db, "discovery_scope_include_cidrs")):
        try:
            include_nets.append(ipaddress.ip_network(str(c).strip(), strict=False))
        except Exception:
            continue
    for c in _parse_cidr_list(_get_setting_value(db, "discovery_scope_exclude_cidrs")):
        try:
            exclude_nets.append(ipaddress.ip_network(str(c).strip(), strict=False))
        except Exception:
            continue

    def _is_allowed(ip_s: str) -> bool:
        try:
            ip_obj = ipaddress.ip_address(str(ip_s).strip())
        except Exception:
            return False
        if ip_obj.is_loopback or ip_obj.is_multicast or ip_obj.is_unspecified or ip_obj.is_link_local:
            return False
        if any(ip_obj in n for n in exclude_nets):
            return False
        if include_nets and not any(ip_obj in n for n in include_nets):
            return False
        return True

    return _is_allowed


@shared_task(name="app.tasks.topology_refresh.refresh_device_topology")
def refresh_device_topology(device_id: int, discovery_job_id: int = None, max_depth: int = 2):
    db = SessionLocal()
    try:
        try:
            is_allowed = _build_scope_checker(db)
        except Exception:
            is_allowed = lambda _ip: True
        if max_depth is None or int(max_depth) < 1:
            max_depth = 1

        job = None
        if discovery_job_id:
            job = db.query(DiscoveryJob).filter(DiscoveryJob.id == discovery_job_id).first()

        try:
            low_conf_threshold = float(_get_setting_value(db, "topology_candidate_low_confidence_threshold") or 0.7)
        except Exception:
            low_conf_threshold = 0.7
        if low_conf_threshold < 0:
            low_conf_threshold = 0.0
        if low_conf_threshold > 1:
            low_conf_threshold = 1.0

        visited = set()
        queue = [(device_id, int(max_depth))]

        total_neighbors = 0
        created_candidates = 0
        created_discovered = 0
        updated_links = 0

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited:
                continue
            visited.add(current_id)

            device = db.query(Device).filter(Device.id == current_id).first()
            if not device:
                continue
            neighbors = []

            if device.ssh_password:
                dev_info = DeviceInfo(
                    host=device.ip_address,
                    username=device.ssh_username or "admin",
                    password=device.ssh_password,
                    secret=device.enable_password,
                    port=int(device.ssh_port or 22),
                    device_type=device.device_type or "cisco_ios",
                )

                conn = DeviceConnection(dev_info)
                if conn.connect():
                    try:
                        neighbors = conn.get_neighbors() or []
                    finally:
                        conn.disconnect()

            if (getattr(device, "snmp_version", None) or "v2c").lower() in ("v3", "3") or device.snmp_community:
                snmp = SnmpManager(
                    device.ip_address,
                    device.snmp_community,
                    port=int(getattr(device, "snmp_port", None) or 161),
                    version=(getattr(device, "snmp_version", None) or "v2c"),
                    v3_username=getattr(device, "snmp_v3_username", None),
                    v3_security_level=getattr(device, "snmp_v3_security_level", None),
                    v3_auth_proto=getattr(device, "snmp_v3_auth_proto", None),
                    v3_auth_key=getattr(device, "snmp_v3_auth_key", None),
                    v3_priv_proto=getattr(device, "snmp_v3_priv_proto", None),
                    v3_priv_key=getattr(device, "snmp_v3_priv_key", None),
                )
                snmp_neighbors = SnmpL2Service.get_lldp_neighbors(snmp) or []
                if snmp_neighbors:
                    seen = set()
                    merged = []
                    for n in (neighbors or []) + snmp_neighbors:
                        key = (
                            (n.get("protocol") or "").strip(),
                            (n.get("local_interface") or "").strip(),
                            (n.get("remote_interface") or "").strip(),
                            (n.get("neighbor_name") or "").strip(),
                            (n.get("mgmt_ip") or "").strip(),
                        )
                        if key in seen:
                            continue
                        seen.add(key)
                        merged.append(n)
                    neighbors = merged

                try:
                    arp = SnmpL2Service.get_arp_table(snmp) or []
                    arp_mac_to_ip = {str(r.get("mac") or "").strip().lower(): str(r.get("ip") or "").strip() for r in arp if r.get("mac") and r.get("ip")}
                    fdb = (SnmpL2Service.get_qbridge_mac_table(snmp) or []) + (SnmpL2Service.get_bridge_mac_table(snmp) or [])
                    if fdb:
                        all_devices = db.query(Device).all()
                        ip_to_dev = {str(d.ip_address or "").strip(): d for d in all_devices if getattr(d, "ip_address", None)}
                        mac_to_dev = {}
                        for d in all_devices:
                            m0 = str(getattr(d, "mac_address", "") or "").strip().lower()
                            if m0:
                                mac_to_dev[m0] = d
                            lp = getattr(d, "latest_parsed_data", None)
                            if isinstance(lp, dict):
                                aliases = lp.get("mac_aliases")
                                if isinstance(aliases, list):
                                    for m in aliases:
                                        mm = str(m or "").strip().lower()
                                        if mm:
                                            mac_to_dev[mm] = d
                        for row in fdb:
                            mac = str(row.get("mac") or "").strip().lower()
                            port = str(row.get("port") or "").strip()
                            if not mac or not port:
                                continue
                            ip2 = arp_mac_to_ip.get(mac)
                            d2 = ip_to_dev.get(ip2) if ip2 else None
                            if not d2:
                                d2 = mac_to_dev.get(mac)
                            if not d2 or not getattr(d2, "ip_address", None) or d2.id == device.id:
                                continue
                            ip2 = str(d2.ip_address or "").strip()
                            neighbors.append(
                                {
                                    "local_interface": port,
                                    "remote_interface": "UNKNOWN",
                                    "neighbor_name": d2.hostname or d2.name or ip2,
                                    "mgmt_ip": ip2,
                                    "protocol": "FDB",
                                    "discovery_source": str(row.get("discovery_source") or "snmp_fdb"),
                                }
                            )
                except Exception:
                    pass

            total_neighbors += len(neighbors)

            link_stats = TopologyLinkService.refresh_links_for_device(db, device, neighbors)
            updated_links += int(link_stats.get("created", 0)) + int(link_stats.get("updated", 0))

            if (getattr(device, "snmp_version", None) or "v2c").lower() in ("v3", "3") or device.snmp_community:
                name_status = SnmpManager(
                    device.ip_address,
                    device.snmp_community,
                    port=int(getattr(device, "snmp_port", None) or 161),
                    version=(getattr(device, "snmp_version", None) or "v2c"),
                    v3_username=getattr(device, "snmp_v3_username", None),
                    v3_security_level=getattr(device, "snmp_v3_security_level", None),
                    v3_auth_proto=getattr(device, "snmp_v3_auth_proto", None),
                    v3_auth_key=getattr(device, "snmp_v3_auth_key", None),
                    v3_priv_proto=getattr(device, "snmp_v3_priv_proto", None),
                    v3_priv_key=getattr(device, "snmp_v3_priv_key", None),
                ).get_interface_name_status_map()
                if name_status:
                    normalized = {str(k).strip().lower().replace(" ", ""): v for k, v in name_status.items()}
                    links = db.query(Link).filter(
                        (Link.source_device_id == device.id) | (Link.target_device_id == device.id)
                    ).all()
                    for l in links:
                        if l.status == "inactive":
                            continue
                        intf = l.source_interface_name if l.source_device_id == device.id else l.target_interface_name
                        key = (intf or "").strip().lower().replace(" ", "")
                        st = normalized.get(key)
                        if st == "down":
                            l.status = "down"

            db.commit()

            for n in neighbors:
                neighbor_name = (n.get("neighbor_name") or "").strip()
                mgmt_ip = (n.get("mgmt_ip") or "").strip()
                local_interface = (n.get("local_interface") or "").strip()
                remote_interface = (n.get("remote_interface") or "").strip()
                protocol = (n.get("protocol") or "UNKNOWN").strip() or "UNKNOWN"

                if mgmt_ip and not is_allowed(mgmt_ip):
                    continue

                target, confidence, reason = TopologyLinkService._match_target_device(db, neighbor_name, mgmt_ip)

                def _upsert_candidate(status_value: str):
                    nonlocal created_candidates
                    n_name = (neighbor_name or "Unknown").strip()
                    n_ip = (mgmt_ip or None)
                    n_local = (local_interface or None)
                    n_remote = (remote_interface or None)
                    existing_candidate = db.query(TopologyNeighborCandidate).filter(
                        TopologyNeighborCandidate.source_device_id == device.id,
                        func.lower(TopologyNeighborCandidate.neighbor_name) == n_name.lower(),
                        TopologyNeighborCandidate.mgmt_ip == n_ip,
                        func.lower(func.coalesce(TopologyNeighborCandidate.local_interface, "")) == str(n_local or "").lower(),
                        func.lower(func.coalesce(TopologyNeighborCandidate.remote_interface, "")) == str(n_remote or "").lower(),
                    ).first()

                    if existing_candidate:
                        existing_candidate.last_seen = func.now()
                        existing_candidate.protocol = protocol
                        existing_candidate.confidence = max(float(existing_candidate.confidence or 0.0), float(confidence or 0.0))
                        existing_candidate.reason = reason
                        if existing_candidate.status not in ("promoted", "ignored"):
                            existing_candidate.status = status_value
                    else:
                        cand = TopologyNeighborCandidate(
                            discovery_job_id=(job.id if job else None),
                            source_device_id=device.id,
                            neighbor_name=n_name,
                            mgmt_ip=n_ip,
                            local_interface=n_local,
                            remote_interface=n_remote,
                            protocol=protocol,
                            confidence=confidence,
                            reason=reason,
                            status=status_value,
                        )
                        db.add(cand)
                        created_candidates += 1
                    db.commit()

                if target:
                    if float(confidence or 0.0) < low_conf_threshold:
                        _upsert_candidate("low_confidence")
                    if depth > 1:
                        queue.append((target.id, depth - 1))
                    continue

                if not target and job and mgmt_ip:
                    existing = db.query(DiscoveredDevice).filter(
                        DiscoveredDevice.job_id == job.id,
                        DiscoveredDevice.ip_address == mgmt_ip,
                    ).first()
                    if not existing:
                        discovered = DiscoveredDevice(
                            job_id=job.id,
                            ip_address=mgmt_ip,
                            hostname=neighbor_name or mgmt_ip,
                            vendor="Unknown",
                            model=None,
                            os_version=None,
                            snmp_status="unknown",
                            status="new",
                            matched_device_id=None,
                        )
                        db.add(discovered)
                        created_discovered += 1
                        db.commit()

                reason_s = str(reason or "").strip().lower()
                if reason_s.startswith("ambiguous_"):
                    _upsert_candidate("low_confidence")
                else:
                    _upsert_candidate("unmatched")

        try:
            auto_on_refresh = _get_setting_value(db, "topology_snapshot_auto_on_topology_refresh").strip().lower() in {"1", "true", "yes", "y", "on"}
        except Exception:
            auto_on_refresh = False

        if auto_on_refresh:
            try:
                root = db.query(Device).filter(Device.id == device_id).first()
                site_id = getattr(job, "site_id", None) if job else getattr(root, "site_id", None) if root else None
                TopologySnapshotPolicyService.maybe_create_snapshot(
                    db,
                    site_id=site_id,
                    job_id=(job.id if job else None),
                    trigger="topology_refresh",
                )
            except Exception:
                pass

        try:
            root = db.query(Device).filter(Device.id == device_id).first()
            site_id = getattr(job, "site_id", None) if job else getattr(root, "site_id", None) if root else None
            publish_topology_event(
                db,
                "topology_refresh",
                {
                    "device_id": int(device_id),
                    "site_id": site_id,
                    "source": "topology_refresh_task",
                    "scope": "device_topology",
                    "devices_visited": int(len(visited)),
                    "neighbors_seen": int(total_neighbors),
                    "links_touched": int(updated_links),
                    "discovered_created": int(created_discovered),
                    "candidates_created": int(created_candidates),
                    "topology_changed": bool(updated_links > 0),
                    "candidate_summary_changed": bool(created_candidates > 0),
                    "refresh_hint": "topology",
                },
                site_id=site_id,
                device_id=int(device_id),
                persist=True,
                realtime=True,
            )
            if created_candidates > 0 or created_discovered > 0:
                publish_topology_event(
                    db,
                    "topology_candidate_update",
                    {
                        "device_id": int(device_id),
                        "site_id": site_id,
                        "source": "topology_refresh_task",
                        "created_candidates": int(created_candidates),
                        "created_discovered": int(created_discovered),
                        "refresh_hint": "candidates",
                    },
                    site_id=site_id,
                    device_id=int(device_id),
                    persist=True,
                    realtime=True,
                )
            db.commit()
        except Exception:
            db.rollback()

        return {
            "status": "ok",
            "devices_visited": len(visited),
            "neighbors_seen": total_neighbors,
            "links_touched": updated_links,
            "discovered_created": created_discovered,
            "candidates_created": created_candidates,
        }
    finally:
        db.close()
