from app.drivers.generic_driver import GenericDriver
from typing import List, Dict, Any
import re
import os
import logging

logger = logging.getLogger(__name__)

class UbiquossDriver(GenericDriver):
    """
    Driver for Ubiquoss switches (L2/L3).
    """
    def __init__(self, hostname: str, username: str, password: str, port: int = 22, secret: str = None):
        super().__init__(hostname, username, password, port, secret, device_type="cisco_ios")

    def get_facts(self) -> Dict[str, Any]:
        if not self.connection:
            raise ConnectionError("Not connected")
        
        facts = {
            "vendor": "Ubiquoss",
            "os_version": "Unknown",
            "model": "Unknown",
            "serial_number": "Unknown",
            "uptime": "Unknown",
            "hostname": self.hostname,
        }
        
        raw_outputs: List[str] = []
        commands = [
            "show version",
            "show running",
            "show running-config",
            "show run",
        ]

        try:
            for cmd in commands:
                try:
                    output = self.connection.send_command(cmd)
                except Exception:
                    continue
                text = str(output or "")
                if not text.strip():
                    continue
                raw_outputs.append(text)
                self._update_facts_from_output(facts, text)
                if (
                    facts.get("hostname") not in {"", "Unknown", self.hostname}
                    and facts.get("model") != "Unknown"
                    and facts.get("os_version") != "Unknown"
                ):
                    break

            if raw_outputs:
                facts["raw_output"] = "\n\n".join(raw_outputs)
        except Exception as e:
            facts["error"] = str(e)
            
        return facts

    def get_neighbors(self) -> List[Dict[str, Any]]:
        neighbors = []
        if not self.connection:
            return []

        try:
            generic = super().get_neighbors()
            if generic:
                return generic
        except Exception:
            pass
            
        try:
            # Ubiquoss LLDP
            raw = self.connection.send_command("show lldp neighbors")
            neighbors.extend(self._parse_ubiquoss_lldp(raw))
        except Exception:
            pass
        return neighbors

    def _parse_ubiquoss_lldp(self, raw: str) -> List[Dict[str, Any]]:
        """
        Parse Ubiquoss LLDP output.
        """
        neighbors = []
        # Similar logic to Dasan/Cisco but robust against column variations
        lines = raw.splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("Device") or line.startswith("--"):
                continue
            
            parts = line.split()
            # Ubiquoss often: Device ID   Local Intf   Hold-time   Capability   Port ID
            if len(parts) >= 4:
                # Heuristic check: is first col a local intf or device id?
                # Usually: Device ID (Name) is first in Cisco-like outputs
                
                # Case 1: Standard Cisco-like
                # Device ID      Local Intf      Holdtme      Capability      Port ID
                # Switch-B       Gi0/2           120          R S             Gi0/1
                
                neighbor_name = parts[0]
                local_intf = parts[1]
                remote_intf = parts[-1] # Port ID is usually last
                
                # Check formatting
                # Sometimes split creates extra columns for capabilities
                
                neighbors.append({
                    "local_interface": local_intf,
                    "remote_interface": remote_intf,
                    "neighbor_name": neighbor_name,
                    "mgmt_ip": "",
                    "protocol": "LLDP"
                })
                
        return neighbors

    @staticmethod
    def _extract_prompt_name(output: str) -> str:
        match = re.search(r"^\s*([A-Za-z0-9_.-]+)#\s*show\b", str(output or ""), re.IGNORECASE | re.MULTILINE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _looks_like_model(value: str) -> bool:
        token = str(value or "").strip()
        return bool(re.match(r"^[A-Za-z]{0,4}\d{3,5}[A-Za-z0-9-]*$", token))

    def _update_facts_from_output(self, facts: Dict[str, Any], output: str) -> None:
        text = str(output or "")
        if not text.strip():
            return

        match = re.search(r"Uptime is (.*)", text, re.IGNORECASE)
        if match:
            facts["uptime"] = match.group(1).strip()

        match_ver = re.search(r"(?:Ubiquoss\s+NOS\s+Software,\s*)?Version\s*[:]?\s*([0-9A-Za-z._-]+\S*)", text, re.IGNORECASE)
        if match_ver:
            facts["os_version"] = match_ver.group(1).strip()

        match_model = re.search(r"Model\s*:\s*([^\n\r]+)", text, re.IGNORECASE)
        if match_model:
            facts["model"] = match_model.group(1).strip()

        match_serial = re.search(r"Serial(?:\s+Number)?\s*:\s*([^\n\r]+)", text, re.IGNORECASE)
        if match_serial:
            facts["serial_number"] = match_serial.group(1).strip()

        match_host = re.search(r"^\s*hostname\s+([^\s!]+)\s*$", text, re.IGNORECASE | re.MULTILINE)
        if match_host:
            facts["hostname"] = match_host.group(1).strip()

        prompt_name = self._extract_prompt_name(text)
        if prompt_name:
            if facts.get("hostname") in {"", "Unknown", self.hostname}:
                facts["hostname"] = prompt_name
            if facts.get("model") == "Unknown" and self._looks_like_model(prompt_name):
                facts["model"] = prompt_name

        host_value = str(facts.get("hostname") or "").strip()
        if facts.get("model") == "Unknown" and self._looks_like_model(host_value):
            facts["model"] = host_value

    def apply_config_replace(self, raw_config: str) -> Dict[str, Any]:
        return super().apply_config_replace(raw_config)

    # ================================================================
    # SWIM Implementation (Added for Domestic Vendor Support)
    # ================================================================

    def transfer_file(self, local_path: str, remote_path: str = None, file_system: str = "flash:") -> bool:
        """
        Ubiquoss uses standard SCP or TFTP.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
            
        try:
            from netmiko import file_transfer
            if not remote_path:
                remote_path = os.path.basename(local_path)
                
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
            self.last_error = f"Ubiquoss File Transfer Failed: {e}"
            logger.warning("UbiquossDriver file transfer failed error=%s", e)
            return False

    def verify_image(self, file_path: str, expected_checksum: str) -> bool:
        """
        Verify MD5 checksum.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
            
        # Try 'verify /md5 <path>'
        cmd = f"verify /md5 {file_path}"
        try:
            output = self.connection.send_command(cmd, read_timeout=300)
            
            import re
            match = re.search(r"=\s+([a-fA-F0-9]{32})", output)
            if match:
                return match.group(1).lower() == expected_checksum.lower()
            
            # Fallback
            if expected_checksum.lower() in output.lower():
                return True
                
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
            
        # Ubiquoss: boot system <file>
        config_cmds = [
            f"boot system {file_path}"
        ]
        
        try:
            output = self.connection.send_config_set(config_cmds)
            self.connection.send_command("write memory")
            return True
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
            self.connection.send_command_timing("reload")
            self.connection.send_command_timing("\n") # Confirm
        except Exception as e:
            logger.info("UbiquossDriver reload sent connection closed error=%s", e)
