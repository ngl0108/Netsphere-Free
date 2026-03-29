from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.device import Device, Link, Site
from app.models.cloud import CloudAccount, CloudResource
from app.models.settings import SystemSetting
from app.api.v1.endpoints.devices import get_topology_links


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_topology_links_endpoint_includes_link_rows(db):
    site = Site(name="s1", type="area")
    db.add(site)
    db.commit()
    db.refresh(site)

    a = Device(name="a", ip_address="10.0.0.1", device_type="cisco_ios", status="online", owner_id=1, site_id=site.id, model="C2960")
    b = Device(name="b", ip_address="10.0.0.2", device_type="cisco_ios", status="online", owner_id=1, site_id=site.id)
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    l = Link(
        source_device_id=a.id,
        source_interface_name="Gi0/1",
        target_device_id=b.id,
        target_interface_name="Gi0/2",
        status="active",
        protocol="LLDP",
        link_speed="1G",
        discovery_source="test",
    )
    db.add(l)
    db.commit()

    payload = get_topology_links(db=db, current_user=object())
    assert isinstance(payload, dict)
    nodes = payload.get("nodes") or []
    node_a = next((n for n in nodes if n.get("id") == str(a.id)), None)
    assert node_a
    assert node_a.get("model") == "C2960"
    links = payload.get("links") or []
    row = next((x for x in links if x.get("source") == str(a.id) and x.get("target") == str(b.id)), None)
    assert row is not None
    assert row.get("id") == l.id


def test_topology_links_endpoint_includes_management_state_for_preview_limit(db):
    db.add_all(
        [
            SystemSetting(key="product_edition", value="preview"),
            SystemSetting(key="preview_deployment_role", value="collector_installed"),
        ]
    )
    site = Site(name="preview", type="area")
    db.add(site)
    db.commit()
    db.refresh(site)

    devices = []
    for idx in range(51):
        devices.append(
            Device(
                name=f"preview-{idx}",
                ip_address=f"10.0.10.{idx + 1}",
                device_type="cisco_ios",
                status="online",
                owner_id=1,
                site_id=site.id,
            )
        )
    db.add_all(devices)
    db.commit()

    payload = get_topology_links(db=db, current_user=object())
    nodes = payload.get("nodes") or []
    managed_nodes = [row for row in nodes if row.get("management_state") == "managed"]
    discovered_only_nodes = [row for row in nodes if row.get("management_state") == "discovered_only"]

    assert len(managed_nodes) == 50
    assert len(discovered_only_nodes) == 1
    assert discovered_only_nodes[0].get("is_managed") is False


def test_topology_links_endpoint_includes_l3_metadata(db):
    site = Site(name="core", type="area")
    db.add(site)
    db.commit()
    db.refresh(site)

    a = Device(
        name="r1",
        hostname="r1",
        ip_address="10.0.0.1",
        device_type="cisco_ios",
        status="online",
        owner_id=1,
        site_id=site.id,
        latest_parsed_data={
            "l3_routing": {
                "bgp_neighbors": [
                    {
                        "neighbor_ip": "10.0.0.2",
                        "local_as": 65001,
                        "remote_as": 65002,
                        "state": "Established",
                        "prefixes_received": 24,
                        "uptime": "01:00:00",
                    }
                ],
                "ospf_neighbors": [
                    {
                        "neighbor_ip": "10.0.0.2",
                        "neighbor_id": "2.2.2.2",
                        "state": "FULL/DR",
                        "interface": "Gi0/1",
                        "area": "0.0.0.0",
                        "priority": 1,
                    }
                ],
            }
        },
    )
    b = Device(
        name="r2",
        hostname="r2",
        ip_address="10.0.0.2",
        device_type="cisco_ios",
        status="online",
        owner_id=1,
        site_id=site.id,
        latest_parsed_data={
            "l3_routing": {
                "bgp_neighbors": [
                    {
                        "neighbor_ip": "10.0.0.1",
                        "local_as": 65002,
                        "remote_as": 65001,
                        "state": "Established",
                    }
                ],
                "ospf_neighbors": [
                    {
                        "neighbor_ip": "10.0.0.1",
                        "neighbor_id": "1.1.1.1",
                        "state": "FULL/BDR",
                        "interface": "Gi0/2",
                        "area": "0.0.0.0",
                        "priority": 1,
                    }
                ],
            }
        },
    )
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    db.add_all(
        [
            Link(
                source_device_id=a.id,
                source_interface_name="",
                target_device_id=b.id,
                target_interface_name="",
                status="active",
                protocol="BGP",
                discovery_source="bgp_neighbor",
                confidence=0.85,
            ),
            Link(
                source_device_id=a.id,
                source_interface_name="Gi0/1",
                target_device_id=b.id,
                target_interface_name="Gi0/2",
                status="active",
                protocol="OSPF",
                discovery_source="ospf_neighbor",
                confidence=0.90,
            ),
        ]
    )
    db.commit()

    payload = get_topology_links(db=db, current_user=object())
    nodes = payload.get("nodes") or []
    node_a = next((n for n in nodes if n.get("id") == str(a.id)), None)
    assert node_a is not None
    assert node_a.get("l3", {}).get("peer_counts", {}).get("total") == 2
    assert node_a.get("l3", {}).get("peer_counts", {}).get("bgp") == 1
    assert node_a.get("l3", {}).get("peer_counts", {}).get("ospf") == 1
    assert node_a.get("l3", {}).get("local_asns") == [65001]

    links = payload.get("links") or []
    bgp_link = next((x for x in links if x.get("protocol") == "BGP"), None)
    ospf_link = next((x for x in links if x.get("protocol") == "OSPF"), None)

    assert bgp_link is not None
    assert bgp_link.get("layer") == "l3"
    assert bgp_link.get("l3", {}).get("relationship") == "ebgp"
    assert bgp_link.get("l3", {}).get("state") == "established"
    assert bgp_link.get("l3", {}).get("source", {}).get("local_as") == 65001
    assert bgp_link.get("l3", {}).get("target", {}).get("local_as") == 65002
    assert bgp_link.get("id") is not None

    assert ospf_link is not None
    assert ospf_link.get("layer") == "l3"
    assert ospf_link.get("l3", {}).get("state") == "full"
    assert ospf_link.get("l3", {}).get("area") == "0.0.0.0"
    assert ospf_link.get("l3", {}).get("source", {}).get("interface") == "Gi0/1"


