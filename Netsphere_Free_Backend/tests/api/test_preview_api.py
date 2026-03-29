import json
from types import SimpleNamespace

from app.models.device import Device
from app.models.settings import SystemSetting
from app.api.v1.endpoints import discovery as discovery_endpoint
from app.api.v1.endpoints import preview as preview_endpoint


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_preview_policy_endpoint_returns_preview_defaults(client, normal_user_token, db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_capture_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_upload_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_opt_in_required", value="true", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="collector_installed", description="", category="preview"),
            SystemSetting(key="preview_upload_target_mode", value="remote_only", description="", category="preview"),
            SystemSetting(key="preview_local_embedded_execution", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    res = client.get("/api/v1/preview/policy", headers=normal_user_token)

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["preview_enabled"] is True
    assert payload["capture_enabled"] is True
    assert payload["upload_feature_available"] is True
    assert payload["upload_enabled"] is False
    assert payload["upload_participation"] == "unset"
    assert payload["upload_decision_recorded"] is False
    assert payload["upload_opt_in_enabled"] is False
    assert payload["upload_locked"] is False
    assert payload["upload_change_requires_reset"] is False
    assert payload["contribution_scope"] == "allowlisted_read_only_commands_only"
    assert payload["deployment_role"] == "collector_installed"
    assert payload["upload_target_mode"] == "remote_only"
    assert payload["local_embedded_execution"] is True
    assert "show version" in payload["allowed_commands"]
    assert "/discovery" in payload["allowed_nav_exact_paths"]
    assert "/automation" in payload["allowed_nav_exact_paths"]
    assert "/sites" in payload["allowed_nav_exact_paths"]
    assert any(item["key"] == "auto_topology" for item in payload["experience_pillars"])
    assert "topology" in payload["same_codebase_surfaces"]


def test_preview_contribution_consent_endpoint_enables_upload(client, normal_user_token, db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_contribution_upload_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_opt_in_required", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    res = client.post(
        "/api/v1/preview/consent/contribution",
        headers=normal_user_token,
        json={"enabled": True, "source": "first_run_wizard"},
    )

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["state"] == "enabled"
    assert payload["policy"]["upload_enabled"] is True
    assert payload["policy"]["upload_decision_recorded"] is True
    assert payload["policy"]["upload_opt_in_enabled"] is True
    assert payload["policy"]["upload_locked"] is True
    assert payload["policy"]["upload_change_requires_reset"] is True


def test_preview_contribution_consent_endpoint_blocks_reconfiguration_after_first_choice(client, normal_user_token, db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_contribution_upload_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_opt_in_required", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    first = client.post(
        "/api/v1/preview/consent/contribution",
        headers=normal_user_token,
        json={"enabled": True, "source": "first_run_wizard"},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/preview/consent/contribution",
        headers=normal_user_token,
        json={"enabled": False, "source": "first_run_wizard"},
    )

    assert second.status_code == 403
    assert "locked for this installation" in str(second.json())


def test_preview_contribution_consent_auto_enrolls_remote_collector(client, normal_user_token, db, monkeypatch):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_contribution_upload_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_opt_in_required", value="true", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="collector_installed", description="", category="preview"),
            SystemSetting(key="preview_upload_target_mode", value="remote_only", description="", category="preview"),
            SystemSetting(key="preview_remote_upload_url", value="https://intake.example.com/api/v1/preview/contributions", description="", category="preview"),
            SystemSetting(key="preview_self_registration_enabled", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    monkeypatch.setattr(
        preview_endpoint.PreviewEditionService,
        "ensure_remote_upload_registration",
        classmethod(
            lambda cls, _db, user=None, source="auto_enroll", policy=None: {
                "status": "registered",
                "collector_id": "pvc-auto-1",
                "upload_url": "https://intake.example.com/api/v1/preview/contributions",
            }
        ),
    )

    res = client.post(
        "/api/v1/preview/consent/contribution",
        headers=normal_user_token,
        json={"enabled": True, "source": "first_run_wizard"},
    )

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["state"] == "enabled"
    assert payload["enrollment"]["status"] == "registered"
    assert payload["policy"]["upload_opt_in_enabled"] is True


def test_preview_sanitize_endpoint_masks_outputs(client, normal_user_token, db):
    db.add(SystemSetting(key="product_edition", value="preview", description="", category="preview"))
    db.commit()

    res = client.post(
        "/api/v1/preview/sanitize",
        headers=normal_user_token,
        json={
            "entries": [
                {
                    "command": "show version",
                    "raw_output": "hostname edge-sw-01\nMgmt 10.1.1.5\nSN: FDO12345\n",
                }
            ],
            "host_candidates": ["edge-sw-01"],
        },
    )

    assert res.status_code == 200
    payload = _unwrap(res.json())
    item = payload["entries"][0]
    assert "edge-sw-01" not in item["sanitized_output"]
    assert "10.1.1.5" not in item["sanitized_output"]
    assert "FDO12345" not in item["sanitized_output"]


def test_preview_capture_endpoint_uses_capture_service(client, operator_user_token, db, monkeypatch):
    db.add(SystemSetting(key="product_edition", value="preview", description="", category="preview"))
    device = Device(
        name="lab-sw-01",
        hostname="lab-sw-01",
        ip_address="10.0.0.10",
        device_type="cisco_ios",
        ssh_username="admin",
        ssh_password="password",
        owner_id=None,
    )
    db.add(device)
    db.commit()

    monkeypatch.setattr(
        preview_endpoint.PreviewEditionService,
        "capture_device_outputs",
        lambda _db, *, device, commands: {
            "device": {"id": device.id, "device_type": device.device_type},
            "entries": [{"command": "show version", "sanitized_output": "HOST_001"}],
            "failures": [],
            "captured_commands": ["show version"],
        },
    )

    res = client.post(
        f"/api/v1/preview/devices/{device.id}/capture",
        headers=operator_user_token,
        json={"commands": ["show version"]},
    )

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["captured_commands"] == ["show version"]


def test_preview_upload_persists_sanitized_bundle(client, normal_user_token, db, tmp_path, monkeypatch):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_contribution_upload_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_opt_in_required", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_participation", value="enabled", description="", category="preview"),
            SystemSetting(key="preview_contribution_require_consent", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_storage_dir", value=str(tmp_path), description="", category="preview"),
        ]
    )
    db.commit()

    res = client.post(
        "/api/v1/preview/contributions",
        headers=normal_user_token,
        json={
            "source": "manual",
            "consent_confirmed": True,
            "notes": "fixture candidate",
            "entries": [
                {
                    "command": "show version",
                    "raw_output": "hostname edge-sw-01\n10.1.1.5\n",
                }
            ],
        },
    )

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["saved"] is True
    files = list(tmp_path.rglob("preview-*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["entry_count"] == 1
    assert "10.1.1.5" not in saved["entries"][0]["sanitized_output"]


def test_preview_admin_can_read_recent_contribution_record_detail(client, normal_user_token, admin_user_token, db, tmp_path):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_contribution_upload_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_opt_in_required", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_participation", value="enabled", description="", category="preview"),
            SystemSetting(key="preview_contribution_require_consent", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_storage_dir", value=str(tmp_path), description="", category="preview"),
        ]
    )
    db.commit()

    create_res = client.post(
        "/api/v1/preview/contributions",
        headers=normal_user_token,
        json={
            "source": "manual",
            "consent_confirmed": True,
            "notes": "audit me",
            "entries": [
                {
                    "command": "show version",
                    "raw_output": "hostname edge-sw-01\n10.1.1.5\n",
                }
            ],
        },
    )

    assert create_res.status_code == 200
    created = _unwrap(create_res.json())
    contribution_id = created["id"]

    detail_res = client.get(
        f"/api/v1/preview/contributions/{contribution_id}",
        headers=admin_user_token,
    )

    assert detail_res.status_code == 200
    detail = _unwrap(detail_res.json())
    assert detail["id"] == contribution_id
    assert detail["notes"] == "audit me"
    assert detail["entry_count"] == 1
    assert detail["entries"][0]["command"] == "show version"
    assert "10.1.1.5" not in detail["entries"][0]["sanitized_output"]


def test_preview_upload_remote_only_forwards_without_local_save(client, normal_user_token, db, tmp_path, monkeypatch):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_contribution_upload_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_opt_in_required", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_participation", value="enabled", description="", category="preview"),
            SystemSetting(key="preview_contribution_require_consent", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_storage_dir", value=str(tmp_path), description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="collector_installed", description="", category="preview"),
            SystemSetting(key="preview_upload_target_mode", value="remote_only", description="", category="preview"),
            SystemSetting(key="preview_remote_upload_url", value="https://preview.example/api/v1/preview/contributions", description="", category="preview"),
            SystemSetting(key="preview_remote_upload_client_id", value="pvc-customer-a", description="", category="preview"),
            SystemSetting(key="preview_remote_upload_token", value="preview-token", description="", category="preview"),
        ]
    )
    db.commit()

    monkeypatch.setattr(
        preview_endpoint.PreviewEditionService,
        "_forward_payload_to_remote",
        classmethod(lambda cls, payload, policy: {"saved": True, "id": "remote-intake-1"}),
    )
    monkeypatch.setattr(
        preview_endpoint.PreviewEditionService,
        "ensure_remote_upload_registration",
        classmethod(lambda cls, _db, user=None, source="auto_enroll", policy=None: {"status": "already_registered", "collector_id": "pvc-customer-a"}),
    )

    res = client.post(
        "/api/v1/preview/contributions",
        headers=normal_user_token,
        json={
            "source": "manual",
            "consent_confirmed": True,
            "notes": "remote only",
            "entries": [{"command": "show version", "raw_output": "hostname edge-sw-01\n10.1.1.5\n"}],
        },
    )

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["saved"] is True
    assert payload["delivery"]["mode"] == "remote_only"
    assert payload["delivery"]["local_saved"] is False
    assert payload["delivery"]["remote_forwarded"] is True
    assert list(tmp_path.rglob("preview-*.json")) == []


