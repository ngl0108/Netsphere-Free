import unittest
from unittest.mock import MagicMock

from app.drivers.korea.domestic_cisco_like_driver import CoreEdgeDriver, NSTDriver, SoltechDriver


class _DomesticDriverAssertions:
    driver_class = None
    vendor_name = ""
    model_name = ""

    def setUp(self):
        self.driver = self.driver_class("10.0.0.1", "admin", "password")
        self.driver.connection = MagicMock()

    def test_get_facts(self):
        self.driver.connection.send_command.return_value = f"""
        {self.vendor_name} NOS Software, Version 1.2.3
        System Name : {self.vendor_name}-Lab
        Model : {self.model_name}
        Serial Number : SN12345678
        System uptime is 12 days, 01:22:33
        """
        facts = self.driver.get_facts()
        self.assertEqual(facts["vendor"], self.vendor_name)
        self.assertEqual(facts["hostname"], f"{self.vendor_name}-Lab")
        self.assertEqual(facts["model"], self.model_name)
        self.assertEqual(facts["serial_number"], "SN12345678")
        self.assertTrue("1.2.3" in facts["os_version"])

    def test_get_neighbors_parsing(self):
        self.driver.connection.send_command.side_effect = [
            "",
            """
            Local Intf: Gi1/0/1
            Port id: Gi0/48
            System Name: LAB-CORE
            Management Address: 10.10.10.1
            """,
        ]
        neighbors = self.driver.get_neighbors()
        self.assertEqual(len(neighbors), 1)
        self.assertEqual(neighbors[0]["local_interface"], "Gi1/0/1")
        self.assertEqual(neighbors[0]["remote_interface"], "Gi0/48")
        self.assertEqual(neighbors[0]["neighbor_name"], "LAB-CORE")
        self.assertEqual(neighbors[0]["mgmt_ip"], "10.10.10.1")


class TestSoltechDriver(_DomesticDriverAssertions, unittest.TestCase):
    driver_class = SoltechDriver
    vendor_name = "Soltech"
    model_name = "SFC5248XG"


class TestCoreEdgeDriver(_DomesticDriverAssertions, unittest.TestCase):
    driver_class = CoreEdgeDriver
    vendor_name = "CoreEdge"
    model_name = "C3300-48GT"


class TestNSTDriver(_DomesticDriverAssertions, unittest.TestCase):
    driver_class = NSTDriver
    vendor_name = "NST"
    model_name = "NST-4828G"


if __name__ == "__main__":
    unittest.main()
