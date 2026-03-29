from app.services.cloud_credentials_service import (
    decrypt_credentials_for_runtime,
    encrypt_credentials_for_storage,
)


def test_encrypt_and_decrypt_cloud_credentials_round_trip():
    raw = {
        "auth_type": "assume_role",
        "region": "ap-northeast-2",
        "role_arn": "arn:aws:iam::123456789012:role/NetSphereReadOnly",
        "external_id": "ext-123",
        "source_access_key": "AKIA_TEST_SOURCE",
        "source_secret_key": "SRC_SECRET",
    }

    stored = encrypt_credentials_for_storage("aws", raw)
    assert stored["role_arn"] == raw["role_arn"]
    assert isinstance(stored["external_id"], str) and stored["external_id"].startswith("enc:")
    assert isinstance(stored["source_access_key"], str) and stored["source_access_key"].startswith("enc:")
    assert isinstance(stored["source_secret_key"], str) and stored["source_secret_key"].startswith("enc:")

    decrypted = decrypt_credentials_for_runtime("aws", stored)
    assert decrypted == raw


def test_non_sensitive_fields_are_not_encrypted():
    raw = {
        "tenant_id": "tenant-a",
        "subscription_id": "sub-a",
        "client_id": "client-a",
        "client_secret": "secret-a",
    }

    stored = encrypt_credentials_for_storage("azure", raw)
    assert stored["tenant_id"] == raw["tenant_id"]
    assert stored["subscription_id"] == raw["subscription_id"]
    assert stored["client_id"] == raw["client_id"]
    assert isinstance(stored["client_secret"], str) and stored["client_secret"].startswith("enc:")
