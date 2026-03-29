from app.services.discovery_hint_cache_service import DiscoveryHintCacheService
from app.services.oui_service import OUIService


def test_scan_single_host_uses_hint_driven_ssh_fallback(monkeypatch):
    from app.services.discovery_service import DiscoveryService
    import app.services.ssh_service as ssh_mod

    DiscoveryHintCacheService.clear_for_tests()
    OUIService.set_override_map_for_tests({"00d0cb": "Dasan Networks"})

    class FakeConnection:
        def __init__(self, device_info):
            self.device_info = device_info

        def connect(self):
            return self.device_info.device_type == "dasan_nos"

        def disconnect(self):
            return None

        def get_facts(self):
            return {
                "hostname": "edge-dasan-01",
                "model": "V5824G",
                "os_version": "NOS 1.2.3",
            }

    monkeypatch.setattr(ssh_mod, "DeviceConnection", FakeConnection)

    try:
        DiscoveryHintCacheService.record_seed_snapshot(
            seed_device_id=1,
            seed_ip="10.0.0.1",
            seed_vendor="core-sw",
            arp_rows=[{"ip": "10.0.0.5", "mac": "00:d0:cb:11:22:33", "interface": "Vlan10"}],
            lldp_rows=[
                {
                    "local_interface": "Gi1/0/24",
                    "neighbor_name": "EDGE-SW",
                    "mgmt_ip": "10.0.0.5",
                    "remote_interface": "Gi0/1",
                    "protocol": "lldp",
                }
            ],
            fdb_rows=[{"mac": "00:d0:cb:11:22:33", "port": "Gi1/0/24", "vlan": "10"}],
        )

        svc = DiscoveryService(db=None)
        monkeypatch.setattr(svc.snmp_handler, "scan", lambda ip, profile: None)
        monkeypatch.setattr(
            svc.port_handler,
            "scan",
            lambda ip: {
                "ip_address": ip,
                "snmp_status": "unreachable",
                "hostname": ip,
                "vendor": "Unknown (SSH/Netconf Open)",
                "model": "",
                "os_version": "",
                "device_type": "manageable_device",
                "vendor_confidence": 0.15,
                "issues": [],
                "evidence": {"open_ports": [22]},
            },
        )

        result = svc._scan_single_host(
            "10.0.0.5",
            {
                "ssh_username": "admin",
                "ssh_password": "pw",
                "ssh_port": 22,
            },
        )

        assert result["vendor"] == "Dasan"
        assert result["device_type"] == "dasan_nos"
        assert result["hostname"] == "edge-dasan-01"
        assert result["evidence"]["ssh_probe"]["driver"] == "dasan_nos"
        assert result["evidence"]["hint_engine"]["normalized_vendor"] == "Dasan"
        assert result["evidence"]["hint_telemetry"]["event_type"] == "hint_success"
    finally:
        OUIService.set_override_map_for_tests(None)
        DiscoveryHintCacheService.clear_for_tests()
