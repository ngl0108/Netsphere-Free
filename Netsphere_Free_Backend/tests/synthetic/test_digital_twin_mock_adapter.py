from __future__ import annotations

import pytest

from app.services.digital_twin_mock_adapter import (
    DigitalTwinMalformedPayloadError,
    DigitalTwinMockAdapter,
    DigitalTwinProtocolError,
    DigitalTwinTimeoutError,
)


@pytest.fixture(scope="module")
def adapter() -> DigitalTwinMockAdapter:
    return DigitalTwinMockAdapter()


def test_available_vendors(adapter: DigitalTwinMockAdapter):
    expected = {"cisco", "arista", "juniper", "fortinet", "paloalto", "f5", "nokia", "vyos", "mikrotik"}
    assert set(adapter.available_vendors("snmp")) >= expected
    assert set(adapter.available_vendors("ssh")) >= expected
    assert set(adapter.available_vendors("gnmi")) >= expected


@pytest.mark.parametrize("vendor", ["cisco", "fortinet", "nokia"])
def test_snmp_normal_case(adapter: DigitalTwinMockAdapter, vendor: str):
    sysinfo = adapter.get_snmp_system_info(vendor, case="normal")
    assert isinstance(sysinfo, dict)
    assert sysinfo.get("sysName")
    assert sysinfo.get("sysObjectID")
    oids = adapter.get_snmp_oids(vendor, case="normal")
    assert isinstance(oids, dict)


@pytest.mark.parametrize("vendor", ["arista", "paloalto", "mikrotik"])
def test_ssh_normal_case(adapter: DigitalTwinMockAdapter, vendor: str):
    inventory = adapter.get_ssh_inventory(vendor, case="normal")
    neighbors = adapter.get_ssh_neighbors(vendor, case="normal")
    assert isinstance(inventory, list)
    assert inventory
    assert isinstance(neighbors, list)


@pytest.mark.parametrize("vendor", ["juniper", "f5", "vyos"])
def test_gnmi_normal_case(adapter: DigitalTwinMockAdapter, vendor: str):
    telemetry = adapter.get_gnmi_telemetry(vendor, case="normal")
    assert isinstance(telemetry, dict)
    assert "cpu_pct" in telemetry or "interfaces_up" in telemetry


@pytest.mark.parametrize(
    "method_name,vendor",
    [
        ("get_snmp_system_info", "cisco"),
        ("get_ssh_inventory", "arista"),
        ("get_gnmi_telemetry", "juniper"),
    ],
)
def test_timeout_cases_raise(adapter: DigitalTwinMockAdapter, method_name: str, vendor: str):
    method = getattr(adapter, method_name)
    with pytest.raises(DigitalTwinTimeoutError):
        method(vendor, case="timeout")


@pytest.mark.parametrize(
    "method_name,vendor",
    [
        ("get_snmp_system_info", "cisco"),
        ("get_ssh_inventory", "arista"),
        ("get_gnmi_telemetry", "juniper"),
    ],
)
def test_malformed_cases_raise(adapter: DigitalTwinMockAdapter, method_name: str, vendor: str):
    method = getattr(adapter, method_name)
    with pytest.raises(DigitalTwinMalformedPayloadError):
        method(vendor, case="malformed")


def test_unknown_vendor_or_case_raises(adapter: DigitalTwinMockAdapter):
    with pytest.raises(DigitalTwinProtocolError):
        adapter.get_snmp_system_info("unknown-vendor", case="normal")
    with pytest.raises(DigitalTwinProtocolError):
        adapter.get_snmp_system_info("cisco", case="no-such-case")
