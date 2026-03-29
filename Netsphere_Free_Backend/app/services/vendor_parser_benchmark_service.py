from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.drivers.manager import DriverManager
from app.drivers.generic_driver import GenericDriver
from app.services.inventory_parsers import get_inventory_parsers


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VENDOR_FIXTURES_ROOT = REPO_ROOT / "test-data" / "vendor-fixtures"

_SUPPORTED_CASE_TYPES = {"inventory", "neighbors", "facts"}
_SUPPORTED_DRIVER_MODES = {"manager", "generic"}


@dataclass(frozen=True)
class VendorFixtureCase:
    case_id: str
    case_type: str
    device_type: str
    commands: dict[str, Any]
    expected: dict[str, Any]
    path: Path
    driver_mode: str = "manager"
    fixture_group: str = "default"


class FixtureConnection:
    def __init__(self, mapping: dict[str, Any]):
        self.mapping = mapping

    def send_command(self, cmd: str, **kwargs: Any) -> Any:
        key = f"{cmd}|textfsm" if kwargs.get("use_textfsm") else cmd
        if key in self.mapping:
            value = self.mapping[key]
        elif cmd in self.mapping:
            value = self.mapping[cmd]
        else:
            value = ""

        if isinstance(value, dict) and "__raise__" in value:
            raise RuntimeError(str(value["__raise__"]))
        return value


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _normalize_case_id(path: Path, payload: dict[str, Any]) -> str:
    from_payload = str(payload.get("id") or "").strip()
    if from_payload:
        return from_payload
    rel = _relative(path)
    return rel.replace("/", ".").replace(".json", "")


def _as_dict(value: Any, *, fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return dict(fallback or {})


def _validate_fixture_payload(path: Path, payload: dict[str, Any]) -> VendorFixtureCase:
    case_id = _normalize_case_id(path, payload)
    case_type = str(payload.get("type") or "").strip().lower()
    device_type = str(payload.get("device_type") or "").strip()
    driver_mode = str(payload.get("driver_mode") or "manager").strip().lower()
    fixture_group = str(payload.get("fixture_group") or "default").strip().lower()
    commands = _as_dict(payload.get("commands"))
    expected = _as_dict(payload.get("expected"))

    if case_type not in _SUPPORTED_CASE_TYPES:
        raise ValueError(f"Unsupported case type '{case_type}' in {path}")
    if not device_type:
        raise ValueError(f"Missing device_type in {path}")
    if driver_mode not in _SUPPORTED_DRIVER_MODES:
        raise ValueError(f"Unsupported driver_mode '{driver_mode}' in {path}")

    return VendorFixtureCase(
        case_id=case_id,
        case_type=case_type,
        device_type=device_type,
        commands=commands,
        expected=expected,
        path=path,
        driver_mode=driver_mode,
        fixture_group=fixture_group,
    )


def load_vendor_fixture_cases(root: Path | None = None) -> list[VendorFixtureCase]:
    fixture_root = (root or DEFAULT_VENDOR_FIXTURES_ROOT).resolve()
    if not fixture_root.exists():
        raise FileNotFoundError(f"Vendor fixture root does not exist: {fixture_root}")

    cases: list[VendorFixtureCase] = []
    for path in sorted(fixture_root.rglob("*.json")):
        if path.name.lower() == "manifest.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Fixture payload must be an object: {path}")
        cases.append(_validate_fixture_payload(path, payload))

    if not cases:
        raise ValueError(f"No fixture cases found under: {fixture_root}")
    return cases


