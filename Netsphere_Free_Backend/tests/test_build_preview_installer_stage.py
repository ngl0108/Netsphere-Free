import json

from tools import build_preview_installer_stage as tool


def test_build_preview_installer_stage_bundles_runtime_and_frontend(tmp_path, monkeypatch):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    for name in [
        "README.md",
        "USER_GUIDE.md",
        "FEATURE_BROCHURE.md",
        "PREVIEW_BROCHURE.md",
        "PREVIEW_EDITION_PLAN.md",
        "PREVIEW_COLLECTOR_ARCHITECTURE.md",
        "PREVIEW_INSTALLER_COLLECTOR_PLAN.md",
        "PREVIEW_EXPERIENCE_POLICY.md",
        "PREVIEW_CONTRIBUTOR_GUIDE.md",
        "PREVIEW_INSTALL_TEST_CHECKLIST.md",
        "PREVIEW_RELEASE_CHECKLIST.md",
    ]:
        (docs_dir / name).write_text(f"# {name}\n", encoding="utf-8")

    (tmp_path / ".env.preview.example").write_text("NETSPHERE_EDITION=preview\n", encoding="utf-8")
    (tmp_path / "Netsphere_Free_Backend" / "app").mkdir(parents=True, exist_ok=True)
    (tmp_path / "Netsphere_Free_Backend" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "Netsphere_Free_Backend" / "app" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "Netsphere_Free_Frontend" / "dist").mkdir(parents=True, exist_ok=True)
    (tmp_path / "Netsphere_Free_Frontend" / "dist" / "index.html").write_text("<html></html>\n", encoding="utf-8")
    (tmp_path / "preview-installer").mkdir(parents=True, exist_ok=True)
    for name in [
        "bootstrap-install.ps1",
        "bootstrap-install.cmd",
        "install-preview-collector.ps1",
        "launch-preview-collector.cmd",
        "open-preview-ui.ps1",
        "open-preview-ui.cmd",
        "start-preview-collector.ps1",
        "start-preview-collector.cmd",
        "stop-preview-collector.ps1",
        "stop-preview-collector.cmd",
        "uninstall-preview-collector.ps1",
        "uninstall-preview-collector.cmd",
    ]:
        (tmp_path / "preview-installer" / name).write_text("echo ok\n", encoding="utf-8")

    fake_python = tmp_path / "python-home"
    (fake_python / "DLLs").mkdir(parents=True, exist_ok=True)
    (fake_python / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)
    for name in [
        "python.exe",
        "pythonw.exe",
        "python3.dll",
        "python311.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "LICENSE.txt",
    ]:
        (fake_python / name).write_text("runtime\n", encoding="utf-8")
    (fake_python / "Lib" / "site.py").write_text("print('site')\n", encoding="utf-8")

    monkeypatch.setattr(tool, "PROJECT_ROOT", tmp_path)

    out_dir, manifest = tool.build_preview_installer_stage(
        out_dir=tmp_path / "dist" / "preview-installer-stage",
        project_root=tmp_path,
        python_home=fake_python,
    )

    manifest_path = out_dir / "manifest.json"
    parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert parsed["distribution_model"] == "installed_collector"
    assert parsed["runtime_defaults"]["disable_integrated_servers"] is True
    assert (out_dir / "Netsphere_Free_Frontend" / "dist" / "index.html").exists()
    assert (out_dir / "runtime" / "python" / "python.exe").exists()
    assert manifest["runtime"]["bundled_executable"].endswith("python.exe")
