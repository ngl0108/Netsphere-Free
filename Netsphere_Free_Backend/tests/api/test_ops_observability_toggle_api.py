from __future__ import annotations

from app.api.v1.endpoints import ops as ops_ep
from app.models.settings import SystemSetting


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_ops_observability_toggle_works_in_logical_mode_when_docker_socket_is_unavailable(
    client,
    admin_user_token,
    db,
    monkeypatch,
):
    monkeypatch.setenv("ENABLE_OBSERVABILITY_TOGGLE", "1")
    monkeypatch.setenv("OBSERVABILITY_DEFAULT_ENABLED", "0")
    monkeypatch.setattr(ops_ep, "_docker_runtime_available", lambda: False)

    row = db.query(SystemSetting).filter(SystemSetting.key == ops_ep.OBSERVABILITY_RUNTIME_SETTING_KEY).first()
    if row:
        db.delete(row)
        db.commit()

    get_before = client.get("/api/v1/ops/observability", headers=admin_user_token)
    assert get_before.status_code == 200
    before_payload = _unwrap(get_before.json())
    assert bool(before_payload.get("enabled")) is False
    assert str(before_payload.get("control_mode") or "") == "logical"

    set_on = client.post(
        "/api/v1/ops/observability",
        json={"enabled": True},
        headers=admin_user_token,
    )
    assert set_on.status_code == 200
    set_on_payload = _unwrap(set_on.json())
    assert bool(set_on_payload.get("enabled")) is True
    assert str(set_on_payload.get("control_mode") or "") == "logical"

    get_after = client.get("/api/v1/ops/observability", headers=admin_user_token)
    assert get_after.status_code == 200
    after_payload = _unwrap(get_after.json())
    assert bool(after_payload.get("enabled")) is True
    assert str(after_payload.get("control_mode") or "") == "logical"

    stored = db.query(SystemSetting).filter(SystemSetting.key == ops_ep.OBSERVABILITY_RUNTIME_SETTING_KEY).first()
    assert stored is not None
    assert str(stored.value or "").strip().lower() == "true"


def test_preview_observability_summary_is_available_without_pro_license(client, operator_user_token, db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="collector_installed", description="", category="preview"),
        ]
    )
    db.commit()

    res = client.get("/api/v1/observability/summary", headers=operator_user_token)

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert "counts" in payload
