from app.services.discovery_hint_cache_service import DiscoveryHintCacheService
from app.services.discovery_hint_service import DiscoveryHintService
from app.services.discovery_hint_rule_service import DiscoveryHintRuleService
from app.services.oui_service import OUIService


def test_discovery_hint_cache_records_arp_fdb_lldp_context():
    DiscoveryHintCacheService.clear_for_tests()
    try:
        recorded = DiscoveryHintCacheService.record_seed_snapshot(
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
            fdb_rows=[{"mac": "00:d0:cb:11:22:33", "port": "Gi1/0/24", "vlan": "10", "discovery_source": "snmp_qbridge"}],
        )
        assert recorded >= 1
        cached = DiscoveryHintCacheService.lookup_ip("10.0.0.5")
        assert cached is not None
        assert cached["mac"] == "00d0.cb11.2233"
        assert cached["local_interface"] == "Gi1/0/24"
        assert cached["neighbor_name"] == "EDGE-SW"
    finally:
        DiscoveryHintCacheService.clear_for_tests()


def test_discovery_hint_service_scores_oui_and_neighbor_context():
    DiscoveryHintCacheService.clear_for_tests()
    OUIService.set_override_map_for_tests({"00d0cb": "Dasan Networks"})
    try:
        DiscoveryHintCacheService.record_seed_snapshot(
            seed_device_id=7,
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
        hint = DiscoveryHintService().build_ip_hint("10.0.0.5", open_ports=[22])
        assert hint is not None
        assert hint["normalized_vendor"] == "Dasan"
        assert hint["driver_candidates"][0]["driver"] == "dasan_nos"
        assert hint["driver_candidates"][0]["score"] >= 0.8
        assert "oui_match" in hint["driver_candidates"][0]["reasons"]
    finally:
        OUIService.set_override_map_for_tests(None)
        DiscoveryHintCacheService.clear_for_tests()


def test_discovery_hint_service_applies_central_rule_overrides():
    DiscoveryHintCacheService.clear_for_tests()
    OUIService.set_override_map_for_tests({"aabbcc": "Intel Corporate"})
    DiscoveryHintRuleService.set_override_rules_for_tests(
        [
            {
                "rule_id": "intel-handream",
                "vendor_family": "HanDreamnet",
                "match_conditions": {
                    "raw_vendor_contains": ["intel"],
                    "ssh_open": True,
                    "neighbor_name_regex": "SG|EDGE",
                },
                "driver_overrides": ["handream_sg"],
                "score_bonus": 0.22,
            }
        ]
    )
    try:
        DiscoveryHintCacheService.record_seed_snapshot(
            seed_device_id=11,
            seed_ip="10.0.0.1",
            seed_vendor="core-sw",
            arp_rows=[{"ip": "10.0.2.9", "mac": "aa:bb:cc:11:22:33", "interface": "Vlan30"}],
            lldp_rows=[
                {
                    "local_interface": "Gi1/0/11",
                    "neighbor_name": "SG2400-EDGE",
                    "mgmt_ip": "10.0.2.9",
                    "remote_interface": "Gi0/24",
                    "protocol": "lldp",
                }
            ],
            fdb_rows=[{"mac": "aa:bb:cc:11:22:33", "port": "Gi1/0/11", "vlan": "30"}],
        )
        hint = DiscoveryHintService().build_ip_hint("10.0.2.9", open_ports=[22])
        assert hint is not None
        assert hint["driver_candidates"][0]["driver"] == "handream_sg"
        assert "central_rule_override" in hint["driver_candidates"][0]["reasons"]
    finally:
        DiscoveryHintRuleService.set_override_rules_for_tests(None)
        OUIService.set_override_map_for_tests(None)
        DiscoveryHintCacheService.clear_for_tests()


def test_discovery_hint_service_adds_chipset_override_candidates():
    DiscoveryHintCacheService.clear_for_tests()
    OUIService.set_override_map_for_tests({"aabbcc": "Intel Corporate"})
    try:
        DiscoveryHintCacheService.record_seed_snapshot(
            seed_device_id=9,
            seed_ip="10.0.0.1",
            seed_vendor="core-sw",
            arp_rows=[{"ip": "10.0.1.9", "mac": "aa:bb:cc:11:22:33", "interface": "Vlan20"}],
            fdb_rows=[{"mac": "aa:bb:cc:11:22:33", "port": "Gi1/0/10", "vlan": "20"}],
        )
        hint = DiscoveryHintService().build_ip_hint("10.0.1.9", open_ports=[22])
        assert hint is not None
        drivers = [row["driver"] for row in hint["driver_candidates"]]
        assert "handream_sg" in drivers
        assert "cisco_ios" in drivers
    finally:
        OUIService.set_override_map_for_tests(None)
        DiscoveryHintCacheService.clear_for_tests()


def test_discovery_hint_service_prefers_nst_for_broadcom_with_neighbor_pattern():
    DiscoveryHintCacheService.clear_for_tests()
    OUIService.set_override_map_for_tests({"ddeeff": "Broadcom Corporation"})
    try:
        DiscoveryHintCacheService.record_seed_snapshot(
            seed_device_id=21,
            seed_ip="10.0.10.1",
            seed_vendor="domestic-l3-core",
            arp_rows=[{"ip": "10.0.10.9", "mac": "dd:ee:ff:11:22:33", "interface": "Vlan110"}],
            lldp_rows=[
                {
                    "local_interface": "Gi1/0/8",
                    "neighbor_name": "NST2400-ACCESS",
                    "mgmt_ip": "10.0.10.9",
                    "remote_interface": "Gi0/48",
                    "protocol": "lldp",
                }
            ],
            fdb_rows=[{"mac": "dd:ee:ff:11:22:33", "port": "Gi1/0/8", "vlan": "110"}],
        )
        hint = DiscoveryHintService().build_ip_hint("10.0.10.9", open_ports=[22])
        assert hint is not None
        assert hint["driver_candidates"][0]["driver"] == "nst_switch"
        assert "neighbor_pattern" in hint["driver_candidates"][0]["reasons"]
        assert "chipset_driver_fit" in hint["driver_candidates"][0]["reasons"]
    finally:
        OUIService.set_override_map_for_tests(None)
        DiscoveryHintCacheService.clear_for_tests()


def test_discovery_hint_service_prefers_domestic_cisco_like_for_woorinet():
    DiscoveryHintCacheService.clear_for_tests()
    OUIService.set_override_map_for_tests({"112233": "Woori-Net"})
    try:
        DiscoveryHintCacheService.record_seed_snapshot(
            seed_device_id=22,
            seed_ip="10.0.20.1",
            seed_vendor="core-sw",
            arp_rows=[{"ip": "10.0.20.9", "mac": "11:22:33:44:55:66", "interface": "Vlan120"}],
            lldp_rows=[
                {
                    "local_interface": "Gi1/0/9",
                    "neighbor_name": "SW2400-EDGE",
                    "mgmt_ip": "10.0.20.9",
                    "remote_interface": "Gi0/12",
                    "protocol": "lldp",
                }
            ],
            fdb_rows=[{"mac": "11:22:33:44:55:66", "port": "Gi1/0/9", "vlan": "120"}],
        )
        hint = DiscoveryHintService().build_ip_hint("10.0.20.9", open_ports=[22])
        assert hint is not None
        assert hint["normalized_vendor"] == "WooriNet"
        assert hint["driver_candidates"][0]["driver"] == "domestic_cisco_like"
        assert "neighbor_pattern" in hint["driver_candidates"][0]["reasons"]
    finally:
        OUIService.set_override_map_for_tests(None)
        DiscoveryHintCacheService.clear_for_tests()


def test_discovery_hint_service_prefers_linux_for_efmnetworks_chipset_neighbor():
    DiscoveryHintCacheService.clear_for_tests()
    OUIService.set_override_map_for_tests({"a1b2c3": "Ralink Technology"})
    try:
        DiscoveryHintCacheService.record_seed_snapshot(
            seed_device_id=23,
            seed_ip="10.0.30.1",
            seed_vendor="domestic-l3-core",
            arp_rows=[{"ip": "10.0.30.9", "mac": "a1:b2:c3:44:55:66", "interface": "Vlan130"}],
            lldp_rows=[
                {
                    "local_interface": "Gi1/0/10",
                    "neighbor_name": "ipTIME-AX3000",
                    "mgmt_ip": "10.0.30.9",
                    "remote_interface": "Gi0/1",
                    "protocol": "lldp",
                }
            ],
            fdb_rows=[{"mac": "a1:b2:c3:44:55:66", "port": "Gi1/0/10", "vlan": "130"}],
        )
        hint = DiscoveryHintService().build_ip_hint("10.0.30.9", open_ports=[22])
        assert hint is not None
        assert hint["driver_candidates"][0]["driver"] == "linux"
        assert "neighbor_pattern" in hint["driver_candidates"][0]["reasons"]
        assert "chipset_driver_fit" in hint["driver_candidates"][0]["reasons"]
    finally:
        OUIService.set_override_map_for_tests(None)
        DiscoveryHintCacheService.clear_for_tests()
