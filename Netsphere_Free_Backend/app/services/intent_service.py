from __future__ import annotations

import ipaddress
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models.cloud import CloudAccount, CloudResource
from app.models.settings import SystemSetting
from app.services.change_execution_service import ChangeExecutionService


class IntentService:
    SETTING_ENABLED = "intent_engine_enabled"
    SETTING_APPLY_REQUIRES_APPROVAL = "intent_apply_requires_approval"
    SETTING_MAX_AUTO_APPLY_RISK_SCORE = "intent_max_auto_apply_risk_score"
    SETTING_APPLY_EXECUTE_ACTIONS = "intent_apply_execute_actions"
    SETTING_NORTHBOUND_POLICY_ENABLED = "intent_northbound_policy_enabled"
    SETTING_NORTHBOUND_MAX_AUTO_PUBLISH_RISK_SCORE = "intent_northbound_max_auto_publish_risk_score"

    ALLOWED_TYPES = {"segment", "access_policy", "qos", "cloud_policy"}
    ALLOWED_PROTOCOLS = {"any", "ip", "icmp", "tcp", "udp"}
    ALLOWED_CLOUD_PROVIDERS = {"aws", "azure", "gcp", "ncp"}

    @staticmethod
    def _get_setting(db: Session, key: str, default: str) -> str:
        row = db.query(SystemSetting).filter(SystemSetting.key == str(key)).first()
        if not row or row.value is None:
            return str(default)
        return str(row.value)

    @staticmethod
    def _get_bool(db: Session, key: str, default: bool) -> bool:
        raw = IntentService._get_setting(db, key, "true" if default else "false").strip().lower()
        return raw in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def _get_int(db: Session, key: str, default: int) -> int:
        try:
            return int(float(IntentService._get_setting(db, key, str(default)).strip()))
        except Exception:
            return int(default)

    @staticmethod
    def is_enabled(db: Session) -> bool:
        return IntentService._get_bool(db, IntentService.SETTING_ENABLED, False)

    @staticmethod
    def apply_requires_approval(db: Session) -> bool:
        return IntentService._get_bool(db, IntentService.SETTING_APPLY_REQUIRES_APPROVAL, True)

    @staticmethod
    def max_auto_apply_risk_score(db: Session) -> int:
        v = IntentService._get_int(db, IntentService.SETTING_MAX_AUTO_APPLY_RISK_SCORE, 30)
        return max(0, min(100, int(v)))

    @staticmethod
    def apply_execute_actions_enabled(db: Session) -> bool:
        return IntentService._get_bool(db, IntentService.SETTING_APPLY_EXECUTE_ACTIONS, False)

    @staticmethod
    def northbound_policy_enabled(db: Session) -> bool:
        return IntentService._get_bool(db, IntentService.SETTING_NORTHBOUND_POLICY_ENABLED, False)

    @staticmethod
    def northbound_max_auto_publish_risk_score(db: Session) -> int:
        v = IntentService._get_int(
            db,
            IntentService.SETTING_NORTHBOUND_MAX_AUTO_PUBLISH_RISK_SCORE,
            IntentService.max_auto_apply_risk_score(db),
        )
        return max(0, min(100, int(v)))

    @staticmethod
    def supported_intents() -> List[str]:
        return ["segment", "access_policy", "qos", "cloud_policy"]

    @staticmethod
    def _norm_str_list(value: Any, *, lower: bool = False) -> List[str]:
        if value is None:
            return []
        items: List[str] = []
        if isinstance(value, list):
            raw = value
        else:
            raw = [value]
        for item in raw:
            text = str(item or "").strip()
            if not text:
                continue
            items.append(text.lower() if lower else text)
        seen = set()
        out: List[str] = []
        for item in items:
            key = item.lower() if not lower else item
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out

    @staticmethod
    def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        raw = dict(payload or {})
        intent_type = str(raw.get("intent_type") or "").strip().lower()
        name = str(raw.get("name") or "").strip()
        spec = raw.get("spec") if isinstance(raw.get("spec"), dict) else {}
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        return {
            "intent_type": intent_type,
            "name": name,
            "spec": spec,
            "metadata": metadata,
            "dry_run": bool(raw.get("dry_run", True)),
            "idempotency_key": str(raw.get("idempotency_key") or "").strip() or None,
            "approval_id": (int(raw.get("approval_id")) if raw.get("approval_id") is not None else None),
            "execution_id": str(raw.get("execution_id") or "").strip() or None,
        }

    @staticmethod
    def _validate_segment_spec(spec: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str], List[Dict[str, Any]]]:
        errors: List[str] = []
        warnings: List[str] = []
        conflicts: List[Dict[str, Any]] = []
        normalized: Dict[str, Any] = {"segments": []}

        segments_raw = spec.get("segments")
        if not isinstance(segments_raw, list) or not segments_raw:
            errors.append("segment intent requires non-empty spec.segments list")
            return normalized, errors, warnings, conflicts

        seen_names = set()
        parsed_cidrs: List[Tuple[str, str, ipaddress._BaseNetwork]] = []

        for idx, row in enumerate(segments_raw, start=1):
            if not isinstance(row, dict):
                errors.append(f"segments[{idx}] must be object")
                continue
            seg_name = str(row.get("name") or "").strip()
            if not seg_name:
                errors.append(f"segments[{idx}].name is required")
                continue
            seg_name_key = seg_name.lower()
            if seg_name_key in seen_names:
                errors.append(f"duplicate segment name: {seg_name}")
                continue
            seen_names.add(seg_name_key)

            cidrs_raw = row.get("cidrs")
            if isinstance(cidrs_raw, str):
                cidrs_raw = [cidrs_raw]
            if not isinstance(cidrs_raw, list) or not cidrs_raw:
                errors.append(f"segments[{idx}].cidrs must be non-empty list")
                continue

            cidr_list: List[str] = []
            for c_idx, cidr in enumerate(cidrs_raw, start=1):
                cidr_text = str(cidr or "").strip()
                if not cidr_text:
                    continue
                try:
                    network = ipaddress.ip_network(cidr_text, strict=False)
                except Exception:
                    errors.append(f"segments[{idx}].cidrs[{c_idx}] invalid CIDR: {cidr_text}")
                    continue
                network_text = str(network)
                cidr_list.append(network_text)
                parsed_cidrs.append((seg_name, network_text, network))

            if not cidr_list:
                errors.append(f"segments[{idx}] has no valid CIDR")
                continue

            normalized["segments"].append(
                {
                    "name": seg_name,
                    "cidrs": cidr_list,
                    "description": str(row.get("description") or "").strip() or None,
                }
            )

        for i in range(len(parsed_cidrs)):
            left_name, left_cidr, left_net = parsed_cidrs[i]
            for j in range(i + 1, len(parsed_cidrs)):
                right_name, right_cidr, right_net = parsed_cidrs[j]
                if left_net.version != right_net.version:
                    continue
                if not left_net.overlaps(right_net):
                    continue
                if left_name == right_name and left_cidr == right_cidr:
                    continue
                conflicts.append(
                    {
                        "type": "cidr_overlap",
                        "left_segment": left_name,
                        "left_cidr": left_cidr,
                        "right_segment": right_name,
                        "right_cidr": right_cidr,
                    }
                )

        if len(normalized["segments"]) > 30:
            warnings.append("large segment set (>30) may increase rollout risk")

        return normalized, errors, warnings, conflicts

    @staticmethod
    def _normalize_ports(value: Any) -> Tuple[List[str], List[str]]:
        errors: List[str] = []
        out: List[str] = []
        if value is None:
            return out, errors
        raw = value if isinstance(value, list) else [value]
        for item in raw:
            text = str(item or "").strip()
            if not text:
                continue
            if "-" in text:
                parts = text.split("-", 1)
                try:
                    start = int(parts[0])
                    end = int(parts[1])
                    if start < 1 or end > 65535 or start > end:
                        raise ValueError
                except Exception:
                    errors.append(f"invalid port range: {text}")
                    continue
                out.append(f"{start}-{end}")
                continue
            try:
                p = int(text)
                if p < 1 or p > 65535:
                    raise ValueError
                out.append(str(p))
            except Exception:
                errors.append(f"invalid port: {text}")
        dedup = sorted(set(out), key=lambda x: (len(x), x))
        return dedup, errors

    @staticmethod
    def _validate_access_policy_spec(spec: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str], List[Dict[str, Any]]]:
        errors: List[str] = []
        warnings: List[str] = []
        conflicts: List[Dict[str, Any]] = []
        normalized: Dict[str, Any] = {"default_action": "deny", "rules": []}

        default_action = str(spec.get("default_action") or "deny").strip().lower()
        if default_action not in {"permit", "deny"}:
            errors.append("spec.default_action must be permit or deny")
        else:
            normalized["default_action"] = default_action

        rules_raw = spec.get("rules")
        if not isinstance(rules_raw, list) or not rules_raw:
            errors.append("access_policy intent requires non-empty spec.rules list")
            return normalized, errors, warnings, conflicts

        signature_to_action: Dict[str, str] = {}
        for idx, row in enumerate(rules_raw, start=1):
            if not isinstance(row, dict):
                errors.append(f"rules[{idx}] must be object")
                continue

            action = str(row.get("action") or "permit").strip().lower()
            if action not in {"permit", "deny"}:
                errors.append(f"rules[{idx}].action must be permit or deny")
                continue

            sources = IntentService._norm_str_list(row.get("sources", row.get("source", ["any"])), lower=True) or ["any"]
            destinations = IntentService._norm_str_list(row.get("destinations", row.get("destination", ["any"])), lower=True) or ["any"]
            protocols = IntentService._norm_str_list(row.get("protocols", row.get("protocol", ["any"])), lower=True) or ["any"]
            protocols = ["any" if p == "all" else p for p in protocols]
            bad_protocols = [p for p in protocols if p not in IntentService.ALLOWED_PROTOCOLS]
            if bad_protocols:
                errors.append(f"rules[{idx}] has invalid protocols: {','.join(sorted(set(bad_protocols)))}")
                continue

            ports, port_errors = IntentService._normalize_ports(row.get("ports"))
            if port_errors:
                for e in port_errors:
                    errors.append(f"rules[{idx}] {e}")
                continue

            signature = json.dumps(
                {
                    "sources": sources,
                    "destinations": destinations,
                    "protocols": sorted(set(protocols)),
                    "ports": ports,
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            prev_action = signature_to_action.get(signature)
            if prev_action and prev_action != action:
                conflicts.append(
                    {
                        "type": "rule_conflict",
                        "rule_index": idx,
                        "reason": "same match condition has different action",
                        "existing_action": prev_action,
                        "new_action": action,
                    }
                )
            else:
                signature_to_action[signature] = action

            if action == "permit" and sources == ["any"] and destinations == ["any"] and set(protocols).intersection({"any", "ip"}):
                warnings.append(f"rules[{idx}] is broad permit(any->any)")

            normalized["rules"].append(
                {
                    "name": str(row.get("name") or f"rule-{idx}").strip(),
                    "action": action,
                    "sources": sources,
                    "destinations": destinations,
                    "protocols": sorted(set(protocols)),
                    "ports": ports,
                    "description": str(row.get("description") or "").strip() or None,
                }
            )

        return normalized, errors, warnings, conflicts

    @staticmethod
    def _validate_qos_spec(spec: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str], List[Dict[str, Any]]]:
        errors: List[str] = []
        warnings: List[str] = []
        conflicts: List[Dict[str, Any]] = []
        normalized: Dict[str, Any] = {"scheduler": "priority", "classes": []}

        scheduler = str(spec.get("scheduler") or "priority").strip().lower()
        if scheduler not in {"priority", "wfq"}:
            errors.append("spec.scheduler must be priority or wfq")
        else:
            normalized["scheduler"] = scheduler

        classes_raw = spec.get("classes")
        if not isinstance(classes_raw, list) or not classes_raw:
            errors.append("qos intent requires non-empty spec.classes list")
            return normalized, errors, warnings, conflicts

        seen_priorities: Dict[int, str] = {}
        total_guarantee = 0.0
        for idx, row in enumerate(classes_raw, start=1):
            if not isinstance(row, dict):
                errors.append(f"classes[{idx}] must be object")
                continue
            class_name = str(row.get("name") or "").strip()
            if not class_name:
                errors.append(f"classes[{idx}].name is required")
                continue
            try:
                priority = int(row.get("priority"))
            except Exception:
                errors.append(f"classes[{idx}].priority is required")
                continue
            if priority < 0 or priority > 7:
                errors.append(f"classes[{idx}].priority must be 0..7")
                continue

            guarantee = 0.0
            if row.get("min_guarantee_pct") is not None:
                try:
                    guarantee = float(row.get("min_guarantee_pct"))
                except Exception:
                    errors.append(f"classes[{idx}].min_guarantee_pct must be numeric")
                    continue
                if guarantee < 0 or guarantee > 100:
                    errors.append(f"classes[{idx}].min_guarantee_pct must be 0..100")
                    continue
            total_guarantee += guarantee

            if priority in seen_priorities:
                conflicts.append(
                    {
                        "type": "priority_conflict",
                        "priority": int(priority),
                        "left_class": seen_priorities[priority],
                        "right_class": class_name,
                    }
                )
            else:
                seen_priorities[priority] = class_name

            max_limit = None
            if row.get("max_limit_mbps") is not None:
                try:
                    max_limit = float(row.get("max_limit_mbps"))
                except Exception:
                    errors.append(f"classes[{idx}].max_limit_mbps must be numeric")
                    continue
                if max_limit <= 0:
                    errors.append(f"classes[{idx}].max_limit_mbps must be > 0")
                    continue

            normalized["classes"].append(
                {
                    "name": class_name,
                    "priority": int(priority),
                    "min_guarantee_pct": float(guarantee),
                    "max_limit_mbps": max_limit,
                    "dscp": str(row.get("dscp") or "").strip() or None,
                }
            )

        if total_guarantee > 100.0:
            conflicts.append(
                {
                    "type": "guarantee_overflow",
                    "total_min_guarantee_pct": round(total_guarantee, 2),
                    "max_allowed_pct": 100.0,
                }
            )

        return normalized, errors, warnings, conflicts

    @staticmethod
    def _normalize_cloud_provider(value: Any) -> str:
        provider = str(value or "").strip().lower()
        if provider in {"naver", "naver_cloud", "ncp"}:
            return "ncp"
        return provider

    @staticmethod
    def _slugify_name(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return "intent"
        out = []
        last_dash = False
        for ch in text:
            if ch.isalnum():
                out.append(ch)
                last_dash = False
                continue
            if not last_dash:
                out.append("-")
                last_dash = True
        slug = "".join(out).strip("-")
        return slug or "intent"

    @staticmethod
    def _extract_cloud_tags(metadata: Any) -> Dict[str, str]:
        if not isinstance(metadata, dict):
            return {}
        out: Dict[str, str] = {}
        for raw in [
            metadata.get("tags"),
            metadata.get("labels"),
            metadata.get("tag_set"),
            metadata.get("tagSet"),
        ]:
            if isinstance(raw, dict):
                for k, v in raw.items():
                    key = str(k or "").strip()
                    if not key:
                        continue
                    out[key] = str(v or "").strip()
            elif isinstance(raw, list):
                for row in raw:
                    if not isinstance(row, dict):
                        continue
                    key = str(row.get("key") or row.get("Key") or row.get("tagKey") or "").strip()
                    if not key:
                        continue
                    val = str(row.get("value") or row.get("Value") or row.get("tagValue") or "").strip()
                    out[key] = val
        return out

    @staticmethod
    def _validate_cloud_policy_spec(spec: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str], List[Dict[str, Any]]]:
        errors: List[str] = []
        warnings: List[str] = []
        conflicts: List[Dict[str, Any]] = []
        normalized: Dict[str, Any] = {
            "targets": {
                "providers": [],
                "account_ids": [],
                "regions": [],
                "resource_types": [],
            },
            "required_tags": [],
            "blocked_ingress_cidrs": [],
            "protected_route_destinations": [],
            "allowed_default_route_targets": [],
            "enforce_private_only_next_hop": False,
        }

        targets = spec.get("targets") if isinstance(spec.get("targets"), dict) else {}

        raw_providers = targets.get("providers")
        provider_items = raw_providers if isinstance(raw_providers, list) else ([raw_providers] if raw_providers is not None else [])
        providers: List[str] = []
        for p in provider_items:
            norm = IntentService._normalize_cloud_provider(p)
            if not norm:
                continue
            if norm not in IntentService.ALLOWED_CLOUD_PROVIDERS:
                errors.append(
                    f"targets.providers contains unsupported provider: {norm} "
                    f"(allowed: {', '.join(sorted(IntentService.ALLOWED_CLOUD_PROVIDERS))})"
                )
                continue
            if norm not in providers:
                providers.append(norm)
        normalized["targets"]["providers"] = providers

        raw_account_ids = targets.get("account_ids")
        account_items = (
            raw_account_ids
            if isinstance(raw_account_ids, list)
            else ([raw_account_ids] if raw_account_ids is not None else [])
        )
        account_ids: List[int] = []
        for idx, v in enumerate(account_items, start=1):
            try:
                aid = int(v)
            except Exception:
                errors.append(f"targets.account_ids[{idx}] must be integer")
                continue
            if aid <= 0:
                errors.append(f"targets.account_ids[{idx}] must be > 0")
                continue
            if aid not in account_ids:
                account_ids.append(aid)
        normalized["targets"]["account_ids"] = account_ids

        raw_regions = targets.get("regions")
        region_items = raw_regions if isinstance(raw_regions, list) else ([raw_regions] if raw_regions is not None else [])
        regions: List[str] = []
        for idx, v in enumerate(region_items, start=1):
            region = str(v or "").strip()
            if not region:
                continue
            if len(region) > 64:
                errors.append(f"targets.regions[{idx}] must be <= 64 chars")
                continue
            if region not in regions:
                regions.append(region)
        normalized["targets"]["regions"] = regions

        raw_types = targets.get("resource_types")
        type_items = raw_types if isinstance(raw_types, list) else ([raw_types] if raw_types is not None else [])
        resource_types: List[str] = []
        for idx, v in enumerate(type_items, start=1):
            t = str(v or "").strip().lower()
            if not t:
                continue
            if len(t) > 64:
                errors.append(f"targets.resource_types[{idx}] must be <= 64 chars")
                continue
            if t not in resource_types:
                resource_types.append(t)
        normalized["targets"]["resource_types"] = resource_types

        raw_required_tags = spec.get("required_tags")
        if raw_required_tags is None:
            raw_required_tags = []
        if not isinstance(raw_required_tags, list):
            errors.append("required_tags must be a list")
            raw_required_tags = []

        tag_value_by_key: Dict[str, str | None] = {}
        required_tags: List[Dict[str, Any]] = []
        for idx, row in enumerate(raw_required_tags, start=1):
            if not isinstance(row, dict):
                errors.append(f"required_tags[{idx}] must be object")
                continue
            key = str(row.get("key") or "").strip()
            if not key:
                errors.append(f"required_tags[{idx}].key is required")
                continue
            if len(key) > 128:
                errors.append(f"required_tags[{idx}].key must be <= 128 chars")
                continue
            raw_value = row.get("value")
            value = str(raw_value).strip() if raw_value is not None else None
            if value == "":
                value = None
            key_norm = key.lower()
            if key_norm in tag_value_by_key and tag_value_by_key[key_norm] != value:
                conflicts.append(
                    {
                        "type": "required_tag_conflict",
                        "tag_key": key,
                        "left_value": tag_value_by_key[key_norm],
                        "right_value": value,
                    }
                )
            else:
                tag_value_by_key[key_norm] = value
            required_tags.append({"key": key, "value": value})
        normalized["required_tags"] = required_tags

        def _parse_cidr_list(value: Any, field_name: str) -> List[str]:
            raw = value if isinstance(value, list) else ([value] if value is not None else [])
            out: List[str] = []
            for idx, item in enumerate(raw, start=1):
                text = str(item or "").strip()
                if not text:
                    continue
                try:
                    network = ipaddress.ip_network(text, strict=False)
                except Exception:
                    errors.append(f"{field_name}[{idx}] invalid CIDR: {text}")
                    continue
                cidr = str(network)
                if cidr not in out:
                    out.append(cidr)
            return out

        normalized["blocked_ingress_cidrs"] = _parse_cidr_list(
            spec.get("blocked_ingress_cidrs"),
            "blocked_ingress_cidrs",
        )
        normalized["protected_route_destinations"] = _parse_cidr_list(
            spec.get("protected_route_destinations"),
            "protected_route_destinations",
        )

        raw_allowed_targets = spec.get("allowed_default_route_targets")
        target_items = (
            raw_allowed_targets
            if isinstance(raw_allowed_targets, list)
            else ([raw_allowed_targets] if raw_allowed_targets is not None else [])
        )
        allowed_default_route_targets: List[str] = []
        for idx, item in enumerate(target_items, start=1):
            text = str(item or "").strip().lower()
            if not text:
                continue
            if len(text) > 64:
                errors.append(f"allowed_default_route_targets[{idx}] must be <= 64 chars")
                continue
            if text not in allowed_default_route_targets:
                allowed_default_route_targets.append(text)
        normalized["allowed_default_route_targets"] = allowed_default_route_targets

        normalized["enforce_private_only_next_hop"] = bool(spec.get("enforce_private_only_next_hop", False))

        has_scope = any(
            [
                bool(normalized["targets"]["providers"]),
                bool(normalized["targets"]["account_ids"]),
                bool(normalized["targets"]["regions"]),
                bool(normalized["targets"]["resource_types"]),
            ]
        )
        has_guardrails = any(
            [
                bool(normalized["required_tags"]),
                bool(normalized["blocked_ingress_cidrs"]),
                bool(normalized["protected_route_destinations"]),
                bool(normalized["allowed_default_route_targets"]),
                bool(normalized["enforce_private_only_next_hop"]),
            ]
        )

        if not has_scope:
            warnings.append("cloud_policy applies to all discovered cloud resources (no targets filters)")
        if not has_guardrails:
            warnings.append("cloud_policy has no guardrails configured")
        if normalized["protected_route_destinations"] and not normalized["allowed_default_route_targets"] and not normalized["enforce_private_only_next_hop"]:
            warnings.append(
                "protected_route_destinations configured without allowed_default_route_targets; default routes may be over-restricted"
            )

        return normalized, errors, warnings, conflicts

    @staticmethod
    def _is_default_route(value: str) -> bool:
        text = str(value or "").strip()
        return text in {"0.0.0.0/0", "::/0"}

    @staticmethod
    def _is_broad_cidr(value: str) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        try:
            network = ipaddress.ip_network(text, strict=False)
        except Exception:
            return False
        if network.version == 4:
            return int(network.prefixlen) <= 16
        return int(network.prefixlen) <= 48

    @staticmethod
    def _build_cloud_operational_guardrails(
        db: Session,
        normalized_intent: Dict[str, Any],
        cloud_scope: Dict[str, Any],
        *,
        risk_score: int,
    ) -> Dict[str, Any]:
        from app.services.cloud_account_readiness_service import CloudAccountReadinessService
        from app.services.cloud_credentials_service import decrypt_credentials_for_runtime
        from app.services.cloud_intent_execution_service import CloudIntentExecutionService

        spec = normalized_intent.get("spec") if isinstance(normalized_intent.get("spec"), dict) else {}
        targets = spec.get("targets") if isinstance(spec.get("targets"), dict) else {}
        blocked_ingress_cidrs = list(spec.get("blocked_ingress_cidrs") or [])
        protected_route_destinations = list(spec.get("protected_route_destinations") or [])
        allowed_default_route_targets = list(spec.get("allowed_default_route_targets") or [])
        target_accounts = [int(v) for v in list(cloud_scope.get("target_accounts") or []) if int(v) > 0]
        target_providers = [str(v) for v in list(cloud_scope.get("target_providers") or []) if str(v or "").strip()]
        target_regions = [str(v) for v in list(targets.get("regions") or []) if str(v or "").strip()]
        resources_by_type = cloud_scope.get("resources_by_type") if isinstance(cloud_scope.get("resources_by_type"), dict) else {}
        scoped_resources = int(cloud_scope.get("scoped_resources") or 0)

        global_execution = CloudIntentExecutionService.execution_readiness()
        global_mode = str(global_execution.get("mode") or "prepare_only")
        global_ready = bool(global_execution.get("ready_for_real_apply"))
        state_backend = str(global_execution.get("state_backend") or "local")

        account_rows = (
            db.query(CloudAccount)
            .filter(CloudAccount.id.in_(target_accounts))
            .order_by(CloudAccount.id.asc())
            .all()
            if target_accounts
            else []
        )

        account_modes: List[Dict[str, Any]] = []
        for account in account_rows:
            runtime_credentials = decrypt_credentials_for_runtime(account.provider, account.credentials or {})
            readiness = CloudAccountReadinessService.build(
                account.provider,
                runtime_credentials,
                global_execution_readiness=global_execution,
            )
            account_modes.append(
                {
                    "account_id": int(account.id),
                    "name": str(account.name or ""),
                    "provider": str(account.provider or ""),
                    "change_mode": str(readiness.get("change_mode") or "read_only"),
                    "stage": str(readiness.get("stage") or "unknown"),
                    "change_enabled": bool(readiness.get("change_enabled")),
                    "change_mode_reason": str(readiness.get("change_mode_reason") or ""),
                    "missing_fields": list(readiness.get("missing_fields") or []),
                }
            )

        findings: List[Dict[str, Any]] = []

        def _add_finding(key: str, severity: str, title: str, message: str, recommendation: str | None = None) -> None:
            findings.append(
                {
                    "key": key,
                    "severity": severity,
                    "title": title,
                    "message": message,
                    "recommendation": recommendation,
                }
            )

        public_ingress_targets = [cidr for cidr in blocked_ingress_cidrs if IntentService._is_default_route(cidr)]
        if public_ingress_targets:
            _add_finding(
                "public_ingress",
                "critical",
                "Public ingress rules are in scope",
                f"This plan will touch {len(public_ingress_targets)} public ingress CIDR guardrails across scoped security policies.",
                "Review blast radius and keep approval mandatory for public ingress changes.",
            )

        broad_cidrs = [
            cidr
            for cidr in list(blocked_ingress_cidrs) + list(protected_route_destinations)
            if IntentService._is_broad_cidr(cidr) and not IntentService._is_default_route(cidr)
        ]
        if broad_cidrs:
            _add_finding(
                "broad_cidr",
                "warning",
                "Broad CIDR ranges detected",
                f"{len(broad_cidrs)} broad CIDR guardrails are included in this scope.",
                "Prefer narrower CIDRs where possible before widening rollout.",
            )

        if (
            any(IntentService._is_default_route(cidr) for cidr in protected_route_destinations)
            or bool(allowed_default_route_targets)
        ):
            _add_finding(
                "default_route",
                "critical",
                "Default route policies are in scope",
                "This intent touches default-route behavior or approved next-hop targets.",
                "Use approval and post-check before any rollout touching default routes.",
            )

        high_impact_types = {
            "nat_gateway",
            "load_balancer",
            "vpn_gateway",
            "transit_gateway",
            "customer_gateway",
            "internet_gateway",
            "public_ip",
            "eip",
            "nat",
            "lb",
            "vpn",
            "tgw",
        }
        high_impact_count = int(
            sum(
                int(value or 0)
                for key, value in resources_by_type.items()
                if str(key or "").strip().lower() in high_impact_types
                or any(token in str(key or "").strip().lower() for token in ("nat", "load_balancer", "vpn", "transit_gateway"))
            )
        )
        if high_impact_count > 0:
            _add_finding(
                "high_impact_edges",
                "critical",
                "High-impact network edges are in scope",
                f"{high_impact_count} NAT/LB/VPN/TGW-like resources are within the current target scope.",
                "Roll out in narrow waves and confirm rollback evidence is ready first.",
            )

        if scoped_resources > 150 or len(target_accounts) > 1 or len(target_regions) > 2:
            _add_finding(
                "broad_scope",
                "warning",
                "Scope is wider than a first-wave rollout",
                f"Current scope spans {scoped_resources} resources across {len(target_accounts)} account(s) and {len(target_regions)} region(s).",
                "Start with one account, one or two regions, and the smallest resource set possible.",
            )

        read_only_accounts = [row for row in account_modes if not bool(row.get("change_enabled"))]
        if read_only_accounts:
            _add_finding(
                "read_only_accounts",
                "warning",
                "Some scoped accounts are still read-only",
                f"{len(read_only_accounts)} scoped account(s) are not change-enabled yet.",
                "Fix credentials or global execution guardrails before planning real apply.",
            )

        if not global_ready:
            _add_finding(
                "execution_guarded",
                "info",
                "Execution is currently guarded",
                f"Global mode is {global_mode} and live apply is not fully ready.",
                "Keep using preview/mock runs until runtime, backend, and live apply policy are ready.",
            )

        if state_backend == "local":
            _add_finding(
                "local_state_backend",
                "warning",
                "Local Terraform state backend is configured",
                "Local state is fine for lab runs, but not for shared operator workflows.",
                "Move to S3, AzureRM, or GCS remote state before production rollout.",
            )

        if IntentService.apply_requires_approval(db):
            _add_finding(
                "approval_required",
                "info",
                "Approval policy is enabled",
                "Cloud changes remain approval-gated by current policy.",
                "Use Approval Center as the primary execution path for any non-preview run.",
            )

        critical_count = sum(1 for finding in findings if str(finding.get("severity")) == "critical")
        warning_count = sum(1 for finding in findings if str(finding.get("severity")) == "warning")

        return {
            "summary": {
                "scoped_accounts": int(len(account_modes)),
                "change_enabled_accounts": int(sum(1 for row in account_modes if bool(row.get("change_enabled")))),
                "read_only_accounts": int(len(read_only_accounts)),
                "critical_findings": int(critical_count),
                "warning_findings": int(warning_count),
                "approval_required": bool(IntentService.apply_requires_approval(db)),
                "global_mode": global_mode,
                "state_backend": state_backend,
                "ready_for_real_apply": bool(global_ready),
                "risk_score": int(risk_score),
            },
            "account_modes": account_modes,
            "findings": findings,
        }

    @staticmethod
    def _build_cloud_policy_terraform_preview(
        normalized_intent: Dict[str, Any],
        cloud_scope: Dict[str, Any],
    ) -> Dict[str, Any]:
        spec = normalized_intent.get("spec") if isinstance(normalized_intent.get("spec"), dict) else {}
        targets = spec.get("targets") if isinstance(spec.get("targets"), dict) else {}
        guardrails = cloud_scope.get("guardrails") if isinstance(cloud_scope.get("guardrails"), dict) else {}

        intent_name = str(normalized_intent.get("name") or "cloud-policy").strip() or "cloud-policy"
        slug = IntentService._slugify_name(intent_name)
        providers = list(targets.get("providers") or cloud_scope.get("target_providers") or [])
        account_ids = list(targets.get("account_ids") or cloud_scope.get("target_accounts") or [])
        regions = list(targets.get("regions") or [])
        resource_types = list(targets.get("resource_types") or [])
        required_tags = list(spec.get("required_tags") or [])
        blocked_ingress_cidrs = list(spec.get("blocked_ingress_cidrs") or [])
        protected_route_destinations = list(spec.get("protected_route_destinations") or [])
        allowed_default_route_targets = list(spec.get("allowed_default_route_targets") or [])
        enforce_private_only_next_hop = bool(spec.get("enforce_private_only_next_hop", False))

        resources_by_type = cloud_scope.get("resources_by_type") if isinstance(cloud_scope.get("resources_by_type"), dict) else {}
        resources_by_provider = (
            cloud_scope.get("resources_by_provider") if isinstance(cloud_scope.get("resources_by_provider"), dict) else {}
        )
        resources_by_provider_type = (
            cloud_scope.get("resources_by_provider_type")
            if isinstance(cloud_scope.get("resources_by_provider_type"), dict)
            else {}
        )
        accounts_by_provider = (
            cloud_scope.get("accounts_by_provider") if isinstance(cloud_scope.get("accounts_by_provider"), dict) else {}
        )
        regions_by_provider = (
            cloud_scope.get("regions_by_provider") if isinstance(cloud_scope.get("regions_by_provider"), dict) else {}
        )
        scoped_resources = int(cloud_scope.get("scoped_resources") or 0)
        missing_required_tags = int(cloud_scope.get("missing_required_tags") or 0)
        sg_targets = int(cloud_scope.get("security_group_like_targets") or 0)
        route_targets = int(cloud_scope.get("route_like_targets") or 0)

        modules: List[Dict[str, Any]] = []
        plan_lines: List[str] = []
        change_blocks: List[Dict[str, Any]] = []

        security_like_types = {"security_group", "nsg", "firewall", "network_acl", "acl"}
        route_like_types = {"route_table", "route", "router"}
        network_like_types = {"vpc", "vnet", "subnet"}

        def _provider_scope(provider: str) -> Dict[str, Any]:
            provider_types = resources_by_provider_type.get(provider)
            provider_type_counts = provider_types if isinstance(provider_types, dict) else {}
            targeted_types = list(resource_types) if resource_types else list(provider_type_counts.keys())
            targeted_types = [str(item).strip().lower() for item in targeted_types if str(item).strip()]
            targeted_counts = {
                str(key): int(provider_type_counts.get(key) or 0)
                for key in targeted_types
                if int(provider_type_counts.get(key) or 0) > 0
            }
            if not targeted_counts and provider_type_counts:
                targeted_counts = {str(key): int(value) for key, value in provider_type_counts.items() if int(value or 0) > 0}
                targeted_types = list(targeted_counts.keys())

            return {
                "resource_count": int(resources_by_provider.get(provider) or 0),
                "targeted_counts": targeted_counts,
                "targeted_types": targeted_types,
                "account_count": len(list(accounts_by_provider.get(provider) or [])),
                "regions": list(regions_by_provider.get(provider) or []),
            }

        def _humanize_type(value: str) -> str:
            raw = str(value or "").strip().lower()
            aliases = {
                "security_group": "security groups",
                "route_table": "route tables",
                "subnet": "subnets",
                "vpc": "VPCs",
                "vnet": "VNets",
                "nsg": "NSGs",
                "firewall": "firewalls",
                "network_acl": "network ACLs",
                "acl": "ACLs",
                "vm": "VMs",
                "instance": "instances",
            }
            return aliases.get(raw, raw.replace("_", " "))

        def _build_provider_block(provider: str) -> Dict[str, Any]:
            scope = _provider_scope(provider)
            targeted_counts = dict(scope.get("targeted_counts") or {})
            targeted_types = list(scope.get("targeted_types") or [])
            targeted_label = ", ".join(_humanize_type(item) for item in targeted_types[:4]) or "scoped resources"

            block_changes: List[str] = []
            verification_checks: List[str] = []
            evidence_artifacts: List[str] = [
                "intent.json",
                "simulation.json",
                "execution-request.json",
                "terraform-render.json",
                "terraform-plan-preview.json",
                "runner-result.json",
            ]
            risk_hints: List[str] = []

            if required_tags:
                block_changes.append(
                    f"Enforce {len(required_tags)} required tag rules across {scope['resource_count']} scoped {provider.upper()} resources."
                )
                verification_checks.append(
                    f"Re-scan {provider.upper()} inventory and confirm required tags are present on targeted {targeted_label}."
                )
                if missing_required_tags > 0:
                    risk_hints.append(
                        f"{missing_required_tags} scoped resources are currently missing one or more required tags."
                    )

            sg_target_count = int(
                sum(value for key, value in targeted_counts.items() if key in security_like_types or "security_group" in key)
            )
            if blocked_ingress_cidrs and sg_target_count > 0:
                block_changes.append(
                    f"Guard ingress on {sg_target_count} security policy targets by blocking {len(blocked_ingress_cidrs)} CIDR patterns."
                )
                verification_checks.append(
                    "Confirm blocked ingress CIDRs are absent from effective security policy rules after apply."
                )
                evidence_artifacts.append("logs/plan.log")

            route_target_count = int(
                sum(value for key, value in targeted_counts.items() if key in route_like_types or "route" in key)
            )
            if protected_route_destinations or allowed_default_route_targets or enforce_private_only_next_hop:
                block_changes.append(
                    f"Review route guardrails on {route_target_count or scope['resource_count']} route-capable targets."
                )
                verification_checks.append(
                    "Verify protected destinations keep approved next hops and default routes remain policy-compliant."
                )
                if protected_route_destinations:
                    risk_hints.append(
                        f"Protected destinations include {len(protected_route_destinations)} route targets that should not drift."
                    )

            if not block_changes:
                block_changes.append(
                    f"Preview-only scope: provider module renders context for {scope['resource_count']} {targeted_label} without mutation guardrails."
                )
                verification_checks.append(
                    f"Refresh {provider.upper()} topology and inventory to confirm the scoped resources stay discoverable."
                )

            verification_checks.append(
                f"Re-run Pipeline/Scan for {provider.upper()} account scope after apply and confirm topology, inventory, and state stay aligned."
            )
            evidence_artifacts.extend(["logs/init.log", "logs/validate.log"])

            return {
                "provider": provider,
                "module": f"{provider}_cloud_policy",
                "title": f"{provider.upper()} Cloud Guardrails",
                "resource_count": int(scope["resource_count"]),
                "account_count": int(scope["account_count"]),
                "regions": list(scope["regions"]),
                "targeted_resource_types": targeted_types,
                "changes": block_changes,
                "verification_checks": verification_checks,
                "evidence_artifacts": sorted(set(evidence_artifacts)),
                "risk_hints": risk_hints,
            }

        for provider in providers or ["hybrid"]:
            workspace = f"netsphere-{provider}-{slug}"
            modules.append(
                {
                    "provider": provider,
                    "workspace": workspace,
                    "module": f"netsphere_cloud_policy_{provider}",
                    "targets": {
                        "account_ids": [int(aid) for aid in account_ids],
                        "regions": list(regions),
                        "resource_types": list(resource_types),
                    },
                }
            )
            plan_lines.append(f'module "{provider}_cloud_policy" {{ source = "./modules/{provider}/cloud_policy" }}')
            change_blocks.append(_build_provider_block(provider))

        if required_tags:
            plan_lines.append(
                f"+ enforce required_tags ({len(required_tags)}) across {scoped_resources} scoped resources"
            )

        if blocked_ingress_cidrs:
            plan_lines.append(
                f"~ patch security group ingress guards ({len(blocked_ingress_cidrs)} cidrs) across {sg_targets} targets"
            )

        if protected_route_destinations or allowed_default_route_targets or enforce_private_only_next_hop:
            route_details = list(protected_route_destinations)
            if allowed_default_route_targets:
                route_details.extend([f"allow:{value}" for value in allowed_default_route_targets])
            if enforce_private_only_next_hop:
                route_details.append("enforce_private_only_next_hop=true")
            plan_lines.append(
                f"~ patch route guardrails ({len(route_details)}) across {route_targets} route targets"
            )

        if not plan_lines:
            plan_lines.append("# no terraform changes would be rendered for the current policy scope")

        post_check_steps: List[str] = [
            "Re-run Pipeline or Scan for the affected cloud accounts immediately after apply.",
            "Confirm cloud topology nodes, device inventory, and account sync state remain aligned.",
        ]
        if blocked_ingress_cidrs:
            post_check_steps.append("Verify blocked ingress CIDRs no longer appear in scoped security policies.")
        if protected_route_destinations or allowed_default_route_targets or enforce_private_only_next_hop:
            post_check_steps.append("Verify protected routes and approved next-hop targets remain policy compliant.")
        if required_tags:
            post_check_steps.append("Confirm required tags are present on the targeted resources after refresh.")

        evidence_artifacts = [
            "intent.json",
            "simulation.json",
            "execution-request.json",
            "terraform-render.json",
            "terraform-plan-preview.json",
            "rollback-plan.json",
            "post-check-result.json",
            "rollback-result.json",
            "runner-result.json",
            "logs/version.log",
            "logs/init.log",
            "logs/validate.log",
            "logs/plan.log",
            "logs/apply.log",
            "logs/output.log",
        ]

        risk_hints = []
        if missing_required_tags > 0:
            risk_hints.append(
                f"{missing_required_tags} scoped resources already violate required tag policy and will need follow-up verification."
            )
        if blocked_ingress_cidrs and sg_targets == 0:
            risk_hints.append("Blocked ingress CIDRs are configured but no security-policy targets are currently in scope.")
        if protected_route_destinations and route_targets == 0:
            risk_hints.append("Protected routes are configured but no route-like targets are currently in scope.")
        if scoped_resources == 0:
            risk_hints.append("Current scope matches no discovered resources. Review provider/account/region filters before approval.")

        return {
            "engine": "terraform",
            "workspace_prefix": f"netsphere-{slug}",
            "modules": modules,
            "plan_lines": plan_lines,
            "change_blocks": change_blocks,
            "scoped_resources": int(scoped_resources),
            "resources_by_type": dict(resources_by_type),
            "missing_required_tags": int(missing_required_tags),
            "summary": {
                "providers": int(len(providers)),
                "accounts": int(len(account_ids)),
                "regions": int(len(regions)),
                "resource_types": int(len(resource_types)),
                "required_tags": int(len(required_tags)),
                "blocked_ingress_cidrs": int(len(blocked_ingress_cidrs)),
                "protected_route_destinations": int(len(protected_route_destinations)),
                "allowed_default_route_targets": int(len(allowed_default_route_targets)),
                "enforce_private_only_next_hop": bool(enforce_private_only_next_hop),
                "security_group_like_targets": int(sg_targets),
                "route_like_targets": int(route_targets),
                "narrow_scope_ready": bool(
                    len(providers) == 1 and len(account_ids) <= 1 and len(regions) <= 2 and len(resource_types) <= 3
                ),
            },
            "post_check_plan": {
                "required": True,
                "steps": post_check_steps,
            },
            "evidence_plan": {
                "operator_package_sections": [
                    "change_preview",
                    "approval_context",
                    "terraform_render",
                    "execution_logs",
                    "post_check_results",
                    "rollback_plan",
                ],
                "artifacts": evidence_artifacts,
            },
            "rollback_plan": {
                "strategy": "terraform_state_reconcile",
                "trigger": "post_check_failed",
                "automatic_enabled": False,
                "automatic_eligible": False,
                "operator_steps": [
                    "Review the post-check result before approving any rollback action.",
                    "Use the rendered Terraform bundle and state backend to prepare rollback execution.",
                    "Capture verification and rollback evidence in the operator package.",
                ],
                "evidence_artifacts": [
                    "terraform-plan-preview.json",
                    "post-check-result.json",
                    "rollback-plan.json",
                    "rollback-result.json",
                ],
            },
            "risk_hints": risk_hints,
            "operator_notes": [
                "Review the change preview before submitting approval.",
                "Provider credentials and Terraform runtime are required for live apply in production.",
                "Start with a single account, one or two regions, and a narrow resource type scope before widening rollout.",
            ],
        }

    @staticmethod
    def _build_pre_check_summary(
        normalized_intent: Dict[str, Any],
        validation: Dict[str, Any],
        blast_radius: Dict[str, Any],
        cloud_scope: Dict[str, Any],
        terraform_plan_preview: Dict[str, Any],
        operational_guardrails: Dict[str, Any],
        *,
        risk_score: int,
    ) -> Dict[str, Any]:
        intent_type = str(normalized_intent.get("intent_type") or "").strip().lower()
        findings: List[Dict[str, Any]] = []
        evaluated_checks: List[str] = []

        def _mark(check_key: str) -> None:
            if check_key not in evaluated_checks:
                evaluated_checks.append(check_key)

        def _add_finding(
            key: str,
            severity: str,
            category: str,
            title: str,
            message: str,
            *,
            blocking: bool = False,
            recommendation: str | None = None,
        ) -> None:
            findings.append(
                {
                    "key": key,
                    "severity": severity,
                    "category": category,
                    "title": title,
                    "message": message,
                    "blocking": bool(blocking),
                    "recommendation": recommendation,
                }
            )

        validation_errors = list(validation.get("errors") or [])
        validation_conflicts = list(validation.get("conflicts") or [])
        validation_warnings = list(validation.get("warnings") or [])

        _mark("validation_errors")
        if validation_errors:
            _add_finding(
                "validation_errors",
                "critical",
                "validity",
                "Validation errors must be fixed first",
                f"{len(validation_errors)} validation error(s) are still present in this intent draft.",
                blocking=True,
                recommendation="Resolve validation failures before moving this intent into approval.",
            )

        _mark("validation_conflicts")
        if validation_conflicts:
            _add_finding(
                "validation_conflicts",
                "critical",
                "validity",
                "Conflicting intent logic detected",
                f"{len(validation_conflicts)} intent conflict(s) were detected during simulation.",
                blocking=True,
                recommendation="Resolve overlapping or contradictory rules before rollout.",
            )

        _mark("validation_warnings")
        if validation_warnings:
            _add_finding(
                "validation_warnings",
                "warning",
                "validity",
                "Validation warnings need operator review",
                f"{len(validation_warnings)} warning(s) were raised while normalizing the intent.",
                recommendation="Review warnings and confirm the intent still reflects the intended rollout.",
            )

        estimated_devices = int(blast_radius.get("estimated_devices") or 0)
        estimated_networks = int(blast_radius.get("estimated_networks") or 0)
        estimated_rules = int(blast_radius.get("estimated_rules") or 0)
        _mark("blast_radius")
        if estimated_devices >= 100 or estimated_networks >= 20 or estimated_rules >= 40:
            _add_finding(
                "blast_radius",
                "warning",
                "scope",
                "Blast radius is larger than a first-wave change",
                f"Simulation touches an estimated {estimated_devices} device(s), {estimated_networks} network object(s), and {estimated_rules} rule/object change(s).",
                recommendation="Start with a narrow subset before widening rollout.",
            )

        _mark("risk_score")
        if int(risk_score) >= 70:
            _add_finding(
                "risk_score",
                "warning",
                "scope",
                "Risk score is in the elevated range",
                f"The current simulated risk score is {int(risk_score)}, which is above the normal narrow-wave baseline.",
                recommendation="Use approval review and staged execution before any production rollout.",
            )

        if intent_type == "cloud_policy":
            scoped_resources = int(cloud_scope.get("scoped_resources") or 0)
            missing_required_tags = int(cloud_scope.get("missing_required_tags") or 0)
            route_targets = int(cloud_scope.get("route_like_targets") or 0)
            security_targets = int(cloud_scope.get("security_group_like_targets") or 0)

            plan_summary = terraform_plan_preview.get("summary") if isinstance(terraform_plan_preview, dict) else {}
            if not isinstance(plan_summary, dict):
                plan_summary = {}
            narrow_scope_ready = bool(plan_summary.get("narrow_scope_ready"))

            guardrail_summary = operational_guardrails.get("summary") if isinstance(operational_guardrails, dict) else {}
            if not isinstance(guardrail_summary, dict):
                guardrail_summary = {}
            guardrail_findings = operational_guardrails.get("findings") if isinstance(operational_guardrails, dict) else []
            if not isinstance(guardrail_findings, list):
                guardrail_findings = []
            guardrail_keys = {str(row.get("key") or "").strip().lower() for row in guardrail_findings if isinstance(row, dict)}

            _mark("scoped_resources")
            if scoped_resources <= 0:
                _add_finding(
                    "empty_scope",
                    "critical",
                    "scope",
                    "Current filters match no discovered resources",
                    "The current provider, account, region, or resource filters do not match any discovered cloud resources.",
                    blocking=True,
                    recommendation="Adjust the target scope before requesting approval.",
                )

            _mark("missing_required_tags")
            if missing_required_tags > 0:
                _add_finding(
                    "missing_required_tags",
                    "warning",
                    "drift",
                    "Existing scope already violates required tags",
                    f"{missing_required_tags} scoped resource(s) are currently missing one or more required tags.",
                    recommendation="Plan follow-up verification so tag drift is closed after apply.",
                )

            _mark("narrow_scope")
            if scoped_resources > 0 and not narrow_scope_ready:
                _add_finding(
                    "narrow_scope",
                    "warning",
                    "scope",
                    "Scope is wider than the preferred first wave",
                    "The current scope spans multiple providers, accounts, regions, or resource types beyond the narrow rollout baseline.",
                    recommendation="Reduce provider, account, or region breadth before the first production change.",
                )

            _mark("public_ingress")
            if "public_ingress" in guardrail_keys and security_targets > 0:
                _add_finding(
                    "public_ingress",
                    "critical",
                    "exposure",
                    "Public ingress controls are affected",
                    f"Security guardrails for {security_targets} scoped policy target(s) include public ingress CIDRs.",
                    blocking=True,
                    recommendation="Keep this change approval-gated and verify effective security rules after apply.",
                )

            _mark("default_route")
            if "default_route" in guardrail_keys and route_targets > 0:
                _add_finding(
                    "default_route",
                    "critical",
                    "routing",
                    "Default-route behavior is in scope",
                    f"Route guardrails affect {route_targets} route-capable target(s), including default-route behavior.",
                    blocking=True,
                    recommendation="Review next-hop policy and plan an explicit post-check before rollout.",
                )

            _mark("high_impact_edges")
            if "high_impact_edges" in guardrail_keys:
                _add_finding(
                    "high_impact_edges",
                    "warning",
                    "scope",
                    "High-impact edge resources are included",
                    "NAT, load balancer, VPN, or transit edge resources are within the target scope.",
                    recommendation="Roll out edge-facing changes in small waves with rollback evidence ready.",
                )

            scoped_accounts = int(guardrail_summary.get("scoped_accounts") or 0)
            change_enabled_accounts = int(guardrail_summary.get("change_enabled_accounts") or 0)
            _mark("change_enabled_accounts")
            if scoped_accounts > 0 and change_enabled_accounts != scoped_accounts:
                _add_finding(
                    "change_enabled_accounts",
                    "critical",
                    "readiness",
                    "Not all scoped accounts are change-enabled",
                    f"Only {change_enabled_accounts} of {scoped_accounts} scoped account(s) are ready for change execution.",
                    blocking=True,
                    recommendation="Fix credentials and execution readiness before any real apply attempt.",
                )

            _mark("state_backend")
            if str(guardrail_summary.get("state_backend") or "").strip().lower() == "local":
                _add_finding(
                    "state_backend",
                    "warning",
                    "readiness",
                    "Local Terraform state backend is still configured",
                    "Local state is acceptable for lab previews but weak for shared operator workflows.",
                    recommendation="Move to remote state before multi-operator or production rollout.",
                )

            _mark("post_check_coverage")
            post_check_plan = (
                terraform_plan_preview.get("post_check_plan")
                if isinstance(terraform_plan_preview, dict)
                else {}
            )
            post_check_steps = list(post_check_plan.get("steps") or []) if isinstance(post_check_plan, dict) else []
            if len(post_check_steps) < 3:
                _add_finding(
                    "post_check_coverage",
                    "warning",
                    "verification",
                    "Post-check coverage is still light",
                    f"Only {len(post_check_steps)} verification step(s) are staged for this rollout.",
                    recommendation="Add targeted verification before approving production execution.",
                )

            _mark("rollback_path")
            rollback_plan = (
                terraform_plan_preview.get("rollback_plan")
                if isinstance(terraform_plan_preview, dict)
                else {}
            )
            if isinstance(rollback_plan, dict) and rollback_plan.get("automatic_enabled") is False:
                _add_finding(
                    "rollback_path",
                    "info",
                    "recovery",
                    "Rollback remains operator-driven",
                    "Automatic rollback is not enabled for this change path and will require operator review.",
                    recommendation="Confirm rollback evidence and operator steps before approval.",
                )

        blocker_count = sum(1 for row in findings if bool(row.get("blocking")))
        warning_count = sum(1 for row in findings if str(row.get("severity") or "").strip().lower() == "warning")
        info_count = sum(1 for row in findings if str(row.get("severity") or "").strip().lower() == "info")
        result = "block" if blocker_count > 0 else "warn" if warning_count > 0 else "pass"

        return {
            "rule_pack": {
                "name": "Digital Twin Lite",
                "version": "2026.03",
                "mode": "explainable",
                "intent_type": intent_type or "unknown",
                "checks_run": evaluated_checks,
            },
            "summary": {
                "result": result,
                "blocking": bool(blocker_count > 0),
                "blockers": int(blocker_count),
                "warnings": int(warning_count),
                "info": int(info_count),
                "checks_run": int(len(evaluated_checks)),
            },
            "findings": findings,
        }

    @staticmethod
    def _build_before_after_compare_summary(
        normalized_intent: Dict[str, Any],
        cloud_scope: Dict[str, Any] | None,
        terraform_plan_preview: Dict[str, Any] | None,
        operational_guardrails: Dict[str, Any] | None,
        pre_check: Dict[str, Any] | None,
        *,
        risk_score: int,
    ) -> Dict[str, Any]:
        intent_type = str(normalized_intent.get("intent_type") or "").strip().lower()
        spec = normalized_intent.get("spec") if isinstance(normalized_intent.get("spec"), dict) else {}
        cloud_scope = cloud_scope if isinstance(cloud_scope, dict) else {}
        terraform_plan_preview = terraform_plan_preview if isinstance(terraform_plan_preview, dict) else {}
        operational_guardrails = operational_guardrails if isinstance(operational_guardrails, dict) else {}
        pre_check = pre_check if isinstance(pre_check, dict) else {}

        cards: List[Dict[str, Any]] = []

        def _add_card(
            key: str,
            title: str,
            before: str,
            after: str,
            *,
            tone: str = "info",
            status: str = "review",
            recommendation: str | None = None,
        ) -> None:
            cards.append(
                {
                    "key": key,
                    "title": title,
                    "before": before,
                    "after": after,
                    "tone": tone,
                    "status": status,
                    "recommendation": recommendation,
                }
            )

        if intent_type == "cloud_policy":
            required_tags = int(len(list(spec.get("required_tags") or [])))
            blocked_ingress_cidrs = int(len(list(spec.get("blocked_ingress_cidrs") or [])))
            protected_route_destinations = int(len(list(spec.get("protected_route_destinations") or [])))
            scoped_resources = int(cloud_scope.get("scoped_resources") or 0)
            target_providers = int(len(list(cloud_scope.get("target_providers") or [])))
            target_accounts = int(len(list(cloud_scope.get("target_accounts") or [])))
            missing_required_tags = int(cloud_scope.get("missing_required_tags") or 0)
            security_targets = int(cloud_scope.get("security_group_like_targets") or 0)
            route_targets = int(cloud_scope.get("route_like_targets") or 0)
            instance_targets = int(cloud_scope.get("instance_like_targets") or 0)
            network_targets = int(cloud_scope.get("network_like_targets") or 0)

            plan_summary = terraform_plan_preview.get("summary") if isinstance(terraform_plan_preview.get("summary"), dict) else {}
            post_check_plan = (
                terraform_plan_preview.get("post_check_plan")
                if isinstance(terraform_plan_preview.get("post_check_plan"), dict)
                else {}
            )
            rollback_plan = (
                terraform_plan_preview.get("rollback_plan")
                if isinstance(terraform_plan_preview.get("rollback_plan"), dict)
                else {}
            )
            guardrail_summary = (
                operational_guardrails.get("summary")
                if isinstance(operational_guardrails.get("summary"), dict)
                else {}
            )
            pre_check_summary = pre_check.get("summary") if isinstance(pre_check.get("summary"), dict) else {}

            narrow_scope_ready = bool(plan_summary.get("narrow_scope_ready"))
            scoped_accounts = int(guardrail_summary.get("scoped_accounts") or 0)
            change_enabled_accounts = int(guardrail_summary.get("change_enabled_accounts") or 0)
            post_check_steps = int(len(list(post_check_plan.get("steps") or [])))
            blockers = int(pre_check_summary.get("blockers") or 0)
            warnings = int(pre_check_summary.get("warnings") or 0)

            if scoped_resources <= 0:
                _add_card(
                    "scope_discipline",
                    "Scope discipline",
                    "The current filters do not match any discovered cloud resources.",
                    "Approval and execution stay blocked until the provider, account, region, or type scope maps to real discovered resources.",
                    tone="bad",
                    status="blocked",
                    recommendation="Adjust the scope selectors so the preview can anchor to discovered resources.",
                )
            else:
                _add_card(
                    "scope_discipline",
                    "Scope discipline",
                    f"The current scope touches {scoped_resources} discovered resources across {target_providers} provider(s) and {target_accounts} account(s).",
                    "This intent is already narrow enough for a staged approval wave."
                    if narrow_scope_ready
                    else "The scope still needs to be reduced into a smaller approval wave before real execution.",
                    tone="good" if narrow_scope_ready else "warn",
                    status="ready" if narrow_scope_ready else "review",
                    recommendation="Keep the first rollout narrow by trimming provider, account, or region breadth."
                    if not narrow_scope_ready
                    else "Carry this same narrow scope into approval so the first execution wave stays controlled.",
                )

            if required_tags > 0:
                _add_card(
                    "tag_hygiene",
                    "Tag hygiene",
                    f"{missing_required_tags} scoped resource(s) currently drift from the {required_tags} required tag rule(s).",
                    f"This intent keeps {required_tags} required tag check(s) in scope so drift stays visible before and after execution.",
                    tone="warn" if missing_required_tags > 0 else "good",
                    status="review" if missing_required_tags > 0 else "ready",
                    recommendation="Use the tag drift findings to clean up ownership and environment metadata before broad rollout."
                    if missing_required_tags > 0
                    else "Keep the required tags in the template so later changes inherit the same baseline.",
                )
            else:
                _add_card(
                    "tag_hygiene",
                    "Tag hygiene",
                    "No required tag policy is currently attached to this cloud scope.",
                    "Tag drift will remain informational until required tag rules are added to the intent or template.",
                    tone="info",
                    status="review",
                    recommendation="Add owner, environment, or service tags if this scope should move into a governed operating baseline.",
                )

            guardrail_actions: List[str] = []
            if blocked_ingress_cidrs > 0:
                guardrail_actions.append(f"block {blocked_ingress_cidrs} ingress CIDR pattern(s)")
            if protected_route_destinations > 0:
                guardrail_actions.append(f"protect {protected_route_destinations} route destination(s)")
            _add_card(
                "edge_exposure",
                "Edge exposure",
                f"The current scope includes {security_targets} security targets, {route_targets} route targets, {instance_targets} instance targets, and {network_targets} network targets.",
                (
                    "This intent will " + " and ".join(guardrail_actions) + " during the staged change path."
                    if guardrail_actions
                    else "No ingress or route guardrails are defined yet for this intent."
                ),
                tone="good" if guardrail_actions else "warn",
                status="ready" if guardrail_actions else "review",
                recommendation="Encode public ingress and default-route protections before approval if this scope touches edge-facing resources."
                if not guardrail_actions
                else "Review the protected ingress and route destinations so they match the intended service boundary.",
            )

            readiness_tone = (
                "good"
                if scoped_accounts > 0 and change_enabled_accounts == scoped_accounts and post_check_steps > 0
                else "warn"
            )
            _add_card(
                "execution_readiness",
                "Execution readiness",
                f"{change_enabled_accounts}/{scoped_accounts or target_accounts} scoped account(s) are currently change-enabled.",
                (
                    f"Post-check runs {post_check_steps} step(s) and automatic rollback is available."
                    if bool(rollback_plan.get("automatic_enabled"))
                    else f"Post-check runs {post_check_steps} step(s) and rollback stays operator-reviewed."
                ),
                tone=readiness_tone,
                status="ready" if readiness_tone == "good" else "review",
                recommendation="Keep execution in preview or approval-only mode until credentials, verification coverage, and rollback steps are complete."
                if readiness_tone != "good"
                else "The execution path is structured enough for approval review.",
            )

            _add_card(
                "approval_readiness",
                "Approval readiness",
                f"Digital Twin Lite currently reports risk {risk_score}, {blockers} blocker(s), and {warnings} warning(s).",
                (
                    "Resolve blockers before apply and carry the remaining warnings into operator review."
                    if blockers > 0
                    else "The current intent is ready to move into approval with the remaining warnings documented for reviewers."
                ),
                tone="bad" if blockers > 0 else "warn" if warnings > 0 else "good",
                status="blocked" if blockers > 0 else "review" if warnings > 0 else "ready",
                recommendation="Close the blocker list first so approval can focus on scoped risk instead of structural issues."
                if blockers > 0
                else "Use approval notes to document the remaining warnings before execution.",
            )
        else:
            _add_card(
                "change_posture",
                "Change posture",
                "The current preview defines the scope, risk score, and approval boundary for this intent.",
                "Approval will carry the same summary forward with verification, rollback, and evidence expectations.",
                tone="info",
                status="review",
                recommendation="Use preview and approval together so the operator path stays explainable.",
            )

        blocked_cards = sum(1 for row in cards if str(row.get("status") or "").strip().lower() == "blocked")
        review_cards = sum(1 for row in cards if str(row.get("status") or "").strip().lower() == "review")
        ready_cards = sum(1 for row in cards if str(row.get("status") or "").strip().lower() == "ready")
        result = "blocked" if blocked_cards > 0 else "review" if review_cards > 0 else "ready"
        return {
            "summary": {
                "result": result,
                "cards": int(len(cards)),
                "ready_cards": int(ready_cards),
                "review_cards": int(review_cards),
                "blocked_cards": int(blocked_cards),
            },
            "cards": cards,
        }

    @staticmethod
    def validate_intent(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
        normalized = IntentService._normalize_payload(payload)
        errors: List[str] = []
        warnings: List[str] = []
        conflicts: List[Dict[str, Any]] = []

        intent_type = normalized["intent_type"]
        if intent_type not in IntentService.ALLOWED_TYPES:
            errors.append(f"intent_type must be one of: {', '.join(sorted(IntentService.ALLOWED_TYPES))}")

        if len(normalized["name"]) < 3:
            errors.append("name must be at least 3 chars")
        if len(normalized["name"]) > 120:
            errors.append("name must be <= 120 chars")

        spec_out: Dict[str, Any] = {}
        if intent_type == "segment":
            spec_out, e, w, c = IntentService._validate_segment_spec(normalized["spec"])
            errors.extend(e)
            warnings.extend(w)
            conflicts.extend(c)
        elif intent_type == "access_policy":
            spec_out, e, w, c = IntentService._validate_access_policy_spec(normalized["spec"])
            errors.extend(e)
            warnings.extend(w)
            conflicts.extend(c)
        elif intent_type == "qos":
            spec_out, e, w, c = IntentService._validate_qos_spec(normalized["spec"])
            errors.extend(e)
            warnings.extend(w)
            conflicts.extend(c)
        elif intent_type == "cloud_policy":
            spec_out, e, w, c = IntentService._validate_cloud_policy_spec(normalized["spec"])
            errors.extend(e)
            warnings.extend(w)
            conflicts.extend(c)

        normalized["spec"] = spec_out

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "conflicts": conflicts,
            "normalized_intent": normalized,
            "supported_intents": IntentService.supported_intents(),
        }

    @staticmethod
    def simulate_intent(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
        validation = IntentService.validate_intent(db, payload)
        normalized = validation.get("normalized_intent") or {}
        intent_type = str(normalized.get("intent_type") or "")
        spec = normalized.get("spec") if isinstance(normalized.get("spec"), dict) else {}

        risk_base = {"segment": 35, "access_policy": 45, "qos": 30, "cloud_policy": 40}.get(intent_type, 50)
        warnings = list(validation.get("warnings") or [])
        conflicts = list(validation.get("conflicts") or [])
        risk_score = int(min(100, max(0, risk_base + (len(warnings) * 5) + (len(conflicts) * 15))))

        blast_radius: Dict[str, Any] = {"estimated_devices": 0, "estimated_networks": 0, "estimated_rules": 0}
        change_summary: List[str] = []
        cloud_scope: Dict[str, Any] = {}
        terraform_plan_preview: Dict[str, Any] = {}
        operational_guardrails: Dict[str, Any] = {}

        if intent_type == "segment":
            segments = list(spec.get("segments") or [])
            blast_radius["estimated_networks"] = len(segments)
            addr_budget = 0
            for seg in segments:
                seg_name = str(seg.get("name") or "")
                cidrs = list(seg.get("cidrs") or [])
                change_summary.append(f"segment:{seg_name} cidrs={len(cidrs)}")
                for cidr in cidrs:
                    try:
                        net = ipaddress.ip_network(str(cidr), strict=False)
                        addr_budget += min(int(net.num_addresses), 4096)
                    except Exception:
                        continue
            blast_radius["estimated_devices"] = int(max(1, addr_budget // 64)) if addr_budget > 0 else 0

        elif intent_type == "access_policy":
            rules = list(spec.get("rules") or [])
            blast_radius["estimated_rules"] = len(rules)
            blast_radius["estimated_devices"] = int(max(1, len(rules) * 3)) if rules else 0
            for rule in rules[:20]:
                change_summary.append(
                    f"acl:{rule.get('name')} {rule.get('action')} src={','.join(rule.get('sources') or [])} dst={','.join(rule.get('destinations') or [])}"
                )

        elif intent_type == "qos":
            classes = list(spec.get("classes") or [])
            blast_radius["estimated_rules"] = len(classes)
            blast_radius["estimated_devices"] = int(max(1, len(classes) * 2)) if classes else 0
            for q in classes[:20]:
                change_summary.append(f"qos:{q.get('name')} priority={q.get('priority')} min={q.get('min_guarantee_pct')}%")
        elif intent_type == "cloud_policy":
            targets = spec.get("targets") if isinstance(spec.get("targets"), dict) else {}
            provider_filter = set(
                IntentService._normalize_cloud_provider(v)
                for v in list(targets.get("providers") or [])
                if str(v or "").strip()
            )
            account_filter = set(int(v) for v in list(targets.get("account_ids") or []) if int(v) > 0)
            region_filter = set(str(v).strip() for v in list(targets.get("regions") or []) if str(v).strip())
            type_filter = set(str(v).strip().lower() for v in list(targets.get("resource_types") or []) if str(v).strip())
            required_tags = list(spec.get("required_tags") or [])
            blocked_ingress_cidrs = list(spec.get("blocked_ingress_cidrs") or [])
            protected_route_destinations = list(spec.get("protected_route_destinations") or [])

            rows = (
                db.query(CloudResource, CloudAccount.provider)
                .join(CloudAccount, CloudAccount.id == CloudResource.account_id)
                .filter(CloudAccount.is_active == True)  # noqa: E712
                .all()
            )

            scoped_resources: List[CloudResource] = []
            resources_by_type: Dict[str, int] = {}
            resources_by_provider: Dict[str, int] = {}
            resources_by_provider_type: Dict[str, Dict[str, int]] = {}
            regions_by_provider: Dict[str, set[str]] = {}
            accounts_by_provider: Dict[str, set[int]] = {}
            missing_required_tags = 0
            target_accounts = set()
            target_providers = set()

            for resource, raw_provider in rows:
                provider = IntentService._normalize_cloud_provider(raw_provider)
                if provider_filter and provider not in provider_filter:
                    continue
                if account_filter and int(resource.account_id) not in account_filter:
                    continue
                region = str(resource.region or "").strip()
                if region_filter and region not in region_filter:
                    continue
                r_type = str(resource.resource_type or "").strip().lower()
                if type_filter and r_type not in type_filter:
                    continue

                scoped_resources.append(resource)
                resources_by_type[r_type] = int(resources_by_type.get(r_type, 0)) + 1
                resources_by_provider[provider] = int(resources_by_provider.get(provider, 0)) + 1
                resources_by_provider_type.setdefault(provider, {})
                resources_by_provider_type[provider][r_type] = int(resources_by_provider_type[provider].get(r_type, 0)) + 1
                regions_by_provider.setdefault(provider, set())
                if region:
                    regions_by_provider[provider].add(region)
                accounts_by_provider.setdefault(provider, set()).add(int(resource.account_id))
                target_accounts.add(int(resource.account_id))
                target_providers.add(provider)

                if required_tags:
                    tags = IntentService._extract_cloud_tags(resource.resource_metadata)
                    missing = False
                    for rule in required_tags:
                        key = str(rule.get("key") or "").strip()
                        if not key:
                            continue
                        expected = rule.get("value")
                        actual = tags.get(key)
                        if actual is None:
                            missing = True
                            break
                        if expected is not None and str(actual) != str(expected):
                            missing = True
                            break
                    if missing:
                        missing_required_tags += 1

            route_like_count = int(
                sum(v for k, v in resources_by_type.items() if "route" in k or "router" in k)
            )
            sg_like_count = int(
                sum(v for k, v in resources_by_type.items() if ("security_group" in k) or (k in {"nsg", "firewall"}))
            )
            instance_like_count = int(
                sum(v for k, v in resources_by_type.items() if (k in {"instance", "vm"}) or ("instance" in k))
            )
            network_like_count = int(
                sum(v for k, v in resources_by_type.items() if (k in {"vpc", "vnet", "subnet"}) or ("subnet" in k))
            )

            cloud_scope = {
                "scoped_resources": int(len(scoped_resources)),
                "resources_by_type": dict(sorted(resources_by_type.items(), key=lambda x: x[0])),
                "resources_by_provider": dict(sorted(resources_by_provider.items(), key=lambda x: x[0])),
                "resources_by_provider_type": {
                    str(provider): dict(sorted(type_counts.items(), key=lambda x: x[0]))
                    for provider, type_counts in sorted(resources_by_provider_type.items(), key=lambda x: x[0])
                },
                "regions_by_provider": {
                    str(provider): sorted(values)
                    for provider, values in sorted(regions_by_provider.items(), key=lambda x: x[0])
                },
                "accounts_by_provider": {
                    str(provider): sorted(int(value) for value in values)
                    for provider, values in sorted(accounts_by_provider.items(), key=lambda x: x[0])
                },
                "missing_required_tags": int(missing_required_tags),
                "target_accounts": sorted(target_accounts),
                "target_providers": sorted(target_providers),
                "security_group_like_targets": int(sg_like_count),
                "route_like_targets": int(route_like_count),
                "instance_like_targets": int(instance_like_count),
                "network_like_targets": int(network_like_count),
                "guardrails": {
                    "required_tags": int(len(required_tags)),
                    "blocked_ingress_cidrs": int(len(blocked_ingress_cidrs)),
                    "protected_route_destinations": int(len(protected_route_destinations)),
                },
            }

            blast_radius["estimated_devices"] = int(instance_like_count)
            blast_radius["estimated_networks"] = int(network_like_count)
            blast_radius["estimated_rules"] = int(
                len(required_tags) + len(blocked_ingress_cidrs) + len(protected_route_destinations)
            )

            change_summary.append(
                f"cloud_scope resources={len(scoped_resources)} providers={len(target_providers)} accounts={len(target_accounts)}"
            )
            if required_tags:
                change_summary.append(
                    f"cloud_tags required={len(required_tags)} missing_estimate={missing_required_tags}"
                )
            if blocked_ingress_cidrs:
                change_summary.append(
                    f"cloud_sg_guardrails cidrs={len(blocked_ingress_cidrs)} targets={sg_like_count}"
                )
            if protected_route_destinations:
                change_summary.append(
                    f"cloud_route_guardrails destinations={len(protected_route_destinations)} targets={route_like_count}"
                )

            terraform_plan_preview = IntentService._build_cloud_policy_terraform_preview(normalized, cloud_scope)

            if len(scoped_resources) > 500:
                risk_score = min(100, risk_score + 15)
            elif len(scoped_resources) > 150:
                risk_score = min(100, risk_score + 8)

            operational_guardrails = IntentService._build_cloud_operational_guardrails(
                db,
                normalized,
                cloud_scope,
                risk_score=int(risk_score),
            )

        max_auto_apply = IntentService.max_auto_apply_risk_score(db)
        max_auto_publish = IntentService.northbound_max_auto_publish_risk_score(db)
        pre_check = IntentService._build_pre_check_summary(
            normalized,
            validation,
            blast_radius,
            cloud_scope,
            terraform_plan_preview,
            operational_guardrails,
            risk_score=int(risk_score),
        )
        before_after_compare = IntentService._build_before_after_compare_summary(
            normalized,
            cloud_scope,
            terraform_plan_preview,
            operational_guardrails,
            pre_check,
            risk_score=int(risk_score),
        )
        pre_check_summary = pre_check.get("summary") if isinstance(pre_check.get("summary"), dict) else {}
        guardrail_summary = {}
        if intent_type == "cloud_policy" and isinstance(operational_guardrails, dict):
            maybe_summary = operational_guardrails.get("summary")
            guardrail_summary = maybe_summary if isinstance(maybe_summary, dict) else {}
        change_enabled_accounts = int(guardrail_summary.get("change_enabled_accounts") or 0)
        scoped_accounts = int(guardrail_summary.get("scoped_accounts") or 0)
        apply_eligible = (
            bool(validation.get("valid"))
            and not conflicts
            and risk_score <= max_auto_apply
            and (scoped_accounts == 0 or change_enabled_accounts == scoped_accounts)
            and not bool(pre_check_summary.get("blocking"))
        )
        northbound_auto_eligible = (
            bool(validation.get("valid"))
            and not conflicts
            and risk_score <= max_auto_publish
            and not bool(pre_check_summary.get("blocking"))
        )

        recommendations: List[str] = []
        if not validation.get("valid"):
            recommendations.append("Fix validation errors before simulation/apply.")
        if conflicts:
            recommendations.append("Resolve conflict list first; current payload is high-risk.")
        if bool(pre_check_summary.get("blocking")):
            recommendations.append(
                "Resolve pre-check blockers before moving from preview into approval or real execution."
            )
        if risk_score > max_auto_apply:
            recommendations.append(
                f"Risk score {risk_score} exceeds auto-apply threshold {max_auto_apply}. Use approval workflow."
            )
        if scoped_accounts > 0 and change_enabled_accounts != scoped_accounts:
            recommendations.append(
                "Some scoped accounts are still read-only. Keep this intent in preview or mock mode until execution readiness is clear."
            )
        if not recommendations:
            recommendations.append("Payload looks consistent for staged rollout.")

        return {
            "validation": validation,
            "risk_score": int(risk_score),
            "blast_radius": blast_radius,
            "change_summary": change_summary,
            "cloud_scope": cloud_scope if intent_type == "cloud_policy" else {},
            "terraform_plan_preview": terraform_plan_preview if intent_type == "cloud_policy" else {},
            "operational_guardrails": operational_guardrails if intent_type == "cloud_policy" else {},
            "pre_check": pre_check,
            "before_after_compare": before_after_compare,
            "apply_eligible": bool(apply_eligible),
            "max_auto_apply_risk_score": int(max_auto_apply),
            "northbound_publish_policy": {
                "policy_enabled": bool(IntentService.northbound_policy_enabled(db)),
                "decision": "auto" if northbound_auto_eligible else "approval_gated",
                "risk_score": int(risk_score),
                "max_auto_publish_risk_score": int(max_auto_publish),
                "auto_eligible": bool(northbound_auto_eligible),
            },
            "recommendations": recommendations,
        }

    @staticmethod
    def _normalize_execution_actions(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not isinstance(metadata, dict):
            return []
        raw = metadata.get("execution_actions")
        if not isinstance(raw, list):
            return []

        out: List[Dict[str, Any]] = []
        for idx, row in enumerate(raw, start=1):
            if not isinstance(row, dict):
                continue
            action_type = str(row.get("type") or "").strip().lower()
            if not action_type:
                continue
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            out.append(
                {
                    "index": idx,
                    "type": action_type,
                    "payload": payload,
                    "continue_on_error": bool(row.get("continue_on_error", False)),
                }
            )
        return out

    @staticmethod
    def _ensure_default_cloud_intent_action(
        normalized_intent: Dict[str, Any],
        *,
        execution_id: str,
        approval_id: int | None,
        actions: List[Dict[str, Any]] | None,
    ) -> List[Dict[str, Any]]:
        out = list(actions or [])
        if str(normalized_intent.get("intent_type") or "").strip().lower() != "cloud_policy":
            return out
        if any(str(row.get("type") or "").strip().lower() == "cloud_intent_apply" for row in out):
            return out
        out.append(
            {
                "index": len(out) + 1,
                "type": "cloud_intent_apply",
                "payload": {
                    "approval_id": int(approval_id) if approval_id is not None else None,
                    "execution_id": str(execution_id),
                },
                "continue_on_error": False,
            }
        )
        return out

    @staticmethod
    def _execute_run_scan_action(
        db: Session,
        *,
        action: Dict[str, Any],
        execution_id: str,
    ) -> Dict[str, Any]:
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
        cidr = str(payload.get("cidr") or "").strip()
        if not cidr:
            raise ValueError("run_scan action requires payload.cidr")

        site_id = payload.get("site_id")
        if site_id is not None and str(site_id).strip() != "":
            site_id = int(site_id)
        else:
            site_id = None

        snmp_profile_id = payload.get("snmp_profile_id")
        if snmp_profile_id is not None and str(snmp_profile_id).strip() != "":
            snmp_profile_id = int(snmp_profile_id)
        else:
            snmp_profile_id = None

        community = str(
            payload.get("community")
            or IntentService._get_setting(db, "default_snmp_community", "public")
            or "public"
        ).strip() or "public"
        snmp_version = str(payload.get("snmp_version") or "v2c").strip() or "v2c"
        try:
            snmp_port = int(payload.get("snmp_port") if payload.get("snmp_port") is not None else 161)
        except Exception:
            snmp_port = 161
        snmp_port = max(1, min(65535, int(snmp_port)))

        from app.services.discovery_service import DiscoveryService
        from app.tasks.discovery_dispatch import dispatch_discovery_scan

        service = DiscoveryService(db)
        job = service.create_scan_job(
            cidr=cidr,
            community=community,
            site_id=site_id,
            snmp_profile_id=snmp_profile_id,
            snmp_version=snmp_version,
            snmp_port=snmp_port,
        )
        idemp = str(payload.get("idempotency_key") or "").strip()
        if not idemp:
            idemp = f"intent:{execution_id}:run_scan:{int(action.get('index') or 0)}"
        dispatch = dispatch_discovery_scan(int(job.id), idempotency_key=idemp)
        status = str(dispatch.get("status") or "").strip().lower()
        if status not in {"enqueued", "skipped"}:
            raise RuntimeError(f"run_scan dispatch failed: {dispatch.get('reason') or status or 'unknown'}")

        return {
            "index": int(action.get("index") or 0),
            "type": "run_scan",
            "status": "dispatched",
            "job_id": int(job.id),
            "cidr": cidr,
            "site_id": site_id,
            "dispatch": dispatch,
        }

    @staticmethod
    def _execute_template_deploy_action(
        db: Session,
        *,
        action: Dict[str, Any],
        execution_id: str,
        actor_user: Any,
    ) -> Dict[str, Any]:
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
        try:
            template_id = int(payload.get("template_id"))
        except Exception:
            raise ValueError("template_deploy action requires payload.template_id")
        if template_id <= 0:
            raise ValueError("template_deploy action requires payload.template_id > 0")

        raw_device_ids = payload.get("device_ids")
        if not isinstance(raw_device_ids, list) or not raw_device_ids:
            raise ValueError("template_deploy action requires non-empty payload.device_ids list")

        device_ids: List[int] = []
        for v in raw_device_ids:
            try:
                did = int(v)
            except Exception:
                continue
            if did > 0 and did not in device_ids:
                device_ids.append(did)
        if not device_ids:
            raise ValueError("template_deploy action payload.device_ids has no valid positive integers")

        variables = payload.get("variables") if isinstance(payload.get("variables"), dict) else {}
        pre_check_commands = [str(c).strip() for c in list(payload.get("pre_check_commands") or []) if str(c).strip()]
        post_check_commands = [str(c).strip() for c in list(payload.get("post_check_commands") or []) if str(c).strip()]

        try:
            canary_count = max(0, int(payload.get("canary_count") if payload.get("canary_count") is not None else 0))
        except Exception:
            canary_count = 0
        try:
            wave_size = max(0, int(payload.get("wave_size") if payload.get("wave_size") is not None else 0))
        except Exception:
            wave_size = 0
        try:
            inter_wave_delay_seconds = float(
                payload.get("inter_wave_delay_seconds") if payload.get("inter_wave_delay_seconds") is not None else 0.0
            )
        except Exception:
            inter_wave_delay_seconds = 0.0
        inter_wave_delay_seconds = max(0.0, min(300.0, inter_wave_delay_seconds))

        approval_id = payload.get("approval_id")
        if approval_id is not None and str(approval_id).strip() == "":
            approval_id = None
        if approval_id is not None:
            approval_id = int(approval_id)

        exec_id = str(payload.get("execution_id") or "").strip() or None
        idemp = str(payload.get("idempotency_key") or "").strip()
        if not idemp:
            idemp = f"intent:{execution_id}:template_deploy:{int(action.get('index') or 0)}"

        from app.api.v1.endpoints.config_template import TemplateDeployRequest, deploy_template

        req = TemplateDeployRequest(
            device_ids=device_ids,
            variables=variables,
            save_pre_backup=bool(payload.get("save_pre_backup", True)),
            rollback_on_failure=bool(payload.get("rollback_on_failure", True)),
            prepare_device_snapshot=bool(payload.get("prepare_device_snapshot", True)),
            pre_check_commands=pre_check_commands,
            post_check_enabled=bool(payload.get("post_check_enabled", True)),
            post_check_commands=post_check_commands,
            canary_count=canary_count,
            wave_size=wave_size,
            stop_on_wave_failure=bool(payload.get("stop_on_wave_failure", True)),
            inter_wave_delay_seconds=inter_wave_delay_seconds,
            idempotency_key=idemp,
            approval_id=approval_id,
            execution_id=exec_id,
        )
        out = deploy_template(template_id=template_id, req=req, db=db, current_user=actor_user)
        execution = out.get("execution") if isinstance(out, dict) else {}

        return {
            "index": int(action.get("index") or 0),
            "type": "template_deploy",
            "status": "dispatched",
            "template_id": int(template_id),
            "device_ids": device_ids,
            "execution": execution if isinstance(execution, dict) else {},
        }

    @staticmethod
    def _execute_webhook_action(
        db: Session,
        *,
        action: Dict[str, Any],
        normalized_intent: Dict[str, Any],
        execution_id: str,
    ) -> Dict[str, Any]:
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}

        from app.services.webhook_service import WebhookService

        result = WebhookService.send(
            db,
            event_type=str(payload.get("event_type") or "intent_apply"),
            title=str(payload.get("title") or f"Intent Applied: {normalized_intent.get('name') or execution_id}"),
            message=str(payload.get("message") or "Intent apply action triggered."),
            severity=str(payload.get("severity") or "info"),
            source=str(payload.get("source") or "intent_engine"),
            data={
                "execution_id": execution_id,
                "intent_type": normalized_intent.get("intent_type"),
                "intent_name": normalized_intent.get("name"),
                "action_payload": payload,
            },
        )
        if not result.get("success"):
            raise RuntimeError(str(result.get("error") or "webhook send failed"))

        return {
            "index": int(action.get("index") or 0),
            "type": "webhook",
            "status": "sent",
            "mode": result.get("mode"),
            "status_code": result.get("status_code"),
            "attempts": result.get("attempts"),
            "delivery_id": result.get("delivery_id"),
        }

    @staticmethod
    def _execute_cloud_bootstrap_action(
        db: Session,
        *,
        action: Dict[str, Any],
        execution_id: str,
        actor_user: Any,
    ) -> Dict[str, Any]:
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}

        raw_account_ids = payload.get("account_ids")
        account_ids: List[int] = []
        if isinstance(raw_account_ids, list):
            for v in raw_account_ids:
                try:
                    aid = int(v)
                except Exception:
                    continue
                if aid > 0 and aid not in account_ids:
                    account_ids.append(aid)

        raw_regions = payload.get("regions")
        regions: List[str] = []
        if isinstance(raw_regions, list):
            for v in raw_regions:
                text = str(v or "").strip()
                if text and text not in regions:
                    regions.append(text)
        raw_resource_ids = payload.get("resource_ids")
        resource_ids: List[str] = []
        seen_resource_ids: set[str] = set()
        if isinstance(raw_resource_ids, list):
            for v in raw_resource_ids:
                text = str(v or "").strip()
                key = text.lower()
                if text and key not in seen_resource_ids:
                    seen_resource_ids.add(key)
                    resource_ids.append(text)

        try:
            canary_count = max(0, int(payload.get("canary_count") if payload.get("canary_count") is not None else 0))
        except Exception:
            canary_count = 0
        try:
            wave_size = max(0, int(payload.get("wave_size") if payload.get("wave_size") is not None else 0))
        except Exception:
            wave_size = 0
        try:
            inter_wave_delay_seconds = float(
                payload.get("inter_wave_delay_seconds") if payload.get("inter_wave_delay_seconds") is not None else 0.0
            )
        except Exception:
            inter_wave_delay_seconds = 0.0
        inter_wave_delay_seconds = max(0.0, min(300.0, inter_wave_delay_seconds))

        approval_id = payload.get("approval_id")
        if approval_id is not None and str(approval_id).strip() == "":
            approval_id = None
        if approval_id is not None:
            approval_id = int(approval_id)

        exec_id = str(payload.get("execution_id") or "").strip() or None
        idemp = str(payload.get("idempotency_key") or "").strip()
        if not idemp:
            idemp = f"intent:{execution_id}:cloud_bootstrap:{int(action.get('index') or 0)}"

        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        script_template = str(payload.get("script_template") or "").strip() or None
        dry_run = bool(payload.get("dry_run", True))

        from app.schemas.cloud import CloudBootstrapRunRequest
        from app.services.change_policy_service import ChangePolicyService
        from app.services.cloud_bootstrap_service import CloudBootstrapService

        if ChangePolicyService.requires_cloud_bootstrap_live_approval(
            db,
            dry_run=bool(dry_run),
            approval_id=(int(approval_id) if approval_id is not None else None),
        ):
            raise ValueError("cloud_bootstrap action requires payload.approval_id for live run by policy")

        req = CloudBootstrapRunRequest(
            account_ids=account_ids or None,
            regions=regions or None,
            resource_ids=resource_ids or None,
            dry_run=bool(dry_run),
            pre_check_enabled=bool(payload.get("pre_check_enabled", True)),
            post_check_enabled=bool(payload.get("post_check_enabled", True)),
            rollback_on_failure=bool(payload.get("rollback_on_failure", True)),
            canary_count=int(canary_count),
            wave_size=int(wave_size),
            stop_on_wave_failure=bool(payload.get("stop_on_wave_failure", True)),
            inter_wave_delay_seconds=float(inter_wave_delay_seconds),
            idempotency_key=idemp,
            force=bool(payload.get("force", False)),
            approval_id=(int(approval_id) if approval_id is not None else None),
            execution_id=exec_id,
            script_template=script_template,
            context=context,
        )
        out = CloudBootstrapService.run(
            db,
            tenant_id=getattr(actor_user, "tenant_id", None),
            owner_id=int(getattr(actor_user, "id", 0) or 0),
            req=req,
        )
        out_payload = out.model_dump() if hasattr(out, "model_dump") else (dict(out) if isinstance(out, dict) else {})

        return {
            "index": int(action.get("index") or 0),
            "type": "cloud_bootstrap",
            "status": "dispatched",
            "run_status": str(out_payload.get("status") or ""),
            "total_targets": int(out_payload.get("total_targets") or 0),
            "success_targets": int(out_payload.get("success_targets") or 0),
            "failed_targets": int(out_payload.get("failed_targets") or 0),
            "dry_run_targets": int(out_payload.get("dry_run_targets") or 0),
            "approval_id": out_payload.get("approval_id"),
            "execution_id": out_payload.get("execution_id"),
            "idempotency_key": out_payload.get("idempotency_key"),
        }

    @staticmethod
    def _execute_cloud_intent_apply_action(
        db: Session,
        *,
        action: Dict[str, Any],
        normalized_intent: Dict[str, Any],
        simulation: Dict[str, Any],
        execution_id: str,
        actor_user: Any,
    ) -> Dict[str, Any]:
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
        approval_id = payload.get("approval_id")
        if approval_id is not None and str(approval_id).strip() == "":
            approval_id = None
        if approval_id is not None:
            approval_id = int(approval_id)

        from app.services.cloud_intent_execution_service import CloudIntentExecutionService

        out = CloudIntentExecutionService.run(
            db,
            normalized_intent=normalized_intent,
            simulation=simulation,
            execution_id=execution_id,
            approval_id=approval_id,
            actor_user=actor_user,
        )
        out["index"] = int(action.get("index") or 0)
        out["type"] = "cloud_intent_apply"
        return out

    @staticmethod
    def _execute_action_plan(
        db: Session,
        *,
        normalized_intent: Dict[str, Any],
        simulation: Dict[str, Any],
        actor_user: Any,
        execution_id: str,
        actions: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        metadata = normalized_intent.get("metadata") if isinstance(normalized_intent.get("metadata"), dict) else {}
        if actions is None:
            actions = IntentService._normalize_execution_actions(metadata)
        stop_on_error = bool(metadata.get("execution_stop_on_error", True))

        results: List[Dict[str, Any]] = []
        errors = 0
        executed = 0

        for action in actions:
            a_type = str(action.get("type") or "").strip().lower()
            continue_on_error = bool(action.get("continue_on_error", False))
            try:
                if a_type == "run_scan":
                    row = IntentService._execute_run_scan_action(
                        db,
                        action=action,
                        execution_id=execution_id,
                    )
                elif a_type == "template_deploy":
                    row = IntentService._execute_template_deploy_action(
                        db,
                        action=action,
                        execution_id=execution_id,
                        actor_user=actor_user,
                    )
                elif a_type == "webhook":
                    row = IntentService._execute_webhook_action(
                        db,
                        action=action,
                        normalized_intent=normalized_intent,
                        execution_id=execution_id,
                    )
                elif a_type == "cloud_bootstrap":
                    row = IntentService._execute_cloud_bootstrap_action(
                        db,
                        action=action,
                        execution_id=execution_id,
                        actor_user=actor_user,
                    )
                elif a_type == "cloud_intent_apply":
                    row = IntentService._execute_cloud_intent_apply_action(
                        db,
                        action=action,
                        normalized_intent=normalized_intent,
                        simulation=simulation,
                        execution_id=execution_id,
                        actor_user=actor_user,
                    )
                else:
                    row = {
                        "index": int(action.get("index") or 0),
                        "type": a_type,
                        "status": "skipped_unsupported_action",
                    }

                if str(row.get("status") or "").strip().lower() not in {"error", "skipped_unsupported_action"}:
                    executed += 1
                results.append(row)
            except Exception as e:
                errors += 1
                row = {
                    "index": int(action.get("index") or 0),
                    "type": a_type,
                    "status": "error",
                    "error": f"{type(e).__name__}: {e}",
                }
                results.append(row)
                if stop_on_error and not continue_on_error:
                    break

        return {
            "enabled": True,
            "requested": len(actions),
            "executed": int(executed),
            "errors": int(errors),
            "results": results,
        }

    @staticmethod
    def _resolve_northbound_publish_policy(
        db: Session,
        *,
        simulation: Dict[str, Any],
        approval_id: int | None,
        requested_actions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        has_webhook_actions = any(str(a.get("type") or "").strip().lower() == "webhook" for a in requested_actions)
        max_auto_publish = IntentService.northbound_max_auto_publish_risk_score(db)
        risk_score = int(simulation.get("risk_score") or 0)
        validation = simulation.get("validation") if isinstance(simulation.get("validation"), dict) else {}
        conflicts = list(validation.get("conflicts") or [])
        auto_eligible = bool(validation.get("valid")) and (len(conflicts) == 0) and risk_score <= max_auto_publish
        decision = "auto" if auto_eligible else "approval_gated"
        policy_enabled = IntentService.northbound_policy_enabled(db)
        requires_approval = bool(
            policy_enabled
            and has_webhook_actions
            and decision == "approval_gated"
            and approval_id is None
        )
        reason = "no_webhook_action"
        if has_webhook_actions:
            if decision == "auto":
                reason = "risk_within_auto_threshold"
            else:
                reason = "risk_or_conflict_requires_approval"
        return {
            "enabled": bool(policy_enabled),
            "decision": decision,
            "reason": reason,
            "requires_approval": bool(requires_approval),
            "approval_provided": approval_id is not None,
            "webhook_actions_requested": int(sum(1 for a in requested_actions if str(a.get("type") or "").strip().lower() == "webhook")),
            "risk_score": int(risk_score),
            "max_auto_publish_risk_score": int(max_auto_publish),
            "auto_eligible": bool(auto_eligible),
        }

    @staticmethod
    def apply_intent(db: Session, payload: Dict[str, Any], actor_user: Any) -> Dict[str, Any]:
        normalized = IntentService._normalize_payload(payload)
        simulation = IntentService.simulate_intent(db, normalized)
        validation = simulation.get("validation") if isinstance(simulation.get("validation"), dict) else {}
        if not validation.get("valid"):
            return {
                "status": "rejected_validation",
                "message": "Intent payload failed validation",
                "simulation": simulation,
            }

        execution_id = str(normalized.get("execution_id") or "").strip()
        if not execution_id:
            execution_id = ChangeExecutionService.make_fingerprint(
                "intent_apply",
                {
                    "intent_type": normalized.get("intent_type"),
                    "name": normalized.get("name"),
                    "spec": normalized.get("spec"),
                    "approval_id": normalized.get("approval_id"),
                },
            )

        idem = str(normalized.get("idempotency_key") or "").strip()
        if idem:
            claimed = ChangeExecutionService.claim_idempotency(
                "intent_apply",
                idem,
                ttl_seconds=120,
                db=db,
            )
            if not claimed:
                return {
                    "status": "skipped_idempotent",
                    "message": "Duplicate intent apply request blocked",
                    "execution_id": execution_id,
                    "idempotency_key": idem,
                    "simulation": simulation,
                }

        if bool(normalized.get("dry_run", True)):
            return {
                "status": "dry_run",
                "message": "Dry-run only. No persistent change applied.",
                "execution_id": execution_id,
                "simulation": simulation,
            }

        requires_approval = IntentService.apply_requires_approval(db)
        approval_id = normalized.get("approval_id")
        if requires_approval and approval_id is None:
            return {
                "status": "approval_required",
                "message": "Live intent apply requires approval_id by policy.",
                "execution_id": execution_id,
                "required": True,
                "simulation": simulation,
            }

        requested_actions = IntentService._normalize_execution_actions(normalized.get("metadata") or {})
        requested_actions = IntentService._ensure_default_cloud_intent_action(
            normalized,
            execution_id=execution_id,
            approval_id=approval_id,
            actions=requested_actions,
        )
        northbound_publish = IntentService._resolve_northbound_publish_policy(
            db,
            simulation=simulation,
            approval_id=approval_id,
            requested_actions=requested_actions,
        )
        if bool(northbound_publish.get("requires_approval")):
            return {
                "status": "approval_required",
                "required": True,
                "required_for": "northbound_publish",
                "message": (
                    "Northbound publish is approval-gated by policy. "
                    "Submit approval_id for this intent apply request."
                ),
                "execution_id": execution_id,
                "simulation": simulation,
                "northbound_publish": northbound_publish,
            }

        actions_enabled = IntentService.apply_execute_actions_enabled(db)
        actions_result = None
        if requested_actions:
            if actions_enabled:
                actions_result = IntentService._execute_action_plan(
                    db,
                    normalized_intent=normalized,
                    simulation=simulation,
                    actor_user=actor_user,
                    execution_id=execution_id,
                    actions=requested_actions,
                )
            else:
                actions_result = {
                    "enabled": False,
                    "requested": len(requested_actions),
                    "executed": 0,
                    "errors": 0,
                    "results": [
                        {
                            "index": int(a.get("index") or 0),
                            "type": str(a.get("type") or ""),
                            "status": "skipped_execution_disabled",
                        }
                        for a in requested_actions
                    ],
                }

        setting_key = f"intent_v1_execution:{execution_id}"
        record = {
            "execution_id": execution_id,
            "intent_type": normalized.get("intent_type"),
            "name": normalized.get("name"),
            "spec": normalized.get("spec"),
            "metadata": normalized.get("metadata"),
            "risk_score": int(simulation.get("risk_score") or 0),
            "conflicts": simulation.get("validation", {}).get("conflicts", []),
            "warnings": simulation.get("validation", {}).get("warnings", []),
            "approval_id": int(approval_id) if approval_id is not None else None,
            "applied_by_user_id": int(getattr(actor_user, "id", 0) or 0),
            "applied_at": datetime.now(timezone.utc).isoformat(),
            "execution_actions": actions_result,
            "northbound_publish": northbound_publish,
            "terraform_plan_preview": simulation.get("terraform_plan_preview"),
        }
        row = db.query(SystemSetting).filter(SystemSetting.key == setting_key).first()
        if not row:
            row = SystemSetting(
                key=setting_key,
                value=json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str),
                description=f"intent execution {execution_id}",
                category="intent",
            )
        else:
            row.value = json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str)
            row.description = f"intent execution {execution_id}"
            row.category = "intent"
        db.add(row)

        last_key = "intent_v1_last_execution_id"
        last = db.query(SystemSetting).filter(SystemSetting.key == last_key).first()
        if not last:
            last = SystemSetting(
                key=last_key,
                value=str(execution_id),
                description="latest intent execution id",
                category="intent",
            )
        else:
            last.value = str(execution_id)
        db.add(last)
        db.commit()

        message = "Intent applied and persisted."
        if isinstance(actions_result, dict):
            if bool(actions_result.get("enabled")):
                errors = int(actions_result.get("errors") or 0)
                requested = int(actions_result.get("requested") or 0)
                executed = int(actions_result.get("executed") or 0)
                message = f"Intent applied and actions processed ({executed}/{requested}, errors={errors})."
            else:
                message = "Intent applied. Execution actions were skipped by policy."

        return {
            "status": "applied",
            "message": message,
            "execution_id": execution_id,
            "setting_key": setting_key,
            "approval_id": int(approval_id) if approval_id is not None else None,
            "simulation": simulation,
            "execution_actions": actions_result,
            "northbound_publish": northbound_publish,
        }
