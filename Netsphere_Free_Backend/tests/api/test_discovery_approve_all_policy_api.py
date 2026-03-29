from app.models.discovery import DiscoveryJob, DiscoveredDevice
from app.models.settings import SystemSetting


def test_discovery_approve_all_policy_mode_applies_auto_approve_rules(client, operator_user_token, db):
    db.add_all(
        [
            SystemSetting(key="auto_approve_enabled", value="true", description="", category="system"),
            SystemSetting(key="auto_approve_min_vendor_confidence", value="0.8", description="", category="system"),
            SystemSetting(key="auto_approve_require_snmp_reachable", value="true", description="", category="system"),
            SystemSetting(key="auto_approve_block_severities", value="error", description="", category="system"),
        ]
    )
    job = DiscoveryJob(cidr="10.0.0.0/24", status="completed", logs="")
    db.add(job)
    db.flush()
    db.add_all(
        [
            DiscoveredDevice(
                job_id=job.id,
                ip_address="10.0.0.10",
                hostname="sw-ok",
                vendor="Cisco",
                vendor_confidence=0.95,
                snmp_status="reachable",
                issues=[],
                status="new",
            ),
            DiscoveredDevice(
                job_id=job.id,
                ip_address="10.0.0.11",
                hostname="sw-low",
                vendor="Cisco",
                vendor_confidence=0.4,
                snmp_status="reachable",
                issues=[],
                status="new",
            ),
        ]
    )
    db.commit()

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
    assert payload["skip_breakdown"]["low_vendor_confidence"] == 1
