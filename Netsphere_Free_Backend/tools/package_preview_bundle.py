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


def _copy_docs(out_dir: Path, docs: list[str]) -> list[str]:
    copied: list[str] = []
    for rel in docs:
        src = (PROJECT_ROOT / rel).resolve()
        if not src.exists():
            continue
        _copy_file(src, out_dir / rel)
        copied.append(rel)
    return copied


def build_manifest(*, copied_docs: list[str]) -> dict:
    return {
        "generated_at": _now_iso(),
        "edition": "preview",
        "product_name": "NetSphere",
        "positioning": "experience-first free intake edition for discovery, topology, connected NMS, and masked parser contribution",
        "included_docs": list(copied_docs),
        "defaults": {
            "raw_original_persistence": False,
            "consent_required": True,
            "device_capture_allowlist_only": True,
            "high_risk_mutations_blocked": True,
        },
    }


def package_preview_bundle(*, out_dir: Path, zip_name: str, docs: list[str]) -> tuple[Path, Path]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    copied_docs = _copy_docs(out_dir, docs)
    manifest = build_manifest(copied_docs=copied_docs)
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    readme_path = out_dir / "README.txt"
    readme_path.write_text(
        "\n".join(
            [
                "NetSphere Free Edition Package",
                "=============================",
                "",
                "This package is intended for experience-first free intake distribution.",
                "",
                "Included docs:",
                *[f"- {item}" for item in copied_docs],
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
    parser = argparse.ArgumentParser(description="Package NetSphere preview edition docs bundle.")
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "dist" / "preview-edition-package"))
    parser.add_argument("--zip-name", default="preview-edition-package.zip")
    args = parser.parse_args()

    out_dir, zip_path = package_preview_bundle(
        out_dir=Path(args.out_dir),
        zip_name=str(args.zip_name),
        docs=list(DEFAULT_DOCS),
    )
    print(json.dumps({"out_dir": str(out_dir), "zip_path": str(zip_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
