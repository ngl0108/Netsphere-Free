import asyncio
import subprocess
import ipaddress
import logging
import os
from fastapi import HTTPException
try:
    import nmap
except ImportError:  # pragma: no cover
    nmap = None
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from datetime import datetime
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.credentials import SnmpCredentialProfile
from app.models.device import Device
from app.models.device import Site
from app.models.settings import SystemSetting
from app.models.topology_candidate import TopologyNeighborCandidate
from app.db.session import SessionLocal
from app.services.discovery.handlers.snmp import SnmpScanHandler
from app.services.discovery.handlers.port_scan import PortScanHandler
from app.services.discovery_hint_service import DiscoveryHintService
from app.services.discovery_hint_telemetry_service import DiscoveryHintTelemetryService
from app.services.parser_quality_service import ParserQualityService
from app.services.snmp_service import SnmpManager
from app.core.device_fingerprints import get_driver_for_vendor
from app.services.capability_profile_service import CapabilityProfileService
from app.services.device_support_policy_service import DeviceSupportPolicyService
from app.services.license_policy_service import LicensePolicyService, LicensePolicyViolation
from app.services.monitoring_profile_service import MonitoringProfileService
from app.services.preview_managed_node_service import PreviewManagedNodeService

logger = logging.getLogger(__name__)

