from datetime import datetime, timedelta, timezone

from app.models.discovery import DiscoveryJob
from app.models.device import Device, Site
from app.models.topology_candidate import TopologyNeighborCandidate


def test_topology_candidates_list_returns_enriched_priority_queue(client, normal_user_token, db):
    now = datetime.now(timezone.utc)

    site = Site(name="HQ")
    db.add(site)
    db.flush()

    job = DiscoveryJob(cidr="seed:priority", status="completed", site_id=site.id)
    source = Device(
        name="core-sw1",
        hostname="core-sw1.hq.local",
        ip_address="10.10.0.1",
        device_type="cisco_ios",
        status="online",
        site_id=site.id,
    )
    db.add_all([job, source])
    db.flush()

    rows = [
        TopologyNeighborCandidate(
            discovery_job_id=job.id,
            source_device_id=source.id,
            neighbor_name="wan-edge-1",
            mgmt_ip="10.10.0.2",
            local_interface="Gi1/0/1",
            remote_interface="Gi0/0",
            protocol="LLDP",
            confidence=0.42,
            reason="ambiguous_name_exact:21,22",
            status="low_confidence",
            first_seen=now - timedelta(days=2),
            last_seen=now - timedelta(hours=30),
        ),
        TopologyNeighborCandidate(
            discovery_job_id=job.id,
            source_device_id=source.id,
            neighbor_name="access-sw9",
            mgmt_ip=None,
            local_interface="Gi1/0/24",
            remote_interface="UNKNOWN",
            protocol="FDB",
            confidence=0.25,
            reason="missing_mgmt_ip",
            status="unmatched",
            first_seen=now - timedelta(hours=4),
            last_seen=now - timedelta(hours=3),
        ),
        TopologyNeighborCandidate(
            discovery_job_id=job.id,
            source_device_id=source.id,
            neighbor_name="done-sw",
            mgmt_ip="10.10.0.9",
            local_interface="Gi1/0/48",
            remote_interface="Gi1/0/48",
            protocol="LLDP",
            confidence=0.9,
            reason="manual",
            status="promoted",
            first_seen=now - timedelta(hours=2),
            last_seen=now - timedelta(hours=1),
        ),
    ]
    db.add_all(rows)
    db.commit()

    res = client.get(
        "/api/v1/topology/candidates",
        params={"job_id": job.id, "order_by": "priority", "order_dir": "desc"},
        headers=normal_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body

    assert len(payload) == 3
    assert payload[0]["neighbor_name"] == "wan-edge-1"
    assert payload[0]["source_device_name"] == "core-sw1.hq.local"
    assert payload[0]["source_device_ip"] == "10.10.0.1"
    assert payload[0]["site_name"] == "HQ"
    assert payload[0]["reason_code"] == "ambiguous_name_exact"
    assert payload[0]["reason_meta"]["kind"] == "ambiguous"
    assert payload[0]["reason_meta"]["candidate_ids"] == [21, 22]
    assert payload[0]["priority_band"] in {"critical", "high"}
    assert payload[0]["actionable"] is True
    assert payload[0]["stale"] is True
    assert payload[0]["backlog"] is True
    assert payload[0]["next_action"]["code"] == "review_matches"

    assert payload[1]["neighbor_name"] == "access-sw9"
    assert payload[1]["reason_code"] == "missing_mgmt_ip"
    assert payload[1]["priority_score"] > payload[2]["priority_score"]
    assert payload[1]["actionable"] is True
    assert payload[1]["stale"] is False

    assert payload[2]["status"] == "promoted"
    assert payload[2]["backlog"] is False


def test_topology_candidates_list_searches_source_and_site_context(client, normal_user_token, db):
    site = Site(name="Branch-East")
    db.add(site)
    db.flush()

    source = Device(
        name="branch-sw1",
        hostname="branch-sw1.edge.local",
        ip_address="10.20.0.1",
        device_type="cisco_ios",
        status="online",
        site_id=site.id,
    )
    db.add(source)
    db.flush()

    db.add(
        TopologyNeighborCandidate(
            source_device_id=source.id,
            neighbor_name="mystery-peer",
            mgmt_ip="10.20.0.9",
            protocol="LLDP",
            confidence=0.55,
            reason="not_found",
            status="unmatched",
        )
    )
    db.commit()

    res = client.get(
        "/api/v1/topology/candidates",
        params={"search": "Branch-East"},
        headers=normal_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body

    assert len(payload) == 1
    assert payload[0]["site_name"] == "Branch-East"
