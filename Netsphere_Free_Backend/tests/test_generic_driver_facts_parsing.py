from app.drivers.generic_driver import GenericDriver


class FakeConn:
    def __init__(self, mapping):
        self.mapping = mapping

    def send_command(self, cmd, **kwargs):
        value = self.mapping.get(cmd, "")
        if isinstance(value, Exception):
            raise value
        return value


def test_generic_driver_parses_aos_switch_facts_from_multiple_commands():
    d = GenericDriver("fixture-host", "u", "p", device_type="hp_procurve")
    d.connection = FakeConn(
        {
            "show version": "WC.16.11.0001\n",
            "show system": "System Name        : Access-2930F\nSystem Up Time     : 45 days 10 hours 15 mins 20 secs\n",
            "show modules": "Chassis: JL254A Aruba 2930F-48G-4SFP+ Switch\n\n  1      Aruba 2930F-48G-4SFP+ Switch           SG76AABCD1       Up\n",
        }
    )

    facts = d.get_facts()

    assert facts["vendor"] == "hp_procurve"
    assert facts["hostname"] == "Access-2930F"
    assert facts["model"] == "JL254A Aruba 2930F-48G-4SFP+ Switch"
    assert facts["serial_number"] == "SG76AABCD1"
    assert facts["os_version"] == "WC.16.11.0001"
    assert facts["uptime"] == "45 days 10 hours 15 mins 20 secs"


def test_generic_driver_parses_h3c_comware_facts():
    d = GenericDriver("fixture-host", "u", "p", device_type="hp_comware")
    d.connection = FakeConn(
        {
            "display version": (
                "H3C Comware Software, Version 7.1.070, Release 6616P51\n"
                "H3C S6800-54QT uptime is 25 weeks, 4 days, 10 hours, 15 minutes\n"
                "BOARD TYPE:         S6800-54QT\n"
            ),
            "display device": "Slot Type             State    Subslot  Operate   Power  Description\n1    S6800-54QT       Master   0        Normal    On     S6800-54QT\n",
        }
    )

    facts = d.get_facts()

    assert facts["vendor"] == "hp_comware"
    assert facts["model"] == "S6800-54QT"
    assert facts["os_version"] == "Version 7.1.070, Release 6616P51"
    assert facts["uptime"] == "25 weeks, 4 days, 10 hours, 15 minutes"


def test_generic_driver_parses_cisco_ios_facts_from_show_version():
    d = GenericDriver("fixture-host", "u", "p", device_type="cisco_ios")
    d.connection = FakeConn(
        {
            "show version": (
                "Cisco IOS Software, C3850 Software (CAT3K_CAA-UNIVERSALK9-M), Version 15.2(4)E7, RELEASE SOFTWARE (fc2)\n"
                "Switch uptime is 2 years, 45 weeks, 3 days, 12 hours, 14 minutes\n"
                "cisco WS-C3850-24T (MIPS) processor with 4194304K/6147K bytes of memory.\n"
                "Processor board ID FOC1935U0AA\n"
                "Model Number                       : WS-C3850-24T\n"
                "System Serial Number               : FOC1935U0AA\n"
            ),
            "show inventory": (
                "NAME: \"Switch 1\", DESCR: \"Cisco Catalyst 3850-24T-L\"\n"
                "PID: WS-C3850-24T-L    , VID: V06  , SN: FOC1935U0AA\n"
            ),
        }
    )

    facts = d.get_facts()

    assert facts["model"] == "WS-C3850-24T"
    assert facts["serial_number"] == "FOC1935U0AA"
    assert facts["os_version"] == "15.2(4)E7"
    assert "2 years, 45 weeks" in facts["uptime"]


def test_generic_driver_parses_cisco_ios_xe_facts_from_show_version():
    d = GenericDriver("fixture-host", "u", "p", device_type="cisco_ios_xe")
    d.connection = FakeConn(
        {
            "show version": (
                "Cisco IOS XE Software, Version 17.06.04\n"
                "Core-9K uptime is 38 weeks, 5 days, 4 hours, 21 minutes\n"
                "cisco C9500-24Y4C (X86) processor with 2942186K/6147K bytes of memory.\n"
                "Processor board ID FDO2411XXXX\n"
                "Model Number                       : C9500-24Y4C\n"
                "System Serial Number               : FDO2411XXXX\n"
            )
        }
    )

    facts = d.get_facts()

    assert facts["model"] == "C9500-24Y4C"
    assert facts["serial_number"] == "FDO2411XXXX"
    assert facts["os_version"] == "17.06.04"
    assert "38 weeks, 5 days" in facts["uptime"]


