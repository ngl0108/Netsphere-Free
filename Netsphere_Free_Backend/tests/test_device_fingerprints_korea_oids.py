from app.core.device_fingerprints import identify_vendor_by_oid, get_driver_for_vendor


def test_identify_vendor_by_oid_korea_pen_variants():
    cases = [
        ("1.3.6.1.4.1.6728.1", "Dasan"),
        ("1.3.6.1.4.1.6296.1", "Dasan"),
        ("1.3.6.1.4.1.36243.1", "Dasan"),
        ("1.3.6.1.4.1.7331.1", "Ubiquoss"),
        ("1.3.6.1.4.1.7784.1", "Ubiquoss"),
        ("1.3.6.1.4.1.10226.1", "Ubiquoss"),
        ("1.3.6.1.4.1.7800.1", "Ubiquoss"),
        ("1.3.6.1.4.1.14781.1", "HanDreamnet"),
        ("1.3.6.1.4.1.25053.1", "HanDreamnet"),
        ("1.3.6.1.4.1.23237.1", "HanDreamnet"),
        ("1.3.6.1.4.1.8842.1", "Piolink"),
        ("1.3.6.1.4.1.11798.1", "Piolink"),
        ("1.3.6.1.4.1.17804.1", "Piolink"),
        ("1.3.6.1.4.1.33152.1", "AhnLab"),
        ("1.3.6.1.4.1.2608.1", "AhnLab"),
        ("1.3.6.1.4.1.26464.1", "AhnLab"),
        ("1.3.6.1.4.1.14922.1", "SECUI"),
        ("1.3.6.1.4.1.4867.1", "SECUI"),
        ("1.3.6.1.4.1.2603.1", "SECUI"),
        ("1.3.6.1.4.1.14441.1", "WINS"),
        ("1.3.6.1.4.1.3996.1", "WINS"),
        ("1.3.6.1.4.1.2439.1", "WINS"),
        ("1.3.6.1.4.1.20237.1", "MonitorApp"),
        ("1.3.6.1.4.1.26472.1", "MonitorApp"),
        ("1.3.6.1.4.1.17792.1", "EFMNetworks"),
        ("1.3.6.1.4.1.19865.1", "EFMNetworks"),
        ("1.3.6.1.4.1.236.1", "Samsung"),
    ]

    for oid, vendor in cases:
        got, conf = identify_vendor_by_oid(oid, "")
        assert got == vendor
        assert conf >= 0.9


def test_identify_vendor_by_sysdescr_fallback():
    got, conf = identify_vendor_by_oid("", "Samsung WLAN AP")
    assert got == "Samsung"
    assert conf > 0

    got, conf = identify_vendor_by_oid("", "ipTime A3004 Linux")
    assert got == "EFMNetworks"
    assert conf > 0


def test_driver_mapping_for_samsung():
    assert get_driver_for_vendor("Samsung") == "linux"


def test_driver_mapping_for_korea_security_vendors():
    assert get_driver_for_vendor("AhnLab") == "linux_ahnlab"
    assert get_driver_for_vendor("SECUI") == "linux_secui"
    assert get_driver_for_vendor("WINS") == "linux_wins"
    assert get_driver_for_vendor("AXGATE") == "linux_axgate"
    assert get_driver_for_vendor("NexG") == "linux_nexg"
    assert get_driver_for_vendor("MonitorApp") == "linux_monitorapp"
