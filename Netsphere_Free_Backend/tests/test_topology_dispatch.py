from app.tasks import topology_dispatch as mod


def test_dispatch_topology_refresh_enqueues(monkeypatch):
    calls = []

    monkeypatch.setattr(mod, "_idempotency_claim", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        mod.refresh_device_topology,
        "delay",
        lambda *args: calls.append(args),
        raising=False,
    )

    out = mod.dispatch_topology_refresh(
        11,
        discovery_job_id=22,
        max_depth=3,
        idempotency_key="topology:11:22:3",
    )

    assert out["status"] == "enqueued"
    assert out["device_id"] == 11
    assert calls == [(11, 22, 3)]


def test_dispatch_topology_refresh_skips_duplicate(monkeypatch):
    called = {"value": False}

    monkeypatch.setattr(mod, "_idempotency_claim", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        mod.refresh_device_topology,
        "delay",
        lambda *_args, **_kwargs: called.__setitem__("value", True),
        raising=False,
    )

    out = mod.dispatch_topology_refresh(33, discovery_job_id=44, max_depth=2, idempotency_key="dup-key")

    assert out["status"] == "skipped"
    assert out["reason"] == "idempotent_duplicate"
    assert called["value"] is False


def test_dispatch_topology_refresh_uses_embedded_local_executor(monkeypatch):
    recorded = {}

    monkeypatch.setattr(mod, "_idempotency_claim", lambda *args, **kwargs: True)
    monkeypatch.setattr(mod.CollectorRuntimeService, "is_local_embedded_execution_enabled", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        mod.CollectorRuntimeService,
        "enqueue",
        lambda **kwargs: recorded.update(kwargs) or {"status": "enqueued", "executor": "embedded_local"},
    )

    out = mod.dispatch_topology_refresh(88, discovery_job_id=12, max_depth=2, idempotency_key="topology:88")

    assert out["status"] == "enqueued"
    assert out["executor"] == "embedded_local"
    assert recorded["args"] == [88, 12, 2]
