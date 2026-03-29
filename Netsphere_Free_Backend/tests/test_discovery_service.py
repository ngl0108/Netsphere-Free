import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.services.discovery_service import DiscoveryService
from app.core.device_fingerprints import identify_vendor_by_oid, extract_model_from_descr

def test_identify_vendor_by_oid_prefix():
    # New function returns (Vendor, Confidence)
    v, c = identify_vendor_by_oid("1.3.6.1.4.1.9.1.1208", "Cisco IOS Software")
    assert v == "Cisco"
    assert c > 0.9

    v, c = identify_vendor_by_oid("1.3.6.1.4.1.2636.1.1.1.2", "Juniper Networks, Inc. junos")
    assert v == "Juniper"
    assert c > 0.9

def test_identify_vendor_by_sysdescr_fallback():
    v, c = identify_vendor_by_oid("0.0", "ARISTA Networks EOS")
    assert v == "Arista"
    assert c >= 0.8

    v, c = identify_vendor_by_oid("0.0", "Fortinet FortiGate")
    assert v == "Fortinet"
    assert c >= 0.8

def test_extract_model_from_descr():
    assert extract_model_from_descr("Cisco", "Cisco IOS Software, C2960 Software (C2960-LANBASEK9-M), Version 12.2(55)SE5") == "C2960"
    assert extract_model_from_descr("Juniper", "Juniper Networks, Inc. mx480 Edge Router, kernel") == "mx480"

def test_extract_version_simple():
    # This method still exists in DiscoveryService for now
    svc = DiscoveryService(db=None)
    assert svc._extract_version("Cisco IOS Software, Version 15.2(2)E, RELEASE SOFTWARE") == "Version 15.2(2)E"
