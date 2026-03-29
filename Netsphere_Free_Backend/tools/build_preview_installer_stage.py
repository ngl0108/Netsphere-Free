#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

DEFAULT_DOCS = [
    "docs/README.md",
    "docs/USER_GUIDE.md",
    "docs/FEATURE_BROCHURE.md",
    "docs/PREVIEW_BROCHURE.md",
    "docs/PREVIEW_EDITION_PLAN.md",
    "docs/PREVIEW_COLLECTOR_ARCHITECTURE.md",
    "docs/PREVIEW_INSTALLER_COLLECTOR_PLAN.md",
    "docs/PREVIEW_EXPERIENCE_POLICY.md",
    "docs/PREVIEW_CONTRIBUTOR_GUIDE.md",
    "docs/PREVIEW_INSTALL_TEST_CHECKLIST.md",
    "docs/PREVIEW_RELEASE_CHECKLIST.md",
]

DEFAULT_FILES = [
    ".env.preview.example",
]

DEFAULT_DIRS = [
    "Netsphere_Free_Backend/app",
    "Netsphere_Free_Frontend/dist",
    "preview-installer",
]

RUNTIME_TOP_LEVEL_FILES = [
    "python.exe",
    "pythonw.exe",
    "python3.dll",
    "python311.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
    "LICENSE.txt",
]

RUNTIME_TOP_LEVEL_DIRS = [
    "DLLs",
    "Lib",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _copy_rel_file(project_root: Path, stage_dir: Path, rel_path: str) -> str:
    src = (project_root / rel_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Missing required file: {src}")
    _copy_file(src, stage_dir / rel_path)
    return rel_path


def _copy_rel_dir(project_root: Path, stage_dir: Path, rel_path: str) -> str:
    src = (project_root / rel_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"Missing required directory: {src}")
    _copy_tree(src, stage_dir / rel_path)
    return rel_path


def _bundle_python_runtime(stage_dir: Path, python_home: Path) -> dict:
    runtime_root = stage_dir / "runtime" / "python"
    runtime_root.mkdir(parents=True, exist_ok=True)

    copied_files: list[str] = []
    copied_dirs: list[str] = []

    for rel_name in RUNTIME_TOP_LEVEL_FILES:
        src = python_home / rel_name
        if src.exists():
            _copy_file(src, runtime_root / rel_name)
            copied_files.append(rel_name)

    for rel_name in RUNTIME_TOP_LEVEL_DIRS:
        src = python_home / rel_name
        if src.exists():
            _copy_tree(src, runtime_root / rel_name)
            copied_dirs.append(rel_name)

    python_executable = runtime_root / "python.exe"
    if not python_executable.exists():
        raise RuntimeError(f"Bundled python executable missing after staging: {python_executable}")

    return {
        "source_home": str(python_home),
        "bundled_root": str(runtime_root),
        "bundled_executable": str(python_executable),
        "copied_top_level_files": copied_files,
        "copied_top_level_dirs": copied_dirs,
    }


def build_preview_installer_stage(
    *,
    out_dir: Path,
    project_root: Path = PROJECT_ROOT,
    python_home: Path | None = None,
    docs: list[str] | None = None,
    files: list[str] | None = None,
    directories: list[str] | None = None,
) -> tuple[Path, dict]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    resolved_docs = list(docs or DEFAULT_DOCS)
    resolved_files = list(files or DEFAULT_FILES)
    resolved_directories = list(directories or DEFAULT_DIRS)

    copied_files = [_copy_rel_file(project_root, out_dir, rel) for rel in resolved_files]
    copied_docs = [_copy_rel_file(project_root, out_dir, rel) for rel in resolved_docs]
    copied_dirs = [_copy_rel_dir(project_root, out_dir, rel) for rel in resolved_directories]

    frontend_index = out_dir / "Netsphere_Free_Frontend" / "dist" / "index.html"
    if not frontend_index.exists():
        raise RuntimeError("Frontend build output is missing from installer stage.")

    runtime_manifest = _bundle_python_runtime(out_dir, Path(python_home or sys.base_prefix))

    manifest = {
        "generated_at": _now_iso(),
        "edition": "preview",
        "distribution_model": "installed_collector",
        "product_name": "NetSphere",
        "included_files": copied_files,
        "included_docs": copied_docs,
        "included_directories": copied_dirs,
        "runtime": runtime_manifest,
        "runtime_defaults": {
            "deployment_role": "collector_installed",
            "upload_target_mode": "remote_only",
            "local_embedded_execution": True,
            "disable_integrated_servers": True,
        },
    }

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "README.txt").write_text(
        "\n".join(
            [
                "NetSphere Free Installer Stage",
                "==============================",
                "",
                "This stage is meant to be wrapped by the NetSphere Free Windows installer.",
                "Do not distribute this folder directly to end users.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return out_dir, manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Build NetSphere preview installer stage.")
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "dist" / "preview-installer-stage"))
    parser.add_argument("--python-home", default="")
    args = parser.parse_args()

    out_dir, manifest = build_preview_installer_stage(
        out_dir=Path(args.out_dir),
        python_home=Path(args.python_home) if args.python_home else None,
    )
    print(
        json.dumps(
            {
                "out_dir": str(out_dir),
                "python": manifest["runtime"]["bundled_executable"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
