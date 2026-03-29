#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

DEFAULT_FILES = [
    ".env.preview.example",
    "preview-installer/bootstrap-install.ps1",
    "preview-installer/bootstrap-install.cmd",
    "preview-installer/install-preview-collector.ps1",
    "preview-installer/launch-preview-collector.cmd",
    "preview-installer/open-preview-ui.ps1",
    "preview-installer/open-preview-ui.cmd",
    "preview-installer/start-preview-collector.ps1",
    "preview-installer/start-preview-collector.cmd",
    "preview-installer/stop-preview-collector.ps1",
    "preview-installer/stop-preview-collector.cmd",
    "preview-installer/uninstall-preview-collector.ps1",
    "preview-installer/uninstall-preview-collector.cmd",
]

DEFAULT_DOCS = [
    "docs/README.md",
    "docs/USER_GUIDE.md",
    "docs/FEATURE_BROCHURE.md",
    "docs/PREVIEW_BROCHURE.md",
    "docs/PREVIEW_EXPERIENCE_POLICY.md",
    "docs/PREVIEW_CONTRIBUTOR_GUIDE.md",
    "docs/PREVIEW_INSTALL_TEST_CHECKLIST.md",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_rel_files(out_dir: Path, rel_files: list[str]) -> list[str]:
    copied: list[str] = []
    for rel in rel_files:
        src = (PROJECT_ROOT / rel).resolve()
        if not src.exists():
            continue
        _copy_file(src, out_dir / rel)
        copied.append(rel)
    return copied


def build_manifest(*, copied_files: list[str], copied_docs: list[str]) -> dict:
    return {
        "generated_at": _now_iso(),
        "edition": "preview",
        "distribution_model": "installed_collector",
        "product_name": "NetSphere",
        "positioning": "installed free intake edition for discovery, topology, connected NMS, and masked parser contribution",
        "included_files": list(copied_files),
        "included_docs": list(copied_docs),
        "runtime_defaults": {
            "deployment_role": "collector_installed",
            "upload_target_mode": "remote_only",
            "local_embedded_execution": True,
            "raw_original_persistence": False,
        },
    }


def package_preview_installer_bundle(*, out_dir: Path, zip_name: str, files: list[str], docs: list[str]) -> tuple[Path, Path]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    copied_files = _copy_rel_files(out_dir, files)
    copied_docs = _copy_rel_files(out_dir, docs)
    manifest = build_manifest(copied_files=copied_files, copied_docs=copied_docs)
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    readme_path = out_dir / "README.txt"
    readme_path.write_text(
        "\n".join(
            [
                "NetSphere Free Installer Package",
                "================================",
                "",
                "This package contains installer-oriented scripts and docs for NetSphere Free.",
                "",
                "Start sequence:",
                "1. Build the installer stage",
                "2. Build the Windows setup executable",
                "3. Distribute the generated setup executable to pilot users",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    zip_path = out_dir.parent / zip_name
    if zip_path.exists():
        zip_path.unlink()
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for file_path in sorted(out_dir.rglob("*")):
            if file_path.is_file():
                zf.write(file_path, file_path.relative_to(out_dir).as_posix())
    return out_dir, zip_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Package NetSphere preview installer bundle.")
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "dist" / "preview-installer-package"))
    parser.add_argument("--zip-name", default="preview-installer-package.zip")
    args = parser.parse_args()

    out_dir, zip_path = package_preview_installer_bundle(
        out_dir=Path(args.out_dir),
        zip_name=str(args.zip_name),
        files=list(DEFAULT_FILES),
        docs=list(DEFAULT_DOCS),
    )
    print(json.dumps({"out_dir": str(out_dir), "zip_path": str(zip_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
