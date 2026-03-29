from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "test-data" / "synthetic"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def test_synthetic_fixture_manifest_integrity():
    manifest_path = FIXTURE_ROOT / "manifest.json"
    assert manifest_path.exists(), f"Missing fixture manifest: {manifest_path}"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest.get("files") or []
    assert files, "Fixture manifest must contain file hashes"

    for row in files:
        rel = Path(str(row.get("path") or "").replace("/", "\\"))
        expected_hash = str(row.get("sha256") or "").strip().lower()
        assert expected_hash, f"Missing sha256 in manifest entry: {row}"
        target = REPO_ROOT / rel
        assert target.exists(), f"Missing fixture file listed in manifest: {target}"
        actual_hash = _sha256(target).lower()
        assert actual_hash == expected_hash, f"Fixture hash mismatch for {target}"


def test_required_scenario_files_exist():
    for name in ("normal", "large_scale", "failure", "security_incident", "rollback_wave", "hybrid_cloud", "wireless_edge"):
        target = FIXTURE_ROOT / "scenarios" / f"{name}.json"
        assert target.exists(), f"Missing synthetic scenario: {target}"

    for protocol in ("snmp", "ssh", "gnmi"):
        target = FIXTURE_ROOT / "digital-twin" / f"{protocol}.json"
        assert target.exists(), f"Missing digital twin protocol fixture: {target}"
