import asyncio
import sys
import types

from app.models.cloud import CloudAccount, CloudResource
from app.services.cloud_service import CloudScanner


def test_cloud_scanner_aws_collects_extended_resource_types(db, monkeypatch):
    acc = CloudAccount(
        name="aws-ext",
        provider="aws",
        credentials={
            "auth_type": "access_key",
            "access_key": "AKIA_TEST",
            "secret_key": "SECRET_TEST",
            "region": "ap-northeast-2",
        },
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)

    class _FakeEc2:
        def describe_vpcs(self):
            return {"Vpcs": [{"VpcId": "vpc-1", "CidrBlock": "10.0.0.0/16", "State": "available", "Tags": []}]}

        def describe_subnets(self):
            return {
                "Subnets": [
                    {
                        "SubnetId": "subnet-1",
                        "VpcId": "vpc-1",
                        "CidrBlock": "10.0.1.0/24",
                        "State": "available",
                        "AvailabilityZone": "ap-northeast-2a",
                        "AvailableIpAddressCount": 200,
                        "MapPublicIpOnLaunch": True,
                        "Tags": [],
                    }
                ]
            }

        def describe_customer_gateways(self):
            return {"CustomerGateways": []}

        def describe_vpn_gateways(self):
            return {"VpnGateways": []}

        def describe_vpn_connections(self):
            return {"VpnConnections": []}

        def describe_transit_gateways(self):
            return {"TransitGateways": []}

        def describe_transit_gateway_attachments(self):
            return {"TransitGatewayAttachments": []}

        def describe_route_tables(self):
            return {"RouteTables": []}

        def describe_security_groups(self):
            return {
                "SecurityGroups": [
                    {
                        "GroupId": "sg-1",
                        "GroupName": "default",
                        "VpcId": "vpc-1",
                        "Description": "default sg",
                        "IpPermissions": [],
                        "IpPermissionsEgress": [],
                    }
                ]
            }

        def describe_instances(self):
            return {
                "Reservations": [
                    {
                        "Instances": [
                            {
                                "InstanceId": "i-1",
                                "State": {"Name": "running"},
                                "InstanceType": "t3.micro",
                                "VpcId": "vpc-1",
                                "SubnetId": "subnet-1",
                                "PrivateIpAddress": "10.0.1.10",
                                "PublicIpAddress": "198.51.100.10",
                                "SecurityGroups": [{"GroupId": "sg-1"}],
                                "NetworkInterfaces": [
                                    {
                                        "PrivateIpAddresses": [
                                            {
                                                "PrivateIpAddress": "10.0.1.10",
                                                "Association": {"PublicIp": "198.51.100.10"},
                                            }
                                        ]
                                    }
                                ],
                                "Tags": [],
                            }
                        ]
                    }
                ]
            }

    class _FakeElbv2:
        def describe_load_balancers(self):
            return {
                "LoadBalancers": [
                    {
                        "LoadBalancerArn": "arn:aws:elasticloadbalancing:ap-northeast-2:1:loadbalancer/app/lb/123",
                        "LoadBalancerName": "lb-main",
                        "VpcId": "vpc-1",
                        "Scheme": "internet-facing",
                        "Type": "application",
                        "DNSName": "lb-main.example.com",
                        "CanonicalHostedZoneId": "Z123",
                        "IpAddressType": "ipv4",
                        "SecurityGroups": ["sg-1"],
                        "AvailabilityZones": [{"ZoneName": "ap-northeast-2a"}],
                        "State": {"Code": "active"},
                    }
                ]
            }

    class _FakeSession:
        def __init__(self, **_kwargs):
            pass

        def client(self, name):
            if name == "ec2":
                return _FakeEc2()
            if name == "elbv2":
                return _FakeElbv2()
            if name == "sts":
                return types.SimpleNamespace(
                    get_caller_identity=lambda: {"Arn": "arn:aws:iam::123:user/test"},
                    assume_role=lambda **_kwargs: {"Credentials": {"AccessKeyId": "A", "SecretAccessKey": "B", "SessionToken": "C"}},
                )
            raise ValueError(name)

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(Session=_FakeSession))

    scanner = CloudScanner(db, acc)
    rows = asyncio.run(scanner.scan())
    types_found = {str(r.get("resource_type") or "") for r in rows}

    assert {"vpc", "subnet", "security_group", "virtual_machine", "load_balancer"}.issubset(types_found)

    stored_rows = db.query(CloudResource).filter(CloudResource.account_id == int(acc.id)).all()
    stored_types = {str(r.resource_type or "") for r in stored_rows}
    assert {"vpc", "subnet", "security_group", "virtual_machine", "load_balancer"}.issubset(stored_types)


