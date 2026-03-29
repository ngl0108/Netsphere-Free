import logging
import re
from app.services.snmp_service import SnmpManager as DefaultSnmpManager
from app.core.device_fingerprints import (
    fingerprint_device,
    identify_vendor_by_oid,
    extract_model_from_descr,
    get_driver_for_vendor
)

logger = logging.getLogger(__name__)

class SnmpScanHandler:
    def __init__(self, snmp_manager_cls=DefaultSnmpManager):
        self.snmp_manager_cls = snmp_manager_cls

    def scan(self, ip: str, profile: dict):
        """
        Executes SNMP scan for a single IP using the provided profile.
        Returns a dict with device info if successful, or None/Empty dict if failed.
        """
        credential_pool = profile.get("credential_pool")
        if not isinstance(credential_pool, list):
            credential_pool = []

        # 1. Try primary profile
        result = self._try_snmp(ip, profile)
        if result:
            return result

        # 2. Try pool profiles
        for p in credential_pool:
            if not isinstance(p, dict):
                continue
            result = self._try_snmp(ip, p)
            if result:
                return result
        
        return None

    def _try_snmp(self, ip: str, p: dict):
        comm = (p.get("community") or "public").strip() or "public"
        ver = (p.get("version") or "v2c").strip().lower() or "v2c"
        prt = int(p.get("port") or 161)
        
        try:
            snmp = self.snmp_manager_cls(
                ip,
                community=comm,
                port=prt,
                version=ver,
                v3_username=p.get("v3_username"),
                v3_security_level=p.get("v3_security_level"),
                v3_auth_proto=p.get("v3_auth_proto"),
                v3_auth_key=p.get("v3_auth_key"),
                v3_priv_proto=p.get("v3_priv_proto"),
                v3_priv_key=p.get("v3_priv_key"),
            )
            sysinfo = snmp.get_system_info()
            if not sysinfo:
                return None
                
            # Basic Info
            info = {
                "snmp_status": "reachable",
                "evidence": {
                    "snmp_version": ver,
                    "snmp_profile_id": p.get("profile_id")
                },
                "issues": []
            }
            
            sys_descr = str(sysinfo.get("sysDescr") or "")
            sys_oid = str(sysinfo.get("sysObjectID") or "")
            sys_name = str(sysinfo.get("sysName") or "")

            info["hostname"] = sys_name if sys_name else ip
            
            # Identification
            fingerprint = fingerprint_device(sys_oid=sys_oid, sys_descr=sys_descr, sys_name=sys_name)
            vendor = str(fingerprint.get("vendor") or "")
            confidence = float(fingerprint.get("confidence") or 0.0)
            info["vendor"] = vendor
            info["model"] = extract_model_from_descr(vendor, sys_descr) or fingerprint.get("model_hint") or self._identify_model(sys_descr)
            info["os_version"] = self._extract_version(sys_descr)
            info["sys_object_id"] = sys_oid
            info["sys_descr"] = sys_descr
            info["device_type"] = get_driver_for_vendor(
                vendor,
                sys_descr=sys_descr,
                model=info["model"],
                sys_oid=sys_oid,
                sys_name=sys_name,
            )
            info["vendor_confidence"] = confidence
            info["chassis_candidate"] = self._estimate_chassis_candidate(sys_descr, info["model"], info["vendor"])
            info["evidence"]["snmp_sys_oid"] = sys_oid
            info["evidence"]["fingerprint"] = {
                "match_source": fingerprint.get("match_source"),
                "rule_id": fingerprint.get("rule_id"),
                "platform": fingerprint.get("platform"),
                "family": fingerprint.get("family"),
                "os_family": fingerprint.get("os_family"),
                "device_type": info["device_type"],
                "model_hint": fingerprint.get("model_hint"),
            }

            # Probes (LLDP/Bridge)
            self._probe_l2_features(snmp, info)
            
            # Type check
            if info["device_type"] == "unknown":
                info["issues"].append({
                    "code": "device_type_unknown",
                    "severity": "info",
                    "message": "장비 타입(device_type) 자동 판별이 확실하지 않습니다.",
                    "hint": "등록 후 SSH/SNMP Sync로 보강되며, 필요시 수동으로 device_type을 지정하세요."
                })

            return info
            
        except Exception as e:
            logger.debug(f"SNMP failed for {ip}: {e}")
            return None

    def _probe_l2_features(self, snmp, info):
        lldp_oid = "1.0.8802.1.1.2.1.3.2.0"
        bridge_oid = "1.3.6.1.2.1.17.1.2.0"
        qbridge_oid = "1.3.6.1.2.1.17.7.1.1.1.0"
        
        try:
            probe = snmp.get_oids([lldp_oid, bridge_oid, qbridge_oid]) or {}
            info["evidence"]["snmp_probe"] = {
                "lldp": bool(probe.get(lldp_oid)),
                "bridge": bool(probe.get(bridge_oid)),
                "qbridge": bool(probe.get(qbridge_oid)),
            }
            
            # MAC Address Probe
            bridge_addr_oid = "1.3.6.1.2.1.17.1.1.0"
            lldp_loc_subtype_oid = "1.0.8802.1.1.2.1.3.1.0"
            lldp_loc_id_oid = "1.0.8802.1.1.2.1.3.2.0"
            
            mac_probe = snmp.get_oids([bridge_addr_oid, lldp_loc_subtype_oid, lldp_loc_id_oid]) or {}
            mac = self._normalize_mac(mac_probe.get(bridge_addr_oid))
            source = "bridge"
            
            if not mac:
                subtype = str(mac_probe.get(lldp_loc_subtype_oid) or "").strip()
                if subtype == "4":
                    mac = self._normalize_mac(mac_probe.get(lldp_loc_id_oid))
                    source = "lldp"
            
            if mac:
                info["mac_address"] = mac
                info["evidence"]["mac_source"] = source

            if not probe.get(lldp_oid):
                info["issues"].append({
                    "code": "snmp_lldp_missing",
                    "severity": "warn",
                    "message": "SNMP는 되지만 LLDP-MIB가 조회되지 않습니다.",
                    "hint": "LLDP 활성화 또는 SNMP view/ACL에서 1.0.8802.1.1.2(LLDP-MIB) 허용을 확인하세요."
                })
            if not probe.get(bridge_oid):
                info["issues"].append({
                    "code": "snmp_bridge_missing",
                    "severity": "warn",
                    "message": "SNMP는 되지만 BRIDGE-MIB가 조회되지 않습니다.",
                    "hint": "L2 스위치가 아니거나, SNMP view/ACL에서 1.3.6.1.2.1.17(BRIDGE-MIB) 허용을 확인하세요."
                })
        except Exception:
            pass

    def _normalize_mac(self, value):
        if value is None: return None
        if isinstance(value, (bytes, bytearray)):
            b = bytes(value)
            if len(b) < 6: return None
            s = b[:6].hex()
            return f"{s[0:4]}.{s[4:8]}.{s[8:12]}".lower()
        s0 = str(value).strip()
        if not s0: return None
        s = s0.lower().replace("0x", "")
        s = re.sub(r"[^0-9a-f]", "", s)
        if len(s) < 12: return None
        s = s[:12]
        return f"{s[0:4]}.{s[4:8]}.{s[8:12]}".lower()

    def _estimate_chassis_candidate(self, sys_descr: str, model: str, vendor: str) -> bool:
        text = f"{sys_descr or ''} {model or ''}".lower()
        if "chassis" in text: return True
        if any(k in text for k in ("c940", "c960", "c950", "nexus 950", "n9k", "nexus 9k", "mx", "ptx", "qfx10", "dcs-7500", "ce128", "s127", "s97")):
            return True
        v = str(vendor or "").lower()
        if v in ("cisco", "juniper", "arista", "huawei", "aruba") and any(k in text for k in ("sup", "supervisor", "linecard", "fpc", "pic", "mpc", "lpu")):
            return True
        return False

    def _identify_model(self, sys_descr):
        if "C3750" in sys_descr: return "Catalyst 3750"
        if "C2960" in sys_descr: return "Catalyst 2960"
        if "N9K" in sys_descr: return "Nexus 9000"
        if "CSR1000V" in sys_descr: return "CSR1000V"
        return ""

    def _extract_version(self, sys_descr):
        parts = sys_descr.split(',')
        if len(parts) > 1:
            return parts[1].strip()
        return ""
