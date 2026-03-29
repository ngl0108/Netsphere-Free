import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.cloud import CloudAccount, CloudResource
from app.services.cloud_credentials_service import decrypt_credentials_for_runtime

logger = logging.getLogger(__name__)


class CloudScanner:
    def __init__(self, db: Session, account: CloudAccount):
        self.db = db
        self.account = account
        self.credentials = decrypt_credentials_for_runtime(account.provider, account.credentials or {})

    async def scan(self) -> List[Dict[str, Any]]:
        provider = (self.account.provider or "").strip().lower()
        if provider == "aws":
            return await self._scan_aws()
        if provider == "azure":
            return await self._scan_azure()
        if provider == "gcp":
            return await self._scan_gcp()
        if provider in {"naver", "naver_cloud", "ncp"}:
            return await self._scan_naver()
        raise ValueError(f"Unsupported provider: {self.account.provider}")

    async def preflight(self) -> Dict[str, Any]:
        provider = (self.account.provider or "").strip().lower()
        if provider == "aws":
            return await self._preflight_aws()
        if provider == "azure":
            return await self._preflight_azure()
        if provider == "gcp":
            return await self._preflight_gcp()
        if provider in {"naver", "naver_cloud", "ncp"}:
            return await self._preflight_naver()
        raise ValueError(f"Unsupported provider: {self.account.provider}")

    async def _preflight_aws(self) -> Dict[str, Any]:
        try:
            import boto3
        except Exception as e:
            raise ImportError("boto3 is required for AWS preflight") from e

        region = str(self.credentials.get("region", "ap-northeast-2")).strip() or "ap-northeast-2"
        auth_type = str(
            self.credentials.get("auth_type") or ("assume_role" if self.credentials.get("role_arn") else "access_key")
        ).strip().lower()
        access_key = str(self.credentials.get("access_key") or "").strip()
        secret_key = str(self.credentials.get("secret_key") or "").strip()
        session_token = str(self.credentials.get("session_token") or "").strip()
        source_access_key = str(self.credentials.get("source_access_key") or "").strip()
        source_secret_key = str(self.credentials.get("source_secret_key") or "").strip()
        source_session_token = str(self.credentials.get("source_session_token") or "").strip()
        role_arn = str(self.credentials.get("role_arn") or "").strip()
        external_id = str(self.credentials.get("external_id") or "").strip()
        role_session_name = str(self.credentials.get("role_session_name") or "netsphere-cloud-scan").strip()

        def _sync() -> Dict[str, Any]:
            checks: List[Dict[str, Any]] = []

            try:
                base_kwargs: Dict[str, Any] = {"region_name": region}
                if source_access_key or source_secret_key:
                    if not source_access_key or not source_secret_key:
                        raise ValueError("source_access_key and source_secret_key must be provided together")
                    base_kwargs["aws_access_key_id"] = source_access_key
                    base_kwargs["aws_secret_access_key"] = source_secret_key
                    if source_session_token:
                        base_kwargs["aws_session_token"] = source_session_token
                elif access_key or secret_key:
                    if not access_key or not secret_key:
                        raise ValueError("Missing AWS access_key/secret_key")
                    base_kwargs["aws_access_key_id"] = access_key
                    base_kwargs["aws_secret_access_key"] = secret_key
                    if session_token:
                        base_kwargs["aws_session_token"] = session_token

                base_session = boto3.Session(**base_kwargs)
                session = base_session
                if auth_type == "assume_role":
                    if not role_arn:
                        raise ValueError("Missing AWS role_arn for assume_role auth")
                    sts = base_session.client("sts")
                    assume_kwargs: Dict[str, Any] = {
                        "RoleArn": role_arn,
                        "RoleSessionName": role_session_name,
                    }
                    if external_id:
                        assume_kwargs["ExternalId"] = external_id
                    assumed = sts.assume_role(**assume_kwargs).get("Credentials", {})
                    if not assumed:
                        raise ValueError("AssumeRole returned empty credentials")
                    session = boto3.Session(
                        aws_access_key_id=assumed.get("AccessKeyId"),
                        aws_secret_access_key=assumed.get("SecretAccessKey"),
                        aws_session_token=assumed.get("SessionToken"),
                        region_name=region,
                    )

                caller = session.client("sts").get_caller_identity()
                checks.append(
                    {
                        "key": "sts_identity",
                        "ok": True,
                        "message": f"Authenticated as {str(caller.get('Arn') or caller.get('Account') or 'unknown')}",
                    }
                )
            except Exception as e:
                checks.append({"key": "sts_identity", "ok": False, "message": f"{type(e).__name__}: {e}"})
                return {
                    "provider": "aws",
                    "status": "failed",
                    "checks": checks,
                    "summary": "AWS credential validation failed",
                }

            try:
                ec2 = session.client("ec2")
                ec2.describe_vpcs(MaxResults=5)
                checks.append({"key": "ec2_describe_vpcs", "ok": True, "message": f"DescribeVpcs succeeded ({region})"})
            except Exception as e:
                checks.append({"key": "ec2_describe_vpcs", "ok": False, "message": f"{type(e).__name__}: {e}"})

            ok = all(bool(c.get("ok")) for c in checks)
            return {
                "provider": "aws",
                "status": "ok" if ok else "failed",
                "checks": checks,
                "summary": "AWS preflight passed" if ok else "AWS preflight has failed checks",
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    async def _preflight_azure(self) -> Dict[str, Any]:
        try:
            from azure.identity import ClientSecretCredential
            from azure.mgmt.network import NetworkManagementClient
        except Exception as e:
            raise ImportError("azure-identity and azure-mgmt-network are required for Azure preflight") from e

        tenant_id = self.credentials.get("tenant_id")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")
        subscription_id = self.credentials.get("subscription_id")

        def _sync() -> Dict[str, Any]:
            checks: List[Dict[str, Any]] = []
            try:
                if not all([tenant_id, client_id, client_secret, subscription_id]):
                    raise ValueError("Missing Azure credentials")
                cred = ClientSecretCredential(tenant_id, client_id, client_secret)
                token = cred.get_token("https://management.azure.com/.default")
                token_len = len(str(getattr(token, "token", "") or ""))
                checks.append({"key": "aad_token", "ok": True, "message": f"Token acquired ({token_len} chars)"})
            except Exception as e:
                checks.append({"key": "aad_token", "ok": False, "message": f"{type(e).__name__}: {e}"})
                return {
                    "provider": "azure",
                    "status": "failed",
                    "checks": checks,
                    "summary": "Azure credential validation failed",
                }

            try:
                client = NetworkManagementClient(cred, subscription_id)
                it = client.virtual_networks.list_all()
                next(iter(it), None)
                checks.append({"key": "vnet_list", "ok": True, "message": "Virtual network list succeeded"})
            except Exception as e:
                checks.append({"key": "vnet_list", "ok": False, "message": f"{type(e).__name__}: {e}"})

            ok = all(bool(c.get("ok")) for c in checks)
            return {
                "provider": "azure",
                "status": "ok" if ok else "failed",
                "checks": checks,
                "summary": "Azure preflight passed" if ok else "Azure preflight has failed checks",
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    async def _preflight_gcp(self) -> Dict[str, Any]:
        try:
            from google.cloud import compute_v1
            from google.oauth2 import service_account
        except Exception as e:
            raise ImportError("google-cloud-compute is required for GCP preflight") from e

        project_id = self.credentials.get("project_id")
        sa_json = self.credentials.get("service_account_json")

        def _sync() -> Dict[str, Any]:
            checks: List[Dict[str, Any]] = []
            try:
                if not project_id or not sa_json:
                    raise ValueError("Missing GCP credentials")
                info = json.loads(sa_json) if isinstance(sa_json, str) else sa_json
                creds = service_account.Credentials.from_service_account_info(info)
                checks.append({"key": "service_account_auth", "ok": True, "message": "Service account credentials parsed"})
            except Exception as e:
                checks.append({"key": "service_account_auth", "ok": False, "message": f"{type(e).__name__}: {e}"})
                return {
                    "provider": "gcp",
                    "status": "failed",
                    "checks": checks,
                    "summary": "GCP credential validation failed",
                }

            try:
                client = compute_v1.NetworksClient(credentials=creds)
                it = client.list(project=project_id)
                next(iter(it), None)
                checks.append({"key": "networks_list", "ok": True, "message": "Compute networks list succeeded"})
            except Exception as e:
                checks.append({"key": "networks_list", "ok": False, "message": f"{type(e).__name__}: {e}"})

            ok = all(bool(c.get("ok")) for c in checks)
            return {
                "provider": "gcp",
                "status": "ok" if ok else "failed",
                "checks": checks,
                "summary": "GCP preflight passed" if ok else "GCP preflight has failed checks",
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    async def _preflight_naver(self) -> Dict[str, Any]:
        try:
            import ncloud_vpc
            from ncloud_vpc.api.v2_api import V2Api
            from ncloud_vpc.configuration import Configuration
            from ncloud_vpc.api_client import ApiClient
            from ncloud_vpc.model.get_vpc_list_request import GetVpcListRequest
        except Exception as e:
            raise ImportError("ncloud-vpc is required for Naver Cloud preflight") from e

        access_key = self.credentials.get("access_key")
        secret_key = self.credentials.get("secret_key")
        region_code = self.credentials.get("region_code") or self.credentials.get("region")

        def _sync() -> Dict[str, Any]:
            checks: List[Dict[str, Any]] = []
            try:
                if not access_key or not secret_key:
                    raise ValueError("Missing Naver Cloud credentials")
                configuration = Configuration()
                configuration.access_key = access_key
                configuration.secret_key = secret_key
                api = V2Api(ApiClient(configuration))
                req = GetVpcListRequest()
                if region_code:
                    req.region_code = str(region_code)
                api.get_vpc_list(req)
                checks.append({"key": "vpc_list", "ok": True, "message": "VPC list succeeded"})
            except Exception as e:
                checks.append({"key": "vpc_list", "ok": False, "message": f"{type(e).__name__}: {e}"})
                return {
                    "provider": "naver",
                    "status": "failed",
                    "checks": checks,
                    "summary": "Naver Cloud preflight failed",
                }

            return {
                "provider": "naver",
                "status": "ok",
                "checks": checks,
                "summary": "Naver Cloud preflight passed",
            }

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync)

    async def _scan_aws(self) -> List[Dict[str, Any]]:
        try:
            import boto3
        except Exception as e:
            raise ImportError("boto3 is required for AWS scanning") from e

        region = str(self.credentials.get("region", "ap-northeast-2")).strip() or "ap-northeast-2"
        auth_type = str(
            self.credentials.get("auth_type") or ("assume_role" if self.credentials.get("role_arn") else "access_key")
        ).strip().lower()
        access_key = str(self.credentials.get("access_key") or "").strip()
        secret_key = str(self.credentials.get("secret_key") or "").strip()
        session_token = str(self.credentials.get("session_token") or "").strip()

        source_access_key = str(self.credentials.get("source_access_key") or "").strip()
        source_secret_key = str(self.credentials.get("source_secret_key") or "").strip()
        source_session_token = str(self.credentials.get("source_session_token") or "").strip()

        role_arn = str(self.credentials.get("role_arn") or "").strip()
        external_id = str(self.credentials.get("external_id") or "").strip()
        role_session_name = str(self.credentials.get("role_session_name") or "netsphere-cloud-scan").strip()

        if auth_type not in {"access_key", "assume_role"}:
            raise ValueError("Invalid AWS auth_type")

        def _sync() -> List[Dict[str, Any]]:
            base_kwargs: Dict[str, Any] = {"region_name": region}
            if source_access_key or source_secret_key:
                if not source_access_key or not source_secret_key:
                    raise ValueError("source_access_key and source_secret_key must be provided together")
                base_kwargs["aws_access_key_id"] = source_access_key
                base_kwargs["aws_secret_access_key"] = source_secret_key
                if source_session_token:
                    base_kwargs["aws_session_token"] = source_session_token
            elif access_key or secret_key:
                if not access_key or not secret_key:
                    raise ValueError("Missing AWS access_key/secret_key")
                base_kwargs["aws_access_key_id"] = access_key
                base_kwargs["aws_secret_access_key"] = secret_key
                if session_token:
                    base_kwargs["aws_session_token"] = session_token

            base_session = boto3.Session(**base_kwargs)

            if auth_type == "assume_role":
                if not role_arn:
                    raise ValueError("Missing AWS role_arn for assume_role auth")
                sts = base_session.client("sts")
                assume_kwargs: Dict[str, Any] = {
                    "RoleArn": role_arn,
                    "RoleSessionName": role_session_name,
                }
                if external_id:
                    assume_kwargs["ExternalId"] = external_id
                assumed = sts.assume_role(**assume_kwargs).get("Credentials", {})
                if not assumed:
                    raise ValueError("AssumeRole returned empty credentials")
                session = boto3.Session(
                    aws_access_key_id=assumed.get("AccessKeyId"),
                    aws_secret_access_key=assumed.get("SecretAccessKey"),
                    aws_session_token=assumed.get("SessionToken"),
                    region_name=region,
                )
            else:
                if not access_key or not secret_key:
                    raise ValueError("Missing AWS credentials")
                session = base_session

            ec2 = session.client("ec2")
            resources: List[Dict[str, Any]] = []

            def _safe_call(fn):
                try:
                    return fn()
                except Exception:
                    return {}

            vpcs = ec2.describe_vpcs()
            for vpc in vpcs.get("Vpcs", []):
                resources.append(
                    {
                        "resource_id": vpc["VpcId"],
                        "resource_type": "vpc",
                        "name": _aws_tag(vpc.get("Tags", []), "Name") or vpc["VpcId"],
                        "region": region,
                        "cidr_block": vpc.get("CidrBlock"),
                        "state": vpc.get("State"),
                        "resource_metadata": {"is_default": vpc.get("IsDefault", False)},
                    }
                )

            subnets = _safe_call(ec2.describe_subnets)
            for subnet in subnets.get("Subnets", []) or []:
                resources.append(
                    {
                        "resource_id": subnet.get("SubnetId"),
                        "resource_type": "subnet",
                        "name": _aws_tag(subnet.get("Tags", []), "Name") or subnet.get("SubnetId"),
                        "region": region,
                        "cidr_block": subnet.get("CidrBlock"),
                        "state": subnet.get("State"),
                        "resource_metadata": {
                            "vpc_id": subnet.get("VpcId"),
                            "availability_zone": subnet.get("AvailabilityZone"),
                            "available_ip_count": subnet.get("AvailableIpAddressCount"),
                            "map_public_ip_on_launch": bool(subnet.get("MapPublicIpOnLaunch", False)),
                        },
                    }
                )

            cgws = _safe_call(ec2.describe_customer_gateways)
            for cgw in cgws.get("CustomerGateways", []) or []:
                resources.append(
                    {
                        "resource_id": cgw.get("CustomerGatewayId"),
                        "resource_type": "customer_gateway",
                        "name": _aws_tag(cgw.get("Tags", []), "Name") or cgw.get("CustomerGatewayId"),
                        "region": region,
                        "state": cgw.get("State"),
                        "resource_metadata": {
                            "bgp_asn": cgw.get("BgpAsn"),
                            "ip_address": cgw.get("IpAddress"),
                            "type": cgw.get("Type"),
                        },
                    }
                )

            vgws = _safe_call(ec2.describe_vpn_gateways)
            for vgw in vgws.get("VpnGateways", []):
                resources.append(
                    {
                        "resource_id": vgw["VpnGatewayId"],
                        "resource_type": "vpn_gateway",
                        "name": _aws_tag(vgw.get("Tags", []), "Name") or vgw["VpnGatewayId"],
                        "region": region,
                        "state": vgw.get("State"),
                        "resource_metadata": {"type": vgw.get("Type"), "asn": vgw.get("AmazonSideAsn")},
                    }
                )

            vpns = _safe_call(ec2.describe_vpn_connections)
            for vpn in vpns.get("VpnConnections", []):
                tunnels: List[Dict[str, Any]] = []
                for t in vpn.get("VgwTelemetry", []) or []:
                    tunnels.append(
                        {
                            "outside_ip": t.get("OutsideIpAddress"),
                            "status": t.get("Status"),
                            "status_message": t.get("StatusMessage"),
                        }
                    )
                resources.append(
                    {
                        "resource_id": vpn["VpnConnectionId"],
                        "resource_type": "vpn_connection",
                        "name": _aws_tag(vpn.get("Tags", []), "Name") or vpn["VpnConnectionId"],
                        "region": region,
                        "state": vpn.get("State"),
                        "resource_metadata": {
                            "customer_gateway_id": vpn.get("CustomerGatewayId"),
                            "vpn_gateway_id": vpn.get("VpnGatewayId"),
                            "tunnels": tunnels,
                        },
                    }
                )

            sgs = _safe_call(ec2.describe_security_groups)
            for sg in sgs.get("SecurityGroups", []) or []:
                resources.append(
                    {
                        "resource_id": sg.get("GroupId"),
                        "resource_type": "security_group",
                        "name": sg.get("GroupName") or sg.get("GroupId"),
                        "region": region,
                        "state": None,
                        "resource_metadata": {
                            "vpc_id": sg.get("VpcId"),
                            "description": sg.get("Description"),
                            "inbound_rules": len(list(sg.get("IpPermissions") or [])),
                            "outbound_rules": len(list(sg.get("IpPermissionsEgress") or [])),
                        },
                    }
                )

            ec2_instances = _safe_call(ec2.describe_instances)
            for reservation in ec2_instances.get("Reservations", []) or []:
                for inst in reservation.get("Instances", []) or []:
                    private_ips: List[str] = []
                    public_ips: List[str] = []

                    primary_private = str(inst.get("PrivateIpAddress") or "").strip()
                    primary_public = str(inst.get("PublicIpAddress") or "").strip()
                    if primary_private:
                        private_ips.append(primary_private)
                    if primary_public:
                        public_ips.append(primary_public)

                    for nic in inst.get("NetworkInterfaces", []) or []:
                        assoc = nic.get("Association") if isinstance(nic, dict) else None
                        if isinstance(assoc, dict):
                            assoc_ip = str(assoc.get("PublicIp") or "").strip()
                            if assoc_ip:
                                public_ips.append(assoc_ip)
                        for p in nic.get("PrivateIpAddresses", []) or []:
                            if not isinstance(p, dict):
                                continue
                            p_ip = str(p.get("PrivateIpAddress") or "").strip()
                            if p_ip:
                                private_ips.append(p_ip)
                            p_assoc = p.get("Association")
                            if isinstance(p_assoc, dict):
                                p_pub = str(p_assoc.get("PublicIp") or "").strip()
                                if p_pub:
                                    public_ips.append(p_pub)

                    private_ips = sorted({ip for ip in private_ips if ip})
                    public_ips = sorted({ip for ip in public_ips if ip})
                    resources.append(
                        {
                            "resource_id": inst.get("InstanceId"),
                            "resource_type": "virtual_machine",
                            "name": _aws_tag(inst.get("Tags", []), "Name") or inst.get("InstanceId"),
                            "region": region,
                            "cidr_block": None,
                            "state": ((inst.get("State") or {}).get("Name") if isinstance(inst.get("State"), dict) else None),
                            "resource_metadata": {
                                "vpc_id": inst.get("VpcId"),
                                "subnet_id": inst.get("SubnetId"),
                                "instance_type": inst.get("InstanceType"),
                                "private_ip": primary_private or None,
                                "public_ip": primary_public or None,
                                "private_ips": private_ips,
                                "public_ips": public_ips,
                                "security_group_ids": [
                                    str(sg.get("GroupId"))
                                    for sg in (inst.get("SecurityGroups") or [])
                                    if isinstance(sg, dict) and str(sg.get("GroupId") or "").strip()
                                ],
                                "iam_profile_arn": ((inst.get("IamInstanceProfile") or {}).get("Arn") if isinstance(inst.get("IamInstanceProfile"), dict) else None),
                            },
                        }
                    )

            tgws = _safe_call(ec2.describe_transit_gateways)
            for tgw in tgws.get("TransitGateways", []) or []:
                resources.append(
                    {
                        "resource_id": tgw.get("TransitGatewayId"),
                        "resource_type": "transit_gateway",
                        "name": _aws_tag(tgw.get("Tags", []), "Name") or tgw.get("TransitGatewayId"),
                        "region": region,
                        "state": tgw.get("State"),
                        "resource_metadata": {
                            "amazon_side_asn": tgw.get("AmazonSideAsn"),
                            "default_route_table_id": tgw.get("AssociationDefaultRouteTableId") or tgw.get("PropagationDefaultRouteTableId"),
                        },
                    }
                )

            tgw_atts = _safe_call(ec2.describe_transit_gateway_attachments)
            for att in tgw_atts.get("TransitGatewayAttachments", []) or []:
                resources.append(
                    {
                        "resource_id": att.get("TransitGatewayAttachmentId"),
                        "resource_type": "tgw_attachment",
                        "name": _aws_tag(att.get("Tags", []), "Name") or att.get("TransitGatewayAttachmentId"),
                        "region": region,
                        "state": att.get("State"),
                        "resource_metadata": {
                            "tgw_id": att.get("TransitGatewayId"),
                            "resource_id": att.get("ResourceId"),
                            "resource_type": att.get("ResourceType"),
                        },
                    }
                )

            rts = _safe_call(ec2.describe_route_tables)
            for rt in rts.get("RouteTables", []) or []:
                routes = []
                for r in (rt.get("Routes", []) or [])[:200]:
                    routes.append(
                        {
                            "dst_cidr": r.get("DestinationCidrBlock") or r.get("DestinationIpv6CidrBlock"),
                            "state": r.get("State"),
                            "gateway_id": r.get("GatewayId"),
                            "tgw_id": r.get("TransitGatewayId"),
                            "nat_gateway_id": r.get("NatGatewayId"),
                            "instance_id": r.get("InstanceId"),
                            "network_interface_id": r.get("NetworkInterfaceId"),
                            "origin": r.get("Origin"),
                        }
                    )
                resources.append(
                    {
                        "resource_id": rt.get("RouteTableId"),
                        "resource_type": "route_table",
                        "name": _aws_tag(rt.get("Tags", []), "Name") or rt.get("RouteTableId"),
                        "region": region,
                        "state": None,
                        "resource_metadata": {
                            "vpc_id": rt.get("VpcId"),
                            "routes": routes,
                            "associations": [
                                {
                                    "id": a.get("RouteTableAssociationId"),
                                    "subnet_id": a.get("SubnetId"),
                                    "main": bool(a.get("Main", False)),
                                }
                                for a in (rt.get("Associations", []) or [])[:50]
                                if isinstance(a, dict)
                            ],
                        },
                    }
                )

            try:
                elbv2 = session.client("elbv2")
            except Exception:
                elbv2 = None
            if elbv2 is not None:
                lbs = _safe_call(lambda: elbv2.describe_load_balancers())
                for lb in lbs.get("LoadBalancers", []) or []:
                    resources.append(
                        {
                            "resource_id": lb.get("LoadBalancerArn") or lb.get("LoadBalancerName"),
                            "resource_type": "load_balancer",
                            "name": lb.get("LoadBalancerName") or lb.get("LoadBalancerArn"),
                            "region": region,
                            "cidr_block": None,
                            "state": ((lb.get("State") or {}).get("Code") if isinstance(lb.get("State"), dict) else None),
                            "resource_metadata": {
                                "vpc_id": lb.get("VpcId"),
                                "scheme": lb.get("Scheme"),
                                "lb_type": lb.get("Type"),
                                "dns_name": lb.get("DNSName"),
                                "canonical_hosted_zone_id": lb.get("CanonicalHostedZoneId"),
                                "ip_address_type": lb.get("IpAddressType"),
                                "security_group_ids": list(lb.get("SecurityGroups") or []),
                                "availability_zones": [
                                    str(az.get("ZoneName"))
                                    for az in (lb.get("AvailabilityZones") or [])
                                    if isinstance(az, dict) and str(az.get("ZoneName") or "").strip()
                                ],
                            },
                        }
                    )

            return resources

        return await self._run_and_persist(_sync)

    async def _scan_azure(self) -> List[Dict[str, Any]]:
        try:
            from azure.identity import ClientSecretCredential
            from azure.mgmt.network import NetworkManagementClient
        except Exception as e:
            raise ImportError("azure-identity and azure-mgmt-network are required for Azure scanning") from e

        tenant_id = self.credentials.get("tenant_id")
        client_id = self.credentials.get("client_id")
        client_secret = self.credentials.get("client_secret")
        subscription_id = self.credentials.get("subscription_id")

        if not all([tenant_id, client_id, client_secret, subscription_id]):
            raise ValueError("Missing Azure credentials")

        def _sync() -> List[Dict[str, Any]]:
            cred = ClientSecretCredential(tenant_id, client_id, client_secret)
            client = NetworkManagementClient(cred, subscription_id)
            resources: List[Dict[str, Any]] = []
            for vnet in client.virtual_networks.list_all():
                prefixes = []
                if vnet.address_space and vnet.address_space.address_prefixes:
                    prefixes = list(vnet.address_space.address_prefixes)
                resources.append(
                    {
                        "resource_id": vnet.id,
                        "resource_type": "vnet",
                        "name": vnet.name,
                        "region": vnet.location,
                        "cidr_block": prefixes[0] if prefixes else None,
                        "state": getattr(vnet, "provisioning_state", None),
                        "resource_metadata": {"prefixes": prefixes},
                    }
                )
                for subnet in list(getattr(vnet, "subnets", None) or []):
                    prefix = getattr(subnet, "address_prefix", None)
                    if not prefix:
                        prefixes_obj = list(getattr(subnet, "address_prefixes", None) or [])
                        prefix = prefixes_obj[0] if prefixes_obj else None
                    resources.append(
                        {
                            "resource_id": getattr(subnet, "id", None) or f"{vnet.id}/subnets/{getattr(subnet, 'name', 'subnet')}",
                            "resource_type": "subnet",
                            "name": getattr(subnet, "name", None) or getattr(subnet, "id", None),
                            "region": vnet.location,
                            "cidr_block": prefix,
                            "state": getattr(subnet, "provisioning_state", None),
                            "resource_metadata": {
                                "vnet_id": vnet.id,
                                "network_security_group": (
                                    getattr(getattr(subnet, "network_security_group", None), "id", None)
                                ),
                                "private_endpoint_network_policies": getattr(subnet, "private_endpoint_network_policies", None),
                            },
                        }
                    )

            try:
                for nsg in client.network_security_groups.list_all():
                    resources.append(
                        {
                            "resource_id": getattr(nsg, "id", None),
                            "resource_type": "security_group",
                            "name": getattr(nsg, "name", None) or getattr(nsg, "id", None),
                            "region": getattr(nsg, "location", None),
                            "cidr_block": None,
                            "state": getattr(nsg, "provisioning_state", None),
                            "resource_metadata": {
                                "security_rule_count": len(list(getattr(nsg, "security_rules", None) or [])),
                                "default_security_rule_count": len(list(getattr(nsg, "default_security_rules", None) or [])),
                            },
                        }
                    )
            except Exception:
                pass

            try:
                for lb in client.load_balancers.list_all():
                    frontend_ips: List[str] = []
                    for cfg in list(getattr(lb, "frontend_ip_configurations", None) or []):
                        private_ip = str(getattr(cfg, "private_ip_address", "") or "").strip()
                        if private_ip:
                            frontend_ips.append(private_ip)
                    resources.append(
                        {
                            "resource_id": getattr(lb, "id", None),
                            "resource_type": "load_balancer",
                            "name": getattr(lb, "name", None) or getattr(lb, "id", None),
                            "region": getattr(lb, "location", None),
                            "cidr_block": None,
                            "state": getattr(lb, "provisioning_state", None),
                            "resource_metadata": {
                                "sku": (getattr(getattr(lb, "sku", None), "name", None)),
                                "frontend_ips": sorted({ip for ip in frontend_ips if ip}),
                                "backend_pool_count": len(list(getattr(lb, "backend_address_pools", None) or [])),
                            },
                        }
                    )
            except Exception:
                pass

            try:
                from azure.mgmt.compute import ComputeManagementClient  # type: ignore

                compute_client = ComputeManagementClient(cred, subscription_id)
                for vm in compute_client.virtual_machines.list_all():
                    nic_ids = [
                        str(getattr(nic, "id", "") or "").strip()
                        for nic in list(getattr(getattr(vm, "network_profile", None), "network_interfaces", None) or [])
                        if str(getattr(nic, "id", "") or "").strip()
                    ]
                    subnet_ids: List[str] = []
                    vnet_ids: List[str] = []
                    private_ips: List[str] = []
                    public_ips: List[str] = []

                    for nic_id in nic_ids:
                        nic_obj = None
                        try:
                            m = re.search(
                                r"/resourceGroups/([^/]+)/providers/Microsoft\.Network/networkInterfaces/([^/]+)",
                                nic_id,
                                flags=re.IGNORECASE,
                            )
                            if m:
                                rg_name = str(m.group(1))
                                nic_name = str(m.group(2))
                                nic_obj = client.network_interfaces.get(rg_name, nic_name)
                        except Exception:
                            nic_obj = None

                        if nic_obj is None:
                            continue

                        for ip_cfg in list(getattr(nic_obj, "ip_configurations", None) or []):
                            subnet_id = str(getattr(getattr(ip_cfg, "subnet", None), "id", "") or "").strip()
                            if subnet_id:
                                subnet_ids.append(subnet_id)

                            p_ip = str(getattr(ip_cfg, "private_ip_address", "") or "").strip()
                            if p_ip:
                                private_ips.append(p_ip)

                            pub_ref_id = str(getattr(getattr(ip_cfg, "public_ip_address", None), "id", "") or "").strip()
                            if pub_ref_id:
                                try:
                                    pm = re.search(
                                        r"/resourceGroups/([^/]+)/providers/Microsoft\.Network/publicIPAddresses/([^/]+)",
                                        pub_ref_id,
                                        flags=re.IGNORECASE,
                                    )
                                    if pm:
                                        prg_name = str(pm.group(1))
                                        pip_name = str(pm.group(2))
                                        pip_obj = client.public_ip_addresses.get(prg_name, pip_name)
                                        pip_addr = str(getattr(pip_obj, "ip_address", "") or "").strip()
                                        if pip_addr:
                                            public_ips.append(pip_addr)
                                except Exception:
                                    pass

                    subnet_ids = sorted({s for s in subnet_ids if s})
                    for subnet_id in subnet_ids:
                        mark = "/subnets/"
                        idx = subnet_id.lower().find(mark)
                        if idx > 0:
                            vnet_ids.append(subnet_id[:idx])
                    vnet_ids = sorted({v for v in vnet_ids if v})
                    private_ips = sorted({ip for ip in private_ips if ip})
                    public_ips = sorted({ip for ip in public_ips if ip})

                    resources.append(
                        {
                            "resource_id": getattr(vm, "id", None),
                            "resource_type": "virtual_machine",
                            "name": getattr(vm, "name", None) or getattr(vm, "id", None),
                            "region": getattr(vm, "location", None),
                            "cidr_block": None,
                            "state": getattr(vm, "provisioning_state", None),
                            "resource_metadata": {
                                "vm_size": getattr(getattr(vm, "hardware_profile", None), "vm_size", None),
                                "network_interface_ids": nic_ids,
                                "subnet_id": subnet_ids[0] if subnet_ids else None,
                                "subnet_ids": subnet_ids,
                                "vnet_id": vnet_ids[0] if vnet_ids else None,
                                "vnet_ids": vnet_ids,
                                "private_ips": private_ips,
                                "public_ips": public_ips,
                                "zones": list(getattr(vm, "zones", None) or []),
                            },
                        }
                    )
            except Exception:
                pass
            return resources

        return await self._run_and_persist(_sync)

    async def _scan_gcp(self) -> List[Dict[str, Any]]:
        try:
            from google.cloud import compute_v1
            from google.oauth2 import service_account
        except Exception as e:
            raise ImportError("google-cloud-compute is required for GCP scanning") from e

        project_id = self.credentials.get("project_id")
        sa_json = self.credentials.get("service_account_json")
        regions = self.credentials.get("regions")

        if not project_id or not sa_json:
            raise ValueError("Missing GCP credentials")
        try:
            info = json.loads(sa_json) if isinstance(sa_json, str) else sa_json
        except Exception as e:
            raise ValueError("Invalid GCP service_account_json") from e

        creds = service_account.Credentials.from_service_account_info(info)

        def _sync() -> List[Dict[str, Any]]:
            resources: List[Dict[str, Any]] = []

            networks_client = compute_v1.NetworksClient(credentials=creds)
            for net in networks_client.list(project=project_id):
                cidr = None
                if getattr(net, "IPv4Range", None):
                    cidr = net.IPv4Range
                resources.append(
                    {
                        "resource_id": net.self_link,
                        "resource_type": "network",
                        "name": net.name,
                        "region": "global",
                        "cidr_block": cidr,
                        "state": None,
                        "resource_metadata": {"auto_create_subnetworks": bool(getattr(net, "auto_create_subnetworks", False))},
                    }
                )

            try:
                subnetworks_client = compute_v1.SubnetworksClient(credentials=creds)
                for _scope, scoped_list in subnetworks_client.aggregated_list(project=project_id):
                    for sn in list(getattr(scoped_list, "subnetworks", None) or []):
                        sn_region = str(getattr(sn, "region", "") or "").split("/")[-1] or "global"
                        resources.append(
                            {
                                "resource_id": getattr(sn, "self_link", None) or getattr(sn, "name", None),
                                "resource_type": "subnet",
                                "name": getattr(sn, "name", None),
                                "region": sn_region,
                                "cidr_block": getattr(sn, "ip_cidr_range", None),
                                "state": None,
                                "resource_metadata": {
                                    "network": getattr(sn, "network", None),
                                    "gateway_address": getattr(sn, "gateway_address", None),
                                    "private_ip_google_access": bool(getattr(sn, "private_ip_google_access", False)),
                                    "purpose": getattr(sn, "purpose", None),
                                    "role": getattr(sn, "role", None),
                                },
                            }
                        )
            except Exception:
                pass

            try:
                instances_client = compute_v1.InstancesClient(credentials=creds)
                for _scope, scoped_list in instances_client.aggregated_list(project=project_id):
                    for inst in list(getattr(scoped_list, "instances", None) or []):
                        private_ips: List[str] = []
                        public_ips: List[str] = []
                        subnetworks: List[str] = []
                        networks: List[str] = []
                        for nic in list(getattr(inst, "network_interfaces", None) or []):
                            p = str(getattr(nic, "network_i_p", "") or "").strip()
                            if p:
                                private_ips.append(p)
                            sn = str(getattr(nic, "subnetwork", "") or "").strip()
                            if sn:
                                subnetworks.append(sn)
                            net_ref = str(getattr(nic, "network", "") or "").strip()
                            if net_ref:
                                networks.append(net_ref)
                            for ac in list(getattr(nic, "access_configs", None) or []):
                                pub = str(getattr(ac, "nat_i_p", "") or "").strip()
                                if pub:
                                    public_ips.append(pub)
                        subnetworks = sorted({sn for sn in subnetworks if sn})
                        networks = sorted({n for n in networks if n})
                        zone_name = str(getattr(inst, "zone", "") or "").split("/")[-1] or None
                        resources.append(
                            {
                                "resource_id": getattr(inst, "self_link", None) or getattr(inst, "name", None),
                                "resource_type": "virtual_machine",
                                "name": getattr(inst, "name", None),
                                "region": zone_name,
                                "cidr_block": None,
                                "state": getattr(inst, "status", None),
                                "resource_metadata": {
                                    "machine_type": str(getattr(inst, "machine_type", "") or "").split("/")[-1] or None,
                                    "private_ips": sorted({ip for ip in private_ips if ip}),
                                    "public_ips": sorted({ip for ip in public_ips if ip}),
                                    "subnetwork": subnetworks[0] if subnetworks else None,
                                    "subnetworks": subnetworks,
                                    "network": networks[0] if networks else None,
                                    "networks": networks,
                                    "labels": dict(getattr(inst, "labels", None) or {}),
                                    "network_tags": list(getattr(getattr(inst, "tags", None), "items", None) or []),
                                },
                            }
                        )
            except Exception:
                pass

            try:
                fw_client = compute_v1.FirewallsClient(credentials=creds)
                for fw in fw_client.list(project=project_id):
                    resources.append(
                        {
                            "resource_id": getattr(fw, "self_link", None) or getattr(fw, "name", None),
                            "resource_type": "security_group",
                            "name": getattr(fw, "name", None),
                            "region": "global",
                            "cidr_block": None,
                            "state": None if not bool(getattr(fw, "disabled", False)) else "disabled",
                            "resource_metadata": {
                                "network": getattr(fw, "network", None),
                                "direction": getattr(fw, "direction", None),
                                "priority": getattr(fw, "priority", None),
                                "source_ranges": list(getattr(fw, "source_ranges", None) or []),
                                "destination_ranges": list(getattr(fw, "destination_ranges", None) or []),
                            },
                        }
                    )
            except Exception:
                pass

            try:
                gfr_client = compute_v1.GlobalForwardingRulesClient(credentials=creds)
                for fr in gfr_client.list(project=project_id):
                    resources.append(
                        {
                            "resource_id": getattr(fr, "self_link", None) or getattr(fr, "name", None),
                            "resource_type": "load_balancer",
                            "name": getattr(fr, "name", None),
                            "region": "global",
                            "cidr_block": None,
                            "state": None,
                            "resource_metadata": {
                                "ip_address": getattr(fr, "i_p_address", None),
                                "ip_protocol": getattr(fr, "i_p_protocol", None),
                                "load_balancing_scheme": getattr(fr, "load_balancing_scheme", None),
                                "target": getattr(fr, "target", None),
                                "port_range": getattr(fr, "port_range", None),
                            },
                        }
                    )
            except Exception:
                pass

            region_list: List[str] = []
            if isinstance(regions, list):
                region_list = [str(r) for r in regions if r]
            elif isinstance(regions, str) and regions.strip():
                region_list = [r.strip() for r in regions.split(",") if r.strip()]

            if region_list:
                vpn_gateways_client = compute_v1.VpnGatewaysClient(credentials=creds)
                vpn_tunnels_client = compute_v1.VpnTunnelsClient(credentials=creds)
                forwarding_rules_client = compute_v1.ForwardingRulesClient(credentials=creds)
                for region_name in region_list:
                    for gw in vpn_gateways_client.list(project=project_id, region=region_name):
                        resources.append(
                            {
                                "resource_id": gw.self_link,
                                "resource_type": "vpn_gateway",
                                "name": gw.name,
                                "region": region_name,
                                "cidr_block": None,
                                "state": getattr(gw, "status", None),
                                "resource_metadata": {"network": getattr(gw, "network", None)},
                            }
                        )
                    for t in vpn_tunnels_client.list(project=project_id, region=region_name):
                        resources.append(
                            {
                                "resource_id": t.self_link,
                                "resource_type": "vpn_tunnel",
                                "name": t.name,
                                "region": region_name,
                                "cidr_block": None,
                                "state": getattr(t, "status", None),
                                "resource_metadata": {
                                    "peer_ip": getattr(t, "peer_ip", None),
                                    "shared_secret_hash": getattr(t, "shared_secret_hash", None),
                                    "vpn_gateway": getattr(t, "vpn_gateway", None),
                                    "router": getattr(t, "router", None),
                                },
                            }
                        )
                    try:
                        for fr in forwarding_rules_client.list(project=project_id, region=region_name):
                            resources.append(
                                {
                                    "resource_id": getattr(fr, "self_link", None) or getattr(fr, "name", None),
                                    "resource_type": "load_balancer",
                                    "name": getattr(fr, "name", None),
                                    "region": region_name,
                                    "cidr_block": None,
                                    "state": None,
                                    "resource_metadata": {
                                        "ip_address": getattr(fr, "i_p_address", None),
                                        "ip_protocol": getattr(fr, "i_p_protocol", None),
                                        "load_balancing_scheme": getattr(fr, "load_balancing_scheme", None),
                                        "target": getattr(fr, "target", None),
                                        "port_range": getattr(fr, "port_range", None),
                                        "subnetwork": getattr(fr, "subnetwork", None),
                                    },
                                }
                            )
                    except Exception:
                        pass

            return resources

        return await self._run_and_persist(_sync)

    async def _scan_naver(self) -> List[Dict[str, Any]]:
        try:
            import ncloud_vpc
            from ncloud_vpc.api.v2_api import V2Api
            from ncloud_vpc.configuration import Configuration
            from ncloud_vpc.api_client import ApiClient
            from ncloud_vpc.model.get_vpc_list_request import GetVpcListRequest
            from ncloud_vpc.model.get_subnet_list_request import GetSubnetListRequest
        except Exception as e:
            raise ImportError("ncloud-vpc is required for Naver Cloud scanning") from e

        access_key = self.credentials.get("access_key")
        secret_key = self.credentials.get("secret_key")
        region_code = self.credentials.get("region_code") or self.credentials.get("region")

        if not access_key or not secret_key:
            raise ValueError("Missing Naver Cloud credentials")

        def _sync() -> List[Dict[str, Any]]:
            configuration = Configuration()
            configuration.access_key = access_key
            configuration.secret_key = secret_key
            api = V2Api(ApiClient(configuration))
            req = GetVpcListRequest()
            if region_code:
                req.region_code = str(region_code)
            resp = api.get_vpc_list(req)

            vpc_list = []
            if hasattr(resp, "vpc_list") and resp.vpc_list:
                vpc_list = list(resp.vpc_list)

            resources: List[Dict[str, Any]] = []
            for vpc in vpc_list:
                vpc_no = getattr(vpc, "vpc_no", None) or getattr(vpc, "vpc_no", "")
                resources.append(
                    {
                        "resource_id": vpc_no,
                        "resource_type": "vpc",
                        "name": getattr(vpc, "vpc_name", None) or getattr(vpc, "vpc_no", None),
                        "region": getattr(vpc, "region_code", None) or (str(region_code) if region_code else None),
                        "cidr_block": getattr(vpc, "ipv4_cidr_block", None),
                        "state": getattr(vpc, "vpc_status", None),
                        "resource_metadata": {
                            "vpc_status_code": getattr(vpc, "vpc_status_code", None),
                            "create_date": str(getattr(vpc, "create_date", "")) or None,
                        },
                    }
                )

                # Subnets under each VPC
                try:
                    sreq = GetSubnetListRequest(vpc_no=str(vpc_no))
                    if region_code:
                        sreq.region_code = str(region_code)
                    sresp = api.get_subnet_list(sreq)
                    subnet_list = list(getattr(sresp, "subnet_list", []) or [])
                except Exception:
                    subnet_list = []

                for subnet in subnet_list:
                    subnet_no = getattr(subnet, "subnet_no", None) or getattr(subnet, "subnet_no", "")
                    resources.append(
                        {
                            "resource_id": str(subnet_no),
                            "resource_type": "subnet",
                            "name": getattr(subnet, "subnet_name", None) or str(subnet_no),
                            "region": getattr(subnet, "region_code", None)
                            or getattr(vpc, "region_code", None)
                            or (str(region_code) if region_code else None),
                            "cidr_block": getattr(subnet, "subnet", None),
                            "state": getattr(subnet, "subnet_status", None),
                            "resource_metadata": {
                                "vpc_no": str(vpc_no) if vpc_no else None,
                                "zone_code": getattr(subnet, "zone_code", None),
                                "subnet_type": getattr(subnet, "subnet_type", None),
                                "usage_type": getattr(subnet, "usage_type", None),
                                "network_acl_no": getattr(subnet, "network_acl_no", None),
                                "create_date": str(getattr(subnet, "create_date", "")) or None,
                            },
                        }
                    )

            # Server instances (best-effort: do not fail whole scan if this API is not allowed)
            try:
                from ncloud_vserver.api.v2_api import V2Api as VServerApi
                from ncloud_vserver.configuration import Configuration as VServerConfiguration
                from ncloud_vserver.api_client import ApiClient as VServerApiClient
                from ncloud_vserver.model.get_server_instance_list_request import GetServerInstanceListRequest

                vserver_cfg = VServerConfiguration()
                vserver_cfg.access_key = access_key
                vserver_cfg.secret_key = secret_key
                vserver_api = VServerApi(VServerApiClient(vserver_cfg))

                sreq = GetServerInstanceListRequest()
                if region_code:
                    sreq.region_code = str(region_code)
                sresp = vserver_api.get_server_instance_list(sreq)
                server_list = list(getattr(sresp, "server_instance_list", []) or [])

                for server in server_list:
                    server_no = getattr(server, "server_instance_no", None) or ""
                    server_name = getattr(server, "server_name", None) or str(server_no)
                    private_ip = getattr(server, "private_ip", None)
                    resources.append(
                        {
                            "resource_id": str(server_no),
                            "resource_type": "virtual_machine",
                            "name": server_name,
                            "region": getattr(server, "region_code", None) or (str(region_code) if region_code else None),
                            "cidr_block": None,
                            "state": getattr(server, "server_instance_status", None),
                            "resource_metadata": {
                                "server_instance_no": str(server_no),
                                "vpc_no": getattr(server, "vpc_no", None),
                                "subnet_no": getattr(server, "subnet_no", None),
                                "zone_code": getattr(server, "zone_code", None),
                                "private_ips": [private_ip] if private_ip else [],
                                "public_ips": [],
                                "server_image_name": getattr(server, "server_image_name", None),
                                "server_spec_code": getattr(server, "server_product_code", None),
                            },
                        }
                    )
            except Exception:
                # Keep scan partially successful (VPC/Subnet) even when server API is blocked.
                pass

            return resources

        return await self._run_and_persist(_sync)

    async def _run_and_persist(self, sync_fn) -> List[Dict[str, Any]]:
        loop = asyncio.get_running_loop()
        try:
            results: List[Dict[str, Any]] = await loop.run_in_executor(None, sync_fn)
            self._save_resources(results)
            self.account.last_synced_at = datetime.now()
            self.account.sync_status = "success"
            self.account.sync_message = f"Scanned {len(results)} resources"
            self.db.commit()
            return results
        except Exception as e:
            self.account.last_synced_at = datetime.now()
            self.account.sync_status = "failed"
            self.account.sync_message = f"{type(e).__name__}: {e}"
            self.db.commit()
            raise

    def _save_resources(self, resources: List[Dict[str, Any]]) -> None:
        def _json_safe(value: Any) -> Any:
            # Convert provider SDK objects (e.g., NCP CommonCode) into DB-safe JSON/scalars.
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            if isinstance(value, list):
                return [_json_safe(v) for v in value]
            if isinstance(value, tuple):
                return [_json_safe(v) for v in value]
            if isinstance(value, dict):
                return {str(k): _json_safe(v) for k, v in value.items()}

            # SDK objects often expose code/code_name attributes.
            code = getattr(value, "code", None)
            code_name = getattr(value, "code_name", None)
            if code is not None or code_name is not None:
                if code is not None and code_name is not None:
                    return f"{code}:{code_name}"
                return str(code if code is not None else code_name)

            to_dict = getattr(value, "to_dict", None)
            if callable(to_dict):
                try:
                    return _json_safe(to_dict())
                except Exception:
                    pass
            return str(value)

        self.db.query(CloudResource).filter(CloudResource.account_id == self.account.id).delete()
        for res in resources:
            self.db.add(
                CloudResource(
                    account_id=self.account.id,
                    resource_id=str(res.get("resource_id") or ""),
                    resource_type=str(res.get("resource_type") or ""),
                    name=res.get("name"),
                    region=res.get("region"),
                    cidr_block=res.get("cidr_block"),
                    state=_json_safe(res.get("state")),
                    resource_metadata=_json_safe(res.get("resource_metadata") or {}),
                )
            )
        self.db.commit()


def _aws_tag(tags: List[Dict[str, Any]], key: str) -> Optional[str]:
    for t in tags or []:
        if t.get("Key") == key:
            return t.get("Value")
    return None
