from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional


class IntentTemplateService:
    _TEMPLATES: List[Dict[str, Any]] = [
        {
            "key": "network-segmentation-baseline",
            "intent_type": "cloud_policy",
            "category": "guardrail",
            "name": "Network Segmentation Baseline",
            "summary": "Start with a conservative private-segmentation baseline before widening edge access.",
            "risk_level": "moderate",
            "supported_providers": ["aws", "azure", "gcp", "ncp"],
            "recommended_scope": "Start with one account and one region, then expand after post-check passes.",
            "risk_notes": [
                "approval_required",
                "verify_post_check",
                "narrow_scope_first",
            ],
            "parameter_schema": [
                {"field_key": "account_ids", "input_kind": "account_selector", "required": False},
                {"field_key": "regions", "input_kind": "list", "required": True},
                {"field_key": "resource_types", "input_kind": "list", "required": True},
                {"field_key": "required_tags", "input_kind": "kv_list", "required": False},
                {"field_key": "blocked_ingress_cidrs", "input_kind": "cidr_list", "required": False},
                {"field_key": "protected_route_destinations", "input_kind": "cidr_list", "required": False},
                {"field_key": "enforce_private_only_next_hop", "input_kind": "boolean", "required": False},
            ],
            "starter_payload": {
                "name": "network-segmentation-baseline",
                "providers": ["aws", "azure", "gcp", "ncp"],
                "regions": ["ap-northeast-2"],
                "resource_types": ["vpc", "subnet", "route_table", "security_group"],
                "required_tags": [{"key": "owner"}, {"key": "env", "value": "prod"}],
                "blocked_ingress_cidrs": ["0.0.0.0/0"],
                "protected_route_destinations": ["0.0.0.0/0"],
                "allowed_default_route_targets": [],
                "enforce_private_only_next_hop": True,
            },
        },
        {
            "key": "public-ingress-lockdown",
            "intent_type": "cloud_policy",
            "category": "security",
            "name": "Public Ingress Lockdown",
            "summary": "Reduce public ingress exposure while preserving known service tags and scoped edge paths.",
            "risk_level": "high",
            "supported_providers": ["aws", "azure", "gcp", "ncp"],
            "recommended_scope": "Use this after discovery confirms the exact security resources and service owners.",
            "risk_notes": [
                "public_edge_review",
                "approval_required",
                "service_owner_signoff",
            ],
            "parameter_schema": [
                {"field_key": "account_ids", "input_kind": "account_selector", "required": False},
                {"field_key": "regions", "input_kind": "list", "required": True},
                {"field_key": "resource_types", "input_kind": "list", "required": True},
                {"field_key": "blocked_ingress_cidrs", "input_kind": "cidr_list", "required": True},
                {"field_key": "required_tags", "input_kind": "kv_list", "required": False},
            ],
            "starter_payload": {
                "name": "public-ingress-lockdown",
                "providers": ["aws", "azure", "gcp", "ncp"],
                "regions": ["ap-northeast-2"],
                "resource_types": ["security_group", "network_acl", "firewall_rule"],
                "required_tags": [{"key": "owner"}, {"key": "service"}],
                "blocked_ingress_cidrs": ["0.0.0.0/0"],
                "protected_route_destinations": [],
                "allowed_default_route_targets": [],
                "enforce_private_only_next_hop": False,
            },
        },
        {
            "key": "default-route-control",
            "intent_type": "cloud_policy",
            "category": "routing",
            "name": "Default Route Control",
            "summary": "Control default-route destinations and verify private next-hop posture before apply.",
            "risk_level": "high",
            "supported_providers": ["aws", "azure", "gcp", "ncp"],
            "recommended_scope": "Run on a single region first and review rollback strategy before widening rollout.",
            "risk_notes": [
                "default_route_guardrail",
                "rollback_ready",
                "approval_required",
            ],
            "parameter_schema": [
                {"field_key": "account_ids", "input_kind": "account_selector", "required": False},
                {"field_key": "regions", "input_kind": "list", "required": True},
                {"field_key": "protected_route_destinations", "input_kind": "cidr_list", "required": True},
                {"field_key": "allowed_default_route_targets", "input_kind": "list", "required": False},
                {"field_key": "enforce_private_only_next_hop", "input_kind": "boolean", "required": False},
            ],
            "starter_payload": {
                "name": "default-route-control",
                "providers": ["aws", "azure", "gcp", "ncp"],
                "regions": ["ap-northeast-2"],
                "resource_types": ["route_table"],
                "required_tags": [{"key": "owner"}, {"key": "network-zone", "value": "private"}],
                "blocked_ingress_cidrs": [],
                "protected_route_destinations": ["0.0.0.0/0"],
                "allowed_default_route_targets": ["nat-gateway", "transit-gateway"],
                "enforce_private_only_next_hop": True,
            },
        },
        {
            "key": "required-tags-compliance",
            "intent_type": "cloud_policy",
            "category": "compliance",
            "name": "Required Tags Compliance",
            "summary": "Apply a light guardrail baseline that verifies ownership and environment tags across scoped assets.",
            "risk_level": "low",
            "supported_providers": ["aws", "azure", "gcp", "ncp"],
            "recommended_scope": "Use this as an early template while the team is still proving service ownership and tenancy boundaries.",
            "risk_notes": [
                "good_first_template",
                "wide_scope_ready",
            ],
            "parameter_schema": [
                {"field_key": "account_ids", "input_kind": "account_selector", "required": False},
                {"field_key": "regions", "input_kind": "list", "required": True},
                {"field_key": "resource_types", "input_kind": "list", "required": True},
                {"field_key": "required_tags", "input_kind": "kv_list", "required": True},
            ],
            "starter_payload": {
                "name": "required-tags-compliance",
                "providers": ["aws", "azure", "gcp", "ncp"],
                "regions": ["ap-northeast-2"],
                "resource_types": ["vpc", "subnet", "instance", "load_balancer"],
                "required_tags": [{"key": "owner"}, {"key": "env"}, {"key": "service"}],
                "blocked_ingress_cidrs": [],
                "protected_route_destinations": [],
                "allowed_default_route_targets": [],
                "enforce_private_only_next_hop": False,
            },
        },
    ]

    @classmethod
    def list_templates(cls) -> List[Dict[str, Any]]:
        return [deepcopy(row) for row in cls._TEMPLATES]

    @classmethod
    def get_template(cls, template_key: str) -> Optional[Dict[str, Any]]:
        normalized = str(template_key or "").strip().lower()
        for row in cls._TEMPLATES:
            if str(row.get("key") or "").strip().lower() == normalized:
                return deepcopy(row)
        return None

    @classmethod
    def get_catalog(cls) -> Dict[str, Any]:
        rows = cls.list_templates()
        providers = sorted(
            {
                provider
                for row in rows
                for provider in list(row.get("supported_providers") or [])
                if str(provider or "").strip()
            }
        )
        categories = sorted(
            {
                str(row.get("category") or "").strip()
                for row in rows
                if str(row.get("category") or "").strip()
            }
        )
        return {
            "templates": rows,
            "coverage": {
                "template_count": len(rows),
                "provider_count": len(providers),
                "providers": providers,
                "categories": categories,
            },
        }
