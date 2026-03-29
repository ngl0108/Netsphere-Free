from app.drivers.generic_driver import GenericDriver
from typing import List, Dict, Any
import re
import os
import logging

logger = logging.getLogger(__name__)

class DasanDriver(GenericDriver):
    """
    Driver for Dasan Networks switches (NOS).
    Extends GenericDriver but provides specialized parsing for LLDP and system facts.
    """
    def __init__(self, hostname: str, username: str, password: str, port: int = 22, secret: str = None):
        super().__init__(hostname, username, password, port, secret, device_type="cisco_ios")

    def get_facts(self) -> Dict[str, Any]:
        """
        Dasan specific facts gathering.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
        
        # Dasan often uses 'show system' or 'show version'
        # We try 'show system info' or fall back to 'show version'
        facts = {
            "vendor": "Dasan",
            "os_version": "Unknown",
            "model": "Unknown",
            "serial_number": "Unknown",
            "uptime": "Unknown",
            "hostname": self.hostname,
        }

        raw_outputs: List[str] = []
        commands = [
            "show system info",
            "show version",
            "show running-config",
            "show running",
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
                if cmd == "show system info" and any(x in text.lower() for x in ["invalid", "unknown command", "ambiguous"]):
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
        """
        Dasan specific LLDP parsing.
        Use 'show lldp neighbors' but handle potential format differences.
        """
        neighbors = []
        if not self.connection:
            return []

        try:
            generic = super().get_neighbors()
            if generic:
                return generic
        except Exception:
            pass

        # Try textual parsing first as TextFSM might not exist for Dasan
        try:
            raw_lldp = self.connection.send_command("show lldp neighbor")
            neighbors.extend(self._parse_dasan_lldp(raw_lldp))
        except Exception:
            pass
            
        return neighbors

    def apply_config_replace(self, raw_config: str) -> Dict[str, Any]:
        return super().apply_config_replace(raw_config)

    def _parse_dasan_lldp(self, raw: str) -> List[Dict[str, Any]]:
        """
        Parses Dasan 'show lldp neighbor' output.
        Format often looks like:
        
        Local Port   Device ID          Port ID          System Name
        ---------------------------------------------------------------
        1/1          00:11:22:33:44:55  gi0/1            Switch-A
        
        Or varying number of columns. We use regex for robustness.
        """
        neighbors = []
        lines = raw.splitlines()
        
        # Regex to capture: Local Intf, Device ID/Name, Remote Intf
        # This is a heuristic.
        # Pattern: <Local> <Spaces> <DeviceID> <Spaces> <RemotePort> ...
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith("Local") or line.startswith("--"):
                continue
                
            # Naive split by whitespace
            parts = line.split()
            if len(parts) >= 3:
                # Heuristic: 
                # Col 0: Local Port
                # Col 1: Device ID (or Name)
                # Col 2: Port ID (Remote)
                # Col 3+: System Name (Optional)
                
                local_intf = parts[0]
                neighbor_id = parts[1] # MAC or Name
                remote_intf = parts[2]
                neighbor_name = parts[-1] if len(parts) > 3 else neighbor_id
                
                # Filter out suspicious headers/garbage
                if "..." in line or "Total" in line:
                    continue

                neighbors.append({
                    "local_interface": local_intf,
                    "remote_interface": remote_intf,
                    "neighbor_name": neighbor_name,
                    "mgmt_ip": "", # Dasan LLDP summary often doesn't show IP
                    "protocol": "LLDP"
                })
        
        # Enhancements: Try 'show lldp neighbor detail' for IP if needed
        # But this basic summary is enough for topology linking.
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

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if "System Name" in line or "Host Name" in line:
                parts = line.split(":", 1)
                if len(parts) > 1 and parts[1].strip():
                    facts["hostname"] = parts[1].strip()
            elif "System Type" in line or re.match(r"^Model\s*:", line, re.IGNORECASE):
                parts = line.split(":", 1)
                if len(parts) > 1 and parts[1].strip():
                    facts["model"] = parts[1].strip()
            elif "Serial Number" in line:
                parts = line.split(":", 1)
                if len(parts) > 1 and parts[1].strip():
                    facts["serial_number"] = parts[1].strip()
            elif "NOS Version" in line or "Software Version" in line or re.match(r"^Version\s*:", line, re.IGNORECASE):
                parts = line.split(":", 1)
                if len(parts) > 1 and parts[1].strip():
                    facts["os_version"] = parts[1].strip()
            elif "Up Time" in line:
                parts = line.split(":", 1)
                if len(parts) > 1 and parts[1].strip():
                    facts["uptime"] = parts[1].strip()
            elif line.lower().startswith("hostname "):
                value = line.split(None, 1)[1].strip() if len(line.split(None, 1)) > 1 else ""
                if value:
                    facts["hostname"] = value

        prompt_name = self._extract_prompt_name(text)
        if prompt_name:
            if facts.get("hostname") in {"", "Unknown", self.hostname}:
                facts["hostname"] = prompt_name
            if facts.get("model") == "Unknown" and self._looks_like_model(prompt_name):
                facts["model"] = prompt_name

        host_value = str(facts.get("hostname") or "").strip()
        if facts.get("model") == "Unknown" and self._looks_like_model(host_value):
            facts["model"] = host_value

    # ================================================================
    # SWIM Implementation (Added for Domestic Vendor Support)
    # ================================================================

    def transfer_file(self, local_path: str, remote_path: str = None, file_system: str = "flash:") -> bool:
        """
        Dasan usually supports SCP. We use Netmiko's file_transfer or fallback to SCP.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
            
        try:
            from netmiko import file_transfer
            if not remote_path:
                remote_path = os.path.basename(local_path)
                
            # Dasan behaves like Cisco IOS for SCP often
            result = file_transfer(
                self.connection,
                source_file=local_path,
                dest_file=remote_path,
                file_system=file_system,
                direction='put',
                overwrite_file=False,
                # Dasan specific tweaks if needed
            )
            return result['file_verified']
        except Exception as e:
            self.last_error = f"Dasan File Transfer Failed: {e}"
            logger.warning("DasanDriver file transfer failed error=%s", e)
            return False

    def verify_image(self, file_path: str, expected_checksum: str) -> bool:
        """
        Verify MD5 checksum.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
            
        # Try 'verify /md5 <path>' (Cisco-like)
        cmd = f"verify /md5 {file_path}"
        try:
            output = self.connection.send_command(cmd, read_timeout=300)
            
            # Check for MD5 in output
            import re
            match = re.search(r"=\s+([a-fA-F0-9]{32})", output)
            if match:
                return match.group(1).lower() == expected_checksum.lower()
            
            # Fallback: Dasan might use 'show file md5'
            cmd2 = f"show file md5 {file_path}"
            output2 = self.connection.send_command(cmd2, read_timeout=300)
            if expected_checksum.lower() in output2.lower():
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
            
        # Dasan: boot system <file>
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
            logger.info("DasanDriver reload sent connection closed error=%s", e)
