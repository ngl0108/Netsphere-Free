from datetime import datetime, timedelta, timezone

from app.models.discovery import DiscoveryJob
from app.models.topology_candidate import TopologyNeighborCandidate
from app.models.device import Device, Site


def test_topology_candidates_summary_returns_backlog_and_processed_kpi(client, normal_user_token, db):
    now = datetime.now(timezone.utc)

    job = DiscoveryJob(cidr="seed:1", status="completed")
    src = Device(name="sw1", ip_address="10.0.0.1", device_type="cisco_ios", status="online")
    db.add_all([job, src])
    db.flush()

    rows = [
        TopologyNeighborCandidate(
            discovery_job_id=job.id,
            source_device_id=src.id,
            neighbor_name="n-low",
            mgmt_ip="10.0.0.10",
            status="low_confidence",
            confidence=0.5,
            reason="weak",
            last_seen=now - timedelta(hours=30),
        ),
        TopologyNeighborCandidate(
            discovery_job_id=job.id,
            source_device_id=src.id,
            neighbor_name="n-unmatched",
            mgmt_ip="10.0.0.11",
            status="unmatched",
            confidence=0.2,
            reason="unknown",
            last_seen=now - timedelta(hours=1),
        ),
        TopologyNeighborCandidate(
            discovery_job_id=job.id,
            source_device_id=src.id,
            neighbor_name="n-promoted",
            mgmt_ip="10.0.0.12",
            status="promoted",
            confidence=0.8,
            reason="manual",
            last_seen=now - timedelta(hours=2),
        ),
        TopologyNeighborCandidate(
            discovery_job_id=job.id,
            source_device_id=src.id,
            neighbor_name="n-ignored",
            mgmt_ip="10.0.0.13",
            status="ignored",
            confidence=0.3,
            reason="noise",
            last_seen=now - timedelta(hours=40),
        ),
    ]
    db.add_all(rows)
    db.commit()

    res = client.get(
        "/api/v1/topology/candidates/summary",
        params={"job_id": job.id},
        headers=normal_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body

    assert payload["totals"]["total"] == 4
    assert payload["totals"]["backlog_total"] == 2
    assert payload["totals"]["backlog_low_confidence"] == 1
    assert payload["totals"]["backlog_unmatched"] == 1
    assert payload["totals"]["resolved_total"] == 2
    assert payload["totals"]["resolved_24h"] == 1
    assert payload["totals"]["stale_backlog_24h"] == 1

    assert payload["by_status"]["low_confidence"] == 1
    assert payload["by_status"]["unmatched"] == 1
    assert payload["by_status"]["promoted"] == 1
    assert payload["by_status"]["ignored"] == 1


def test_topology_candidates_summary_supports_site_filter(client, normal_user_token, db):
    site_a = Site(name="A")
    site_b = Site(name="B")
    db.add_all([site_a, site_b])
    db.flush()

    src_a = Device(name="sw-a", ip_address="10.20.0.1", device_type="cisco_ios", status="online", site_id=site_a.id)
    src_b = Device(name="sw-b", ip_address="10.21.0.1", device_type="cisco_ios", status="online", site_id=site_b.id)
    db.add_all([src_a, src_b])
    db.flush()

    db.add_all(
        [
            TopologyNeighborCandidate(
                source_device_id=src_a.id,
                neighbor_name="a-1",
                mgmt_ip="10.20.0.11",
                status="low_confidence",
                confidence=0.3,
            ),
            TopologyNeighborCandidate(
                source_device_id=src_b.id,
                neighbor_name="b-1",
                mgmt_ip="10.21.0.11",
                status="unmatched",
                confidence=0.2,
            ),
        ]
    )
    db.commit()

    res = client.get(
        "/api/v1/topology/candidates/summary",
        params={"site_id": site_a.id},
        headers=normal_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert payload["scope"]["site_id"] == int(site_a.id)
    assert payload["totals"]["total"] == 1
    assert payload["totals"]["backlog_low_confidence"] == 1
