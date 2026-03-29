from app.services.license_service import LicenseService


def _payload(res):
    body = res.json()
    if isinstance(body, dict) and body.get("success") is True and isinstance(body.get("data"), dict):
        return body["data"]
    return body


def test_license_revocations_list_api(client, admin_user_token, monkeypatch):
    monkeypatch.setattr(
        LicenseService,
        "list_revocations",
        staticmethod(lambda: {"revocation_file": "x.json", "count": 1, "revoked": [{"jti": "j-1"}]}),
    )
    res = client.get("/api/v1/license/revocations", headers=admin_user_token)
    assert res.status_code == 200
    body = _payload(res)
    assert body.get("count") == 1


def test_license_revoke_installed_api(client, admin_user_token, monkeypatch):
    monkeypatch.setattr(
        LicenseService,
        "revoke_installed_license",
        staticmethod(lambda db, reason, revoked_by: {"ok": True, "reason": reason, "revoked_by": revoked_by}),
    )
    res = client.post("/api/v1/license/revoke", json={"installed_license": True, "reason": "manual_revoke"}, headers=admin_user_token)
    assert res.status_code == 200
    body = _payload(res)
    assert body.get("ok") is True


def test_license_revoke_jti_api(client, admin_user_token, monkeypatch):
    monkeypatch.setattr(
        LicenseService,
        "revoke_jti",
        staticmethod(lambda jti, reason, revoked_by: {"ok": True, "jti": jti, "reason": reason, "revoked_by": revoked_by}),
    )
    res = client.post(
        "/api/v1/license/revoke",
        json={"installed_license": False, "jti": "j-22", "reason": "refund"},
        headers=admin_user_token,
    )
    assert res.status_code == 200
    body = _payload(res)
    assert body.get("jti") == "j-22"


def test_license_unrevoke_api(client, admin_user_token, monkeypatch):
    monkeypatch.setattr(
        LicenseService,
        "unrevoke_jti",
        staticmethod(lambda jti: {"ok": True, "jti": jti, "removed": True}),
    )
    res = client.delete("/api/v1/license/revoke/j-99", headers=admin_user_token)
    assert res.status_code == 200
    body = _payload(res)
    assert body.get("removed") is True
