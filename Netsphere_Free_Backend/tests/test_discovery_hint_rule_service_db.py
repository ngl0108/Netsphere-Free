from sqlalchemy.orm import sessionmaker

from app.services.discovery_hint_rule_service import DiscoveryHintRuleService


def test_db_backed_rule_override_is_applied(db):
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    DiscoveryHintRuleService.set_session_factory_for_tests(factory)
    try:
        DiscoveryHintRuleService.clear_for_tests()
        inserted_id = DiscoveryHintRuleService.upsert_rule(
            {
                "rule_key": "intel-handreamnet-override",
                "vendor_family": "HanDreamnet",
                "match_conditions": {
                    "ssh_open": True,
                    "raw_vendor_contains": ["intel"],
                    "neighbor_name_regex": "sg24",
                },
                "driver_overrides": ["handream_sg"],
                "score_bonus": 0.31,
                "source": "telemetry",
                "is_active": True,
            }
        )

        assert inserted_id is not None
        candidates = DiscoveryHintRuleService.evaluate_overrides(
            cache_hit={"neighbor_name": "Handream SG2400", "seed_vendor": "Domestic L3 Core"},
            raw_vendor="Intel Corporate",
            normalized_vendor="Intel Corporate",
            open_ports=[22],
        )

        assert candidates
        assert candidates[0]["driver"] == "handream_sg"
        assert "central_rule_override" in candidates[0]["reasons"]
    finally:
        DiscoveryHintRuleService.clear_for_tests()
        DiscoveryHintRuleService.set_session_factory_for_tests(None)


def test_rule_service_normalizes_legacy_driver_aliases(db):
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    DiscoveryHintRuleService.set_session_factory_for_tests(factory)
    try:
        DiscoveryHintRuleService.clear_for_tests()
        inserted_id = DiscoveryHintRuleService.upsert_rule(
            {
                "rule_key": "legacy-handream-driver-alias",
                "vendor_family": "HanDreamnet",
                "match_conditions": {
                    "ssh_open": True,
                    "raw_vendor_contains": ["intel"],
                },
                "driver_overrides": ["handreamnet_sg"],
                "score_bonus": 0.29,
                "source": "telemetry",
                "is_active": True,
            }
        )

        assert inserted_id is not None
        listed = DiscoveryHintRuleService.list_rules_detailed(include_inactive=True)
        assert listed[0]["driver_overrides"] == ["handream_sg"]
    finally:
        DiscoveryHintRuleService.clear_for_tests()
        DiscoveryHintRuleService.set_session_factory_for_tests(None)