def test_preview_upload_accepts_intake_token_without_user_session(client, db, tmp_path):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_contribution_upload_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_opt_in_required", value="false", description="", category="preview"),
            SystemSetting(key="preview_contribution_require_consent", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_storage_dir", value=str(tmp_path), description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="intake_server", description="", category="preview"),
            SystemSetting(key="preview_accept_remote_uploads", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    issued = preview_endpoint.PreviewEditionService.create_intake_registration(
        db,
        label="Customer A",
        issued_to="customer-a",
    )

    res = client.post(
        "/api/v1/preview/contributions",
        headers={
            "X-Preview-Collector-Id": issued["collector_id"],
            "X-Preview-Intake-Token": issued["intake_token"],
        },
        json={
            "source": "collector_forward",
            "consent_confirmed": True,
            "notes": "collector upload",
            "device_context": {"device_type": "cisco_ios", "model": "C9300", "os_version": "17.9.3"},
            "collector_context": {"collector_id": "lab-collector-01", "deployment_role": "collector_installed"},
            "entries": [{"command": "show version", "sanitized_output": "HOST_001\nIP_001\n"}],
        },
    )

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["saved"] is True
    files = list(tmp_path.rglob("preview-*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["submitter_role"] == "collector"
    assert saved["device"]["device_type"] == "cisco_ios"
    assert saved["collector_context"]["collector_id"] == issued["collector_id"]
    assert saved["collector_context"]["registration_label"] == "Customer A"


def test_preview_intake_registration_management_endpoints_issue_rotate_and_revoke(client, admin_user_token, db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="intake_server", description="", category="preview"),
            SystemSetting(key="preview_accept_remote_uploads", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    create_res = client.post(
        "/api/v1/preview/intake-registrations",
        headers=admin_user_token,
        json={"label": "Customer A", "issued_to": "customer-a", "notes": "pilot"},
    )

    assert create_res.status_code == 200
    create_payload = _unwrap(create_res.json())
    collector_id = create_payload["collector_id"]
    token = create_payload["intake_token"]
    assert collector_id.startswith("pvc-")
    assert token

    list_res = client.get("/api/v1/preview/intake-registrations", headers=admin_user_token)
    assert list_res.status_code == 200
    items = _unwrap(list_res.json())["items"]
    assert any(item["collector_id"] == collector_id and item["is_active"] is True for item in items)

    rotate_res = client.post(
        f"/api/v1/preview/intake-registrations/{collector_id}/rotate",
        headers=admin_user_token,
        json={"notes": "rotated"},
    )
    assert rotate_res.status_code == 200
    rotate_payload = _unwrap(rotate_res.json())
    assert rotate_payload["collector_id"] == collector_id
    assert rotate_payload["intake_token"] != token

    revoke_res = client.post(
        f"/api/v1/preview/intake-registrations/{collector_id}/revoke",
        headers=admin_user_token,
    )
    assert revoke_res.status_code == 200
    revoke_payload = _unwrap(revoke_res.json())
    assert revoke_payload["collector_id"] == collector_id
    assert revoke_payload["is_active"] is False


def test_preview_intake_self_enroll_endpoint_issues_registration_without_admin_session(client, db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="intake_server", description="", category="preview"),
            SystemSetting(key="preview_accept_remote_uploads", value="true", description="", category="preview"),
            SystemSetting(key="preview_self_registration_enabled", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    res = client.post(
        "/api/v1/preview/intake-enroll",
        json={
            "installation_id": "pvi-abc123",
            "requested_label": "Preview Collector ABC123",
            "source": "first_run_wizard",
            "consent_confirmed": True,
            "metadata": {"deployment_role": "collector_installed"},
        },
    )

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["collector_id"].startswith("pvc-")
    assert payload["intake_token"]
    assert payload["registration"]["issued_to"] == "self_install:pvi-abc123"


def test_preview_upload_rejects_until_instance_opt_in_is_enabled(client, normal_user_token, db, tmp_path):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_contribution_upload_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_opt_in_required", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_participation", value="disabled", description="", category="preview"),
            SystemSetting(key="preview_contribution_require_consent", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_storage_dir", value=str(tmp_path), description="", category="preview"),
        ]
    )
    db.commit()

    res = client.post(
        "/api/v1/preview/contributions",
        headers=normal_user_token,
        json={
            "source": "manual",
            "consent_confirmed": True,
            "notes": "blocked until opt in",
            "entries": [{"command": "show version", "raw_output": "hostname edge-sw-01\n10.1.1.5\n"}],
        },
    )

    assert res.status_code == 403
    assert "Enable optional data sharing first" in str(res.json())


def test_preview_guard_blocks_settings_update_when_preview_enabled(client, admin_user_token, db):
    db.add(SystemSetting(key="product_edition", value="preview", description="", category="preview"))
    db.commit()

    res = client.put(
        "/api/v1/settings/general",
        headers=admin_user_token,
        json={"settings": {"hostname": "blocked-preview-host"}},
    )

    assert res.status_code == 403
    payload = res.json()
    detail = payload.get("error") or payload.get("detail") or {}
    code = detail.get("code") if isinstance(detail, dict) else None
    assert code == "PREVIEW_EDITION_BLOCKED"


def test_preview_guard_allows_discovery_scan_when_preview_enabled(client, operator_user_token, db, monkeypatch):
    db.add(SystemSetting(key="product_edition", value="preview", description="", category="preview"))
    db.commit()

    monkeypatch.setattr(
        discovery_endpoint.DiscoveryService,
        "create_scan_job",
        lambda self, cidr, community, **kwargs: SimpleNamespace(
            id=123,
            cidr=cidr,
            status="pending",
            logs="",
            created_at="2026-03-10T00:00:00Z",
        ),
    )
    monkeypatch.setattr(
        discovery_endpoint,
        "dispatch_discovery_scan",
        lambda *args, **kwargs: {"status": "enqueued"},
    )

    res = client.post(
        "/api/v1/discovery/scan",
        headers=operator_user_token,
        json={"cidr": "192.168.1.0/24", "community": "public"},
    )

    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert payload["id"] == 123
