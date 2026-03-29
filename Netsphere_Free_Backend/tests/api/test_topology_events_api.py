import json

from app.models.topology import TopologyChangeEvent


def test_topology_events_filters_link_pair_and_protocol(client, normal_user_token, db):
    db.add(
        TopologyChangeEvent(
            site_id=1,
            device_id=10,
            event_type="link_update",
            payload_json=json.dumps(
                {
                    "device_id": 10,
                    "neighbor_device_id": 20,
                    "local_interface": "Gi0/1",
                    "remote_interface": "Gi0/2",
                    "protocol": "LLDP",
                    "state": "active",
                }
            ),
        )
    )
    db.add(
        TopologyChangeEvent(
            site_id=1,
            device_id=10,
            event_type="link_update",
            payload_json=json.dumps(
                {
                    "device_id": 10,
                    "neighbor_device_id": 30,
                    "local_interface": "Gi0/3",
                    "remote_interface": "Gi0/4",
                    "protocol": "BGP",
                    "state": "active",
                }
            ),
        )
    )
    db.commit()

    res = client.get(
        "/api/v1/topology/events",
        params={
            "event_type": "link_update",
            "source_device_id": 10,
            "target_device_id": 20,
            "protocol": "LLDP",
            "limit": 10,
        },
        headers=normal_user_token,
    )
    assert res.status_code == 200
    body = res.json()
    items = body.get("data") if isinstance(body, dict) and "data" in body else body
    assert isinstance(items, list)
    assert len(items) == 1
    assert items[0]["payload"]["neighbor_device_id"] == 20
    assert str(items[0]["payload"]["protocol"]).upper() == "LLDP"
