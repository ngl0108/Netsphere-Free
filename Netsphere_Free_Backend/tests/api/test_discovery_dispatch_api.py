from app.api.v1.endpoints import discovery as discovery_ep
from app.models.discovery import DiscoveryJob


def test_discovery_scan_returns_503_when_queue_unavailable(client, operator_user_token, db, monkeypatch):
    monkeypatch.setattr(
        discovery_ep,
        "dispatch_discovery_scan",
        lambda *_args, **_kwargs: {"status": "queue_unavailable", "reason": "no_task_dispatch_api"},
    )

    res = client.post(
        "/api/v1/discovery/scan",
        json={"cidr": "10.20.30.0/24", "community": "public"},
        headers=operator_user_token,
    )
    assert res.status_code == 503

    job = db.query(DiscoveryJob).order_by(DiscoveryJob.id.desc()).first()
    assert job is not None
    assert job.status == "failed"
    assert "Queue dispatch failed" in str(job.logs or "")


def test_discovery_scan_accepts_enqueued_dispatch(client, operator_user_token, db, monkeypatch):
    monkeypatch.setattr(
        discovery_ep,
        "dispatch_discovery_scan",
        lambda *_args, **_kwargs: {"status": "enqueued"},
    )

    res = client.post(
        "/api/v1/discovery/scan",
        json={"cidr": "10.21.30.0/24", "community": "public"},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert payload["cidr"] == "10.21.30.0/24"


def test_discovery_crawl_returns_503_when_queue_unavailable(client, operator_user_token, db, monkeypatch):
    monkeypatch.setattr(
        discovery_ep,
        "dispatch_neighbor_crawl",
        lambda *_args, **_kwargs: {"status": "queue_unavailable", "reason": "no_task_dispatch_api"},
    )

    res = client.post(
        "/api/v1/discovery/crawl",
        json={"seed_ip": "10.30.40.1", "max_depth": 2, "community": "public"},
        headers=operator_user_token,
    )
    assert res.status_code == 503

    job = db.query(DiscoveryJob).order_by(DiscoveryJob.id.desc()).first()
    assert job is not None
    assert job.status == "failed"
    assert "Queue dispatch failed" in str(job.logs or "")

