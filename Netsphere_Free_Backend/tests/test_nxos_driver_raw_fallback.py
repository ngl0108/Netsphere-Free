from app.drivers.cisco.nxos_driver import CiscoNXOSDriver


class FakeNxosConn:
    def __init__(self, mapping):
        self.mapping = mapping

    def send_command(self, cmd, **kwargs):
        key = f"{cmd}|textfsm" if kwargs.get("use_textfsm") else cmd
        value = self.mapping.get(key, "")
        if isinstance(value, Exception):
            raise value
        return value

    def find_prompt(self):
        return "Nexus-9K-Leaf1#"


def test_nxos_driver_parses_raw_facts_without_textfsm():
    driver = CiscoNXOSDriver("fixture-host", "u", "p")
    driver.connection = FakeNxosConn(
        {
            "show version|textfsm": None,
            "show inventory|textfsm": None,
            "show version": (
                "Cisco Nexus Operating System (NX-OS) Software\n"
                "  NXOS: version 9.3(10)\n"
                "  cisco Nexus9000 C93180YC-EX Chassis\n"
                "  Processor Board ID FDO2112XXXX\n"
                "  Device name: Nexus-9K-Leaf1\n"
                "Kernel uptime is 152 day(s), 14 hour(s), 22 minute(s), 45 second(s)\n"
            ),
            "show inventory": 'NAME: "Chassis",  DESCR: "Nexus9000 C93180YC-EX Chassis"\nPID: N9K-C93180YC-EX     ,  VID: V03 ,  SN: FDO2112XXXX\n',
        }
    )

    facts = driver.get_facts()

    assert facts["hostname"] == "Nexus-9K-Leaf1"
    assert facts["os_version"] == "9.3(10)"
    assert facts["model"] in {"N9K-C93180YC-EX", "Nexus9000 C93180YC-EX Chassis"}
    assert facts["serial_number"] == "FDO2112XXXX"
    assert facts["uptime"] == "152 day(s), 14 hour(s), 22 minute(s), 45 second(s)"


def test_nxos_driver_parses_raw_neighbor_details_without_textfsm():
    driver = CiscoNXOSDriver("fixture-host", "u", "p")
    driver.connection = FakeNxosConn(
        {
            "show lldp neighbors detail|textfsm": None,
            "show cdp neighbors detail|textfsm": None,
            "show lldp neighbors detail": (
                "Chassis id: 00a1.b2c3.d4e5\n"
                "Port id: Ethernet1/1\n"
                "Local Port id: Eth1/49\n"
                "System Name: Spine-9K-01\n"
                "Management Address: 10.255.255.101\n"
            ),
            "show cdp neighbors detail": (
                "----------------------------------------\n"
                "Device ID: Spine-9K-01(FDO2020XXXX)\n"
                "System Name: Spine-9K-01\n"
                "Interface: Ethernet1/49, Port ID (outgoing port): Ethernet1/1\n"
                "Mgmt address(es):\n"
                "  IPv4 Address: 10.255.255.101\n"
            ),
        }
    )

    neighbors = driver.get_neighbors()

    assert any(
        row["protocol"] == "LLDP"
        and row["local_interface"] == "Ethernet1/49"
        and row["remote_interface"] == "Ethernet1/1"
        and row["neighbor_name"] == "Spine-9K-01"
        and row["mgmt_ip"] == "10.255.255.101"
        for row in neighbors
    )
    assert any(
        row["protocol"] == "CDP"
        and row["local_interface"] == "Ethernet1/49"
        and row["remote_interface"] == "Ethernet1/1"
        and row["mgmt_ip"] == "10.255.255.101"
        for row in neighbors
    )