def _match_value(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if "equals" in expected:
            return str(actual) == str(expected["equals"])
        if "contains" in expected:
            needle = str(expected["contains"]).lower()
            return needle in str(actual).lower()
        if "regex" in expected:
            pattern = str(expected["regex"])
            return re.search(pattern, str(actual)) is not None
        return False
    if actual == expected:
        return True
    return str(actual).strip() == str(expected).strip()


def _dict_contains(target: dict[str, Any], probe: dict[str, Any]) -> bool:
    for key, expected in probe.items():
        if key not in target:
            return False
        if not _match_value(target.get(key), expected):
            return False
    return True


def _evaluate_list_result(
    rows: list[dict[str, Any]],
    expected: dict[str, Any],
    *,
    parser_name: str = "",
    driver_name: str = "",
) -> list[str]:
    reasons: list[str] = []

    min_rows = int(expected.get("min_rows") or 0)
    if len(rows) < min_rows:
        reasons.append(f"Expected at least {min_rows} rows, got {len(rows)}")

    contains_rows = expected.get("contains_rows") or []
    if isinstance(contains_rows, list):
        for probe in contains_rows:
            if not isinstance(probe, dict):
                reasons.append("contains_rows must contain objects")
                continue
            if not any(_dict_contains(row, probe) for row in rows):
                reasons.append(f"Row probe not matched: {probe}")

    forbid_rows = expected.get("forbid_rows") or []
    if isinstance(forbid_rows, list):
        for probe in forbid_rows:
            if not isinstance(probe, dict):
                reasons.append("forbid_rows must contain objects")
                continue
            if any(_dict_contains(row, probe) for row in rows):
                reasons.append(f"Forbidden row probe matched: {probe}")

    required_protocols = expected.get("required_protocols") or []
    if isinstance(required_protocols, list) and required_protocols:
        seen_protocols = {str(r.get("protocol") or "") for r in rows}
        for proto in required_protocols:
            if str(proto) not in seen_protocols:
                reasons.append(f"Missing required protocol '{proto}' in rows")

    parser_contains = str(expected.get("parser_contains") or "").strip()
    if parser_contains and parser_contains.lower() not in parser_name.lower():
        reasons.append(f"Parser '{parser_name}' does not contain '{parser_contains}'")

    driver_contains = str(expected.get("driver_contains") or "").strip()
    if driver_contains and driver_contains.lower() not in driver_name.lower():
        reasons.append(f"Driver '{driver_name}' does not contain '{driver_contains}'")

    return reasons


def _evaluate_facts_result(
    facts: dict[str, Any],
    expected: dict[str, Any],
    *,
    driver_name: str,
) -> list[str]:
    reasons: list[str] = []
    checks = expected.get("facts_contains") or {}
    if not isinstance(checks, dict):
        reasons.append("facts_contains must be an object")
        return reasons
    for key, probe in checks.items():
        if key not in facts:
            reasons.append(f"Missing fact key '{key}'")
            continue
        if not _match_value(facts.get(key), probe):
            reasons.append(f"Fact '{key}' mismatch. actual={facts.get(key)!r}, expected={probe!r}")

    driver_contains = str(expected.get("driver_contains") or "").strip()
    if driver_contains and driver_contains.lower() not in driver_name.lower():
        reasons.append(f"Driver '{driver_name}' does not contain '{driver_contains}'")
    return reasons


def _run_inventory_case(case: VendorFixtureCase, conn: FixtureConnection) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    selected_parser = ""
    for parser in get_inventory_parsers():
        try:
            if not parser.can_handle(case.device_type):
                continue
        except Exception:
            continue
        try:
            parsed = parser.collect(conn) or []
        except Exception:
            continue
        if parsed:
            rows = [r for r in parsed if isinstance(r, dict)]
            selected_parser = getattr(parser, "name", parser.__class__.__name__)
            break
    return rows, selected_parser


def _build_driver(case: VendorFixtureCase):
    if case.driver_mode == "generic":
        return GenericDriver(
            hostname="fixture-host",
            username="fixture-user",
            password="fixture-pass",
            device_type=case.device_type,
        )
    return DriverManager.get_driver(
        device_type=case.device_type,
        hostname="fixture-host",
        username="fixture-user",
        password="fixture-pass",
    )


def _run_neighbors_case(case: VendorFixtureCase, conn: FixtureConnection) -> tuple[list[dict[str, Any]], str]:
    driver = _build_driver(case)
    driver.connection = conn
    rows = driver.get_neighbors() or []
    return [r for r in rows if isinstance(r, dict)], driver.__class__.__name__


def _run_facts_case(case: VendorFixtureCase, conn: FixtureConnection) -> tuple[dict[str, Any], str]:
    driver = _build_driver(case)
    driver.connection = conn
    facts = driver.get_facts() or {}
    return facts if isinstance(facts, dict) else {}, driver.__class__.__name__


def run_vendor_fixture_case(case: VendorFixtureCase) -> dict[str, Any]:
    conn = FixtureConnection(case.commands)
    reasons: list[str] = []

    parser_name = ""
    driver_name = ""
    rows: list[dict[str, Any]] = []
    facts: dict[str, Any] = {}

    try:
        if case.case_type == "inventory":
            rows, parser_name = _run_inventory_case(case, conn)
            reasons.extend(_evaluate_list_result(rows, case.expected, parser_name=parser_name))
        elif case.case_type == "neighbors":
            rows, driver_name = _run_neighbors_case(case, conn)
            reasons.extend(_evaluate_list_result(rows, case.expected, driver_name=driver_name))
        elif case.case_type == "facts":
            facts, driver_name = _run_facts_case(case, conn)
            reasons.extend(_evaluate_facts_result(facts, case.expected, driver_name=driver_name))
        else:
            reasons.append(f"Unsupported case type: {case.case_type}")
    except Exception as exc:
        reasons.append(f"Execution error: {type(exc).__name__}: {exc}")

    status = "pass" if not reasons else "fail"
    result = {
        "id": case.case_id,
        "type": case.case_type,
        "device_type": case.device_type,
        "fixture_group": case.fixture_group,
        "path": _relative(case.path),
        "driver_mode": case.driver_mode,
        "status": status,
        "parser": parser_name,
        "driver": driver_name,
        "row_count": len(rows),
        "reasons": reasons,
    }
    if case.case_type == "facts":
        result["facts"] = facts
    return result


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total": len(results),
        "passed": 0,
        "failed": 0,
        "pass_rate_pct": 0.0,
        "by_type": {},
        "by_device_type": {},
        "by_fixture_group": {},
        "coverage": {},
    }
    for row in results:
        passed = row.get("status") == "pass"
        if passed:
            summary["passed"] += 1
        else:
            summary["failed"] += 1

        ctype = str(row.get("type") or "")
        dtype = str(row.get("device_type") or "")
        gname = str(row.get("fixture_group") or "default")
        for bucket_name, key in (("by_type", ctype), ("by_device_type", dtype), ("by_fixture_group", gname)):
            bucket = summary[bucket_name].setdefault(key, {"total": 0, "passed": 0, "failed": 0})
            bucket["total"] += 1
            if passed:
                bucket["passed"] += 1
            else:
                bucket["failed"] += 1

    if summary["total"] > 0:
        summary["pass_rate_pct"] = round((summary["passed"] / summary["total"]) * 100.0, 2)

    target_types = get_supported_device_types()
    covered_types = sorted(summary["by_device_type"].keys())
    missing_types = sorted(set(target_types) - set(covered_types))
    coverage_pct = 100.0
    if target_types:
        coverage_pct = round(((len(target_types) - len(missing_types)) / len(target_types)) * 100.0, 2)
    summary["coverage"] = {
        "target_device_types": target_types,
        "covered_device_types": covered_types,
        "missing_device_types": missing_types,
        "coverage_pct": coverage_pct,
    }
    return summary


