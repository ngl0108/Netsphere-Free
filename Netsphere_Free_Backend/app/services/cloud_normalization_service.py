from __future__ import annotations

import ipaddress
from typing import Any, Dict, Iterable, List

from app.models.cloud import CloudAccount, CloudResource


class CloudNormalizationService:
    @staticmethod
    def provider_group(provider: str | None) -> str:
        p = str(provider or "").strip().lower()
        if p in {"naver_cloud", "ncp"}:
            return "naver"
        if p in {"aws", "azure", "gcp", "naver"}:
            return p
        return "cloud"

    @classmethod
    def normalize_resource(cls, account: CloudAccount, resource: CloudResource) -> Dict[str, Any]:
        provider = str(getattr(account, "provider", "") or "").strip().lower()
        provider_grp = cls.provider_group(provider)
        metadata = getattr(resource, "resource_metadata", None) or {}
        peer_ips = cls.extract_peer_ips(
            resource_type=str(getattr(resource, "resource_type", "") or ""),
            metadata=metadata,
        )
        peer_confidence = "high" if peer_ips and str(getattr(resource, "resource_type", "") or "") in {"vpn_connection", "vpn_tunnel"} else ("medium" if peer_ips else "none")

        return {
            "account_id": int(getattr(account, "id")),
            "account_name": str(getattr(account, "name", "") or "") or None,
            "provider": provider,
            "provider_group": provider_grp,
            "resource_uid": f"{provider_grp}:{str(getattr(resource, 'resource_type', '') or '')}:{str(getattr(resource, 'resource_id', '') or '')}",
            "resource_id": str(getattr(resource, "resource_id", "") or ""),
            "resource_type": str(getattr(resource, "resource_type", "") or ""),
            "name": str(getattr(resource, "name", "") or "") or None,
            "region": str(getattr(resource, "region", "") or "") or None,
            "cidr_block": str(getattr(resource, "cidr_block", "") or "") or None,
            "state": str(getattr(resource, "state", "") or "") or None,
            "peer_ips": peer_ips,
            "peer_confidence": peer_confidence,
            "labels": cls.extract_labels(metadata),
            "evidence": metadata if isinstance(metadata, dict) else {},
            "created_at": getattr(resource, "created_at", None),
            "updated_at": getattr(resource, "updated_at", None),
        }

    @classmethod
    def extract_peer_ips(cls, resource_type: str, metadata: Dict[str, Any] | None) -> List[str]:
        rt = str(resource_type or "").strip().lower()
        meta = metadata if isinstance(metadata, dict) else {}
        out: List[str] = []

        if rt == "vpn_connection":
            tunnels = meta.get("tunnels")
            if isinstance(tunnels, list):
                for item in tunnels:
                    if isinstance(item, dict):
                        cls._append_ip(out, item.get("outside_ip"))
            cls._append_ip(out, meta.get("customer_gateway_ip"))
        elif rt == "vpn_tunnel":
            cls._append_ip(out, meta.get("peer_ip"))
        else:
            for key in ("peer_ip", "outside_ip", "customer_gateway_ip", "neighbor_ip", "ip_address"):
                cls._append_ip(out, meta.get(key))

            for item in cls._flatten_values(meta.values()):
                if isinstance(item, str):
                    cls._append_ip(out, item)
                elif isinstance(item, dict):
                    for key in ("peer_ip", "outside_ip", "customer_gateway_ip", "neighbor_ip", "ip_address"):
                        cls._append_ip(out, item.get(key))

        return sorted(set(out))

    @staticmethod
    def extract_labels(metadata: Dict[str, Any] | None) -> Dict[str, str]:
        meta = metadata if isinstance(metadata, dict) else {}
        labels: Dict[str, str] = {}
        raw_tags = meta.get("tags")
        if isinstance(raw_tags, dict):
            for k, v in raw_tags.items():
                key = str(k).strip()
                val = str(v).strip()
                if key and val:
                    labels[key] = val
        return labels

    @staticmethod
    def _flatten_values(values: Iterable[Any]) -> List[Any]:
        out: List[Any] = []
        for value in values:
            if isinstance(value, dict):
                out.append(value)
                out.extend(CloudNormalizationService._flatten_values(value.values()))
            elif isinstance(value, list):
                out.extend(CloudNormalizationService._flatten_values(value))
            else:
                out.append(value)
        return out

    @staticmethod
    def _append_ip(bucket: List[str], candidate: Any) -> None:
        s = str(candidate or "").strip()
        if not s:
            return
        try:
            ipaddress.ip_address(s)
        except Exception:
            return
        bucket.append(s)
