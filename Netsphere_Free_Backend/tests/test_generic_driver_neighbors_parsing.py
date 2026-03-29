from app.drivers.generic_driver import GenericDriver


class FakeConn:
    def __init__(self, mapping):
        self.mapping = mapping

    def send_command(self, cmd, **kwargs):
        key = f"{cmd}|textfsm" if kwargs.get("use_textfsm") else cmd
        v = self.mapping.get(key)
        if isinstance(v, Exception):
            raise v
        return v


def test_generic_driver_parses_lldp_raw_neighbors():
    raw = """
Local Intf: Gi1/0/1
Chassis id: 0011.2233.4455
Port id: Gi0/1
System Name: CORE-SW
Management Address: 10.0.0.1
System Description: DASAN Switch

Local Intf: Gi1/0/2
Port id: Gi0/2
System Name: EDGE-SW
"""
    d = GenericDriver("h", "u", "p", device_type="cisco_ios")
    d.connection = FakeConn({"show lldp neighbors detail|textfsm": None, "show lldp neighbors detail": raw})
    n = d.get_neighbors()
    assert any(x["protocol"] == "LLDP" and x["local_interface"] == "Gi1/0/1" and x["remote_interface"] == "Gi0/1" and x["neighbor_name"] == "CORE-SW" and x["mgmt_ip"] == "10.0.0.1" for x in n)


def test_generic_driver_parses_cdp_raw_neighbors():
    raw = """
Device ID: DIST-SW
Entry address(es):
  IP address: 10.0.0.2
Platform: cisco WS-C3850,  Capabilities: Switch IGMP
Interface: GigabitEthernet1/0/3,  Port ID (outgoing port): GigabitEthernet0/3
"""
    d = GenericDriver("h", "u", "p", device_type="cisco_ios")
    d.connection = FakeConn(
        {
            "show lldp neighbors detail|textfsm": None,
            "show lldp neighbors detail": "",
            "show cdp neighbors detail|textfsm": None,
            "show cdp neighbors detail": raw,
        }
    )
    n = d.get_neighbors()
    assert any(x["protocol"] == "CDP" and x["local_interface"].lower().startswith("gigabit") and x["remote_interface"].lower().startswith("gigabit") and x["neighbor_name"] == "DIST-SW" and x["mgmt_ip"] == "10.0.0.2" for x in n)


def test_generic_driver_parses_aruba_lldp_detail_variants():
    raw = """
Local Port   : 1/1/49
ChassisType  : mac-address
ChassisId    : 00:2a:b1:cc:20:00
PortType     : interface-name
PortId       : Ethernet1/1
SysName      : Spine-CE-01
Mgmt Address : 10.255.255.101
"""
    d = GenericDriver("h", "u", "p", device_type="hp_procurve")
    d.connection = FakeConn({"show lldp neighbor-info detail|textfsm": None, "show lldp neighbor-info detail": raw})
    n = d.get_neighbors()
    assert any(
        x["protocol"] == "LLDP"
        and x["local_interface"] == "1/1/49"
        and x["remote_interface"] == "Ethernet1/1"
        and x["neighbor_name"] == "Spine-CE-01"
        and x["mgmt_ip"] == "10.255.255.101"
        for x in n
    )


def test_generic_driver_parses_comware_lldp_verbose_output():
    raw = """
LLDP neighbor-information of port 49[FortyGigE1/0/49]:
Neighbor index : 1
Chassis type   : MAC address
Chassis ID     : 002a-b1cc-2000
Port ID type   : Interface name
Port ID        : FortyGigE1/0/1
System name    : Spine-01
Management address                : 10.255.255.101
"""
    d = GenericDriver("h", "u", "p", device_type="hp_comware")
    d.connection = FakeConn({"display lldp neighbor-information verbose|textfsm": None, "display lldp neighbor-information verbose": raw})
    n = d.get_neighbors()
    assert any(
        x["protocol"] == "LLDP"
        and x["local_interface"] == "FortyGigE1/0/49"
        and x["remote_interface"] == "FortyGigE1/0/1"
        and x["neighbor_name"] == "Spine-01"
        and x["mgmt_ip"] == "10.255.255.101"
        for x in n
    )


