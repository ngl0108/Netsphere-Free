from app.drivers.manager import DriverManager
from jinja2 import Template
from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class DeviceInfo:
    """
    DTO for device connection information.
    """
    def __init__(self, host, username, password, secret=None, port=22, device_type='cisco_ios'):
        self.host = host
        self.username = username
        self.password = password
        self.secret = secret
        self.port = port
        self.device_type = device_type


class DeviceConnection:
    """
    Service class handling device interactions via the Driver Manager.
    Acts as a facade/adapter for the core logic to access the unified driver layer.
    """
    def __init__(self, device_info: DeviceInfo):
        self.device_info = device_info
        self.last_error = None
        
        # Instantiate the creation of the appropriate driver via Factory
        try:
            self.driver = DriverManager.get_driver(
                device_type=device_info.device_type,
                hostname=device_info.host,
                username=device_info.username,
                password=device_info.password,
                port=device_info.port,
                secret=device_info.secret
            )
        except Exception as e:
            logger.exception("Driver init error")
            self.driver = None
            self.last_error = str(e)

    def connect(self) -> bool:
        if not self.driver:
            return False
        try:
            logger.info("Connecting to device", extra={"device_id": None})
            connected = self.driver.connect()
            if connected:
                logger.info("Connection established")
            else:
                logger.warning("Connection failed")
            return connected
        except Exception as e:
            self.last_error = str(e)
            logger.exception("Connection error")
            return False

    def disconnect(self):
        if self.driver:
            self.driver.disconnect()

    def send_config_set(self, commands: List[str]) -> str:
        """
        Wrapper for push_config to support legacy calls (like Netmiko's send_config_set).
        Returns the output log string upon success, or raises an exception on failure.
        """
        if not self.driver:
            raise ConnectionError("Driver not initialized")

        result = self.driver.push_config(commands)
        
        # Driver returns {'success': bool, 'output': str, 'error': str}
        if isinstance(result, dict):
            if not result.get('success', False):
                raise Exception(result.get('error', 'Config Push Failed'))
            return result.get('output', '')
        
        return str(result)

    def deploy_config_template(self, template_str: str, context: Dict[str, Any]):
        """
        Renders Jinja2 template and delegates push to driver.
        """
        if not self.driver:
            return {"success": False, "error": "Driver not initialized"}

        try:
            # 1. Render Template
            tm = Template(template_str)
            rendered_config = tm.render(context)
            config_lines = [line.strip() for line in rendered_config.split('\n') if line.strip()]

            # 2. Push via Driver
            return self.driver.push_config(config_lines)
        except Exception as e:
            logger.exception("Deploy error")
            return {"success": False, "error": str(e)}

    def get_facts(self):
        if not self.driver:
            return {}
        return self.driver.get_facts()

    def get_running_config(self):
        if not self.driver:
            raise ConnectionError("Driver not initialized")
        return self.driver.get_config("running")

    def get_interface_statuses(self):
        """
        Returns simple status dict {interface_name: status} for backward compatibility.
        """
        if not self.driver:
            return {}
        
        interfaces = self.driver.get_interfaces()
        result = {}
        for intf in interfaces:
            # Simple mapping: 'up' if enabled (and ideally operative up), but config only knows 'is_enabled' (no shutdown).
            # If driver implements live status check later, this logic will improve automatically.
            status = 'up' if intf.get('is_enabled', False) else 'admin_down'
            result[intf['name']] = status
        return result

    def rollback(self) -> bool:
        if not self.driver:
            raise ConnectionError("Driver not initialized")
        if hasattr(self.driver, "rollback"):
            return bool(self.driver.rollback())
        raise NotImplementedError("Rollback not supported by this driver")

    def get_neighbors(self):
        if not self.driver:
            return []
        return self.driver.get_neighbors()

    def get_detailed_interfaces(self):
        """
        Returns full interface details list from driver.
        """
        if not self.driver:
            return []
        return self.driver.get_interfaces()

    def send_command(self, command: str, use_textfsm: bool = False, **kwargs) -> str:
        if not self.driver or not getattr(self.driver, "connection", None):
            raise ConnectionError("Not connected")
        return self.driver.connection.send_command(command, use_textfsm=use_textfsm, **kwargs)

    def get_route_to(self, target_ip: str, vrf: str = None) -> Dict[str, Any]:
        """
        Best-effort route lookup for a given target IP.
        Returns: {next_hop_ip, outgoing_interface, protocol, vrf, raw}
        """
        if not self.driver or not getattr(self.driver, "connection", None):
            return {"next_hop_ip": None, "outgoing_interface": None, "protocol": None, "vrf": None, "raw": None}

        if vrf:
            cmd = f"show ip route vrf {vrf} {target_ip}"
        else:
            cmd = f"show ip route {target_ip}"

        parsed = self.driver.connection.send_command(cmd, use_textfsm=True)
        if isinstance(parsed, list) and parsed:
            entry = parsed[0]
            next_hop = entry.get("nexthop_ip") or entry.get("next_hop") or entry.get("nexthop") or entry.get("nexthopaddr")
            out_intf = entry.get("interface") or entry.get("outgoing_interface") or entry.get("out_intf") or entry.get("exit_interface")
            proto = entry.get("protocol") or entry.get("route_protocol")
            vrf = entry.get("vrf") or entry.get("vrfname")
            return {"next_hop_ip": next_hop, "outgoing_interface": out_intf, "protocol": proto, "vrf": vrf, "raw": None}

        raw = parsed if isinstance(parsed, str) else self.driver.connection.send_command(cmd)
        if vrf and ("Invalid input" in raw or "Unknown command" in raw):
            cmd2 = f"show ip route {target_ip} vrf {vrf}"
            raw = self.driver.connection.send_command(cmd2)
        next_hop_ip = None
        outgoing_interface = None
        protocol = None

        import re


        m = re.search(r"Known via \"([^\"]+)\"", raw)
        if m:
            protocol = m.group(1)

        m = re.search(r"via\s+(\d+\.\d+\.\d+\.\d+),\s*(\S+)", raw)
        if m:
            next_hop_ip = m.group(1)
            outgoing_interface = m.group(2)
        else:
            m = re.search(r"directly connected,\s*(\S+)", raw)
            if m:
                outgoing_interface = m.group(1)

        detected_vrf = vrf
        m = re.search(r"Routing Table:\s+(\S+)", raw)
        if m:
            detected_vrf = m.group(1)

        return {"next_hop_ip": next_hop_ip, "outgoing_interface": outgoing_interface, "protocol": protocol, "vrf": detected_vrf, "raw": raw}

    def get_arp_entry(self, target_ip: str, vrf: str = None) -> Dict[str, Any]:
        """
        Best-effort ARP lookup for a given target IP.
        Returns: {ip, mac, interface, raw}
        """
        if not self.driver or not getattr(self.driver, "connection", None):
            return {"ip": target_ip, "mac": None, "interface": None, "raw": None}

        if vrf:
            cmd = f"show ip arp vrf {vrf} {target_ip}"
        else:
            cmd = f"show ip arp {target_ip}"
        parsed = self.driver.connection.send_command(cmd, use_textfsm=True)
        if isinstance(parsed, list) and parsed:
            entry = parsed[0]
            mac = entry.get("mac") or entry.get("hw_address") or entry.get("mac_address")
            intf = entry.get("interface") or entry.get("intf")
            ip = entry.get("address") or entry.get("ip") or target_ip
            return {"ip": ip, "mac": mac, "interface": intf, "raw": None}

        raw = parsed if isinstance(parsed, str) else self.driver.connection.send_command(cmd)
        if vrf and ("Invalid input" in raw or "Unknown command" in raw):
            cmd2 = f"show ip arp {target_ip} vrf {vrf}"
            raw = self.driver.connection.send_command(cmd2)
        import re

        mac = None
        intf = None
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+[\d\-]+\s+([0-9a-f\.]{10,})\s+\S+\s+(\S+)", raw, re.IGNORECASE)
        if m:
            mac = m.group(2)
            intf = m.group(3)
        return {"ip": target_ip, "mac": mac, "interface": intf, "raw": raw}

    def get_vrfs(self) -> List[str]:
        if not self.driver or not getattr(self.driver, "connection", None):
            return []

        cmds = ["show vrf", "show ip vrf"]
        output = ""
        for c in cmds:
            out = self.driver.connection.send_command(c)
            if out and "Invalid input" not in out and "Unknown command" not in out:
                output = out
                break

        if not output:
            return []

        lines = [ln.strip() for ln in str(output).splitlines() if ln.strip()]
        if not lines:
            return []

        vrfs = []
        for ln in lines[1:]:
            if ln.lower().startswith("name") or ln.lower().startswith("---"):
                continue
            parts = ln.split()
            if not parts:
                continue
            name = parts[0].strip()
            if name and name.lower() != "default":
                vrfs.append(name)
        return list(dict.fromkeys(vrfs))

    def get_interface_vrf(self, interface_name: str) -> Dict[str, Any]:
        if not self.driver or not getattr(self.driver, "connection", None):
            return {"interface": interface_name, "vrf": None, "raw": None}

        if not interface_name:
            return {"interface": interface_name, "vrf": None, "raw": None}

        cmds = [
            f"show ip vrf interface {interface_name}",
            f"show vrf interface {interface_name}",
        ]
        raw = ""
        for c in cmds:
            out = self.driver.connection.send_command(c)
            if out and "Invalid input" not in out and "Unknown command" not in out:
                raw = out
                break

        if not raw:
            return {"interface": interface_name, "vrf": None, "raw": None}

        import re

        vrf = None
        m = re.search(r"\bVRF\s+Name\s*:\s*(\S+)", raw, re.IGNORECASE)
        if m:
            vrf = m.group(1)
        if not vrf:
            m = re.search(r"\bis\s+in\s+VRF\s+(\S+)", raw, re.IGNORECASE)
            if m:
                vrf = m.group(1)
        if not vrf:
            m = re.search(r"\bvrf\s*[:=]\s*(\S+)", raw, re.IGNORECASE)
            if m:
                vrf = m.group(1)

        if vrf and vrf.lower() == "default":
            vrf = None

        return {"interface": interface_name, "vrf": vrf, "raw": raw}

    def get_mac_table_port(self, mac: str, vrf: str = None) -> Dict[str, Any]:
        if not self.driver or not getattr(self.driver, "connection", None):
            return {"mac": mac, "port": None, "vlan": None, "raw": None}

        import re

        def normalize(m: str) -> str:
            s = (m or "").strip().lower()
            s = re.sub(r"[^0-9a-f]", "", s)
            if len(s) != 12:
                return (m or "").strip()
            return f"{s[0:4]}.{s[4:8]}.{s[8:12]}"

        mac_n = normalize(mac)

        cmds = [
            f"show mac address-table address {mac_n}",
            f"show mac address-table | include {mac_n}",
            f"show mac address-table dynamic address {mac_n}",
        ]
        raw = ""
        for c in cmds:
            out = self.driver.connection.send_command(c)
            if out and "Invalid input" not in out and "Unknown command" not in out:
                raw = out
                break

        if not raw:
            return {"mac": mac_n, "port": None, "vlan": None, "raw": None}

        port = None
        vlan = None
        for ln in str(raw).splitlines():
            line = ln.strip()
            if not line:
                continue
            if line.lower().startswith("vlan") or line.lower().startswith("---"):
                continue
            m = re.search(r"^\s*(\d+)\s+([0-9a-f\.]{10,})\s+\S+\s+(\S+)\s*$", line, re.IGNORECASE)
            if m:
                vlan = m.group(1)
                port = m.group(3)
                break
            m = re.search(r"\b(\d+)\b.*\b([0-9a-f\.]{10,})\b.*\b(dynamic|static)\b.*\b(\S+)\b", line, re.IGNORECASE)
            if m:
                vlan = m.group(1)
                port = m.group(4)
                break

        return {"mac": mac_n, "port": port, "vlan": vlan, "raw": raw}

    def get_mac_table(self) -> List[Dict[str, Any]]:
        if not self.driver or not getattr(self.driver, "connection", None):
            return []

        cmds = [
            "show mac address-table dynamic",
            "show mac address-table",
            "show mac-address-table",
            "show bridge address-table",
            "display mac-address",
        ]
        output = ""
        parsed = None
        for c in cmds:
            out = self.driver.connection.send_command(c, use_textfsm=True)
            if isinstance(out, list) and out:
                parsed = out
                output = ""
                break
            out2 = out if isinstance(out, str) else self.driver.connection.send_command(c)
            if out2 and "Invalid input" not in out2 and "Unknown command" not in out2:
                output = out2
                break

        results: List[Dict[str, Any]] = []
        if isinstance(parsed, list) and parsed:
            for e in parsed:
                mac = e.get("mac") or e.get("mac_address") or e.get("destination_address")
                vlan = e.get("vlan") or e.get("vlan_id")
                port = e.get("destination_port") or e.get("port") or e.get("interface")
                entry_type = e.get("type") or e.get("entry_type") or e.get("mac_type")
                if mac and port:
                    results.append({"mac": mac, "vlan": str(vlan) if vlan is not None else None, "port": port, "type": entry_type})
            return results

        if not output:
            return []

        import re

        for ln in str(output).splitlines():
            line = ln.strip()
            if not line:
                continue
            if line.lower().startswith("vlan") or line.lower().startswith("---"):
                continue
            m = re.search(r"^\s*(\d+)\s+([0-9a-f\.:-]{11,})\s+(\S+)\s+(\S+)\s*$", line, re.IGNORECASE)
            if m:
                results.append({"vlan": m.group(1), "mac": m.group(2), "type": m.group(3), "port": m.group(4)})
                continue
            m = re.search(r"^\s*(\d+)\s+([0-9a-f\.:-]{11,})\s+(\S+)\s+(\S+)\s+(\S+)\s*$", line, re.IGNORECASE)
            if m:
                results.append({"vlan": m.group(1), "mac": m.group(2), "type": m.group(3), "port": m.group(5)})

        return results

    def get_arp_table(self) -> List[Dict[str, Any]]:
        if not self.driver or not getattr(self.driver, "connection", None):
            return []

        cmds = ["show ip arp", "show arp", "display arp"]
        results: List[Dict[str, Any]] = []
        raw = ""
        for cmd in cmds:
            parsed = self.driver.connection.send_command(cmd, use_textfsm=True)
            if isinstance(parsed, list) and parsed:
                for e in parsed:
                    ip = e.get("address") or e.get("ip") or e.get("protocol_address")
                    mac = e.get("mac") or e.get("hw_address") or e.get("mac_address") or e.get("hardware_address")
                    intf = e.get("interface") or e.get("intf")
                    if ip and mac:
                        results.append({"ip": ip, "mac": mac, "interface": intf})
                if results:
                    return results
            raw = parsed if isinstance(parsed, str) else self.driver.connection.send_command(cmd)
            if raw and "Invalid input" not in raw and "Unknown command" not in raw:
                break

        if not raw:
            return results

        import re

        for ln in str(raw).splitlines():
            line = ln.strip()
            if not line or line.lower().startswith("protocol"):
                continue
            m = re.search(r"(\d+\.\d+\.\d+\.\d+)\s+\d+\s+([0-9a-f\.:-]{11,})\s+\S+\s+(\S+)", line, re.IGNORECASE)
            if m:
                results.append({"ip": m.group(1), "mac": m.group(2), "interface": m.group(3)})
        return results

    def get_dhcp_snooping_bindings(self) -> List[Dict[str, Any]]:
        if not self.driver or not getattr(self.driver, "connection", None):
            return []

        cmds = ["show ip dhcp snooping binding", "show dhcp snooping binding", "display dhcp snooping binding"]
        raw = ""
        for cmd in cmds:
            try:
                raw = self.driver.connection.send_command(cmd)
            except Exception:
                raw = ""
            if raw and "Invalid input" not in raw and "Unknown command" not in raw:
                break
        if not raw:
            return []

        import re

        results: List[Dict[str, Any]] = []
        for ln in str(raw).splitlines():
            line = ln.strip()
            if not line:
                continue
            if line.lower().startswith("macaddress") or line.lower().startswith("---"):
                continue
            m = re.search(
                r"^\s*([0-9a-f\.:-]{11,})\s+(\d+\.\d+\.\d+\.\d+)\s+\S+\s+(\d+)\s+(\S+)",
                line,
                re.IGNORECASE,
            )
            if m:
                results.append({"mac": m.group(1), "ip": m.group(2), "vlan": m.group(3), "interface": m.group(4)})
        return results

    def get_lldp_neighbors_detail(self) -> List[Dict[str, Any]]:
        if not self.driver or not getattr(self.driver, "connection", None):
            return []

        cmds = [
            "show lldp neighbors detail",
            "show lldp neighbors",
            "show lldp neighbor detail",
            "display lldp neighbor",
            "display lldp neighbors",
        ]
        raw = ""
        for cmd in cmds:
            try:
                raw = self.driver.connection.send_command(cmd)
            except Exception:
                raw = ""
            if raw and "Invalid input" not in raw and "Unknown command" not in raw:
                break
        if not raw:
            return []

        results: List[Dict[str, Any]] = []
        current: Dict[str, Any] = {}
        in_sys_descr = False
        for ln in str(raw).splitlines():
            line = ln.rstrip("\n")
            if not line.strip():
                continue
            s = line.strip()
            low = s.lower()
            if low.startswith("local intf:") or low.startswith("local interface:") or low.startswith("local port:"):
                if current.get("local_interface"):
                    results.append(current)
                current = {}
                current["local_interface"] = s.split(":", 1)[1].strip()
                in_sys_descr = False
                continue
            if ":" in s:
                k, v = s.split(":", 1)
                key = k.strip().lower()
                val = v.strip()
                if key in ("port id", "portid"):
                    current["port_id"] = val
                    in_sys_descr = False
                elif key in ("system name",):
                    current["system_name"] = val
                    in_sys_descr = False
                elif key in ("system description", "system descr"):
                    current["system_description"] = (current.get("system_description", "") + " " + val).strip()
                    in_sys_descr = True
                elif key in ("chassis id",):
                    current["chassis_id"] = val
                    in_sys_descr = False
                elif key in ("management address", "management ip", "mgmt address", "mgmt ip"):
                    current["mgmt_ip"] = val
                    in_sys_descr = False
                else:
                    in_sys_descr = False
            else:
                if in_sys_descr and current.get("system_description"):
                    current["system_description"] = (str(current.get("system_description") or "") + " " + s).strip()
        if current.get("local_interface"):
            results.append(current)
        return results
