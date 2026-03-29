from sqlalchemy.orm import sessionmaker

from app.models.discovery_hint_learning import DiscoveryHintTelemetryEvent
from app.services.discovery_hint_telemetry_service import DiscoveryHintTelemetryService


def test_hint_telemetry_event_is_persisted(db):
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    DiscoveryHintTelemetryService.set_session_factory_for_tests(factory)
    try:
        DiscoveryHintTelemetryService.clear_for_tests()

        event_id = DiscoveryHintTelemetryService.record_event(
            {
                "event_type": "hint_success",
                "target_ip": "10.0.0.5",
                "mac": "00:d0:cb:11:22:33",
                "oui_prefix": "00d0cb",
                "raw_vendor": "Dasan Networks",
                "normalized_vendor": "Dasan",
                "seed_device_id": 17,
                "seed_ip": "10.0.0.1",
                "seed_vendor": "Dasan",
                "chosen_driver": "dasan_nos",
                "final_driver": "dasan_nos",
                "success": True,
                "candidates": [{"driver": "dasan_nos", "score": 0.92}],
            }
        )

        assert event_id is not None
        row = db.query(DiscoveryHintTelemetryEvent).filter(DiscoveryHintTelemetryEvent.id == event_id).first()
        assert row is not None
        assert row.event_type == "hint_success"
        assert row.final_driver == "dasan_nos"
        assert bool(row.success) is True
    finally:
        DiscoveryHintTelemetryService.clear_for_tests()
        DiscoveryHintTelemetryService.set_session_factory_for_tests(None)
