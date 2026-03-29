from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.topology import TopologySnapshot
from app.models.topology_candidate import TopologyNeighborCandidate
from app.models.device import Site


def test_discovery_job_kpi_returns_core_metrics(client, normal_user_token, db):
    job = DiscoveryJob(cidr="seed:1", status="completed", logs="")
    db.add(job)
    db.commit()
    db.refresh(job)

    db.add_all(
        [
            DiscoveredDevice(job_id=job.id, ip_address="10.10.0.1", status="approved", snmp_status="reachable"),
            DiscoveredDevice(job_id=job.id, ip_address="10.10.0.2", status="existing", snmp_status="reachable"),
            DiscoveredDevice(job_id=job.id, ip_address="10.10.0.3", status="ignored", snmp_status="unknown"),
            DiscoveredDevice(job_id=job.id, ip_address="10.10.0.4", status="new", snmp_status="unknown"),
        ]
    )
    db.add(
        TopologySnapshot(
            site_id=None,
            job_id=job.id,
            label="first",
            node_count=1,
            link_count=0,
            nodes_json="[]",
            links_json="[]",
            metadata_json="{}",
        )
    )
    db.add_all(
        [
            TopologyNeighborCandidate(
                discovery_job_id=job.id,
                source_device_id=1,
                neighbor_name="n1",
                mgmt_ip="10.10.10.1",
                local_interface="Gi0/1",
                remote_interface="Gi0/2",
                protocol="LLDP",
                confidence=0.4,
                reason="ambiguous_name_exact",
                status="low_confidence",
            ),
            TopologyNeighborCandidate(
                discovery_job_id=job.id,
                source_device_id=1,
                neighbor_name="n2",
                mgmt_ip="10.10.10.2",
                local_interface="Gi0/3",
                remote_interface="Gi0/4",
                protocol="LLDP",
                confidence=0.9,
                reason="ip_match",
                status="promoted",
            ),
            TopologyNeighborCandidate(
                discovery_job_id=job.id,
                source_device_id=2,
                neighbor_name="n3",
                mgmt_ip="10.10.10.3",
                local_interface="Gi0/5",
                remote_interface="Gi0/6",
                protocol="LLDP",
                confidence=0.5,
                reason="ambiguous_name_exact",
                status="low_confidence",
            ),
        ]
    )
    db.commit()

    res = client.get(f"/api/v1/discovery/jobs/{job.id}/kpi", headers=normal_user_token)
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body

    assert payload["job_id"] == job.id
    assert payload["totals"]["discovered"] == 4
    assert payload["totals"]["approved"] == 1
    assert payload["totals"]["existing"] == 1
    assert payload["totals"]["ignored"] == 1
    assert payload["kpi"]["auto_reflection_rate_pct"] == 50.0
    assert payload["kpi"]["false_positive_rate_pct"] == 50.0
    assert payload["kpi"]["low_confidence_rate_pct"] == 50.0
    assert payload["totals"]["low_confidence_candidates"] == 2
    assert payload["kpi"]["low_confidence_top_reasons"][0]["reason"] == "ambiguous_name_exact"
    assert payload["kpi"]["low_confidence_top_reasons"][0]["count"] == 2
    assert payload["first_snapshot"]["id"] is not None


def test_discovery_kpi_summary_supports_site_filter(client, normal_user_token, db):
    site_a = Site(name="DISC-A")
    site_b = Site(name="DISC-B")
    db.add_all([site_a, site_b])
    db.flush()

    job_a = DiscoveryJob(cidr="10.0.0.0/24", status="completed", site_id=site_a.id, logs="")
    job_b = DiscoveryJob(cidr="10.1.0.0/24", status="completed", site_id=site_b.id, logs="")
    db.add_all([job_a, job_b])
    db.flush()

    db.add_all(
        [
            DiscoveredDevice(job_id=job_a.id, ip_address="10.0.0.1", status="approved", snmp_status="reachable"),
            DiscoveredDevice(job_id=job_b.id, ip_address="10.1.0.1", status="ignored", snmp_status="unknown"),
        ]
    )
    db.commit()

    res = client.get(
        "/api/v1/discovery/kpi/summary",
        params={"days": 7, "site_id": site_a.id},
        headers=normal_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert payload["site_id"] == int(site_a.id)
    assert payload["jobs_count"] == 1
    assert payload["totals"]["approved"] == 1
    assert payload["totals"]["ignored"] == 0
