from datetime import datetime, timedelta, timezone

from app.core.license import LicenseSchema
from app.models.license_state import LicenseState
from app.services.license_service import LicenseService


def _valid_license() -> LicenseSchema:
    return LicenseSchema(
        customer="ACME",
        expiration=datetime.now(timezone.utc) + timedelta(days=30),
        max_devices=500,
        features=["all"],
        is_valid=True,
        status="Active",
    )


def test_install_encrypts_license_token_at_rest(db, monkeypatch):
    monkeypatch.setattr(LicenseService, "verify_token", staticmethod(lambda token: _valid_license()))

    LicenseService.install(db, "header.payload.signature")
    row = db.query(LicenseState).filter(LicenseState.id == 1).first()

    assert row is not None
    assert isinstance(row.license_jwt, str)
    assert row.license_jwt.startswith("enc:")
    assert LicenseService.get_installed_token(db) == "header.payload.signature"


def test_plaintext_token_is_migrated_to_encrypted_storage_on_read(db):
    row = LicenseState(id=1, license_jwt="plain.jwt.token")
    db.add(row)
    db.commit()

    plain = LicenseService.get_installed_token(db)
    db.refresh(row)

    assert plain == "plain.jwt.token"
    assert isinstance(row.license_jwt, str)
    assert row.license_jwt.startswith("enc:")
