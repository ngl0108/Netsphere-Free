#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

try:
    from tools.build_preview_installer_stage import PROJECT_ROOT, build_preview_installer_stage
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_preview_installer_stage import PROJECT_ROOT, build_preview_installer_stage


BACKEND_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_FILES = [
    "preview-installer/bootstrap-install.ps1",
    "preview-installer/bootstrap-install.cmd",
]


def build_payload_zip(*, stage_dir: Path, payload_zip: Path) -> Path:
    payload_zip.parent.mkdir(parents=True, exist_ok=True)
    if payload_zip.exists():
        payload_zip.unlink()
    with ZipFile(payload_zip, "w", compression=ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(stage_dir, topdown=True):
            root_path = Path(root)
            existing_dirs: list[str] = []
            for dirname in dirs:
                try:
                    candidate = root_path / dirname
                    if candidate.exists():
                        existing_dirs.append(dirname)
                except OSError:
                    continue
            dirs[:] = existing_dirs

            for filename in files:
                file_path = root_path / filename
                try:
                    if not file_path.is_file():
                        continue
                    zf.write(file_path, file_path.relative_to(stage_dir).as_posix())
                except (FileNotFoundError, PermissionError, OSError):
                    continue
    return payload_zip


def build_iexpress_sed_text(*, build_root: Path, target_exe: Path) -> str:
    source_root = str(build_root.resolve())
    target_name = str(target_exe.resolve())
    return "\n".join(
        [
            "[Version]",
            "Class=IEXPRESS",
            "SEDVersion=3",
            "[Options]",
            "PackagePurpose=InstallApp",
            "ShowInstallProgramWindow=1",
            "HideExtractAnimation=1",
            "UseLongFileName=1",
            "InsideCompressed=1",
            "CAB_FixedSize=0",
            "CAB_ResvCodeSigning=0",
            "RebootMode=N",
            "InstallPrompt=",
            "DisplayLicense=",
            "FinishMessage=NetSphere Free setup completed.",
            f"TargetName={target_name}",
            "FriendlyName=NetSphere Free Setup",
            "AppLaunched=bootstrap-install.cmd",
            "PostInstallCmd=<None>",
            "AdminQuietInstCmd=bootstrap-install.cmd /quiet",
            "UserQuietInstCmd=bootstrap-install.cmd /quiet",
            "SourceFiles=SourceFiles",
            "[SourceFiles]",
            f"SourceFiles0={source_root}\\",
            "[SourceFiles0]",
            "%FILE0%=",
            "%FILE1%=",
            "%FILE2%=",
            "[Strings]",
            'FILE0="payload.zip"',
            'FILE1="bootstrap-install.ps1"',
            'FILE2="bootstrap-install.cmd"',
            "",
        ]
    )


def build_preview_installer_exe(
    *,
    stage_dir: Path,
    out_dir: Path,
    exe_name: str = "NetSphere-Free-Setup.exe",
) -> tuple[Path, Path, Path]:
    iexpress = shutil.which("iexpress.exe")
    if not iexpress:
        raise RuntimeError("IExpress is not available on this Windows host.")

    out_dir.mkdir(parents=True, exist_ok=True)
    final_exe = out_dir / exe_name

    with tempfile.TemporaryDirectory(prefix="netsphere-preview-installer-") as temp_root:
        build_root = Path(temp_root)
        payload_zip = build_payload_zip(stage_dir=stage_dir, payload_zip=build_root / "payload.zip")

        for rel_path in BOOTSTRAP_FILES:
            src = PROJECT_ROOT / rel_path
            if not src.exists():
                raise FileNotFoundError(f"Missing bootstrap file: {src}")
            shutil.copy2(src, build_root / src.name)

        temp_target = build_root / exe_name
        sed_path = build_root / "preview-installer.sed"
        sed_path.write_text(
            build_iexpress_sed_text(build_root=build_root, target_exe=temp_target),
            encoding="utf-8",
        )

        completed = subprocess.run(
            [iexpress, "/N", str(sed_path)],
            cwd=str(build_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0 or not temp_target.exists():
            raise RuntimeError(
                "IExpress build failed.\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )

        shutil.copy2(temp_target, final_exe)
        return final_exe, payload_zip, sed_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build NetSphere preview installer executable.")
    parser.add_argument("--stage-dir", default=str(PROJECT_ROOT / "dist" / "preview-installer-stage"))
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / "dist" / "preview-installer-exe"))
    parser.add_argument("--exe-name", default="NetSphere-Free-Setup.exe")
    parser.add_argument("--rebuild-stage", action="store_true")
    parser.add_argument("--python-home", default="")
    args = parser.parse_args()

    stage_dir = Path(args.stage_dir)
    if args.rebuild_stage or not stage_dir.exists():
        build_preview_installer_stage(
            out_dir=stage_dir,
            python_home=Path(args.python_home) if args.python_home else None,
        )

    final_exe, payload_zip, sed_path = build_preview_installer_exe(
        stage_dir=stage_dir,
        out_dir=Path(args.out_dir),
        exe_name=args.exe_name,
    )
    print(
        json.dumps(
            {
                "stage_dir": str(stage_dir),
                "installer_exe": str(final_exe),
                "payload_zip": str(payload_zip),
                "sed_path": str(sed_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
