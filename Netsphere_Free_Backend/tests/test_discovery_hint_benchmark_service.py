from sqlalchemy.orm import sessionmaker

from app.services.discovery_hint_benchmark_service import DiscoveryHintBenchmarkService
from app.services.discovery_hint_telemetry_service import DiscoveryHintTelemetryService


def test_discovery_hint_benchmark_summary_tracks_success_and_false_positive(db):
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    DiscoveryHintTelemetryService.set_session_factory_for_tests(factory)
    try:
        DiscoveryHintTelemetryService.clear_for_tests()
        DiscoveryHintTelemetryService.record_event(
            {
                "event_type": "hint_success",
                "normalized_vendor": "dasan",
                "chosen_driver": "dasan_nos",
                "final_driver": "dasan_nos",
                "success": True,
            }
        )
        DiscoveryHintTelemetryService.record_event(
            {
                "event_type": "hint_false_positive",
                "normalized_vendor": "unknown",
                "chosen_driver": "generic_linux",
                "final_driver": "handream_sg",
                "success": True,
            }
        )
        DiscoveryHintTelemetryService.record_event(
            {
                "event_type": "unknown_after_hint",
                "normalized_vendor": "ubiquoss",
                "chosen_driver": "ubiquoss_l2",
                "final_driver": "",
                "success": False,
            }
        )
        DiscoveryHintTelemetryService.record_event(
            {
                "event_type": "unknown_after_hint",
                "normalized_vendor": "efmnetworks",
                "chosen_driver": "linux",
                "final_driver": "",
                "success": False,
            }
        )

        summary = DiscoveryHintBenchmarkService.summarize_recent(limit=10)
        assert summary["summary"]["total"] == 4
        assert summary["summary"]["success"] == 2
        assert summary["summary"]["false_positive"] == 1
        assert summary["summary"]["unknown_after_hint"] == 2
        assert summary["summary"]["success_rate_pct"] == 50.0
        assert any(item["vendor"] == "dasan" for item in summary["by_vendor"])
        vendor_row = next(item for item in summary["by_vendor"] if item["vendor"] == "efmnetworks")
        assert vendor_row["unknown_after_hint"] == 1
        assert vendor_row["false_positive_rate_pct"] == 0.0
        driver_row = next(item for item in summary["by_driver"] if item["driver"] == "handream_sg")
        assert driver_row["false_positive"] == 1
        assert driver_row["false_positive_rate_pct"] == 100.0
        hotspot = next(item for item in summary["opportunity_drivers"] if item["driver"] == "linux")
        assert hotspot["unknown_after_hint"] == 1
    finally:
        DiscoveryHintTelemetryService.clear_for_tests()
        DiscoveryHintTelemetryService.set_session_factory_for_tests(None)


def test_discovery_hint_benchmark_trend_compares_current_and_previous_windows(db):
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    DiscoveryHintTelemetryService.set_session_factory_for_tests(factory)
    try:
        DiscoveryHintTelemetryService.clear_for_tests()
        # Previous window (older 2 events)
        DiscoveryHintTelemetryService.record_event(
            {
                "event_type": "unknown_after_hint",
                "normalized_vendor": "ubiquoss",
                "chosen_driver": "ubiquoss_l2",
                "final_driver": "",
                "success": False,
            }
        )
        DiscoveryHintTelemetryService.record_event(
            {
                "event_type": "hint_success",
                "normalized_vendor": "ubiquoss",
                "chosen_driver": "ubiquoss_l2",
                "final_driver": "ubiquoss_l2",
                "success": True,
            }
        )
        # Current window (most recent 2 events)
        DiscoveryHintTelemetryService.record_event(
            {
                "event_type": "hint_false_positive",
                "normalized_vendor": "handreamnet",
                "chosen_driver": "handream_sg",
                "final_driver": "handream_sg",
                "success": True,
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

        trend = DiscoveryHintBenchmarkService.summarize_trend(window=2)
        assert trend["current"]["total"] == 2
        assert trend["previous"]["total"] == 2
        assert "success_rate_pct" in trend["delta"]
        assert "false_positive_rate_pct" in trend["delta"]
    finally:
        DiscoveryHintTelemetryService.clear_for_tests()
        DiscoveryHintTelemetryService.set_session_factory_for_tests(None)
