from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models.device import Device, Link, Site
from app.models.topology import TopologySnapshot
from app.services.topology_event_service import publish_topology_event


class TopologySnapshotService:
    @staticmethod
    def _build_graph(db: Session, *, site_id: Optional[int] = None) -> Dict[str, Any]:
        devices_q = db.query(Device)
        if site_id is not None:
            devices_q = devices_q.filter(Device.site_id == site_id)
        devices = devices_q.all()

        sites = db.query(Site.id, Site.name).all()
        site_map = {sid: name for sid, name in sites}

        nodes: List[Dict[str, Any]] = []
        for d in devices:
            is_cloud = str(getattr(d, "device_type", "") or "") == "cloud_virtual"
            label = d.name
            if is_cloud:
                refs = (((d.variables or {}).get("cloud") or {}).get("refs") or [])
                provider = (refs[0].get("provider") if refs else None) or "cloud"
                region = (refs[0].get("region") if refs else None) or ""
                provider_label = str(provider).upper()
                region_label = str(region).strip()
                label = f"{provider_label}{(' ' + region_label) if region_label else ''} {d.ip_address}"
            nodes.append(
                {
                    "id": str(d.id),
                    "label": label,
                    "ip": d.ip_address,
                    "type": d.device_type,
                    "hostname": d.hostname,
                    "model": d.model,
                    "os_version": d.os_version,
                    "status": "online" if is_cloud else str(getattr(d, "status", None) or "offline").lower(),
                    "site_id": getattr(d, "site_id", None),
                    "site_name": "Cloud" if is_cloud else site_map.get(getattr(d, "site_id", None), "Default Site"),
                    "tier": 1 if is_cloud else 2,
                    "role": "cloud" if is_cloud else str(getattr(d, "role", None) or "access"),
                    "metrics": {
                        "cpu": 0,
                        "memory": 0,
                        "health_score": 100,
                        "traffic_in": 0,
                        "traffic_out": 0,
                    },
                }
            )

        device_ids = [d.id for d in devices if d and d.id is not None]
        links_q = db.query(Link).filter(Link.target_device_id.isnot(None))
        if site_id is not None and device_ids:
            links_q = links_q.filter(Link.source_device_id.in_(device_ids), Link.target_device_id.in_(device_ids))
        links = links_q.all()

        edges: List[Dict[str, Any]] = []
        for l in links:
            src_port_raw = str(l.source_interface_name or "")
            dst_port_raw = str(l.target_interface_name or "")
            edges.append(
                {
                    "source": str(l.source_device_id),
                    "target": str(l.target_device_id),
                    "src_port": src_port_raw,
                    "dst_port": dst_port_raw,
                    "label": f"{src_port_raw}<->{dst_port_raw}",
                    "status": "active" if str(l.status) in ["up", "active"] else "down",
                    "protocol": l.protocol or "LLDP",
                    "traffic": {"fwd_bps": 0, "rev_bps": 0, "fwd": 0, "rev": 0},
                }
            )

        return {"nodes": nodes, "links": edges}

    @staticmethod
    def create_snapshot(
        db: Session,
        *,
        site_id: Optional[int] = None,
        job_id: Optional[int] = None,
        label: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TopologySnapshot:
        graph = TopologySnapshotService._build_graph(db, site_id=site_id)
        nodes = graph.get("nodes") or []
        links = graph.get("links") or []

        snap = TopologySnapshot(
            site_id=site_id,
            job_id=job_id,
            label=label,
            node_count=int(len(nodes)),
            link_count=int(len(links)),
            nodes_json=json.dumps(nodes, ensure_ascii=False, default=str),
            links_json=json.dumps(links, ensure_ascii=False, default=str),
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False, default=str),
        )
        db.add(snap)
        db.commit()
        db.refresh(snap)
        publish_topology_event(
            db,
            "topology_snapshot_created",
            {
                "snapshot": TopologySnapshotService.to_dict(snap),
                "site_id": site_id,
                "job_id": job_id,
                "label": label,
                "source": "topology_snapshot",
                "refresh_hint": "snapshots",
            },
            site_id=site_id,
            persist=True,
            realtime=True,
        )
        db.commit()
        return snap

    @staticmethod
    def get_snapshot_graph(db: Session, snapshot_id: int) -> Dict[str, Any]:
        snap = db.query(TopologySnapshot).filter(TopologySnapshot.id == snapshot_id).first()
        if not snap:
            raise ValueError("snapshot not found")
        try:
            nodes = json.loads(snap.nodes_json or "[]")
        except Exception:
            nodes = []
        try:
            links = json.loads(snap.links_json or "[]")
        except Exception:
            links = []
        return {"snapshot": TopologySnapshotService.to_dict(snap), "nodes": nodes, "links": links}

    @staticmethod
    def list_snapshots(
        db: Session,
        *,
        site_id: Optional[int] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        q = db.query(TopologySnapshot)
        if site_id is not None:
            q = q.filter(TopologySnapshot.site_id == site_id)
        if limit < 1:
            limit = 1
        if limit > 200:
            limit = 200
        rows = q.order_by(desc(TopologySnapshot.created_at), desc(TopologySnapshot.id)).limit(limit).all()
        return [TopologySnapshotService.to_dict(r) for r in rows]

    @staticmethod
    def to_dict(snap: TopologySnapshot) -> Dict[str, Any]:
        created_at = getattr(snap, "created_at", None)
        return {
            "id": int(snap.id),
            "site_id": getattr(snap, "site_id", None),
            "job_id": getattr(snap, "job_id", None),
            "label": getattr(snap, "label", None),
            "node_count": int(getattr(snap, "node_count", 0) or 0),
            "link_count": int(getattr(snap, "link_count", 0) or 0),
            "created_at": created_at.isoformat() if created_at else None,
        }

    @staticmethod
    def diff_snapshots(db: Session, snapshot_a: int, snapshot_b: int) -> Dict[str, Any]:
        a = db.query(TopologySnapshot).filter(TopologySnapshot.id == snapshot_a).first()
        b = db.query(TopologySnapshot).filter(TopologySnapshot.id == snapshot_b).first()
        if not a or not b:
            raise ValueError("snapshot not found")

        def parse_links(s: TopologySnapshot) -> List[Dict[str, Any]]:
            try:
                v = json.loads(s.links_json or "[]")
            except Exception:
                v = []
            return v if isinstance(v, list) else []

        a_links = parse_links(a)
        b_links = parse_links(b)

        def key_of(link: Dict[str, Any]) -> str:
            return "|".join(
                [
                    str(link.get("source") or ""),
                    str(link.get("src_port") or ""),
                    str(link.get("target") or ""),
                    str(link.get("dst_port") or ""),
                    str(link.get("protocol") or "LLDP").upper(),
                ]
            )

        a_by = {key_of(l): l for l in a_links if isinstance(l, dict)}
        b_by = {key_of(l): l for l in b_links if isinstance(l, dict)}

        a_keys = set(a_by.keys())
        b_keys = set(b_by.keys())

        added = [b_by[k] for k in sorted(b_keys - a_keys)]
        removed = [a_by[k] for k in sorted(a_keys - b_keys)]

        changed: List[Dict[str, Any]] = []
        for k in sorted(a_keys & b_keys):
            la = a_by.get(k) or {}
            lb = b_by.get(k) or {}
            if str(la.get("status")) != str(lb.get("status")):
                changed.append({"before": la, "after": lb})

        return {
            "snapshot_a": TopologySnapshotService.to_dict(a),
            "snapshot_b": TopologySnapshotService.to_dict(b),
            "counts": {"added": len(added), "removed": len(removed), "changed": len(changed)},
            "added": added,
            "removed": removed,
            "changed": changed,
        }
