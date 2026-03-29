from app.models.settings import SystemSetting


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_preview_initial_admin_status_requires_setup_for_new_preview_install(client, db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="collector_installed", description="", category="preview"),
        ]
    )
    db.commit()

    res = client.get("/api/v1/auth/bootstrap/status")

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["enabled"] is True
    assert payload["initial_admin_required"] is True
    assert payload["deployment_role"] == "collector_installed"


def test_preview_initial_admin_create_provisions_first_admin_once(client, db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="collector_installed", description="", category="preview"),
        ]
    )
    db.commit()

    res = client.post(
        "/api/v1/auth/bootstrap/initial-admin",
        json={
            "username": "admin",
            "password": "Password1!!@",
            "full_name": "Preview Administrator",
            "email": "admin@example.com",
        },
    )

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["username"] == "admin"
    assert payload["role"] == "admin"
    assert payload["must_change_password"] is False
    assert payload["eula_accepted"] is False

    status_res = client.get("/api/v1/auth/bootstrap/status")
    status_payload = _unwrap(status_res.json())
    assert status_payload["initial_admin_required"] is False

    second = client.post(
        "/api/v1/auth/bootstrap/initial-admin",
        json={"username": "admin2", "password": "Password1!!@"},
    )
    assert second.status_code == 409


def test_preview_initial_admin_create_rejects_when_preview_not_enabled(client, db):
    db.add(SystemSetting(key="product_edition", value="enterprise", description="", category="preview"))
    db.commit()

    res = client.post(
        "/api/v1/auth/bootstrap/initial-admin",
        json={"username": "admin", "password": "Password1!!@"},
    )

    assert res.status_code == 403
