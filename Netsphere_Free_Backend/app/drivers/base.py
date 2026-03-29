from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import json
import re
import os
import time

class NetworkDriver(ABC):
    """
    Abstract Base Class for all Network Drivers.
    This defines the standard interface that the core system uses to interact with devices.
    """
    
    def __init__(self, hostname: str, username: str, password: str, port: int = 22, secret: Optional[str] = None):
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.secret = secret
        self.connection = None
        self.last_error = None

    @abstractmethod
    def connect(self) -> bool:
        """Establish connection to the device."""
        pass

    @abstractmethod
    def disconnect(self):
        """Close the connection."""
        pass

    @abstractmethod
    def check_connection(self) -> bool:
        """Check if connection is still alive."""
        pass

    @abstractmethod
    def get_facts(self) -> Dict[str, Any]:
        """
        Return standardized device facts.
        Expected keys: vendor, model, os_version, serial_number, uptime, hostname
        """
        pass

    @abstractmethod
    def get_interfaces(self) -> List[Dict[str, Any]]:
        """
        Return list of interfaces with standardized keys.
        Expected keys per item: name, description, is_up, is_enabled, ip_address, subnet_mask, mac_address
        """
        pass

    @abstractmethod
    def push_config(self, config_commands: List[str]) -> Dict[str, Any]:
        """
        Push configuration commands to the device.
        Returns: {success: bool, output: str, error: str}
        """
        pass
    
    @abstractmethod
    def get_config(self, source: str = "running") -> str:
        """Get full configuration (running or startup)."""
        pass

    @abstractmethod
    def get_neighbors(self) -> List[Dict[str, Any]]:
        """
        Return list of neighbors (CDP/LLDP).
        """
        pass

    def prepare_rollback(self, snapshot_name: str) -> bool:
        return False

    def rollback(self) -> bool:
        return False

    # ================================================================
    # SWIM (Software Image Management) Methods
    # ================================================================
    
    @abstractmethod
    def transfer_file(self, local_path: str, remote_path: str = None, file_system: str = None) -> bool:
        """
        Transfer a file to the device (SCP/SFTP).
        """
        pass

    @abstractmethod
    def verify_image(self, file_path: str, expected_checksum: str) -> bool:
        """
        Verify the integrity of a file on the device (MD5/SHA).
        """
        pass
        
    @abstractmethod
    def set_boot_variable(self, file_path: str) -> bool:
        """
        Configure the device to boot from the specified image.
        """
        pass
        
    @abstractmethod
    def reload(self, save_config: bool = True):
        """
        Reboot the device.
        """
        pass

    # ================================================================
    # L3 Topology Discovery Methods (Optional - default returns empty)
    # ================================================================

    def get_ospf_neighbors(self) -> List[Dict[str, Any]]:
        """
        Return list of OSPF neighbors.
        Expected keys per item:
          - neighbor_id: str (Router ID)
          - neighbor_ip: str (IP address)
          - state: str (e.g. FULL, 2WAY)
          - interface: str (local interface)
          - area: str (OSPF area)
          - priority: int
        """
        return []

    def get_bgp_neighbors(self) -> List[Dict[str, Any]]:
        """
        Return list of BGP neighbors.
        Expected keys per item:
          - neighbor_ip: str (Peer IP)
          - remote_as: int (Remote ASN)
          - state: str (e.g. Established, Idle)
          - uptime: str
          - prefixes_received: int
          - local_as: int
        """
        return []

    @abstractmethod
    def get_gnmi_telemetry(self, port: int = 57400) -> Dict[str, Any]:
        """
        Get telemetry using gNMI (gRPC).
        Returns standardized dictionary similar to get_system_metrics but fetched via gNMI.
        Should raise NotImplementedError or specific ConnectionError if fails.
        """
        pass

    def _gnmi_path_to_str(self, path: Any) -> str:
        if isinstance(path, str):
            return path
        if isinstance(path, dict):
            elems = path.get("elem") or []
            parts: List[str] = []
            for e in elems:
                if not isinstance(e, dict):
                    continue
                name = e.get("name")
                if not name:
                    continue
                key = e.get("key")
                if isinstance(key, dict) and key:
                    key_parts = [f"{k}={v}" for k, v in key.items()]
                    parts.append(f"{name}[{','.join(key_parts)}]")
                else:
                    parts.append(str(name))
            return "/" + "/".join(parts)
        return str(path)

    def _gnmi_value_to_python(self, val: Any) -> Any:
        if isinstance(val, dict):
            for k in ("intVal", "uintVal", "floatVal", "doubleVal", "stringVal", "boolVal", "jsonVal", "jsonIetfVal"):
                if k in val:
                    v = val.get(k)
                    if k in ("jsonVal", "jsonIetfVal"):
                        if isinstance(v, (bytes, bytearray)):
                            try:
                                v = v.decode()
                            except Exception:
                                return v
                        if isinstance(v, str):
                            try:
                                return json.loads(v)
                            except Exception:
                                return v
                    return v
        return val

    def _gnmi_extract_interface(self, path_str: str, elems: List[dict] | None) -> str | None:
        if elems:
            for e in elems:
                if isinstance(e, dict) and e.get("name") == "interface":
                    key = e.get("key") or {}
                    name = key.get("name") or key.get("id")
                    if name:
                        return str(name)
        if path_str:
            m = re.search(r"interface\[(?:name=)?([^\]]+)\]", path_str)
            if m:
                return m.group(1)
            m = re.search(r"/interface/([^/]+)/", path_str)
            if m:
                return m.group(1)
        return None

    def _collect_gnmi_metrics(self, port: int = 57400) -> Dict[str, Any]:
        try:
            from pygnmi.client import gNMIclient
        except ImportError:
            raise NotImplementedError("gNMI library 'pygnmi' not installed.")

        mode = str(os.getenv("GNMI_MODE", "stream")).lower()
        sample_interval_sec = float(os.getenv("GNMI_SAMPLE_INTERVAL_SEC", "1"))
        stream_window_sec = float(os.getenv("GNMI_STREAM_WINDOW_SEC", "3"))
        max_updates = int(os.getenv("GNMI_MAX_UPDATES", "2000"))

        if mode == "stream":
            try:
                return self._collect_gnmi_metrics_stream(
                    gNMIclient=gNMIclient,
                    port=port,
                    sample_interval_sec=sample_interval_sec,
                    window_sec=stream_window_sec,
                    max_updates=max_updates,
                )
            except Exception:
                return self._collect_gnmi_metrics_get(gNMIclient=gNMIclient, port=port)

        return self._collect_gnmi_metrics_get(gNMIclient=gNMIclient, port=port)

    def _collect_gnmi_metrics_get(self, gNMIclient, port: int = 57400) -> Dict[str, Any]:
        target = (self.hostname, int(port or 57400))
        paths = [
            "/system/processes/process/state/cpu-utilization",
            "/system/state/memory/utilization",
            "/interfaces/interface/state/counters",
            "/interfaces/interface/state/oper-status",
        ]
        with gNMIclient(target=target, username=self.username, password=self.password, insecure=True) as gc:
            resp = gc.get(path=paths)

        notifications = resp.get("notification") or []
        cpu_vals: List[float] = []
        mem_vals: List[float] = []
        if_counters: Dict[str, Dict[str, Any]] = {}

        for n in notifications:
            updates = n.get("update") or []
            for u in updates:
                path = u.get("path")
                path_str = self._gnmi_path_to_str(path)
                elems = path.get("elem") if isinstance(path, dict) else None
                val = self._gnmi_value_to_python(u.get("val"))
                if val is None:
                    continue
                self._ingest_gnmi_path_value(
                    path_str=str(path_str),
                    path_elems=elems,
                    val=val,
                    cpu_vals=cpu_vals,
                    mem_vals=mem_vals,
                    if_counters=if_counters,
                )

        total_in, total_out = self._sum_octets(if_counters)
        cpu = sum(cpu_vals) / len(cpu_vals) if cpu_vals else 0.0
        mem = sum(mem_vals) / len(mem_vals) if mem_vals else 0.0

        return {
            "cpu_usage": float(cpu),
            "memory_usage": float(mem),
            "raw_octets_in": int(total_in),
            "raw_octets_out": int(total_out),
            "if_counters": if_counters,
            "raw_gnmi": resp,
        }

    def _collect_gnmi_metrics_stream(
        self,
        gNMIclient,
        port: int = 57400,
        sample_interval_sec: float = 1.0,
        window_sec: float = 3.0,
        max_updates: int = 2000,
    ) -> Dict[str, Any]:
        target = (self.hostname, int(port or 57400))
        sample_interval_ns = int(max(sample_interval_sec, 0.1) * 1_000_000_000)
        subscribe = {
            "mode": "stream",
            "encoding": "json_ietf",
            "subscription": [
                {"path": "/system/processes/process/state/cpu-utilization", "mode": "sample", "sample_interval": sample_interval_ns},
                {"path": "/system/state/memory/utilization", "mode": "sample", "sample_interval": sample_interval_ns},
                {"path": "/interfaces/interface/state/counters", "mode": "sample", "sample_interval": sample_interval_ns},
                {"path": "/interfaces/interface/state/oper-status", "mode": "on_change"},
            ],
        }

        cpu_vals: List[float] = []
        mem_vals: List[float] = []
        if_counters: Dict[str, Dict[str, Any]] = {}
        raw_msgs: List[dict] = []

        end_ts = time.time() + max(window_sec, 0.5)
        with gNMIclient(target=target, username=self.username, password=self.password, insecure=True) as gc:
            sub = gc.subscribe_stream(subscribe=subscribe)
            while True:
                remaining = end_ts - time.time()
                if remaining <= 0:
                    break
                try:
                    msg = sub.get_update(timeout=remaining)
                except TimeoutError:
                    break
                if not isinstance(msg, dict):
                    continue
                if len(raw_msgs) < max_updates:
                    raw_msgs.append(msg)
                upd = msg.get("update") or {}
                prefix = upd.get("prefix")
                updates = upd.get("update") or []
                if not isinstance(updates, list):
                    continue
                for u in updates:
                    if not isinstance(u, dict):
                        continue
                    path = u.get("path")
                    val = u.get("val")
                    if path is None or val is None:
                        continue
                    full_path = self._join_gnmi_prefix(prefix, path)
                    self._ingest_gnmi_path_value(
                        path_str=full_path,
                        path_elems=None,
                        val=val,
                        cpu_vals=cpu_vals,
                        mem_vals=mem_vals,
                        if_counters=if_counters,
                    )

        total_in, total_out = self._sum_octets(if_counters)
        cpu = sum(cpu_vals) / len(cpu_vals) if cpu_vals else 0.0
        mem = sum(mem_vals) / len(mem_vals) if mem_vals else 0.0

        return {
            "cpu_usage": float(cpu),
            "memory_usage": float(mem),
            "raw_octets_in": int(total_in),
            "raw_octets_out": int(total_out),
            "if_counters": if_counters,
            "raw_gnmi": raw_msgs,
        }

    def _join_gnmi_prefix(self, prefix: Any, path: Any) -> str:
        prefix_str = "" if prefix is None else str(prefix)
        path_str = "" if path is None else str(path)
        if not prefix_str and path_str:
            return path_str if path_str.startswith("/") else "/" + path_str
        if not path_str:
            return prefix_str if prefix_str.startswith("/") else "/" + prefix_str
        p = prefix_str.lstrip("/")
        s = path_str.lstrip("/")
        return "/" + "/".join([x for x in (p, s) if x])

    def _sum_octets(self, if_counters: Dict[str, Dict[str, Any]]) -> tuple[int, int]:
        total_in = 0
        total_out = 0
        for v in if_counters.values():
            try:
                total_in += int(v.get("in_octets", 0) or 0)
            except Exception:
                pass
            try:
                total_out += int(v.get("out_octets", 0) or 0)
            except Exception:
                pass
        return total_in, total_out

    def _ingest_gnmi_path_value(
        self,
        path_str: str,
        path_elems: List[dict] | None,
        val: Any,
        cpu_vals: List[float],
        mem_vals: List[float],
        if_counters: Dict[str, Dict[str, Any]],
    ) -> None:
        path_lower = str(path_str).lower()

        if "cpu" in path_lower and "util" in path_lower:
            try:
                cpu_vals.append(float(val))
            except Exception:
                pass
            return
        if "memory" in path_lower and "util" in path_lower:
            try:
                mem_vals.append(float(val))
            except Exception:
                pass
            return

        if "/interfaces/interface" not in path_lower:
            return

        if "oper-status" in path_lower:
            if_name = self._gnmi_extract_interface(path_str, path_elems)
            if not if_name:
                return
            entry = if_counters.get(if_name)
            if entry is None:
                entry = {}
                if_counters[if_name] = entry
            try:
                oper = str(val)
            except Exception:
                oper = ""
            entry["oper_status"] = oper
            entry["is_up"] = str(oper).strip().lower() in {"up", "active", "true", "1"}
            return

        if "counters" not in path_lower:
            return

        if_name = self._gnmi_extract_interface(path_str, path_elems)
        if not if_name:
            return
        entry = if_counters.get(if_name)
        if entry is None:
            entry = {}
            if_counters[if_name] = entry

        def _assign_counter(key: str, value: Any) -> None:
            try:
                entry[key] = int(value)
            except Exception:
                entry[key] = 0

        if isinstance(val, dict):
            for k, v in val.items():
                k_norm = str(k).lower().replace("_", "-")
                if "in-octets" in k_norm:
                    _assign_counter("in_octets", v)
                elif "out-octets" in k_norm:
                    _assign_counter("out_octets", v)
                elif "in-errors" in k_norm:
                    _assign_counter("in_errors", v)
                elif "out-errors" in k_norm:
                    _assign_counter("out_errors", v)
                elif "in-discards" in k_norm:
                    _assign_counter("in_discards", v)
                elif "out-discards" in k_norm:
                    _assign_counter("out_discards", v)
            return

        if "in-octets" in path_lower or "in_octets" in path_lower:
            _assign_counter("in_octets", val)
        elif "out-octets" in path_lower or "out_octets" in path_lower:
            _assign_counter("out_octets", val)
        elif "in-errors" in path_lower or "in_errors" in path_lower:
            _assign_counter("in_errors", val)
        elif "out-errors" in path_lower or "out_errors" in path_lower:
            _assign_counter("out_errors", val)
        elif "in-discards" in path_lower or "in_discards" in path_lower:
            _assign_counter("in_discards", val)
        elif "out-discards" in path_lower or "out_discards" in path_lower:
            _assign_counter("out_discards", val)
