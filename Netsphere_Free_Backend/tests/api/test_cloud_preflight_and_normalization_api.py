from datetime import datetime, timedelta, timezone
import json

from app.models.approval import ApprovalRequest
from app.models.audit import AuditLog
from app.core.license import LicenseSchema
from app.models.cloud import CloudAccount, CloudResource
from app.models.device import EventLog
from app.models.settings import SystemSetting
from app.models.user import User
from app.services.cloud_bootstrap_service import CloudBootstrapService
from app.services.cloud_pipeline_service import CloudPipelineService
from app.services.cloud_service import CloudScanner
from app.services.license_service import LicenseService


def _payload(res):
    body = res.json()
    if isinstance(body, dict) and "data" in body:
        return body.get("data")
    return body


def _error_message(res) -> str:
    body = res.json()
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else {}
        return str(err.get("message") or body.get("detail") or "")
    return ""


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


def test_cloud_provider_presets_available(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    res = client.get("/api/v1/cloud/providers/presets", headers=operator_user_token)
    assert res.status_code == 200
    payload = _payload(res)
    providers = [str(x.get("provider")) for x in payload if isinstance(x, dict)]
    assert "aws" in providers
    assert "azure" in providers
    assert "gcp" in providers
    assert "naver" in providers


def test_cloud_preflight_validates_credentials_schema(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    res = client.post(
        "/api/v1/cloud/preflight",
        json={
            "provider": "aws",
            "credentials": {"auth_type": "access_key", "region": "ap-northeast-2"},
        },
        headers=operator_user_token,
    )
    assert res.status_code == 400
    assert "Access Key/Secret Key" in _error_message(res)


def test_cloud_preflight_uses_scanner_result(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    async def _fake_preflight(self):
        return {
            "provider": "aws",
            "status": "ok",
            "summary": "fake passed",
            "checks": [{"key": "sts_identity", "ok": True, "message": "ok"}],
        }

    monkeypatch.setattr(CloudScanner, "preflight", _fake_preflight)
    res = client.post(
        "/api/v1/cloud/preflight",
        json={
            "provider": "aws",
            "credentials": {
                "auth_type": "access_key",
                "region": "ap-northeast-2",
                "access_key": "AKIA_TEST",
                "secret_key": "SECRET_TEST",
            },
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _payload(res)
    assert body["status"] == "ok"
    assert body["summary"] == "fake passed"


def test_cloud_account_preflight_and_normalized_resources(client, admin_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    acc = CloudAccount(
        name="ncp-prod",
        provider="ncp",
        credentials={"access_key": "AK", "secret_key": "SK"},
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.flush()
    db.add(
        CloudResource(
            account_id=acc.id,
            resource_id="vpn-tunnel-1",
            resource_type="vpn_tunnel",
            name="tunnel-1",
            region="KR",
            cidr_block=None,
            state="available",
            resource_metadata={"peer_ip": "203.0.113.10", "tags": {"env": "prod"}},
        )
    )
    db.commit()

    async def _fake_preflight(self):
        return {
            "provider": "ncp",
            "status": "failed",
            "summary": "permission denied",
            "checks": [{"key": "vpc_list", "ok": False, "message": "403"}],
        }

    monkeypatch.setattr(CloudScanner, "preflight", _fake_preflight)

    preflight = client.post(f"/api/v1/cloud/accounts/{int(acc.id)}/preflight", headers=admin_user_token)
    assert preflight.status_code == 200
    assert _payload(preflight)["status"] == "failed"

    normalized = client.get("/api/v1/cloud/resources/normalized", headers=admin_user_token)
    assert normalized.status_code == 200
    rows = _payload(normalized)
    assert len(rows) >= 1
    item = next((r for r in rows if str(r.get("resource_id")) == "vpn-tunnel-1"), None)
    assert item is not None
    assert item["provider_group"] == "naver"
    assert "203.0.113.10" in (item.get("peer_ips") or [])
    assert str((item.get("labels") or {}).get("env") or "") == "prod"


def test_cloud_account_update_writes_bootstrap_path_audit_log(client, admin_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)

    create_res = client.post(
        "/api/v1/cloud/accounts",
        json={
            "name": "aws-audit-path",
            "provider": "aws",
            "is_active": True,
            "credentials": {
                "auth_type": "access_key",
                "region": "ap-northeast-2",
                "access_key": "AKIA_AUDIT",
                "secret_key": "SECRET_AUDIT",
            },
        },
        headers=admin_user_token,
    )
    assert create_res.status_code == 200
    account = _payload(create_res)
    account_id = int(account["id"])

    update_res = client.put(
        f"/api/v1/cloud/accounts/{account_id}",
        json={"credentials": {"bootstrap_path": "ssm"}},
        headers=admin_user_token,
    )
    assert update_res.status_code == 200

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.resource_type == "cloud_account")
        .filter(AuditLog.resource_name == f"/api/v1/cloud/accounts/{account_id}")
        .order_by(AuditLog.id.desc())
        .all()
    )
    assert rows, "expected explicit cloud_account audit log rows"

    payload = None
    for row in rows:
        try:
            parsed = json.loads(str(row.details or ""))
            if isinstance(parsed, dict) and str(parsed.get("event") or "") == "cloud_bootstrap_path_update":
                payload = parsed
                break
        except Exception:
            continue

    assert payload is not None, "expected cloud_bootstrap_path_update audit payload"
    assert str(payload.get("bootstrap_path_before") or "") == "auto"
    assert str(payload.get("bootstrap_path_after") or "") == "ssm"


def test_cloud_accounts_list_exposes_execution_readiness(client, admin_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)

    db.add_all(
        [
            CloudAccount(
                name="aws-ready",
                provider="aws",
                credentials={
                    "auth_type": "access_key",
                    "region": "ap-northeast-2",
                    "access_key": "AKIA_READY",
                    "secret_key": "SECRET_READY",
                },
                is_active=True,
                tenant_id=None,
            ),
            CloudAccount(
                name="azure-missing-secret",
                provider="azure",
                credentials={
                    "tenant_id": "tenant-1",
                    "subscription_id": "sub-1",
                    "client_id": "client-1",
                },
                is_active=True,
                tenant_id=None,
            ),
            CloudAccount(
                name="ncp-scaffold",
                provider="ncp",
                credentials={
                    "access_key": "NCP_AK",
                    "secret_key": "NCP_SK",
                },
                is_active=True,
                tenant_id=None,
            ),
        ]
    )
    db.commit()

    res = client.get("/api/v1/cloud/accounts", headers=admin_user_token)
    assert res.status_code == 200
    rows = _payload(res)

    aws_row = next((row for row in rows if str(row.get("name")) == "aws-ready"), None)
    azure_row = next((row for row in rows if str(row.get("name")) == "azure-missing-secret"), None)
    ncp_row = next((row for row in rows if str(row.get("name")) == "ncp-scaffold"), None)

    assert aws_row is not None
    assert azure_row is not None
    assert ncp_row is not None

    assert (aws_row.get("execution_readiness") or {}).get("stage") == "real_apply_ready"
    assert (aws_row.get("execution_readiness") or {}).get("ready_for_real_apply") is True

    assert (azure_row.get("execution_readiness") or {}).get("stage") == "credentials_missing"
    assert "client_secret" in list((azure_row.get("execution_readiness") or {}).get("missing_fields") or [])

    assert (ncp_row.get("execution_readiness") or {}).get("stage") == "real_apply_ready"
    assert (ncp_row.get("execution_readiness") or {}).get("supports_real_apply") is True


def test_cloud_account_operations_ledger_summarizes_recent_runs(client, admin_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    requester = db.query(User).order_by(User.id.asc()).first()
    assert requester is not None

    acc = CloudAccount(
        name="aws-ledger",
        provider="aws",
        credentials={
            "auth_type": "access_key",
            "region": "ap-northeast-2",
            "access_key": "AKIA_LEDGER",
            "secret_key": "SECRET_LEDGER",
        },
        is_active=True,
        tenant_id=None,
        sync_status="failed",
        sync_message="AccessDenied while scanning account",
    )
    db.add(acc)
    db.flush()

    now = datetime.now(timezone.utc)
    db.add_all(
        [
            EventLog(
                device_id=None,
                severity="warning",
                event_id="CLOUD_ACCOUNT_PREFLIGHT",
                source="CloudPreflight",
                timestamp=now - timedelta(minutes=8),
                message=json.dumps(
                    {
                        "event_type": "preflight",
                        "account_id": int(acc.id),
                        "provider": "aws",
                        "status": "failed",
                        "summary": "sts:GetCallerIdentity denied",
                        "blocker_count": 1,
                        "warning_count": 0,
                        "retryable": True,
                    }
                ),
            ),
            EventLog(
                device_id=None,
                severity="warning",
                event_id=CloudPipelineService.KPI_EVENT_ID,
                source="CloudPipeline",
                timestamp=now - timedelta(minutes=5),
                message=json.dumps(
                    {
                        "status": "partial",
                        "accounts": [
                            {
                                "account_id": int(acc.id),
                                "provider": "aws",
                                "preflight_status": "ok",
                                "scan_status": "failed",
                                "scan_count": 0,
                                "message": "AccessDenied: ec2:DescribeInstances",
                            }
                        ],
                    }
                ),
            ),
            EventLog(
                device_id=None,
                severity="info",
                event_id=CloudBootstrapService.KPI_EVENT_ID,
                source="CloudBootstrap",
                timestamp=now - timedelta(minutes=2),
                message=json.dumps(
                    {
                        "status": "ok",
                        "approval_id": 77,
                        "account_ids": [int(acc.id)],
                        "total_targets": 2,
                        "success_targets": 2,
                        "failed_targets": 0,
                        "dry_run_targets": 0,
                        "skipped_targets": 0,
                    }
                ),
            ),
        ]
    )
    db.add(
        ApprovalRequest(
            requester_id=int(requester.id),
            approver_id=None,
            title="Cloud Bootstrap Approval",
            description="pending cloud bootstrap",
            request_type="cloud_bootstrap",
            payload={"account_ids": [int(acc.id)]},
            status="pending",
        )
    )
    db.commit()

    res = client.get("/api/v1/cloud/accounts/operations-ledger", headers=admin_user_token)
    assert res.status_code == 200
    rows = _payload(res)
    assert rows

    ledger = next((row for row in rows if int(row.get("account_id") or 0) == int(acc.id)), None)
    assert ledger is not None
    assert str(ledger.get("operations_posture") or "") == "approval_pending"
    assert int(ledger.get("pending_approvals") or 0) == 1
    assert int(ledger.get("latest_approval_id") or 0) > 0
    assert str(ledger.get("last_operation_type") or "") == "bootstrap"
    assert str(ledger.get("last_operation_status") or "") == "ok"
    assert int(ledger.get("blocker_events") or 0) >= 2
    assert bool(ledger.get("retry_recommended")) is True
    assert str(ledger.get("last_failure_reason_code") or "") == "permission_issue"
    assert str(ledger.get("last_failure_reason_label") or "") == "Permission issue"

    recent_ops = list(ledger.get("recent_operations") or [])
    assert len(recent_ops) >= 3
    labels = {str(item.get("label") or "") for item in recent_ops}
    assert {"Validate", "Pipeline", "Bootstrap"}.issubset(labels)
    failed_ops = [item for item in recent_ops if str(item.get("status") or "").lower() not in {"ok", "success"}]
    assert failed_ops
    assert any(str(item.get("failure_reason_code") or "") == "permission_issue" for item in failed_ops)
