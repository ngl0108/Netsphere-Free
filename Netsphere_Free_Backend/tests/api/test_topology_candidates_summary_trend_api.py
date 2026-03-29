from datetime import datetime, timedelta, timezone

from app.models.discovery import DiscoveryJob
from app.models.device import Device, Site
from app.models.topology_candidate import TopologyNeighborCandidate


def test_topology_candidates_summary_trend_returns_series_and_jobs(client, normal_user_token, db):
    now = datetime.now(timezone.utc)
    job1 = DiscoveryJob(cidr="seed:1", status="completed")
    job2 = DiscoveryJob(cidr="seed:2", status="completed")
    src = Device(name="sw-trend", ip_address="10.10.10.1", device_type="cisco_ios", status="online")
    db.add_all([job1, job2, src])
    db.flush()

    db.add_all(
        [
            TopologyNeighborCandidate(
                discovery_job_id=job1.id,
                source_device_id=src.id,
                neighbor_name="n1",
                mgmt_ip="10.10.10.11",
                status="low_confidence",
                last_seen=now - timedelta(days=1),
            ),
            TopologyNeighborCandidate(
                discovery_job_id=job1.id,
                source_device_id=src.id,
                neighbor_name="n2",
                mgmt_ip="10.10.10.12",
                status="promoted",
                last_seen=now - timedelta(days=1),
            ),
            TopologyNeighborCandidate(
                discovery_job_id=job2.id,
                source_device_id=src.id,
                neighbor_name="n3",
                mgmt_ip="10.10.10.13",
                status="unmatched",
                last_seen=now - timedelta(days=2),
            ),
        ]
    )
    db.commit()

    res = client.get(
        "/api/v1/topology/candidates/summary/trend",
        params={"days": 7, "limit": 5},
        headers=normal_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body

    assert payload["window_days"] == 7
    assert isinstance(payload.get("series"), list)
    assert len(payload["series"]) == 7
    assert isinstance(payload.get("jobs"), list)
    assert len(payload["jobs"]) >= 2

    by_job = {int(j["job_id"]): j for j in payload["jobs"]}
    assert by_job[int(job1.id)]["backlog_total"] == 1
    assert by_job[int(job1.id)]["resolved_total"] == 1
    assert by_job[int(job2.id)]["backlog_total"] == 1


def test_topology_candidates_summary_trend_supports_site_filter(client, normal_user_token, db):
    now = datetime.now(timezone.utc)
    site_a = Site(name="TS-A")
    site_b = Site(name="TS-B")
    db.add_all([site_a, site_b])
    db.flush()

    src_a = Device(name="ts-sw-a", ip_address="10.30.0.1", device_type="cisco_ios", status="online", site_id=site_a.id)
    src_b = Device(name="ts-sw-b", ip_address="10.31.0.1", device_type="cisco_ios", status="online", site_id=site_b.id)
    db.add_all([src_a, src_b])
    db.flush()

    db.add_all(
        [
            TopologyNeighborCandidate(
                source_device_id=src_a.id,
                neighbor_name="tsa",
                mgmt_ip="10.30.0.11",
                status="low_confidence",
                last_seen=now - timedelta(days=1),
            ),
            TopologyNeighborCandidate(
                source_device_id=src_b.id,
                neighbor_name="tsb",
                mgmt_ip="10.31.0.11",
                status="unmatched",
                last_seen=now - timedelta(days=1),
            ),
        ]
    )
    db.commit()

    res = client.get(
        "/api/v1/topology/candidates/summary/trend",
        params={"days": 7, "site_id": site_a.id},
        headers=normal_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert payload["site_id"] == int(site_a.id)
    assert any(int(x.get("backlog_total", 0)) > 0 for x in payload["series"])
    assert all(int(x.get("unmatched", 0)) == 0 for x in payload["series"])
