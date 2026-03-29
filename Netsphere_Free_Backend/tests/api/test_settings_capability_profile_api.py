import json

from app.models.settings import SystemSetting


def test_update_settings_rejects_invalid_capability_profile_json(client, admin_user_token):
    res = client.put(
        "/api/v1/settings/general",
        json={"settings": {"capability_profile_json": "{invalid-json"}},
        headers=admin_user_token,
    )
    assert res.status_code == 400
    body = res.json()
    assert "capability_profile_json" in json.dumps(body, ensure_ascii=False)


def test_update_settings_accepts_and_normalizes_capability_profile_json(client, admin_user_token, db):
    profile = {
        "default": {
            "allowed_protocols": ["ssh", "SNMP", "invalid_protocol"],
            "auto_reflection": {"approval": True, "sync": False},
            "read_only": False,
        },
        "sites": {
            "10": {
                "read_only": True,
                "auto_reflection": {"topology": True},
            }
        },
        "device_types": {
            "Cisco_IOS": {
                "allowed_protocols": ["snmp"],
            }
        },
    }
    res = client.put(
        "/api/v1/settings/general",
        json={"settings": {"capability_profile_json": profile}},
        headers=admin_user_token,
    )
    assert res.status_code == 200

    setting = db.query(SystemSetting).filter(SystemSetting.key == "capability_profile_json").first()
    assert setting is not None
    saved = json.loads(setting.value)

    assert saved["default"]["allowed_protocols"] == ["ssh", "snmp"]
    assert saved["default"]["auto_reflection"]["approval"] is True
    assert saved["default"]["auto_reflection"]["sync"] is False
    assert saved["default"]["read_only"] is False
    assert saved["sites"]["10"]["read_only"] is True
    assert saved["sites"]["10"]["auto_reflection"]["topology"] is True
    assert "cisco_ios" in saved["device_types"]
    assert saved["device_types"]["cisco_ios"]["allowed_protocols"] == ["snmp"]


def test_capability_profile_endpoints_return_profile_and_effective_policy(client, admin_user_token):
    profile = {
        "default": {
            "allowed_protocols": ["snmp", "ssh"],
            "auto_reflection": {"approval": True, "topology": True, "sync": False},
            "read_only": False,
        },
        "sites": {"10": {"read_only": True}},
        "device_types": {"cisco_ios": {"allowed_protocols": ["snmp"]}},
    }
    save_res = client.put(
        "/api/v1/settings/general",
        json={"settings": {"capability_profile_json": profile}},
        headers=admin_user_token,
    )
    assert save_res.status_code == 200

    profile_res = client.get("/api/v1/settings/capability-profile", headers=admin_user_token)
    assert profile_res.status_code == 200
    profile_body = profile_res.json()
    profile_payload = profile_body.get("data") if isinstance(profile_body, dict) and "data" in profile_body else profile_body
    assert profile_payload["default"]["allowed_protocols"] == ["snmp", "ssh"]
    assert profile_payload["sites"]["10"]["read_only"] is True

    effective_res = client.get(
        "/api/v1/settings/capability-profile/effective",
        params={"site_id": 10, "device_type": "cisco_ios"},
        headers=admin_user_token,
    )
    assert effective_res.status_code == 200
    effective_body = effective_res.json()
    effective = effective_body.get("data") if isinstance(effective_body, dict) and "data" in effective_body else effective_body
    assert effective["allowed_protocols"] == ["snmp"]
    assert effective["read_only"] is True
    assert effective["auto_reflection"]["sync"] is False


def test_update_settings_ignores_masked_secret_values(client, admin_user_token, db):
    secret_rows = {
        "smtp_password": "smtp-real-password",
        "default_ssh_password": "ssh-real-password",
        "default_enable_password": "enable-real-password",
        "audit_hmac_key": "audit-real-key",
        "webhook_secret": "webhook-real-secret",
        "webhook_auth_token": "webhook-real-token",
    }
    for key, value in secret_rows.items():
        db.add(SystemSetting(key=key, value=value, description="t", category="General"))
    db.commit()

    res = client.put(
        "/api/v1/settings/general",
        json={
            "settings": {
                "smtp_password": "********",
                "default_ssh_password": "********",
                "default_enable_password": "********",
                "audit_hmac_key": "********",
                "webhook_secret": "********",
                "webhook_auth_token": "********",
            }
        },
        headers=admin_user_token,
    )
    assert res.status_code == 200

    db.expire_all()
    for key, expected in secret_rows.items():
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        assert row is not None
        assert row.value == expected


def test_test_webhook_connector_returns_delivery_result(client, admin_user_token, monkeypatch):
    from app.services import webhook_service as webhook_mod

    monkeypatch.setattr(
        webhook_mod.WebhookService,
        "send",
        staticmethod(
            lambda _db, **_kwargs: {
                "success": True,
                "mode": "jira",
                "status_code": 202,
                "attempts": 2,
                "delivery_id": "delivery-test-1",
            }
        ),
    )

    res = client.post(
        "/api/v1/settings/test-webhook-connector",
        json={
            "event_type": "test",
            "title": "connector-test",
            "message": "connector-test-message",
        },
        headers=admin_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert payload.get("message") == "Webhook sent successfully"
    result = payload.get("result") or {}
    assert result.get("mode") == "jira"
    assert int(result.get("status_code")) == 202
    assert int(result.get("attempts")) == 2
    assert str(result.get("delivery_id")) == "delivery-test-1"
