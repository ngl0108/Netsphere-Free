from __future__ import annotations

from app.services.vendor_parser_benchmark_service import (
    DEFAULT_VENDOR_FIXTURES_ROOT,
    build_vendor_capability_matrix,
    load_vendor_fixture_cases,
    run_vendor_parser_benchmark,
)


def _row_by_device_type(rows: list[dict], device_type: str) -> dict:
    for row in rows:
        if str(row.get("device_type") or "").strip().lower() == device_type:
            return row
    return {}


def test_vendor_support_matrix_generation():
    cases = load_vendor_fixture_cases(DEFAULT_VENDOR_FIXTURES_ROOT)
    report = run_vendor_parser_benchmark(cases)
    matrix = build_vendor_capability_matrix(report)

    summary = matrix.get("summary") or {}
    assert int(summary.get("total_supported_device_types") or 0) >= 20
    assert float(summary.get("coverage_pct") or 0.0) == 100.0

    readiness = summary.get("readiness") or {}
    assert int(readiness.get("full") or 0) >= 4
    assert int(readiness.get("none") or 0) == 0

    rows = matrix.get("rows") or []
    dasan = _row_by_device_type(rows, "dasan_nos")
    assert dasan
    assert dasan.get("readiness") in {"extended", "full"}
    assert int(dasan.get("readiness_score") or 0) >= 60

    for device_type in ("soltech_switch", "coreedge_switch", "nst_switch"):
        row = _row_by_device_type(rows, device_type)
        assert row
        assert row.get("readiness") in {"extended", "full"}
        assert int(row.get("readiness_score") or 0) >= 60

    linux = _row_by_device_type(rows, "linux")
    assert linux
    assert linux.get("readiness") in {"basic", "extended", "full"}