def get_supported_device_types() -> list[str]:
    supported = set(DriverManager.CUSTOM_DRIVERS.keys()) | set(DriverManager.GENERIC_SUPPORT)
    return sorted(str(x).strip().lower() for x in supported if str(x).strip())


def run_vendor_parser_benchmark(cases: list[VendorFixtureCase]) -> dict[str, Any]:
    results = [run_vendor_fixture_case(case) for case in cases]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixtures_root": _relative(DEFAULT_VENDOR_FIXTURES_ROOT),
        "summary": _summarize(results),
        "results": results,
    }


def write_vendor_benchmark_report(report: dict[str, Any], output: Path) -> Path:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def _readiness_level(passed_types: set[str]) -> str:
    has_facts = "facts" in passed_types
    has_inventory = "inventory" in passed_types
    has_neighbors = "neighbors" in passed_types

    if has_facts and has_inventory and has_neighbors:
        return "full"
    if has_facts and (has_inventory or has_neighbors):
        return "extended"
    if has_facts:
        return "basic"
    if has_inventory or has_neighbors:
        return "partial"
    return "none"


def build_vendor_capability_matrix(report: dict[str, Any]) -> dict[str, Any]:
    raw_results = report.get("results") or []
    results = [r for r in raw_results if isinstance(r, dict)]
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    coverage = summary.get("coverage") if isinstance(summary.get("coverage"), dict) else {}

    supported_types = [
        str(x).strip().lower()
        for x in (coverage.get("target_device_types") or get_supported_device_types())
        if str(x).strip()
    ]
    matrix_rows: list[dict[str, Any]] = []

    by_device: dict[str, dict[str, Any]] = {}
    for row in results:
        dtype = str(row.get("device_type") or "").strip().lower()
        if not dtype:
            continue
        ctype = str(row.get("type") or "").strip().lower()
        status = str(row.get("status") or "").strip().lower()
        fixture_group = str(row.get("fixture_group") or "default").strip().lower()
        driver_mode = str(row.get("driver_mode") or "manager").strip().lower()

        entry = by_device.setdefault(
            dtype,
            {
                "device_type": dtype,
                "totals": {"total": 0, "passed": 0, "failed": 0},
                "by_type": {},
                "fixture_groups": set(),
                "driver_modes": set(),
            },
        )
        entry["totals"]["total"] += 1
        if status == "pass":
            entry["totals"]["passed"] += 1
        else:
            entry["totals"]["failed"] += 1

        by_type = entry["by_type"].setdefault(ctype, {"total": 0, "passed": 0, "failed": 0})
        by_type["total"] += 1
        if status == "pass":
            by_type["passed"] += 1
        else:
            by_type["failed"] += 1

        entry["fixture_groups"].add(fixture_group)
        entry["driver_modes"].add(driver_mode)

    for dtype in sorted(set(supported_types) | set(by_device.keys())):
        base = by_device.get(
            dtype,
            {
                "device_type": dtype,
                "totals": {"total": 0, "passed": 0, "failed": 0},
                "by_type": {},
                "fixture_groups": set(),
                "driver_modes": set(),
            },
        )
        passed_types = {
            ctype for ctype, bucket in base["by_type"].items() if int(bucket.get("passed") or 0) > 0
        }
        readiness = _readiness_level(passed_types)
        score = 0
        if "facts" in passed_types:
            score += 30
        if "inventory" in passed_types:
            score += 30
        if "neighbors" in passed_types:
            score += 40

        matrix_rows.append(
            {
                "device_type": dtype,
                "readiness": readiness,
                "readiness_score": score,
                "totals": base["totals"],
                "by_type": base["by_type"],
                "fixture_groups": sorted(base["fixture_groups"]),
                "driver_modes": sorted(base["driver_modes"]),
                "covered": bool(base["totals"]["total"]),
            }
        )

    readiness_summary = {
        "full": 0,
        "extended": 0,
        "basic": 0,
        "partial": 0,
        "none": 0,
    }
    for row in matrix_rows:
        readiness_summary[str(row.get("readiness") or "none")] += 1

    covered_count = sum(1 for row in matrix_rows if row.get("covered"))
    total_supported = len(matrix_rows)
    coverage_pct = round((covered_count / total_supported) * 100.0, 2) if total_supported else 100.0

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_report_generated_at": report.get("generated_at"),
        "summary": {
            "total_supported_device_types": total_supported,
            "covered_device_types": covered_count,
            "coverage_pct": coverage_pct,
            "readiness": readiness_summary,
        },
        "rows": matrix_rows,
    }


