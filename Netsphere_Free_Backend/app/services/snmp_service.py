from typing import Dict
import re
try:
    from pysnmp.hlapi import (
        SnmpEngine, CommunityData, UdpTransportTarget, ContextData,
        ObjectType, ObjectIdentity, getCmd, nextCmd,
        UsmUserData,
        usmNoAuthProtocol, usmHMACMD5AuthProtocol, usmHMACSHAAuthProtocol,
        usmNoPrivProtocol, usmDESPrivProtocol, usmAesCfb128Protocol
    )
except Exception:
    SnmpEngine = None
    CommunityData = None
    UdpTransportTarget = None
    ContextData = None
    ObjectType = None
    ObjectIdentity = None
    getCmd = None
    nextCmd = None
    UsmUserData = None
    usmNoAuthProtocol = None
    usmHMACMD5AuthProtocol = None
    usmHMACSHAAuthProtocol = None
    usmNoPrivProtocol = None
    usmDESPrivProtocol = None
    usmAesCfb128Protocol = None

class SnmpManager:
    def __init__(
        self,
        target_ip,
        community='public',
        port=161,
        version: str = "v2c",
        v3_username: str | None = None,
        v3_security_level: str | None = None,
        v3_auth_proto: str | None = None,
        v3_auth_key: str | None = None,
        v3_priv_proto: str | None = None,
        v3_priv_key: str | None = None,
        mp_model: int | None = None,
    ):
        self.target = target_ip
        self.community = community
        self.port = port
        self.version = (version or "v2c").strip().lower()
        self.v3_username = v3_username
        self.v3_security_level = (v3_security_level or "").strip() or None
        self.v3_auth_proto = (v3_auth_proto or "").strip() or None
        self.v3_auth_key = v3_auth_key
        self.v3_priv_proto = (v3_priv_proto or "").strip() or None
        self.v3_priv_key = v3_priv_key
        self.mp_model = mp_model
        # Shared SNMP Engine is generally okay for sync, or new per request if very infrequent
        # But creating new engine per request is safer for thread-safety in simple scripts
        self.snmp_engine = SnmpEngine() if SnmpEngine else None

    def _resolve_v3_protocols(self):
        auth_map = {
            None: usmHMACSHAAuthProtocol,
            "sha": usmHMACSHAAuthProtocol,
            "md5": usmHMACMD5AuthProtocol,
        }
        priv_map = {
            None: usmAesCfb128Protocol,
            "aes": usmAesCfb128Protocol,
            "aes128": usmAesCfb128Protocol,
            "des": usmDESPrivProtocol,
        }
        auth_proto = auth_map.get((self.v3_auth_proto or "").lower(), usmHMACSHAAuthProtocol)
        priv_proto = priv_map.get((self.v3_priv_proto or "").lower(), usmAesCfb128Protocol)
        return auth_proto, priv_proto

    def _build_auth_data(self):
        if not self.snmp_engine:
            return None
        if self.version in ("v3", "3") or self.v3_username:
            if not UsmUserData or not self.v3_username:
                return None

            security_level = (self.v3_security_level or "").strip()
            if not security_level:
                if self.v3_priv_key:
                    security_level = "authPriv"
                elif self.v3_auth_key:
                    security_level = "authNoPriv"
                else:
                    security_level = "noAuthNoPriv"

            auth_proto, priv_proto = self._resolve_v3_protocols()

            if security_level == "noAuthNoPriv":
                return UsmUserData(self.v3_username)
            if security_level == "authNoPriv":
                return UsmUserData(self.v3_username, self.v3_auth_key or "", authProtocol=auth_proto)
            if security_level == "authPriv":
                return UsmUserData(
                    self.v3_username,
                    self.v3_auth_key or "",
                    self.v3_priv_key or "",
                    authProtocol=auth_proto,
                    privProtocol=priv_proto,
                )
            return UsmUserData(self.v3_username)

        if not CommunityData:
            return None
        if self.mp_model is not None:
            return CommunityData(self.community, mpModel=int(self.mp_model))
        return CommunityData(self.community, mpModel=1)

    def _get_request(self, oids):
        """SNMP GET (Synchronous)"""
        if not self.snmp_engine or not getCmd:
            return None
        auth_data = self._build_auth_data()
        if not auth_data:
            return None
        try:
            iterator = getCmd(
                self.snmp_engine,
                auth_data,
                UdpTransportTarget((self.target, self.port), timeout=2.0, retries=2),
                ContextData(),
                *[ObjectType(ObjectIdentity(oid)) for oid in oids],
                lookupMib=False
            )

            errorIndication, errorStatus, errorIndex, varBinds = next(iterator)

            if errorIndication or errorStatus:
                return None

            result = {}
            for varBind in varBinds:
                oid = str(varBind[0])
                val = varBind[1]
                result[oid] = str(val)
            return result

        except Exception as e:
            return None

    def check_status(self):
        oids = ['1.3.6.1.2.1.1.1.0', '1.3.6.1.2.1.1.3.0']
        data = self._get_request(oids)

        if data:
            return {
                "status": "online",
                "uptime": data.get('1.3.6.1.2.1.1.3.0', 'Unknown'),
                "description": data.get('1.3.6.1.2.1.1.1.0', 'Unknown')
            }
        else:
            return {"status": "offline"}

    def get_oids(self, oids: list[str]) -> Dict[str, str] | None:
        return self._get_request(oids)

    def get_system_info(self) -> Dict[str, str] | None:
        oids = [
            '1.3.6.1.2.1.1.1.0',
            '1.3.6.1.2.1.1.2.0',
            '1.3.6.1.2.1.1.5.0',
        ]
        data = self._get_request(oids)
        if not data:
            return None
        return {
            "sysDescr": data.get('1.3.6.1.2.1.1.1.0', ''),
            "sysObjectID": data.get('1.3.6.1.2.1.1.2.0', ''),
            "sysName": data.get('1.3.6.1.2.1.1.5.0', ''),
        }

    def get_total_octets(self) -> Dict[str, int]:
        """
        Get sum of all interfaces octets (In/Out).
        Prioritizes HC (64-bit) counters.
        Uses synchronous nextCmd walk.
        """
        def _walk_sum(oid_str):
            if not self.snmp_engine or not nextCmd:
                return 0
            auth_data = self._build_auth_data()
            if not auth_data:
                return 0
            try:
                total = 0
                
                # Synchronous Walk
                for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                    self.snmp_engine,
                    auth_data,
                    UdpTransportTarget((self.target, self.port), timeout=2.0, retries=2),
                    ContextData(),
                    ObjectType(ObjectIdentity(oid_str)),
                    lexicographicMode=False, lookupMib=False
                ):
                    if errorIndication or errorStatus:
                        break
                    
                    for varBind in varBinds:
                        # oid = varBind[0]
                        value = varBind[1]
                        try:
                            total += int(value)
                        except:
                            pass
                
                return total
            except Exception as e:
                return 0

        i64 = _walk_sum('1.3.6.1.2.1.31.1.1.1.6') # ifHCInOctets
        o64 = _walk_sum('1.3.6.1.2.1.31.1.1.1.10') # ifHCOutOctets
        
        if i64 == 0 and o64 == 0:
            i32 = _walk_sum('1.3.6.1.2.1.2.2.1.10') # ifInOctets
            o32 = _walk_sum('1.3.6.1.2.1.2.2.1.16') # ifOutOctets
            return {"in": i32, "out": o32}
        return {"in": i64, "out": o64}

    @staticmethod
    def normalize_interface_name(name: str) -> str:
        s = str(name or "").strip()
        if not s:
            return ""
        s = s.replace(" ", "")
        low = s.lower()
        mapping = {
            "gi": "gigabitethernet",
            "fa": "fastethernet",
            "te": "tengigabitethernet",
            "fo": "fortygigabitethernet",
            "hu": "hundredgigabitethernet",
            "et": "ethernet",
            "po": "port-channel",
            "portchannel": "port-channel",
            "vl": "vlan",
        }
        for short, full in mapping.items():
            if low.startswith(short) and not low.startswith(full):
                import re
                m = re.search(r"(\d.*)", s)
                if m:
                    return f"{full}{m.group(1)}"
        return low

    @staticmethod
    def normalize_mac(value) -> str:
        if value is None:
            return ""
        if isinstance(value, (bytes, bytearray)):
            b = bytes(value)
            if len(b) < 6:
                return ""
            s = b[:6].hex()
            return f"{s[0:4]}.{s[4:8]}.{s[8:12]}".lower()
        s0 = str(value).strip()
        if not s0:
            return ""
        s = s0.lower().replace("0x", "")
        s = re.sub(r"[^0-9a-f]", "", s)
        if len(s) < 12:
            return ""
        s = s[:12]
        return f"{s[0:4]}.{s[4:8]}.{s[8:12]}".lower()

    def get_interface_phys_address_map(self) -> Dict[str, str]:
        if not self.snmp_engine or not nextCmd:
            return {}
        names_by_idx = self.walk_table_column('1.3.6.1.2.1.31.1.1.1.1')  # ifName
        if not names_by_idx:
            names_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.2')  # ifDescr
        mac_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.6')  # ifPhysAddress
        if not names_by_idx or not mac_by_idx:
            return {}
        out: Dict[str, str] = {}
        for idx, name in names_by_idx.items():
            raw = mac_by_idx.get(idx)
            mac = self.normalize_mac(raw)
            if not mac:
                continue
            norm = self.normalize_interface_name(name)
            if norm:
                out[norm] = mac
        return out

    def get_mac_aliases(self) -> list[str]:
        macs = set()
        try:
            bridge = (self.get_oids(["1.3.6.1.2.1.17.1.1.0"]) or {}).get("1.3.6.1.2.1.17.1.1.0")
            m = self.normalize_mac(bridge)
            if m:
                macs.add(m)
        except Exception:
            pass
        try:
            for m in self.get_interface_phys_address_map().values():
                if m:
                    macs.add(m)
        except Exception:
            pass
        return sorted(macs)

    def get_interface_octets_map(self) -> Dict[str, Dict[str, int]]:
        if not self.snmp_engine or not nextCmd:
            return {}

        names_by_idx = self.walk_table_column('1.3.6.1.2.1.31.1.1.1.1')  # ifName
        if not names_by_idx:
            names_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.2')  # ifDescr

        in64_by_idx = self.walk_table_column('1.3.6.1.2.1.31.1.1.1.6')   # ifHCInOctets
        out64_by_idx = self.walk_table_column('1.3.6.1.2.1.31.1.1.1.10') # ifHCOutOctets
        use_32 = (not in64_by_idx) and (not out64_by_idx)
        if use_32:
            in64_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.10')  # ifInOctets
            out64_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.16') # ifOutOctets

        result: Dict[str, Dict[str, int]] = {}
        for idx, name in names_by_idx.items():
            n = str(name or "").strip()
            if not n:
                continue
            try:
                i = int(str(in64_by_idx.get(idx, "0")))
            except Exception:
                i = 0
            try:
                o = int(str(out64_by_idx.get(idx, "0")))
            except Exception:
                o = 0
            result[n] = {"in": i, "out": o}
        return result

    def get_interface_counters_map(self) -> Dict[str, Dict[str, int]]:
        if not self.snmp_engine or not nextCmd:
            return {}

        names_by_idx = self.walk_table_column('1.3.6.1.2.1.31.1.1.1.1')  # ifName
        if not names_by_idx:
            names_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.2')  # ifDescr

        in_octets_by_idx = self.walk_table_column('1.3.6.1.2.1.31.1.1.1.6')   # ifHCInOctets
        out_octets_by_idx = self.walk_table_column('1.3.6.1.2.1.31.1.1.1.10') # ifHCOutOctets
        use_32 = (not in_octets_by_idx) and (not out_octets_by_idx)
        if use_32:
            in_octets_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.10')  # ifInOctets
            out_octets_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.16') # ifOutOctets

        in_discards_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.13')  # ifInDiscards
        in_errors_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.14')    # ifInErrors
        out_discards_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.19') # ifOutDiscards
        out_errors_by_idx = self.walk_table_column('1.3.6.1.2.1.2.2.1.20')   # ifOutErrors

        result: Dict[str, Dict[str, int]] = {}
        for idx, name in names_by_idx.items():
            n = str(name or "").strip()
            if not n:
                continue
            try:
                i_oct = int(str(in_octets_by_idx.get(idx, "0")))
            except Exception:
                i_oct = 0
            try:
                o_oct = int(str(out_octets_by_idx.get(idx, "0")))
            except Exception:
                o_oct = 0
            try:
                i_err = int(str(in_errors_by_idx.get(idx, "0")))
            except Exception:
                i_err = 0
            try:
                o_err = int(str(out_errors_by_idx.get(idx, "0")))
            except Exception:
                o_err = 0
            try:
                i_dis = int(str(in_discards_by_idx.get(idx, "0")))
            except Exception:
                i_dis = 0
            try:
                o_dis = int(str(out_discards_by_idx.get(idx, "0")))
            except Exception:
                o_dis = 0

            result[n] = {
                "in_octets": i_oct,
                "out_octets": o_oct,
                "in_errors": i_err,
                "out_errors": o_err,
                "in_discards": i_dis,
                "out_discards": o_dis,
            }
        return result

    def get_interface_counters_for_ports(self, ports: list[str]) -> Dict[str, Dict[str, int]]:
        if not ports:
            return {}
        wanted = [self.normalize_interface_name(p) for p in ports if str(p or "").strip()]
        wanted_set = set([w for w in wanted if w])
        if not wanted_set:
            return {}

        counters = self.get_interface_counters_map()
        if not counters:
            return {}

        by_norm: Dict[str, Dict[str, int]] = {}
        for raw_name, v in counters.items():
            norm = self.normalize_interface_name(raw_name)
            if norm:
                by_norm[norm] = {
                    "in_octets": int(v.get("in_octets", 0) or 0),
                    "out_octets": int(v.get("out_octets", 0) or 0),
                    "in_errors": int(v.get("in_errors", 0) or 0),
                    "out_errors": int(v.get("out_errors", 0) or 0),
                    "in_discards": int(v.get("in_discards", 0) or 0),
                    "out_discards": int(v.get("out_discards", 0) or 0),
                }

        result: Dict[str, Dict[str, int]] = {}
        for p in wanted_set:
            if p in by_norm:
                result[p] = by_norm[p]
        return result

    def get_interface_octets_for_ports(self, ports: list[str]) -> Dict[str, Dict[str, int]]:
        if not ports:
            return {}
        wanted = [self.normalize_interface_name(p) for p in ports if str(p or "").strip()]
        wanted_set = set([w for w in wanted if w])
        if not wanted_set:
            return {}

        octets = self.get_interface_octets_map()
        if not octets:
            return {}

        by_norm: Dict[str, Dict[str, int]] = {}
        for raw_name, v in octets.items():
            norm = self.normalize_interface_name(raw_name)
            if norm:
                by_norm[norm] = {"in": int(v.get("in", 0) or 0), "out": int(v.get("out", 0) or 0)}

        result: Dict[str, Dict[str, int]] = {}
        for p in wanted_set:
            if p in by_norm:
                result[p] = by_norm[p]
        return result

    def get_resource_usage(self):
        """
        CPU, Memory, and Traffic Usage
        """
        cpu_oids = [
            '1.3.6.1.4.1.9.9.109.1.1.1.1.5.1',  # cpmCPUTotal5minRev
            '1.3.6.1.4.1.9.9.109.1.1.1.1.8.1',  # cpmCPUTotal1minRev
            '1.3.6.1.4.1.9.2.1.58.0',  # Old Cisco CPU
        ]
        mem_used_oid = '1.3.6.1.4.1.9.9.48.1.1.1.5.1'
        mem_free_oid = '1.3.6.1.4.1.9.9.48.1.1.1.6.1'

        target_oids = cpu_oids + [mem_used_oid, mem_free_oid]
        data = self._get_request(target_oids)
        
        traffic = self.get_total_octets()

        if not data:
            return {
                "cpu_usage": 0, "memory_usage": 0, "temperature": 0.0,
                "traffic_in": 0.0, "traffic_out": 0.0, 
                "raw_octets_in": traffic['in'], "raw_octets_out": traffic['out']
            }

        cpu_val = 0
        for oid in cpu_oids:
            if oid in data and data[oid] not in ('No Such Object', 'None'):
                try:
                    cpu_val = int(data[oid])
                    break
                except:
                    continue

        mem_percent = 0
        try:
            used = int(data.get(mem_used_oid, 0))
            free = int(data.get(mem_free_oid, 0))
            total = used + free
            if total > 0:
                mem_percent = (used / total) * 100
        except:
            mem_percent = 0

        return {
            "cpu_usage": cpu_val,
            "memory_usage": round(mem_percent, 2),
            "temperature": 0.0,
            "traffic_in": 0.0, 
            "traffic_out": 0.0,
            "raw_octets_in": traffic['in'], 
            "raw_octets_out": traffic['out']
        }

    def get_interface_statuses(self) -> Dict[int, str]:
        """
        SNMP WALK for ifOperStatus (Synchronous)
        """
        if not self.snmp_engine or not nextCmd:
            return {}
        auth_data = self._build_auth_data()
        if not auth_data:
            return {}
        try:
            results = {}
            for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                self.snmp_engine, auth_data,
                UdpTransportTarget((self.target, self.port), timeout=2.0, retries=2),
                ContextData(),
                ObjectType(ObjectIdentity('1.3.6.1.2.1.2.2.1.8')),
                lexicographicMode=False, lookupMib=False
            ):
                if errorIndication or errorStatus:
                    break
                for varBind in varBinds:
                    oid = str(varBind[0])
                    val = int(varBind[1])
                    try:
                        idx = int(oid.split('.')[-1])
                        results[idx] = 'up' if val == 1 else 'down'
                    except:
                        continue
            return results
        except Exception:
            return {}

    def get_interface_name_status_map(self) -> Dict[str, str]:
        """
        Build mapping of interface name -> oper status ('up'/'down') using ifName (preferred) or ifDescr.
        """
        def _walk_table(oid_str: str) -> Dict[int, str]:
            if not self.snmp_engine or not nextCmd:
                return {}
            auth_data = self._build_auth_data()
            if not auth_data:
                return {}
            results = {}
            try:
                for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                    self.snmp_engine, auth_data,
                    UdpTransportTarget((self.target, self.port), timeout=2.0, retries=2),
                    ContextData(),
                    ObjectType(ObjectIdentity(oid_str)),
                    lexicographicMode=False, lookupMib=False
                ):
                    if errorIndication or errorStatus:
                        break
                    for varBind in varBinds:
                        oid = str(varBind[0])
                        val = str(varBind[1])
                        try:
                            idx = int(oid.split('.')[-1])
                            results[idx] = val
                        except:
                            continue
            except Exception:
                return {}
            return results

        status_by_idx = self.get_interface_statuses()
        names_by_idx = _walk_table('1.3.6.1.2.1.31.1.1.1.1')  # ifName
        if not names_by_idx:
            names_by_idx = _walk_table('1.3.6.1.2.1.2.2.1.2')  # ifDescr

        result = {}
        for idx, name in names_by_idx.items():
            st = status_by_idx.get(idx)
            if st:
                result[str(name).strip()] = st
        return result

    def walk_table_column(self, oid_str: str) -> Dict[int, str]:
        if not self.snmp_engine or not nextCmd:
            return {}
        auth_data = self._build_auth_data()
        if not auth_data:
            return {}
        results: Dict[int, str] = {}
        try:
            for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                self.snmp_engine, auth_data,
                UdpTransportTarget((self.target, self.port), timeout=2.0, retries=2),
                ContextData(),
                ObjectType(ObjectIdentity(oid_str)),
                lexicographicMode=False, lookupMib=False
            ):
                if errorIndication or errorStatus:
                    break
                for varBind in varBinds:
                    oid = str(varBind[0])
                    val = str(varBind[1])
                    try:
                        idx = int(oid.split('.')[-1])
                        results[idx] = val
                    except Exception:
                        continue
        except Exception:
            return {}
        return results

    def walk_oid(self, oid_str: str, max_rows: int = 5000) -> Dict[str, str]:
        if not self.snmp_engine or not nextCmd:
            return {}
        auth_data = self._build_auth_data()
        if not auth_data:
            return {}
        results: Dict[str, str] = {}
        try:
            count = 0
            for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
                self.snmp_engine, auth_data,
                UdpTransportTarget((self.target, self.port), timeout=2.0, retries=2),
                ContextData(),
                ObjectType(ObjectIdentity(oid_str)),
                lexicographicMode=False, lookupMib=False
            ):
                if errorIndication or errorStatus:
                    break
                for varBind in varBinds:
                    results[str(varBind[0])] = str(varBind[1])
                    count += 1
                    if max_rows and count >= int(max_rows):
                        return results
        except Exception:
            return {}
        return results

    def get_wlc_client_count(self) -> int:
        data = self._get_request(['1.3.6.1.4.1.14179.2.1.1.1.38'])
        if data and '1.3.6.1.4.1.14179.2.1.1.1.38' in data:
            try:
                return int(data['1.3.6.1.4.1.14179.2.1.1.1.38'])
            except:
                pass
        return 0
