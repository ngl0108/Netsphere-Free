import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.tasks import device_sync


def test_enqueue_ssh_sync_batch_schedules_with_countdown(monkeypatch):
    scheduled = []

    def fake_apply_async(*, args=None, countdown=None, **kwargs):
        scheduled.append((args, countdown))
        return None

    monkeypatch.setattr(device_sync.ssh_sync_device, "apply_async", fake_apply_async, raising=False)

    res = device_sync.enqueue_ssh_sync_batch([10, 20, 30], interval_seconds=2.0, jitter_seconds=0.0)
    assert res["scheduled"] == 3

    assert scheduled[0][0] == [10]
    assert scheduled[0][1] == 0.0
    assert scheduled[1][0] == [20]
    assert scheduled[1][1] == 2.0
    assert scheduled[2][0] == [30]
    assert scheduled[2][1] == 4.0


def test_enqueue_ssh_sync_batch_uses_stable_idempotency_prefix(monkeypatch):
    calls = []

    def fake_dispatch(device_id, *, idempotency_key=None, countdown=None):
        calls.append((device_id, idempotency_key, countdown))
        return {"status": "enqueued"}

    monkeypatch.setattr(device_sync, "dispatch_device_sync", fake_dispatch)

    res = device_sync.enqueue_ssh_sync_batch(
        [7, 8],
        interval_seconds=1.0,
        jitter_seconds=0.0,
        idempotency_prefix="approve-all:55",
    )

    assert res["scheduled"] == 2
    assert calls[0][1] == "batch:approve-all:55:7"
    assert calls[1][1] == "batch:approve-all:55:8"


def test_schedule_ssh_sync_batch_uses_embedded_local_path(monkeypatch):
    called = {}

    monkeypatch.setattr(device_sync.CollectorRuntimeService, "is_local_embedded_execution_enabled", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        device_sync,
        "enqueue_ssh_sync_batch",
        lambda *args, **kwargs: called.update({"args": args, "kwargs": kwargs}) or {"scheduled": 1},
    )

    res = device_sync.schedule_ssh_sync_batch([101], interval_seconds=0.0, jitter_seconds=0.0, idempotency_prefix="preview")

    assert res["scheduled"] == 1
    assert called["args"][0] == [101]
