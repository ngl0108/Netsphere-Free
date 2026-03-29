from __future__ import annotations

from typing import Dict, List

from app.schemas.cloud import CloudProviderPresetResponse


_AWS_READ_ONLY_POLICY = """{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeRouteTables",
        "ec2:DescribeCustomerGateways",
        "ec2:DescribeVpnGateways",
        "ec2:DescribeVpnConnections",
        "ec2:DescribeTransitGateways",
        "ec2:DescribeTransitGatewayAttachments"
      ],
      "Resource": "*"
    }
  ]
}"""

_AWS_ASSUME_ROLE_TRUST_POLICY = """{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowNetSphereAssumeRoleWithExternalId",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::<NETSPHERE_CALLER_ACCOUNT_ID>:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "<YOUR_EXTERNAL_ID>"
        }
      }
    }
  ]
}"""


def _build_presets() -> Dict[str, CloudProviderPresetResponse]:
    presets: Dict[str, CloudProviderPresetResponse] = {}

    presets["aws"] = CloudProviderPresetResponse(
        provider="aws",
        display_name="AWS",
        read_only_policy=_AWS_READ_ONLY_POLICY,
        trust_policy=_AWS_ASSUME_ROLE_TRUST_POLICY,
        credential_fields=[
            {"key": "auth_type", "label": "Auth Type", "required": True, "description": "access_key | assume_role"},
            {"key": "region", "label": "Region", "required": True},
            {"key": "access_key", "label": "Access Key", "required": False, "secret": True},
            {"key": "secret_key", "label": "Secret Key", "required": False, "secret": True},
            {"key": "session_token", "label": "Session Token", "required": False, "secret": True},
            {"key": "role_arn", "label": "Role ARN", "required": False},
            {"key": "external_id", "label": "External ID", "required": False, "secret": True},
            {"key": "source_access_key", "label": "Source Access Key", "required": False, "secret": True},
            {"key": "source_secret_key", "label": "Source Secret Key", "required": False, "secret": True},
            {"key": "source_session_token", "label": "Source Session Token", "required": False, "secret": True},
        ],
        preflight_checks=["sts:get_caller_identity", "ec2:describe_vpcs"],
    )

    presets["azure"] = CloudProviderPresetResponse(
        provider="azure",
        display_name="Azure",
        read_only_policy=(
            "Assign Reader (or equivalent read-only custom role) to the subscription/resource group. "
            "Required network read actions include Microsoft.Network/*/read."
        ),
        credential_fields=[
            {"key": "tenant_id", "label": "Tenant ID", "required": True},
            {"key": "subscription_id", "label": "Subscription ID", "required": True},
            {"key": "client_id", "label": "Client ID", "required": True},
            {"key": "client_secret", "label": "Client Secret", "required": True, "secret": True},
        ],
        preflight_checks=["aad:token", "network:virtual_networks:list_all"],
    )

    presets["gcp"] = CloudProviderPresetResponse(
        provider="gcp",
        display_name="GCP",
        read_only_policy=(
            "Use a read-only service account role set including "
            "compute.networks.list and compute.vpnGateways.list."
        ),
        credential_fields=[
            {"key": "project_id", "label": "Project ID", "required": True},
            {"key": "service_account_json", "label": "Service Account JSON", "required": True, "secret": True},
            {"key": "regions", "label": "Regions", "required": False, "description": "comma-separated"},
        ],
        preflight_checks=["gcp:service_account_auth", "compute:networks:list"],
    )

    naver_base = CloudProviderPresetResponse(
        provider="naver",
        display_name="Naver Cloud",
        read_only_policy="Grant VPC read/list permissions for API key credentials.",
        credential_fields=[
            {"key": "access_key", "label": "Access Key", "required": True, "secret": True},
            {"key": "secret_key", "label": "Secret Key", "required": True, "secret": True},
            {"key": "region_code", "label": "Region Code", "required": False},
        ],
        preflight_checks=["ncloud:vpc:list"],
    )
    presets["naver"] = naver_base
    presets["naver_cloud"] = naver_base.model_copy(update={"provider": "naver_cloud"})
    presets["ncp"] = naver_base.model_copy(update={"provider": "ncp"})
    return presets


class CloudPresetService:
    _PRESETS = _build_presets()

    @staticmethod
    def normalize_provider(provider: str | None) -> str:
        p = str(provider or "").strip().lower()
        if p in {"ncp", "naver_cloud"}:
            return "naver"
        return p

    @classmethod
    def list_presets(cls) -> List[CloudProviderPresetResponse]:
        ordered = ["aws", "azure", "gcp", "naver"]
        return [cls._PRESETS[p] for p in ordered]

    @classmethod
    def get_preset(cls, provider: str | None) -> CloudProviderPresetResponse | None:
        p = str(provider or "").strip().lower()
        if p in cls._PRESETS:
            return cls._PRESETS[p]
        n = cls.normalize_provider(p)
        return cls._PRESETS.get(n)
