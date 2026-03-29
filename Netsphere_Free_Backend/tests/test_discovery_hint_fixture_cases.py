import json
from pathlib import Path

from app.services.discovery_hint_cache_service import DiscoveryHintCacheService
from app.services.discovery_hint_service import DiscoveryHintService
from app.services.oui_service import OUIService


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "discovery_hint_domestic_cases.json"


def _load_cases():
    with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_discovery_hint_fixture_cases_cover_domestic_fallback_paths():
    cases = _load_cases()
    assert len(cases) >= 5
    override_map = {str(case["oui_prefix"]).lower(): str(case["raw_vendor"]) for case in cases}

    DiscoveryHintCacheService.clear_for_tests()
    OUIService.set_override_map_for_tests(override_map)
    try:
        for case in cases:
            DiscoveryHintCacheService.record_seed_snapshot(
                seed_device_id=int(case["seed_device_id"]),
                seed_ip=case["seed_ip"],
                seed_vendor=case["seed_vendor"],
                arp_rows=[
                    {
                        "ip": case["target_ip"],
                        "mac": case["target_mac"],
                        "interface": f"Vlan{case['vlan']}",
                    }
                ],
                lldp_rows=[
                    {
                        "local_interface": case["local_interface"],
                        "neighbor_name": case["neighbor_name"],
                        "mgmt_ip": case["neighbor_mgmt_ip"],
                        "remote_interface": "Gi0/1",
                        "protocol": "lldp",
                    }
                ],
                fdb_rows=[
                    {
                        "mac": case["target_mac"],
                        "port": case["local_interface"],
                        "vlan": case["vlan"],
                    }
                ],
            )

            hint = DiscoveryHintService().build_ip_hint(case["target_ip"], open_ports=list(case["open_ports"]))
            assert hint is not None, case["name"]
            if case.get("expected_vendor"):
                assert hint["normalized_vendor"] == case["expected_vendor"], case["name"]
            assert hint["driver_candidates"][0]["driver"] == case["expected_top_driver"], case["name"]
            for expected_reason in case.get("expected_reasons") or []:
                assert expected_reason in hint["driver_candidates"][0]["reasons"], case["name"]
    finally:
        OUIService.set_override_map_for_tests(None)
        DiscoveryHintCacheService.clear_for_tests()
