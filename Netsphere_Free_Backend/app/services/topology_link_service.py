from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.device import Device, Link
from app.services.topology_event_service import publish_topology_event


class TopologyLinkService:
    @staticmethod
    def _normalize_device_name(name: str) -> str:
        s = (name or "").strip().lower()
        if not s:
            return ""
        if "." in s:
            s = s.split(".")[0]
        for ch in ("-", "_", " "):
            s = s.replace(ch, "")
        return s

    @staticmethod
    def _expand_neighbor_name_candidates(name: str) -> Tuple[str, ...]:
        raw = (name or "").strip()
        if not raw:
            return tuple()
        cands = {raw}
        if "." in raw:
            cands.add(raw.split(".")[0])
        if "(" in raw and ")" in raw:
            cands.add(raw.split("(")[0].strip())
        return tuple(x for x in cands if x)

    @staticmethod
    def delete_links_for_device(db: Session, device_id: int) -> None:
        db.query(Link).filter(
            or_(
                Link.source_device_id == device_id,
                Link.target_device_id == device_id,
            )
        ).delete(synchronize_session=False)

    @staticmethod
    def _normalize_link(
        a_id: int,
        a_intf: str,
        b_id: int,
        b_intf: str,
    ) -> Tuple[int, str, int, str]:
        if a_id <= b_id:
            return a_id, a_intf, b_id, b_intf
        return b_id, b_intf, a_id, a_intf

    @staticmethod
    def _find_target_device(db: Session, neighbor_name: str, mgmt_ip: str) -> Optional[Device]:
        n_name = (neighbor_name or "").strip()
        n_ip = (mgmt_ip or "").strip()

        filters = []
        if n_ip:
            filters.append(Device.ip_address == n_ip)
        if n_name:
            filters.append(func.lower(Device.hostname) == n_name.lower())
            filters.append(func.lower(Device.name) == n_name.lower())

        if filters:
            target = db.query(Device).filter(or_(*filters)).first()
        else:
            target = None

        if not target and "." in n_name:
            short_name = n_name.split(".")[0]
            target = db.query(Device).filter(
                or_(
                    func.lower(Device.hostname) == short_name.lower(),
                    func.lower(Device.name) == short_name.lower(),
                )
            ).first()

        if not target and len(n_name) >= 5:
            target = db.query(Device).filter(
                or_(
                    Device.hostname.ilike(f"{n_name}%"),
                    Device.name.ilike(f"{n_name}%"),
                )
            ).first()

        return target

    @staticmethod
    def _match_target_device(db: Session, neighbor_name: str, mgmt_ip: str) -> Tuple[Optional[Device], float, str]:
        n_name = (neighbor_name or "").strip()
        n_ip = (mgmt_ip or "").strip()

        if n_ip:
            target = db.query(Device).filter(Device.ip_address == n_ip).first()
            if target:
                return target, 0.95, "ip_match"

        name_candidates = TopologyLinkService._expand_neighbor_name_candidates(n_name)
        for cand in name_candidates:
            matches = db.query(Device).filter(
                or_(
                    func.lower(Device.hostname) == cand.lower(),
                    func.lower(Device.name) == cand.lower(),
                )
            ).limit(5).all()
            if len(matches) == 1:
                return matches[0], 0.8, "name_exact"
            if len(matches) > 1:
                ids = ",".join(str(d.id) for d in matches)
                return None, 0.0, f"ambiguous_name_exact:{ids}"

        if n_name:
            n_norm = TopologyLinkService._normalize_device_name(n_name)
            if n_norm:
                prefix = n_norm[:2]
                candidates_query = db.query(Device)
                if prefix:
                    candidates_query = candidates_query.filter(
                        or_(
                            Device.hostname.ilike(f"{prefix}%"),
                            Device.name.ilike(f"{prefix}%"),
                        )
                    )
                candidates = candidates_query.limit(200).all()
                strong = []
                for d in candidates:
                    if TopologyLinkService._normalize_device_name(d.hostname) == n_norm or TopologyLinkService._normalize_device_name(d.name) == n_norm:
                        strong.append(d)
                if len(strong) == 1:
                    return strong[0], 0.75, "name_normalized"
                if len(strong) > 1:
                    ids = ",".join(str(d.id) for d in strong[:5])
                    return None, 0.0, f"ambiguous_name_normalized:{ids}"

        if len(n_name) >= 5:
            matches = db.query(Device).filter(
                or_(
                    Device.hostname.ilike(f"{n_name}%"),
                    Device.name.ilike(f"{n_name}%"),
                )
            ).limit(5).all()
            if len(matches) == 1:
                return matches[0], 0.6, "name_prefix"
            if len(matches) > 1:
                ids = ",".join(str(d.id) for d in matches)
                return None, 0.0, f"ambiguous_name_prefix:{ids}"

        if not n_name and not n_ip:
            return None, 0.0, "missing_neighbor_identity"
        if not n_ip:
            return None, 0.0, "missing_mgmt_ip"
        return None, 0.0, "not_found"

    @staticmethod
    def refresh_links_for_device(db: Session, device: Device, neighbors: Iterable[Dict[str, Any]]) -> Dict[str, int]:
        now = datetime.now(timezone.utc)
        created = 0
        updated = 0
        skipped = 0
        site_id = getattr(device, "site_id", None)
        touched = []

        existing_links = db.query(Link).filter(
            or_(
                Link.source_device_id == device.id,
                Link.target_device_id == device.id,
            )
        ).all()
        existing_by_key = {}
        for l in existing_links:
            if l.source_device_id is None or l.target_device_id is None:
                continue
            key = (l.source_device_id, l.source_interface_name or "", l.target_device_id, l.target_interface_name or "")
            existing_by_key[key] = l

        seen = set()

        for n in neighbors or []:
            local_intf = (n.get("local_interface") or "").strip()
            remote_intf = (n.get("remote_interface") or "").strip()
            neighbor_name = n.get("neighbor_name") or ""
            mgmt_ip = n.get("mgmt_ip") or ""
            protocol = (n.get("protocol") or "UNKNOWN").strip() or "UNKNOWN"

            if not local_intf or not remote_intf:
                skipped += 1
                continue

            target, confidence, _ = TopologyLinkService._match_target_device(db, neighbor_name, mgmt_ip)
            if not target or target.id == device.id:
                skipped += 1
                continue

            src_id, src_intf, dst_id, dst_intf = TopologyLinkService._normalize_link(
                device.id, local_intf, target.id, remote_intf
            )
            key = (src_id, src_intf, dst_id, dst_intf)
            if key in seen:
                continue
            seen.add(key)

            existing = existing_by_key.get(key)
            if existing:
                prev = existing.status
                existing.status = "active"
                existing.protocol = protocol
                existing.last_seen = now
                existing.confidence = max(float(existing.confidence or 0.0), float(confidence or 0.0))
                updated += 1
                if prev != "active":
                    touched.append((src_id, src_intf, dst_id, dst_intf, protocol, "active"))
            else:
                try:
                    with db.begin_nested():
                        link = Link(
                            source_device_id=src_id,
                            source_interface_name=src_intf,
                            target_device_id=dst_id,
                            target_interface_name=dst_intf,
                            status="active",
                            link_speed="1G",
                            protocol=protocol,
                            confidence=confidence,
                            discovery_source="ssh_neighbors",
                            first_seen=now,
                            last_seen=now,
                        )
                        db.add(link)
                        db.flush()
                    created += 1
                    touched.append((src_id, src_intf, dst_id, dst_intf, protocol, "active"))
                except IntegrityError:
                    existing = db.query(Link).filter(
                        Link.source_device_id == src_id,
                        Link.source_interface_name == src_intf,
                        Link.target_device_id == dst_id,
                        Link.target_interface_name == dst_intf,
                    ).first()
                    if existing:
                        existing.status = "active"
                        existing.protocol = protocol
                        existing.last_seen = now
                        existing.confidence = max(float(existing.confidence or 0.0), float(confidence or 0.0))
                        updated += 1
                        touched.append((src_id, src_intf, dst_id, dst_intf, protocol, "active"))

        for key, link in existing_by_key.items():
            if key in seen:
                continue
            prev = link.status
            link.status = "inactive"
            if prev != "inactive":
                touched.append(
                    (
                        link.source_device_id,
                        link.source_interface_name or "",
                        link.target_device_id,
                        link.target_interface_name or "",
                        link.protocol or "UNKNOWN",
                        "down",
                    )
                )

        if touched:
            site_id = getattr(device, "site_id", None)
            for src_id, src_intf, dst_id, dst_intf, protocol, state in touched[:2000]:
                payload = {
                    "device_id": src_id,
                    "neighbor_device_id": dst_id,
                    "local_interface": src_intf,
                    "remote_interface": dst_intf,
                    "protocol": protocol,
                    "state": state,
                    "ts": now.isoformat(),
                    "source": "topology_refresh",
                    "structure_changed": True,
                    "refresh_hint": "topology",
                }
                publish_topology_event(
                    db,
                    "link_update",
                    payload,
                    site_id=site_id,
                    device_id=int(getattr(device, "id")),
                    persist=True,
                    realtime=True,
                )

            publish_topology_event(
                db,
                "topology_refresh",
                {
                    "device_id": int(getattr(device, "id")),
                    "site_id": site_id,
                    "source": "topology_refresh",
                    "scope": "l2_links",
                    "changes": {
                        "created": int(created),
                        "updated": int(updated),
                        "inactive": int(max(0, len(existing_by_key) - len(seen))),
                        "skipped": int(skipped),
                    },
                    "topology_changed": bool(created or updated or (len(existing_by_key) - len(seen)) > 0),
                    "refresh_hint": "topology",
                },
                site_id=site_id,
                device_id=int(getattr(device, "id")),
                persist=True,
                realtime=True,
            )

        return {"created": created, "updated": updated, "skipped": skipped, "inactive": max(0, len(existing_by_key) - len(seen))}

    @staticmethod
    def refresh_l3_links_for_device(
        db: Session,
        device: Device,
        ospf_neighbors: list,
        bgp_neighbors: list,
    ) -> Dict[str, int]:
        """
        L3 토폴로지 링크 갱신 (OSPF/BGP 이웃 기반).
        기존 Link 테이블에 protocol='OSPF' 또는 'BGP'로 저장합니다.
        """
        now = datetime.now(timezone.utc)
        created = 0
        updated = 0
        skipped = 0
        site_id = getattr(device, "site_id", None)
        touched = []

        # --- OSPF neighbors ---
        for n in ospf_neighbors or []:
            neighbor_ip = (n.get("neighbor_ip") or "").strip()
            neighbor_id = (n.get("neighbor_id") or "").strip()
            local_intf = (n.get("interface") or "").strip()
            state = (n.get("state") or "").strip()

            if not neighbor_ip and not neighbor_id:
                skipped += 1
                continue

            # Find target device by IP or Router-ID
            target = None
            if neighbor_ip:
                target = db.query(Device).filter(Device.ip_address == neighbor_ip).first()
            if not target and neighbor_id:
                target = db.query(Device).filter(Device.ip_address == neighbor_id).first()
            if not target:
                # Try hostname matching
                target, _, _ = TopologyLinkService._match_target_device(db, neighbor_id, neighbor_ip)

            if not target or target.id == device.id:
                skipped += 1
                continue

            src_id, src_intf, dst_id, dst_intf = TopologyLinkService._normalize_link(
                device.id, local_intf, target.id, ""
            )

            existing = db.query(Link).filter(
                Link.source_device_id == src_id,
                Link.target_device_id == dst_id,
                Link.protocol == "OSPF",
            ).first()

            if existing:
                next_state = "active" if "FULL" in state.upper() else "degraded"
                prev_state = str(existing.status or "").lower()
                existing.status = next_state
                existing.last_seen = now
                existing.source_interface_name = src_intf or existing.source_interface_name
                existing.confidence = max(float(existing.confidence or 0), 0.9)
                updated += 1
                if prev_state != next_state:
                    touched.append((src_id, src_intf, dst_id, dst_intf, "OSPF", next_state))
            else:
                try:
                    with db.begin_nested():
                        db.add(Link(
                            source_device_id=src_id,
                            source_interface_name=src_intf,
                            target_device_id=dst_id,
                            target_interface_name=dst_intf,
                            status="active" if "FULL" in state.upper() else "degraded",
                            link_speed="L3",
                            protocol="OSPF",
                            confidence=0.9,
                            discovery_source="ospf_neighbor",
                            first_seen=now,
                            last_seen=now,
                        ))
                        db.flush()
                    created += 1
                    touched.append((src_id, src_intf, dst_id, dst_intf, "OSPF", "active" if "FULL" in state.upper() else "degraded"))
                except IntegrityError:
                    updated += 1

        # --- BGP neighbors ---
        for n in bgp_neighbors or []:
            neighbor_ip = (n.get("neighbor_ip") or "").strip()
            state = (n.get("state") or "").strip()

            if not neighbor_ip:
                skipped += 1
                continue

            target = db.query(Device).filter(Device.ip_address == neighbor_ip).first()
            if not target:
                target, _, _ = TopologyLinkService._match_target_device(db, "", neighbor_ip)

            if not target or target.id == device.id:
                skipped += 1
                continue

            src_id, src_intf, dst_id, dst_intf = TopologyLinkService._normalize_link(
                device.id, "", target.id, ""
            )

            existing = db.query(Link).filter(
                Link.source_device_id == src_id,
                Link.target_device_id == dst_id,
                Link.protocol == "BGP",
            ).first()

            if existing:
                next_state = "active" if "established" in state.lower() or state.isdigit() else "degraded"
                prev_state = str(existing.status or "").lower()
                existing.status = next_state
                existing.last_seen = now
                existing.confidence = max(float(existing.confidence or 0), 0.85)
                updated += 1
                if prev_state != next_state:
                    touched.append((src_id, src_intf, dst_id, dst_intf, "BGP", next_state))
            else:
                try:
                    with db.begin_nested():
                        db.add(Link(
                            source_device_id=src_id,
                            source_interface_name="",
                            target_device_id=dst_id,
                            target_interface_name="",
                            status="active" if "established" in state.lower() or state.isdigit() else "degraded",
                            link_speed="L3",
                            protocol="BGP",
                            confidence=0.85,
                            discovery_source="bgp_neighbor",
                            first_seen=now,
                            last_seen=now,
                        ))
                        db.flush()
                    created += 1
                    touched.append((src_id, src_intf, dst_id, dst_intf, "BGP", "active" if "established" in state.lower() or state.isdigit() else "degraded"))
                except IntegrityError:
                    updated += 1

        for src_id, src_intf, dst_id, dst_intf, protocol, state in touched[:2000]:
            publish_topology_event(
                db,
                "link_update",
                {
                    "device_id": src_id,
                    "neighbor_device_id": dst_id,
                    "local_interface": src_intf,
                    "remote_interface": dst_intf,
                    "protocol": protocol,
                    "state": state,
                    "ts": now.isoformat(),
                    "source": "l3_topology_refresh",
                    "structure_changed": True,
                    "refresh_hint": "topology",
                },
                site_id=site_id,
                device_id=int(getattr(device, "id")),
                persist=True,
                realtime=True,
            )

        if created or updated:
            publish_topology_event(
                db,
                "topology_refresh",
                {
                    "device_id": int(getattr(device, "id")),
                    "site_id": site_id,
                    "source": "l3_topology_refresh",
                    "scope": "l3_links",
                    "changes": {
                        "created": int(created),
                        "updated": int(updated),
                        "skipped": int(skipped),
                    },
                    "topology_changed": True,
                    "refresh_hint": "topology",
                },
                site_id=site_id,
                device_id=int(getattr(device, "id")),
                persist=True,
                realtime=True,
            )

        return {"created": created, "updated": updated, "skipped": skipped}

