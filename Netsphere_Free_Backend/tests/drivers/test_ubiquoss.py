import unittest
from unittest.mock import MagicMock
from app.drivers.korea.ubiquoss_driver import UbiquossDriver

class TestUbiquossDriver(unittest.TestCase):
    def setUp(self):
        self.driver = UbiquossDriver("2.2.2.2", "admin", "password")
        self.driver.connection = MagicMock()

    def test_get_facts(self):
        # Mock 'show version'
        self.driver.connection.send_command.return_value = """
        Ubiquoss NOS Software, Version 3.1.2
        Copyright (c) 2000-2023 by Ubiquoss Inc.
        
        Model          : E4200
        Uptime is 20 weeks, 3 days, 1 hours, 22 minutes
        """
        
        facts = self.driver.get_facts()
        self.assertEqual(facts["vendor"], "Ubiquoss")
        self.assertEqual(facts["model"], "E4200")
        self.assertTrue("3.1.2" in facts["os_version"])

    def test_get_neighbors_parsing(self):
        # Mock 'show lldp neighbors' (Cisco-like)
        raw_output = """
Device ID      Local Intf      Holdtme      Capability      Port ID
Switch-Core    Gi0/24          120          R S             Gi1/0/1
Switch-Access  Gi0/23          120          S               Gi0/1
        """
        self.driver.connection.send_command.return_value = raw_output
        
        neighbors = self.driver.get_neighbors()
        self.assertEqual(len(neighbors), 2)
        
        n1 = neighbors[0]
        self.assertEqual(n1["neighbor_name"], "Switch-Core")
        self.assertEqual(n1["local_interface"], "Gi0/24")
        self.assertEqual(n1["remote_interface"], "Gi1/0/1")

    def test_get_facts_falls_back_to_show_running_real_output(self):
        self.driver.connection.send_command.side_effect = [
            "",
            """
E4020-24PS#show running

Wed Jan 01 2025 09:48:12 UTC

Building configuration...

hostname E4020-24PS

boot system os1: UbiEnt.r255.bin

service ssh
service telnet
            """,
        ]

        facts = self.driver.get_facts()
        self.assertEqual(facts["vendor"], "Ubiquoss")
        self.assertEqual(facts["hostname"], "E4020-24PS")
        self.assertEqual(facts["model"], "E4020-24PS")

if __name__ == '__main__':
    unittest.main()
