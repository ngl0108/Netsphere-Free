from app.services.discovery.handlers.snmp import SnmpScanHandler


def test_snmp_scan_handler_records_fingerprint_metadata_for_platform_specific_devices():
    class FakeSnmp:
        def __init__(self, ip, community, port=161, version="v2c", **kwargs):
            self.ip = ip

        def get_system_info(self):
            return {
                "sysName": "core-n9k-01",
                "sysDescr": "Cisco Nexus Operating System (NX-OS) Software, Version 10.2(3), Nexus9000 C93180YC-FX",
                "sysObjectID": "1.3.6.1.4.1.9.1.1208",
            }

        def get_oids(self, oids):
            return {}

    handler = SnmpScanHandler(snmp_manager_cls=FakeSnmp)
    result = handler.scan("10.10.10.10", {"community": "public", "version": "v2c"})

    assert result is not None
    assert result["vendor"] == "Cisco"
    assert result["device_type"] == "cisco_nxos"
    assert result["model"] == "C93180YC-FX"
    assert result["vendor_confidence"] >= 0.9
    assert result["evidence"]["fingerprint"] == {
        "match_source": "oid",
        "rule_id": "cisco:nxos",
        "platform": "nexus",
        "family": "datacenter",
        "os_family": "nxos",
        "device_type": "cisco_nxos",
        "model_hint": "C93180YC-FX",
    }


def test_snmp_scan_handler_records_fingerprint_metadata_for_fortinet():
    class FakeSnmp:
        def __init__(self, ip, community, port=161, version="v2c", **kwargs):
            self.ip = ip

        def get_system_info(self):
            return {
                "sysName": "FortiGate-HA",
                "sysDescr": "FortiGate-1000D FortiOS v7.0.5",
                "sysObjectID": "1.3.6.1.4.1.12356.101.1.514",
            }

        def get_oids(self, oids):
            return {}

    handler = SnmpScanHandler(snmp_manager_cls=FakeSnmp)
    result = handler.scan("10.10.10.20", {"community": "public", "version": "v2c"})

    assert result is not None
    assert result["vendor"] == "Fortinet"
    assert result["device_type"] == "fortinet"
    assert result["model"] == "FortiGate-1000D"
    assert result["evidence"]["fingerprint"] == {
        "match_source": "oid",
        "rule_id": "fortinet:fortigate:oid",
        "platform": "fortigate",
        "family": "security",
        "os_family": "fortios",
        "device_type": "fortinet",
        "model_hint": "FortiGate-1000D",
    }


def test_snmp_scan_handler_records_fingerprint_metadata_for_paloalto():
    class FakeSnmp:
        def __init__(self, ip, community, port=161, version="v2c", **kwargs):
            self.ip = ip

        def get_system_info(self):
            return {
                "sysName": "PA-3220-FW-A",
                "sysDescr": "Palo Alto Networks PA-3220 firewall PAN-OS 10.1.6-h6",
                "sysObjectID": "1.3.6.1.4.1.25461.2.3.43",
            }

        def get_oids(self, oids):
            return {}

    handler = SnmpScanHandler(snmp_manager_cls=FakeSnmp)
    result = handler.scan("10.10.10.21", {"community": "public", "version": "v2c"})

    assert result is not None
    assert result["vendor"] == "PaloAlto"
    assert result["device_type"] == "paloalto_panos"
    assert result["model"] == "PA-3220"
    assert result["evidence"]["fingerprint"] == {
        "match_source": "oid",
        "rule_id": "paloalto:panos:oid",
        "platform": "firewall",
        "family": "security",
        "os_family": "panos",
        "device_type": "paloalto_panos",
        "model_hint": "PA-3220",
    }