class DiscoveryService:
    def __init__(self, db: Session):
        self.db = db
        self.snmp_handler = SnmpScanHandler(snmp_manager_cls=SnmpManager)
        self.port_handler = PortScanHandler(nmap_module=nmap)

    def _append_job_log(self, job: DiscoveryJob, message: str, max_chars: int = 20000) -> None:
        msg = str(message or "")
        if not msg:
            return
        if job.logs is None:
            job.logs = ""
        if not msg.startswith("\n"):
            msg = "\n" + msg
        job.logs = (job.logs or "") + msg
        if len(job.logs) > max_chars:
            job.logs = job.logs[-max_chars:]

    def _extract_up_hosts(self, nm) -> list:
        hosts = []
        for h in nm.all_hosts() if nm else []:
            try:
                if nm[h].state() == "up":
                    hosts.append(h)
            except Exception:
                continue
        return hosts

    def _normalize_host_key(self, value: str) -> str:
        s = str(value or "").strip().lower()
        if not s:
            return ""
        if "." in s:
            s = s.split(".")[0]
        for ch in ("-", "_", " "):
            s = s.replace(ch, "")
        return s

    def _normalize_mac_key(self, value: str) -> str:
        s = str(value or "").strip().lower()
        if not s:
            return ""
        for ch in (":", "-", ".", " "):
            s = s.replace(ch, "")
        return s

    def _tcp_alive_sweep(self, cidr: str, ports=None, max_hosts: int = 1024, timeout: float = 0.25, include_cidrs: list[str] | None = None, exclude_cidrs: list[str] | None = None) -> list:
        network = ipaddress.ip_network(cidr, strict=False)
        total = int(network.num_addresses) - 2 if int(network.num_addresses) >= 2 else 0
        if total > max_hosts:
            return []

        ports = ports or [22, 23, 80, 443, 161, 830]

        import socket

        def check(ip: str) -> bool:
            for p in ports:
                s = None
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(timeout)
                    r = s.connect_ex((ip, int(p)))
                    if r in (0, 111, 10061):
                        return True
                except Exception:
                    continue
                finally:
                    try:
                        if s is not None:
                            s.close()
                    except Exception:
                        pass
            return False

        alive = []
        include_nets = []
        exclude_nets = []
        for c in include_cidrs or []:
            try:
                include_nets.append(ipaddress.ip_network(str(c).strip(), strict=False))
            except Exception:
                continue
        for c in exclude_cidrs or []:
            try:
                exclude_nets.append(ipaddress.ip_network(str(c).strip(), strict=False))
            except Exception:
                continue

        ips = []
        for ip in network.hosts():
            try:
                ip_obj = ipaddress.ip_address(str(ip))
            except Exception:
                continue
            if ip_obj.is_loopback or ip_obj.is_multicast or ip_obj.is_unspecified or ip_obj.is_link_local:
                continue
            if any(ip_obj in n for n in exclude_nets):
                continue
            if include_nets and not any(ip_obj in n for n in include_nets):
                continue
            ips.append(str(ip_obj))

        base_workers = int(os.getenv("DISCOVERY_PING_MAX_WORKERS", "0") or 0)
        if base_workers <= 0:
            cpu = os.cpu_count() or 4
            base_workers = cpu * 10
        max_workers = max(10, min(200, base_workers, len(ips) or 1))

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(check, ip): ip for ip in ips}
            for fut in as_completed(futs):
                ip = futs[fut]
                try:
                    if fut.result():
                        alive.append(ip)
                except Exception:
                    continue
        return alive

    def create_scan_job(
        self,
        cidr: str,
        community: str,
        site_id: int | None = None,
        snmp_profile_id: int | None = None,
        snmp_version: str = "v2c",
        snmp_port: int = 161,
        snmp_v3_username: str | None = None,
        snmp_v3_security_level: str | None = None,
        snmp_v3_auth_proto: str | None = None,
        snmp_v3_auth_key: str | None = None,
        snmp_v3_priv_proto: str | None = None,
        snmp_v3_priv_key: str | None = None,
    ) -> DiscoveryJob:
        """
        Job 생성 및 초기화 (동기 실행)
        """
        profile = None
        if snmp_profile_id is not None:
            profile = self.db.query(SnmpCredentialProfile).filter(SnmpCredentialProfile.id == snmp_profile_id).first()
        if profile is None and site_id is not None:
            site = self.db.query(Site).filter(Site.id == site_id).first()
            if site and getattr(site, "snmp_profile_id", None):
                profile = self.db.query(SnmpCredentialProfile).filter(SnmpCredentialProfile.id == site.snmp_profile_id).first()

        if profile is not None:
            effective_community = profile.snmp_community
            effective_version = profile.snmp_version
            effective_port = profile.snmp_port
            effective_v3_username = profile.snmp_v3_username
            effective_v3_security_level = profile.snmp_v3_security_level
            effective_v3_auth_proto = profile.snmp_v3_auth_proto
            effective_v3_auth_key = profile.snmp_v3_auth_key
            effective_v3_priv_proto = profile.snmp_v3_priv_proto
            effective_v3_priv_key = profile.snmp_v3_priv_key
        else:
            effective_community = community
            effective_version = snmp_version
            effective_port = snmp_port
            effective_v3_username = snmp_v3_username
            effective_v3_security_level = snmp_v3_security_level
            effective_v3_auth_proto = snmp_v3_auth_proto
            effective_v3_auth_key = snmp_v3_auth_key
            effective_v3_priv_proto = snmp_v3_priv_proto
            effective_v3_priv_key = snmp_v3_priv_key

        job = DiscoveryJob(
            cidr=cidr,
            site_id=site_id,
            snmp_profile_id=(profile.id if profile else snmp_profile_id),
            snmp_community=effective_community,
            snmp_version=(effective_version or "v2c"),
            snmp_port=int(effective_port or 161),
            snmp_v3_username=effective_v3_username,
            snmp_v3_security_level=effective_v3_security_level,
            snmp_v3_auth_proto=effective_v3_auth_proto,
            snmp_v3_auth_key=effective_v3_auth_key,
            snmp_v3_priv_proto=effective_v3_priv_proto,
            snmp_v3_priv_key=effective_v3_priv_key,
            status="pending",
            logs="Job Created. Waiting for worker...",
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def run_scan_worker(self, job_id: int):
        """
        Worker Process: 실제 스캔 실행 (Background Task) with Nmap & SNMP
        """
        db = SessionLocal()
        job = db.query(DiscoveryJob).filter(DiscoveryJob.id == job_id).first()
        
        if not job:
            db.close()
            return

        try:
            job.status = "running"
            self._append_job_log(job, "Worker Started. Initializing Scanner...")
            db.commit()

            def _get_setting_value(key: str) -> str:
                setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
                return setting.value if setting and setting.value and setting.value != "********" else ""

            def _parse_cidr_list(raw: str) -> list[str]:
                out = []
                for part in (raw or "").replace("\n", ",").split(","):
                    s = part.strip()
                    if s:
                        out.append(s)
                return out

            cidr = job.cidr
            snmp_profile = {
                "community": (job.snmp_community or "public"),
                "version": (getattr(job, "snmp_version", None) or "v2c"),
                "port": int(getattr(job, "snmp_port", None) or 161),
                "v3_username": getattr(job, "snmp_v3_username", None),
                "v3_security_level": getattr(job, "snmp_v3_security_level", None),
                "v3_auth_proto": getattr(job, "snmp_v3_auth_proto", None),
                "v3_auth_key": getattr(job, "snmp_v3_auth_key", None),
                "v3_priv_proto": getattr(job, "snmp_v3_priv_proto", None),
                "v3_priv_key": getattr(job, "snmp_v3_priv_key", None),
            }
            try:
                raw_lim = (_get_setting_value("auto_credential_max_profiles") or "").strip()
                try:
                    max_profiles = int(raw_lim)
                except Exception:
                    max_profiles = 8
                if max_profiles < 0:
                    max_profiles = 0
                if max_profiles > 50:
                    max_profiles = 50
                if max_profiles and getattr(job, "snmp_profile_id", None) is None:
                    profiles = db.query(SnmpCredentialProfile).order_by(SnmpCredentialProfile.id.asc()).limit(max_profiles).all()
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
                                "ssh_username": getattr(p, "ssh_username", None),
                                "ssh_password": getattr(p, "ssh_password", None),
                                "ssh_port": getattr(p, "ssh_port", None),
                                "enable_password": getattr(p, "enable_password", None),
                                "device_type": getattr(p, "device_type", None),
                            }
                        )
                    snmp_profile["credential_pool"] = pool
            except Exception:
                pass

            network = ipaddress.ip_network(cidr, strict=False)
            host_count = int(network.num_addresses) - 2 if int(network.num_addresses) >= 2 else 0
            job.total_ips = max(0, host_count)
            self._append_job_log(job, f"Target Network: {cidr} ({job.total_ips} hosts)")
            
            # Nmap Scanner Init
            nm = None
            if nmap is not None:
                nm = nmap.PortScanner()
            
            # --- Phase 1: Fast Ping Scan (Nmap) ---
            # Nmap is much faster than running ping subprocess for each IP
            active_hosts = []
            include_cidrs = _parse_cidr_list(_get_setting_value("discovery_scope_include_cidrs"))
            exclude_cidrs = _parse_cidr_list(_get_setting_value("discovery_scope_exclude_cidrs"))
            prefer_private = (_get_setting_value("discovery_prefer_private") or "true").strip().lower() in ("true", "1", "yes", "y", "on")
            if nm is not None:
                scan_args = "-sn -PE -PP"
                self._append_job_log(job, f"[Phase 1] Ping Sweeping with Nmap ({scan_args})...")
                db.commit()
                nm.scan(hosts=cidr, arguments=scan_args)
                active_hosts = self._extract_up_hosts(nm)

                if len(active_hosts) == 0:
                    scan_args2 = "-sn -PS22,23,80,443,161,830 -PA80,443"
                    self._append_job_log(job, f"[Phase 1b] TCP Ping Sweeping with Nmap ({scan_args2})...")
                    db.commit()
                    nm.scan(hosts=cidr, arguments=scan_args2)
                    active_hosts = self._extract_up_hosts(nm)
            else:
                self._append_job_log(job, "[Phase 1] python-nmap missing; using TCP connect probe fallback...")
                db.commit()
                active_hosts = self._tcp_alive_sweep(cidr, include_cidrs=include_cidrs, exclude_cidrs=exclude_cidrs)

            try:
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
                filtered = []
                for ip in active_hosts:
                    try:
                        ip_obj = ipaddress.ip_address(str(ip).strip())
                    except Exception:
                        continue
                    if ip_obj.is_loopback or ip_obj.is_multicast or ip_obj.is_unspecified or ip_obj.is_link_local:
                        continue
                    if any(ip_obj in n for n in exclude_nets):
                        continue
                    if include_nets and not any(ip_obj in n for n in include_nets):
                        continue
                    filtered.append(str(ip_obj))
                if prefer_private:
                    filtered.sort(key=lambda s: (0 if ipaddress.ip_address(s).is_private else 1, s))
                active_hosts = filtered
            except Exception:
                pass

            self._append_job_log(job, f"[Phase 1] Found {len(active_hosts)} active hosts.")
            self._append_job_log(job, "[Phase 2] Deep Inspection (SNMP & Ports)...")
            db.commit()
            
            # --- Phase 2: Deep Inspection (Parallel) ---
            def _get_int_setting(key: str, default: int) -> int:
                raw = (_get_setting_value(key) or "").strip()
                try:
                    return int(raw)
                except Exception:
                    return default

            max_workers = _get_int_setting("discovery_max_workers", 60)
            max_workers = max(10, min(200, max_workers))

            commit_batch = _get_int_setting("discovery_commit_batch_size", 25)
            commit_batch = max(5, min(200, commit_batch))

            inflight_mult = _get_int_setting("discovery_inflight_multiplier", 4)
            inflight_mult = max(2, min(10, inflight_mult))
            try:
                parser_low_conf_threshold = float(_get_setting_value("parser_low_confidence_threshold") or 0.45)
            except Exception:
                parser_low_conf_threshold = 0.45
            if parser_low_conf_threshold < 0:
                parser_low_conf_threshold = 0.0
            if parser_low_conf_threshold > 1:
                parser_low_conf_threshold = 1.0

            existing_devices = {
                ip: did
                for did, ip in db.query(Device.id, Device.ip_address).filter(Device.ip_address.isnot(None)).all()
            }

            completed_count = 0
            job.scanned_ips = 0
            job.total_ips = len(active_hosts)
            db.commit()

            pending_rows = []
            pending_logs = []

            def flush_pending():
                nonlocal pending_rows, pending_logs
                if pending_rows:
                    try:
                        db.add_all(pending_rows)
                        pending_rows = []
                        db.flush()
                    except IntegrityError:
                        db.rollback()
                        for r in pending_rows:
                            self._save_discovered_device(db, job.id, {
                                "ip_address": r.ip_address,
                                "hostname": r.hostname,
                                "vendor": r.vendor,
                                "model": r.model,
                                "os_version": r.os_version,
                                "snmp_status": r.snmp_status,
                                "device_type": r.device_type,
                                "sys_object_id": getattr(r, "sys_object_id", None),
                                "sys_descr": getattr(r, "sys_descr", None),
                                "vendor_confidence": getattr(r, "vendor_confidence", 0.0),
                                "chassis_candidate": getattr(r, "chassis_candidate", False),
                                "issues": getattr(r, "issues", None),
                                "evidence": getattr(r, "evidence", None),
                            })
                        pending_rows = []
                if pending_logs:
                    self._append_job_log(job, "\n".join(pending_logs))
                    pending_logs = []
                db.commit()

            def build_row(result: dict) -> DiscoveredDevice:
                ip = result.get("ip_address")
                matched_id = existing_devices.get(ip)
                status = "existing" if matched_id else "new"
                return DiscoveredDevice(
                    job_id=job.id,
                    ip_address=ip,
                    hostname=result.get("hostname") or ip,
                    vendor=result.get("vendor"),
                    model=result.get("model"),
                    os_version=result.get("os_version"),
                    snmp_status=result.get("snmp_status", "unknown"),
                    status=status,
                    matched_device_id=matched_id,
                    device_type=result.get("device_type") or "unknown",
                    sys_object_id=result.get("sys_object_id"),
                    sys_descr=result.get("sys_descr"),
                    vendor_confidence=float(result.get("vendor_confidence") or 0.0),
                    chassis_candidate=bool(result.get("chassis_candidate") or False),
                    issues=result.get("issues"),
                    evidence=result.get("evidence"),
                )

            inflight = max_workers * inflight_mult
            active_iter = iter([str(ip) for ip in active_hosts])

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_map = {}
                for _ in range(inflight):
                    ip = next(active_iter, None)
                    if not ip:
                        break
                    future_map[executor.submit(self._scan_single_host, ip, snmp_profile, parser_low_conf_threshold)] = ip

                while future_map:
                    done, _ = wait(list(future_map.keys()), return_when=FIRST_COMPLETED)
                    for fut in done:
                        ip = future_map.pop(fut, None)
                        if not ip:
                            continue
                        try:
                            result = fut.result()
                            if result:
                                vendor_str = f"{result.get('vendor','')} {result.get('model','')}".strip()
                                pending_logs.append(f"  [+] {ip}: {vendor_str} ({result.get('snmp_status')})")
                                pending_rows.append(build_row(result))
                            completed_count += 1
                            job.scanned_ips = completed_count
                            if completed_count % commit_batch == 0:
                                flush_pending()
                        except Exception as e:
                            pending_logs.append(f"  [!] {ip}: inspect error {str(e)}")
                        finally:
                            nxt = next(active_iter, None)
                            if nxt:
                                future_map[executor.submit(self._scan_single_host, nxt, snmp_profile, parser_low_conf_threshold)] = nxt

                flush_pending()

            try:
                DiscoveryService(db).auto_approve_job(job.id)
            except Exception:
                pass
            
            job.status = "completed"
            job.completed_at = datetime.now()
            self._append_job_log(job, "Scan Completed Successfully.")
            db.commit()

            try:
                from app.services.topology_snapshot_policy_service import TopologySnapshotPolicyService
                from app.models.settings import SystemSetting

                row = db.query(SystemSetting).filter(SystemSetting.key == "topology_snapshot_auto_on_discovery_job_complete").first()
                enabled = True
                if row and row.value is not None:
                    enabled = str(row.value).strip().lower() in {"1", "true", "yes", "y", "on"}
                if enabled:
                    TopologySnapshotPolicyService.maybe_create_snapshot(
                        db,
                        site_id=getattr(job, "site_id", None),
                        job_id=int(job.id),
                        trigger="discovery_job_completed",
                    )
            except Exception:
                pass

        except Exception as e:
            job.status = "failed"
            self._append_job_log(job, f"[Error] Scan Failed: {str(e)}")
            db.commit()
        finally:
            db.close()

    def _scan_single_host(self, ip: str, snmp_profile: dict, parser_low_conf_threshold: float = 0.45):
        """
        개별 호스트 정밀 스캔 (Delegated to Handlers)
        1. SNMP Attempt
        2. If SNMP Fails -> Port Scan (Fallback)
        """
        # 1. SNMP Scan
        info = self.snmp_handler.scan(ip, snmp_profile)

        if info:
            return ParserQualityService.normalize_discovery_result(
                info,
                ip_address=ip,
                low_conf_threshold=parser_low_conf_threshold,
            )

        # 2. Port Scan Fallback
        info = self.port_handler.scan(ip)
        normalized = ParserQualityService.normalize_discovery_result(
            info,
            ip_address=ip,
            low_conf_threshold=parser_low_conf_threshold,
        )
        hinted = self._apply_hint_driven_fallback(ip, normalized, snmp_profile, parser_low_conf_threshold)
        return hinted or normalized

    def _apply_hint_driven_fallback(
        self,
        ip: str,
        normalized: dict,
        snmp_profile: dict,
        parser_low_conf_threshold: float,
    ) -> dict | None:
        if not isinstance(normalized, dict):
            return None
        evidence = normalized.get("evidence") if isinstance(normalized.get("evidence"), dict) else {}
        open_ports = evidence.get("open_ports") if isinstance(evidence.get("open_ports"), list) else []
        if not any(int(port) in {22, 830} for port in open_ports if str(port).isdigit()):
            return None

        hint = DiscoveryHintService(self.db).build_ip_hint(ip, open_ports=open_ports)
        if not hint:
            return None

        evidence["hint_engine"] = {
            "oui_prefix": hint.get("oui_prefix"),
            "raw_vendor": hint.get("raw_vendor"),
            "normalized_vendor": hint.get("normalized_vendor"),
            "cache_context": hint.get("cache_context"),
            "driver_candidates": hint.get("driver_candidates"),
        }
        normalized["evidence"] = evidence
        issues = list(normalized.get("issues") or [])
        issues.append(
            {
                "code": "mac_hint_available",
                "severity": "info",
                "message": "MAC/OUI와 인접 장비 컨텍스트로 SSH 드라이버 후보를 계산했습니다.",
                "hint": "SNMP 실패 시 힌트 기반 SSH 재시도를 우선 수행합니다.",
            }
        )
        normalized["issues"] = issues

        ssh_result = self._try_hint_drivers_via_ssh(ip, hint, snmp_profile)
        if not ssh_result:
            telemetry_event = DiscoveryHintService(self.db).build_hint_telemetry_event(
                ip=ip,
                hint=hint,
                chosen_driver=(hint.get("driver_candidates") or [{}])[0].get("driver") if hint.get("driver_candidates") else None,
                final_driver=None,
                success=False,
                failure_reason="ssh_probe_failed_or_credentials_missing",
            )
            normalized["evidence"]["hint_telemetry"] = telemetry_event
            DiscoveryHintTelemetryService.record_event(telemetry_event)
            return normalized

        merged = ParserQualityService.normalize_discovery_result(
            ssh_result,
            ip_address=ip,
            low_conf_threshold=parser_low_conf_threshold,
        )
        merged_evidence = merged.get("evidence") if isinstance(merged.get("evidence"), dict) else {}
        merged_evidence["hint_engine"] = evidence.get("hint_engine")
        telemetry_event = DiscoveryHintService(self.db).build_hint_telemetry_event(
            ip=ip,
            hint=hint,
            chosen_driver=ssh_result.get("device_type"),
            final_driver=ssh_result.get("device_type"),
            success=True,
        )
        merged_evidence["hint_telemetry"] = telemetry_event
        DiscoveryHintTelemetryService.record_event(telemetry_event)
        merged["evidence"] = merged_evidence
        merged_issues = list(merged.get("issues") or [])
        merged_issues.append(
            {
                "code": "hint_driven_ssh_success",
                "severity": "info",
                "message": "SNMP 없이 MAC/OUI 힌트 기반 SSH 드라이버 선택으로 장비 식별에 성공했습니다.",
                "hint": "인접 장비 ARP/LLDP 캐시와 OUI 힌트를 기반으로 재시도했습니다.",
            }
        )
        merged["issues"] = merged_issues
        return merged

    def _build_ssh_credential_candidates(self, snmp_profile: dict) -> list[dict]:
        candidates: list[dict] = []
        seen: set[tuple[str, str, int, str]] = set()

        def _append_candidate(raw: dict, source: str) -> None:
            if not isinstance(raw, dict):
                return
            username = str(raw.get("ssh_username") or "").strip()
            password = raw.get("ssh_password")
            port = int(raw.get("ssh_port") or 22)
            enable_password = raw.get("enable_password")
            if not username or not password:
                return
            key = (username, str(password), port, str(enable_password or ""))
            if key in seen:
                return
            seen.add(key)
            candidates.append(
                {
                    "ssh_username": username,
                    "ssh_password": password,
                    "ssh_port": port,
                    "enable_password": enable_password,
                    "source": source,
                }
            )

        _append_candidate(snmp_profile or {}, "primary_profile")
        for profile in (snmp_profile or {}).get("credential_pool") or []:
            _append_candidate(profile, f"profile:{profile.get('profile_id')}")

        if self.db is not None:
            default_ssh_username = self._get_setting_value("default_ssh_username")
            default_ssh_password = self._get_setting_value("default_ssh_password")
            default_enable_password = self._get_setting_value("default_enable_password")
            if default_ssh_username and default_ssh_password:
                _append_candidate(
                    {
                        "ssh_username": default_ssh_username,
                        "ssh_password": default_ssh_password,
                        "ssh_port": 22,
                        "enable_password": default_enable_password,
                    },
                    "defaults",
                )
        return candidates[:4]

    def _try_hint_drivers_via_ssh(self, ip: str, hint: dict, snmp_profile: dict) -> dict | None:
        candidates = [row for row in (hint.get("driver_candidates") or []) if isinstance(row, dict)]
        if not candidates:
            return None
        creds = self._build_ssh_credential_candidates(snmp_profile)
        if not creds:
            return None

        from app.services.ssh_service import DeviceConnection, DeviceInfo

        for cred in creds:
            for candidate in candidates[:3]:
                driver = str(candidate.get("driver") or "").strip()
                if not driver:
                    continue
                info = DeviceInfo(
                    host=ip,
                    username=cred["ssh_username"],
                    password=cred["ssh_password"],
                    secret=cred.get("enable_password"),
                    port=int(cred.get("ssh_port") or 22),
                    device_type=driver,
                )
                conn = DeviceConnection(info)
                try:
                    if not conn.connect():
                        continue
                    facts = conn.get_facts() or {}
                    vendor = (
                        str(facts.get("vendor") or "").strip()
                        or str(hint.get("normalized_vendor") or "").strip()
                        or str(hint.get("raw_vendor") or "").strip()
                        or "Unknown"
                    )
                    model = str(facts.get("model") or facts.get("platform") or "").strip()
                    version = str(facts.get("os_version") or facts.get("version") or "").strip()
                    hostname = str(facts.get("hostname") or facts.get("fqdn") or ip).strip() or ip
                    return {
                        "ip_address": ip,
                        "hostname": hostname,
                        "vendor": vendor,
                        "model": model,
                        "os_version": version,
                        "device_type": driver,
                        "snmp_status": "unreachable",
                        "vendor_confidence": float(candidate.get("score") or 0.0),
                        "chassis_candidate": False,
                        "issues": [],
                        "evidence": {
                            "ssh_probe": {
                                "driver": driver,
                                "credential_source": cred.get("source"),
                                "method": "hint_driven_ssh",
                            }
                        },
                    }
                except Exception:
                    continue
                finally:
                    try:
                        conn.disconnect()
                    except Exception:
                        pass
        return None



    def _estimate_chassis_candidate(self, sys_descr: str, model: str, vendor: str) -> bool:
        text = f"{sys_descr or ''} {model or ''}".lower()
        if "chassis" in text:
            return True
        if any(k in text for k in ("c940", "c960", "c950", "nexus 950", "n9k", "nexus 9k", "mx", "ptx", "qfx10", "dcs-7500", "ce128", "s127", "s97")):
            return True
        v = str(vendor or "").lower()
        if v in ("cisco", "juniper", "arista", "huawei", "aruba") and any(k in text for k in ("sup", "supervisor", "linecard", "fpc", "pic", "mpc", "lpu")):
            return True
        return False

    def _identify_model(self, sys_descr):
        if "C3750" in sys_descr: return "Catalyst 3750"
        if "C2960" in sys_descr: return "Catalyst 2960"
        if "N9K" in sys_descr: return "Nexus 9000"
        if "CSR1000V" in sys_descr: return "CSR1000V"
        return ""

    def _extract_version(self, sys_descr):
        # Simplified version extraction
        parts = sys_descr.split(',')
        if len(parts) > 1:
            return parts[1].strip()
        return ""

    def _save_discovered_device(self, db, job_id, data):
        existing_device = db.query(Device).filter(Device.ip_address == data['ip_address']).first()
        if not existing_device:
            mac = str(data.get("mac_address") or "").strip().lower()
            if mac:
                existing_device = db.query(Device).filter(Device.mac_address == mac).first()
                if not existing_device:
                    mac_norm = self._normalize_mac_key(mac)
                    if mac_norm:
                        for d in db.query(Device).filter(Device.mac_address.isnot(None)).all():
                            if self._normalize_mac_key(getattr(d, "mac_address", None)) == mac_norm:
                                existing_device = d
                                break
        status = "existing" if existing_device else "new"
        matched_id = existing_device.id if existing_device else None

        issues = data.get("issues") or []
        evidence = data.get("evidence") or {}
        try:
            hn = (data.get("hostname") or "").strip()
            if hn:
                host_conflict = db.query(Device).filter(or_(Device.name == hn, Device.hostname == hn)).first()
                if host_conflict and (not matched_id or host_conflict.id != matched_id):
                    issues = list(issues) + [{
                        "code": "hostname_conflict",
                        "severity": "warn",
                        "message": "Hostname이 기존 관리 장비와 중복됩니다.",
                        "hint": f"기존 장비(ID:{host_conflict.id})와 이름 충돌 가능성이 있어 확인이 필요합니다.",
                    }]
        except Exception:
            pass
        
        # Calculate snmp status text from data if needed, or use what's passed
        snmp_status = data.get('snmp_status', 'unknown')
        existing = db.query(DiscoveredDevice).filter(
            DiscoveredDevice.job_id == job_id,
            DiscoveredDevice.ip_address == data['ip_address'],
        ).first()

        if existing:
            existing.hostname = data.get("hostname") or existing.hostname
            existing.vendor = data.get("vendor") or existing.vendor
            existing.model = data.get("model") or existing.model
            existing.os_version = data.get("os_version") or existing.os_version
            existing.mac_address = data.get("mac_address") or existing.mac_address
            existing.snmp_status = snmp_status
            existing.status = existing.status if existing.status in ("approved", "ignored") else status
            existing.matched_device_id = matched_id
            existing.device_type = data.get("device_type") or existing.device_type
            existing.sys_object_id = data.get("sys_object_id") or existing.sys_object_id
            existing.sys_descr = data.get("sys_descr") or existing.sys_descr
            existing.vendor_confidence = data.get("vendor_confidence") if data.get("vendor_confidence") is not None else existing.vendor_confidence
            existing.chassis_candidate = data.get("chassis_candidate") if data.get("chassis_candidate") is not None else existing.chassis_candidate
            existing.issues = issues if issues is not None else existing.issues
            existing.evidence = evidence if evidence is not None else existing.evidence
        else:
            discovered = DiscoveredDevice(
                job_id=job_id,
                ip_address=data['ip_address'],
                hostname=data.get('hostname') or data['ip_address'],
                vendor=data.get('vendor'),
                model=data.get('model'),
                os_version=data.get('os_version'),
                mac_address=data.get("mac_address"),
                snmp_status=snmp_status,
                status=status,
                matched_device_id=matched_id,
                device_type=data.get("device_type") or "unknown",
                sys_object_id=data.get("sys_object_id"),
                sys_descr=data.get("sys_descr"),
                vendor_confidence=data.get("vendor_confidence") or 0.0,
                chassis_candidate=bool(data.get("chassis_candidate") or False),
                issues=issues,
                evidence=evidence,
            )
            db.add(discovered)
            db.flush()

    def _is_hint_prefetch_seed_candidate(self, device: Device | None) -> bool:
        if device is None:
            return False
        device_type = str(getattr(device, "device_type", "") or "").strip().lower()
        vendor = str(getattr(device, "vendor", "") or "").strip().lower()
        deny_tokens = {"linux", "windows", "windows_cmd", "server", "hypervisor", "vmware", "kvm"}
        if device_type in deny_tokens:
            return False
        allow_tokens = (
            "switch",
            "router",
            "firewall",
            "gateway",
            "cisco_ios",
            "juniper_junos",
            "arista_eos",
            "huawei",
            "hp_procurve",
            "dell_os",
            "extreme",
            "fortinet",
            "dasan",
            "ubiquoss",
            "handream",
            "soltech",
            "coreedge",
            "nst",
            "piolink",
        )
        return any(token in device_type for token in allow_tokens) or any(token in vendor for token in allow_tokens)

    def _maybe_dispatch_hint_prefetch(self, job: DiscoveryJob | None, device: Device | None, discovered: DiscoveredDevice | None = None) -> None:
        if job is None or device is None:
            return
        if not self._is_hint_prefetch_seed_candidate(device):
            return
        enabled = (self._get_setting_value("hint_prefetch_on_approve_enabled") or "true").strip().lower() in ("true", "1", "yes", "y", "on")
        if not enabled:
            return
        seed_ip = str(getattr(device, "ip_address", None) or getattr(discovered, "ip_address", None) or "").strip()
        if not seed_ip:
            return
        try:
            delay_seconds = float(self._get_setting_value("hint_prefetch_on_approve_delay_seconds") or 0.1)
        except Exception:
            delay_seconds = 0.1
        try:
            from app.tasks.discovery_dispatch import dispatch_discovery_hint_prefetch

            result = dispatch_discovery_hint_prefetch(
                int(job.id),
                seed_device_id=int(device.id),
                seed_ip=seed_ip,
                idempotency_key=f"hint-prefetch:{job.id}:{device.id}:{seed_ip}",
                countdown=max(0.0, float(delay_seconds)),
            )
            if isinstance(result, dict):
                self._append_job_log(
                    job,
                    f"Hint Prefetch Dispatch: device={int(device.id)} ip={seed_ip} status={result.get('status')}",
                )
                self.db.commit()
        except Exception:
            pass

    def approve_device(self, discovered_id: int):
        discovered = self.db.query(DiscoveredDevice).filter(DiscoveredDevice.id == discovered_id).first()
        if not discovered: 
            logger.warning("DiscoveredDevice not found", extra={"job_id": None, "device_id": None})
            return None
        job = self.db.query(DiscoveryJob).filter(DiscoveryJob.id == discovered.job_id).first()

        host_name = discovered.hostname if discovered.hostname else None
        if host_name:
            by_name = (
                self.db.query(Device)
                .filter(or_(Device.name == host_name, Device.hostname == host_name))
                .first()
            )
            if by_name:
                discovered.status = "existing"
                discovered.matched_device_id = by_name.id
                self.db.commit()
                self._maybe_dispatch_hint_prefetch(job, by_name, discovered)
                return by_name
            normalized = self._normalize_host_key(host_name)
            if normalized:
                all_devices = self.db.query(Device).all()
                for d in all_devices:
                    if self._normalize_host_key(getattr(d, "name", None)) == normalized or self._normalize_host_key(getattr(d, "hostname", None)) == normalized:
                        discovered.status = "existing"
                        discovered.matched_device_id = d.id
                        self.db.commit()
                        self._maybe_dispatch_hint_prefetch(job, d, discovered)
                        return d
        
        # Check if IP already exists to prevent duplicate key error
        existing = self.db.query(Device).filter(Device.ip_address == discovered.ip_address).first()
        if existing: 
            logger.info("Device already exists", extra={"device_id": existing.id})
            discovered.status = "existing"
            discovered.matched_device_id = existing.id
            self.db.commit()
            self._maybe_dispatch_hint_prefetch(job, existing, discovered)
            return existing

        discovered_mac = str(getattr(discovered, "mac_address", None) or "").strip().lower()
        if discovered_mac:
            existing_by_mac = self.db.query(Device).filter(Device.mac_address == discovered_mac).first()
            if not existing_by_mac:
                d_norm = self._normalize_mac_key(discovered_mac)
                if d_norm:
                    for d in self.db.query(Device).filter(Device.mac_address.isnot(None)).all():
                        if self._normalize_mac_key(getattr(d, "mac_address", None)) == d_norm:
                            existing_by_mac = d
                            break
            if existing_by_mac:
                logger.info("Device already exists by MAC", extra={"device_id": existing_by_mac.id})
                discovered.status = "existing"
                discovered.matched_device_id = existing_by_mac.id
                self.db.commit()
                self._maybe_dispatch_hint_prefetch(job, existing_by_mac, discovered)
                return existing_by_mac

        # Determine Device Type (Canonical)
        # Default to 'cisco_ios' to ensure successful creation
        device_type = "cisco_ios" 
        
        # 1. Use type discovered by SNMP or Scan Logic
        discovered_type = str(getattr(discovered, "device_type", "") or "").strip().lower()
        driver = get_driver_for_vendor(
            getattr(discovered, "vendor", None),
            sys_descr=getattr(discovered, "sys_descr", None) or "",
            model=getattr(discovered, "model", None) or "",
            sys_oid=getattr(discovered, "sys_object_id", None) or "",
            sys_name=getattr(discovered, "hostname", None) or "",
        )
        if driver and driver != "unknown":
            device_type = driver
        elif discovered_type and discovered_type != "unknown":
            device_type = discovered_type
        else:
            # Fallback based on vendor string (Case-insensitive check)
            v_lower = (discovered.vendor or "").lower()
            if "cisco" in v_lower: device_type = "cisco_ios"
            elif "juniper" in v_lower: device_type = "juniper_junos"
            elif "arista" in v_lower: device_type = "arista_eos"
            elif "huawei" in v_lower: device_type = "huawei"
            elif "hp" in v_lower: device_type = "hp_procurve"
            elif "dell" in v_lower: device_type = "dell_os10"
            elif "extreme" in v_lower: device_type = "extreme_exos"
            elif "fortinet" in v_lower: device_type = "fortinet"
            # Korean Vendors 
            elif "dasan" in v_lower: device_type = "dasan_nos"
            elif "ubiquoss" in v_lower: device_type = "ubiquoss_l2"
            elif "handream" in v_lower: device_type = "handream_sg"
            elif "soltech" in v_lower: device_type = "soltech_switch"
            elif "coreedge" in v_lower or "core edge" in v_lower: device_type = "coreedge_switch"
            elif v_lower == "nst" or "nst " in v_lower or "nst ic" in v_lower: device_type = "nst_switch"
            elif "linux" in v_lower: device_type = "linux"
            elif "windows" in v_lower: device_type = "windows_cmd" 

            # Special case for "Unknown" but reachable (SSH/Netconf)
            # Default is already cisco_ios, so no explicit else needed, 
            # but we ensure it's set if currently unknown
        
        try:
            # Defensive check for required fields even though DB might have defaults
            hostname = discovered.hostname if discovered.hostname else f"Device-{discovered.ip_address}"
            model = discovered.model if discovered.model else "Unknown Model"
            version = discovered.os_version if discovered.os_version else "Unknown Version"

            LicensePolicyService.assert_can_add_devices(
                self.db,
                source="discovery_approve",
            )

            # Create new Device
            default_ssh_username = self._get_setting_value("default_ssh_username")
            default_ssh_password = self._get_setting_value("default_ssh_password")
            default_enable_password = self._get_setting_value("default_enable_password")

            support = DeviceSupportPolicyService.evaluate_metadata(
                self.db,
                site_id=(getattr(job, "site_id", None) if job else None),
                device_type=str(device_type or ""),
                os_version=str(version or ""),
                model=str(model or ""),
                hostname=str(hostname or ""),
            )
            if not bool((support.get("features") or {}).get("discovery", True)):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "DEVICE_SUPPORT_BLOCKED",
                        "message": "Discovery approval is blocked for this vendor tier.",
                        "details": {
                            "feature": "discovery",
                            "ip_address": str(discovered.ip_address or ""),
                            "hostname": str(hostname or ""),
                            "device_type": str(device_type or ""),
                            "tier": support.get("tier"),
                            "fallback_mode": support.get("fallback_mode"),
                            "reasons": list(support.get("reasons") or []),
                        },
                    },
                )
            support_variables = {
                "tier": support.get("tier"),
                "fallback_mode": support.get("fallback_mode"),
                "features": support.get("features"),
                "reasons": support.get("reasons"),
            }

            new_device = Device(
                name=hostname,
                ip_address=discovered.ip_address,
                device_type=device_type,
                status="reachable", # Assume reachable since we are approving it
                site_id=(getattr(job, "site_id", None) if job else None),
                model=model,
                os_version=version,
                mac_address=discovered.mac_address,
                snmp_community=(job.snmp_community if job and job.snmp_community else "public"),
                snmp_version=(getattr(job, "snmp_version", None) or "v2c"),
                snmp_port=int(getattr(job, "snmp_port", None) or 161),
                snmp_v3_username=getattr(job, "snmp_v3_username", None),
                snmp_v3_security_level=getattr(job, "snmp_v3_security_level", None),
                snmp_v3_auth_proto=getattr(job, "snmp_v3_auth_proto", None),
                snmp_v3_auth_key=getattr(job, "snmp_v3_auth_key", None),
                snmp_v3_priv_proto=getattr(job, "snmp_v3_priv_proto", None),
                snmp_v3_priv_key=getattr(job, "snmp_v3_priv_key", None),
                ssh_username=(default_ssh_username or "admin"),
                ssh_password=(default_ssh_password or None),
                enable_password=(default_enable_password or None),
                variables={"support_policy": support_variables},
            )
            self.db.add(new_device)
            self.db.flush() # Flush to get ID, but don't commit yet
            
            # Update Discovered Record
            discovered.status = "approved"
            discovered.matched_device_id = new_device.id
            
            self.db.commit()
            PreviewManagedNodeService.reconcile_managed_devices(self.db)
            MonitoringProfileService.ensure_assignment(self.db, new_device, commit=True)
            self.db.refresh(new_device)
            logger.info("Device approved successfully", extra={"device_id": new_device.id})
            self._maybe_dispatch_hint_prefetch(job, new_device, discovered)
            return new_device

        except LicensePolicyViolation as exc:
            issues = list(getattr(discovered, "issues", None) or [])
            issues.append(
                {
                    "severity": "error",
                    "code": "license_policy_blocked",
                    "message": str(exc),
                }
            )
            discovered.issues = issues
            discovered.status = "new"
            self.db.commit()
            raise
        except Exception as e:
            self.db.rollback()
            logger.exception("Failed to approve device")
            raise e

    def auto_approve_job(self, job_id: int) -> dict:
        job = self.db.query(DiscoveryJob).filter(DiscoveryJob.id == int(job_id)).first()
        if not job:
            return {
                "approved_count": 0,
                "skipped_count": 0,
                "device_ids": [],
                "skip_breakdown": {},
                "policy": {"enabled": False, "reason": "job_not_found"},
            }

        def _get_setting_value(key: str) -> str:
            setting = self.db.query(SystemSetting).filter(SystemSetting.key == key).first()
            return str(setting.value) if setting and setting.value and setting.value != "********" else ""

        enabled = (_get_setting_value("auto_approve_enabled") or "false").strip().lower() in ("true", "1", "yes", "y", "on")
        discovered_list = (
            self.db.query(DiscoveredDevice)
            .filter(DiscoveredDevice.job_id == job.id, DiscoveredDevice.status == "new")
            .order_by(DiscoveredDevice.id.asc())
            .all()
        )
        if not enabled:
            return {
                "approved_count": 0,
                "skipped_count": len(discovered_list),
                "device_ids": [],
                "skip_breakdown": {"policy_disabled": len(discovered_list)},
                "policy": {"enabled": False, "reason": "policy_disabled"},
            }

        try:
            min_conf = float(_get_setting_value("auto_approve_min_vendor_confidence") or 0.8)
        except Exception:
            min_conf = 0.8
        if min_conf < 0:
            min_conf = 0.0
        if min_conf > 1:
            min_conf = 1.0

        require_snmp = (_get_setting_value("auto_approve_require_snmp_reachable") or "true").strip().lower() in ("true", "1", "yes", "y", "on")
        block_sev_raw = (_get_setting_value("auto_approve_block_severities") or "error").strip()
        blocked = set([s.strip().lower() for s in block_sev_raw.replace("\n", ",").split(",") if s.strip()])
        if not blocked:
            blocked = {"error"}
        try:
            low_conf_threshold = float(_get_setting_value("topology_candidate_low_confidence_threshold") or 0.7)
        except Exception:
            low_conf_threshold = 0.7
        if low_conf_threshold < 0:
            low_conf_threshold = 0.0
        if low_conf_threshold > 1:
            low_conf_threshold = 1.0

        low_conf_rows = (
            self.db.query(TopologyNeighborCandidate.mgmt_ip)
            .filter(TopologyNeighborCandidate.discovery_job_id == job.id)
            .filter(TopologyNeighborCandidate.confidence < float(low_conf_threshold))
            .all()
        )
        low_conf_ips = set([str(ip or "").strip() for (ip,) in low_conf_rows if str(ip or "").strip()])

        approved_ids: list[int] = []
        skip_breakdown = {
            "low_vendor_confidence": 0,
            "snmp_unreachable": 0,
            "blocked_issue_severity": 0,
            "low_confidence_link": 0,
            "capability_policy": 0,
            "approve_exception": 0,
        }
        for d in discovered_list:
            try:
                conf = float(getattr(d, "vendor_confidence", 0.0) or 0.0)
            except Exception:
                conf = 0.0
            if conf < min_conf:
                skip_breakdown["low_vendor_confidence"] += 1
                continue
            if require_snmp and str(getattr(d, "snmp_status", "") or "").strip().lower() != "reachable":
                skip_breakdown["snmp_unreachable"] += 1
                continue
            if str(getattr(d, "ip_address", "") or "").strip() in low_conf_ips:
                skip_breakdown["low_confidence_link"] += 1
                continue
            issues = getattr(d, "issues", None)
            if isinstance(issues, list) and blocked:
                bad = False
                for it in issues:
                    if not isinstance(it, dict):
                        continue
                    sev = str(it.get("severity") or "").strip().lower()
                    if sev and sev in blocked:
                        bad = True
                        break
                if bad:
                    skip_breakdown["blocked_issue_severity"] += 1
                    continue

            inferred_device_type = get_driver_for_vendor(
                getattr(d, "vendor", None),
                sys_descr=getattr(d, "sys_descr", None) or "",
                model=getattr(d, "model", None) or "",
                sys_oid=getattr(d, "sys_object_id", None) or "",
                sys_name=getattr(d, "hostname", None) or "",
            ) or str(getattr(d, "device_type", "") or "").strip().lower()
            capability = CapabilityProfileService.get_effective_policy(
                self.db,
                site_id=getattr(job, "site_id", None),
                device_type=inferred_device_type,
            )
            if bool(capability.get("read_only", False)) or not bool((capability.get("auto_reflection") or {}).get("approval", True)):
                skip_breakdown["capability_policy"] += 1
                continue

            try:
                device = self.approve_device(d.id)
                if device:
                    approved_ids.append(int(device.id))
            except Exception:
                skip_breakdown["approve_exception"] += 1
                continue
        skipped = len(discovered_list) - len(approved_ids)

        try:
            self._append_job_log(job, f"Auto Approve: approved={len(approved_ids)} skipped={max(0, skipped)}")
            self.db.commit()
        except Exception:
            pass

        trigger_topology = (_get_setting_value("auto_approve_trigger_topology") or "false").strip().lower() in ("true", "1", "yes", "y", "on")
        trigger_sync = (_get_setting_value("auto_approve_trigger_sync") or "false").strip().lower() in ("true", "1", "yes", "y", "on")
        trigger_monitoring = (_get_setting_value("auto_approve_trigger_monitoring") or "false").strip().lower() in ("true", "1", "yes", "y", "on")
        try:
            topo_depth = int(_get_setting_value("auto_approve_topology_depth") or 2)
        except Exception:
            topo_depth = 2
        topo_depth = max(1, min(6, topo_depth))

        if approved_ids and trigger_topology:
            try:
                from app.tasks.topology_dispatch import dispatch_topology_refresh
                for did in approved_ids:
                    try:
                        device = self.db.query(Device).filter(Device.id == did).first()
                        if device and CapabilityProfileService.allow_auto_action(self.db, device, "topology"):
                            dispatch_topology_refresh(
                                did,
                                discovery_job_id=job.id,
                                max_depth=topo_depth,
                                idempotency_key=f"auto-approve:{job.id}:{did}:topology",
                            )
                    except Exception:
                        continue
            except Exception:
                pass

        if approved_ids and trigger_monitoring:
            try:
                from app.tasks.monitoring import burst_monitor_devices
                burst_monitor_devices.delay(approved_ids, 3, 5)
            except Exception:
                pass

        if approved_ids and trigger_sync:
            try:
                enabled_sync = (_get_setting_value("auto_sync_enabled") or "true").strip().lower() in ("true", "1", "yes", "y", "on")
                interval = float(_get_setting_value("auto_sync_interval_seconds") or 3)
                jitter = float(_get_setting_value("auto_sync_jitter_seconds") or 0.5)
                allowed_sync_ids = []
                for did in approved_ids:
                    device = self.db.query(Device).filter(Device.id == did).first()
                    if device and CapabilityProfileService.allow_auto_action(self.db, device, "sync"):
                        allowed_sync_ids.append(did)
                if enabled_sync and allowed_sync_ids:
                    from app.tasks.device_sync import schedule_ssh_sync_batch
                    schedule_ssh_sync_batch(
                        allowed_sync_ids,
                        interval,
                        jitter,
                        f"auto-approve:{job.id}",
                    )
                elif allowed_sync_ids:
                    from app.tasks.device_sync import dispatch_device_sync
                    for did in allowed_sync_ids:
                        dispatch_device_sync(did, idempotency_key=f"auto-approve:{job.id}:{did}")
            except Exception:
                from app.tasks.device_sync import dispatch_device_sync
                for did in approved_ids:
                    device = self.db.query(Device).filter(Device.id == did).first()
                    if device and CapabilityProfileService.allow_auto_action(self.db, device, "sync"):
                        dispatch_device_sync(did, idempotency_key=f"auto-approve:{job.id}:{did}")

        return {
            "approved_count": len(approved_ids),
            "skipped_count": max(0, skipped),
            "device_ids": approved_ids,
            "skip_breakdown": {k: int(v) for k, v in skip_breakdown.items() if int(v) > 0},
            "policy": {
                "enabled": True,
                "min_vendor_confidence": float(min_conf),
                "require_snmp_reachable": bool(require_snmp),
                "block_severities": sorted(list(blocked)),
                "low_confidence_threshold": float(low_conf_threshold),
            },
        }

    def _get_setting_value(self, key: str) -> str:
        setting = self.db.query(SystemSetting).filter(SystemSetting.key == key).first()
        return setting.value if setting and setting.value and setting.value != "********" else ""
