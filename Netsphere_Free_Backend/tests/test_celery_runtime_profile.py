import importlib

import pytest


def test_celery_schedule_respects_runtime_interval_env(monkeypatch):
    pytest.importorskip("celery")
    monkeypatch.setenv("MONITOR_ALL_DEVICES_INTERVAL_SEC", "120")
    monkeypatch.setenv("GNMI_COLLECT_INTERVAL_SEC", "30")
    monkeypatch.setenv("CLOUD_AUTO_SYNC_BEAT_INTERVAL_SEC", "180")

    import celery_app as celery_module

    celery_module = importlib.reload(celery_module)
    schedule = celery_module.celery_app.conf.beat_schedule

    assert schedule["monitor-all-devices-interval"]["schedule"] == 120.0
    assert schedule["collect-gnmi-metrics-interval"]["schedule"] == 30.0
    assert schedule["cloud-auto-sync-interval"]["schedule"] == 180.0


def test_monitoring_worker_env_bounds(monkeypatch):
    from app.tasks import monitoring

    monkeypatch.setenv("MONITOR_ALL_DEVICES_MAX_WORKERS", "999")
    monkeypatch.setenv("GNMI_COLLECT_MAX_WORKERS", "1")

    assert monitoring._env_int("MONITOR_ALL_DEVICES_MAX_WORKERS", 30, minimum=2, maximum=30) == 30
    assert monitoring._env_int("GNMI_COLLECT_MAX_WORKERS", 30, minimum=2, maximum=30) == 2
