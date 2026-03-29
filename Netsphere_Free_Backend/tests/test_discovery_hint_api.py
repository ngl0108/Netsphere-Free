from sqlalchemy.orm import sessionmaker

from app.models.settings import SystemSetting
from app.services.discovery_hint_rule_service import DiscoveryHintRuleService
from app.services.discovery_hint_sync_service import DiscoveryHintSyncService
from app.services.discovery_hint_telemetry_service import DiscoveryHintTelemetryService
from app.services.oui_service import OUIService


def _session_factory_for(db):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    return lambda: TestingSessionLocal()


def _unwrap(response):
    body = response.json()
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_discovery_hint_rule_management_and_ota_snapshot(client, db, admin_user_token, normal_user_token):
    session_factory = _session_factory_for(db)
    DiscoveryHintRuleService.set_session_factory_for_tests(session_factory)
    DiscoveryHintRuleService.clear_for_tests()
    try:
        payload = {
            "rules": [
                {
                    "rule_key": "intel-switch-override",
                    "vendor_family": "handreamnet",
                    "match_conditions": {
                        "ssh_open": True,
                        "raw_vendor_contains": ["intel"],
                    },
                    "driver_overrides": ["handream_sg", "domestic_cisco_like"],
                    "score_bonus": 0.41,
                    "evidence_count": 3,
                    "source": "telemetry",
                    "is_active": True,
                }
            ]
        }
        post_response = client.post("/api/v1/discovery/hints/rules", headers=admin_user_token, json=payload)
        assert post_response.status_code == 200, post_response.text
        post_body = _unwrap(post_response)
        assert post_body["accepted"] == 1
        assert post_body["upserted"] == 1
        assert isinstance(post_body["version"], str) and ":" in post_body["version"]

        list_response = client.get("/api/v1/discovery/hints/rules", headers=admin_user_token)
        assert list_response.status_code == 200, list_response.text
        list_body = _unwrap(list_response)
        assert list_body["count"] == 1
        assert list_body["active_count"] == 1
        assert list_body["items"][0]["rule_key"] == "intel-switch-override"
        assert list_body["items"][0]["vendor_family"] == "handreamnet"

        snapshot_response = client.get("/api/v1/discovery/hints/rules/ota", headers=normal_user_token)
        assert snapshot_response.status_code == 200, snapshot_response.text
        snapshot_body = _unwrap(snapshot_response)
        assert snapshot_body["count"] == 1
        assert snapshot_body["not_modified"] is False
        assert snapshot_body["rules"][0]["driver_overrides"][0] == "handream_sg"

        same_version_response = client.get(
            f"/api/v1/discovery/hints/rules/ota?since_version={snapshot_body['version']}",
            headers=normal_user_token,
        )
        assert same_version_response.status_code == 200, same_version_response.text
        same_version_body = _unwrap(same_version_response)
        assert same_version_body["not_modified"] is True
        assert same_version_body["rules"] == []
    finally:
        DiscoveryHintRuleService.clear_for_tests()
        DiscoveryHintRuleService.set_session_factory_for_tests(None)