def test_cloud_scanner_azure_vm_includes_subnet_vnet_refs(db, monkeypatch):
    acc = CloudAccount(
        name="azure-ext",
        provider="azure",
        credentials={
            "tenant_id": "tenant-test",
            "client_id": "client-test",
            "client_secret": "secret-test",
            "subscription_id": "sub-test",
        },
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)

    subnet_id = "/subscriptions/sub-test/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-a/subnets/subnet-a"
    vnet_id = "/subscriptions/sub-test/resourceGroups/rg-test/providers/Microsoft.Network/virtualNetworks/vnet-a"
    nic_id = "/subscriptions/sub-test/resourceGroups/rg-test/providers/Microsoft.Network/networkInterfaces/nic-a"
    pip_id = "/subscriptions/sub-test/resourceGroups/rg-test/providers/Microsoft.Network/publicIPAddresses/pip-a"

    class _FakeClientSecretCredential:
        def __init__(self, *_args, **_kwargs):
            pass

    class _FakeNetworkManagementClient:
        def __init__(self, *_args, **_kwargs):
            vnet = types.SimpleNamespace(
                id=vnet_id,
                name="vnet-a",
                location="koreacentral",
                address_space=types.SimpleNamespace(address_prefixes=["10.20.0.0/16"]),
                provisioning_state="Succeeded",
                subnets=[
                    types.SimpleNamespace(
                        id=subnet_id,
                        name="subnet-a",
                        address_prefix="10.20.1.0/24",
                        provisioning_state="Succeeded",
                        network_security_group=None,
                        private_endpoint_network_policies=None,
                    )
                ],
            )
            self.virtual_networks = types.SimpleNamespace(list_all=lambda: [vnet])
            self.network_security_groups = types.SimpleNamespace(list_all=lambda: [])
            self.load_balancers = types.SimpleNamespace(list_all=lambda: [])
            self.network_interfaces = types.SimpleNamespace(get=self._get_nic)
            self.public_ip_addresses = types.SimpleNamespace(get=self._get_public_ip)

        def _get_nic(self, *_args, **_kwargs):
            return types.SimpleNamespace(
                ip_configurations=[
                    types.SimpleNamespace(
                        subnet=types.SimpleNamespace(id=subnet_id),
                        private_ip_address="10.20.1.10",
                        public_ip_address=types.SimpleNamespace(id=pip_id),
                    )
                ]
            )

        def _get_public_ip(self, *_args, **_kwargs):
            return types.SimpleNamespace(ip_address="203.0.113.10")

    class _FakeComputeManagementClient:
        def __init__(self, *_args, **_kwargs):
            vm = types.SimpleNamespace(
                id="/subscriptions/sub-test/resourceGroups/rg-test/providers/Microsoft.Compute/virtualMachines/vm-a",
                name="vm-a",
                location="koreacentral",
                provisioning_state="Succeeded",
                hardware_profile=types.SimpleNamespace(vm_size="Standard_B1s"),
                network_profile=types.SimpleNamespace(network_interfaces=[types.SimpleNamespace(id=nic_id)]),
                zones=["1"],
            )
            self.virtual_machines = types.SimpleNamespace(list_all=lambda: [vm])

    azure_mod = types.ModuleType("azure")
    azure_identity_mod = types.ModuleType("azure.identity")
    azure_identity_mod.ClientSecretCredential = _FakeClientSecretCredential
    azure_mgmt_mod = types.ModuleType("azure.mgmt")
    azure_mgmt_network_mod = types.ModuleType("azure.mgmt.network")
    azure_mgmt_network_mod.NetworkManagementClient = _FakeNetworkManagementClient
    azure_mgmt_compute_mod = types.ModuleType("azure.mgmt.compute")
    azure_mgmt_compute_mod.ComputeManagementClient = _FakeComputeManagementClient

    monkeypatch.setitem(sys.modules, "azure", azure_mod)
    monkeypatch.setitem(sys.modules, "azure.identity", azure_identity_mod)
    monkeypatch.setitem(sys.modules, "azure.mgmt", azure_mgmt_mod)
    monkeypatch.setitem(sys.modules, "azure.mgmt.network", azure_mgmt_network_mod)
    monkeypatch.setitem(sys.modules, "azure.mgmt.compute", azure_mgmt_compute_mod)

    scanner = CloudScanner(db, acc)
    rows = asyncio.run(scanner.scan())
    vm = next(r for r in rows if str(r.get("resource_type") or "") == "virtual_machine")
    meta = vm.get("resource_metadata") or {}
    assert str(meta.get("subnet_id") or "") == subnet_id
    assert str(meta.get("vnet_id") or "") == vnet_id
    assert "10.20.1.10" in list(meta.get("private_ips") or [])
    assert "203.0.113.10" in list(meta.get("public_ips") or [])


