import io
import json
from zipfile import ZipFile

from tools import package_preview_installer_bundle as tool


def test_package_preview_installer_bundle_writes_manifest_and_zip(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "README.md").write_text("# Index\n", encoding="utf-8")
    (docs_dir / "USER_GUIDE.md").write_text("# Guide\n", encoding="utf-8")
    (docs_dir / "FEATURE_BROCHURE.md").write_text("# Brochure\n", encoding="utf-8")
    (docs_dir / "PREVIEW_BROCHURE.md").write_text("# Preview Brochure\n", encoding="utf-8")
    (docs_dir / "PREVIEW_EDITION_PLAN.md").write_text("# Preview Plan\n", encoding="utf-8")
    (docs_dir / "PREVIEW_COLLECTOR_ARCHITECTURE.md").write_text("# Preview Collector Architecture\n", encoding="utf-8")
    (docs_dir / "PREVIEW_INSTALLER_COLLECTOR_PLAN.md").write_text("# Preview Installer Collector Plan\n", encoding="utf-8")
    (docs_dir / "PREVIEW_EXPERIENCE_POLICY.md").write_text("# Preview Experience Policy\n", encoding="utf-8")
    (docs_dir / "PREVIEW_CONTRIBUTOR_GUIDE.md").write_text("# Preview Contributor Guide\n", encoding="utf-8")
    (docs_dir / "PREVIEW_INSTALL_TEST_CHECKLIST.md").write_text("# Preview Install Test Checklist\n", encoding="utf-8")
    (docs_dir / "PREVIEW_RELEASE_CHECKLIST.md").write_text("# Preview Checklist\n", encoding="utf-8")

    (tmp_path / ".env.preview.example").write_text("NETSPHERE_EDITION=preview\n", encoding="utf-8")
    (tmp_path / "preview-installer").mkdir(parents=True, exist_ok=True)
    (tmp_path / "preview-installer" / "bootstrap-install.ps1").write_text("Write-Host bootstrap\n", encoding="utf-8")
    (tmp_path / "preview-installer" / "bootstrap-install.cmd").write_text("@echo off\n", encoding="utf-8")
    (tmp_path / "preview-installer" / "install-preview-collector.ps1").write_text("Write-Host install\n", encoding="utf-8")
    (tmp_path / "preview-installer" / "launch-preview-collector.cmd").write_text("@echo off\n", encoding="utf-8")
    (tmp_path / "preview-installer" / "open-preview-ui.ps1").write_text("Write-Host open\n", encoding="utf-8")
    (tmp_path / "preview-installer" / "open-preview-ui.cmd").write_text("@echo off\n", encoding="utf-8")
    (tmp_path / "preview-installer" / "start-preview-collector.ps1").write_text("Write-Host start\n", encoding="utf-8")
    (tmp_path / "preview-installer" / "start-preview-collector.cmd").write_text("@echo off\n", encoding="utf-8")
    (tmp_path / "preview-installer" / "stop-preview-collector.ps1").write_text("Write-Host stop\n", encoding="utf-8")
    (tmp_path / "preview-installer" / "stop-preview-collector.cmd").write_text("@echo off\n", encoding="utf-8")
    (tmp_path / "preview-installer" / "uninstall-preview-collector.ps1").write_text("Write-Host uninstall\n", encoding="utf-8")
    (tmp_path / "preview-installer" / "uninstall-preview-collector.cmd").write_text("@echo off\n", encoding="utf-8")

    monkeypatch.setattr(tool, "PROJECT_ROOT", tmp_path)

    out_dir, zip_path = tool.package_preview_installer_bundle(
        out_dir=tmp_path / "dist" / "preview-installer-package",
        zip_name="preview-installer-package.zip",
        files=list(tool.DEFAULT_FILES),
        docs=list(tool.DEFAULT_DOCS),
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["distribution_model"] == "installed_collector"
    assert manifest["runtime_defaults"]["local_embedded_execution"] is True
    assert zip_path.exists()

    with ZipFile(io.BytesIO(zip_path.read_bytes()), "r") as zf:
        names = set(zf.namelist())
    assert ".env.preview.example" in names
    assert "preview-installer/bootstrap-install.ps1" in names
    assert "preview-installer/bootstrap-install.cmd" in names
    assert "preview-installer/install-preview-collector.ps1" in names
    assert "preview-installer/launch-preview-collector.cmd" in names
    assert "preview-installer/open-preview-ui.ps1" in names
    assert "preview-installer/open-preview-ui.cmd" in names
    assert "preview-installer/start-preview-collector.ps1" in names
    assert "preview-installer/start-preview-collector.cmd" in names
    assert "preview-installer/stop-preview-collector.ps1" in names
    assert "preview-installer/stop-preview-collector.cmd" in names
    assert "preview-installer/uninstall-preview-collector.ps1" in names
    assert "preview-installer/uninstall-preview-collector.cmd" in names
    for rel_path in tool.DEFAULT_DOCS:
        assert rel_path in names
