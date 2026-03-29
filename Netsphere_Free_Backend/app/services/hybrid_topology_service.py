from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.cloud import CloudAccount, CloudResource
from app.models.device import Device, Link
from app.models.settings import SystemSetting
from app.models.topology_candidate import TopologyNeighborCandidate
from app.services.cloud_normalization_service import CloudNormalizationService
from app.services.ip_intel_service import IpIntelService
from app.services.license_policy_service import LicensePolicyService
from app.services.topology_link_service import TopologyLinkService


class HybridTopologyService:
    @staticmethod
    def build_inferred_cloud_links(
        db: Session,
        *,
        tenant_id: int | None,
        owner_id: int,
        enrich: bool = True,
    ) -> Dict[str, int]:
        peer_map = HybridTopologyService._collect_inferred_peer_ips(db, tenant_id=tenant_id, enrich=enrich)
        if not peer_map:
            return {
                "created_virtual_devices": 0,
                "updated_virtual_devices": 0,
                "created_links": 0,
                "updated_links": 0,
                "low_confidence_enqueued": 0,
                "skipped": 0,
            }

        virtual_by_ip, created_v, updated_v = HybridTopologyService._ensure_virtual_devices(
            db,
            tenant_id=tenant_id,
            owner_id=owner_id,
            peer_map=peer_map,
        )

        created_l = 0
        updated_l = 0
        low_confidence_enqueued = 0
        skipped = 0
        now = datetime.now(timezone.utc)

        devices_q = db.query(Device)
        if tenant_id is not None:
            devices_q = devices_q.filter(Device.tenant_id == tenant_id)
        devices = devices_q.filter(Device.device_type != "cloud_virtual").all()

        for dev in devices:
            parsed = dev.latest_parsed_data or {}
            l3 = parsed.get("l3_routing") or {}
            bgp_neighbors = l3.get("bgp_neighbors") or []

            for n in bgp_neighbors:
                n_ip = (n.get("neighbor_ip") or "").strip()
                if not n_ip:
                    continue
                vdev = virtual_by_ip.get(n_ip)
                if not vdev:
                    continue
                state = str(n.get("state") or "").strip().lower()
                status = "active" if ("established" in state or state.isdigit()) else "degraded"
                confidence = HybridTopologyService._confidence_score_from_refs(
                    HybridTopologyService._cloud_refs_from_virtual(vdev),
                    fallback=0.62,
                )
                created, updated = HybridTopologyService._upsert_link(
                    db,
                    now=now,
                    a=dev,
                    a_intf="BGP",
                    b=vdev,
                    b_intf="CLOUD",
                    protocol="BGP",
                    status=status,
                    confidence=confidence,
                    discovery_source="bgp_inferred_cloud",
                )
                created_l += created
                updated_l += updated
                low_confidence_enqueued += HybridTopologyService._upsert_low_confidence_candidate_for_cloud_link(
                    db,
                    now=now,
                    source=dev,
                    cloud_peer=vdev,
                    local_interface="BGP",
                    remote_interface="CLOUD",
                    protocol="BGP",
                    confidence=confidence,
                    discovery_source="bgp_inferred_cloud",
                )

        return {
            "created_virtual_devices": created_v,
            "updated_virtual_devices": updated_v,
            "created_links": created_l,
            "updated_links": updated_l,
            "low_confidence_enqueued": low_confidence_enqueued,
            "skipped": skipped,
        }

    @staticmethod
    def build_cloud_peer_links(
        db: Session,
        *,
        tenant_id: int | None,
        owner_id: int,
    ) -> Dict[str, int]:
        peer_map = HybridTopologyService._collect_cloud_peer_ips(db, tenant_id=tenant_id)
        if not peer_map:
            return {
                "created_virtual_devices": 0,
                "updated_virtual_devices": 0,
                "created_links": 0,
                "updated_links": 0,
                "low_confidence_enqueued": 0,
                "skipped": 0,
            }

        virtual_by_ip, created_v, updated_v = HybridTopologyService._ensure_virtual_devices(
            db,
            tenant_id=tenant_id,
            owner_id=owner_id,
            peer_map=peer_map,
        )

        created_l = 0
        updated_l = 0
        low_confidence_enqueued = 0
        skipped = 0
        now = datetime.now(timezone.utc)

        devices_q = db.query(Device)
        if tenant_id is not None:
            devices_q = devices_q.filter(Device.tenant_id == tenant_id)
        devices = devices_q.filter(Device.device_type != "cloud_virtual").all()

        for dev in devices:
            parsed = dev.latest_parsed_data or {}
            l3 = parsed.get("l3_routing") or {}
            bgp_neighbors = l3.get("bgp_neighbors") or []
            ospf_neighbors = l3.get("ospf_neighbors") or []

            for n in bgp_neighbors:
                n_ip = (n.get("neighbor_ip") or "").strip()
                if not n_ip:
                    continue
                vdev = virtual_by_ip.get(n_ip)
                if not vdev:
                    continue
                state = str(n.get("state") or "").strip().lower()
                status = "active" if ("established" in state or state.isdigit()) else "degraded"
                refs = HybridTopologyService._cloud_refs_from_virtual(vdev)
                confidence = min(
                    0.92 if status == "active" else 0.78,
                    HybridTopologyService._confidence_score_from_refs(refs, fallback=0.78),
                )
                created, updated = HybridTopologyService._upsert_link(
                    db,
                    now=now,
                    a=dev,
                    a_intf="BGP",
                    b=vdev,
                    b_intf="CLOUD",
                    protocol="BGP",
                    status=status,
                    confidence=confidence,
                    discovery_source="cloud_hybrid",
                )
                created_l += created
                updated_l += updated
                low_confidence_enqueued += HybridTopologyService._upsert_low_confidence_candidate_for_cloud_link(
                    db,
                    now=now,
                    source=dev,
                    cloud_peer=vdev,
                    local_interface="BGP",
                    remote_interface="CLOUD",
                    protocol="BGP",
                    confidence=confidence,
                    discovery_source="cloud_hybrid",
                )

            for n in ospf_neighbors:
                n_ip = (n.get("neighbor_ip") or "").strip()
                if not n_ip:
                    continue
                vdev = virtual_by_ip.get(n_ip)
                if not vdev:
                    continue
                local_intf = (n.get("interface") or "").strip() or "OSPF"
                state = str(n.get("state") or "").strip().upper()
                status = "active" if "FULL" in state else "degraded"
                refs = HybridTopologyService._cloud_refs_from_virtual(vdev)
                confidence = min(
                    0.88 if status == "active" else 0.74,
                    HybridTopologyService._confidence_score_from_refs(refs, fallback=0.74),
                )
                created, updated = HybridTopologyService._upsert_link(
                    db,
                    now=now,
                    a=dev,
                    a_intf=local_intf,
                    b=vdev,
                    b_intf="CLOUD",
                    protocol="OSPF",
                    status=status,
                    confidence=confidence,
                    discovery_source="cloud_hybrid",
                )
                created_l += created
                updated_l += updated
                low_confidence_enqueued += HybridTopologyService._upsert_low_confidence_candidate_for_cloud_link(
                    db,
                    now=now,
                    source=dev,
                    cloud_peer=vdev,
                    local_interface=local_intf,
                    remote_interface="CLOUD",
                    protocol="OSPF",
                    confidence=confidence,
                    discovery_source="cloud_hybrid",
                )

        return {
            "created_virtual_devices": created_v,
            "updated_virtual_devices": updated_v,
            "created_links": created_l,
            "updated_links": updated_l,
            "low_confidence_enqueued": low_confidence_enqueued,
            "skipped": skipped,
        }

    @staticmethod
    def _is_public_ip(value: str) -> bool:
        try:
            ip = ipaddress.ip_address(str(value).strip())
        except Exception:
            return False
        if ip.is_loopback or ip.is_multicast or ip.is_unspecified or ip.is_link_local:
            return False
        if getattr(ip, "is_private", False):
            return False
        if getattr(ip, "is_reserved", False):
            return False
        if hasattr(ip, "is_global"):
            return bool(ip.is_global)
        return True

    @staticmethod
    def _collect_inferred_peer_ips(db: Session, *, tenant_id: int | None, enrich: bool) -> Dict[str, List[Dict[str, Any]]]:
        devices_q = db.query(Device)
        if tenant_id is not None:
            devices_q = devices_q.filter(Device.tenant_id == tenant_id)
        devices = devices_q.filter(Device.device_type != "cloud_virtual").all()

        known_ips_q = db.query(Device.ip_address)
        if tenant_id is not None:
            known_ips_q = known_ips_q.filter(Device.tenant_id == tenant_id)
        known_ips = {str(r[0]).strip() for r in known_ips_q.all() if r and r[0]}

        peer_map: Dict[str, List[Dict[str, Any]]] = {}
        for dev in devices:
            parsed = dev.latest_parsed_data or {}
            l3 = parsed.get("l3_routing") or {}
            bgp_neighbors = l3.get("bgp_neighbors") or []
            for n in bgp_neighbors:
                n_ip = (n.get("neighbor_ip") or "").strip()
                if not n_ip:
                    continue
                if n_ip in known_ips:
                    continue
                if not HybridTopologyService._is_public_ip(n_ip):
                    continue
                provider = "inferred"
                intel = None
                if enrich:
                    try:
                        intel = IpIntelService.get_or_fetch(db, n_ip)
                    except Exception:
                        intel = None
                if intel and intel.get("provider_guess"):
                    provider = str(intel.get("provider_guess"))
                peer_map.setdefault(n_ip, []).append(
                    {
                        "provider": provider,
                        "account_id": None,
                        "cloud_resource_id": None,
                        "resource_type": "bgp_peer",
                        "resource_id": n_ip,
                        "name": "BGP Peer",
                        "region": "",
                        "inferred_from": {"device_id": int(dev.id), "device_name": str(dev.name or ""), "reason": "public_bgp_neighbor"},
                        "ip_intel": intel,
                    }
                )

        return peer_map

    @staticmethod
    def _collect_cloud_peer_ips(db: Session, *, tenant_id: int | None) -> Dict[str, List[Dict[str, Any]]]:
        q = db.query(CloudResource, CloudAccount).join(CloudAccount, CloudAccount.id == CloudResource.account_id)
        if tenant_id is not None:
            q = q.filter(CloudAccount.tenant_id == tenant_id)
        rows = q.all()

        peer_map: Dict[str, List[Dict[str, Any]]] = {}
        for res, acc in rows:
            provider = CloudNormalizationService.provider_group(acc.provider)
            normalized = CloudNormalizationService.normalize_resource(acc, res)
            peer_ips = list(normalized.get("peer_ips") or [])
            peer_confidence = str(normalized.get("peer_confidence") or "none").strip().lower() or "none"

            for ip in peer_ips:
                peer_map.setdefault(ip, []).append(
                    {
                        "provider": provider,
                        "account_id": int(acc.id),
                        "account_name": str(acc.name or "") or None,
                        "cloud_resource_id": int(res.id),
                        "resource_type": str(res.resource_type),
                        "resource_id": str(res.resource_id),
                        "name": str(res.name or ""),
                        "region": str(res.region or ""),
                        "peer_confidence": peer_confidence,
                    }
                )

        return peer_map

    @staticmethod
    def _ensure_virtual_devices(
        db: Session,
        *,
        tenant_id: int | None,
        owner_id: int,
        peer_map: Dict[str, List[Dict[str, Any]]],
    ) -> Tuple[Dict[str, Device], int, int]:
        created = 0
        updated = 0
        out: Dict[str, Device] = {}

        existing_q = db.query(Device).filter(Device.device_type == "cloud_virtual")
        if tenant_id is not None:
            existing_q = existing_q.filter(Device.tenant_id == tenant_id)
        existing = existing_q.filter(Device.ip_address.in_(list(peer_map.keys()))).all()
        existing_by_ip = {d.ip_address: d for d in existing if d.ip_address}
        new_peer_ips = [ip for ip in peer_map.keys() if ip not in existing_by_ip]
        if new_peer_ips:
            LicensePolicyService.assert_can_add_devices(
                db,
                additional_devices=len(new_peer_ips),
                source="hybrid_cloud_virtual_device_sync",
            )

        for peer_ip, refs in peer_map.items():
            d = existing_by_ip.get(peer_ip)
            if d:
                vars_ = d.variables or {}
                cloud = vars_.get("cloud") or {}
                cloud["peer_ip"] = peer_ip
                cloud["refs"] = refs
                vars_["virtual"] = True
                vars_["cloud"] = cloud
                d.variables = vars_
                d.role = "cloud"
                if str(getattr(d, "status", "") or "").lower() != "online":
                    d.status = "online"
                d.reachability_status = "reachable"
                db.add(d)
                updated += 1
                out[peer_ip] = d
                continue

            name = HybridTopologyService._virtual_device_name(tenant_id=tenant_id, peer_ip=peer_ip, refs=refs)
            vars_ = {"virtual": True, "cloud": {"peer_ip": peer_ip, "refs": refs}}
            d = Device(
                name=name,
                ip_address=peer_ip,
                device_type="cloud_virtual",
                model="Cloud",
                os_version="N/A",
                status="online",
                reachability_status="reachable",
                telemetry_mode="none",
                polling_interval=3600,
                status_interval=3600,
                variables=vars_,
                owner_id=int(owner_id),
                tenant_id=tenant_id,
                role="cloud",
            )
            db.add(d)
            try:
                db.commit()
                db.refresh(d)
            except IntegrityError:
                db.rollback()
                d = db.query(Device).filter(Device.name == name).first()
                if not d:
                    raise
            created += 1
            out[peer_ip] = d

        db.commit()
        return out, created, updated

    @staticmethod
    def _virtual_device_name(*, tenant_id: int | None, peer_ip: str, refs: List[Dict[str, Any]]) -> str:
        provider = "cloud"
        if refs and refs[0].get("provider"):
            provider = str(refs[0].get("provider"))
        safe_ip = peer_ip.replace(".", "-")
        t = f"t{tenant_id}" if tenant_id is not None else "t0"
        return f"{t}-cloud-{provider}-{safe_ip}"

    @staticmethod
    def _cloud_refs_from_virtual(vdev: Device) -> List[Dict[str, Any]]:
        vars_ = vdev.variables if isinstance(vdev.variables, dict) else {}
        cloud = vars_.get("cloud") if isinstance(vars_.get("cloud"), dict) else {}
        refs = cloud.get("refs") if isinstance(cloud.get("refs"), list) else []
        return [r for r in refs if isinstance(r, dict)]

    @staticmethod
    def _confidence_score_from_refs(refs: List[Dict[str, Any]], *, fallback: float = 0.7) -> float:
        score_by_level = {
            "high": 0.92,
            "medium": 0.78,
            "low": 0.62,
            "none": 0.55,
        }
        best = 0.0
        for ref in refs:
            level = str(ref.get("peer_confidence") or "").strip().lower()
            best = max(best, float(score_by_level.get(level, 0.0)))
        if best <= 0:
            best = float(fallback)
        return max(0.0, min(1.0, float(best)))

    @staticmethod
    def _low_confidence_threshold(db: Session) -> float:
        row = db.query(SystemSetting).filter(SystemSetting.key == "topology_candidate_low_confidence_threshold").first()
        raw = str(getattr(row, "value", "") or "").strip()
        try:
            return float(raw or 0.7)
        except Exception:
            return 0.7

    @staticmethod
    def _upsert_low_confidence_candidate_for_cloud_link(
        db: Session,
        *,
        now: datetime,
        source: Device,
        cloud_peer: Device,
        local_interface: str,
        remote_interface: str,
        protocol: str,
        confidence: float,
        discovery_source: str,
    ) -> int:
        threshold = HybridTopologyService._low_confidence_threshold(db)
        if float(confidence or 0.0) >= threshold:
            return 0

        neighbor_name = str(cloud_peer.name or cloud_peer.hostname or cloud_peer.ip_address or "Cloud Peer").strip()
        mgmt_ip = str(cloud_peer.ip_address or "").strip() or None
        local_i = str(local_interface or "").strip() or None
        remote_i = str(remote_interface or "").strip() or None
        reason = f"cloud_low_confidence:{discovery_source}:{round(float(confidence or 0.0), 3)}"

        existing = db.query(TopologyNeighborCandidate).filter(
            TopologyNeighborCandidate.source_device_id == source.id,
            func.lower(TopologyNeighborCandidate.neighbor_name) == neighbor_name.lower(),
            TopologyNeighborCandidate.mgmt_ip == mgmt_ip,
            func.lower(func.coalesce(TopologyNeighborCandidate.local_interface, "")) == str(local_i or "").lower(),
            func.lower(func.coalesce(TopologyNeighborCandidate.remote_interface, "")) == str(remote_i or "").lower(),
            func.lower(func.coalesce(TopologyNeighborCandidate.protocol, "")) == str(protocol or "").lower(),
        ).first()

        if existing:
            existing.last_seen = now
            existing.reason = reason
            existing.confidence = min(float(existing.confidence or 1.0), float(confidence or 0.0))
            if str(existing.status or "").lower() not in {"promoted", "ignored"}:
                existing.status = "low_confidence"
            db.add(existing)
            db.commit()
            return 0

        db.add(
            TopologyNeighborCandidate(
                discovery_job_id=None,
                source_device_id=int(source.id),
                neighbor_name=neighbor_name,
                mgmt_ip=mgmt_ip,
                local_interface=local_i,
                remote_interface=remote_i,
                protocol=str(protocol or "UNKNOWN"),
                confidence=float(confidence or 0.0),
                reason=reason,
                status="low_confidence",
                first_seen=now,
                last_seen=now,
            )
        )
        db.commit()
        return 1

    @staticmethod
    def _upsert_link(
        db: Session,
        *,
        now: datetime,
        a: Device,
        a_intf: str,
        b: Device,
        b_intf: str,
        protocol: str,
        status: str,
        confidence: float,
        discovery_source: str,
    ) -> Tuple[int, int]:
        src_id, src_intf, dst_id, dst_intf = TopologyLinkService._normalize_link(a.id, a_intf or "", b.id, b_intf or "")
        existing = db.query(Link).filter(
            Link.source_device_id == src_id,
            Link.source_interface_name == (src_intf or ""),
            Link.target_device_id == dst_id,
            Link.target_interface_name == (dst_intf or ""),
        ).first()
        if existing:
            existing.protocol = protocol
            existing.status = status
            existing.last_seen = now
            existing.discovery_source = discovery_source
            existing.confidence = max(float(existing.confidence or 0.0), float(confidence or 0.0))
            db.add(existing)
            db.commit()
            return 0, 1

        link = Link(
            source_device_id=src_id,
            source_interface_name=src_intf or "",
            target_device_id=dst_id,
            target_interface_name=dst_intf or "",
            status=status,
            link_speed="1G",
            protocol=protocol,
            confidence=confidence,
            discovery_source=discovery_source,
            first_seen=now,
            last_seen=now,
        )
        db.add(link)
        db.commit()
        return 1, 0