def test_generic_driver_parses_juniper_junos_facts_from_version_and_uptime():
    d = GenericDriver("fixture-host", "u", "p", device_type="juniper_junos")
    d.connection = FakeConn(
        {
            "show version": (
                "Hostname: QFX5120-VC\n"
                "Model: qfx5120-48y-8c\n"
                "Junos: 20.4R3-S2.3\n"
            ),
            "show system uptime": (
                "System booted: 2025-10-15 02:10:15 KST (20w3d 16:14 ago)\n"
                " 6:25PM  up 143 days, 16:14, 1 user, load averages: 0.15, 0.12, 0.10\n"
            ),
            "show chassis hardware": "Chassis                                VD37XXXXXXXX      Virtual Chassis\n",
        }
    )

    facts = d.get_facts()

    assert facts["hostname"] == "QFX5120-VC"
    assert facts["model"] == "qfx5120-48y-8c"
    assert facts["serial_number"] == "VD37XXXXXXXX"
    assert facts["os_version"] == "20.4R3-S2.3"
    assert facts["uptime"] == "20w3d 16:14"


def test_generic_driver_parses_huawei_vrp_facts():
    d = GenericDriver("fixture-host", "u", "p", device_type="huawei_vrp")
    d.connection = FakeConn(
        {
            "display version": (
                "Huawei Versatile Routing Platform Software\n"
                "VRP (R) software, Version 8.150 (CE6850EI V200R005C10SPC800)\n"
                "HUAWEI CE6850-48S6Q-HI uptime is 120 days, 14 hours, 32 minutes\n"
            )
        }
    )

    facts = d.get_facts()

    assert facts["model"] == "CE6850-48S6Q-HI"
    assert facts["os_version"] == "8.150 (CE6850EI V200R005C10SPC800)"
    assert facts["uptime"] == "120 days, 14 hours, 32 minutes"


def test_generic_driver_parses_arista_eos_facts():
    d = GenericDriver("fixture-host", "u", "p", device_type="arista_eos")
    d.connection = FakeConn(
        {
            "show version": (
                "Arista DCS-7050CX3-32S-R\n"
                "Serial number: JPE2045XXXX\n"
                "Software image version: 4.27.4M\n"
                "Uptime: 45 weeks, 2 days, 10 hours and 15 minutes\n"
            )
        }
    )

    facts = d.get_facts()

    assert facts["model"] == "DCS-7050CX3-32S-R"
    assert facts["serial_number"] == "JPE2045XXXX"
    assert facts["os_version"] == "4.27.4M"
    assert facts["uptime"] == "45 weeks, 2 days, 10 hours and 15 minutes"


def test_generic_driver_parses_cisco_wlc_facts_from_sysinfo():
    d = GenericDriver("fixture-host", "u", "p", device_type="cisco_wlc")
    d.connection = FakeConn(
        {
            "show sysinfo": (
                "Product Name..................................... Cisco Controller\n"
                "Product Version.................................. 8.10.183.0\n"
                "System Name...................................... WLC-5520-Pri\n"
                "System Up Time................................... 120 days 14 hrs 30 mins 12 secs\n"
            ),
            "show inventory": 'NAME: "Chassis"    , DESCR: "Cisco 5520 Wireless LAN Controller"\nPID: AIR-CT5520-K9,  VID: V02,  SN: FDO2115XXXX\n',
        }
    )

    facts = d.get_facts()

    assert facts["hostname"] == "WLC-5520-Pri"
    assert facts["model"] == "Cisco Controller"
    assert facts["serial_number"] == "FDO2115XXXX"
    assert facts["os_version"] == "8.10.183.0"
    assert facts["uptime"] == "120 days 14 hrs 30 mins 12 secs"


def test_generic_driver_parses_alcatel_facts_from_system_and_chassis():
    d = GenericDriver("fixture-host", "u", "p", device_type="alcatel_aos")
    d.connection = FakeConn(
        {
            "show system": (
                "System:\n"
                "  Description:  Alcatel-Lucent Enterprise OS6900-X48C6 8.7.468.R02\n"
                "  Up Time:      45 days 10 hours 15 minutes 20 seconds\n"
                "  Name:         OS6900-Core\n"
            ),
            "show chassis": (
                "Chassis 1\n"
                "  Model Name:             OS6900-X48C6,\n"
                "  Serial Number:          P248XXXX,\n"
            ),
            "show microcode": "Tos                          8.7.468.R02  3452342  Alcatel-Lucent OS\n",
        }
    )

    facts = d.get_facts()

    assert facts["hostname"] == "OS6900-Core"
    assert facts["model"] == "OS6900-X48C6"
    assert facts["serial_number"] == "P248XXXX"
    assert facts["os_version"] == "8.7.468.R02"
    assert facts["uptime"] == "45 days 10 hours 15 minutes 20 seconds"


def test_generic_driver_parses_f5_facts_from_sys_version_and_hardware():
    d = GenericDriver("fixture-host", "u", "p", device_type="f5_ltm")
    d.connection = FakeConn(
        {
            "show sys version": (
                "Sys::Version\n"
                "Main Package\n"
                "  Product     BIG-IP\n"
                "  Version     15.1.8.2\n"
            ),
            "show sys hardware": (
                "Sys::Hardware\n"
                "Chassis Information\n"
                "  Chassis Serial     ZPE2345XXXX\n"
                "  Hardware Version   Name: BIG-IP i5800\n"
            ),
        }
    )

    facts = d.get_facts()

    assert facts["model"] == "BIG-IP i5800"
    assert facts["serial_number"] == "ZPE2345XXXX"
    assert facts["os_version"] == "15.1.8.2"
