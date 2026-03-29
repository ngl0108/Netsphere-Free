from sqlalchemy.orm import sessionmaker

from app.services.discovery_hint_rule_service import DiscoveryHintRuleService
from app.services.discovery_hint_seed_rule_service import DiscoveryHintSeedRuleService


def test_installing_seed_rules_adds_domestic_hint_overrides(db):
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    DiscoveryHintRuleService.set_session_factory_for_tests(factory)
    try:
        DiscoveryHintRuleService.clear_for_tests()
        result = DiscoveryHintSeedRuleService.install_defaults()
        assert result["installed"] == result["available"]

        candidates = DiscoveryHintRuleService.evaluate_overrides(
            cache_hit={"neighbor_name": "SG2400", "seed_vendor": "domestic-l3-core"},
            raw_vendor="Intel Corporate",
            normalized_vendor="intel",
            open_ports=[22],
        )
        assert candidates
        assert candidates[0]["driver"] == "handream_sg"

        piolink = DiscoveryHintRuleService.evaluate_overrides(
            cache_hit={"neighbor_name": "PIOLINK-AGG", "seed_vendor": "domestic-l3-core"},
            raw_vendor="Piolink Corporation",
            normalized_vendor="piolink",
            open_ports=[22],
        )
        assert piolink
        assert piolink[0]["driver"] == "piolink_pas"

        nst = DiscoveryHintRuleService.evaluate_overrides(
            cache_hit={"neighbor_name": "NST2400", "seed_vendor": "domestic-l3-core"},
            raw_vendor="Broadcom NST Switch",
            normalized_vendor="nst",
            open_ports=[22],
        )
        assert nst
        assert nst[0]["driver"] == "nst_switch"

        efm = DiscoveryHintRuleService.evaluate_overrides(
            cache_hit={"neighbor_name": "ipTIME-AX3000", "seed_vendor": "domestic-l3-core"},
            raw_vendor="Ralink Technology",
            normalized_vendor="efmnetworks",
            open_ports=[22],
        )
        assert efm
        assert efm[0]["driver"] == "linux"

        davolink = DiscoveryHintRuleService.evaluate_overrides(
            cache_hit={"neighbor_name": "DAVOLINK-EDGE", "seed_vendor": "domestic-l3-core"},
            raw_vendor="Davolink Realtek Switch",
            normalized_vendor="davolink",
            open_ports=[22],
        )
        assert davolink
        assert davolink[0]["driver"] == "linux"
    finally:
        DiscoveryHintRuleService.clear_for_tests()
        DiscoveryHintRuleService.set_session_factory_for_tests(None)


def test_installing_seed_rules_is_idempotent(db):
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    DiscoveryHintRuleService.set_session_factory_for_tests(factory)
    try:
        DiscoveryHintRuleService.clear_for_tests()
        first = DiscoveryHintSeedRuleService.install_defaults()
        second = DiscoveryHintSeedRuleService.install_defaults()
        assert first["installed"] == first["available"]
        assert second["installed"] == 0
        listed = DiscoveryHintRuleService.list_rules_detailed(include_inactive=True)
        assert len(listed) == first["available"]
    finally:
        DiscoveryHintRuleService.clear_for_tests()
        DiscoveryHintRuleService.set_session_factory_for_tests(None)
