from __future__ import annotations

from app.services.vendor_parser_benchmark_service import (
    DEFAULT_VENDOR_FIXTURES_ROOT,
    load_vendor_fixture_cases,
    run_vendor_parser_benchmark,
)


def test_vendor_parser_replay_variants_pass():
    cases = [
        c
        for c in load_vendor_fixture_cases(DEFAULT_VENDOR_FIXTURES_ROOT)
        if "variant" in str(c.case_id).lower()
    ]
    assert len(cases) >= 9

    report = run_vendor_parser_benchmark(cases)
    summary = report.get("summary") or {}
    assert int(summary.get("failed") or 0) == 0
    assert int(summary.get("passed") or 0) == int(summary.get("total") or 0)

