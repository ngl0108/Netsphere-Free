"""
Juniper JunOS Driver using NAPALM for multi-vendor abstraction.
Provides unified API for device management across vendors.
"""
from app.drivers.base import NetworkDriver
from typing import Dict, List, Any, Optional
import logging
import os

logger = logging.getLogger(__name__)

try:
    from napalm import get_network_driver
    NAPALM_AVAILABLE = True
except ImportError:
    NAPALM_AVAILABLE = False
    logger.warning("NAPALM not installed")


class JuniperJunOSDriver(NetworkDriver):
    """
    Juniper JunOS Driver using NAPALM.
    
    NAPALM provides:
    - Unified API across vendors
    - Structured data getters (get_facts, get_interfaces, etc.)
    - Configuration management with diff/commit/rollback
    """
    
    DEVICE_TYPE = "juniper_junos"
    
    def __init__(self, hostname: str, username: str, password: str, port: int = 22, secret: Optional[str] = None):
        super().__init__(hostname, username, password, port, secret)
        self.driver_class = None
        
        if NAPALM_AVAILABLE:
            self.driver_class = get_network_driver("junos")
        
    def connect(self) -> bool:
        """Establish NAPALM connection to Juniper device."""
        if not NAPALM_AVAILABLE:
            self.last_error = "NAPALM not installed"
            return False
            
        try:
            self.connection = self.driver_class(
                hostname=self.hostname,
                username=self.username,
                password=self.password,
                optional_args={
                    "port": self.port,
                    "ssh_strict": False,
                    "allow_agent": False
                }
            )
            self.connection.open()
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.warning("JuniperJunOSDriver connection error error=%s", e)
            return False

    def disconnect(self):
        """Close NAPALM connection."""
        if self.connection:
            try:
                self.connection.close()
            except:
                pass
            self.connection = None

    def check_connection(self) -> bool:
        """Check if connection is alive."""
        if not self.connection:
            return False
        try:
            # NAPALM doesn't have is_alive, try a simple getter
            self.connection.get_facts()
            return True
        except:
            return False

    def get_facts(self) -> Dict[str, Any]:
        """
        Get device facts using NAPALM getter.
        Returns standardized format matching NetworkDriver interface.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        try:
            facts = self.connection.get_facts()
            
            return {
                "vendor": facts.get("vendor", "Juniper"),
                "model": facts.get("model", "Unknown"),
                "os_version": facts.get("os_version", "Unknown"),
                "serial_number": facts.get("serial_number", "Unknown"),
                "uptime": self._format_uptime(facts.get("uptime", 0)),
                "hostname": facts.get("hostname", self.hostname),
                "fqdn": facts.get("fqdn", ""),
                "interface_list": facts.get("interface_list", [])
            }
        except Exception as e:
            self.last_error = str(e)
            return {
                "vendor": "Juniper",
                "model": "Unknown",
                "os_version": "Unknown",
                "serial_number": "Unknown",
                "uptime": "Unknown",
                "hostname": self.hostname
            }

    def get_interfaces(self) -> List[Dict[str, Any]]:
        """
        Get interface details using NAPALM getter.
        Returns list of interfaces in standardized format.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        interfaces = []
        
        try:
            # Get interface status
            intf_data = self.connection.get_interfaces()
            
            # Get IP addresses
            ip_data = self.connection.get_interfaces_ip()
            
            for intf_name, info in intf_data.items():
                # Find IP address for this interface
                ip_address = ""
                if intf_name in ip_data:
                    ipv4_addrs = ip_data[intf_name].get("ipv4", {})
                    if ipv4_addrs:
                        ip_address = list(ipv4_addrs.keys())[0]
                
                interfaces.append({
                    "name": intf_name,
                    "description": info.get("description", ""),
                    "is_up": info.get("is_up", False),
                    "is_enabled": info.get("is_enabled", True),
                    "link_status": "up" if info.get("is_up") else "down",
                    "protocol_status": "up" if info.get("is_up") else "down",
                    "ip_address": ip_address,
                    "mac_address": info.get("mac_address", ""),
                    "mtu": info.get("mtu", 0),
                    "speed": info.get("speed", 0),
                })
        except Exception as e:
            self.last_error = str(e)
            logger.warning("JuniperJunOSDriver get_interfaces error=%s", e)
        
        return interfaces

    def push_config(self, config_commands: List[str]) -> Dict[str, Any]:
        """
        Push configuration to device using NAPALM.
        Supports automatic commit.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        try:
            # Join commands into config string
            config_str = "\n".join(config_commands)
            
            # Load config (merge mode)
            self.connection.load_merge_candidate(config=config_str)
            
            # Get diff
            diff = self.connection.compare_config()
            
            # Commit
            self.connection.commit_config()
            
            return {
                "success": True,
                "output": diff or "Configuration applied successfully",
                "diff": diff
            }
        except Exception as e:
            # Discard changes on error
            try:
                self.connection.discard_config()
            except:
                pass
            return {
                "success": False,
                "error": str(e)
            }

    def get_config(self, source: str = "running") -> str:
        """
        Get device configuration using NAPALM.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        try:
            configs = self.connection.get_config()
            return configs.get(source, configs.get("running", ""))
        except Exception as e:
            self.last_error = str(e)
            return ""

    def get_neighbors(self) -> List[Dict[str, Any]]:
        """
        Get LLDP neighbors using NAPALM getter.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        neighbors = []
        
        try:
            lldp_data = self.connection.get_lldp_neighbors_detail()
            
            for local_intf, neighbor_list in lldp_data.items():
                for n in neighbor_list:
                    neighbors.append({
                        "neighbor_name": n.get("remote_system_name", "Unknown"),
                        "mgmt_ip": n.get("remote_management_address", ""),
                        "local_interface": local_intf,
                        "remote_interface": n.get("remote_port", ""),
                        "platform": n.get("remote_system_description", ""),
                        "capability": n.get("remote_system_capab", ""),
                        "protocol": "LLDP"
                    })
        except Exception as e:
            self.last_error = str(e)
            logger.warning("JuniperJunOSDriver get_neighbors error=%s", e)
        
        return neighbors

    # ========== Helper Methods ==========
    
    def _format_uptime(self, uptime_seconds: int) -> str:
        """Convert uptime in seconds to human readable format."""
        if not uptime_seconds:
            return "0d 0h 0m"
        
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        
        return f"{days}d {hours}h {minutes}m"

    # ========== NAPALM-specific Advanced Methods ==========
    
    def get_bgp_neighbors(self) -> Dict[str, Any]:
        """Get BGP neighbor information (NAPALM getter)."""
        if not self.connection:
            raise ConnectionError("Not connected")
        try:
            return self.connection.get_bgp_neighbors()
        except Exception as e:
            self.last_error = str(e)
            return {}

    def get_environment(self) -> Dict[str, Any]:
        """Get hardware environment (CPU, memory, fans, power)."""
        if not self.connection:
            raise ConnectionError("Not connected")
        try:
            return self.connection.get_environment()
        except Exception as e:
            self.last_error = str(e)
            return {}

    def rollback(self) -> bool:
        """Rollback to previous configuration."""
        if not self.connection:
            raise ConnectionError("Not connected")
        try:
            self.connection.rollback()
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    # ========== SWIM Methods (Required by BaseDriver) ==========
    
    def _normalize_image_path(self, file_ref: str) -> str:
        ref = str(file_ref or "").strip()
        if ref == "":
            return "/var/tmp/"
        if ":" in ref and not ref.startswith("/"):
            ref = ref.split(":", 1)[1]
        ref = ref.lstrip("/")
        return f"/var/tmp/{ref}"
    
    def transfer_file(self, local_path: str, remote_path: str = None, file_system: str = None) -> bool:
        """
        Transfer a file to the device.
        Uses basic SCP via Paramiko (since NAPALM doesn't expose a clean file_transfer method for images).
        """
        try:
            import paramiko
            from scp import SCPClient
            
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(self.hostname, port=self.port, username=self.username, password=self.password, timeout=30)
            
            if not remote_path:
                remote_path = os.path.basename(local_path)
            
            if not remote_path.startswith("/"):
                remote_path = self._normalize_image_path(remote_path)
                
            logger.info(f"Starting SCP transfer to {self.hostname}:{remote_path}")
            
            with SCPClient(ssh.get_transport()) as scp:
                scp.put(local_path, remote_path)
                
            ssh.close()
            return True
        except Exception as e:
            self.last_error = f"Juniper SCP Failed: {e}"
            logger.error(self.last_error)
            return False

    def verify_image(self, file_path: str, expected_checksum: str) -> bool:
        """
        Verify image integrity on Juniper device.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
            
        file_path = self._normalize_image_path(file_path)

        try:
            # Juniper uses 'file checksum md5'
            # NAPALM cli() returns a dict of {cmd: output}
            result = self.connection.cli([f"file checksum md5 {file_path}"])
            output = result.get(f"file checksum md5 {file_path}", "")
            
            # Output example:
            # MD5 (/var/tmp/junos-install.tgz) = 5b3267...
            
            return expected_checksum.lower() in output.lower()
        except Exception as e:
            self.last_error = str(e)
            return False

    def set_boot_variable(self, file_path: str) -> bool:
        """
        Install the image on Juniper device (request system software add).
        This is equivalent to 'set boot variable' + 'install' in JunOS.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        file_path = self._normalize_image_path(file_path)

        try:
            # This command installs the software but does not reboot immediately
            # 'no-validate' is often safer for automation, but let's stick to standard
            cmd = f"request system software add {file_path}"
            result = self.connection.cli([cmd])
            output = result.get(cmd, "")
            
            if "error" in output.lower() or "failed" in output.lower():
                self.last_error = f"Install failed: {output}"
                return False
                
            return True
        except Exception as e:
            self.last_error = str(e)
            return False

    def reload(self, save_config: bool = True):
        """
        Reload the Juniper device.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        try:
            if save_config:
                self.connection.commit_config()
            # Schedule reload
            self.connection.cli(["request system reboot"])
        except Exception as e:
            self.last_error = str(e)

    def get_gnmi_telemetry(self, port: int = 57400) -> Dict[str, Any]:
        try:
            return self._collect_gnmi_metrics(port=port)
        except Exception:
            try:
                env = self.get_environment()
                cpu_info = env.get("cpu", {})
                mem_info = env.get("memory", {})
                cpu_usage = 0
                if cpu_info:
                    cpu_values = [v.get("%usage", 0) for v in cpu_info.values() if isinstance(v, dict)]
                    cpu_usage = sum(cpu_values) / len(cpu_values) if cpu_values else 0
                mem_used = mem_info.get("used_ram", 0)
                mem_total = mem_info.get("available_ram", 1) + mem_used
                mem_usage = (mem_used / mem_total * 100) if mem_total > 0 else 0
                return {
                    "cpu_usage": round(cpu_usage, 1),
                    "memory_usage": round(mem_usage, 1),
                    "temperature": 0,
                    "power_status": "ok",
                    "fan_status": "ok"
                }
            except Exception as e:
                self.last_error = str(e)
                return {
                    "cpu_usage": 0,
                    "memory_usage": 0,
                    "temperature": 0,
                    "power_status": "unknown",
                    "fan_status": "unknown"
                }
