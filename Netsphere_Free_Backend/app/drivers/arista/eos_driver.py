"""
Arista EOS Driver using Netmiko (SSH).
Replaces NAPALM/eAPI implementation for better compatibility and simplicity.
"""
from app.drivers.base import NetworkDriver
try:
    from netmiko import ConnectHandler
except Exception:  # pragma: no cover
    ConnectHandler = None
from typing import Dict, List, Any, Optional
import re
import os
import logging
import uuid

logger = logging.getLogger(__name__)

# Set NTC_TEMPLATES_DIR for netmiko to find templates (same as Cisco driver)
try:
    import ntc_templates
    NTC_TEMPLATES_DIR = os.path.dirname(ntc_templates.__file__) + "/templates"
    os.environ.setdefault("NET_TEXTFSM", NTC_TEMPLATES_DIR)
except ImportError:
    NTC_TEMPLATES_DIR = None


class AristaEOSDriver(NetworkDriver):
    """
    Arista EOS Driver using Netmiko (SSH).
    """
    
    DEVICE_TYPE = "arista_eos"
    
    def connect(self) -> bool:
        """Establish SSH connection to Arista device."""
        try:
            if not ConnectHandler:
                raise ModuleNotFoundError("netmiko is not installed")
            self.connection = ConnectHandler(
                device_type=self.DEVICE_TYPE,
                host=self.hostname,
                username=self.username,
                password=self.password,
                secret=self.secret,
                port=self.port,  # Uses SSH port (22)
                global_delay_factor=2,
                banner_timeout=30,
                auth_timeout=30,
                conn_timeout=60,
                fast_cli=False
            )
            if self.secret:
                self.connection.enable()
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.warning("AristaEOSDriver connection error error=%s", e)
            return False

    def disconnect(self):
        if self.connection:
            self.connection.disconnect()
            self.connection = None

    def check_connection(self) -> bool:
        if not self.connection:
            return False
        return self.connection.is_alive()

    def get_facts(self) -> Dict[str, Any]:
        """
        Get device facts using 'show version'.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        try:
            output = self.connection.send_command("show version")
            
            # Arista IOS style output
            version_match = re.search(r"Software image version:\s+(\S+)", output)
            model_match = re.search(r"Hardware version:\s+(\S+)", output)
            serial_match = re.search(r"Serial number:\s+(\S+)", output)
            uptime_match = re.search(r"Uptime:\s+(.+)", output)
            
            # Hostname is usually in prompt
            prompt = self.connection.find_prompt().replace("#", "").replace(">", "").strip()

            return {
                "vendor": "Arista",
                "os_version": version_match.group(1) if version_match else "Unknown",
                "model": "vEOS" if "vEOS" in output else (model_match.group(1) if model_match else "Unknown"),
                "serial_number": serial_match.group(1) if serial_match else "Unknown",
                "uptime": uptime_match.group(1) if uptime_match else "Unknown",
                "hostname": prompt
            }
        except Exception as e:
            self.last_error = str(e)
            return {"vendor": "Arista", "model": "Unknown", "os_version": "Unknown", 
                    "hostname": self.hostname, "uptime": "Unknown"}

    def get_interfaces(self) -> List[Dict[str, Any]]:
        """
        Get interfaces using 'show interfaces'.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        interfaces = []
        try:
            # Use TextFSM if available
            parsed = self.connection.send_command("show interfaces", use_textfsm=True)
            
            # Simple fallback if TextFSM fails or returns string
            if isinstance(parsed, str):
                 # Fallback to ip int brief for simple list
                 brief = self.connection.send_command("show ip interface brief")
                 for line in brief.splitlines():
                     if "Interface" in line or not line.strip(): continue
                     parts = line.split()
                     if len(parts) >= 2:
                         interfaces.append({
                             "name": parts[0],
                             "ip_address": parts[1] if parts[1] != "unassigned" else "",
                             "is_up": "up" in line.lower(),
                             "is_enabled": "up" in line.lower(),
                             "mac_address": ""
                         })
                 return interfaces

            for entry in parsed:
                 is_up = entry.get("link_status", "").lower() == "up" or entry.get("protocol_status", "").lower() == "up"
                 interfaces.append({
                     "name": entry.get("interface", ""),
                     "description": entry.get("description", ""),
                     "is_up": is_up,
                     "is_enabled": entry.get("admin_status", "").lower() == "up",
                     "ip_address": entry.get("ip_address", ""),
                     "mac_address": entry.get("hardware_address", ""),
                     "mtu": entry.get("mtu", 0),
                     "speed": entry.get("bandwidth", 0)
                 })
                 
        except Exception as e:
            self.last_error = str(e)
            logger.warning("AristaEOSDriver get_interfaces error=%s", e)
            
        return interfaces

    def push_config(self, config_commands: List[str]) -> Dict[str, Any]:
        if not self.connection:
            raise ConnectionError("Not connected")
        try:
            output = self.connection.send_config_set(config_commands)
            self.connection.send_command("write memory")
            return {"success": True, "output": output}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def apply_config_replace(self, raw_config: str) -> Dict[str, Any]:
        if not self.connection:
            raise ConnectionError("Not connected")

        filename = f"flash:golden_{uuid.uuid4().hex[:10]}.cfg"
        try:
            out = self.connection.send_command_timing(f"copy terminal: {filename}", read_timeout=120)
            for _ in range(10):
                low = str(out or "").lower()
                if "destination filename" in low or "destination file name" in low:
                    out = self.connection.send_command_timing("\n", read_timeout=120)
                    continue
                if "[confirm]" in low:
                    out = self.connection.send_command_timing("\n", read_timeout=120)
                    continue
                if "enter" in low and "configuration" in low:
                    break
                break

            text = str(raw_config or "")
            if not text.endswith("\n"):
                text += "\n"
            chunk = []
            sent_out = out or ""
            for line in text.splitlines():
                chunk.append(line)
                if len(chunk) >= 200:
                    sent_out = self.connection.send_command_timing("\n".join(chunk) + "\n", read_timeout=120)
                    chunk = []
            if chunk:
                sent_out = self.connection.send_command_timing("\n".join(chunk) + "\n", read_timeout=120)
            sent_out = self.connection.send_command_timing("\x1a", read_timeout=120)

            rep = self.connection.send_command_timing(f"configure replace {filename} force", read_timeout=300)
            for _ in range(10):
                low = str(rep or "").lower()
                if "[confirm]" in low or "proceed" in low or "confirm" in low:
                    rep = self.connection.send_command_timing("\n", read_timeout=300)
                    continue
                break
            self.connection.send_command("write memory", read_timeout=60)
            low = str(rep or "").lower()
            if "error" in low or "invalid" in low or "failed" in low:
                return {"success": False, "error": rep, "ref": filename}
            return {"success": True, "output": f"{sent_out}\n{rep}", "ref": filename}
        except Exception as e:
            self.last_error = str(e)
            return {"success": False, "error": str(e), "ref": filename}

    def prepare_rollback(self, snapshot_name: str) -> bool:
        if not self.connection:
            raise ConnectionError("Not connected")
        snap = f"flash:{snapshot_name}.cfg"
        try:
            out = self.connection.send_command_timing(f"copy running-config {snap}", read_timeout=120)
            for _ in range(6):
                low = str(out or "").lower()
                if "destination filename" in low or "destination file name" in low or "[confirm]" in low:
                    out = self.connection.send_command_timing("\n", read_timeout=120)
                    continue
                if "overwrite" in low and ("confirm" in low or "[y/n]" in low or "(y/n)" in low):
                    out = self.connection.send_command_timing("y\n", read_timeout=120)
                    continue
                break
            self._rollback_ref = snap
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def rollback(self) -> bool:
        if not self.connection:
            raise ConnectionError("Not connected")
        ref = getattr(self, "_rollback_ref", None)
        if not ref:
            return False
        try:
            out = self.connection.send_command_timing(f"configure replace {ref} force", read_timeout=180)
            for _ in range(6):
                low = str(out or "").lower()
                if "[confirm]" in low or "proceed" in low or "confirm" in low:
                    out = self.connection.send_command_timing("\n", read_timeout=180)
                    continue
                break
            self.connection.send_command("write memory", read_timeout=60)
            low = str(out or "").lower()
            if "error" in low or "invalid" in low or "failed" in low:
                return False
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def get_config(self, source: str = "running") -> str:
        if not self.connection:
            raise ConnectionError("Not connected")
        cmd = "show running-config" if source == "running" else "show startup-config"
        return self.connection.send_command(cmd)

    def get_neighbors(self) -> List[Dict[str, Any]]:
        if not self.connection:
            raise ConnectionError("Not connected")
        
        neighbors = []
        try:
            # Try LLDP
            out = self.connection.send_command("show lldp neighbors detail", use_textfsm=True)
            if isinstance(out, list):
                for entry in out:
                    neighbors.append({
                        "neighbor_name": entry.get("neighbor_name", "Unknown"),
                        "mgmt_ip": entry.get("management_ip", ""),
                        "local_interface": entry.get("local_interface", ""),
                        "remote_interface": entry.get("neighbor_interface", ""),
                        "platform": entry.get("system_description", ""),
                        "protocol": "LLDP"
                    })
        except Exception:
            pass
        return neighbors

    # ========== SWIM Methods ==========

    def transfer_file(self, local_path: str, remote_path: str = None, file_system: str = "flash:") -> bool:
        if not self.connection:
            raise ConnectionError("Not connected")
        from netmiko import file_transfer
        if not remote_path: remote_path = os.path.basename(local_path)
        try:
            res = file_transfer(self.connection, source_file=local_path, dest_file=remote_path,
                                file_system=file_system, direction='put', overwrite_file=False)
            return res['file_verified']
        except Exception as e:
            self.last_error = str(e)
            return False

    def verify_image(self, file_path: str, expected_checksum: str) -> bool:
        # Arista verify /md5
        if not self.connection: raise ConnectionError("Not connected")
        try:
            out = self.connection.send_command(f"verify /md5 {file_path}", read_timeout=120)
            return expected_checksum.lower() in out.lower()
        except: return False

    def set_boot_variable(self, file_path: str) -> bool:
        if not self.connection: raise ConnectionError("Not connected")
        try:
            self.push_config([f"boot system {file_path}"])
            return True
        except: return False

    def reload(self, save_config: bool = True):
        if not self.connection: raise ConnectionError("Not connected")
        if save_config: self.connection.send_command("write memory")
        try:
            self.connection.send_command_timing("reload now")
        except: pass

    def get_gnmi_telemetry(self, port: int = 57400) -> Dict[str, Any]:
        try:
            return self._collect_gnmi_metrics(port=port)
        except Exception:
            if not self.connection:
                raise ConnectionError("Not connected")
            try:
                out = self.connection.send_command("show processes top once")
                match = re.search(r"Cpu\(s\):\s+([\d\.]+)%us,\s+([\d\.]+)%sy", out)
                cpu = float(match.group(1)) + float(match.group(2)) if match else 0.0
                out_mem = self.connection.send_command("show version")
                mem_match = re.search(r"KiB Mem :\s+(\d+)\s+total,\s+(\d+)\s+free,\s+(\d+)\s+used", out)
                if mem_match:
                    total = int(mem_match.group(1))
                    used = int(mem_match.group(3))
                    mem = (used / total) * 100
                else:
                    mem = 0.0

                return {
                    "cpu_usage": round(cpu, 1),
                    "memory_usage": round(mem, 1),
                    "temperature": 0,
                    "power_status": "ok",
                    "fan_status": "ok"
                }
            except Exception:
                return {"cpu_usage": 0, "memory_usage": 0}
