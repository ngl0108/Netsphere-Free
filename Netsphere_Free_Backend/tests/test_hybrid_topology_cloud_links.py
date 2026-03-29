from app.models.cloud import CloudAccount, CloudResource
from app.models.device import Device, Link
from app.models.user import User
from app.services.hybrid_topology_service import HybridTopologyService


def test_build_hybrid_links_creates_virtual_device_and_link(db):
    user = User(username="u", email="u@x", hashed_password="x", role="admin", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    onprem = Device(
        name="r1",
        ip_address="10.0.0.1",
        owner_id=user.id,
        tenant_id=None,
        device_type="cisco_ios",
        latest_parsed_data={
            "l3_routing": {
                "bgp_neighbors": [
                    {"neighbor_ip": "203.0.113.10", "state": "Established", "remote_as": 65010, "local_as": 65001}
                ]
            }
        },
    )
    db.add(onprem)
    db.commit()
    db.refresh(onprem)

    acc = CloudAccount(name="aws1", provider="aws", credentials={"access_key": "x", "secret_key": "y"}, tenant_id=None, is_active=True)
    db.add(acc)
    db.commit()
    db.refresh(acc)

    res = CloudResource(
        account_id=acc.id,
        resource_id="vpn-1",
        resource_type="vpn_connection",
        name="vpn",
        region="ap-northeast-2",
        cidr_block=None,
        state="available",
        resource_metadata={"tunnels": [{"outside_ip": "203.0.113.10", "status": "UP"}]},
    )
    db.add(res)
    db.commit()

    stats = HybridTopologyService.build_cloud_peer_links(db, tenant_id=None, owner_id=user.id)
    assert stats["created_virtual_devices"] >= 1
    assert stats["created_links"] >= 1
    assert int(stats.get("low_confidence_enqueued") or 0) == 0

    vdev = db.query(Device).filter(Device.device_type == "cloud_virtual", Device.ip_address == "203.0.113.10").first()
    assert vdev is not None
    link = db.query(Link).filter(
        (Link.source_device_id == onprem.id) | (Link.target_device_id == onprem.id)
    ).first()
    assert link is not None
    assert link.protocol == "BGP"
