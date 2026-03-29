"""
Cisco Catalyst 9800 WLC Driver (IOS-XE Based).
Optimized for wireless infrastructure visibility.
"""
from app.drivers.cisco.ios_driver import CiscoIOSDriver
from typing import Dict, List, Any
import re
import logging

logger = logging.getLogger(__name__)

class CiscoWLCDriver(CiscoIOSDriver):
    """
    Driver for Catalyst 9800 Wireless Controllers.
    Inherits primary IOS-XE functionality but adds Wireless-specific parsing.
    """
    
    DEVICE_TYPE = "cisco_ios" # C9800 uses IOS-XE engine
    
    def get_facts(self) -> Dict[str, Any]:
        facts = super().get_facts()
        facts["role"] = "WLC"
        # Often C9800 has 'Wireless' in the version string, let's ensure it's identified
        if "Wireless" not in facts.get("os_version", ""):
             facts["model"] = f"Catalyst 9800 ({facts.get('model', 'WLC')})"
        return facts

    def get_wireless_summary(self) -> Dict[str, Any]:
        """
        Specific to C9800: Get counts of APs, Clients, and WLANs.
        """
        if not self.connection:
            raise ConnectionError("Not connected")
            
        summary = {
            "total_aps": 0,
            "up_aps": 0,
            "down_aps": 0,
            "total_clients": 0,
            "wlan_summary": []
        }
        
        # 1. Get AP Summary
        ap_parsed = self.connection.send_command("show ap summary", use_textfsm=True)
        if isinstance(ap_parsed, list):
            summary["total_aps"] = len(ap_parsed)
            for ap in ap_parsed:
                # Normalize keys for consistency
                ap["name"] = ap.get("name") or ap.get("ap_name") or "Unknown"
                ap["model"] = ap.get("ap_model") or ap.get("model") or ap.get("pid") or "N/A"
                ap["status"] = ap.get("status") or ap.get("state") or "Unknown"
                ap["uptime"] = ap.get("uptime") or ap.get("up_time") or "N/A"
                ap["serial_number"] = ap.get("serial_number") or ap.get("serial") or "N/A"
                ap["ip_address"] = ap.get("ip_address") or "N/A"
                
                status_lower = str(ap["status"]).lower()
                if "up" in status_lower or "reg" in status_lower:
                    summary["up_aps"] += 1
                    ap["status"] = "online"
                else:
                    summary["down_aps"] += 1
                    ap["status"] = "offline"
            
            summary["ap_list"] = ap_parsed

        # 2. Get Client Summary
        client_out = self.connection.send_command("show wireless client summary")
        client_match = re.search(r"Number of Clients\s*:\s*(\d+)", client_out, re.IGNORECASE)
        if client_match:
            summary["total_clients"] = int(client_match.group(1))

        # 3. Get WLAN Summary (With manual parser fallback)
        wlan_out = self.connection.send_command("show wlan summary")
        wlan_parsed = []
        
        # Try TextFSM first if available
        try:
            wlan_parsed = self.connection.send_command("show wlan summary", use_textfsm=True)
        except:
            pass
            
        if isinstance(wlan_parsed, list) and len(wlan_parsed) > 0:
            for wl in wlan_parsed:
                summary["wlan_summary"].append({
                    "id": wl.get("wlan_id") or wl.get("id"),
                    "profile": wl.get("profile_name"),
                    "ssid": wl.get("ssid"),
                    "status": wl.get("status") # UP/DOWN
                })
        else:
            # Manual Regex Parser for: "1    coupang_Inspection               coupang_Inspection               UP"
            logger.warning("CiscoWLCDriver TextFSM for WLAN failed, using manual regex parser")
            # Pattern: ID (digit), Profile (str), SSID (str), Status (UP/DISABLED)
            # We skip the header lines and look for the table rows
            lines = wlan_out.splitlines()
            for line in lines:
                # Match line starting with an ID (digit)
                match = re.match(r"^\s*(\d+)\s+(\S+)\s+(\S+)\s+(UP|DISABLED|DOWN|ENABLED)", line, re.IGNORECASE)
                if match:
                    summary["wlan_summary"].append({
                        "id": match.group(1),
                        "profile": match.group(2),
                        "ssid": match.group(3),
                        "status": "UP" if "UP" in match.group(4).upper() or "ENABLED" in match.group(4).upper() else "DOWN"
                    })
            
        return summary

    def get_interfaces(self) -> List[Dict[str, Any]]:
        """
        WLC interfaces often include 'Service-Port', 'Redundancy', etc.
        """
        interfaces = super().get_interfaces()
        # We can add WLC specific interface tagging here if needed
        return interfaces

    def get_neighbors(self) -> List[Dict[str, Any]]:
        """
        Standard CDP/LLDP but also consider CAPWAP tunnels as a specialized neighbor type.
        For now, keep standard infra neighbors.
        """
        return super().get_neighbors()
