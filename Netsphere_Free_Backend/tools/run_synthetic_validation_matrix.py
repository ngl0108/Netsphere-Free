from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tools.run_synthetic_soak import run_soak
except ModuleNotFoundError:  # pragma: no cover - script execution fallback
    from run_synthetic_soak import run_soak


REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTHETIC_ROOT = REPO_ROOT / "test-data" / "synthetic"
SCENARIO_ROOT = SYNTHETIC_ROOT / "scenarios"
MANIFEST_PATH = SYNTHETIC_ROOT / "manifest.json"
EVE_PLAN_PATH = REPO_ROOT / "docs" / "operational-validation" / "eve-global-vendor-test-plan.md"
DEFAULT_JSON_OUT = REPO_ROOT / "docs" / "reports" / "synthetic-validation-matrix.latest.json"
DEFAULT_MD_OUT = REPO_ROOT / "docs" / "reports" / "synthetic-validation-matrix.latest.md"

REQUIRED_SCENARIOS = ("normal", "large_scale", "failure", "security_incident")
EXPANDED_SCENARIOS = ("rollback_wave", "hybrid_cloud", "wireless_edge")
REQUIRED_SCENARIO_FOCUS_AREAS = ("rollback", "hybrid", "wireless")
REQUIRED_PROTOCOLS = ("snmp", "ssh", "gnmi")
REQUIRED_DIGITAL_TWIN_VENDORS = (
    "cisco",
    "arista",
    "juniper",
    "fortinet",
    "paloalto",
    "f5",
    "nokia",
    "vyos",
    "mikrotik",
)
REQUIRED_FIRST_WAVE_VENDORS = ("Juniper", "Fortinet", "Palo Alto", "F5", "Nokia", "VyOS", "MikroTik")

DEFAULT_SCENARIO_SPECS: dict[str, dict[str, int]] = {
    "normal": {"duration_sec": 5, "tick_ms": 10},
    "failure": {"duration_sec": 5, "tick_ms": 10},
    "security_incident": {"duration_sec": 5, "tick_ms": 10},
    "rollback_wave": {"duration_sec": 5, "tick_ms": 10},
    "hybrid_cloud": {"duration_sec": 5, "tick_ms": 10},
    "wireless_edge": {"duration_sec": 5, "tick_ms": 10},
    "large_scale": {"duration_sec": 5, "tick_ms": 5},
}

PROFILE_PRESETS: dict[str, list[str]] = {
    "ci": ["failure", "security_incident", "rollback_wave", "large_scale"],
    "local": ["normal", "failure", "security_incident", "rollback_wave", "hybrid_cloud", "wireless_edge", "large_scale"],
    "release": ["normal", "failure", "security_incident", "rollback_wave", "hybrid_cloud", "wireless_edge", "large_scale"],
}

PROFILE_MULTIPLIERS: dict[str, float] = {
    "ci": 1.0,
    "local": 2.0,
    "release": 4.0,
}


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _scenario_path(name: str, scenario_root: Path = SCENARIO_ROOT) -> Path:
    return scenario_root / f"{name}.json"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def summarize_scenario(name: str, scenario_root: Path = SCENARIO_ROOT) -> dict[str, Any]:
    path = _scenario_path(name, scenario_root)
    payload = _load_json(path)
    devices = list(payload.get("devices") or [])
    links = list(payload.get("links") or [])
    events = list(payload.get("events") or [])
    severities = Counter(str(event.get("severity") or "info").strip().lower() for event in events)
    focus_areas = [str(item).strip().lower() for item in list(payload.get("focus_areas") or []) if str(item).strip()]
    protocols = sorted(
        {
            str(link.get("protocol") or "").strip().lower()
            for link in links
            if str(link.get("protocol") or "").strip()
        }
    )
    event_types = sorted(
        {
            str(event.get("type") or "").strip().lower()
            for event in events
            if str(event.get("type") or "").strip()
        }
    )
    vendor_mix = payload.get("vendor_mix") if isinstance(payload.get("vendor_mix"), dict) else {}

    return {
        "name": name,
        "path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "focus_areas": focus_areas,
        "protocols": protocols,
        "event_types": event_types,
        "counts": {
            "devices": len(devices),
            "links": len(links),
            "events": len(events),
        },
        "vendor_mix": {str(key): int(value) for key, value in vendor_mix.items()},
        "severities": {
            "critical": int(severities.get("critical", 0)),
            "warning": int(severities.get("warning", 0) + severities.get("warn", 0)),
            "info": int(severities.get("info", 0)),
        },
    }


