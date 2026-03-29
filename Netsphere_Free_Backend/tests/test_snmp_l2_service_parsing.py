from app.services.snmp_l2_service import SnmpL2Service


class FakeSnmp:
    def __init__(self, table_cols=None, oid_data=None):
        self.table_cols = table_cols or {}
        self.oid_data = oid_data or {}

    def walk_table_column(self, oid_str: str):
        return self.table_cols.get(oid_str, {})

    def walk_oid(self, oid_str: str, max_rows: int = 5000):
        return self.oid_data.get(oid_str, {})


def test_bridge_mac_table_maps_bridge_port_to_ifname():
    snmp = FakeSnmp(
        table_cols={
            SnmpL2Service.DOT1D_BASE_PORT_IFINDEX: {5: "12"},
            SnmpL2Service.IF_NAME: {12: "Gi1/0/5"},
        },
        oid_data={
            SnmpL2Service.DOT1D_TP_FDB_PORT: {"1.3.6.1.2.1.17.4.3.1.2.0.17.34.51.68.85": "5"},
        },
    )
    rows = SnmpL2Service.get_bridge_mac_table(snmp)
    assert rows and rows[0]["port"] == "Gi1/0/5" and rows[0]["mac"] == "0011.2233.4455"

def test_qbridge_mac_table_maps_vlan_and_port():
    snmp = FakeSnmp(
        table_cols={
            SnmpL2Service.DOT1D_BASE_PORT_IFINDEX: {5: "12"},
            SnmpL2Service.IF_NAME: {12: "Gi1/0/5"},
        },
        oid_data={
            SnmpL2Service.DOT1Q_VLAN_FDB_ID: {"1.3.6.1.2.1.17.7.1.4.3.1.2.10": "100"},
            SnmpL2Service.DOT1Q_TP_FDB_PORT: {"1.3.6.1.2.1.17.7.1.2.2.1.2.100.0.17.34.51.68.85": "5"},
        },
    )
    rows = SnmpL2Service.get_qbridge_mac_table(snmp)
    assert rows and rows[0]["vlan"] == "10" and rows[0]["port"] == "Gi1/0/5" and rows[0]["mac"] == "0011.2233.4455"


def test_lldp_neighbors_parses_rem_tables_and_maps_local_port():
    snmp = FakeSnmp(
        table_cols={
            SnmpL2Service.LLDP_LOC_PORT_ID: {101: "Gi1/0/1"},
        },
        oid_data={
            SnmpL2Service.LLDP_REM_SYS_NAME: {"1.0.8802.1.1.2.1.4.1.1.9.12345.101.1": "CORE-SW"},
            SnmpL2Service.LLDP_REM_PORT_ID: {"1.0.8802.1.1.2.1.4.1.1.7.12345.101.1": "Gi0/1"},
        },
    )
    n = SnmpL2Service.get_lldp_neighbors(snmp)
    assert any(x["local_interface"] == "Gi1/0/1" and x["remote_interface"] == "Gi0/1" and x["neighbor_name"] == "CORE-SW" for x in n)

def test_lldp_neighbors_fills_mgmt_ip_from_chassis_mac_and_arp():
    snmp = FakeSnmp(
        table_cols={
            SnmpL2Service.LLDP_LOC_PORT_ID: {101: "Gi1/0/1"},
        },
        oid_data={
            SnmpL2Service.LLDP_REM_SYS_NAME: {"1.0.8802.1.1.2.1.4.1.1.9.12345.101.1": "EDGE-SW"},
            SnmpL2Service.LLDP_REM_PORT_ID: {"1.0.8802.1.1.2.1.4.1.1.7.12345.101.1": "Gi0/1"},
            SnmpL2Service.LLDP_REM_CHASSIS_ID_SUBTYPE: {"1.0.8802.1.1.2.1.4.1.1.4.12345.101.1": "4"},
            SnmpL2Service.LLDP_REM_CHASSIS_ID: {"1.0.8802.1.1.2.1.4.1.1.5.12345.101.1": "0x001122334455"},
            SnmpL2Service.IP_NET_TO_MEDIA_PHYS: {"1.3.6.1.2.1.4.22.1.2.2.10.0.0.5": "0x001122334455"},
        },
    )
    n = SnmpL2Service.get_lldp_neighbors(snmp)
    assert any(x["neighbor_name"] == "EDGE-SW" and x["mgmt_ip"] == "10.0.0.5" for x in n)

def test_cdp_neighbors_parses_cache_table_and_maps_local_ifname():
    snmp = FakeSnmp(
        table_cols={
            SnmpL2Service.IF_NAME: {12: "Gi1/0/12"},
        },
        oid_data={
            SnmpL2Service.CDP_CACHE_DEVICE_ID: {"1.3.6.1.4.1.9.9.23.1.2.1.1.6.12.1": "SW-CORE"},
            SnmpL2Service.CDP_CACHE_DEVICE_PORT: {"1.3.6.1.4.1.9.9.23.1.2.1.1.7.12.1": "Gi0/1"},
            SnmpL2Service.CDP_CACHE_ADDRESS: {"1.3.6.1.4.1.9.9.23.1.2.1.1.4.12.1": "0x0a000005"},
        },
    )
    n = SnmpL2Service.get_cdp_neighbors(snmp)
    assert any(x["local_interface"] == "Gi1/0/12" and x["remote_interface"] == "Gi0/1" and x["neighbor_name"] == "SW-CORE" and x["mgmt_ip"] == "10.0.0.5" for x in n)


def test_arp_table_parses_ipnettomedia_index_and_mac():
    snmp = FakeSnmp(
        table_cols={SnmpL2Service.IF_NAME: {2: "Vlan10"}},
        oid_data={
            SnmpL2Service.IP_NET_TO_MEDIA_PHYS: {"1.3.6.1.2.1.4.22.1.2.2.10.0.0.5": "0x001122334455"},
        },
    )
    rows = SnmpL2Service.get_arp_table(snmp)
    assert rows and rows[0]["ip"] == "10.0.0.5" and rows[0]["mac"] == "0011.2233.4455" and rows[0]["interface"] == "Vlan10"
