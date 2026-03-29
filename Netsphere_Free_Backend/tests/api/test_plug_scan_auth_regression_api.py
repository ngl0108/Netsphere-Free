from app.api.v1.endpoints import discovery as discovery_ep
from app.models.discovery import DiscoveryJob, DiscoveredDevice


def _extract_payload(res):
    body = res.json()
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_discovery_authenticated_flow_does_not_return_401_403(client, operator_user_token, normal_user_token, monkeypatch):
    monkeypatch.setattr(
        discovery_ep,
        "dispatch_discovery_scan",
        lambda *_args, **_kwargs: {"status": "enqueued"},
    )

    scan_res = client.post(
        "/api/v1/discovery/scan",
        json={"cidr": "10.77.0.0/24", "community": "public"},
        headers=operator_user_token,
    )
    assert scan_res.status_code == 200
    assert scan_res.status_code not in {401, 403}
    payload = _extract_payload(scan_res)
    job_id = int(payload["id"])

    status_res = client.get(f"/api/v1/discovery/jobs/{job_id}", headers=normal_user_token)
    assert status_res.status_code == 200
    assert status_res.status_code not in {401, 403}

    results_res = client.get(f"/api/v1/discovery/jobs/{job_id}/results", headers=normal_user_token)
    assert results_res.status_code == 200
    assert results_res.status_code not in {401, 403}


def test_discovery_approve_all_repeat_has_no_auth_regression(client, operator_user_token, db, monkeypatch):
    topo_calls = []
    sync_calls = []

    monkeypatch.setattr(
        discovery_ep.CapabilityProfileService,
        "allow_auto_action",
        staticmethod(lambda *_args, **_kwargs: True),
        raising=False,
    )
    monkeypatch.setattr(
        discovery_ep,
        "dispatch_topology_refresh",
        lambda *args, **kwargs: (topo_calls.append((args, kwargs)) or {"status": "enqueued"}),
    )
    monkeypatch.setattr(
        discovery_ep.enqueue_ssh_sync_batch,
        "delay",
        lambda *args: sync_calls.append(args),
        raising=False,
    )

    job = DiscoveryJob(cidr="10.88.0.0/24", status="completed", logs="")
    db.add(job)
    db.flush()
    db.add(
        DiscoveredDevice(
            job_id=job.id,
            ip_address="10.88.0.10",
            hostname="sw-auth-chain",
            vendor="Cisco",
            snmp_status="reachable",
            status="new",
        )
    )
    db.commit()

    first = client.post(f"/api/v1/discovery/jobs/{job.id}/approve-all", headers=operator_user_token)
    second = client.post(f"/api/v1/discovery/jobs/{job.id}/approve-all", headers=operator_user_token)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.status_code not in {401, 403}
    assert second.status_code not in {401, 403}

    p1 = _extract_payload(first)
    p2 = _extract_payload(second)
    assert p1["approved_count"] == 1
    assert p2["approved_count"] == 0
    assert len(topo_calls) == 1
    assert len(sync_calls) == 1