def test_discovery_hint_telemetry_ingest_and_list(client, db, admin_user_token, operator_user_token):
    session_factory = _session_factory_for(db)
    DiscoveryHintTelemetryService.set_session_factory_for_tests(session_factory)
    DiscoveryHintTelemetryService.clear_for_tests()
    try:
        payload = {
            "events": [
                {
                    "event_type": "hint_false_positive",
                    "target_ip": "10.10.10.12",
                    "mac": "00:D0:CB:11:22:33",
                    "oui_prefix": "00:D0:CB",
                    "raw_vendor": "Intel",
                    "normalized_vendor": "unknown",
                    "seed_device_id": 7,
                    "seed_ip": "10.10.10.1",
                    "seed_vendor": "dasan",
                    "local_interface": "gi1/0/24",
                    "neighbor_name": "SG2400",
                    "chosen_driver": "generic_linux",
                    "final_driver": "handream_sg",
                    "success": True,
                    "candidates": [{"driver": "handream_sg", "score": 0.91}],
                }
            ]
        }
        ingest_response = client.post("/api/v1/discovery/hints/telemetry", headers=operator_user_token, json=payload)
        assert ingest_response.status_code == 200, ingest_response.text
        ingest_body = _unwrap(ingest_response)
        assert ingest_body["accepted"] == 1
        assert ingest_body["ingested"] == 1
        assert len(ingest_body["ids"]) == 1

        list_response = client.get("/api/v1/discovery/hints/telemetry?include_payload=true", headers=admin_user_token)
        assert list_response.status_code == 200, list_response.text
        list_body = _unwrap(list_response)
        assert list_body["count"] == 1
        item = list_body["items"][0]
        assert item["event_type"] == "hint_false_positive"
        assert item["normalized_vendor"] == "unknown"
        assert item["final_driver"] == "handream_sg"
        assert item["payload"]["neighbor_name"] == "SG2400"
    finally:
        DiscoveryHintTelemetryService.clear_for_tests()
        DiscoveryHintTelemetryService.set_session_factory_for_tests(None)


def test_discovery_hint_seed_defaults_and_summary_endpoints(client, db, admin_user_token):
    rule_session_factory = _session_factory_for(db)
    telemetry_session_factory = _session_factory_for(db)
    DiscoveryHintRuleService.set_session_factory_for_tests(rule_session_factory)
    DiscoveryHintTelemetryService.set_session_factory_for_tests(telemetry_session_factory)
    DiscoveryHintRuleService.clear_for_tests()
    DiscoveryHintTelemetryService.clear_for_tests()
    try:
        seed_response = client.post("/api/v1/discovery/hints/rules/seed-defaults", headers=admin_user_token)
        assert seed_response.status_code == 200, seed_response.text
        seed_body = _unwrap(seed_response)
        assert seed_body["installed"] >= 1
        assert isinstance(seed_body["version"], str) and ":" in seed_body["version"]

        DiscoveryHintTelemetryService.record_event(
            {
                "event_type": "hint_success",
                "normalized_vendor": "dasan",
                "chosen_driver": "dasan_nos",
                "final_driver": "dasan_nos",
                "success": True,
            }
        )
        summary_response = client.get("/api/v1/discovery/hints/telemetry/summary", headers=admin_user_token)
        assert summary_response.status_code == 200, summary_response.text
        summary_body = _unwrap(summary_response)
        assert summary_body["summary"]["total"] == 1
        assert summary_body["summary"]["success"] == 1
        assert summary_body["summary"]["success_rate_pct"] == 100.0
    finally:
        DiscoveryHintRuleService.clear_for_tests()
        DiscoveryHintTelemetryService.clear_for_tests()
        DiscoveryHintRuleService.set_session_factory_for_tests(None)
        DiscoveryHintTelemetryService.set_session_factory_for_tests(None)


