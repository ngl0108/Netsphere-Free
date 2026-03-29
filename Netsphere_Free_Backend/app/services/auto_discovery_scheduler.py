from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
import ipaddress

from app.db.session import SessionLocal
from app.models.settings import SystemSetting
from app.services.discovery_service import DiscoveryService


def _get_setting_value(db, key: str) -> str:
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not s or not s.value or s.value == "********":
        return ""
    return str(s.value)


def _parse_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    s = str(value).strip().lower()
    if s == "":
        return default
    return s in ("true", "1", "yes", "y", "on")


def _parse_int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _acquire_lock(db, key: str, ttl_seconds: int = 120) -> bool:
    now = datetime.utcnow()
    lock_until = now + timedelta(seconds=int(ttl_seconds))
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if setting and setting.value:
        try:
            current = datetime.fromisoformat(str(setting.value))
            if current > now:
                return False
        except Exception:
            pass
    if not setting:
        setting = SystemSetting(key=key, value=lock_until.isoformat(), description=key, category="system")
    else:
        setting.value = lock_until.isoformat()
        if not setting.category:
            setting.category = "system"
    db.add(setting)
    db.commit()
    return True


def _set_setting(db, key: str, value: str, category: str = "system", description: str = "") -> None:
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not s:
        s = SystemSetting(key=key, value=str(value), description=description or key, category=category)
    else:
        s.value = str(value)
        if not s.category:
            s.category = category
        if description and not s.description:
            s.description = description
    db.add(s)
    db.commit()


def _parse_cidr_list(raw: str) -> list[str]:
    out = []
    for part in (raw or "").replace("\n", ",").split(","):
        s = part.strip()
        if s:
            out.append(s)
    return out


def _build_scope_checker(db):
    include_raw = _get_setting_value(db, "discovery_scope_include_cidrs")
    exclude_raw = _get_setting_value(db, "discovery_scope_exclude_cidrs")
    include_nets = []
    exclude_nets = []
    for c in _parse_cidr_list(include_raw):
        try:
            include_nets.append(ipaddress.ip_network(str(c).strip(), strict=False))
        except Exception:
            continue
    for c in _parse_cidr_list(exclude_raw):
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


