from __future__ import annotations

from app.services.vendor_parser_benchmark_service import (
    DEFAULT_VENDOR_FIXTURES_ROOT,
    load_vendor_fixture_cases,
    run_vendor_parser_benchmark,
)


def test_vendor_parser_benchmark_replay_passes():
    cases = load_vendor_fixture_cases(DEFAULT_VENDOR_FIXTURES_ROOT)
    assert len(cases) >= 8

    report = run_vendor_parser_benchmark(cases)
    summary = report.get("summary") or {}
    assert int(summary.get("failed") or 0) == 0
    assert int(summary.get("passed") or 0) == int(summary.get("total") or 0)

    by_type = summary.get("by_type") or {}
    assert int((by_type.get("inventory") or {}).get("total") or 0) >= 4
    assert int((by_type.get("neighbors") or {}).get("total") or 0) >= 4
    assert int((by_type.get("facts") or {}).get("total") or 0) >= 2

    coverage = summary.get("coverage") or {}
    assert float(coverage.get("coverage_pct") or 0.0) == 100.0
    assert not list(coverage.get("missing_device_types") or [])