def render_vendor_capability_matrix_markdown(matrix: dict[str, Any]) -> str:
    summary = matrix.get("summary") if isinstance(matrix.get("summary"), dict) else {}
    rows = matrix.get("rows") if isinstance(matrix.get("rows"), list) else []

    lines = [
        "# Vendor Capability Matrix (Fixture-based)",
        "",
        f"- Generated At: `{matrix.get('generated_at')}`",
        f"- Coverage: `{summary.get('covered_device_types', 0)}/{summary.get('total_supported_device_types', 0)}` (`{summary.get('coverage_pct', 0)}%`)",
    ]

    readiness = summary.get("readiness") if isinstance(summary.get("readiness"), dict) else {}
    lines.append(
        "- Readiness: "
        + ", ".join(
            [
                f"full={int(readiness.get('full', 0))}",
                f"extended={int(readiness.get('extended', 0))}",
                f"basic={int(readiness.get('basic', 0))}",
                f"partial={int(readiness.get('partial', 0))}",
                f"none={int(readiness.get('none', 0))}",
            ]
        )
    )
    lines.append("")
    lines.append("| device_type | readiness | score | facts | inventory | neighbors | groups |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | --- |")

    def _passed_of(row: dict[str, Any], ctype: str) -> int:
        by_type = row.get("by_type") if isinstance(row.get("by_type"), dict) else {}
        bucket = by_type.get(ctype) if isinstance(by_type.get(ctype), dict) else {}
        return int(bucket.get("passed") or 0)

    for row in rows:
        groups = ",".join(row.get("fixture_groups") or [])
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("device_type") or ""),
                    str(row.get("readiness") or "none"),
                    str(int(row.get("readiness_score") or 0)),
                    str(_passed_of(row, "facts")),
                    str(_passed_of(row, "inventory")),
                    str(_passed_of(row, "neighbors")),
                    groups or "-",
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def write_vendor_capability_matrix_report(matrix: dict[str, Any], output: Path) -> Path:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
