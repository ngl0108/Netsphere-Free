import pytest

from app.core.device_fingerprints import fingerprint_device, get_driver_for_vendor


@pytest.mark.parametrize(
    ("sys_oid", "sys_descr", "expected"),
    [
        (
            "1.3.6.1.4.1.9.1.1745",
            "Cisco device",
            {
                "vendor": "Cisco",
                "device_type": "cisco_ios",
                "platform": "ios",
                "os_family": "ios",
                "rule_id": "cisco:ios:oid",
            },
        ),
        (
            "1.3.6.1.4.1.9.1.2504",
            "Cisco device",
            {
                "vendor": "Cisco",
                "device_type": "cisco_ios_xe",
                "platform": "ios_xe",
                "os_family": "ios_xe",
                "rule_id": "cisco:ios_xe:oid",
            },
        ),
        (
            "1.3.6.1.4.1.9.1.1208",
            "Cisco Nexus Operating System (NX-OS) Software, Version 10.2(3), Nexus9000 C93180YC-FX",
            {
                "vendor": "Cisco",
                "device_type": "cisco_nxos",
                "platform": "nexus",
                "os_family": "nxos",
                "rule_id": "cisco:nxos",
            },
        ),
        (
            "1.3.6.1.4.1.9.1.1208",
            "Cisco Catalyst 9800-CL Wireless Controller, Cisco IOS XE Software, Version 17.9.3",
            {
                "vendor": "Cisco",
                "device_type": "cisco_wlc",
                "platform": "wireless_controller",
                "os_family": "ios_xe",
                "rule_id": "cisco:wlc",
            },
        ),
        (
            "1.3.6.1.4.1.2636.1.1.1.2.144",
            "Juniper device",
            {
                "vendor": "Juniper",
                "device_type": "juniper_junos",
                "platform": "switch",
                "os_family": "junos",
                "rule_id": "juniper:switch:oid",
            },
        ),
        (
            "1.3.6.1.4.1.674.10895.5000",
            "Dell EMC Networking OS10 Enterprise, Version 10.5.1.0",
            {
                "vendor": "Dell",
                "device_type": "dell_os10",
                "platform": "os10",
                "os_family": "os10",
                "rule_id": "dell:os10",
            },
        ),
        (
            "1.3.6.1.4.1.674.10895.5000",
            "Dell Force10 FTOS Version 9.14(2.4), PowerConnect S4810",
            {
                "vendor": "Dell",
                "device_type": "dell_force10",
                "platform": "force10",
                "os_family": "ftos",
                "rule_id": "dell:force10",
            },
        ),
        (
            "1.3.6.1.4.1.1916.2.325",
            "Extreme NetIron SLX-9540, IronWare Version 20.3.4",
            {
                "vendor": "Extreme",
                "device_type": "extreme_netiron",
                "platform": "netiron",
                "os_family": "netiron",
                "rule_id": "extreme:netiron",
            },
        ),
        (
            "1.3.6.1.4.1.2011.2.239.11",
            "Huawei device",
            {
                "vendor": "Huawei",
                "device_type": "huawei_vrp",
                "platform": "cloudengine",
                "os_family": "vrp",
                "rule_id": "huawei:cloudengine:oid",
            },
        ),
        (
            "1.3.6.1.4.1.25506.1.123",
            "H3C S6800-54QT Comware Software, Version 7.1.070",
            {
                "vendor": "H3C",
                "device_type": "hp_comware",
                "platform": "comware",
                "os_family": "comware",
                "rule_id": "h3c:comware:oid",
            },
        ),
        (
            "1.3.6.1.4.1.11.2.3.7.11.160",
            "Aruba 2930F-48G-4SFP+ Switch running AOS-Switch WC.16.11.0001",
            {
                "vendor": "HP",
                "device_type": "hp_procurve",
                "platform": "aos_switch",
                "os_family": "aos_switch",
                "rule_id": "hp:aos_switch:oid",
            },
        ),
        (
            "1.3.6.1.4.1.47196.4.1.25.1.1",
            "Switch device",
            {
                "vendor": "Aruba",
                "device_type": "aruba_os",
                "platform": "aos_cx",
                "os_family": "aos_cx",
                "rule_id": "aruba:aos_cx:oid",
            },
        ),
        (
            "1.3.6.1.4.1.12356.101.1.514",
            "FortiGate-1000D FortiOS v7.0.5",
            {
                "vendor": "Fortinet",
                "device_type": "fortinet",
                "platform": "fortigate",
                "os_family": "fortios",
                "rule_id": "fortinet:fortigate:oid",
            },
        ),
        (
            "1.3.6.1.4.1.25461.2.3.43",
            "Palo Alto Networks PA-3220 firewall PAN-OS 10.1.6-h6",
            {
                "vendor": "PaloAlto",
                "device_type": "paloalto_panos",
                "platform": "firewall",
                "os_family": "panos",
                "rule_id": "paloalto:panos:oid",
            },
        ),
        (
            "1.3.6.1.4.1.2620.1.6.123",
            "Check Point Gaia R81.10 6500 Appliance",
            {
                "vendor": "CheckPoint",
                "device_type": "checkpoint_gaia",
                "platform": "gaia",
                "os_family": "gaia",
                "rule_id": "checkpoint:gaia:oid",
            },
        ),
        (
            "1.3.6.1.4.1.3375.2.1.3.4.119",
            "F5 BIG-IP i5800 TMOS 15.1.8.2",
            {
                "vendor": "F5",
                "device_type": "f5_ltm",
                "platform": "bigip",
                "os_family": "tmos",
                "rule_id": "f5:tmos:oid",
            },
        ),
        (
            "1.3.6.1.4.1.7800.1",
            "Ubiquoss uNOS L3 Switch U5800 routing software",
            {
                "vendor": "Ubiquoss",
                "device_type": "ubiquoss_l3",
                "platform": "l3",
                "os_family": "unos",
                "rule_id": "ubiquoss:l3",
            },
        ),
        (
            "1.3.6.1.4.1.6527.3.1",
            "Nokia 7750 SR-1 running SR OS 24.3.R1",
            {
                "vendor": "Nokia",
                "device_type": "nokia_sros",
                "platform": "sr_os",
                "os_family": "sros",
                "rule_id": "nokia:sros",
            },
        ),
    ],
)
def test_fingerprint_device_identifies_platform_specific_drivers(sys_oid, sys_descr, expected):
    fingerprint = fingerprint_device(sys_oid=sys_oid, sys_descr=sys_descr, sys_name="lab-device")

    assert fingerprint["vendor"] == expected["vendor"]
    assert fingerprint["device_type"] == expected["device_type"]
    assert fingerprint["platform"] == expected["platform"]
    assert fingerprint["os_family"] == expected["os_family"]
    assert fingerprint["rule_id"] == expected["rule_id"]
    assert fingerprint["confidence"] >= 0.8


