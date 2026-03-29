from app.tasks import discovery_dispatch as mod


def test_dispatch_discovery_scan_enqueues(monkeypatch):
    calls = []

    monkeypatch.setattr(mod, "_idempotency_claim", lambda *args, **kwargs: True)
    monkeypatch.setattr(mod.run_discovery_job, "delay", lambda job_id: calls.append(job_id), raising=False)

    out = mod.dispatch_discovery_scan(101, idempotency_key="scan:101")

    assert out["status"] == "enqueued"
    assert out["job_id"] == 101
    assert calls == [101]


def test_dispatch_discovery_scan_skips_duplicate(monkeypatch):
    called = {"value": False}

    monkeypatch.setattr(mod, "_idempotency_claim", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        mod.run_discovery_job,
        "delay",
        lambda *_args, **_kwargs: called.__setitem__("value", True),
        raising=False,
    )

    out = mod.dispatch_discovery_scan(202, idempotency_key="scan:202")

    assert out["status"] == "skipped"
    assert out["reason"] == "idempotent_duplicate"
    assert called["value"] is False


def test_dispatch_discovery_scan_reports_queue_unavailable(monkeypatch):
    monkeypatch.setattr(mod, "_idempotency_claim", lambda *args, **kwargs: True)
    monkeypatch.delattr(mod.run_discovery_job, "delay", raising=False)
    monkeypatch.delattr(mod.run_discovery_job, "apply_async", raising=False)

    out = mod.dispatch_discovery_scan(303, idempotency_key="scan:303")

    assert out["status"] == "queue_unavailable"
    assert out["reason"] == "no_task_dispatch_api"


def test_dispatch_neighbor_crawl_enqueues(monkeypatch):
    calls = []

    monkeypatch.setattr(mod, "_idempotency_claim", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        mod.run_neighbor_crawl_job,
        "delay",
        lambda *args: calls.append(args),
        raising=False,
    )

    out = mod.dispatch_neighbor_crawl(
        404,
        seed_device_id=77,
        seed_ip="10.1.1.1",
        max_depth=4,
        idempotency_key="crawl:404",
    )

    assert out["status"] == "enqueued"
    assert calls == [(404, 77, "10.1.1.1", 4)]


def test_dispatch_discovery_hint_prefetch_enqueues(monkeypatch):
    calls = []

    monkeypatch.setattr(mod, "_idempotency_claim", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        mod.run_discovery_hint_prefetch_job,
        "delay",
        lambda *args: calls.append(args),
        raising=False,
    )

    out = mod.dispatch_discovery_hint_prefetch(
        505,
        seed_device_id=88,
        seed_ip="10.2.2.2",
        idempotency_key="hint-prefetch:505",
    )

    assert out["status"] == "enqueued"
    assert calls == [(505, 88, "10.2.2.2")]


def test_dispatch_discovery_scan_uses_embedded_local_executor(monkeypatch):
    recorded = {}

    monkeypatch.setattr(mod, "_idempotency_claim", lambda *args, **kwargs: True)
    monkeypatch.setattr(mod.CollectorRuntimeService, "is_local_embedded_execution_enabled", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        mod.CollectorRuntimeService,
        "enqueue",
        lambda **kwargs: recorded.update(kwargs) or {"status": "enqueued", "executor": "embedded_local"},
    )

    out = mod.dispatch_discovery_scan(505, idempotency_key="scan:505")

    assert out["status"] == "enqueued"
    assert out["executor"] == "embedded_local"
    assert recorded["task_name"]
    assert recorded["args"] == [505]
