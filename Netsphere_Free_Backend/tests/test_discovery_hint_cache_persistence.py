from sqlalchemy.orm import sessionmaker

from app.models.discovery_hint import DiscoveryHintCacheEntry
from app.services.discovery_hint_cache_service import DiscoveryHintCacheService


def test_hint_cache_persists_and_can_be_reloaded_from_db(db):
    factory = sessionmaker(autocommit=False, autoflush=False, bind=db.get_bind())
    DiscoveryHintCacheService.set_session_factory_for_tests(factory)
    try:
        DiscoveryHintCacheService.clear_for_tests()

        recorded = DiscoveryHintCacheService.record_seed_snapshot(
            seed_device_id=17,
            seed_ip="10.0.0.1",
            seed_vendor="Dasan",
            arp_rows=[{"ip": "10.0.0.5", "mac": "00:d0:cb:11:22:33", "interface": "Vlan10"}],
            lldp_rows=[
                {
                    "local_interface": "Gi1/0/24",
                    "neighbor_name": "dist-dasan-1",
                    "mgmt_ip": "10.0.0.1",
                    "remote_interface": "Gi0/1",
                    "protocol": "LLDP",
                }
            ],
            fdb_rows=[{"mac": "00:d0:cb:11:22:33", "port": "Gi1/0/24", "vlan": "10"}],
        )

        assert recorded == 1
        row = db.query(DiscoveryHintCacheEntry).filter(DiscoveryHintCacheEntry.ip_address == "10.0.0.5").first()
        assert row is not None
        assert row.seed_vendor == "Dasan"
        assert row.local_interface == "Gi1/0/24"

        DiscoveryHintCacheService.reset_memory_for_tests()
        loaded = DiscoveryHintCacheService.lookup_ip("10.0.0.5")
        assert loaded is not None
        assert loaded["neighbor_name"] == "dist-dasan-1"
        assert loaded["seed_device_id"] == 17
    finally:
        DiscoveryHintCacheService.clear_for_tests()
        DiscoveryHintCacheService.set_session_factory_for_tests(None)
