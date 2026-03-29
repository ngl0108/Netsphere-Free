from __future__ import annotations

from app.services.vendor_parser_benchmark_service import (
    DEFAULT_VENDOR_FIXTURES_ROOT,
    load_vendor_fixture_cases,
    run_vendor_parser_benchmark,
)


def test_vendor_parser_domestic_switch_group_passes():
    cases = [c for c in load_vendor_fixture_cases(DEFAULT_VENDOR_FIXTURES_ROOT) if c.fixture_group == "domestic_switch"]
    assert len(cases) >= 10

    report = run_vendor_parser_benchmark(cases)
    summary = report.get("summary") or {}
    assert int(summary.get("failed") or 0) == 0
    assert int(summary.get("passed") or 0) == int(summary.get("total") or 0)

    by_type = summary.get("by_type") or {}
    assert int((by_type.get("inventory") or {}).get("total") or 0) >= 4
    assert int((by_type.get("neighbors") or {}).get("total") or 0) >= 4
    assert int((by_type.get("facts") or {}).get("total") or 0) >= 4
