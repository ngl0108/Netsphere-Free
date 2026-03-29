from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "Netsphere_Free_Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.vendor_parser_benchmark_service import (  # noqa: E402
    DEFAULT_VENDOR_FIXTURES_ROOT,
    build_vendor_capability_matrix,
    load_vendor_fixture_cases,
    render_vendor_capability_matrix_markdown,
    run_vendor_parser_benchmark,
    write_vendor_capability_matrix_report,
)


DEFAULT_JSON_OUT = REPO_ROOT / "docs" / "reports" / "vendor-support-matrix.latest.json"
DEFAULT_MD_OUT = REPO_ROOT / "docs" / "reports" / "vendor-support-matrix.latest.md"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate vendor support matrix (fixture-based) as JSON and Markdown."
    )
    parser.add_argument(
        "--fixtures-root",
        default=str(DEFAULT_VENDOR_FIXTURES_ROOT),
        help="Fixture root directory (default: test-data/vendor-fixtures).",
    )
    parser.add_argument(
        "--group",
        default="",
        help="Optional fixture_group filter (comma-separated). Example: domestic_switch,global_switch",
    )
    parser.add_argument(
        "--json-out",
        default=str(DEFAULT_JSON_OUT),
        help="Output JSON file path.",
    )
    parser.add_argument(
        "--md-out",
        default=str(DEFAULT_MD_OUT),
        help="Output Markdown file path.",
    )
    args = parser.parse_args()

    fixtures_root = Path(args.fixtures_root).resolve()
    cases = load_vendor_fixture_cases(fixtures_root)
    if args.group.strip():
        group_filter = {x.strip().lower() for x in args.group.split(",") if x.strip()}
        cases = [c for c in cases if str(getattr(c, "fixture_group", "default")).lower() in group_filter]

    report = run_vendor_parser_benchmark(cases)
    matrix = build_vendor_capability_matrix(report)

    json_output = write_vendor_capability_matrix_report(matrix, Path(args.json_out))
    md_output = Path(args.md_out).resolve()
    md_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.write_text(render_vendor_capability_matrix_markdown(matrix), encoding="utf-8")

    summary = matrix.get("summary") if isinstance(matrix.get("summary"), dict) else {}
    readiness = summary.get("readiness") if isinstance(summary.get("readiness"), dict) else {}

    print(
        "Vendor support matrix generated: "
        f"covered={summary.get('covered_device_types', 0)}/{summary.get('total_supported_device_types', 0)} "
        f"coverage={summary.get('coverage_pct', 0)}%"
    )
    print(
        "Readiness distribution: "
        f"full={readiness.get('full', 0)} "
        f"extended={readiness.get('extended', 0)} "
        f"basic={readiness.get('basic', 0)} "
        f"partial={readiness.get('partial', 0)} "
        f"none={readiness.get('none', 0)}"
    )
    print(f"JSON report: {json_output}")
    print(f"Markdown report: {md_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
