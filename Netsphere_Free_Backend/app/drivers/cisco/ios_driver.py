"""
Cisco IOS Driver with TextFSM-based structured parsing.
Uses ntc-templates for reliable, vendor-agnostic data extraction.
"""
from app.drivers.base import NetworkDriver
try:
    from netmiko import ConnectHandler
except Exception:  # pragma: no cover
    ConnectHandler = None
from typing import Dict, List, Any, Optional
import os
import logging
import uuid

logger = logging.getLogger(__name__)

# Set NTC_TEMPLATES_DIR for netmiko to find templates
try:
    import ntc_templates
    NTC_TEMPLATES_DIR = os.path.dirname(ntc_templates.__file__) + "/templates"
    os.environ.setdefault("NET_TEXTFSM", NTC_TEMPLATES_DIR)
except ImportError:
    NTC_TEMPLATES_DIR = None


class CiscoIOSDriver(NetworkDriver):
    """
    Cisco IOS/IOS-XE Driver using TextFSM for structured parsing.
    Supports: show version, show interfaces, show ip interface brief, 
              show cdp neighbors, show lldp neighbors
    """
    
    DEVICE_TYPE = "cisco_ios"
    
    def connect(self) -> bool:
        try:
            if not ConnectHandler:
                raise ModuleNotFoundError("netmiko is not installed")
            self.connection = ConnectHandler(
                device_type=self.DEVICE_TYPE,
                host=self.hostname,
                username=self.username,
                password=self.password,
                secret=self.secret,
                port=self.port,
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
            logger.warning("CiscoIOSDriver connection error error=%s", e)
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
        Get device facts using TextFSM parsed 'show version'.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        # Use TextFSM parsing
        parsed = self.connection.send_command("show version", use_textfsm=True)
        
        # Handle case where TextFSM fails (returns string instead of list)
        if isinstance(parsed, str):
            logger.warning("CiscoIOSDriver TextFSM parsing failed for show version, using raw output")
            return self._parse_version_fallback(parsed)
        
        if not parsed:
            return {"vendor": "Cisco", "os_version": "Unknown", "model": "Unknown", 
                    "serial_number": "Unknown", "uptime": "Unknown", "hostname": self.hostname}
        
        # NTC template returns list of dicts
        data = parsed[0] if parsed else {}
        
        return {
            "vendor": "Cisco",
            "os_version": data.get("version", data.get("software_version", "Unknown")),
            "model": data.get("hardware", ["Unknown"])[0] if isinstance(data.get("hardware"), list) else data.get("hardware", "Unknown"),
            "serial_number": data.get("serial", ["Unknown"])[0] if isinstance(data.get("serial"), list) else data.get("serial", "Unknown"),
            "uptime": data.get("uptime", "Unknown"),
            "hostname": data.get("hostname", self.connection.find_prompt().replace("#", "").strip())
        }

    def get_interfaces(self) -> List[Dict[str, Any]]:
        """
        Get interface details using TextFSM parsed output.
        Combines 'show interfaces' and 'show ip interface brief' for complete picture.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        interfaces = []
        
        # 1. Get brief status (fast, shows up/down status)
        brief_parsed = self.connection.send_command("show ip interface brief", use_textfsm=True)
        brief_map = {}
        
        if isinstance(brief_parsed, list):
            for entry in brief_parsed:
                intf_name = entry.get("intf", entry.get("interface", ""))
                brief_map[intf_name] = {
                    "ip_address": entry.get("ipaddr", entry.get("ip_address", "")),
                    "status": entry.get("status", "down"),
                    "protocol": entry.get("proto", entry.get("protocol", "down")),
                }
        
        # 2. Get detailed interface info (slower but has more details)
        detail_parsed = self.connection.send_command("show interfaces", use_textfsm=True, read_timeout=90)
        
        if isinstance(detail_parsed, list):
            for entry in detail_parsed:
                intf_name = entry.get("interface", "")
                brief_info = brief_map.get(intf_name, {})
                
                # Determine status
                link_status = entry.get("link_status", "down")
                protocol_status = entry.get("protocol_status", "down")
                
                is_up = link_status.lower() in ("up", "connected")
                is_enabled = "administratively" not in link_status.lower()
                
                interfaces.append({
                    "name": intf_name,
                    "description": entry.get("description", ""),
                    "is_up": is_up,
                    "is_enabled": is_enabled,
                    "link_status": link_status,
                    "protocol_status": protocol_status,
                    "ip_address": brief_info.get("ip_address", entry.get("ip_address", "")),
                    "mac_address": entry.get("address", entry.get("mac_address", "")),
                    "mtu": entry.get("mtu", ""),
                    "bandwidth": entry.get("bandwidth", ""),
                    "duplex": entry.get("duplex", ""),
                    "speed": entry.get("speed", ""),
                    "input_errors": entry.get("input_errors", 0),
                    "output_errors": entry.get("output_errors", 0),
                })
        else:
            # Fallback to brief if detail parsing fails
            logger.warning("CiscoIOSDriver TextFSM failed for show interfaces, using brief only")
            for intf_name, info in brief_map.items():
                is_up = info.get("status", "down").lower() == "up"
                interfaces.append({
                    "name": intf_name,
                    "description": "",
                    "is_up": is_up,
                    "is_enabled": True,
                    "link_status": info.get("status", "down"),
                    "protocol_status": info.get("protocol", "down"),
                    "ip_address": info.get("ip_address", ""),
                    "mac_address": "",
                })
        
        return interfaces

    def push_config(self, config_commands: List[str]) -> Dict[str, Any]:
        if not self.connection:
            raise ConnectionError("Not connected")
            
        try:
            output = self.connection.send_config_set(config_commands)
            # Save config
            self.connection.send_command("write memory", read_timeout=30)
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
                if "address or name of remote host" in low:
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
        return self.connection.send_command(cmd, read_timeout=120)

    def get_neighbors(self) -> List[Dict[str, Any]]:
        """
        Get CDP/LLDP neighbors with interface name normalization.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        neighbors = []
        
        def normalize_intf(name: str) -> str:
            if not name: return ""
            # Gi1/0/1 -> GigabitEthernet1/0/1, Fa... -> FastEthernet..., Te... -> TenGigabitEthernet...
            mapping = {
                "gi": "GigabitEthernet",
                "fa": "FastEthernet",
                "te": "TenGigabitEthernet",
                "fo": "FortyGigabitEthernet",
                "hu": "HundredGigabitEthernet",
                "et": "Ethernet",
                "vl": "Vlan",
                "po": "Port-channel"
            }
            name_lower = name.lower()
            for short, full in mapping.items():
                if name_lower.startswith(short) and not name_lower.startswith(full.lower()):
                    # Extract the numeric/port part
                    import re
                    match = re.search(r"(\d.*)", name)
                    if match:
                        return f"{full}{match.group(1)}"
            return name

        # Try CDP first
        cdp_parsed = self.connection.send_command("show cdp neighbors detail", use_textfsm=True)
        
        if isinstance(cdp_parsed, list) and cdp_parsed:
            for entry in cdp_parsed:
                neighbor_name = entry.get("destination_host") or entry.get("dest_host") or entry.get("neighbor") or entry.get("neighbor_name", "Unknown")
                mgmt_ip = entry.get("management_ip") or entry.get("mgmt_address") or entry.get("ip_address") or ""
                local_interface = normalize_intf(entry.get("local_port") or entry.get("local_interface", ""))
                remote_interface = normalize_intf(entry.get("remote_port") or entry.get("neighbor_interface", ""))
                
                neighbors.append({
                    "neighbor_name": neighbor_name,
                    "mgmt_ip": mgmt_ip,
                    "local_interface": local_interface,
                    "remote_interface": remote_interface,
                    "platform": entry.get("platform", ""),
                    "capability": entry.get("capabilities", ""),
                    "protocol": "CDP"
                })
        
        # Also try LLDP
        lldp_parsed = self.connection.send_command("show lldp neighbors detail", use_textfsm=True)
        
        if isinstance(lldp_parsed, list) and lldp_parsed:
            for entry in lldp_parsed:
                neighbor_name = entry.get("neighbor") or entry.get("neighbor_name") or entry.get("device_id") or "Unknown"
                mgmt_ip = entry.get("management_ip") or entry.get("mgmt_address") or ""
                local_interface = normalize_intf(entry.get("local_interface") or entry.get("local_port", ""))
                remote_interface = normalize_intf(entry.get("neighbor_interface") or entry.get("port_id", ""))

                neighbors.append({
                    "neighbor_name": neighbor_name,
                    "mgmt_ip": mgmt_ip,
                    "local_interface": local_interface,
                    "remote_interface": remote_interface,
                    "platform": entry.get("system_description", ""),
                    "capability": entry.get("capabilities", ""),
                    "protocol": "LLDP"
                })
        
        return neighbors
    
    # ========== Fallback Methods (when TextFSM fails) ==========
    
    def _parse_version_fallback(self, raw_output: str) -> Dict[str, Any]:
        """Fallback regex parser for show version when TextFSM fails."""
        import re
        
        version_match = re.search(r"Version\s+([^,\s]+)", raw_output)
        model_match = re.search(r"cisco\s+(\S+)", raw_output, re.IGNORECASE)
        serial_match = re.search(r"Processor board ID\s+(\S+)", raw_output)
        uptime_match = re.search(r"uptime is\s+(.+)", raw_output)
        hostname_match = re.search(r"^(\S+)\s+uptime", raw_output, re.MULTILINE)
        
        return {
            "vendor": "Cisco",
            "os_version": version_match.group(1) if version_match else "Unknown",
            "model": model_match.group(1) if model_match else "Unknown",
            "serial_number": serial_match.group(1) if serial_match else "Unknown",
            "uptime": uptime_match.group(1) if uptime_match else "Unknown",
            "hostname": hostname_match.group(1) if hostname_match else self.hostname
        }

    # ================================================================
    # SWIM Implementation
    # ================================================================

    def transfer_file(self, local_path: str, remote_path: str = None, file_system: str = "flash:") -> bool:
        """
        Transfer file using Netmiko's file_transfer utility.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
            
        from netmiko import file_transfer
        
        if not remote_path:
            remote_path = os.path.basename(local_path)
            
        logger.info("CiscoIOSDriver starting file transfer local_path=%s dest=%s%s", local_path, file_system, remote_path)
        
        try:
            # enable_scp() might be needed on device, netmiko handles some of this
            result = file_transfer(
                self.connection,
                source_file=local_path,
                dest_file=remote_path,
                file_system=file_system,
                direction='put',
                overwrite_file=False
            )
            return result['file_verified']
        except Exception as e:
            self.last_error = f"File Transfer Failed: {e}"
            logger.warning("CiscoIOSDriver file transfer failed error=%s", e)
            return False

    def verify_image(self, file_path: str, expected_checksum: str) -> bool:
        """
        Verify MD5 checksum on device.
        Note: file_path should include filesystem if not default (e.g. flash:image.bin)
        """
        if not self.connection:
            raise ConnectionError("Not connected")
            
        cmd = f"verify /md5 {file_path}"
        try:
            # Output format: ".....Done! verify /md5 (flash:cat9k_ iosxe...bin) = <hash>"
            output = self.connection.send_command(cmd, read_timeout=300) # Checksum calc takes time
            
            import re
            # Extract hash from output
            match = re.search(r"=\s+([a-fA-F0-9]{32})", output)
            if match:
                device_hash = match.group(1).strip()
                return device_hash.lower() == expected_checksum.lower()
            
            # Sometimes output is just the hash
            if len(output.strip()) == 32:
                 return output.strip().lower() == expected_checksum.lower()
                 
            self.last_error = f"Could not parse checksum from output: {output}"
            return False
        except Exception as e:
            self.last_error = f"Verification Failed: {e}"
            return False

    def set_boot_variable(self, file_path: str) -> bool:
        """
        Configure boot system variable.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
            
        config_cmds = [
            "no boot system",
            f"boot system {file_path}"
        ]
        
        try:
            output = self.connection.send_config_set(config_cmds)
            self.connection.send_command("write memory")
            return "boot system" in self.connection.send_command("show run | include boot")
        except Exception as e:
            self.last_error = f"Set Boot Var Failed: {e}"
            return False

    def reload(self, save_config: bool = True):
        """
        Reload the device.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
            
        if save_config:
            self.connection.send_command("write memory")
            
        try:
            # Send reload, expect confirmation
            # "Proceed with reload? [confirm]"
            self.connection.send_command_timing("reload")
            self.connection.send_command_timing("\n") # Confirm
        except Exception as e:
            # Connection will be lost, which is expected
            logger.info("CiscoIOSDriver reload sent connection closed error=%s", e)

    # ================================================================
    # gNMI Telemetry
    # ================================================================

    def get_gnmi_telemetry(self, port: int = 57400) -> Dict[str, Any]:
        try:
            return self._collect_gnmi_metrics(port=port)
        except Exception as e:
            raise ConnectionError(f"gNMI Connection Failed: {e}")


