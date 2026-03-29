from app.models.device import Device
from app.models.discovery import DiscoveryJob
from app.services.neighbor_crawl_service import NeighborCrawlService


def test_prefetch_seed_context_returns_counts_and_updates_job_log(db, monkeypatch):
    job = DiscoveryJob(cidr="10.0.0.0/24", status="pending", snmp_community="public")
    seed = Device(name="seed-core-1", ip_address="10.0.0.1", device_type="cisco_ios", status="reachable")
    db.add(job)
    db.add(seed)
    db.commit()

    monkeypatch.setattr(
        NeighborCrawlService,
        "_collect_seed_context",
        lambda self, device, ip, profile: {
            "lldp_rows": [{"local_interface": "Gi1/0/24"}],
            "cdp_rows": [],
            "arp_rows": [{"ip": "10.0.0.5", "mac": "00:d0:cb:11:22:33"}],
            "fdb_rows": [{"mac": "00:d0:cb:11:22:33", "port": "Gi1/0/24"}],
            "recorded": 3,
        },
    )

    result = NeighborCrawlService(db).prefetch_seed_context(job_id=job.id, seed_device_id=seed.id)

    db.refresh(job)
    assert result["status"] == "ok"
    assert result["recorded"] == 3
    assert result["seed_ip"] == "10.0.0.1"
    assert "Hint Prefetch Completed" in str(job.logs or "")
