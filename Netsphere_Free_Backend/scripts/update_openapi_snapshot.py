from __future__ import annotations

import json
import sys
from pathlib import Path

backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.main import app


def _normalize(value):
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def main() -> None:
    snapshot_path = backend_root / "tests" / "contracts" / "openapi.snapshot.json"
    snapshot = dict(app.openapi() or {})
    snapshot.pop("servers", None)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(_normalize(snapshot), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"OpenAPI snapshot updated: {snapshot_path}")


if __name__ == "__main__":
    main()