def test_generic_driver_parses_cisco_wlc_summary_neighbors():
    cdp_raw = """
Device ID        Local Intrfce     Holdtme    Capability  Platform         Port ID
---------------- ----------------- ---------- ----------  ---------------- ---------
Core-SW-01       1                 162        R S I       WS-C3850-24T     TenGigabitEthernet1/1/1
"""
    lldp_raw = """
Device ID        Local Intrfce     Holdtme    Capability  Platform         Port ID
---------------- ----------------- ---------- ----------  ---------------- ---------
Core-SW-01       1                 100        B,R         Cisco IOS Softwa Te1/1/1
"""
    d = GenericDriver("h", "u", "p", device_type="cisco_wlc")
    d.connection = FakeConn(
        {
            "show lldp neighbors detail|textfsm": None,
            "show lldp neighbors detail": "",
            "show lldp neighbors|textfsm": None,
            "show lldp neighbors": lldp_raw,
            "show cdp neighbors|textfsm": None,
            "show cdp neighbors": cdp_raw,
        }
    )
    n = d.get_neighbors()
    assert any(
        x["protocol"] == "CDP"
        and x["local_interface"] == "1"
        and x["remote_interface"] == "TenGigabitEthernet1/1/1"
        and x["neighbor_name"] == "Core-SW-01"
        for x in n
    )
    assert any(
        x["protocol"] == "LLDP"
        and x["local_interface"] == "1"
        and x["remote_interface"] == "Te1/1/1"
        and x["neighbor_name"] == "Core-SW-01"
        for x in n
    )


def test_generic_driver_parses_f5_lldp_summary_neighbors():
    raw = """
-------------------------------------------------------------------------
Net::LLDP Neighbors
-------------------------------------------------------------------------
Local Port  Chassis ID          Port ID           System Name
-------------------------------------------------------------------------
1.1         00:2a:b1:cc:20:00   Ethernet1/1       Core-SW-01
1.2         00:2a:b1:cc:20:00   Ethernet1/2       Core-SW-01
"""
    d = GenericDriver("h", "u", "p", device_type="f5_ltm")
    d.connection = FakeConn(
        {
            "show net lldp-neighbors|textfsm": None,
            "show net lldp-neighbors": raw,
            "show cdp neighbors detail|textfsm": None,
            "show cdp neighbors detail": "",
        }
    )
    n = d.get_neighbors()
    assert any(
        x["protocol"] == "LLDP"
        and x["local_interface"] == "1.1"
        and x["remote_interface"] == "Ethernet1/1"
        and x["neighbor_name"] == "Core-SW-01"
        for x in n
    )
    assert any(
        x["protocol"] == "LLDP"
        and x["local_interface"] == "1.2"
        and x["remote_interface"] == "Ethernet1/2"
        and x["neighbor_name"] == "Core-SW-01"
        for x in n
    )


def test_generic_driver_parses_alcatel_lldp_remote_system():
    raw = """
Local Port     : 1/1/49
Chassis ID     : 00:2a:b1:cc:20:00
Port ID        : Ethernet 1/1
System Name    : Spine-01
System Descr   : Alcatel-Lucent Enterprise OS6900-X48C6 8.7.468.R02
"""
    d = GenericDriver("h", "u", "p", device_type="alcatel_aos")
    d.connection = FakeConn(
        {
            "show lldp remote-system|textfsm": None,
            "show lldp remote-system": raw,
            "show cdp neighbors detail|textfsm": None,
            "show cdp neighbors detail": "",
        }
    )
    n = d.get_neighbors()
    assert any(
        x["protocol"] == "LLDP"
        and x["local_interface"] == "1/1/49"
        and x["remote_interface"] == "Ethernet 1/1"
        and x["neighbor_name"] == "Spine-01"
        for x in n
    )
