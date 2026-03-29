from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
import sys

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from openapi_contract import build_openapi_snapshot, load_snapshot, save_snapshot


SNAPSHOT_PATH = Path(__file__).with_name("openapi.snapshot.json")


def _as_pretty_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def test_openapi_snapshot_contract():
    current = build_openapi_snapshot()

    if os.getenv("UPDATE_OPENAPI_SNAPSHOT", "").strip() == "1":
        save_snapshot(SNAPSHOT_PATH, current)

    assert SNAPSHOT_PATH.exists(), (
        f"OpenAPI snapshot not found: {SNAPSHOT_PATH}. "
        "Run `python scripts/update_openapi_snapshot.py` from Netsphere_Free_Backend."
    )

    expected = load_snapshot(SNAPSHOT_PATH)
    if expected != current:
        expected_text = _as_pretty_json(expected).splitlines()
        current_text = _as_pretty_json(current).splitlines()
        diff = "\n".join(
            difflib.unified_diff(
                expected_text,
                current_text,
                fromfile="openapi.snapshot.json",
                tofile="openapi.current.json",
                lineterm="",
                n=2,
            )
        )
        preview = "\n".join(diff.splitlines()[:120])
        raise AssertionError(
            "OpenAPI contract drift detected.\n"
            "If this change is intentional, regenerate snapshot with:\n"
            "  python scripts/update_openapi_snapshot.py\n\n"
            f"Diff preview:\n{preview}"
        )
