from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.device import Site, Device
from app.models.settings import SystemSetting
from app.models.topology_candidate import TopologyNeighborCandidate


def test_plug_scan_policy_to_kpi_flow(client, operator_user_token, normal_user_token, db):
    site = Site(name="E2E-SITE")
    src = Device(name="e2e-sw", ip_address="10.50.0.1", device_type="cisco_ios", status="online", site_obj=site)
    db.add_all([site, src])
    db.flush()

    db.add_all(
        [
            SystemSetting(key="auto_approve_enabled", value="true", description="", category="system"),
            SystemSetting(key="auto_approve_min_vendor_confidence", value="0.8", description="", category="system"),
            SystemSetting(key="auto_approve_require_snmp_reachable", value="true", description="", category="system"),
            SystemSetting(key="auto_approve_block_severities", value="error", description="", category="system"),
            SystemSetting(key="topology_candidate_low_confidence_threshold", value="0.7", description="", category="system"),
        ]
    )

    job = DiscoveryJob(cidr="seed:1", status="completed", site_id=site.id, logs="")
    db.add(job)
    db.flush()

    d1 = DiscoveredDevice(
        job_id=job.id,
        ip_address="10.50.0.10",
        hostname="ok-sw",
        vendor="Cisco",
        vendor_confidence=0.95,
        snmp_status="reachable",
        issues=[],
        status="new",
    )
    d2 = DiscoveredDevice(
        job_id=job.id,
        ip_address="10.50.0.11",
        hostname="low-sw",
        vendor="Cisco",
        vendor_confidence=0.4,
        snmp_status="reachable",
        issues=[],
        status="new",
    )
    db.add_all([d1, d2])
    db.add(
        TopologyNeighborCandidate(
            discovery_job_id=job.id,
            source_device_id=src.id,
            neighbor_name="cand-low",
            mgmt_ip="10.50.0.11",
            status="low_confidence",
            confidence=0.3,
            reason="weak_match",
        )
    )
    db.commit()

    # 1) Policy-based auto approve
    res = client.post(
        f"/api/v1/discovery/jobs/{job.id}/approve-all",
        params={"policy": True},
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert payload["approved_count"] == 1
    assert payload["skipped_count"] == 1

    # 2) Discovery KPI reflects approval result
    res2 = client.get(f"/api/v1/discovery/jobs/{job.id}/kpi", headers=normal_user_token)
    assert res2.status_code == 200
    body2 = res2.json()
    kpi_payload = body2.get("data") if isinstance(body2, dict) and "data" in body2 else body2
    assert kpi_payload["totals"]["approved"] == 1
    assert kpi_payload["totals"]["discovered"] == 2

    # 3) Topology candidate summary reflects backlog by site
    res3 = client.get(
        "/api/v1/topology/candidates/summary",
        params={"site_id": site.id},
        headers=normal_user_token,
    )
    assert res3.status_code == 200
    body3 = res3.json()
    summary_payload = body3.get("data") if isinstance(body3, dict) and "data" in body3 else body3
    assert summary_payload["totals"]["backlog_low_confidence"] >= 1
