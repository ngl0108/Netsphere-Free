from sqlalchemy.orm import sessionmaker

from app.services.discovery_hint_rule_service import DiscoveryHintRuleService
from app.services.discovery_hint_sync_service import DiscoveryHintSyncService
from app.services.discovery_hint_telemetry_service import DiscoveryHintTelemetryService


def _session_factory_for(db):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    return TestingSessionLocal


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_pull_rule_snapshot_applies_remote_rules_and_updates_version(db, monkeypatch):
    session_factory = _session_factory_for(db)
    DiscoveryHintRuleService.set_session_factory_for_tests(session_factory)
    DiscoveryHintRuleService.clear_for_tests()
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_SYNC_ENABLED", "true")
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_BASE_URL", "https://hint-core.example")
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return _FakeResponse(
            {
                "success": True,
                "data": {
                    "version": "1:123456",
                    "not_modified": False,
                    "count": 1,
                    "rules": [
                        {
                            "rule_key": "remote-intel-switch",
                            "vendor_family": "handreamnet",
                            "match_conditions": {"ssh_open": True, "raw_vendor_contains": ["intel"]},
                            "driver_overrides": ["handream_sg"],
                            "score_bonus": 0.27,
                            "evidence_count": 4,
                            "source": "telemetry",
                        }
                    ],
                },
            }
        )

    monkeypatch.setattr("app.services.discovery_hint_sync_service.requests.get", fake_get)
    try:
        result = DiscoveryHintSyncService.pull_rule_snapshot(db)
        assert result["status"] == "ok"
        assert result["version"] == "1:123456"
        assert result["upserted"] == 1
        assert captured["url"].endswith("/api/v1/discovery/hints/rules/ota")

        rules = DiscoveryHintRuleService.list_rules_detailed(include_inactive=True)
        assert len(rules) == 1
        assert rules[0]["rule_key"] == "remote-intel-switch"
        assert rules[0]["source"] == DiscoveryHintSyncService.MANAGED_REMOTE_SOURCE

        not_modified = DiscoveryHintSyncService.pull_rule_snapshot(db)
        # same mocked payload still returns ok because mock doesn't honor since_version;
        # at least the persisted version must now be available in settings and request params.
        assert captured["params"]["since_version"] == "1:123456"
        assert not_modified["status"] == "ok"
    finally:
        DiscoveryHintRuleService.clear_for_tests()
        DiscoveryHintRuleService.set_session_factory_for_tests(None)


def test_push_recent_telemetry_uploads_new_events_and_advances_cursor(db, monkeypatch):
    session_factory = _session_factory_for(db)
    DiscoveryHintTelemetryService.set_session_factory_for_tests(session_factory)
    DiscoveryHintTelemetryService.clear_for_tests()
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_SYNC_ENABLED", "true")
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_BASE_URL", "https://hint-core.example")
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse(
            {
                "success": True,
                "data": {
                    "accepted": len(list((json or {}).get("events") or [])),
                    "ingested": len(list((json or {}).get("events") or [])),
                    "ids": [101],
                },
            }
        )

    monkeypatch.setattr("app.services.discovery_hint_sync_service.requests.post", fake_post)
    try:
        first_event_id = DiscoveryHintTelemetryService.record_event(
            {
                "event_type": "hint_success",
                "target_ip": "10.1.1.5",
                "mac": "00:d0:cb:11:22:33",
                "oui_prefix": "00d0cb",
                "raw_vendor": "Dasan Networks",
                "normalized_vendor": "dasan",
                "chosen_driver": "dasan_nos",
                "final_driver": "dasan_nos",
                "success": True,
                "candidates": [{"driver": "dasan_nos", "score": 0.93}],
            }
        )
        assert first_event_id is not None

        result = DiscoveryHintSyncService.push_recent_telemetry(db)
        assert result["status"] == "ok"
        assert result["uploaded"] == 1
        assert result["last_event_id"] == int(first_event_id)
        assert captured["url"].endswith("/api/v1/discovery/hints/telemetry")
        assert len(captured["json"]["events"]) == 1
        assert captured["json"]["events"][0]["event_type"] == "hint_success"

        idle_result = DiscoveryHintSyncService.push_recent_telemetry(db)
        assert idle_result["status"] == "idle"
        assert idle_result["uploaded"] == 0
    finally:
        DiscoveryHintTelemetryService.clear_for_tests()
        DiscoveryHintTelemetryService.set_session_factory_for_tests(None)
