from app.services.auto_discovery_scheduler import AutoDiscoveryScheduler
from app.tasks import discovery_dispatch as dispatch_mod


def test_launch_scan_uses_discovery_dispatch(monkeypatch):
    calls = []

    def fake_scan(job_id, **kwargs):
        calls.append((job_id, kwargs))
        return {"status": "enqueued", "job_id": int(job_id)}

    monkeypatch.setattr(dispatch_mod, "dispatch_discovery_scan", fake_scan)

    out = AutoDiscoveryScheduler()._launch_scan(123)

    assert out["status"] == "enqueued"
    assert calls == [(123, {"idempotency_key": "auto-scheduler-scan:123"})]


def test_launch_crawl_uses_discovery_dispatch(monkeypatch):
    calls = []

    def fake_crawl(job_id, **kwargs):
        calls.append((job_id, kwargs))
        return {"status": "enqueued", "job_id": int(job_id)}

    monkeypatch.setattr(dispatch_mod, "dispatch_neighbor_crawl", fake_crawl)

    out = AutoDiscoveryScheduler()._launch_crawl(
        456,
        seed_device_id=7,
        seed_ip="10.10.10.7",
        max_depth=3,
    )

    assert out["status"] == "enqueued"
    assert calls == [
        (
            456,
            {
                "seed_device_id": 7,
                "seed_ip": "10.10.10.7",
                "max_depth": 3,
                "idempotency_key": "auto-scheduler-crawl:456",
            },
        )
    ]
