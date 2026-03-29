import io
import json
from zipfile import ZipFile

from tools import package_sales_demo_bundle as tool


def test_build_demo_manifest_uses_current_proof_inputs():
    manifest = tool.build_demo_manifest(
        release_evidence={"summary": {"overall_status": "warning", "accepted_gates": 3, "total_gates": 4}},
        kpi_readiness={"payload": {"readiness": {"status": "healthy"}}},
        vendor_support={"summary": {"readiness": {"full": 18, "extended": 6, "basic": 25}}},
        synthetic_validation={"overall_pass": True, "summary": {"checked_fixture_scenarios": 7}},
        real_device_acceptance={"summary": {"wave_counts": {"wave_1": 28}}},
    )

    assert manifest["current_proof"]["release_overall_status"] == "warning"
    assert manifest["current_proof"]["accepted_gates"] == 3
    assert manifest["current_proof"]["kpi_status"] == "healthy"
    assert manifest["current_proof"]["vendor_full_count"] == 18
    assert manifest["current_proof"]["vendor_basic_or_better_count"] == 49
    assert manifest["current_proof"]["synthetic_overall_pass"] is True
    assert manifest["current_proof"]["real_device_wave_1"] == 28
    assert len(manifest["demo_tracks"]) >= 5


def test_package_sales_demo_bundle_writes_manifest_brief_and_zip(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    reports_dir = docs_dir / "reports"
    docs_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    backend_cache = tmp_path / "backend_cache"
    backend_cache.mkdir(parents=True, exist_ok=True)

    (docs_dir / "README.md").write_text("# Index\n", encoding="utf-8")
    (docs_dir / "USER_GUIDE.md").write_text("# Guide\n", encoding="utf-8")
    (docs_dir / "FEATURE_BROCHURE.md").write_text("# Brochure\n", encoding="utf-8")
    (docs_dir / "SALES_DEMO_PLAYBOOK.md").write_text("# Demo\n", encoding="utf-8")
    (docs_dir / "AUTODISCOVERY_AUTOTOPOLOGY_RUNBOOK.md").write_text("# Auto\n", encoding="utf-8")
    (docs_dir / "KPI_READINESS_RUNBOOK.md").write_text("# KPI\n", encoding="utf-8")
    (docs_dir / "VENDOR_SUPPORT_POLICY.md").write_text("# Policy\n", encoding="utf-8")
    ov_dir = docs_dir / "operational-validation"
    ov_dir.mkdir(parents=True, exist_ok=True)
    (ov_dir / "REAL_DEVICE_ACCEPTANCE_RUNBOOK.md").write_text("# Acceptance\n", encoding="utf-8")
    (reports_dir / "kpi-readiness-30d-latest.json").write_text(json.dumps({"payload": {"readiness": {"status": "healthy"}}}), encoding="utf-8")
    (reports_dir / "vendor-support-matrix.latest.json").write_text(json.dumps({"summary": {"readiness": {"full": 1, "extended": 1, "basic": 1}}}), encoding="utf-8")
    (reports_dir / "synthetic-validation-matrix.latest.json").write_text(json.dumps({"overall_pass": True, "summary": {"checked_fixture_scenarios": 7}}), encoding="utf-8")
    (reports_dir / "real-device-acceptance.latest.json").write_text(json.dumps({"summary": {"wave_counts": {"wave_1": 3}}}), encoding="utf-8")
    (backend_cache / "release-evidence.latest.json").write_text(json.dumps({"summary": {"overall_status": "warning", "accepted_gates": 3, "total_gates": 4}}), encoding="utf-8")

    monkeypatch.setattr(tool, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(tool, "REPORT_CACHE_DIR", backend_cache)
    monkeypatch.setattr(
        tool,
        "REPORT_SPECS",
        {
            "reports/release-evidence.latest.json": (backend_cache / "release-evidence.latest.json",),
            "reports/kpi-readiness-30d-latest.json": (reports_dir / "kpi-readiness-30d-latest.json",),
            "reports/vendor-support-matrix.latest.json": (reports_dir / "vendor-support-matrix.latest.json",),
            "reports/synthetic-validation-matrix.latest.json": (reports_dir / "synthetic-validation-matrix.latest.json",),
            "reports/real-device-acceptance.latest.json": (reports_dir / "real-device-acceptance.latest.json",),
        },
    )

    out_dir, zip_path = tool.package_sales_demo_bundle(
        out_dir=tmp_path / "dist" / "sales-demo-package",
        zip_name="sales-demo-package.zip",
        docs=list(tool.DEFAULT_DOCS),
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["current_proof"]["accepted_gates"] == 3
    assert (out_dir / "demo-brief.md").exists()
    assert zip_path.exists()
    with ZipFile(io.BytesIO(zip_path.read_bytes()), "r") as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    assert "demo-brief.md" in names
    assert "docs/README.md" in names
    assert "docs/USER_GUIDE.md" in names
    assert "docs/FEATURE_BROCHURE.md" in names
    assert "docs/SALES_DEMO_PLAYBOOK.md" in names
    assert "reports/release-evidence.latest.json" in names
