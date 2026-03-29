from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "Netsphere_Free_Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.vendor_parser_benchmark_service import (  # noqa: E402
    DEFAULT_VENDOR_FIXTURES_ROOT,
    load_vendor_fixture_cases,
    run_vendor_parser_benchmark,
    write_vendor_benchmark_report,
)


DEFAULT_REPORT_PATH = REPO_ROOT / "docs" / "reports" / "vendor-parser-benchmark.latest.json"


def _print_summary(report: dict) -> None:
    summary = report.get("summary") or {}
    total = int(summary.get("total") or 0)
    passed = int(summary.get("passed") or 0)
    failed = int(summary.get("failed") or 0)
    rate = float(summary.get("pass_rate_pct") or 0.0)
    print(f"Vendor parser benchmark: total={total} passed={passed} failed={failed} pass_rate={rate:.2f}%")

    by_type = summary.get("by_type") or {}
    for case_type, row in sorted(by_type.items()):
        print(
            "  - "
            f"{case_type}: total={int(row.get('total') or 0)} "
            f"passed={int(row.get('passed') or 0)} "
            f"failed={int(row.get('failed') or 0)}"
        )
    by_group = summary.get("by_fixture_group") or {}
    for group_name, row in sorted(by_group.items()):
        print(
            "  - "
            f"group={group_name}: total={int(row.get('total') or 0)} "
            f"passed={int(row.get('passed') or 0)} "
            f"failed={int(row.get('failed') or 0)}"
        )
    coverage = summary.get("coverage") or {}
    target = coverage.get("target_device_types") or []
    covered = coverage.get("covered_device_types") or []
    missing = coverage.get("missing_device_types") or []
    cov_pct = float(coverage.get("coverage_pct") or 0.0)
    print(
        f"Coverage: target={len(target)} covered={len(covered)} "
        f"missing={len(missing)} coverage_pct={cov_pct:.2f}%"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay vendor fixture cases and output parser benchmark report.")
    parser.add_argument(
        "--fixtures-root",
        default=str(DEFAULT_VENDOR_FIXTURES_ROOT),
        help="Fixture root directory (default: test-data/vendor-fixtures).",
    )
    parser.add_argument(
        "--report-out",
        default=str(DEFAULT_REPORT_PATH),
        help="Path to write benchmark report JSON.",
    )
    parser.add_argument(
        "--allow-failures",
        action="store_true",
        help="Do not fail process when benchmark contains failed cases.",
    )
    parser.add_argument(
        "--allow-missing-vendors",
        action="store_true",
        help="Do not fail process when supported device types are missing from fixtures.",
    )
    parser.add_argument(
        "--print-failure-limit",
        type=int,
        default=15,
        help="Maximum number of failed cases to print in console.",
    )
    parser.add_argument(
        "--group",
        default="",
        help="Optional fixture_group filter (comma-separated). Example: domestic_switch",
    )
    args = parser.parse_args()

    fixtures_root = Path(args.fixtures_root).resolve()
    cases = load_vendor_fixture_cases(fixtures_root)
    group_filter = [x.strip().lower() for x in str(args.group or "").split(",") if x.strip()]
    if group_filter:
        cases = [c for c in cases if str(getattr(c, "fixture_group", "default")).lower() in group_filter]
        if not cases:
            print(f"No cases found for groups: {group_filter}")
            return 1
    report = run_vendor_parser_benchmark(cases)
    output = write_vendor_benchmark_report(report, Path(args.report_out))

    _print_summary(report)
    print(f"Report written: {output}")

    failed_results = [r for r in report.get("results") or [] if r.get("status") != "pass"]
    missing_types = list(((report.get("summary") or {}).get("coverage") or {}).get("missing_device_types") or [])
    if failed_results:
        print(f"Failed cases: {len(failed_results)}")
        for row in failed_results[: max(0, int(args.print_failure_limit))]:
            print(f"- {row.get('id')} ({row.get('type')}/{row.get('device_type')}): {row.get('reasons')}")
    if missing_types and not group_filter:
        print(f"Missing fixture coverage for device types: {len(missing_types)}")
        for dtype in missing_types[: max(0, int(args.print_failure_limit))]:
            print(f"- {dtype}")

    if failed_results and not args.allow_failures:
        return 1
    if missing_types and not args.allow_missing_vendors and not group_filter:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
