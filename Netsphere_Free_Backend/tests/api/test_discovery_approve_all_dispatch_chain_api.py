from app.api.v1.endpoints import discovery as discovery_ep
from app.models.discovery import DiscoveryJob, DiscoveredDevice


def test_discovery_approve_all_uses_chain_dispatchers(client, operator_user_token, db, monkeypatch):
    topo_calls = []
    sync_calls = []

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
    monkeypatch.setattr(
        discovery_ep.CapabilityProfileService,
        "allow_auto_action",
        staticmethod(lambda *_args, **_kwargs: True),
        raising=False,
    )

    job = DiscoveryJob(cidr="10.9.0.0/24", status="completed", logs="")
    db.add(job)
    db.flush()
    db.add(
        DiscoveredDevice(
            job_id=job.id,
            ip_address="10.9.0.10",
            hostname="sw-chain",
            vendor="Cisco",
            snmp_status="reachable",
            status="new",
        )
    )
    db.commit()

    res = client.post(
        f"/api/v1/discovery/jobs/{job.id}/approve-all",
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    payload = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert payload["approved_count"] == 1
    assert len(payload["device_ids"]) == 1

    approved_device_id = int(payload["device_ids"][0])
    assert len(topo_calls) == 1
    assert topo_calls[0][1]["idempotency_key"] == f"discovery-approve-all:{job.id}:{approved_device_id}:topology"

    assert len(sync_calls) == 1
    assert sync_calls[0][0] == [approved_device_id]
    assert sync_calls[0][3] == f"discovery-approve-all:{job.id}"