def test_topology_links_endpoint_infers_overlay_metadata_from_parsed_data(db):
    site = Site(name="fabric", type="area")
    db.add(site)
    db.commit()
    db.refresh(site)

    leaf1 = Device(
        name="leaf1",
        hostname="leaf1",
        ip_address="10.10.10.1",
        device_type="cisco_nxos",
        status="online",
        owner_id=1,
        site_id=site.id,
        latest_parsed_data={
            "overlay": {
                "nve_interface": "nve1",
                "local_vtep_ip": "172.16.0.1",
                "vxlan_peers": [
                    {
                        "peer_ip": "172.16.0.2",
                        "state": "up",
                        "transport": "evpn",
                        "interface": "nve1",
                        "vnis": [10010, 20010],
                    }
                ],
                "evpn_neighbors": [
                    {
                        "peer_ip": "172.16.0.2",
                        "state": "Established",
                        "local_as": 65101,
                        "remote_as": 65102,
                    }
                ],
                "vnis": [
                    {"vni": 10010, "type": "l2", "bridge_domain": "Users", "state": "up"},
                    {"vni": 20010, "type": "l3", "vrf": "Tenant-A", "state": "up"},
                ],
            }
        },
    )
    leaf2 = Device(
        name="leaf2",
        hostname="leaf2",
        ip_address="10.10.10.2",
        device_type="cisco_nxos",
        status="online",
        owner_id=1,
        site_id=site.id,
        latest_parsed_data={
            "overlay": {
                "nve_interface": "nve1",
                "local_vtep_ip": "172.16.0.2",
                "vxlan_peers": [
                    {
                        "peer_ip": "172.16.0.1",
                        "state": "up",
                        "transport": "evpn",
                        "interface": "nve1",
                        "vnis": [10010, 20010],
                    }
                ],
                "evpn_neighbors": [
                    {
                        "peer_ip": "172.16.0.1",
                        "state": "Established",
                        "local_as": 65102,
                        "remote_as": 65101,
                    }
                ],
                "vnis": [
                    {"vni": 10010, "type": "l2", "bridge_domain": "Users", "state": "up"},
                    {"vni": 20010, "type": "l3", "vrf": "Tenant-A", "state": "up"},
                ],
            }
        },
    )
    db.add_all([leaf1, leaf2])
    db.commit()
    db.refresh(leaf1)
    db.refresh(leaf2)

    payload = get_topology_links(db=db, current_user=object())
    nodes = payload.get("nodes") or []
    links = payload.get("links") or []

    node1 = next((n for n in nodes if n.get("id") == str(leaf1.id)), None)
    assert node1 is not None
    assert node1.get("overlay", {}).get("peer_counts", {}).get("total") == 1
    assert node1.get("overlay", {}).get("peer_counts", {}).get("evpn") == 1
    assert node1.get("overlay", {}).get("vni_counts", {}).get("total") == 2
    assert node1.get("overlay", {}).get("vni_counts", {}).get("l2") == 1
    assert node1.get("overlay", {}).get("vni_counts", {}).get("l3") == 1
    assert node1.get("overlay", {}).get("local_vtep_ips") == ["172.16.0.1"]

    overlay_link = next((x for x in links if x.get("layer") == "overlay"), None)
    assert overlay_link is not None
    assert overlay_link.get("protocol") == "VXLAN"
    assert overlay_link.get("overlay", {}).get("state") == "up"
    assert overlay_link.get("overlay", {}).get("transport") == "evpn"
    assert overlay_link.get("overlay", {}).get("vni_count") == 2
    assert [row.get("vni") for row in (overlay_link.get("overlay", {}).get("vnis") or [])] == [10010, 20010]
    assert overlay_link.get("overlay", {}).get("evpn", {}).get("relationship") == "ebgp"
    assert overlay_link.get("overlay", {}).get("source", {}).get("local_vtep_ip") == "172.16.0.1"
    assert overlay_link.get("overlay", {}).get("target", {}).get("local_vtep_ip") == "172.16.0.2"
    assert str(overlay_link.get("id")).startswith("overlay-")


