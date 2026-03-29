from datetime import datetime, timedelta, timezone

from app.core.license import LicenseSchema
from app.models.approval import ApprovalRequest
from app.models.cloud import CloudAccount, CloudResource
from app.models.settings import SystemSetting
from app.models.user import User
from app.services.cloud_bootstrap_service import CloudBootstrapService
from app.services.license_service import LicenseService


def _payload(res):
    body = res.json()
    if isinstance(body, dict) and "data" in body:
        return body.get("data")
    return body


def _enable_cloud_scope(db, monkeypatch):
    row = db.query(SystemSetting).filter(SystemSetting.key == "product_operating_mode").first()
    if row:
        row.value = "multicloud_full"
    else:
        db.add(SystemSetting(key="product_operating_mode", value="multicloud_full", description="", category="General"))
    db.commit()

    monkeypatch.setattr(
        LicenseService,
        "get_effective_license",
        staticmethod(
            lambda _db: LicenseSchema(
                customer="pytest-cloud",
                expiration=datetime.now(timezone.utc) + timedelta(days=30),
                max_devices=1000,
                features=["cloud"],
                is_valid=True,
                status="Active",
            )
        ),
    )


def _set_cloud_bootstrap_policy(db, enabled: bool):
    key = "change_policy_cloud_bootstrap_live_requires_approval"
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    value = "true" if bool(enabled) else "false"
    if row:
        row.value = value
    else:
        db.add(SystemSetting(key=key, value=value, description="", category="General"))
    db.commit()


