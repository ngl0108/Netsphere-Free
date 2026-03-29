from __future__ import annotations

import re
from pathlib import Path
import sys

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from openapi_contract import build_openapi_snapshot


API_CALL_RE = re.compile(
    r"api\.(get|post|put|patch|delete)\(\s*(`[^`]*`|'[^']*'|\"[^\"]*\")",
    re.S,
)


def _normalize_param_path(path: str) -> str:
    out = str(path or "").strip()
    out = re.sub(r"\$\{[^}]+\}", "{param}", out)
    out = re.sub(r"\{[^}/]+\}", "{param}", out)
    out = out.split("?", 1)[0].strip()
    if out != "/" and out.endswith("/"):
        out = out[:-1]
    return out


def _extract_frontend_api_contracts(services_path: Path) -> set[tuple[str, str]]:
    text = services_path.read_text(encoding="utf-8", errors="ignore")
    contracts: set[tuple[str, str]] = set()
    for match in API_CALL_RE.finditer(text):
        method = str(match.group(1) or "").strip().lower()
        literal = str(match.group(2) or "")
        if len(literal) < 2:
            continue
        path = _normalize_param_path(literal[1:-1])
        if not path.startswith("/"):
            continue
        if not path.startswith("/api/v1"):
            path = f"/api/v1{path}"
        contracts.add((method, path))
    return contracts


def _build_openapi_method_set(schema: dict) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    paths = schema.get("paths") or {}
    for raw_path, ops in paths.items():
        normalized_path = _normalize_param_path(str(raw_path))
        if not isinstance(ops, dict):
            continue
        for method in ops.keys():
            m = str(method or "").strip().lower()
            if m in {"get", "post", "put", "patch", "delete"}:
                out.add((m, normalized_path))
    return out


def test_frontend_services_match_backend_openapi_contract():
    schema = build_openapi_snapshot()
    repo_root = Path(__file__).resolve().parents[3]
    services_path = repo_root / "Netsphere_Free_Frontend" / "src" / "api" / "services.js"
    assert services_path.exists(), f"Frontend services file not found: {services_path}"

    frontend_contracts = _extract_frontend_api_contracts(services_path)
    openapi_contracts = _build_openapi_method_set(schema)

    missing = sorted(frontend_contracts - openapi_contracts)
    assert not missing, (
        "Frontend API contract mismatch: endpoints used in services.js are not present in backend OpenAPI.\n"
        + "\n".join(f"- {method.upper()} {path}" for method, path in missing[:80])
    )