def test_cloud_scanner_gcp_vm_includes_subnetwork_network_refs(db, monkeypatch):
    acc = CloudAccount(
        name="gcp-ext",
        provider="gcp",
        credentials={
            "project_id": "project-test",
            "service_account_json": {"type": "service_account", "client_email": "test@example.com"},
        },
        is_active=True,
        tenant_id=None,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)

    network_ref = "https://www.googleapis.com/compute/v1/projects/project-test/global/networks/net-a"
    subnetwork_ref = "https://www.googleapis.com/compute/v1/projects/project-test/regions/us-central1/subnetworks/sub-a"

    class _FakeCredentialsFactory:
        @staticmethod
        def from_service_account_info(_info):
            return object()

    class _NetworksClient:
        def __init__(self, **_kwargs):
            pass

        def list(self, **_kwargs):
            return [
                types.SimpleNamespace(
                    self_link=network_ref,
                    name="net-a",
                    auto_create_subnetworks=False,
                    IPv4Range=None,
                )
            ]

    class _SubnetworksClient:
        def __init__(self, **_kwargs):
            pass

        def aggregated_list(self, **_kwargs):
            subnet = types.SimpleNamespace(
                self_link=subnetwork_ref,
                name="sub-a",
                region="https://www.googleapis.com/compute/v1/projects/project-test/regions/us-central1",
                ip_cidr_range="10.30.1.0/24",
                network=network_ref,
                gateway_address="10.30.1.1",
                private_ip_google_access=True,
                purpose="PRIVATE",
                role="ACTIVE",
            )
            return [("regions/us-central1", types.SimpleNamespace(subnetworks=[subnet]))]

    class _InstancesClient:
        def __init__(self, **_kwargs):
            pass

        def aggregated_list(self, **_kwargs):
            nic = types.SimpleNamespace(
                network_i_p="10.30.1.10",
                subnetwork=subnetwork_ref,
                network=network_ref,
                access_configs=[types.SimpleNamespace(nat_i_p="198.51.100.20")],
            )
            inst = types.SimpleNamespace(
                self_link="https://www.googleapis.com/compute/v1/projects/project-test/zones/us-central1-a/instances/vm-a",
                name="vm-a",
                zone="https://www.googleapis.com/compute/v1/projects/project-test/zones/us-central1-a",
                status="RUNNING",
                machine_type="https://www.googleapis.com/compute/v1/projects/project-test/zones/us-central1-a/machineTypes/e2-micro",
                labels={"env": "test"},
                tags=types.SimpleNamespace(items=["web"]),
                network_interfaces=[nic],
            )
            return [("zones/us-central1-a", types.SimpleNamespace(instances=[inst]))]

    class _EmptyListClient:
        def __init__(self, **_kwargs):
            pass

        def list(self, **_kwargs):
            return []

    compute_v1_mod = types.ModuleType("google.cloud.compute_v1")
    compute_v1_mod.NetworksClient = _NetworksClient
    compute_v1_mod.SubnetworksClient = _SubnetworksClient
    compute_v1_mod.InstancesClient = _InstancesClient
    compute_v1_mod.FirewallsClient = _EmptyListClient
    compute_v1_mod.GlobalForwardingRulesClient = _EmptyListClient
    compute_v1_mod.VpnGatewaysClient = _EmptyListClient
    compute_v1_mod.VpnTunnelsClient = _EmptyListClient
    compute_v1_mod.ForwardingRulesClient = _EmptyListClient

    google_mod = types.ModuleType("google")
    google_cloud_mod = types.ModuleType("google.cloud")
    google_cloud_mod.compute_v1 = compute_v1_mod
    google_oauth2_mod = types.ModuleType("google.oauth2")
    google_service_account_mod = types.ModuleType("google.oauth2.service_account")
    google_service_account_mod.Credentials = _FakeCredentialsFactory

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.cloud", google_cloud_mod)
    monkeypatch.setitem(sys.modules, "google.cloud.compute_v1", compute_v1_mod)
    monkeypatch.setitem(sys.modules, "google.oauth2", google_oauth2_mod)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", google_service_account_mod)

    scanner = CloudScanner(db, acc)
    rows = asyncio.run(scanner.scan())
    vm = next(r for r in rows if str(r.get("resource_type") or "") == "virtual_machine")
    meta = vm.get("resource_metadata") or {}
    assert str(meta.get("subnetwork") or "") == subnetwork_ref
    assert str(meta.get("network") or "") == network_ref
    assert "10.30.1.10" in list(meta.get("private_ips") or [])
    assert "198.51.100.20" in list(meta.get("public_ips") or [])