def test_cloud_bootstrap_dry_run_filters_vm_targets(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)

    acc = CloudAccount(
        name="aws-bootstrap",
        provider="aws",
        credentials={"access_key": "AK", "secret_key": "SK", "region": "ap-northeast-2"},
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.flush()
    db.add_all(
        [
            CloudResource(
                account_id=int(acc.id),
                resource_id="i-001",
                resource_type="virtual_machine",
                name="vm-001",
                region="ap-northeast-2",
                state="running",
                resource_metadata={},
            ),
            CloudResource(
                account_id=int(acc.id),
                resource_id="i-002",
                resource_type="virtual_machine",
                name="vm-002",
                region="ap-northeast-2",
                state="running",
                resource_metadata={},
            ),
            CloudResource(
                account_id=int(acc.id),
                resource_id="subnet-001",
                resource_type="subnet",
                name="sn-001",
                region="ap-northeast-2",
                state="available",
                resource_metadata={},
            ),
        ]
    )
    db.commit()

    res = client.post(
        "/api/v1/cloud/bootstrap/run",
        json={
            "account_ids": [int(acc.id)],
            "dry_run": True,
            "wave_size": 1,
            "stop_on_wave_failure": True,
            "idempotency_key": "cloud-bootstrap-dry-1",
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _payload(res)
    assert str(body.get("status")) == "ok"
    assert int(body.get("total_targets") or 0) == 2
    assert int(body.get("dry_run_targets") or 0) == 2
    assert int(body.get("failed_targets") or 0) == 0
    rows = list(body.get("results") or [])
    assert len(rows) == 2
    assert all(str(r.get("status")) == "dry_run" for r in rows)
    assert all(str(r.get("script_sha256") or "").strip() for r in rows)


def test_cloud_bootstrap_dry_run_filters_single_resource_id(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)

    acc = CloudAccount(
        name="aws-bootstrap-single-target",
        provider="aws",
        credentials={"access_key": "AK", "secret_key": "SK", "region": "ap-northeast-2"},
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.flush()
    db.add_all(
        [
            CloudResource(
                account_id=int(acc.id),
                resource_id="i-single-001",
                resource_type="virtual_machine",
                name="vm-single-001",
                region="ap-northeast-2",
                state="running",
                resource_metadata={},
            ),
            CloudResource(
                account_id=int(acc.id),
                resource_id="i-single-002",
                resource_type="virtual_machine",
                name="vm-single-002",
                region="ap-northeast-2",
                state="running",
                resource_metadata={},
            ),
        ]
    )
    db.commit()

    res = client.post(
        "/api/v1/cloud/bootstrap/run",
        json={
            "account_ids": [int(acc.id)],
            "resource_ids": ["i-single-002"],
            "dry_run": True,
            "idempotency_key": "cloud-bootstrap-single-target-1",
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _payload(res)
    assert str(body.get("status")) == "ok"
    assert int(body.get("total_targets") or 0) == 1
    rows = list(body.get("results") or [])
    assert len(rows) == 1
    assert str(rows[0].get("resource_id")) == "i-single-002"
    assert str(rows[0].get("status")) == "dry_run"


def test_cloud_bootstrap_apply_halts_on_failed_wave(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    _set_cloud_bootstrap_policy(db, False)

    acc = CloudAccount(
        name="azure-bootstrap",
        provider="azure",
        credentials={"tenant_id": "t1", "subscription_id": "s1", "client_id": "c1", "client_secret": "x"},
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.flush()
    db.add_all(
        [
            CloudResource(
                account_id=int(acc.id),
                resource_id="vm-a",
                resource_type="virtual_machine",
                name="vm-a",
                region="koreacentral",
                state="running",
                resource_metadata={"simulate_bootstrap_apply_success": True},
            ),
            CloudResource(
                account_id=int(acc.id),
                resource_id="vm-b",
                resource_type="virtual_machine",
                name="vm-b",
                region="koreacentral",
                state="stopped",
                resource_metadata={},
            ),
            CloudResource(
                account_id=int(acc.id),
                resource_id="vm-c",
                resource_type="virtual_machine",
                name="vm-c",
                region="koreacentral",
                state="running",
                resource_metadata={},
            ),
        ]
    )
    db.commit()

    res = client.post(
        "/api/v1/cloud/bootstrap/run",
        json={
            "account_ids": [int(acc.id)],
            "dry_run": False,
            "wave_size": 1,
            "stop_on_wave_failure": True,
            "rollback_on_failure": True,
            "idempotency_key": "cloud-bootstrap-apply-1",
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _payload(res)
    assert str(body.get("status")) == "partial"
    rows = list(body.get("results") or [])
    by_resource = {str(r.get("resource_id")): r for r in rows if str(r.get("resource_id") or "").strip()}
    assert str(by_resource["vm-a"].get("status")) == "success"
    assert str(by_resource["vm-b"].get("status")) == "precheck_failed"
    skipped = next((r for r in rows if str(r.get("status")) == "skipped_wave_halt"), None)
    assert skipped is not None


def test_cloud_bootstrap_requires_approved_approval_id(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    requester = db.query(User).order_by(User.id.asc()).first()
    assert requester is not None

    approval = ApprovalRequest(
        requester_id=int(requester.id),
        title="cloud bootstrap",
        description="test",
        request_type="cloud_bootstrap",
        payload={"account_ids": [1]},
        status="pending",
    )
    db.add(approval)
    db.commit()
    db.refresh(approval)

    res = client.post(
        "/api/v1/cloud/bootstrap/run",
        json={
            "dry_run": True,
            "approval_id": int(approval.id),
            "idempotency_key": "cloud-bootstrap-approval-1",
        },
        headers=operator_user_token,
    )
    assert res.status_code == 409
    assert "must be approved before execution" in str(res.json())


def test_cloud_bootstrap_live_requires_approval_when_policy_enabled(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    _set_cloud_bootstrap_policy(db, True)

    acc = CloudAccount(
        name="aws-bootstrap-approval-policy",
        provider="aws",
        credentials={"access_key": "AK", "secret_key": "SK", "region": "ap-northeast-2"},
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.flush()
    db.add(
        CloudResource(
            account_id=int(acc.id),
            resource_id="i-live-policy-1",
            resource_type="virtual_machine",
            name="vm-live-policy-1",
            region="ap-northeast-2",
            state="running",
            resource_metadata={},
        )
    )
    db.commit()

    res = client.post(
        "/api/v1/cloud/bootstrap/run",
        json={
            "account_ids": [int(acc.id)],
            "dry_run": False,
            "idempotency_key": "cloud-bootstrap-live-policy-1",
        },
        headers=operator_user_token,
    )
    assert res.status_code == 409
    assert "Approval required for live cloud bootstrap" in str(res.json())


def test_cloud_account_bootstrap_live_requires_approval_when_policy_enabled(client, admin_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    _set_cloud_bootstrap_policy(db, True)

    acc = CloudAccount(
        name="aws-account-bootstrap-approval-policy",
        provider="aws",
        credentials={"access_key": "AK", "secret_key": "SK", "region": "ap-northeast-2"},
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.flush()
    db.add(
        CloudResource(
            account_id=int(acc.id),
            resource_id="i-live-policy-account-1",
            resource_type="virtual_machine",
            name="vm-live-policy-account-1",
            region="ap-northeast-2",
            state="running",
            resource_metadata={},
        )
    )
    db.commit()

    res = client.post(
        f"/api/v1/cloud/accounts/{int(acc.id)}/bootstrap/run",
        json={
            "dry_run": False,
            "idempotency_key": "cloud-account-bootstrap-live-policy-1",
        },
        headers=admin_user_token,
    )
    assert res.status_code == 409
    assert "Approval required for live cloud bootstrap" in str(res.json())


def test_cloud_account_bootstrap_requires_existing_account(client, admin_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    res = client.post(
        "/api/v1/cloud/accounts/99999/bootstrap/run",
        json={"dry_run": True},
        headers=admin_user_token,
    )
    assert res.status_code == 404


def test_cloud_bootstrap_passes_runtime_credentials_and_context(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    _set_cloud_bootstrap_policy(db, False)

    acc = CloudAccount(
        name="aws-bootstrap-context",
        provider="aws",
        credentials={"access_key": "AKIA_TEST", "secret_key": "SECRET_TEST", "region": "ap-northeast-2"},
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.flush()
    db.add(
        CloudResource(
            account_id=int(acc.id),
            resource_id="i-ctx-001",
            resource_type="virtual_machine",
            name="ctx-vm-001",
            region="ap-northeast-2",
            state="running",
            resource_metadata={},
        )
    )
    db.commit()

    captured = {}

    def _fake_apply(**kwargs):
        captured["request_context"] = dict(kwargs.get("request_context") or {})
        captured["runtime_credentials"] = dict(kwargs.get("runtime_credentials") or {})
        return {"ok": True, "message": "mock applied", "transport": "mock"}

    monkeypatch.setattr(CloudBootstrapService, "_apply_bootstrap", staticmethod(_fake_apply))

    res = client.post(
        "/api/v1/cloud/bootstrap/run",
        json={
            "account_ids": [int(acc.id)],
            "dry_run": False,
            "post_check_enabled": False,
            "context": {
                "bootstrap_channel": "ssm",
                "controller_url": "https://controller.example.local/api/v1",
            },
            "idempotency_key": "cloud-bootstrap-context-1",
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _payload(res)
    assert str(body.get("status")) == "ok"
    assert str(captured.get("request_context", {}).get("bootstrap_channel")) == "ssm"
    assert str(captured.get("runtime_credentials", {}).get("access_key")) == "AKIA_TEST"
    assert str(captured.get("runtime_credentials", {}).get("secret_key")) == "SECRET_TEST"


def test_cloud_bootstrap_uses_account_bootstrap_path_when_context_missing(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    _set_cloud_bootstrap_policy(db, False)

    acc = CloudAccount(
        name="aws-bootstrap-default-path",
        provider="aws",
        credentials={
            "access_key": "AKIA_DEFAULT",
            "secret_key": "SECRET_DEFAULT",
            "region": "ap-northeast-2",
            "bootstrap_path": "ssm",
        },
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.flush()
    db.add(
        CloudResource(
            account_id=int(acc.id),
            resource_id="i-default-001",
            resource_type="virtual_machine",
            name="default-vm-001",
            region="ap-northeast-2",
            state="running",
            resource_metadata={},
        )
    )
    db.commit()

    captured = {}

    def _fake_apply(**kwargs):
        captured["request_context"] = dict(kwargs.get("request_context") or {})
        return {"ok": True, "message": "mock applied", "transport": "mock"}

    monkeypatch.setattr(CloudBootstrapService, "_apply_bootstrap", staticmethod(_fake_apply))

    res = client.post(
        "/api/v1/cloud/bootstrap/run",
        json={
            "account_ids": [int(acc.id)],
            "dry_run": False,
            "post_check_enabled": False,
            "idempotency_key": "cloud-bootstrap-default-path-1",
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _payload(res)
    assert str(body.get("status")) == "ok"
    assert str(captured.get("request_context", {}).get("aws_bootstrap_path")) == "ssm"
