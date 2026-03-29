import logging
import re

logger = logging.getLogger(__name__)

class PortScanHandler:
    def __init__(self, nmap_module=None):
        self.nmap = nmap_module

    def scan(self, ip: str, fallback_ports=None):
        """
        Executes Port Scan fallback when SNMP fails.
        """
        info = {
            "ip_address": ip,
            "snmp_status": "unreachable",
            "hostname": ip,
            "vendor": "Unknown",
            "model": "",
            "os_version": "",
            "device_type": "unknown",
            "vendor_confidence": 0.05,
            "chassis_candidate": False,
            "issues": [{
                "code": "snmp_unreachable",
                "severity": "warn",
                "message": "SNMP 응답이 없습니다.",
                "hint": "UDP 161 접근(방화벽/ACL), SNMP 버전(v3/v2c/v1), 인증정보(Auth/Priv 또는 community), SNMP view 제한을 확인하세요."
            }],
            "evidence": {},
        }

        try:
            if self.nmap is None:
                # Without Nmap module, we can't do much deep inspection here efficiently in sync
                # But _tcp_alive_sweep in main service already confirmed it's alive.
                return info

            nm = self.nmap.PortScanner()
            # Scan common headers: 22(SSH), 23(Telnet), 80(HTTP), 443(HTTPS), 161(SNMP), 830(Netconf)
            nm.scan(ip, arguments='-p 22,23,80,443,161,830 -T4 --open')
            
            if ip in nm.all_hosts():
                tcp = nm[ip].get('tcp', {})
                open_ports = [p for p in tcp.keys()]
                
                if 22 in open_ports or 830 in open_ports:
                     info["vendor"] = "Unknown (SSH/Netconf Open)"
                     info["device_type"] = "manageable_device" # Will be mapped to 'generic' later
                     info["vendor_confidence"] = 0.15
                     info["evidence"]["open_ports"] = open_ports
                     info["issues"].append({
                         "code": "ssh_open_snmp_blocked",
                         "severity": "info",
                         "message": "SSH/NETCONF는 열려 있지만 SNMP는 실패했습니다.",
                         "hint": "SNMP(UDP 161) 방화벽/ACL 또는 커뮤니티 설정을 확인하세요."
                     })
                elif 80 in open_ports or 443 in open_ports:
                     info["vendor"] = "Unknown (Web Interface Open)"
                     info["device_type"] = "web_device"
                     info["vendor_confidence"] = 0.10
                     info["evidence"]["open_ports"] = open_ports
                else:
                     info["vendor"] = "Unknown (ICMP Only)"
                     info["vendor_confidence"] = 0.05
                     info["evidence"]["open_ports"] = open_ports
                     
                # OUI (MAC Vendor) Lookup if available (requires root generally)
                if 'mac' in nm[ip].get('addresses', {}):
                     mac_value = nm[ip]['addresses'].get('mac')
                     mac_norm = self._normalize_mac(mac_value)
                     if mac_norm:
                         info["mac_address"] = mac_norm
                         info["evidence"]["mac_source"] = "nmap"
                     mac_vendor = nm[ip]['vendor'].get(nm[ip]['addresses']['mac'], '')
                     if mac_vendor:
                         info["vendor"] = f"{mac_vendor} (MAC)"
                         info["vendor_confidence"] = 0.40
                         
        except Exception as e:
             info["vendor"] = f"Scan Error: {str(e)}"
             info["vendor_confidence"] = 0.0
             info["issues"].append({
                 "code": "scan_error",
                 "severity": "error",
                 "message": "포트 스캔 중 오류가 발생했습니다.",
                 "hint": str(e)
             })

        return info

    def _normalize_mac(self, value):
        if value is None: return None
        s0 = str(value).strip()
        if not s0: return None
        s = s0.lower().replace("0x", "")
        s = re.sub(r"[^0-9a-f]", "", s)
        if len(s) < 12: return None
        s = s[:12]
        return f"{s[0:4]}.{s[4:8]}.{s[8:12]}".lower()
