import unittest
from unittest.mock import MagicMock
from app.drivers.korea.dasan_driver import DasanDriver

class TestDasanDriver(unittest.TestCase):
    def setUp(self):
        self.driver = DasanDriver("1.1.1.1", "admin", "password")
        self.driver.connection = MagicMock()

    def test_get_facts(self):
        # Mock 'show system info'
        self.driver.connection.send_command.side_effect = [
            """
            System Name        : Dasan-Switch
            System Type        : V8240
            Serial Number      : DS12345678
            NOS Version        : 5.02
            Up Time            : 10 day(s), 2 hour(s)
            """,
            "" # fallback for invalid command if needed
        ]
        
        facts = self.driver.get_facts()
        self.assertEqual(facts["vendor"], "Dasan")
        self.assertEqual(facts["hostname"], "Dasan-Switch")
        self.assertEqual(facts["model"], "V8240")
        self.assertEqual(facts["serial_number"], "DS12345678")
        self.assertEqual(facts["os_version"], "5.02")

    def test_get_neighbors_parsing(self):
        # Mock 'show lldp neighbor'
        raw_output = """
Local Port   Device ID          Port ID          System Name
---------------------------------------------------------------
1/1          00:11:22:33:44:55  gi0/1            Switch-A
1/2          00:AA:BB:CC:DD:EE  gi0/2            Switch-B
        """
        self.driver.connection.send_command.return_value = raw_output
        
        neighbors = self.driver.get_neighbors()
        self.assertEqual(len(neighbors), 2)
        
        n1 = neighbors[0]
        self.assertEqual(n1["local_interface"], "1/1")
        self.assertEqual(n1["remote_interface"], "gi0/1")
        self.assertEqual(n1["neighbor_name"], "Switch-A")
        
        n2 = neighbors[1]
        self.assertEqual(n2["local_interface"], "1/2")
        self.assertEqual(n2["remote_interface"], "gi0/2")

    def test_get_facts_falls_back_to_running_config_real_output(self):
        self.driver.connection.send_command.side_effect = [
            "",
            "",
            """
V5424G# show running-config

hostname V5424G

time-zone GMT+9

bridge vlan create 2
            """,
        ]

        facts = self.driver.get_facts()
        self.assertEqual(facts["vendor"], "Dasan")
        self.assertEqual(facts["hostname"], "V5424G")
        self.assertEqual(facts["model"], "V5424G")

    def test_get_facts_extracts_hostname_from_show_run_real_output(self):
        self.driver.connection.send_command.side_effect = [
            "",
            "",
            "",
            "",
            """
# show run

Building configuration...

Current configuration:
hostname taeyoungENT
!
interface br1
 ip address 112.xxx.xxx.126/25
            """,
        ]

        facts = self.driver.get_facts()
        self.assertEqual(facts["vendor"], "Dasan")
        self.assertEqual(facts["hostname"], "taeyoungENT")

if __name__ == '__main__':
    unittest.main()
