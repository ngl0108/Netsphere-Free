from __future__ import annotations

from app.services.vendor_parser_benchmark_service import (
    DEFAULT_VENDOR_FIXTURES_ROOT,
    load_vendor_fixture_cases,
    run_vendor_fixture_case,
)


def test_real_domestic_output_fact_fixtures_pass():
    wanted = {
        "facts.dasan_nos.show_running_config_v5424g_real",
        "facts.dasan_nos.show_run_6180f_real",
        "facts.ubiquoss_l2.show_running_e4020_24ps_real",
    }
    cases = [c for c in load_vendor_fixture_cases(DEFAULT_VENDOR_FIXTURES_ROOT) if c.case_id in wanted]
    assert {c.case_id for c in cases} == wanted

    for case in cases:
        result = run_vendor_fixture_case(case)
        assert result.get("status") == "pass", result
