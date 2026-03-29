import json

from tools import cleanup_generated_reports as tool


def test_cleanup_generated_reports_moves_stale_outputs_and_keeps_latest(tmp_path, monkeypatch):
    reports_root = tmp_path / "docs" / "reports"
    archive_root = reports_root / "archive"
    reports_root.mkdir(parents=True, exist_ok=True)

    keep_names = {
        "kpi-readiness-30d-latest.json",
        "kpi-readiness-30d-latest.md",
        "northbound-soak-72h-latest.json",
        "northbound-soak-72h-latest.md",
        "northbound-soak-72h-run-state.json",
        "northbound-soak-probe.latest.json",
        "northbound-soak-probe.latest.md",
        "northbound-soak-probe.progress.log",
        "real-device-acceptance.latest.json",
        "real-device-acceptance.latest.md",
        "real-device-acceptance-checklist.latest.csv",
        "synthetic-validation-matrix.latest.json",
        "synthetic-validation-matrix.latest.md",
        "vendor-parser-benchmark.latest.json",
        "vendor-support-matrix.latest.json",
        "vendor-support-matrix.latest.md",
    }
    for name in keep_names:
        (reports_root / name).write_text("keep", encoding="utf-8")

    stale_files = {
        ".ipDISK.db",
        "kpi-readiness-20260304-155851.json",
        "kpi-readiness-20260304-155851.md",
        "northbound-soak-probe-20260309-041333.json",
        "northbound-soak-probe-20260309-041333.md",
        "northbound-soak-72h.err.log",
        "northbound-soak-72h.log",
        "northbound-soak-72h.progress.log",
        "northbound-soak-preflight-latest.json",
        "northbound-soak-preflight-latest.md",
        "northbound-soak-smoke.progress.log",
    }
    for name in stale_files:
        (reports_root / name).write_text("stale", encoding="utf-8")

    for dirname in ("daily", "soak", "signoff-bundles"):
        subdir = reports_root / dirname
        subdir.mkdir(parents=True, exist_ok=True)
        (subdir / "sample.txt").write_text(dirname, encoding="utf-8")

    monkeypatch.setattr(tool, "_now_stamp", lambda: "20260309-150000")
    summary = tool.cleanup_generated_reports(reports_root=reports_root, archive_root=archive_root)

    session_root = archive_root / "20260309-150000"
    root_archive = session_root / "root-files"
    dirs_archive = session_root / "legacy-dirs"

    assert summary["moved_files_count"] == len(stale_files)
    assert summary["moved_dirs_count"] == 3
    assert sorted(summary["moved_dirs"]) == ["daily", "signoff-bundles", "soak"]
    assert json.loads((session_root / "cleanup-summary.json").read_text(encoding="utf-8"))["moved_files_count"] == len(stale_files)

    for name in keep_names:
        assert (reports_root / name).exists()

    for name in stale_files:
        assert not (reports_root / name).exists()
        assert (root_archive / name).exists()

    for dirname in ("daily", "soak", "signoff-bundles"):
        assert not (reports_root / dirname).exists()
        assert (dirs_archive / dirname / "sample.txt").exists()
