import pytest


def test_scan_single_host_tries_credential_pool(monkeypatch):
    from app.services import discovery_service as mod
    from app.services.discovery_service import DiscoveryService

    class FakeSnmp:
        def __init__(self, ip, community, port=161, version="v2c", **kwargs):
            self.community = community
        def get_system_info(self):
            if self.community == "good":
                return {
                    "sysName": "sw1",
                    "sysDescr": "Cisco IOS Software",
                    "sysObjectID": "1.3.6.1.4.1.9.1.1208",
                }
            return None
        def get_oids(self, oids):
            return {}

    monkeypatch.setattr(mod, "SnmpManager", FakeSnmp)

    svc = DiscoveryService(db=None)
    res = svc._scan_single_host(
        "10.0.0.10",
        {"community": "bad", "credential_pool": [{"profile_id": 2, "community": "good", "version": "v2c", "port": 161}]},
    )
    assert res["snmp_status"] == "reachable"
    assert res["evidence"].get("snmp_profile_id") == 2

