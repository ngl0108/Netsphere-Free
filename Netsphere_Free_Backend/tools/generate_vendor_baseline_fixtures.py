from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "Netsphere_Free_Backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.vendor_parser_benchmark_service import (  # noqa: E402
    DEFAULT_VENDOR_FIXTURES_ROOT,
    get_supported_device_types,
    load_vendor_fixture_cases,
)


def _facts_output_for(dtype: str) -> tuple[str, str]:
    dt = str(dtype or "").lower()
    show_ver = (
        f"Synthetic {dt} software output\n"
        f"Version: 1.0-test\n"
        f"Model: {dt.upper()}-SIM\n"
    )
    display_ver = (
        f"Synthetic {dt} display output\n"
        f"VRP Version V1R0 Test\n"
        f"Model: {dt.upper()}-SIM\n"
    )
    if "huawei" in dt:
        return show_ver, display_ver
    return show_ver, display_ver


def _build_payload(dtype: str) -> dict[str, Any]:
    show_ver, display_ver = _facts_output_for(dtype)
    return {
        "id": f"facts.{dtype}.baseline_generic",
        "type": "facts",
        "device_type": dtype,
        "driver_mode": "generic",
        "commands": {
            "show version": show_ver,
            "display version": display_ver,
        },
        "expected": {
            "driver_contains": "GenericDriver",
            "facts_contains": {
                "vendor": {"equals": dtype},
                "hostname": {"equals": "fixture-host"},
                "raw_output": {"contains": "Synthetic"},
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate baseline facts fixtures for all supported device types.")
    parser.add_argument(
        "--fixtures-root",
        default=str(DEFAULT_VENDOR_FIXTURES_ROOT),
        help="Fixture root directory.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing baseline fixtures.",
    )
    args = parser.parse_args()

    fixtures_root = Path(args.fixtures_root).resolve()
    fixtures_root.mkdir(parents=True, exist_ok=True)

    try:
        existing_cases = load_vendor_fixture_cases(fixtures_root)
    except Exception:
        existing_cases = []
    covered = {str(c.device_type).lower() for c in existing_cases}
    target_types = get_supported_device_types()

    created = 0
    skipped = 0
    for dtype in target_types:
        out_dir = fixtures_root / "facts" / dtype
        out_path = out_dir / "baseline_generic.json"

        if not args.overwrite and dtype in covered:
            skipped += 1
            continue
        if out_path.exists() and not args.overwrite:
            skipped += 1
            continue

        out_dir.mkdir(parents=True, exist_ok=True)
        payload = _build_payload(dtype)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        created += 1
        print(f"created: {out_path}")

    print(f"baseline fixture generation done: created={created} skipped={skipped} total_target={len(target_types)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
