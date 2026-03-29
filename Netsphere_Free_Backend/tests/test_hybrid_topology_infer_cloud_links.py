import os

from app.models.device import Device, Link
from app.models.topology_candidate import TopologyNeighborCandidate
from app.models.user import User
from app.services.hybrid_topology_service import HybridTopologyService


def test_infer_cloud_links_creates_virtual_device_and_link(db):
    os.environ["DISABLE_IP_INTEL"] = "1"
    user = User(username="u2", email="u2@x", hashed_password="x", role="admin", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)

    onprem = Device(
        name="r2",
        ip_address="10.0.0.2",
        owner_id=user.id,
        tenant_id=None,
        device_type="cisco_ios",
        latest_parsed_data={
            "l3_routing": {
                "bgp_neighbors": [
                    {"neighbor_ip": "8.8.8.8", "state": "Established", "remote_as": 65020, "local_as": 65001}
                ]
            }
        },
    )
    db.add(onprem)
    db.commit()
    db.refresh(onprem)

    stats = HybridTopologyService.build_inferred_cloud_links(db, tenant_id=None, owner_id=user.id)
    assert stats["created_virtual_devices"] >= 1
    assert stats["created_links"] >= 1
    assert int(stats.get("low_confidence_enqueued") or 0) >= 1

    vdev = db.query(Device).filter(Device.device_type == "cloud_virtual", Device.ip_address == "8.8.8.8").first()
    assert vdev is not None
    assert vdev.role == "cloud"

    link = db.query(Link).filter((Link.source_device_id == onprem.id) | (Link.target_device_id == onprem.id)).first()
    assert link is not None
    assert link.protocol == "BGP"

    cand = (
        db.query(TopologyNeighborCandidate)
        .filter(TopologyNeighborCandidate.source_device_id == onprem.id)
        .filter(TopologyNeighborCandidate.status == "low_confidence")
        .first()
    )
    assert cand is not None
