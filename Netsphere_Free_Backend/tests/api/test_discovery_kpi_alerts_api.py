from datetime import datetime, timedelta, timezone

from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.device import Device, Site
from app.models.topology_candidate import TopologyNeighborCandidate


def test_discovery_kpi_alerts_detects_threshold_breaches(client, normal_user_token, db):
    now = datetime.now(timezone.utc)
    site = Site(name="ALERT-SITE")
    src = Device(name="alert-sw", ip_address="10.90.0.1", device_type="cisco_ios", status="online", site_obj=site)
    db.add_all([site, src])
    db.flush()

    job = DiscoveryJob(cidr="10.90.0.0/24", status="completed", site_id=site.id, logs="")
    db.add(job)
    db.flush()

    db.add_all(
        [
            DiscoveredDevice(job_id=job.id, ip_address="10.90.0.10", status="approved", snmp_status="reachable"),
            DiscoveredDevice(job_id=job.id, ip_address="10.90.0.11", status="ignored", snmp_status="unknown"),
            DiscoveredDevice(job_id=job.id, ip_address="10.90.0.12", status="ignored", snmp_status="unknown"),
        ]
    )

    db.add_all(
        [
            TopologyNeighborCandidate(
                discovery_job_id=job.id,
                source_device_id=src.id,
                neighbor_name="n1",
                mgmt_ip="10.90.1.1",
                status="low_confidence",
                confidence=0.3,
                last_seen=now - timedelta(hours=30),
            ),
            TopologyNeighborCandidate(
                discovery_job_id=job.id,
                source_device_id=src.id,
                neighbor_name="n2",
                mgmt_ip="10.90.1.2",
                status="unmatched",
                confidence=0.2,
                last_seen=now - timedelta(hours=28),
            ),
        ]
    )
    db.commit()

    res = client.get(
        "/api/v1/discovery/kpi/alerts",
        params={
            "days": 7,
            "site_id": site.id,
            "min_auto_reflection_pct": 60,
            "max_false_positive_pct": 30,
            "max_low_confidence_rate_pct": 20,
            "max_candidate_backlog": 1,
            "max_stale_backlog_24h": 0,
        },
        headers=normal_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body

    assert payload["status"] == "critical"
    codes = {a["code"] for a in payload["alerts"]}
    assert "low_auto_reflection_rate" in codes
    assert "high_false_positive_rate" in codes
    assert "high_low_confidence_rate" in codes
    assert "candidate_backlog_over_limit" in codes
    assert "stale_candidate_backlog" in codes


def test_discovery_kpi_alerts_supports_site_filter(client, normal_user_token, db):
    site_a = Site(name="A")
    site_b = Site(name="B")
    db.add_all([site_a, site_b])
    db.flush()

    src_a = Device(name="a-sw", ip_address="10.91.0.1", device_type="cisco_ios", status="online", site_id=site_a.id)
    src_b = Device(name="b-sw", ip_address="10.92.0.1", device_type="cisco_ios", status="online", site_id=site_b.id)
    db.add_all([src_a, src_b])
    db.flush()

    job_a = DiscoveryJob(cidr="10.91.0.0/24", status="completed", site_id=site_a.id, logs="")
    job_b = DiscoveryJob(cidr="10.92.0.0/24", status="completed", site_id=site_b.id, logs="")
    db.add_all([job_a, job_b])
    db.flush()

    db.add_all(
        [
            DiscoveredDevice(job_id=job_a.id, ip_address="10.91.0.10", status="ignored", snmp_status="unknown"),
            DiscoveredDevice(job_id=job_b.id, ip_address="10.92.0.10", status="approved", snmp_status="reachable"),
        ]
    )
    db.add(
        TopologyNeighborCandidate(
            discovery_job_id=job_a.id,
            source_device_id=src_a.id,
            neighbor_name="a-n1",
            mgmt_ip="10.91.1.1",
            status="low_confidence",
            confidence=0.2,
        )
    )
    db.commit()

    res = client.get(
        "/api/v1/discovery/kpi/alerts",
        params={"days": 7, "site_id": site_b.id},
        headers=normal_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body

    assert payload["site_id"] == int(site_b.id)
    assert payload["status"] == "healthy"
    assert payload["metrics"]["candidate_backlog_total"] == 0
