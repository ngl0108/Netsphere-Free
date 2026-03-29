import io
import json
from zipfile import ZipFile

from tools import package_preview_bundle as tool


def test_package_preview_bundle_writes_manifest_and_zip(tmp_path, monkeypatch):
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

    monkeypatch.setattr(tool, "PROJECT_ROOT", tmp_path)

    out_dir, zip_path = tool.package_preview_bundle(
        out_dir=tmp_path / "dist" / "preview-edition-package",
        zip_name="preview-edition-package.zip",
        docs=list(tool.DEFAULT_DOCS),
    )

    manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["edition"] == "preview"
    assert manifest["defaults"]["raw_original_persistence"] is False
    assert zip_path.exists()

    with ZipFile(io.BytesIO(zip_path.read_bytes()), "r") as zf:
        names = set(zf.namelist())
    assert "manifest.json" in names
    for rel_path in tool.DEFAULT_DOCS:
        assert rel_path in names
