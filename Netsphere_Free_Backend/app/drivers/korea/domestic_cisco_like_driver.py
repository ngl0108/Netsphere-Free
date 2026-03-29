from __future__ import annotations

import os
import re
import logging
from typing import Any, Dict, List

from app.drivers.generic_driver import GenericDriver


logger = logging.getLogger(__name__)


class DomesticCiscoLikeDriver(GenericDriver):
    """
    Shared driver for domestic switch vendors that mostly behave like Cisco IOS
    over SSH but need vendor-aware fact parsing and LLDP fallback parsing.
    """

    vendor_name = "Domestic"
    fact_commands = ("show version", "show system info", "show system")
    neighbor_commands = (
        "show lldp neighbors detail",
        "show lldp neighbor detail",
        "show lldp neighbors",
        "show lldp neighbor",
    )

    def __init__(self, hostname: str, username: str, password: str, port: int = 22, secret: str | None = None):
        super().__init__(hostname, username, password, port, secret, device_type="cisco_ios")

    @staticmethod
    def _first_match(text: str, patterns: List[str]) -> str:
        for pattern in patterns:
            m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if m:
                return str(m.group(1)).strip()
        return ""

    def get_facts(self) -> Dict[str, Any]:
        if not self.connection:
            raise ConnectionError("Not connected")

        output = ""
        for cmd in self.fact_commands:
            try:
                output = str(self.connection.send_command(cmd) or "")
            except Exception:
                output = ""
            if output.strip():
                break

        facts = {
            "vendor": self.vendor_name,
            "os_version": self._first_match(
                output,
                [
                    r"^\s*(?:NOS|Software|Firmware)\s+Version\s*:\s*(.+)$",
                    r"^\s*Version\s*[: ]\s*(.+)$",
                    r"\bVersion\s+([A-Za-z0-9._-]+)\b",
                ],
            )
            or "Unknown",
            "model": self._first_match(
                output,
                [
                    r"^\s*(?:System\s+Type|Model(?:\s+Name)?|Product\s+Model|Switch\s+Model)\s*:\s*(.+)$",
                ],
            )
            or "Unknown",
            "serial_number": self._first_match(
                output,
                [
                    r"^\s*(?:Serial(?:\s+Number)?|S/N)\s*:\s*(.+)$",
                ],
            )
            or "Unknown",
            "uptime": self._first_match(
                output,
                [
                    r"^\s*(?:System\s+uptime\s+is|Uptime\s+is|Up\s+Time)\s*[: ]\s*(.+)$",
                ],
            )
            or "Unknown",
            "hostname": self._first_match(
                output,
                [
                    r"^\s*(?:System\s+Name|Host\s*Name|Hostname)\s*:\s*(.+)$",
                ],
            )
            or self.hostname,
            "raw_output": output,
        }
        return facts

    @staticmethod
    def _parse_lldp_detail(raw: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        text = str(raw or "").strip()
        if not text:
            return rows
        blocks = re.split(r"\n\s*\n", text)
        for block in blocks:
            local = DomesticCiscoLikeDriver._first_match(
                block,
                [
                    r"^\s*(?:Local\s+Intf|Local\s+Interface|Local\s+Port)\s*:\s*(.+)$",
                ],
            )
            remote = DomesticCiscoLikeDriver._first_match(
                block,
                [
                    r"^\s*(?:Port\s+id|Port\s+ID|Remote\s+Port)\s*:\s*(.+)$",
                ],
            )
            name = DomesticCiscoLikeDriver._first_match(
                block,
                [
                    r"^\s*(?:System\s+Name|Device\s+ID)\s*:\s*(.+)$",
                ],
            )
            mgmt = DomesticCiscoLikeDriver._first_match(
                block,
                [
                    r"^\s*(?:Management\s+Address|Mgmt\s+Address)\s*:\s*(.+)$",
                ],
            )
            if local and (remote or name):
                rows.append(
                    {
                        "local_interface": local,
                        "remote_interface": remote,
                        "neighbor_name": name or remote,
                        "mgmt_ip": mgmt,
                        "protocol": "LLDP",
                    }
                )
        return rows

    @staticmethod
    def _parse_lldp_summary(raw: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        text = str(raw or "").strip()
        if not text:
            return rows
        for line in text.splitlines():
            ln = line.strip()
            if not ln:
                continue
            low = ln.lower()
            if low.startswith(("local port", "local intf", "device id")) or ln.startswith("-"):
                continue
            parts = ln.split()
            if len(parts) < 3:
                continue
            if "/" in parts[0] and ":" not in parts[0] and not parts[0].lower().startswith("switch"):
                local_intf = parts[0]
                remote_intf = parts[2] if len(parts) >= 3 else ""
                neighbor_name = parts[-1] if len(parts) > 3 else parts[1]
            else:
                neighbor_name = parts[0]
                local_intf = parts[1] if len(parts) >= 2 else ""
                remote_intf = parts[-1]
            if local_intf and remote_intf:
                rows.append(
                    {
                        "local_interface": local_intf,
                        "remote_interface": remote_intf,
                        "neighbor_name": neighbor_name,
                        "mgmt_ip": "",
                        "protocol": "LLDP",
                    }
                )
        return rows

    def get_neighbors(self) -> List[Dict[str, Any]]:
        if not self.connection:
            return []

        try:
            generic = super().get_neighbors()
            if generic:
                return generic
        except Exception:
            pass

        for cmd in self.neighbor_commands:
            try:
                raw = self.connection.send_command(cmd)
            except Exception:
                raw = ""
            rows = self._parse_lldp_detail(str(raw or "")) if "detail" in cmd else self._parse_lldp_summary(str(raw or ""))
            if rows:
                return rows
        return []

    def apply_config_replace(self, raw_config: str) -> Dict[str, Any]:
        return super().apply_config_replace(raw_config)

    def transfer_file(self, local_path: str, remote_path: str | None = None, file_system: str = "flash:") -> bool:
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
                direction="put",
                overwrite_file=False,
            )
            return bool(result.get("file_verified"))
        except Exception as e:
            self.last_error = f"{self.vendor_name} File Transfer Failed: {e}"
            logger.warning("%s file transfer failed error=%s", self.vendor_name, e)
            return False


class SoltechDriver(DomesticCiscoLikeDriver):
    vendor_name = "Soltech"


class CoreEdgeDriver(DomesticCiscoLikeDriver):
    vendor_name = "CoreEdge"


class NSTDriver(DomesticCiscoLikeDriver):
    vendor_name = "NST"