def test_discovery_hint_operational_summary_endpoint(client, db, admin_user_token, monkeypatch):
    rule_session_factory = _session_factory_for(db)
    telemetry_session_factory = _session_factory_for(db)
    DiscoveryHintRuleService.set_session_factory_for_tests(rule_session_factory)
    DiscoveryHintTelemetryService.set_session_factory_for_tests(telemetry_session_factory)
    DiscoveryHintRuleService.clear_for_tests()
    DiscoveryHintTelemetryService.clear_for_tests()
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_SYNC_ENABLED", "true")
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_BASE_URL", "https://hint-core.example")
    monkeypatch.setenv("DISCOVERY_HINT_REMOTE_BEARER_TOKEN", "token")
    try:
        DiscoveryHintRuleService.upsert_rule(
            {
                "rule_key": "dasan-default",
                "vendor_family": "dasan",
                "match_conditions": {"oui_prefixes": ["00:D0:CB"]},
                "driver_overrides": ["dasan_nos"],
                "score_bonus": 0.55,
                "source": "seed",
                "is_active": True,
            }
        )
        DiscoveryHintTelemetryService.record_event(
            {
                "event_type": "hint_success",
                "normalized_vendor": "dasan",
                "chosen_driver": "dasan_nos",
                "final_driver": "dasan_nos",
                "success": True,
            }
        )
        db.add(SystemSetting(key=DiscoveryHintSyncService.SETTING_RULE_VERSION_KEY, value="v1", description="v", category="discovery_hint"))
        db.add(SystemSetting(key=DiscoveryHintSyncService.SETTING_PULL_STATUS_KEY, value="ok:v1", description="pull", category="discovery_hint"))
        db.add(SystemSetting(key=DiscoveryHintSyncService.SETTING_PUSH_STATUS_KEY, value="idle:0", description="push", category="discovery_hint"))
        db.commit()

        response = client.get("/api/v1/discovery/hints/summary", headers=admin_user_token)
        assert response.status_code == 200, response.text
        body = _unwrap(response)
        assert body["sync"]["enabled"] is True
        assert body["sync"]["base_url_configured"] is True
        assert body["sync"]["bearer_configured"] is True
        assert body["rules"]["active"] == 1
        assert body["benchmark"]["summary"]["success"] == 1
        assert body["sync"]["last_pull_status"] == "ok:v1"
        assert isinstance(body["recommendations"], list)
        assert isinstance(body["score_adjustments"], list)
        assert isinstance(body["alias_candidates"], list)
        assert isinstance(body["seed_rule_drafts"], list)
        assert isinstance(body["benchmark_trend"], dict)
        assert isinstance(body["false_positive_hotspots"], list)
    finally:
        DiscoveryHintRuleService.clear_for_tests()
        DiscoveryHintTelemetryService.clear_for_tests()
        DiscoveryHintRuleService.set_session_factory_for_tests(None)
        DiscoveryHintTelemetryService.set_session_factory_for_tests(None)


def test_discovery_hint_apply_score_adjustments_endpoint(client, db, admin_user_token):
    rule_session_factory = _session_factory_for(db)
    telemetry_session_factory = _session_factory_for(db)
    DiscoveryHintRuleService.set_session_factory_for_tests(rule_session_factory)
    DiscoveryHintTelemetryService.set_session_factory_for_tests(telemetry_session_factory)
    DiscoveryHintRuleService.clear_for_tests()
    DiscoveryHintTelemetryService.clear_for_tests()
    try:
        DiscoveryHintRuleService.upsert_rule(
            {
                "rule_key": "dasan-default",
                "vendor_family": "dasan",
                "match_conditions": {"oui_prefixes": ["00:D0:CB"]},
                "driver_overrides": ["dasan_nos"],
                "score_bonus": 0.55,
                "source": "seed",
                "is_active": True,
            }
        )
        DiscoveryHintRuleService.upsert_rule(
            {
                "rule_key": "handreamnet-intel-override",
                "vendor_family": "handreamnet",
                "match_conditions": {"raw_vendor_contains": ["intel"], "ssh_open": True},
                "driver_overrides": ["handream_sg"],
                "score_bonus": 0.35,
                "source": "seed",
                "is_active": True,
            }
        )

        for _ in range(5):
            DiscoveryHintTelemetryService.record_event(
                {
                    "event_type": "hint_success",
                    "normalized_vendor": "dasan",
                    "chosen_driver": "dasan_nos",
                    "final_driver": "dasan_nos",
                    "success": True,
                }
            )
        for _ in range(4):
            DiscoveryHintTelemetryService.record_event(
                {
                    "event_type": "hint_false_positive",
                    "normalized_vendor": "handreamnet",
                    "chosen_driver": "handream_sg",
                    "final_driver": "generic_linux",
                    "success": False,
                }
            )

        response = client.post(
            "/api/v1/discovery/hints/rules/score-adjustments/apply",
            headers=admin_user_token,
            json={},
        )
        assert response.status_code == 200, response.text
        body = _unwrap(response)
        assert body["accepted"] >= 2
        assert body["applied"] >= 2
        assert "dasan-default" in body["rule_keys"]
        assert "handreamnet-intel-override" in body["rule_keys"]

        list_response = client.get("/api/v1/discovery/hints/rules", headers=admin_user_token)
        assert list_response.status_code == 200, list_response.text
        list_body = _unwrap(list_response)
        items = {item["rule_key"]: item for item in list_body["items"]}
        assert float(items["dasan-default"]["score_bonus"]) > 0.55
        assert float(items["handreamnet-intel-override"]["score_bonus"]) < 0.35
    finally:
        DiscoveryHintRuleService.clear_for_tests()
        DiscoveryHintTelemetryService.clear_for_tests()
        DiscoveryHintRuleService.set_session_factory_for_tests(None)
        DiscoveryHintTelemetryService.set_session_factory_for_tests(None)