def test_get_driver_for_vendor_can_infer_driver_from_unknown_vendor_hints():
    driver = get_driver_for_vendor(
        "Unknown",
        sys_descr="Cisco Nexus Operating System (NX-OS) Software, Version 10.2(3), Nexus9000 C93180YC-FX",
        sys_oid="1.3.6.1.4.1.9.1.1208",
        sys_name="core-n9k-01",
    )
    assert driver == "cisco_nxos"


def test_fingerprint_device_preserves_model_hint_for_platform_rules():
    fingerprint = fingerprint_device(
        sys_oid="1.3.6.1.4.1.9.1.1208",
        sys_descr="Cisco Catalyst 9800-CL Wireless Controller, Cisco IOS XE Software, Version 17.9.3",
        sys_name="wlc-01",
    )

    assert fingerprint["device_type"] == "cisco_wlc"
    assert fingerprint["model_hint"] == "9800-CL"


@pytest.mark.parametrize(
    ("sys_oid", "sys_descr", "expected_model"),
    [
        ("1.3.6.1.4.1.12356.101.1.514", "FortiGate-1000D FortiOS v7.0.5", "FortiGate-1000D"),
        ("1.3.6.1.4.1.25461.2.3.43", "Palo Alto Networks PA-3220 firewall PAN-OS 10.1.6-h6", "PA-3220"),
        ("1.3.6.1.4.1.2620.1.6.123", "Check Point Gaia R81.10 6500 Appliance", "6500"),
        ("1.3.6.1.4.1.3375.2.1.3.4.119", "F5 BIG-IP i5800 TMOS 15.1.8.2", "BIG-IP i5800"),
        ("1.3.6.1.4.1.6486.801.1.1.2.1.11.1.2", "Alcatel-Lucent Enterprise OS6900-X48C6 8.7.468.R02", "OS6900-X48C6"),
        ("1.3.6.1.4.1.11.2.3.7.11.160", "Aruba 2930F-48G-4SFP+ Switch running AOS-Switch WC.16.11.0001", "2930F-48G-4SFP+"),
    ],
)
def test_fingerprint_device_extracts_model_hints_for_security_and_aos_platforms(sys_oid, sys_descr, expected_model):
    fingerprint = fingerprint_device(sys_oid=sys_oid, sys_descr=sys_descr, sys_name="lab-device")

    assert fingerprint["model_hint"] == expected_model