def validate_manifest(manifest_path: Path = MANIFEST_PATH, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    files = list(manifest.get("files") or [])
    missing_files: list[str] = []
    hash_mismatches: list[str] = []

    for row in files:
        rel = Path(str(row.get("path") or "").replace("/", "\\"))
        expected_hash = str(row.get("sha256") or "").strip().lower()
        target = repo_root / rel
        display = str(rel).replace("\\", "/")
        if not target.exists():
            missing_files.append(display)
            continue
        if _sha256(target).lower() != expected_hash:
            hash_mismatches.append(display)

    protocols_present = []
    protocol_vendor_map: dict[str, list[str]] = {}
    protocol_case_map: dict[str, dict[str, list[str]]] = {}
    for protocol in REQUIRED_PROTOCOLS:
        target = SYNTHETIC_ROOT / "digital-twin" / f"{protocol}.json"
        if target.exists():
            protocols_present.append(protocol)
            payload = _load_json(target)
            vendors = payload.get("vendors") if isinstance(payload.get("vendors"), dict) else {}
            protocol_vendor_map[protocol] = sorted(str(key) for key in vendors.keys())
            protocol_case_map[protocol] = {
                str(vendor): sorted(str(case_name) for case_name in cases.keys())
                for vendor, cases in vendors.items()
                if isinstance(cases, dict)
            }

    shared_vendors = set(protocol_vendor_map.get(protocols_present[0], [])) if protocols_present else set()
    for protocol in protocols_present[1:]:
        shared_vendors &= set(protocol_vendor_map.get(protocol, []))
    shared_case_consistency = True
    if shared_vendors:
        for vendor in shared_vendors:
            case_signatures = {
                tuple(protocol_case_map.get(protocol, {}).get(vendor, []))
                for protocol in protocols_present
            }
            if len(case_signatures) > 1:
                shared_case_consistency = False
                break

    pass_map = {
        "manifest_file_exists": manifest_path.exists(),
        "manifest_has_entries": bool(files),
        "manifest_hashes_match": not missing_files and not hash_mismatches,
        "digital_twin_protocols_present": set(protocols_present) == set(REQUIRED_PROTOCOLS),
        "digital_twin_vendor_floor": set(REQUIRED_DIGITAL_TWIN_VENDORS).issubset(shared_vendors),
        "digital_twin_case_consistency": shared_case_consistency,
    }

    return {
        "path": str(manifest_path.relative_to(repo_root)).replace("\\", "/"),
        "generated_at": manifest.get("generated_at"),
        "base_seed": manifest.get("base_seed"),
        "file_count": len(files),
        "missing_files": missing_files,
        "hash_mismatches": hash_mismatches,
        "protocols_present": protocols_present,
        "digital_twin_vendors": sorted(shared_vendors),
        "protocol_vendor_map": protocol_vendor_map,
        "pass": pass_map,
    }


def build_scenario_catalog(scenario_root: Path = SCENARIO_ROOT) -> dict[str, Any]:
    available_names = sorted(path.stem for path in scenario_root.glob("*.json"))
    rows = [summarize_scenario(name, scenario_root) for name in available_names]
    by_name = {row["name"]: row for row in rows}
    missing_required = [name for name in REQUIRED_SCENARIOS if name not in by_name]
    missing_expanded = [name for name in EXPANDED_SCENARIOS if name not in by_name]

    normal = by_name.get("normal", {})
    failure = by_name.get("failure", {})
    security_incident = by_name.get("security_incident", {})
    large_scale = by_name.get("large_scale", {})
    rollback_wave = by_name.get("rollback_wave", {})
    hybrid_cloud = by_name.get("hybrid_cloud", {})
    wireless_edge = by_name.get("wireless_edge", {})

    focus_areas_present = sorted(
        {
            str(area).strip().lower()
            for row in rows
            for area in list(row.get("focus_areas") or [])
            if str(area).strip()
        }
    )
    protocols_present = sorted(
        {
            str(protocol).strip().lower()
            for row in rows
            for protocol in list(row.get("protocols") or [])
            if str(protocol).strip()
        }
    )

    pass_map = {
        "required_scenarios_present": not missing_required,
        "expanded_scenarios_present": not missing_expanded,
        "scenario_count_floor": len(rows) >= len(REQUIRED_SCENARIOS) + len(EXPANDED_SCENARIOS),
        "normal_has_only_info_events": int((normal.get("severities") or {}).get("critical") or 0) == 0
        and int((normal.get("severities") or {}).get("warning") or 0) == 0
        and int((normal.get("counts") or {}).get("events") or 0) >= 10,
        "failure_has_critical_signal": int((failure.get("severities") or {}).get("critical") or 0) >= 1
        and int((failure.get("severities") or {}).get("warning") or 0) >= 1,
        "security_incident_has_critical_burst": int((security_incident.get("severities") or {}).get("critical") or 0)
        >= 10,
        "large_scale_meets_floor": int((large_scale.get("counts") or {}).get("devices") or 0) >= 200
        and int((large_scale.get("counts") or {}).get("links") or 0) >= 300
        and int((large_scale.get("counts") or {}).get("events") or 0) >= 50,
        "expanded_focus_areas_present": set(REQUIRED_SCENARIO_FOCUS_AREAS).issubset(set(focus_areas_present)),
        "rollback_wave_has_rollback_signal": "rollback" in list(rollback_wave.get("focus_areas") or [])
        and "auto_rollback_executed" in list(rollback_wave.get("event_types") or [])
        and int((rollback_wave.get("severities") or {}).get("critical") or 0) >= 1,
        "hybrid_cloud_has_hybrid_signal": "hybrid" in list(hybrid_cloud.get("focus_areas") or [])
        and set(list(hybrid_cloud.get("protocols") or [])) >= {"bgp", "cloud"},
        "wireless_edge_has_wireless_signal": "wireless" in list(wireless_edge.get("focus_areas") or [])
        and any(str(item).startswith("wireless_") or str(item).startswith("wlan_") for item in list(wireless_edge.get("event_types") or [])),
    }

    total_devices = sum(int((row.get("counts") or {}).get("devices") or 0) for row in rows)
    total_links = sum(int((row.get("counts") or {}).get("links") or 0) for row in rows)
    total_events = sum(int((row.get("counts") or {}).get("events") or 0) for row in rows)

    return {
        "scenarios": rows,
        "summary": {
            "scenario_count": len(rows),
            "required_scenarios": list(REQUIRED_SCENARIOS),
            "missing_required_scenarios": missing_required,
            "expanded_scenarios": list(EXPANDED_SCENARIOS),
            "missing_expanded_scenarios": missing_expanded,
            "focus_areas_present": focus_areas_present,
            "protocols_present": protocols_present,
            "total_devices": total_devices,
            "total_links": total_links,
            "total_events": total_events,
        },
        "pass": pass_map,
    }


def _parse_markdown_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_title = ""
    for raw_line in text.splitlines():
        if raw_line.startswith("## "):
            current_title = raw_line[3:].strip().lower()
            sections[current_title] = []
            continue
        if current_title:
            sections[current_title].append(raw_line.rstrip())
    return sections


def _extract_bullets(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
    return items


def _extract_numbered(lines: list[str]) -> list[str]:
    items: list[str] = []
    for line in lines:
        match = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if match:
            items.append(match.group(1).strip())
    return items


def parse_eve_vendor_test_plan(plan_path: Path = EVE_PLAN_PATH) -> dict[str, Any]:
    text = plan_path.read_text(encoding="utf-8")
    sections = _parse_markdown_sections(text)

    vendors_section = sections.get("3. recommended first-wave vendors", [])
    first_wave: list[str] = []
    second_wave: list[str] = []
    second_wave_mode = False
    for line in vendors_section:
        stripped = line.strip()
        if stripped.lower().startswith("second-wave expansion"):
            second_wave_mode = True
            continue
        if not stripped.startswith("- "):
            continue
        vendor_text = stripped[2:].strip()
        vendor_name = vendor_text.split(":", 1)[0].strip()
        if second_wave_mode:
            second_wave.append(vendor_name)
        else:
            first_wave.append(vendor_name)

    mandatory_cases = _extract_numbered(sections.get("6. mandatory test cases", []))
    acceptance_gates = _extract_bullets(sections.get("7. acceptance gates", []))
    evidence_files = [item for item in _extract_bullets(sections.get("8. evidence files", [])) if item.startswith("`")]
    evidence_files = [item.strip("`") for item in evidence_files]

    pass_map = {
        "required_first_wave_vendors_present": set(REQUIRED_FIRST_WAVE_VENDORS).issubset(set(first_wave)),
        "first_wave_vendor_count_floor": len(first_wave) >= len(REQUIRED_FIRST_WAVE_VENDORS),
        "mandatory_case_count_floor": len(mandatory_cases) >= 8,
        "acceptance_gate_count_floor": len(acceptance_gates) >= 5,
        "evidence_file_count_floor": len(evidence_files) >= 4,
    }

    return {
        "path": str(plan_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "first_wave_vendors": first_wave,
        "second_wave_vendors": second_wave,
        "mandatory_test_cases": mandatory_cases,
        "acceptance_gates": acceptance_gates,
        "evidence_files": evidence_files,
        "pass": pass_map,
    }


def _build_soak_specs(profile: str, selected_scenarios: list[str] | None) -> list[dict[str, int | str]]:
    profile_names = PROFILE_PRESETS.get(profile, PROFILE_PRESETS["ci"])
    names = profile_names
    if selected_scenarios:
        names = selected_scenarios

    multiplier = PROFILE_MULTIPLIERS.get(profile, 1.0)
    specs: list[dict[str, int | str]] = []
    for name in names:
        if name not in DEFAULT_SCENARIO_SPECS:
            raise ValueError(f"Unsupported synthetic scenario: {name}")
        base = DEFAULT_SCENARIO_SPECS[name]
        specs.append(
            {
                "scenario": name,
                "duration_sec": int(max(1, round(base["duration_sec"] * multiplier))),
                "tick_ms": int(base["tick_ms"]),
            }
        )
    return specs


def run_synthetic_validation_matrix(
    *,
    profile: str = "ci",
    selected_scenarios: list[str] | None = None,
    duration_scale: float = 1.0,
    tick_ms_override: int | None = None,
    session_timeout_sec: int = 30,
    refresh_interval_sec: int = 10,
    seed: int = 20260219,
) -> dict[str, Any]:
    manifest = validate_manifest()
    catalog = build_scenario_catalog()
    eve_plan = parse_eve_vendor_test_plan()

    soak_specs = _build_soak_specs(profile, selected_scenarios)
    soak_runs: list[dict[str, Any]] = []
    for index, spec in enumerate(soak_specs):
        duration_sec = int(max(1, round(int(spec["duration_sec"]) * max(duration_scale, 0.01))))
        tick_ms = int(max(1, tick_ms_override if tick_ms_override is not None else int(spec["tick_ms"])))
        soak_runs.append(
            run_soak(
                scenario_name=str(spec["scenario"]),
                duration_sec=duration_sec,
                tick_ms=tick_ms,
                seed=seed + (index * 101),
                session_timeout_sec=max(1, int(session_timeout_sec)),
                refresh_interval_sec=max(1, int(refresh_interval_sec)),
            )
        )

    soak_pass = {
        "runs_executed": bool(soak_runs),
        "all_runs_healthy": all(all((run.get("pass") or {}).values()) for run in soak_runs),
    }
    if any(str(run.get("scenario")) == "large_scale" for run in soak_runs):
        soak_pass["large_scale_has_high_volume"] = any(
            str(run.get("scenario")) == "large_scale"
            and int(((run.get("metrics") or {}).get("processed_events")) or 0) >= 100
            for run in soak_runs
        )

    soak_summary = {
        "run_count": len(soak_runs),
        "total_processed_events": sum(int(((run.get("metrics") or {}).get("processed_events")) or 0) for run in soak_runs),
        "max_duplicate_ratio": round(
            max((float(((run.get("metrics") or {}).get("duplicate_ratio")) or 0.0) for run in soak_runs), default=0.0),
            6,
        ),
        "max_queue_depth": max((int(((run.get("metrics") or {}).get("max_queue_depth")) or 0) for run in soak_runs), default=0),
        "max_throughput_eps": round(
            max((float(((run.get("metrics") or {}).get("throughput_eps")) or 0.0) for run in soak_runs), default=0.0),
            2,
        ),
    }

    overall_pass = all(
        [
            *manifest.get("pass", {}).values(),
            *catalog.get("pass", {}).values(),
            *eve_plan.get("pass", {}).values(),
            *soak_pass.values(),
        ]
    )

    return {
        "generated_at": _iso_now(),
        "profile": profile,
        "manifest": manifest,
        "scenario_catalog": catalog,
        "soak_matrix": {
            "runs": soak_runs,
            "summary": soak_summary,
            "pass": soak_pass,
        },
        "eve_plan": eve_plan,
        "summary": {
            "overall_pass": overall_pass,
            "checked_fixture_scenarios": int((catalog.get("summary") or {}).get("scenario_count") or 0),
            "executed_soak_runs": len(soak_runs),
            "total_processed_events": soak_summary["total_processed_events"],
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    catalog = report.get("scenario_catalog") or {}
    catalog_summary = catalog.get("summary") or {}
    catalog_rows = catalog.get("scenarios") or []
    soak_matrix = report.get("soak_matrix") or {}
    soak_runs = soak_matrix.get("runs") or []
    eve_plan = report.get("eve_plan") or {}

    lines = [
        "# Synthetic Validation Matrix",
        "",
        f"- Generated at: {report.get('generated_at')}",
        f"- Profile: {report.get('profile')}",
        f"- Overall: {'PASS' if summary.get('overall_pass') else 'FAIL'}",
        "",
            "## Scenario catalog",
            "",
        "| Scenario | Devices | Links | Events | Critical | Warning | Info | Focus | Protocols |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in catalog_rows:
        counts = row.get("counts") or {}
        severities = row.get("severities") or {}
        lines.append(
            "| {name} | {devices} | {links} | {events} | {critical} | {warning} | {info} | {focus} | {protocols} |".format(
                name=row.get("name"),
                devices=counts.get("devices", 0),
                links=counts.get("links", 0),
                events=counts.get("events", 0),
                critical=severities.get("critical", 0),
                warning=severities.get("warning", 0),
                info=severities.get("info", 0),
                focus=", ".join(list(row.get("focus_areas") or [])) or "-",
                protocols=", ".join(list(row.get("protocols") or [])) or "-",
            )
        )

    lines.extend(
        [
            "",
            f"- Required scenarios: {', '.join(catalog_summary.get('required_scenarios') or [])}",
            f"- Missing required scenarios: {', '.join(catalog_summary.get('missing_required_scenarios') or []) or 'none'}",
            f"- Expanded scenarios: {', '.join(catalog_summary.get('expanded_scenarios') or [])}",
            f"- Missing expanded scenarios: {', '.join(catalog_summary.get('missing_expanded_scenarios') or []) or 'none'}",
            f"- Focus areas: {', '.join(catalog_summary.get('focus_areas_present') or []) or 'none'}",
            f"- Protocols: {', '.join(catalog_summary.get('protocols_present') or []) or 'none'}",
            f"- Total devices: {catalog_summary.get('total_devices', 0)}",
            f"- Total links: {catalog_summary.get('total_links', 0)}",
            f"- Total events: {catalog_summary.get('total_events', 0)}",
            "",
            "## Soak matrix",
            "",
            "| Scenario | Duration(s) | Tick(ms) | Processed | Dup ratio | Forced logout | Max queue | Throughput eps | Status |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )

    for run in soak_runs:
        metrics = run.get("metrics") or {}
        status = "PASS" if all((run.get("pass") or {}).values()) else "FAIL"
        lines.append(
            "| {scenario} | {duration_sec} | {tick_ms} | {processed_events} | {duplicate_ratio} | {forced_logout_count} | {max_queue_depth} | {throughput_eps} | {status} |".format(
                scenario=run.get("scenario"),
                duration_sec=run.get("duration_sec", 0),
                tick_ms=run.get("tick_ms", 0),
                processed_events=metrics.get("processed_events", 0),
                duplicate_ratio=metrics.get("duplicate_ratio", 0),
                forced_logout_count=metrics.get("forced_logout_count", 0),
                max_queue_depth=metrics.get("max_queue_depth", 0),
                throughput_eps=metrics.get("throughput_eps", 0),
                status=status,
            )
        )

    lines.extend(
        [
            "",
            "## EVE plan coverage",
            "",
            f"- Digital twin vendors: {', '.join((report.get('manifest') or {}).get('digital_twin_vendors') or [])}",
            f"- First-wave vendors: {', '.join(eve_plan.get('first_wave_vendors') or [])}",
            f"- Second-wave vendors: {', '.join(eve_plan.get('second_wave_vendors') or [])}",
            f"- Mandatory cases: {len(eve_plan.get('mandatory_test_cases') or [])}",
            f"- Acceptance gates: {len(eve_plan.get('acceptance_gates') or [])}",
            f"- Evidence files: {len(eve_plan.get('evidence_files') or [])}",
            "",
            "## Gate checks",
            "",
        ]
    )

    for group_name in ("manifest", "scenario_catalog", "soak_matrix", "eve_plan"):
        pass_map = (report.get(group_name) or {}).get("pass") or {}
        if not pass_map:
            continue
        lines.append(f"### {group_name}")
        lines.append("")
        for key, value in pass_map.items():
            lines.append(f"- {key}: {'PASS' if value else 'FAIL'}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_reports(report: dict[str, Any], json_out: Path, md_out: Path) -> tuple[Path, Path]:
    json_output = json_out.resolve()
    md_output = md_out.resolve()
    json_output.parent.mkdir(parents=True, exist_ok=True)
    md_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_output.write_text(render_markdown(report), encoding="utf-8")
    return json_output, md_output


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the synthetic validation matrix for fixture integrity, soak simulation, and EVE plan coverage."
    )
    parser.add_argument("--profile", choices=sorted(PROFILE_PRESETS.keys()), default="ci")
    parser.add_argument("--scenarios", default="", help="Optional comma-separated soak scenarios override.")
    parser.add_argument("--duration-scale", type=float, default=1.0)
    parser.add_argument("--tick-ms-override", type=int, default=0)
    parser.add_argument("--session-timeout-sec", type=int, default=30)
    parser.add_argument("--refresh-interval-sec", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260219)
    parser.add_argument("--json-out", default=str(DEFAULT_JSON_OUT))
    parser.add_argument("--md-out", default=str(DEFAULT_MD_OUT))
    parser.add_argument("--fail-on-unhealthy", action="store_true")
    args = parser.parse_args()

    selected_scenarios = [item.strip() for item in args.scenarios.split(",") if item.strip()]
    report = run_synthetic_validation_matrix(
        profile=args.profile,
        selected_scenarios=selected_scenarios or None,
        duration_scale=float(args.duration_scale),
        tick_ms_override=int(args.tick_ms_override) if int(args.tick_ms_override) > 0 else None,
        session_timeout_sec=max(1, int(args.session_timeout_sec)),
        refresh_interval_sec=max(1, int(args.refresh_interval_sec)),
        seed=int(args.seed),
    )
    json_output, md_output = write_reports(report, Path(args.json_out), Path(args.md_out))

    print(
        "Synthetic validation matrix generated: "
        f"profile={report.get('profile')} "
        f"overall={'pass' if (report.get('summary') or {}).get('overall_pass') else 'fail'} "
        f"soak_runs={((report.get('soak_matrix') or {}).get('summary') or {}).get('run_count', 0)}"
    )
    print(f"JSON report: {json_output}")
    print(f"Markdown report: {md_output}")
    print(json.dumps(report.get("summary") or {}, ensure_ascii=False, indent=2))

    if args.fail_on_unhealthy and not bool((report.get("summary") or {}).get("overall_pass")):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
