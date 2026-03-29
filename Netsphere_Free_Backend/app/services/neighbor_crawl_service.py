from __future__ import annotations

import time
import re
import socket
import ipaddress
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.credentials import SnmpCredentialProfile
from app.models.device import Site
from app.models.settings import SystemSetting
from app.services.discovery_service import DiscoveryService
from app.services.discovery_hint_cache_service import DiscoveryHintCacheService
from app.services.snmp_l2_service import SnmpL2Service
from app.services.snmp_service import SnmpManager
from app.services.ssh_service import DeviceConnection, DeviceInfo


class NeighborCrawlService:
    def __init__(self, db: Session):
        self.db = db
        self.discovery = DiscoveryService(db)

    def _snmp_from_profile(self, ip: str, profile: Dict[str, Any]) -> SnmpManager:
        version = str(profile.get("version") or "v2c")
        port = int(profile.get("port") or 161)
        return SnmpManager(
            ip,
            community=str(profile.get("community") or "public"),
            port=port,
            version=version,
            v3_username=profile.get("v3_username"),
            v3_security_level=profile.get("v3_security_level"),
            v3_auth_proto=profile.get("v3_auth_proto"),
            v3_auth_key=profile.get("v3_auth_key"),
            v3_priv_proto=profile.get("v3_priv_proto"),
            v3_priv_key=profile.get("v3_priv_key"),
        )

    def _snmp_for_device(self, device: Optional[Device], profile: Dict[str, Any], ip_fallback: str) -> SnmpManager:
        ip = str(getattr(device, "ip_address", None) or ip_fallback)
        version = str(getattr(device, "snmp_version", None) or profile.get("version") or "v2c")
        port = int(getattr(device, "snmp_port", None) or profile.get("port") or 161)
        return SnmpManager(
            ip,
            community=str(getattr(device, "snmp_community", None) or profile.get("community") or "public"),
            port=port,
            version=version,
            v3_username=getattr(device, "snmp_v3_username", None) or profile.get("v3_username"),
            v3_security_level=getattr(device, "snmp_v3_security_level", None) or profile.get("v3_security_level"),
            v3_auth_proto=getattr(device, "snmp_v3_auth_proto", None) or profile.get("v3_auth_proto"),
            v3_auth_key=getattr(device, "snmp_v3_auth_key", None) or profile.get("v3_auth_key"),
            v3_priv_proto=getattr(device, "snmp_v3_priv_proto", None) or profile.get("v3_priv_proto"),
            v3_priv_key=getattr(device, "snmp_v3_priv_key", None) or profile.get("v3_priv_key"),
        )

    def _collect_seed_context(self, device: Optional[Device], ip: str, profile: Dict[str, Any]) -> Dict[str, Any]:
        snmp = self._snmp_for_device(device, profile, ip_fallback=ip)
        lldp_rows = SnmpL2Service.get_lldp_neighbors(snmp) or []
        cdp_rows = SnmpL2Service.get_cdp_neighbors(snmp) or []
        arp_rows = SnmpL2Service.get_arp_table(snmp) or []
        fdb_rows = (SnmpL2Service.get_qbridge_mac_table(snmp) or []) + (SnmpL2Service.get_bridge_mac_table(snmp) or [])
        recorded = DiscoveryHintCacheService.record_seed_snapshot(
            seed_device_id=(int(device.id) if device and getattr(device, "id", None) is not None else None),
            seed_ip=ip,
            seed_vendor=((getattr(device, "vendor", None) or getattr(device, "name", None)) if device else None),
            arp_rows=arp_rows,
            lldp_rows=lldp_rows + cdp_rows,
            fdb_rows=fdb_rows,
        )
        return {
            "lldp_rows": lldp_rows,
            "cdp_rows": cdp_rows,
            "arp_rows": arp_rows,
            "fdb_rows": fdb_rows,
            "recorded": int(recorded),
        }

    def _get_neighbors(self, device: Optional[Device], ip: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        neighbors: List[Dict[str, Any]] = []

        try:
            seed_context = self._collect_seed_context(device, ip, profile)
            lldp_rows = list(seed_context.get("lldp_rows") or [])
            cdp_rows = list(seed_context.get("cdp_rows") or [])
            neighbors.extend(lldp_rows)
            neighbors.extend(cdp_rows)
            arp = list(seed_context.get("arp_rows") or [])
            arp_mac_to_ip = {str(r.get("mac") or "").strip().lower(): str(r.get("ip") or "").strip() for r in arp if r.get("mac") and r.get("ip")}
            fdb_rows = list(seed_context.get("fdb_rows") or [])
            for row in fdb_rows:
                mac = str(row.get("mac") or "").strip().lower()
                local_port = str(row.get("port") or "").strip()
                if not mac or not local_port:
                    continue
                ip2 = arp_mac_to_ip.get(mac)
                if not ip2:
                    try:
                        cache = getattr(self, "_mac_to_ip_cache", None)
                        if isinstance(cache, dict) and mac in cache:
                            ip2 = str(cache.get(mac) or "").strip()
                        else:
                            d2 = self.db.query(Device).filter(Device.mac_address == mac).first()
                            if d2 and getattr(d2, "ip_address", None):
                                ip2 = str(d2.ip_address or "").strip()
                    except Exception:
                        ip2 = None
                if not ip2:
                    continue
                neighbors.append(
                    {
                        "local_interface": local_port,
                        "remote_interface": "UNKNOWN",
                        "neighbor_name": ip2,
                        "mgmt_ip": ip2,
                        "protocol": "FDB",
                        "discovery_source": str(row.get("discovery_source") or "snmp_fdb"),
                    }
                )
        except Exception:
            pass

        ssh_password = (getattr(device, "ssh_password", None) if device else None) or profile.get("ssh_password")
        if ssh_password:
            try:
                dev_info = DeviceInfo(
                    host=str(getattr(device, "ip_address", None) or ip),
                    username=(getattr(device, "ssh_username", None) if device else None) or profile.get("ssh_username") or "admin",
                    password=ssh_password,
                    secret=(getattr(device, "enable_password", None) if device else None) or profile.get("enable_password"),
                    port=int((getattr(device, "ssh_port", None) if device else None) or profile.get("ssh_port") or 22),
                    device_type=(getattr(device, "device_type", None) if device else None) or profile.get("device_type") or "cisco_ios",
                )
                conn = DeviceConnection(dev_info)
                if conn.connect():
                    try:
                        neighbors.extend(conn.get_neighbors() or [])
                    finally:
                        conn.disconnect()
            except Exception:
                pass

        merged: List[Dict[str, Any]] = []
        seen: Set[Tuple[str, str, str, str]] = set()
        for n in neighbors:
            neighbor_name = str(n.get("neighbor_name") or "").strip()
            mgmt_ip = str(n.get("mgmt_ip") or "").strip()
            local_interface = str(n.get("local_interface") or "").strip()
            remote_interface = str(n.get("remote_interface") or "").strip()
            key = (neighbor_name, mgmt_ip, local_interface, remote_interface)
            if key in seen:
                continue
            seen.add(key)
            merged.append(n)
        return merged

    def prefetch_seed_context(
        self,
        *,
        job_id: int,
        seed_device_id: int | None = None,
        seed_ip: str | None = None,
    ) -> Dict[str, Any]:
        job = self.db.query(DiscoveryJob).filter(DiscoveryJob.id == int(job_id)).first()
        if not job:
            raise ValueError("job not found")

        seed_device = None
        if seed_device_id is not None:
            seed_device = self.db.query(Device).filter(Device.id == int(seed_device_id)).first()
            if not seed_device:
                raise ValueError("seed device not found")

        seed_ip_s = str(seed_ip or (seed_device.ip_address if seed_device else "") or "").strip()
        if not seed_ip_s:
            raise ValueError("seed_ip is required")

        profile = self._job_snmp_profile(job)
        context = self._collect_seed_context(seed_device, seed_ip_s, profile)
        self.discovery._append_job_log(
            job,
            (
                "Hint Prefetch Completed: "
                f"seed={seed_device_id or ''} ip={seed_ip_s} "
                f"recorded={int(context.get('recorded') or 0)} "
                f"arp={len(context.get('arp_rows') or [])} "
                f"lldp={len(context.get('lldp_rows') or []) + len(context.get('cdp_rows') or [])} "
                f"fdb={len(context.get('fdb_rows') or [])}"
            ),
        )
        self.db.commit()
        return {
            "status": "ok",
            "job_id": int(job.id),
            "seed_device_id": int(seed_device_id) if seed_device_id is not None else None,
            "seed_ip": seed_ip_s,
            "recorded": int(context.get("recorded") or 0),
            "arp_count": len(context.get("arp_rows") or []),
            "lldp_count": len(context.get("lldp_rows") or []) + len(context.get("cdp_rows") or []),
            "fdb_count": len(context.get("fdb_rows") or []),
        }

    def _job_snmp_profile(self, job: DiscoveryJob) -> Dict[str, Any]:
        profile = None
        try:
            pid = getattr(job, "snmp_profile_id", None)
            if pid is not None:
                profile = self.db.query(SnmpCredentialProfile).filter(SnmpCredentialProfile.id == pid).first()
            if profile is None:
                sid = getattr(job, "site_id", None)
                if sid is not None:
                    site = self.db.query(Site).filter(Site.id == sid).first()
                    if site and getattr(site, "snmp_profile_id", None):
                        profile = (
                            self.db.query(SnmpCredentialProfile)
                            .filter(SnmpCredentialProfile.id == site.snmp_profile_id)
                            .first()
                        )
        except Exception:
            profile = None

        out = {
            "community": (job.snmp_community or getattr(profile, "snmp_community", None) or "public"),
            "version": (getattr(job, "snmp_version", None) or getattr(profile, "snmp_version", None) or "v2c"),
            "port": int(getattr(job, "snmp_port", None) or getattr(profile, "snmp_port", None) or 161),
            "v3_username": getattr(job, "snmp_v3_username", None) or getattr(profile, "snmp_v3_username", None),
            "v3_security_level": getattr(job, "snmp_v3_security_level", None) or getattr(profile, "snmp_v3_security_level", None),
            "v3_auth_proto": getattr(job, "snmp_v3_auth_proto", None) or getattr(profile, "snmp_v3_auth_proto", None),
            "v3_auth_key": getattr(job, "snmp_v3_auth_key", None) or getattr(profile, "snmp_v3_auth_key", None),
            "v3_priv_proto": getattr(job, "snmp_v3_priv_proto", None) or getattr(profile, "snmp_v3_priv_proto", None),
            "v3_priv_key": getattr(job, "snmp_v3_priv_key", None) or getattr(profile, "snmp_v3_priv_key", None),
            "ssh_username": getattr(profile, "ssh_username", None),
            "ssh_password": getattr(profile, "ssh_password", None),
            "ssh_port": getattr(profile, "ssh_port", None),
            "enable_password": getattr(profile, "enable_password", None),
            "device_type": getattr(profile, "device_type", None),
        }
        if getattr(job, "snmp_profile_id", None) is None:
            try:
                profiles = self.db.query(SnmpCredentialProfile).order_by(SnmpCredentialProfile.id.asc()).limit(8).all()
                pool = []
                for p in profiles:
                    pool.append(
                        {
                            "profile_id": p.id,
                            "community": getattr(p, "snmp_community", None) or "public",
                            "version": getattr(p, "snmp_version", None) or "v2c",
                            "port": int(getattr(p, "snmp_port", None) or 161),
                            "v3_username": getattr(p, "snmp_v3_username", None),
                            "v3_security_level": getattr(p, "snmp_v3_security_level", None),
                            "v3_auth_proto": getattr(p, "snmp_v3_auth_proto", None),
                            "v3_auth_key": getattr(p, "snmp_v3_auth_key", None),
                            "v3_priv_proto": getattr(p, "snmp_v3_priv_proto", None),
                            "v3_priv_key": getattr(p, "snmp_v3_priv_key", None),
                        }
                    )
                if pool:
                    out["credential_pool"] = pool
            except Exception:
                pass
        return out

    def _upsert_discovered(self, job: DiscoveryJob, ip: str, seed_profile: Dict[str, Any], neighbor_name: str = "") -> DiscoveredDevice:
        ip = str(ip or "").strip()
        if not ip:
            raise ValueError("ip is required")

        existing_device = self.db.query(Device).filter(Device.ip_address == ip).first()
        existing = (
            self.db.query(DiscoveredDevice)
            .filter(DiscoveredDevice.job_id == job.id, DiscoveredDevice.ip_address == ip)
            .first()
        )

        if existing_device:
            if not existing:
                existing = DiscoveredDevice(
                    job_id=job.id,
                    ip_address=ip,
                    hostname=existing_device.hostname or existing_device.name,
                    vendor="",
                    model=existing_device.model,
                    os_version=existing_device.os_version,
                    snmp_status="reachable",
                    status="existing",
                    matched_device_id=existing_device.id,
                    device_type=existing_device.device_type,
                    vendor_confidence=1.0,
                    chassis_candidate=False,
                    issues=[],
                    evidence={"source": "neighbor_crawl"},
                )
                self.db.add(existing)
                self.db.commit()
                return existing

            existing.status = "existing"
            existing.matched_device_id = existing_device.id
            existing.hostname = existing_device.hostname or existing_device.name
            self.db.commit()
            return existing

        scan_result = self.discovery._scan_single_host(ip, seed_profile)
        hostname = (scan_result.get("hostname") if isinstance(scan_result, dict) else None) or neighbor_name or ip

        if not existing:
            existing = DiscoveredDevice(job_id=job.id, ip_address=ip)
            self.db.add(existing)

        existing.hostname = hostname
        existing.vendor = (scan_result.get("vendor") if isinstance(scan_result, dict) else None) or existing.vendor
        existing.model = (scan_result.get("model") if isinstance(scan_result, dict) else None) or existing.model
        existing.os_version = (scan_result.get("os_version") if isinstance(scan_result, dict) else None) or existing.os_version
        existing.snmp_status = (scan_result.get("snmp_status") if isinstance(scan_result, dict) else None) or existing.snmp_status
        existing.device_type = (scan_result.get("device_type") if isinstance(scan_result, dict) else None) or existing.device_type
        existing.sys_object_id = (scan_result.get("sys_object_id") if isinstance(scan_result, dict) else None) or existing.sys_object_id
        existing.sys_descr = (scan_result.get("sys_descr") if isinstance(scan_result, dict) else None) or existing.sys_descr
        existing.vendor_confidence = float((scan_result.get("vendor_confidence") if isinstance(scan_result, dict) else 0.0) or 0.0)
        existing.chassis_candidate = bool((scan_result.get("chassis_candidate") if isinstance(scan_result, dict) else False) or False)
        existing.issues = (scan_result.get("issues") if isinstance(scan_result, dict) else None) or existing.issues
        existing.evidence = (scan_result.get("evidence") if isinstance(scan_result, dict) else None) or existing.evidence
        existing.status = existing.status or "new"
        existing.matched_device_id = None
        self.db.commit()
        return existing

    def run_neighbor_crawl(
        self,
        job_id: int,
        seed_device_id: int | None = None,
        seed_ip: str | None = None,
        max_depth: int = 2,
        max_devices: int = 300,
        min_interval_sec: float = 0.02,
    ) -> Dict[str, Any]:
        job = self.db.query(DiscoveryJob).filter(DiscoveryJob.id == job_id).first()
        if not job:
            raise ValueError("job not found")
        seed = None
        if seed_device_id is not None:
            seed = self.db.query(Device).filter(Device.id == int(seed_device_id)).first()
            if not seed:
                raise ValueError("seed device not found")
        seed_ip_s = str(seed_ip or (seed.ip_address if seed else "") or "").strip()
        if not seed_ip_s:
            raise ValueError("seed_ip is required")

        depth = int(max_depth or 1)
        if depth < 1:
            depth = 1

        profile = self._job_snmp_profile(job)
        try:
            def _get_setting_value(key: str) -> str:
                setting = self.db.query(SystemSetting).filter(SystemSetting.key == key).first()
                return setting.value if setting and setting.value and setting.value != "********" else ""

            def _parse_cidr_list(raw: str) -> list[str]:
                out = []
                for part in (raw or "").replace("\n", ",").split(","):
                    s = part.strip()
                    if s:
                        out.append(s)
                return out

            include_cidrs = _parse_cidr_list(_get_setting_value("neighbor_crawl_scope_include_cidrs") or _get_setting_value("discovery_scope_include_cidrs"))
            exclude_cidrs = _parse_cidr_list(_get_setting_value("neighbor_crawl_scope_exclude_cidrs") or _get_setting_value("discovery_scope_exclude_cidrs"))
            prefer_private = (_get_setting_value("neighbor_crawl_prefer_private") or _get_setting_value("discovery_prefer_private") or "true").strip().lower() in ("true", "1", "yes", "y", "on")

            include_nets = []
            exclude_nets = []
            for c in include_cidrs:
                try:
                    include_nets.append(ipaddress.ip_network(str(c).strip(), strict=False))
                except Exception:
                    continue
            for c in exclude_cidrs:
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

            self._scope_is_allowed = _is_allowed
            self._scope_prefer_private = bool(prefer_private)
        except Exception:
            self._scope_is_allowed = lambda _ip: True
            self._scope_prefer_private = True

        try:
            mac_to_ip = {}
            for d in self.db.query(Device).all():
                ip0 = str(getattr(d, "ip_address", "") or "").strip()
                if not ip0:
                    continue
                m0 = str(getattr(d, "mac_address", "") or "").strip().lower()
                if m0:
                    mac_to_ip[m0] = ip0
                lp = getattr(d, "latest_parsed_data", None)
                if isinstance(lp, dict):
                    aliases = lp.get("mac_aliases")
                    if isinstance(aliases, list):
                        for m in aliases:
                            mm = str(m or "").strip().lower()
                            if mm:
                                mac_to_ip[mm] = ip0
            self._mac_to_ip_cache = mac_to_ip
        except Exception:
            self._mac_to_ip_cache = {}

        if not self._scope_is_allowed(seed_ip_s):
            raise ValueError("seed_ip is outside discovery scope")

        visited_ips: Set[str] = set()
        queue: List[Tuple[str, int]] = [(seed_ip_s, depth)]

        discovered_created = 0
        discovered_updated = 0
        edges_seen = 0

        job.status = "running"
        job.total_ips = int(max_devices or 0) or 0
        job.scanned_ips = 0
        self.discovery._append_job_log(job, f"Neighbor Crawl Started: seed={seed.id if seed else ''} ip={seed_ip_s} depth={depth}")
        self.db.commit()

        try:
            self._upsert_discovered(job, seed_ip_s, profile, neighbor_name=(seed.hostname if seed else "") or (seed.name if seed else ""))
        except Exception:
            pass

        while queue:
            if len(visited_ips) >= int(max_devices or 1):
                self.discovery._append_job_log(job, f"Neighbor Crawl Stopped: reached max_devices={max_devices}")
                break
            current_ip, dleft = queue.pop(0)
            current_ip = str(current_ip or "").strip()
            if not current_ip:
                continue
            if current_ip in visited_ips:
                continue
            visited_ips.add(current_ip)
            try:
                job.scanned_ips = len(visited_ips)
                if len(visited_ips) % 10 == 0:
                    self.db.commit()
            except Exception:
                pass

            current_device = self.db.query(Device).filter(Device.ip_address == current_ip).first()
            neighbors = self._get_neighbors(current_device, current_ip, profile)
            edges_seen += len(neighbors)

            for n in neighbors:
                neighbor_name = str(n.get("neighbor_name") or "").strip()
                mgmt_ip = str(n.get("mgmt_ip") or "").strip()
                if not mgmt_ip and neighbor_name:
                    base = neighbor_name.split(".")[0].strip()
                    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", neighbor_name):
                        mgmt_ip = neighbor_name
                    if not mgmt_ip:
                        dd = (
                            self.db.query(DiscoveredDevice)
                            .filter(DiscoveredDevice.job_id == job.id, (DiscoveredDevice.hostname == neighbor_name) | (DiscoveredDevice.hostname == base))
                            .first()
                        )
                        if dd and dd.ip_address:
                            mgmt_ip = str(dd.ip_address).strip()
                    cand = (
                        self.db.query(Device)
                        .filter((Device.hostname == neighbor_name) | (Device.hostname == base) | (Device.name == neighbor_name) | (Device.name == base))
                        .first()
                    )
                    if cand and cand.ip_address:
                        mgmt_ip = str(cand.ip_address).strip()
                    if not mgmt_ip:
                        for host in (neighbor_name, base):
                            h = str(host or "").strip()
                            if not h:
                                continue
                            try:
                                mgmt_ip = socket.gethostbyname(h)
                                break
                            except Exception:
                                continue
                if not mgmt_ip:
                    continue
                if not self._scope_is_allowed(mgmt_ip):
                    continue
                if mgmt_ip in visited_ips:
                    continue

                existing = (
                    self.db.query(DiscoveredDevice)
                    .filter(DiscoveredDevice.job_id == job.id, DiscoveredDevice.ip_address == mgmt_ip)
                    .first()
                )
                before_id = existing.id if existing else None

                self._upsert_discovered(job, mgmt_ip, profile, neighbor_name=neighbor_name)
                if before_id is None:
                    discovered_created += 1
                else:
                    discovered_updated += 1

                if dleft > 1:
                    if getattr(self, "_scope_prefer_private", True):
                        try:
                            if ipaddress.ip_address(mgmt_ip).is_private:
                                queue.insert(0, (mgmt_ip, dleft - 1))
                            else:
                                queue.append((mgmt_ip, dleft - 1))
                        except Exception:
                            queue.append((mgmt_ip, dleft - 1))
                    else:
                        queue.append((mgmt_ip, dleft - 1))
                if min_interval_sec and min_interval_sec > 0:
                    time.sleep(float(min_interval_sec))

        try:
            DiscoveryService(self.db).auto_approve_job(job.id)
        except Exception:
            pass

        job.status = "completed"
        self.discovery._append_job_log(job, f"Neighbor Crawl Completed: visited={len(visited_ips)} neighbors_seen={edges_seen} discovered_created={discovered_created} discovered_updated={discovered_updated}")
        self.db.commit()

        return {
            "status": "ok",
            "visited_ips": len(visited_ips),
            "neighbors_seen": edges_seen,
            "discovered_created": discovered_created,
            "discovered_updated": discovered_updated,
        }
