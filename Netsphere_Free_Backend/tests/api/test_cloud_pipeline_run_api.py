from datetime import datetime, timedelta, timezone

from app.core.license import LicenseSchema
from app.models.cloud import CloudAccount, CloudResource
from app.models.settings import SystemSetting
from app.services.cloud_service import CloudScanner
from app.services.hybrid_topology_service import HybridTopologyService
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


def test_cloud_pipeline_run_for_target_account(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)

    acc = CloudAccount(
        name="aws-prod",
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
            resource_id="vpn-1",
            resource_type="vpn_connection",
            name="vpn-main",
            region="ap-northeast-2",
            state="available",
            resource_metadata={"tunnels": [{"outside_ip": "203.0.113.10"}]},
        )
    )
    db.commit()

    async def _fake_preflight(self):
        return {"provider": "aws", "status": "ok", "summary": "ok", "checks": [{"key": "sts", "ok": True, "message": "ok"}]}

    async def _fake_scan(self):
        return [{"resource_id": "r1"}, {"resource_id": "r2"}]

    monkeypatch.setattr(CloudScanner, "preflight", _fake_preflight)
    monkeypatch.setattr(CloudScanner, "scan", _fake_scan)
    monkeypatch.setattr(
        HybridTopologyService,
        "build_cloud_peer_links",
        staticmethod(lambda *_a, **_k: {"created_virtual_devices": 1, "updated_virtual_devices": 0, "created_links": 1, "updated_links": 0, "skipped": 0}),
    )
    monkeypatch.setattr(
        HybridTopologyService,
        "build_inferred_cloud_links",
        staticmethod(lambda *_a, **_k: {"created_virtual_devices": 0, "updated_virtual_devices": 1, "created_links": 1, "updated_links": 0, "skipped": 0}),
    )

    res = client.post(
        "/api/v1/cloud/pipeline/run",
        json={
            "account_ids": [int(acc.id)],
            "preflight": True,
            "include_hybrid_build": True,
            "include_hybrid_infer": True,
            "idempotency_key": "pipeline-aws-1",
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    data = _payload(res)
    assert str(data.get("status")) == "ok"
    assert int(data.get("total_accounts") or 0) == 1
    assert int(data.get("scanned_resources") or 0) == 2
    assert int(data.get("failed_accounts") or 0) == 0
    assert int((data.get("normalized_by_provider") or {}).get("aws") or 0) >= 1
    assert isinstance(data.get("hybrid_build"), dict)
    assert isinstance(data.get("hybrid_infer"), dict)

    kpi = client.get("/api/v1/cloud/kpi/summary?days=30", headers=operator_user_token)
    assert kpi.status_code == 200
    kpi_data = _payload(kpi)
    assert int(kpi_data.get("runs") or 0) >= 1
    assert "auto_reflection_rate_pct" in kpi_data


def test_cloud_pipeline_idempotency_blocks_duplicate(client, operator_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)

    acc = CloudAccount(
        name="azure-prod",
        provider="azure",
        credentials={"tenant_id": "t1", "subscription_id": "s1", "client_id": "c1", "client_secret": "x"},
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.commit()

    calls = {"scan": 0}

    async def _fake_preflight(self):
        return {"provider": "azure", "status": "ok", "summary": "ok", "checks": [{"key": "aad", "ok": True, "message": "ok"}]}

    async def _fake_scan(self):
        calls["scan"] += 1
        return [{"resource_id": "vnet-1"}]

    monkeypatch.setattr(CloudScanner, "preflight", _fake_preflight)
    monkeypatch.setattr(CloudScanner, "scan", _fake_scan)
    monkeypatch.setattr(
        HybridTopologyService,
        "build_cloud_peer_links",
        staticmethod(lambda *_a, **_k: {"created_virtual_devices": 0, "updated_virtual_devices": 0, "created_links": 0, "updated_links": 0, "skipped": 0}),
    )
    monkeypatch.setattr(
        HybridTopologyService,
        "build_inferred_cloud_links",
        staticmethod(lambda *_a, **_k: {"created_virtual_devices": 0, "updated_virtual_devices": 0, "created_links": 0, "updated_links": 0, "skipped": 0}),
    )

    payload = {
        "account_ids": [int(acc.id)],
        "preflight": True,
        "include_hybrid_build": True,
        "include_hybrid_infer": True,
        "idempotency_key": "pipeline-dup-1",
    }
    first = client.post("/api/v1/cloud/pipeline/run", json=payload, headers=operator_user_token)
    assert first.status_code == 200
    assert str(_payload(first).get("status")) == "ok"

    second = client.post("/api/v1/cloud/pipeline/run", json=payload, headers=operator_user_token)
    assert second.status_code == 200
    assert str(_payload(second).get("status")) == "skipped_duplicate"
    assert calls["scan"] == 1


def test_cloud_account_pipeline_requires_existing_account(client, admin_user_token, db, monkeypatch):
    _enable_cloud_scope(db, monkeypatch)
    res = client.post(
        "/api/v1/cloud/accounts/99999/pipeline/run",
        json={"preflight": True},
        headers=admin_user_token,
    )
    assert res.status_code == 404