def test_topology_links_endpoint_preserves_degraded_status(db):
    site = Site(name="wan", type="area")
    db.add(site)
    db.commit()
    db.refresh(site)

    a = Device(name="wan-a", ip_address="10.1.0.1", device_type="cisco_ios", status="online", owner_id=1, site_id=site.id)
    b = Device(name="wan-b", ip_address="10.1.0.2", device_type="cisco_ios", status="online", owner_id=1, site_id=site.id)
    db.add_all([a, b])
    db.commit()
    db.refresh(a)
    db.refresh(b)

    db.add(
        Link(
            source_device_id=a.id,
            source_interface_name="Gi0/0",
            target_device_id=b.id,
            target_interface_name="Gi0/1",
            status="degraded",
            protocol="BGP",
            confidence=0.72,
        )
    )
    db.commit()

    payload = get_topology_links(db=db, current_user=object())
    links = payload.get("links") or []
    row = next((x for x in links if x.get("source") == str(a.id) and x.get("target") == str(b.id)), None)
    assert row is not None
    assert row.get("status") == "degraded"


def test_topology_links_endpoint_enriches_hybrid_cloud_metadata(db):
    site = Site(name="hq", type="area")
    db.add(site)
    db.commit()
    db.refresh(site)

    edge = Device(
        name="edge-r1",
        hostname="edge-r1",
        ip_address="10.0.0.1",
        device_type="cisco_iosxe",
        status="online",
        owner_id=1,
        site_id=site.id,
    )
    cloud_peer = Device(
        name="aws-peer-1",
        hostname="aws-peer-1",
        ip_address="203.0.113.10",
        device_type="cloud_virtual",
        status="online",
        owner_id=1,
        variables={
            "cloud": {
                "refs": [
                    {
                        "provider": "aws",
                        "account_id": 101,
                        "account_name": "prod",
                        "region": "ap-northeast-2",
                        "resource_type": "instance",
                        "resource_id": "i-abc123",
                        "name": "prod-vm-1",
                    },
                    {
                        "provider": "aws",
                        "account_id": 101,
                        "account_name": "prod",
                        "region": "ap-northeast-2",
                        "resource_type": "subnet",
                        "resource_id": "subnet-001",
                        "name": "app-subnet",
                    },
                ]
            }
        },
    )
    db.add_all([edge, cloud_peer])
    db.commit()
    db.refresh(edge)
    db.refresh(cloud_peer)

    acc = CloudAccount(
        name="prod",
        provider="aws",
        credentials={"access_key": "x", "secret_key": "y"},
        is_active=True,
        tenant_id=None,
        last_synced_at=datetime(2026, 3, 19, 1, 2, 3, tzinfo=timezone.utc),
        sync_status="success",
        sync_message="Scanned 5 resources",
    )
    db.add(acc)
    db.flush()
    db.add_all(
        [
            CloudResource(
                account_id=acc.id,
                resource_id="vpc-001",
                resource_type="vpc",
                name="prod-vpc",
                region="ap-northeast-2",
                cidr_block="10.10.0.0/16",
                state="available",
                resource_metadata={},
            ),
            CloudResource(
                account_id=acc.id,
                resource_id="subnet-001",
                resource_type="subnet",
                name="app-subnet",
                region="ap-northeast-2",
                cidr_block="10.10.1.0/24",
                state="available",
                resource_metadata={"vpc_id": "vpc-001"},
            ),
            CloudResource(
                account_id=acc.id,
                resource_id="rtb-001",
                resource_type="route_table",
                name="prod-main-rt",
                region="ap-northeast-2",
                cidr_block=None,
                state=None,
                resource_metadata={
                    "vpc_id": "vpc-001",
                    "routes": [{"dst_cidr": "0.0.0.0/0"}],
                    "associations": [{"subnet_id": "subnet-001", "main": False}],
                },
            ),
            CloudResource(
                account_id=acc.id,
                resource_id="sg-001",
                resource_type="security_group",
                name="prod-app-sg",
                region="ap-northeast-2",
                cidr_block=None,
                state=None,
                resource_metadata={"vpc_id": "vpc-001", "inbound_rules": 2, "outbound_rules": 1},
            ),
            CloudResource(
                account_id=acc.id,
                resource_id="i-abc123",
                resource_type="instance",
                name="prod-vm-1",
                region="ap-northeast-2",
                cidr_block=None,
                state="running",
                resource_metadata={"subnet_id": "subnet-001", "vpc_id": "vpc-001", "security_group_ids": ["sg-001"]},
            ),
        ]
    )
    db.flush()

    db.add(
        Link(
            source_device_id=edge.id,
            source_interface_name="Gi0/0",
            target_device_id=cloud_peer.id,
            target_interface_name="cloud-bgp",
            status="active",
            protocol="BGP",
            confidence=0.97,
            discovery_source="hybrid_cloud",
        )
    )
    db.commit()

    payload = get_topology_links(db=db, current_user=object())
    nodes = payload.get("nodes") or []
    links = payload.get("links") or []

    cloud_node = next((n for n in nodes if n.get("id") == str(cloud_peer.id)), None)
    assert cloud_node is not None
    assert cloud_node.get("cloud", {}).get("kind") == "virtual_peer"
    assert cloud_node.get("cloud", {}).get("resource_id") == "i-abc123"
    assert cloud_node.get("cloud", {}).get("resource_name") == "prod-vm-1"
    assert cloud_node.get("cloud", {}).get("ref_resource_types") == ["instance", "subnet"]
    assert len(cloud_node.get("cloud", {}).get("refs") or []) == 2
    assert cloud_node.get("hybrid", {}).get("connected") is True
    assert cloud_node.get("hybrid", {}).get("peer_links") == 1

    edge_node = next((n for n in nodes if n.get("id") == str(edge.id)), None)
    assert edge_node is not None
    assert edge_node.get("hybrid", {}).get("peer_links") == 1
    assert edge_node.get("hybrid", {}).get("providers") == ["aws"]

    hybrid_link = next((x for x in links if x.get("source") == str(edge.id) and x.get("target") == str(cloud_peer.id)), None)
    assert hybrid_link is not None
    assert hybrid_link.get("hybrid", {}).get("kind") == "cloud_peer"
    assert hybrid_link.get("hybrid", {}).get("provider") == "aws"
    assert hybrid_link.get("hybrid", {}).get("account_name") == "prod"
    assert hybrid_link.get("hybrid", {}).get("resource_name") == "prod-vm-1"

    inventory_nodes = [n for n in nodes if str(n.get("id") or "").startswith("cr-")]
    assert len(inventory_nodes) >= 2
    assert any(n.get("cloud", {}).get("kind") == "inventory_resource" for n in inventory_nodes)
    vm_inventory_node = next((n for n in inventory_nodes if n.get("cloud", {}).get("resource_type") == "instance"), None)
    assert vm_inventory_node is not None
    assert vm_inventory_node.get("cloud", {}).get("resource_name") == "prod-vm-1"
    assert vm_inventory_node.get("cloud", {}).get("sync_status") == "success"
    assert vm_inventory_node.get("cloud", {}).get("sync_message") == "Scanned 5 resources"
    assert vm_inventory_node.get("cloud", {}).get("provider_state") == "running"
    assert vm_inventory_node.get("cloud", {}).get("last_synced_at") is not None
    summary = vm_inventory_node.get("cloud", {}).get("operational_summary") or {}
    assert summary.get("route_tables") == 1
    assert summary.get("routes") == 1
    assert summary.get("security_policies") >= 1
    assert summary.get("security_rules") == 3
    assert summary.get("route_refs")[0].get("resource_name") == "prod-main-rt"
    assert summary.get("security_refs")[0].get("resource_name") == "prod-app-sg"
    assert vm_inventory_node.get("status") == "online"

    subnet_inventory_node = next((n for n in inventory_nodes if n.get("cloud", {}).get("resource_type") == "subnet"), None)
    assert subnet_inventory_node is not None
    subnet_to_vm = next(
        (
            x
            for x in links
            if x.get("protocol") == "CLOUD"
            and x.get("source") == subnet_inventory_node.get("id")
            and x.get("target") == vm_inventory_node.get("id")
        ),
        None,
    )
    assert subnet_to_vm is not None

    inventory_edge = next((x for x in links if x.get("protocol") == "CLOUD"), None)
    assert inventory_edge is not None
    assert inventory_edge.get("hybrid", {}).get("kind") == "inventory"
    assert inventory_edge.get("layer") == "hybrid"
