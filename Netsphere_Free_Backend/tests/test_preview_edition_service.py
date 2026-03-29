from app.models.settings import SystemSetting
from app.models.user import User
from app.services.preview_edition_service import PreviewEditionService


def test_preview_sanitizer_masks_identifiers_and_preserves_structure():
    payload = PreviewEditionService.sanitize_output(
        command="show lldp neighbors detail",
        raw_output=(
            "hostname edge-sw-01\n"
            "Mgmt IP: 10.10.1.12\n"
            "Peer MAC: aa:bb:cc:dd:ee:ff\n"
            "admin@example.com\n"
            "SN: FDO1234ABCD\n"
            "snmp community public-secret\n"
        ),
        host_candidates=["edge-sw-01"],
    )

    text = payload["sanitized_output"]
    assert "edge-sw-01" not in text
    assert "10.10.1.12" not in text
    assert "aa:bb:cc:dd:ee:ff" not in text
    assert "admin@example.com" not in text
    assert "FDO1234ABCD" not in text
    assert "public-secret" not in text
    assert "<REDACTED_SECRET>" in text
    assert "snmp community <REDACTED_SECRET>" in text
    assert "HOST_001" in text
    assert "IP_001" in text
    assert "MAC_001" in text
    assert "EMAIL_001" in text
    assert "SERIAL_001" in text


def test_preview_command_allowlist_blocks_running_config():
    assert PreviewEditionService.is_command_allowed("show version") is True
    assert PreviewEditionService.is_command_allowed("show running-config") is False
    assert PreviewEditionService.is_command_allowed("show running-config | include aaa") is False


def test_preview_mutation_policy_allows_experience_paths_and_blocks_admin_paths(db):
    db.add(SystemSetting(key="product_edition", value="preview", description="", category="preview"))
    db.commit()
    assert PreviewEditionService.is_mutation_blocked(db, "POST", "/api/v1/discovery/scan") is False
    assert PreviewEditionService.is_mutation_blocked(db, "POST", "/api/v1/topology/path-trace") is False
    assert PreviewEditionService.is_mutation_blocked(db, "POST", "/api/v1/diagnosis/one-click") is False
    assert PreviewEditionService.is_mutation_blocked(db, "POST", "/api/v1/auth/users") is True


def test_preview_initial_admin_required_only_before_first_human_user(db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="collector_installed", description="", category="preview"),
        ]
    )
    db.commit()

    assert PreviewEditionService.initial_admin_required(db) is True

    db.add(
        User(
            username="preview-admin",
            hashed_password="hashed",
            full_name="Preview Admin",
            role="admin",
            is_active=True,
            must_change_password=False,
            eula_accepted=False,
        )
    )
    db.commit()

    assert PreviewEditionService.initial_admin_required(db) is False


def test_preview_intake_registration_auth_uses_active_registration(db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="intake_server", description="", category="preview"),
            SystemSetting(key="preview_accept_remote_uploads", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    issued = PreviewEditionService.create_intake_registration(db, label="Customer A", issued_to="customer-a")
    collector_id = issued["collector_id"]
    token = issued["intake_token"]

    assert (
        PreviewEditionService.authenticate_intake_registration(
            db,
            collector_id=collector_id,
            token=token,
        )
        is not None
    )
    assert (
        PreviewEditionService.authenticate_intake_registration(
            db,
            collector_id=collector_id,
            token="wrong-token",
        )
        is None
    )


def test_preview_self_enroll_reuses_installation_identity(db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="intake_server", description="", category="preview"),
            SystemSetting(key="preview_accept_remote_uploads", value="true", description="", category="preview"),
            SystemSetting(key="preview_self_registration_enabled", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    first = PreviewEditionService.self_enroll_intake_registration(
        db,
        installation_id="pvi-same-install",
        requested_label="Collector A",
    )
    second = PreviewEditionService.self_enroll_intake_registration(
        db,
        installation_id="pvi-same-install",
        requested_label="Collector A Reissued",
    )

    assert first["collector_id"] == second["collector_id"]
    assert first["intake_token"] != second["intake_token"]
    assert (
        PreviewEditionService.authenticate_intake_registration(
            db,
            collector_id=second["collector_id"],
            token=second["intake_token"],
        )
        is not None
    )


def test_preview_auto_enrollment_persists_remote_credentials(db, monkeypatch):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="collector_installed", description="", category="preview"),
            SystemSetting(key="preview_upload_target_mode", value="remote_only", description="", category="preview"),
            SystemSetting(key="preview_remote_upload_url", value="https://intake.example.com/api/v1/preview/contributions", description="", category="preview"),
            SystemSetting(key="preview_self_registration_enabled", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "collector_id": "pvc-auto-collector",
                "intake_token": "auto-issued-token",
                "upload_url": "https://intake.example.com/api/v1/preview/contributions",
            }

    monkeypatch.setattr(
        "app.services.preview_edition_service.requests.post",
        lambda *args, **kwargs: _Response(),
    )

    result = PreviewEditionService.ensure_remote_upload_registration(db, source="first_run_wizard")
    policy = PreviewEditionService.get_policy(db)

    assert result["status"] == "registered"
    assert policy["remote_upload_registered"] is True
    assert policy["remote_upload_registration_state"] == "registered"
    assert policy["remote_upload_client_id"] == "pvc-auto-collector"


def test_preview_policy_normalizes_installed_collector_role(db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_deployment_role", value="collector", description="", category="preview"),
        ]
    )
    db.commit()

    policy = PreviewEditionService.get_policy(db)

    assert policy["deployment_role"] == "collector_installed"
    assert policy["upload_target_mode"] == "remote_only"
    assert policy["local_embedded_execution"] is True


def test_preview_policy_defaults_to_opt_in_model_until_decision_is_recorded(db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_contribution_upload_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_opt_in_required", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    policy = PreviewEditionService.get_policy(db)

    assert policy["upload_feature_available"] is True
    assert policy["upload_enabled"] is False
    assert policy["upload_participation"] == "unset"
    assert policy["upload_decision_recorded"] is False
    assert policy["upload_opt_in_enabled"] is False
    assert policy["upload_locked"] is False
    assert policy["upload_change_requires_reset"] is False
    assert policy["contribution_scope"] == "allowlisted_read_only_commands_only"


def test_preview_contribution_policy_locks_after_first_record(db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview", description="", category="preview"),
            SystemSetting(key="preview_contribution_upload_enabled", value="true", description="", category="preview"),
            SystemSetting(key="preview_contribution_opt_in_required", value="true", description="", category="preview"),
        ]
    )
    db.commit()

    user = User(
        username="preview-admin",
        hashed_password="hashed",
        full_name="Preview Admin",
        role="admin",
        is_active=True,
        must_change_password=False,
        eula_accepted=True,
    )
    db.add(user)
    db.commit()

    first = PreviewEditionService.set_upload_participation(
        db,
        user=user,
        enabled=True,
        source="first_run_wizard",
    )

    assert first["state"] == "enabled"
    assert first["policy"]["upload_locked"] is True
    assert first["policy"]["upload_change_requires_reset"] is True

    try:
        PreviewEditionService.set_upload_participation(
            db,
            user=user,
            enabled=False,
            source="first_run_wizard",
        )
        assert False, "expected locked contribution policy to reject reconfiguration"
    except PermissionError as exc:
        assert "locked for this installation" in str(exc)
