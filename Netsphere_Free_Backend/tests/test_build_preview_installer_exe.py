from pathlib import Path

from tools import build_preview_installer_exe as tool


def test_build_iexpress_sed_text_references_payload_and_bootstrap(tmp_path):
    sed = tool.build_iexpress_sed_text(
        build_root=tmp_path,
        target_exe=tmp_path / "NetSphere-Free-Setup.exe",
    )

    assert "AppLaunched=bootstrap-install.cmd" in sed
    assert 'FILE0="payload.zip"' in sed
    assert 'FILE1="bootstrap-install.ps1"' in sed
    assert 'FILE2="bootstrap-install.cmd"' in sed
    assert "SourceFiles0=" in sed


def test_build_payload_zip_archives_stage_contents(tmp_path):
    stage_dir = tmp_path / "stage"
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
    (stage_dir / "preview-installer").mkdir(parents=True, exist_ok=True)
    (stage_dir / "preview-installer" / "launch-preview-collector.cmd").write_text("echo ok\n", encoding="utf-8")

    payload = tool.build_payload_zip(stage_dir=stage_dir, payload_zip=tmp_path / "payload.zip")

    assert payload.exists()