class AutoDiscoveryScheduler:
    def __init__(self):
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_loop, name="auto_discovery_scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t and t.is_alive():
            try:
                t.join(timeout=2.0)
            except Exception:
                pass

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._tick_once()
            except Exception:
                pass
            time.sleep(1.0)

    def _tick_once(self) -> None:
        db = SessionLocal()
        try:
            enabled = _parse_bool(_get_setting_value(db, "auto_discovery_enabled"), default=False)
            if not enabled:
                return

            interval_seconds = _parse_int(_get_setting_value(db, "auto_discovery_interval_seconds"), 1800)
            interval_seconds = max(60, min(86400, interval_seconds))

            if not _acquire_lock(db, "auto_discovery_scheduler_tick_lock", ttl_seconds=max(120, interval_seconds // 2)):
                return

            last_run_raw = _get_setting_value(db, "auto_discovery_last_run_at")
            if last_run_raw:
                try:
                    last_run = datetime.fromisoformat(last_run_raw)
                    if datetime.utcnow() - last_run < timedelta(seconds=interval_seconds):
                        return
                except Exception:
                    pass

            mode = (_get_setting_value(db, "auto_discovery_mode") or "cidr").strip().lower()
            cidr = (_get_setting_value(db, "auto_discovery_cidr") or "").strip()
            seed_ip = (_get_setting_value(db, "auto_discovery_seed_ip") or "").strip()
            seed_device_id_raw = (_get_setting_value(db, "auto_discovery_seed_device_id") or "").strip()
            max_depth = _parse_int(_get_setting_value(db, "auto_discovery_max_depth"), 2)
            max_depth = max(1, min(6, max_depth))

            site_id = _get_setting_value(db, "auto_discovery_site_id").strip()
            snmp_profile_id = _get_setting_value(db, "auto_discovery_snmp_profile_id").strip()
            snmp_version = (_get_setting_value(db, "auto_discovery_snmp_version") or "v2c").strip()
            snmp_port = _parse_int(_get_setting_value(db, "auto_discovery_snmp_port"), 161)
            if snmp_port < 1 or snmp_port > 65535:
                snmp_port = 161

            default_community = (_get_setting_value(db, "default_snmp_community") or "public").strip() or "public"

            svc = DiscoveryService(db)

            _set_setting(db, "auto_discovery_last_error", "", category="system", description="auto discovery last error")

            if mode == "seed":
                if not seed_ip and not seed_device_id_raw:
                    return
                seed_device_id = None
                if seed_device_id_raw:
                    try:
                        seed_device_id = int(seed_device_id_raw)
                    except Exception:
                        seed_device_id = None
                job_cidr = f"seedip:{seed_ip}" if seed_ip else f"seed:{seed_device_id}"
                job = svc.create_scan_job(
                    job_cidr,
                    default_community,
                    site_id=int(site_id) if site_id else None,
                    snmp_profile_id=int(snmp_profile_id) if snmp_profile_id else None,
                    snmp_version=snmp_version,
                    snmp_port=snmp_port,
                )
                launch = self._launch_crawl(job.id, seed_device_id=seed_device_id, seed_ip=seed_ip, max_depth=max_depth)
            else:
                if not cidr:
                    return
                job = svc.create_scan_job(
                    cidr,
                    default_community,
                    site_id=int(site_id) if site_id else None,
                    snmp_profile_id=int(snmp_profile_id) if snmp_profile_id else None,
                    snmp_version=snmp_version,
                    snmp_port=snmp_port,
                )
                launch = self._launch_scan(job.id)

            if launch.get("status") not in {"enqueued", "skipped"}:
                raise RuntimeError(f"discovery dispatch failed: {launch}")

            _set_setting(db, "auto_discovery_last_run_at", datetime.utcnow().isoformat(), category="system", description="auto discovery last run")
            _set_setting(db, "auto_discovery_last_job_id", str(job.id), category="system", description="auto discovery last job id")
            _set_setting(db, "auto_discovery_last_job_cidr", str(job.cidr), category="system", description="auto discovery last job cidr")

            refresh_topology = _parse_bool(_get_setting_value(db, "auto_discovery_refresh_topology"), default=False)
            if refresh_topology:
                topo_max_depth = _parse_int(_get_setting_value(db, "auto_topology_refresh_max_depth"), 2)
                topo_max_depth = max(1, min(6, topo_max_depth))
                topo_max_devices = _parse_int(_get_setting_value(db, "auto_topology_refresh_max_devices"), 200)
                topo_max_devices = max(1, min(2000, topo_max_devices))
                topo_min_interval = float(_get_setting_value(db, "auto_topology_refresh_min_interval_seconds") or "0.05")
                if topo_min_interval < 0:
                    topo_min_interval = 0.0
                self._launch_topology_refresh(job_id=job.id, max_depth=topo_max_depth, max_devices=topo_max_devices, min_interval=topo_min_interval)
        except Exception as e:
            try:
                _set_setting(db, "auto_discovery_last_error", str(e), category="system", description="auto discovery last error")
            except Exception:
                pass
            raise
        finally:
            db.close()

    def _launch_scan(self, job_id: int) -> dict:
        from app.tasks.discovery_dispatch import dispatch_discovery_scan

        return dispatch_discovery_scan(
            int(job_id),
            idempotency_key=f"auto-scheduler-scan:{int(job_id)}",
        )

    def _launch_crawl(self, job_id: int, seed_device_id: int | None, seed_ip: str, max_depth: int) -> dict:
        from app.tasks.discovery_dispatch import dispatch_neighbor_crawl

        return dispatch_neighbor_crawl(
            int(job_id),
            seed_device_id=seed_device_id,
            seed_ip=seed_ip,
            max_depth=int(max_depth or 2),
            idempotency_key=f"auto-scheduler-crawl:{int(job_id)}",
        )

    def _launch_topology_refresh(self, job_id: int, max_depth: int, max_devices: int, min_interval: float) -> None:
        def _run():
            from app.models.device import Device
            from app.tasks.topology_dispatch import dispatch_topology_refresh

            db2 = SessionLocal()
            try:
                if not _acquire_lock(db2, "auto_topology_refresh_lock", ttl_seconds=max(300, int(max_devices) * 2)):
                    return

                _set_setting(db2, "auto_topology_last_error", "", category="system", description="auto topology last error")
                _set_setting(db2, "auto_topology_last_job_id", str(job_id), category="system", description="auto topology last job id")

                is_allowed = _build_scope_checker(db2)

                site_id = None
                try:
                    from app.models.discovery import DiscoveryJob
                    job = db2.query(DiscoveryJob).filter(DiscoveryJob.id == int(job_id)).first()
                    site_id = int(getattr(job, "site_id", None)) if job and getattr(job, "site_id", None) is not None else None
                except Exception:
                    site_id = None

                q = db2.query(Device).filter(Device.ip_address.isnot(None))
                if site_id is not None:
                    q = q.filter(Device.site_id == site_id)

                candidates = q.order_by(Device.id.asc()).limit(int(max_devices) * 3).all()
                devices = []
                for d in candidates:
                    ip0 = str(getattr(d, "ip_address", "") or "").strip()
                    if not ip0:
                        continue
                    if not is_allowed(ip0):
                        continue
                    devices.append(d)
                    if len(devices) >= int(max_devices):
                        break

                _set_setting(db2, "auto_topology_last_run_at", datetime.utcnow().isoformat(), category="system", description="auto topology last run")
                _set_setting(db2, "auto_topology_last_targets", str(len(devices)), category="system", description="auto topology last targets")

                ok = 0
                fail = 0
                skipped = 0
                for d in devices:
                    try:
                        dispatch = dispatch_topology_refresh(
                            d.id,
                            discovery_job_id=job_id,
                            max_depth=max_depth,
                            idempotency_key=f"auto-topology-refresh:{int(job_id)}:{int(d.id)}:{int(max_depth)}",
                        )
                        if dispatch.get("status") == "enqueued":
                            ok += 1
                        elif dispatch.get("status") == "skipped":
                            skipped += 1
                        else:
                            fail += 1
                    except Exception:
                        fail += 1
                    if min_interval and min_interval > 0:
                        time.sleep(float(min_interval))
                _set_setting(db2, "auto_topology_last_enqueued_ok", str(ok), category="system", description="auto topology last enqueued ok")
                _set_setting(db2, "auto_topology_last_enqueued_skipped", str(skipped), category="system", description="auto topology last enqueued skipped")
                _set_setting(db2, "auto_topology_last_enqueued_fail", str(fail), category="system", description="auto topology last enqueued fail")
            finally:
                db2.close()

        threading.Thread(target=_run, name=f"auto_topology_refresh_{job_id}", daemon=True).start()
