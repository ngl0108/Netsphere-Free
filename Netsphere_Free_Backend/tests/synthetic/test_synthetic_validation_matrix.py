from __future__ import annotations

import json
from pathlib import Path

from tools.run_synthetic_validation_matrix import (
    EVE_PLAN_PATH,
    parse_eve_vendor_test_plan,
    run_synthetic_validation_matrix,
    write_reports,
)


def test_parse_eve_vendor_test_plan_expected_coverage():
    report = parse_eve_vendor_test_plan(EVE_PLAN_PATH)

    assert report["pass"]["required_first_wave_vendors_present"] is True
    assert report["pass"]["mandatory_case_count_floor"] is True
    assert report["pass"]["acceptance_gate_count_floor"] is True
    assert set(report["first_wave_vendors"]) >= {
        "Juniper",
        "Fortinet",
        "Palo Alto",
        "F5",
        "Nokia",
        "VyOS",
        "MikroTik",
    }
    assert len(report["mandatory_test_cases"]) >= 8
    assert len(report["acceptance_gates"]) >= 5
    assert len(report["evidence_files"]) >= 4


def test_run_synthetic_validation_matrix_ci_smoke_and_write(tmp_path: Path):
    report = run_synthetic_validation_matrix(
        profile="ci",
        selected_scenarios=["failure", "rollback_wave"],
        duration_scale=0.2,
        tick_ms_override=1,
        seed=20260308,
    )

    assert report["summary"]["overall_pass"] is True
    assert report["soak_matrix"]["summary"]["run_count"] == 2
    assert report["scenario_catalog"]["pass"]["large_scale_meets_floor"] is True
    assert report["scenario_catalog"]["pass"]["expanded_scenarios_present"] is True
    assert report["scenario_catalog"]["pass"]["expanded_focus_areas_present"] is True
    assert report["manifest"]["pass"]["manifest_hashes_match"] is True
    assert report["manifest"]["pass"]["digital_twin_vendor_floor"] is True
    assert report["soak_matrix"]["pass"]["all_runs_healthy"] is True

    json_out = tmp_path / "synthetic-validation.json"
    md_out = tmp_path / "synthetic-validation.md"
    write_reports(report, json_out, md_out)

    written = json.loads(json_out.read_text(encoding="utf-8"))
    assert written["summary"]["overall_pass"] is True
    markdown = md_out.read_text(encoding="utf-8")
    assert "# Synthetic Validation Matrix" in markdown
    assert "| failure |" in markdown
    assert "| rollback_wave |" in markdown
