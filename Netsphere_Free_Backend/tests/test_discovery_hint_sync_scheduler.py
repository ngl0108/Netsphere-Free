from datetime import datetime

from sqlalchemy.orm import sessionmaker

from app.services.discovery_hint_sync_scheduler import DiscoveryHintSyncScheduler
from app.services.discovery_hint_sync_service import DiscoveryHintSyncService


def _session_factory_for(db):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    return lambda: TestingSessionLocal()


def test_scheduler_runs_pull_and_push_when_due(db, monkeypatch):
    session_factory = _session_factory_for(db)
    monkeypatch.setattr("app.services.discovery_hint_sync_scheduler.SessionLocal", session_factory)
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_SYNC_ENABLED", "true")
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_PULL_INTERVAL_SECONDS", "300")
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_PUSH_INTERVAL_SECONDS", "120")

    calls = []

    def fake_pull(session):
        calls.append("pull")
        return {"status": "ok", "version": "v1"}

    def fake_push(session):
        calls.append("push")
        return {"status": "idle", "uploaded": 0}

    monkeypatch.setattr(DiscoveryHintSyncService, "pull_rule_snapshot", fake_pull)
    monkeypatch.setattr(DiscoveryHintSyncService, "push_recent_telemetry", fake_push)

    scheduler = DiscoveryHintSyncScheduler()
    scheduler._tick_once()

    assert calls == ["pull", "push"]

    session = session_factory()
    try:
        pull_attempt = DiscoveryHintSyncService._get_setting(
            session,
            DiscoveryHintSyncService.SETTING_SCHEDULER_LAST_PULL_ATTEMPT_KEY,
            "",
        )
        push_attempt = DiscoveryHintSyncService._get_setting(
            session,
            DiscoveryHintSyncService.SETTING_SCHEDULER_LAST_PUSH_ATTEMPT_KEY,
            "",
        )
        assert pull_attempt
        assert push_attempt
    finally:
        session.close()


def test_scheduler_skips_when_not_due(db, monkeypatch):
    session_factory = _session_factory_for(db)
    monkeypatch.setattr("app.services.discovery_hint_sync_scheduler.SessionLocal", session_factory)
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_SYNC_ENABLED", "true")
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_PULL_INTERVAL_SECONDS", "3600")
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_PUSH_INTERVAL_SECONDS", "3600")

    session = session_factory()
    try:
        now_iso = datetime.utcnow().isoformat()
        DiscoveryHintSyncService._set_setting(
            session,
            key=DiscoveryHintSyncService.SETTING_SCHEDULER_LAST_PULL_ATTEMPT_KEY,
            value=now_iso,
            description="pull attempt",
        )
        DiscoveryHintSyncService._set_setting(
            session,
            key=DiscoveryHintSyncService.SETTING_SCHEDULER_LAST_PUSH_ATTEMPT_KEY,
            value=now_iso,
            description="push attempt",
        )
        session.commit()
    finally:
        session.close()

    calls = []
    monkeypatch.setattr(DiscoveryHintSyncService, "pull_rule_snapshot", lambda session: calls.append("pull"))
    monkeypatch.setattr(DiscoveryHintSyncService, "push_recent_telemetry", lambda session: calls.append("push"))

    scheduler = DiscoveryHintSyncScheduler()
    scheduler._tick_once()

    assert calls == []
