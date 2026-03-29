from app.services.discovery_hint_tuning_service import DiscoveryHintTuningService


def test_discovery_hint_tuning_service_highlights_vendor_and_driver_hotspots():
    benchmark = {
        "by_vendor": [
            {
                "vendor": "efmnetworks",
                "total": 3,
                "success": 1,
                "false_positive": 0,
                "unknown_after_hint": 2,
                "success_rate_pct": 33.33,
            },
            {
                "vendor": "handreamnet",
                "total": 2,
                "success": 1,
                "false_positive": 1,
                "unknown_after_hint": 0,
                "success_rate_pct": 50.0,
            },
        ],
        "by_driver": [
            {
                "driver": "linux",
                "vendor": "efmnetworks",
                "total": 3,
                "success": 1,
                "false_positive": 0,
                "unknown_after_hint": 2,
                "success_rate_pct": 33.33,
            },
            {
                "driver": "handream_sg",
                "vendor": "handreamnet",
                "total": 2,
                "success": 1,
                "false_positive": 1,
                "unknown_after_hint": 0,
                "success_rate_pct": 50.0,
            },
        ],
        "opportunity_vendors": [
            {
                "vendor": "efmnetworks",
                "total": 3,
                "success": 1,
                "false_positive": 0,
                "unknown_after_hint": 2,
                "success_rate_pct": 33.33,
            },
            {
                "vendor": "handreamnet",
                "total": 2,
                "success": 1,
                "false_positive": 1,
                "unknown_after_hint": 0,
                "success_rate_pct": 50.0,
            },
        ],
        "opportunity_drivers": [
            {
                "driver": "linux",
                "vendor": "efmnetworks",
                "total": 3,
                "success": 1,
                "false_positive": 0,
                "unknown_after_hint": 2,
                "success_rate_pct": 33.33,
            },
            {
                "driver": "handream_sg",
                "vendor": "handreamnet",
                "total": 2,
                "success": 1,
                "false_positive": 1,
                "unknown_after_hint": 0,
                "success_rate_pct": 50.0,
            },
        ],
    }
    active_rules = [{"vendor_family": "handreamnet", "is_active": True}]

    recommendations = DiscoveryHintTuningService.build_recommendations(
        benchmark=benchmark,
        active_rules=active_rules,
    )

    assert recommendations
    kinds = {item["kind"] for item in recommendations}
    assert "seed_rule_gap" in kinds
    assert "driver_false_positive" in kinds
    assert any(item["scope"] == "vendor:efmnetworks" for item in recommendations)
    assert any(item["scope"] == "driver:linux" for item in recommendations)


def test_discovery_hint_tuning_service_builds_score_adjustments():
    benchmark = {
        "by_vendor": [
            {
                "vendor": "handreamnet",
                "total": 5,
                "success": 2,
                "false_positive": 2,
                "unknown_after_hint": 0,
                "success_rate_pct": 40.0,
            },
            {
                "vendor": "dasan",
                "total": 4,
                "success": 4,
                "false_positive": 0,
                "unknown_after_hint": 0,
                "success_rate_pct": 100.0,
            },
        ],
        "by_driver": [
            {
                "driver": "handream_sg",
                "vendor": "handreamnet",
                "total": 5,
                "success": 2,
                "false_positive": 2,
                "unknown_after_hint": 0,
                "success_rate_pct": 40.0,
            },
            {
                "driver": "dasan_nos",
                "vendor": "dasan",
                "total": 4,
                "success": 4,
                "false_positive": 0,
                "unknown_after_hint": 0,
                "success_rate_pct": 100.0,
            },
        ],
    }
    active_rules = [
        {
            "rule_key": "seed-handreamnet-intel",
            "vendor_family": "handreamnet",
            "driver_overrides": ["handream_sg"],
            "score_bonus": 0.22,
            "is_active": True,
        },
        {
            "rule_key": "seed-dasan-direct",
            "vendor_family": "dasan",
            "driver_overrides": ["dasan_nos"],
            "score_bonus": 0.41,
            "is_active": True,
        },
    ]

    adjustments = DiscoveryHintTuningService.build_score_adjustments(
        benchmark=benchmark,
        active_rules=active_rules,
    )

    assert adjustments
    by_rule = {item["rule_key"]: item for item in adjustments}
    assert by_rule["seed-handreamnet-intel"]["suggested_score_bonus"] < by_rule["seed-handreamnet-intel"]["current_score_bonus"]
    assert by_rule["seed-dasan-direct"]["suggested_score_bonus"] > by_rule["seed-dasan-direct"]["current_score_bonus"]


def test_discovery_hint_tuning_service_builds_alias_and_seed_rule_drafts():
    telemetry_events = [
        {
            "payload": {
                "raw_vendor": "HDN Corp",
                "normalized_vendor": "unknown",
                "final_driver": "handream_sg",
                "chosen_driver": "handream_sg",
            }
        },
        {
            "payload": {
                "raw_vendor": "HDN Corp",
                "normalized_vendor": "unknown",
                "final_driver": "handream_sg",
                "chosen_driver": "handream_sg",
            }
        },
        {
            "payload": {
                "raw_vendor": "Intel Corporation",
                "normalized_vendor": "unknown",
                "final_driver": "handream_sg",
                "chosen_driver": "handream_sg",
                "neighbor_name": "SG2400",
                "seed_vendor": "dasan",
            }
        },
        {
            "payload": {
                "raw_vendor": "Intel Corporation",
                "normalized_vendor": "unknown",
                "final_driver": "handream_sg",
                "chosen_driver": "handream_sg",
                "neighbor_name": "SG2408",
                "seed_vendor": "dasan",
            }
        },
    ]

    alias_candidates = DiscoveryHintTuningService.build_alias_candidates(
        telemetry_events=telemetry_events,
    )
    assert alias_candidates
    assert alias_candidates[0]["raw_vendor"] == "HDN Corp"
    assert alias_candidates[0]["suggested_vendor_family"] == "handreamnet"

    seed_rule_drafts = DiscoveryHintTuningService.build_seed_rule_drafts(
        telemetry_events=telemetry_events,
        active_rules=[],
    )
    assert seed_rule_drafts
    first_draft = seed_rule_drafts[0]
    assert first_draft["vendor_family"] == "handreamnet"
    assert first_draft["driver_overrides"] == ["handream_sg"]
    assert "intel" in first_draft["match_conditions"]["raw_vendor_contains"]
