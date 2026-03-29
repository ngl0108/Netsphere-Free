from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.main import app


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, list):
        return [_normalize(v) for v in value]
    return value


def build_openapi_snapshot() -> dict[str, Any]:
    schema = dict(app.openapi() or {})
    # FastAPI may include dynamic server metadata depending on runtime context.
    schema.pop("servers", None)
    return _normalize(schema)


def load_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_snapshot(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
