from app.db.encrypted_types import EncryptedString


def test_encrypted_string_roundtrip():
    t = EncryptedString()
    stored = t.process_bind_param("secret123", None)
    assert stored.startswith("enc:")
    plain = t.process_result_value(stored, None)
    assert plain == "secret123"


def test_encrypted_string_plaintext_backcompat():
    t = EncryptedString()
    plain = t.process_result_value("legacy_plain", None)
    assert plain == "legacy_plain"

