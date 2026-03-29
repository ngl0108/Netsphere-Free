from app.schemas.cloud import mask_credentials, normalize_and_validate_credentials


def test_normalize_aws_access_key_auth():
    out = normalize_and_validate_credentials(
        "aws",
        {
            "region": "ap-northeast-2",
            "access_key": "AKIA_TEST",
            "secret_key": "SECRET_TEST",
        },
    )
    assert out["auth_type"] == "access_key"
    assert out["access_key"] == "AKIA_TEST"


def test_normalize_aws_assume_role_requires_role_arn():
    try:
        normalize_and_validate_credentials(
            "aws",
            {
                "auth_type": "assume_role",
                "external_id": "ext-1",
            },
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert "role_arn" in str(e)


def test_normalize_aws_assume_role_source_keys_must_be_pair():
    try:
        normalize_and_validate_credentials(
            "aws",
            {
                "auth_type": "assume_role",
                "role_arn": "arn:aws:iam::123456789012:role/TestRole",
                "source_access_key": "AKIA_TEST",
            },
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert "provided together" in str(e)


def test_mask_credentials_masks_assume_role_sensitive_fields():
    masked = mask_credentials(
        "aws",
        {
            "auth_type": "assume_role",
            "role_arn": "arn:aws:iam::123456789012:role/TestRole",
            "external_id": "ext-123",
            "source_access_key": "AKIA_TEST",
            "source_secret_key": "SECRET_TEST",
        },
    )
    assert masked["role_arn"] == "arn:aws:iam::123456789012:role/TestRole"
    assert masked["external_id"] == "********"
    assert masked["source_access_key"] == "********"
    assert masked["source_secret_key"] == "********"
