from __future__ import annotations

from app.services.vendor_parser_benchmark_service import (
    DEFAULT_VENDOR_FIXTURES_ROOT,
    load_vendor_fixture_cases,
    run_vendor_fixture_case,
)


def test_real_global_output_fixture_subset_passes():
    wanted = {
        "facts.alcatel_aos.show_system_real_os6900",
        "facts.arista_eos.show_version_real_7050cx3",
        "facts.cisco_ios.show_version_real_c3850",
        "facts.cisco_ios_xe.show_version_real_c9500",
        "facts.cisco_wlc.show_sysinfo_real_5520",
        "facts.f5_ltm.show_sys_version_real_i5800",
        "facts.aruba_os.show_version_real_aos_cx",
        "facts.huawei_vrp.display_version_real_ce6850",
        "facts.juniper_junos.show_version_real_qfx5120",
        "facts.hp_comware.display_version_real",
        "inventory.alcatel_aos.show_chassis_real_os6900",
        "inventory.aruba_os.show_modules_aos_switch_real",
        "inventory.aruba_os.show_inventory_aos_cx_real",
        "inventory.cisco_ios_xe.chassis_whitespace_variant",
        "inventory.hp_comware.display_device_real",
        "inventory.cisco_nxos.show_inventory_real",
        "inventory.cisco_wlc.show_inventory_real_5520",
        "inventory.f5_ltm.show_sys_hardware_real_i5800",
        "neighbors.alcatel_aos.lldp_remote_system_real",
        "neighbors.aruba_os.lldp_detail_aos_switch_real",
        "neighbors.aruba_os.lldp_detail_aos_cx_real",
        "neighbors.cisco_wlc.neighbor_summary_real_5520",
        "neighbors.hp_comware.lldp_verbose_real",
        "neighbors.cisco_nxos.lldp_detail_real",
        "neighbors.f5_ltm.lldp_neighbors_real_i5800",
    }
    cases = [c for c in load_vendor_fixture_cases(DEFAULT_VENDOR_FIXTURES_ROOT) if c.case_id in wanted]
    assert {c.case_id for c in cases} == wanted

    for case in cases:
        result = run_vendor_fixture_case(case)
        assert result.get("status") == "pass", result