def test_discovery_hint_apply_alias_candidates_and_seed_rule_drafts(client, db, admin_user_token):
    session_factory = _session_factory_for(db)
    DiscoveryHintRuleService.set_session_factory_for_tests(session_factory)
    DiscoveryHintTelemetryService.set_session_factory_for_tests(session_factory)
    OUIService.set_session_factory_for_tests(session_factory)
    DiscoveryHintRuleService.clear_for_tests()
    DiscoveryHintTelemetryService.clear_for_tests()
    OUIService.clear_aliases_for_tests()
    try:
        for _ in range(2):
            DiscoveryHintTelemetryService.record_event(
                {
                    "event_type": "hint_success",
                    "raw_vendor": "HDN Corp",
                    "chosen_driver": "handream_sg",
                    "final_driver": "handream_sg",
                    "success": True,
                }
            )
        for neighbor in ("SG2400", "SG2408"):
            DiscoveryHintTelemetryService.record_event(
                {
                    "event_type": "chipset_oui_override",
                    "raw_vendor": "Intel Corporation",
                    "seed_vendor": "dasan",
                    "neighbor_name": neighbor,
                    "chosen_driver": "handream_sg",
                    "final_driver": "handream_sg",
                    "success": True,
                }
            )

        alias_response = client.post(
            "/api/v1/discovery/hints/rules/alias-candidates/apply",
            headers=admin_user_token,
            json={},
        )
        assert alias_response.status_code == 200, alias_response.text
        alias_body = _unwrap(alias_response)
        assert alias_body["accepted"] >= 1
        assert alias_body["applied"] >= 1
        assert "HDN Corp" in alias_body["raw_vendors"]
        assert OUIService.normalize_vendor_name("HDN Corp") == "HanDreamnet"

        draft_response = client.post(
            "/api/v1/discovery/hints/rules/seed-rule-drafts/apply",
            headers=admin_user_token,
            json={},
        )
        assert draft_response.status_code == 200, draft_response.text
        draft_body = _unwrap(draft_response)
        assert draft_body["accepted"] >= 1
        assert draft_body["applied"] >= 1
        assert "draft-handreamnet-intel-handream-sg" in draft_body["rule_keys"]

        list_response = client.get("/api/v1/discovery/hints/rules", headers=admin_user_token)
        assert list_response.status_code == 200, list_response.text
        list_body = _unwrap(list_response)
        items = {item["rule_key"]: item for item in list_body["items"]}
        assert "draft-handreamnet-intel-handream-sg" in items
        assert items["draft-handreamnet-intel-handream-sg"]["driver_overrides"] == ["handream_sg"]
    finally:
        DiscoveryHintRuleService.clear_for_tests()
        DiscoveryHintTelemetryService.clear_for_tests()
        OUIService.clear_aliases_for_tests()
        DiscoveryHintRuleService.set_session_factory_for_tests(None)
        DiscoveryHintTelemetryService.set_session_factory_for_tests(None)
        OUIService.set_session_factory_for_tests(None)
