#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
REPORTS_ROOT = PROJECT_ROOT / "docs" / "reports"
ARCHIVE_ROOT = REPORTS_ROOT / "archive"
ARCHIVE_PREFIXES = (
    "northbound-soak-preflight",
    "northbound-soak-progress-test",
    "northbound-soak-quickcheck2",
    "northbound-soak-smoke",
    "northbound-soak-windowless-test",
)
KEEP_ROOT_FILES = {
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
MOVE_DIRS = ("daily", "soak", "signoff-bundles")


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _should_archive_root_file(path: Path) -> bool:
    name = path.name
    if name in KEEP_ROOT_FILES:
        return False
    if name == ".ipDISK.db":
        return True
    if name.startswith("kpi-readiness-") and name.endswith((".json", ".md")):
        return True
    if name.startswith("northbound-soak-probe-") and name.endswith((".json", ".md")):
        return True
    if name in {"northbound-soak-72h.err.log", "northbound-soak-72h.log", "northbound-soak-72h.progress.log"}:
        return True
    return any(name.startswith(prefix) for prefix in ARCHIVE_PREFIXES)


def cleanup_generated_reports(
    *,
    reports_root: Path = REPORTS_ROOT,
    archive_root: Path = ARCHIVE_ROOT,
) -> dict:
    stamp = _now_stamp()
    archive_session_root = archive_root / stamp
    root_archive = archive_session_root / "root-files"
    dirs_archive = archive_session_root / "legacy-dirs"
    moved_files: list[str] = []
    moved_dirs: list[str] = []

    archive_session_root.mkdir(parents=True, exist_ok=True)

    for path in sorted(reports_root.iterdir(), key=lambda p: p.name):
        if path.name == "archive":
            continue
        if path.is_file() and _should_archive_root_file(path):
            root_archive.mkdir(parents=True, exist_ok=True)
            dst = root_archive / path.name
            shutil.move(str(path), str(dst))
            moved_files.append(path.name)

    for dirname in MOVE_DIRS:
        src = reports_root / dirname
        if not src.exists():
            continue
        dirs_archive.mkdir(parents=True, exist_ok=True)
        dst = dirs_archive / dirname
        if dst.exists():
            shutil.rmtree(dst)
        shutil.move(str(src), str(dst))
        moved_dirs.append(dirname)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "archive_root": str(archive_session_root),
        "moved_files_count": len(moved_files),
        "moved_dirs_count": len(moved_dirs),
        "moved_files": moved_files,
        "moved_dirs": moved_dirs,
    }
    (archive_session_root / "cleanup-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive stale generated report artifacts and completed validation bundles.")
    parser.add_argument("--reports-root", default=str(REPORTS_ROOT), help="Root report directory to clean")
    parser.add_argument("--archive-root", default=str(ARCHIVE_ROOT), help="Archive directory")
    args = parser.parse_args()

    summary = cleanup_generated_reports(
        reports_root=Path(args.reports_root).resolve(),
        archive_root=Path(args.archive_root).resolve(),
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
