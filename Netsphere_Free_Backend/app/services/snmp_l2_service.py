import re
from typing import Any, Dict, List, Optional, Tuple

from app.services.snmp_service import SnmpManager


class SnmpL2Service:
    LLDP_LOC_PORT_ID = "1.0.8802.1.1.2.1.3.7.1.3"
    LLDP_LOC_PORT_DESC = "1.0.8802.1.1.2.1.3.7.1.4"
    LLDP_REM_SYS_NAME = "1.0.8802.1.1.2.1.4.1.1.9"
    LLDP_REM_PORT_ID = "1.0.8802.1.1.2.1.4.1.1.7"
    LLDP_REM_CHASSIS_ID_SUBTYPE = "1.0.8802.1.1.2.1.4.1.1.4"
    LLDP_REM_CHASSIS_ID = "1.0.8802.1.1.2.1.4.1.1.5"
    LLDP_REM_MAN_ADDR = "1.0.8802.1.1.2.1.4.2.1.2"

    CDP_CACHE_ADDRESS = "1.3.6.1.4.1.9.9.23.1.2.1.1.4"
    CDP_CACHE_DEVICE_ID = "1.3.6.1.4.1.9.9.23.1.2.1.1.6"
    CDP_CACHE_DEVICE_PORT = "1.3.6.1.4.1.9.9.23.1.2.1.1.7"
    CDP_CACHE_SYS_NAME = "1.3.6.1.4.1.9.9.23.1.2.1.1.17"

    DOT1D_BASE_PORT_IFINDEX = "1.3.6.1.2.1.17.1.4.1.2"
    DOT1D_TP_FDB_PORT = "1.3.6.1.2.1.17.4.3.1.2"

    DOT1Q_VLAN_FDB_ID = "1.3.6.1.2.1.17.7.1.4.3.1.2"
    DOT1Q_TP_FDB_PORT = "1.3.6.1.2.1.17.7.1.2.2.1.2"
    DOT1Q_TP_FDB_STATUS = "1.3.6.1.2.1.17.7.1.2.2.1.3"

    IP_NET_TO_MEDIA_PHYS = "1.3.6.1.2.1.4.22.1.2"
    IP_NET_TO_MEDIA_NET = "1.3.6.1.2.1.4.22.1.3"

    IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
    IF_DESCR = "1.3.6.1.2.1.2.2.1.2"

    @staticmethod
    def _oid_suffix(oid: str, base: str) -> List[str]:
        if not oid.startswith(base + "."):
            return []
        return oid[len(base) + 1 :].split(".")

    @staticmethod
    def _mac_from_oid_suffix(parts: List[str]) -> str:
        if len(parts) < 6:
            return ""
        try:
            octets = [int(x) for x in parts[:6]]
        except Exception:
            return ""
        hexs = ["%02x" % b for b in octets]
        s = "".join(hexs)
        return f"{s[0:4]}.{s[4:8]}.{s[8:12]}"

    @staticmethod
    def _mac_from_snmp_value(v: str) -> str:
        s = str(v or "").strip()
        if not s:
            return ""
        if s.lower().startswith("0x"):
            s = s[2:]
        s = re.sub(r"[^0-9a-fA-F]", "", s)
        s = s.lower()
        if len(s) != 12:
            return ""
        return f"{s[0:4]}.{s[4:8]}.{s[8:12]}"

    @staticmethod
    def _ipv4_from_snmp_value(v: str) -> str:
        s = str(v or "").strip()
        if not s:
            return ""
        if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", s):
            return s
        if s.lower().startswith("0x"):
            s = s[2:]
        s = re.sub(r"[^0-9a-fA-F]", "", s)
        if len(s) == 8:
            try:
                octets = [str(int(s[i : i + 2], 16)) for i in range(0, 8, 2)]
                return ".".join(octets)
            except Exception:
                return ""
        return ""

    @staticmethod
    def get_lldp_neighbors(snmp: SnmpManager, max_rows: int = 3000) -> List[Dict[str, Any]]:
        if not snmp:
            return []

        loc_port_id = snmp.walk_table_column(SnmpL2Service.LLDP_LOC_PORT_ID)
        loc_port_desc = snmp.walk_table_column(SnmpL2Service.LLDP_LOC_PORT_DESC)

        sys_names = snmp.walk_oid(SnmpL2Service.LLDP_REM_SYS_NAME, max_rows=max_rows)
        port_ids = snmp.walk_oid(SnmpL2Service.LLDP_REM_PORT_ID, max_rows=max_rows)
        chassis_subtypes = snmp.walk_oid(SnmpL2Service.LLDP_REM_CHASSIS_ID_SUBTYPE, max_rows=max_rows)
        chassis_ids = snmp.walk_oid(SnmpL2Service.LLDP_REM_CHASSIS_ID, max_rows=max_rows)
        man_addrs = snmp.walk_oid(SnmpL2Service.LLDP_REM_MAN_ADDR, max_rows=max_rows)

        def local_name(local_port_num: int) -> str:
            return str(loc_port_id.get(local_port_num) or loc_port_desc.get(local_port_num) or "").strip()

        by_key: Dict[Tuple[int, int], Dict[str, Any]] = {}

        for oid, val in sys_names.items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.LLDP_REM_SYS_NAME)
            if len(parts) < 3:
                continue
            try:
                local_port_num = int(parts[-2])
                rem_index = int(parts[-1])
            except Exception:
                continue
            k = (local_port_num, rem_index)
            by_key.setdefault(k, {})
            by_key[k]["neighbor_name"] = str(val).strip()

        for oid, val in port_ids.items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.LLDP_REM_PORT_ID)
            if len(parts) < 3:
                continue
            try:
                local_port_num = int(parts[-2])
                rem_index = int(parts[-1])
            except Exception:
                continue
            k = (local_port_num, rem_index)
            by_key.setdefault(k, {})
            by_key[k]["remote_interface"] = str(val).strip()

        chassis_mac_by_key: Dict[Tuple[int, int], str] = {}
        chassis_sub_by_key: Dict[Tuple[int, int], int] = {}
        for oid, val in (chassis_subtypes or {}).items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.LLDP_REM_CHASSIS_ID_SUBTYPE)
            if len(parts) < 3:
                continue
            try:
                local_port_num = int(parts[-2])
                rem_index = int(parts[-1])
                subtype = int(str(val).strip())
            except Exception:
                continue
            chassis_sub_by_key[(local_port_num, rem_index)] = subtype

        for oid, val in (chassis_ids or {}).items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.LLDP_REM_CHASSIS_ID)
            if len(parts) < 3:
                continue
            try:
                local_port_num = int(parts[-2])
                rem_index = int(parts[-1])
            except Exception:
                continue
            subtype = chassis_sub_by_key.get((local_port_num, rem_index))
            if subtype == 4:
                mac = SnmpL2Service._mac_from_snmp_value(val)
                if mac:
                    chassis_mac_by_key[(local_port_num, rem_index)] = mac

        mgmt_ip_by_key: Dict[Tuple[int, int], str] = {}
        for oid in (man_addrs or {}).keys():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.LLDP_REM_MAN_ADDR)
            if len(parts) < 6:
                continue
            try:
                local_port_num = int(parts[1])
                rem_index = int(parts[2])
                addr_len = int(parts[4])
            except Exception:
                continue
            addr_octets = parts[5 : 5 + addr_len]
            if addr_len == 4 and len(addr_octets) >= 4:
                try:
                    mgmt_ip_by_key.setdefault((local_port_num, rem_index), ".".join(str(int(x)) for x in addr_octets[:4]))
                except Exception:
                    continue

        arp_mac_to_ip: Dict[str, str] = {}
        arp_phys = snmp.walk_oid(SnmpL2Service.IP_NET_TO_MEDIA_PHYS, max_rows=max_rows)
        for oid, v in (arp_phys or {}).items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.IP_NET_TO_MEDIA_PHYS)
            if len(parts) < 5:
                continue
            ip_parts = parts[1:5]
            try:
                ip = ".".join(str(int(x)) for x in ip_parts)
            except Exception:
                continue
            mac = SnmpL2Service._mac_from_snmp_value(v)
            if mac and ip:
                arp_mac_to_ip.setdefault(mac, ip)

        results: List[Dict[str, Any]] = []
        for (local_port_num, _), data in by_key.items():
            li = local_name(local_port_num)
            ri = str(data.get("remote_interface") or "").strip()
            nn = str(data.get("neighbor_name") or "").strip()
            if not li or not ri:
                continue
            mgmt_ip = mgmt_ip_by_key.get((local_port_num, _), "")
            if not mgmt_ip:
                chassis_mac = chassis_mac_by_key.get((local_port_num, _), "")
                if chassis_mac:
                    mgmt_ip = arp_mac_to_ip.get(chassis_mac, "")
            results.append(
                {
                    "local_interface": li,
                    "remote_interface": ri,
                    "neighbor_name": nn,
                    "mgmt_ip": mgmt_ip,
                    "protocol": "LLDP",
                    "discovery_source": "snmp_lldp",
                }
            )
        return results

    @staticmethod
    def get_cdp_neighbors(snmp: SnmpManager, max_rows: int = 3000) -> List[Dict[str, Any]]:
        if not snmp:
            return []

        addrs = snmp.walk_oid(SnmpL2Service.CDP_CACHE_ADDRESS, max_rows=max_rows)
        dev_ids = snmp.walk_oid(SnmpL2Service.CDP_CACHE_DEVICE_ID, max_rows=max_rows)
        dev_ports = snmp.walk_oid(SnmpL2Service.CDP_CACHE_DEVICE_PORT, max_rows=max_rows)
        sys_names = snmp.walk_oid(SnmpL2Service.CDP_CACHE_SYS_NAME, max_rows=max_rows)

        by_key: Dict[Tuple[int, int], Dict[str, Any]] = {}

        for oid, v in (dev_ids or {}).items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.CDP_CACHE_DEVICE_ID)
            if len(parts) < 2:
                continue
            try:
                if_index = int(parts[-2])
                dev_index = int(parts[-1])
            except Exception:
                continue
            by_key.setdefault((if_index, dev_index), {})
            by_key[(if_index, dev_index)]["neighbor_name"] = str(v).strip()

        for oid, v in (sys_names or {}).items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.CDP_CACHE_SYS_NAME)
            if len(parts) < 2:
                continue
            try:
                if_index = int(parts[-2])
                dev_index = int(parts[-1])
            except Exception:
                continue
            by_key.setdefault((if_index, dev_index), {})
            by_key[(if_index, dev_index)]["neighbor_sysname"] = str(v).strip()

        for oid, v in (dev_ports or {}).items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.CDP_CACHE_DEVICE_PORT)
            if len(parts) < 2:
                continue
            try:
                if_index = int(parts[-2])
                dev_index = int(parts[-1])
            except Exception:
                continue
            by_key.setdefault((if_index, dev_index), {})
            by_key[(if_index, dev_index)]["remote_interface"] = str(v).strip()

        for oid, v in (addrs or {}).items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.CDP_CACHE_ADDRESS)
            if len(parts) < 2:
                continue
            try:
                if_index = int(parts[-2])
                dev_index = int(parts[-1])
            except Exception:
                continue
            by_key.setdefault((if_index, dev_index), {})
            by_key[(if_index, dev_index)]["mgmt_ip"] = SnmpL2Service._ipv4_from_snmp_value(v)

        if_names = snmp.walk_table_column(SnmpL2Service.IF_NAME) or snmp.walk_table_column(SnmpL2Service.IF_DESCR)

        results: List[Dict[str, Any]] = []
        for (if_index, dev_index), data in by_key.items():
            local_if = str(if_names.get(int(if_index)) or "").strip()
            remote_if = str(data.get("remote_interface") or "").strip()
            neighbor_name = str(data.get("neighbor_sysname") or data.get("neighbor_name") or "").strip()
            mgmt_ip = str(data.get("mgmt_ip") or "").strip()
            if not local_if or not remote_if:
                continue
            results.append(
                {
                    "local_interface": local_if,
                    "remote_interface": remote_if,
                    "neighbor_name": neighbor_name,
                    "mgmt_ip": mgmt_ip,
                    "protocol": "CDP",
                    "discovery_source": "snmp_cdp",
                }
            )
        return results

    @staticmethod
    def get_bridge_mac_table(snmp: SnmpManager, max_rows: int = 8000) -> List[Dict[str, Any]]:
        if not snmp:
            return []

        bridge_port_to_ifindex = snmp.walk_table_column(SnmpL2Service.DOT1D_BASE_PORT_IFINDEX)
        if_names = snmp.walk_table_column(SnmpL2Service.IF_NAME) or snmp.walk_table_column(SnmpL2Service.IF_DESCR)

        fdb_port = snmp.walk_oid(SnmpL2Service.DOT1D_TP_FDB_PORT, max_rows=max_rows)
        if not fdb_port:
            return []

        results: List[Dict[str, Any]] = []
        for oid, port_val in fdb_port.items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.DOT1D_TP_FDB_PORT)
            mac = SnmpL2Service._mac_from_oid_suffix(parts)
            if not mac:
                continue
            try:
                bridge_port = int(str(port_val).strip())
            except Exception:
                continue
            if_index = bridge_port_to_ifindex.get(bridge_port)
            if if_index is None:
                continue
            try:
                if_index_i = int(if_index)
            except Exception:
                continue
            if_name = str(if_names.get(if_index_i) or "").strip()
            if not if_name:
                continue
            results.append({"mac": mac, "vlan": None, "port": if_name, "type": "dynamic", "discovery_source": "snmp_bridge"})
        return results

    @staticmethod
    def get_qbridge_mac_table(snmp: SnmpManager, max_rows: int = 20000) -> List[Dict[str, Any]]:
        if not snmp:
            return []

        bridge_port_to_ifindex = snmp.walk_table_column(SnmpL2Service.DOT1D_BASE_PORT_IFINDEX)
        if_names = snmp.walk_table_column(SnmpL2Service.IF_NAME) or snmp.walk_table_column(SnmpL2Service.IF_DESCR)

        vlan_fdb = snmp.walk_oid(SnmpL2Service.DOT1Q_VLAN_FDB_ID, max_rows=max_rows)
        fdbid_to_vlan: Dict[int, int] = {}
        for oid, v in (vlan_fdb or {}).items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.DOT1Q_VLAN_FDB_ID)
            if len(parts) != 1:
                continue
            try:
                vlan = int(parts[0])
                fdbid = int(str(v).strip())
            except Exception:
                continue
            if fdbid > 0 and vlan > 0:
                fdbid_to_vlan[fdbid] = vlan

        fdb_port = snmp.walk_oid(SnmpL2Service.DOT1Q_TP_FDB_PORT, max_rows=max_rows)
        if not fdb_port:
            return []
        fdb_status = snmp.walk_oid(SnmpL2Service.DOT1Q_TP_FDB_STATUS, max_rows=max_rows)

        results: List[Dict[str, Any]] = []
        for oid, port_val in fdb_port.items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.DOT1Q_TP_FDB_PORT)
            if len(parts) < 7:
                continue
            try:
                fdbid = int(parts[0])
            except Exception:
                continue
            mac = SnmpL2Service._mac_from_oid_suffix(parts[1:7])
            if not mac:
                continue
            try:
                bridge_port = int(str(port_val).strip())
            except Exception:
                continue
            if_index = bridge_port_to_ifindex.get(bridge_port)
            if if_index is None:
                continue
            try:
                if_index_i = int(if_index)
            except Exception:
                continue
            if_name = str(if_names.get(if_index_i) or "").strip()
            if not if_name:
                continue

            vlan = fdbid_to_vlan.get(fdbid)
            if vlan is None:
                vlan = fdbid if fdbid > 0 else None

            st_key = f"{SnmpL2Service.DOT1Q_TP_FDB_STATUS}.{'.'.join(parts)}"
            st = fdb_status.get(st_key)
            entry_type = "dynamic"
            try:
                if st is not None and int(str(st).strip()) == 4:
                    entry_type = "static"
            except Exception:
                pass

            results.append({"mac": mac, "vlan": str(vlan) if vlan is not None else None, "port": if_name, "type": entry_type, "discovery_source": "snmp_qbridge"})
        return results

    @staticmethod
    def get_arp_table(snmp: SnmpManager, max_rows: int = 6000) -> List[Dict[str, Any]]:
        if not snmp:
            return []

        if_names = snmp.walk_table_column(SnmpL2Service.IF_NAME) or snmp.walk_table_column(SnmpL2Service.IF_DESCR)
        phys = snmp.walk_oid(SnmpL2Service.IP_NET_TO_MEDIA_PHYS, max_rows=max_rows)
        if not phys:
            return []

        results: List[Dict[str, Any]] = []
        for oid, mac_val in phys.items():
            parts = SnmpL2Service._oid_suffix(oid, SnmpL2Service.IP_NET_TO_MEDIA_PHYS)
            if len(parts) < 5:
                continue
            try:
                if_index = int(parts[0])
                ip = ".".join(parts[1:5])
            except Exception:
                continue
            mac = SnmpL2Service._mac_from_snmp_value(mac_val)
            if not mac:
                continue
            intf = str(if_names.get(if_index) or "").strip()
            results.append({"ip": ip, "mac": mac, "interface": intf or None, "discovery_source": "snmp_arp"})
        return results
