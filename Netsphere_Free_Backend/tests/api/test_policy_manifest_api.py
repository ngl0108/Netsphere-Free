from app.models.settings import SystemSetting
from app.services.license_service import LicenseService


def _enable_preview(db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="collector_installed", description="", category="preview"),
        ]
    )
    db.commit()


def test_policy_manifest_hides_pro_only_surfaces_in_free_preview(client, operator_user_token, db):
    _enable_preview(db)

    res = client.get("/api/v1/ops/policy-manifest", headers=operator_user_token)

    assert res.status_code == 200
    payload = res.json()["data"]
    assert payload["preview_enabled"] is True
    assert payload["edition"] == "free"
    assert payload["surfaces"]["operations_home"]["navigable"] is True
    assert payload["surfaces"]["discovery"]["navigable"] is True
    assert payload["surfaces"]["topology"]["navigable"] is True
    assert payload["surfaces"]["diagnosis"]["navigable"] is True
    assert payload["surfaces"]["observability"]["navigable"] is True
    assert payload["surfaces"]["config"]["visible"] is False
    assert payload["surfaces"]["config"]["blocked_code"] == "preview_blocked"
    assert payload["surfaces"]["config"]["blocked_title_key"] == "policy_block_title_preview"
    assert payload["surfaces"]["config"]["blocked_action_path"] == "/edition/compare"
    assert payload["surfaces"]["config"]["blocked_action_desc_key"] == "policy_block_action_compare_desc"
    assert payload["surfaces"]["approval"]["visible"] is False
    assert payload["surfaces"]["preview_contribute"]["visible"] is False
    assert any(section["key"] == "operations" for section in payload["navigation"]["sidebar_sections"])
    assert any(section["key"] == "observe" for section in payload["navigation"]["sidebar_sections"])
    assert all(section["key"] != "administration" for section in payload["navigation"]["sidebar_sections"])
    assert any(workspace["key"] == "discover" for workspace in payload["workspaces"])


def test_policy_manifest_exposes_pro_surfaces_for_admin_when_license_allows(client, admin_user_token, db, monkeypatch):
    monkeypatch.setattr(
        LicenseService,
        "get_status",
        staticmethod(
            lambda db: {
                "is_valid": True,
                "features": ["all"],
                "status": "Developer Mode",
            }
        ),
    )

    res = client.get("/api/v1/ops/policy-manifest", headers=admin_user_token)

    assert res.status_code == 200
    payload = res.json()["data"]
    assert payload["preview_enabled"] is False
    assert payload["edition"] == "pro"
    assert payload["surfaces"]["operations_home"]["navigable"] is True
    assert payload["surfaces"]["cloud_accounts"]["navigable"] is True
    assert payload["surfaces"]["cloud_intents"]["navigable"] is True
    assert payload["surfaces"]["settings"]["navigable"] is True
    assert payload["surfaces"]["users"]["navigable"] is True
    assert payload["surfaces"]["settings"]["blocked_code"] == ""
    assert any(section["key"] == "administration" for section in payload["navigation"]["sidebar_sections"])
    assert any(workspace["key"] == "control" for workspace in payload["workspaces"])
    control_workspace = next(workspace for workspace in payload["workspaces"] if workspace["key"] == "control")
    assert "cloud_intents" in control_workspace["primary_surface_keys"]