def test_snmp_scan_handler_records_fingerprint_metadata_for_h3c_and_hp_aos_switch():
    cases = [
        (
            {
                "sysName": "Core-H3C",
                "sysDescr": "H3C S6800-54QT Comware Software, Version 7.1.070",
                "sysObjectID": "1.3.6.1.4.1.25506.1.123",
            },
            {
                "vendor": "H3C",
                "device_type": "hp_comware",
                "model": "S6800-54QT",
                "fingerprint": {
                    "match_source": "oid",
                    "rule_id": "h3c:comware:oid",
                    "platform": "comware",
                    "family": "networking",
                    "os_family": "comware",
                    "device_type": "hp_comware",
                    "model_hint": "S6800-54QT",
                },
            },
        ),
        (
            {
                "sysName": "Access-2930F",
                "sysDescr": "Aruba 2930F-48G-4SFP+ Switch running AOS-Switch WC.16.11.0001",
                "sysObjectID": "1.3.6.1.4.1.11.2.3.7.11.160",
            },
            {
                "vendor": "HP",
                "device_type": "hp_procurve",
                "model": "2930F-48G-4SFP+",
                "fingerprint": {
                    "match_source": "oid",
                    "rule_id": "hp:aos_switch:oid",
                    "platform": "aos_switch",
                    "family": "switching",
                    "os_family": "aos_switch",
                    "device_type": "hp_procurve",
                    "model_hint": "2930F-48G-4SFP+",
                },
            },
        ),
    ]

    for sysinfo, expected in cases:
        class FakeSnmp:
            def __init__(self, ip, community, port=161, version="v2c", **kwargs):
                self.ip = ip

            def get_system_info(self):
                return sysinfo

            def get_oids(self, oids):
                return {}

        handler = SnmpScanHandler(snmp_manager_cls=FakeSnmp)
        result = handler.scan("10.10.10.40", {"community": "public", "version": "v2c"})

        assert result is not None
        assert result["vendor"] == expected["vendor"]
        assert result["device_type"] == expected["device_type"]
        assert result["model"] == expected["model"]
        assert result["evidence"]["fingerprint"] == expected["fingerprint"]


def test_snmp_scan_handler_records_fingerprint_metadata_for_checkpoint_and_f5():
    cases = [
        (
            {
                "sysName": "CP-Gateway",
                "sysDescr": "Check Point Gaia R81.10 6500 Appliance",
                "sysObjectID": "1.3.6.1.4.1.2620.1.6.123",
            },
                {
                    "vendor": "CheckPoint",
                    "device_type": "checkpoint_gaia",
                    "model": "6500",
                    "fingerprint": {
                        "match_source": "oid",
                        "rule_id": "checkpoint:gaia:oid",
                        "platform": "gaia",
                        "family": "security",
                        "os_family": "gaia",
                        "device_type": "checkpoint_gaia",
                        "model_hint": "6500",
                    },
                },
            ),
        (
            {
                "sysName": "BIG-IP-Active",
                "sysDescr": "F5 BIG-IP i5800 TMOS 15.1.8.2",
                "sysObjectID": "1.3.6.1.4.1.3375.2.1.3.4.119",
            },
            {
                "vendor": "F5",
                "device_type": "f5_ltm",
                "model": "BIG-IP i5800",
                "fingerprint": {
                    "match_source": "oid",
                    "rule_id": "f5:tmos:oid",
                    "platform": "bigip",
                    "family": "adc",
                    "os_family": "tmos",
                    "device_type": "f5_ltm",
                    "model_hint": "BIG-IP i5800",
                },
            },
        ),
    ]

    for sysinfo, expected in cases:
        class FakeSnmp:
            def __init__(self, ip, community, port=161, version="v2c", **kwargs):
                self.ip = ip

            def get_system_info(self):
                return sysinfo

            def get_oids(self, oids):
                return {}

        handler = SnmpScanHandler(snmp_manager_cls=FakeSnmp)
        result = handler.scan("10.10.10.30", {"community": "public", "version": "v2c"})

        assert result is not None
        assert result["vendor"] == expected["vendor"]
        assert result["device_type"] == expected["device_type"]
        assert result["model"] == expected["model"]
        assert result["evidence"]["fingerprint"] == expected["fingerprint"]
