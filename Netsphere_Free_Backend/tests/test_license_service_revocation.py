from datetime import datetime, timedelta, timezone

import jwt

from app.core.license import license_verifier
from app.services.license_service import LicenseService


def test_revoke_and_unrevoke_jti_persist_file(tmp_path, monkeypatch):
    revocation_file = tmp_path / "license_revocations.json"
    monkeypatch.setattr(license_verifier, "revocation_list_path", str(revocation_file))

    out = LicenseService.revoke_jti("jti-1", reason="contract_terminated", revoked_by="qa")
    assert out["ok"] is True
    assert out["revoked"]["jti"] == "jti-1"
    assert revocation_file.exists()

    listed = LicenseService.list_revocations()
    assert listed["count"] == 1
    assert listed["revoked"][0]["reason"] == "contract_terminated"

    removed = LicenseService.unrevoke_jti("jti-1")
    assert removed["removed"] is True
    listed2 = LicenseService.list_revocations()
    assert listed2["count"] == 0


def test_revoke_installed_license_uses_token_jti(db, tmp_path, monkeypatch):
    revocation_file = tmp_path / "license_revocations.json"
    monkeypatch.setattr(license_verifier, "revocation_list_path", str(revocation_file))

    exp = datetime.now(timezone.utc) + timedelta(days=30)
    token = jwt.encode({"sub": "ACME", "jti": "installed-jti", "exp": int(exp.timestamp())}, "secret", algorithm="HS256")

    monkeypatch.setattr(LicenseService, "get_installed_token", staticmethod(lambda _db: token))
    monkeypatch.setattr(LicenseService, "get_status", staticmethod(lambda _db: {"status": "ok"}))

    out = LicenseService.revoke_installed_license(db, reason="customer_refund", revoked_by="admin")
    assert out["ok"] is True
    assert out["revoked"]["jti"] == "installed-jti"
    assert out["license_status"]["status"] == "ok"
