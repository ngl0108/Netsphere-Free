from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class CompileResult:
    ir: List[Dict[str, Any]]
    device_ids: List[int]
    errors: List[str]
    errors_by_node_id: Dict[str, List[str]]


def _push_err(errors_by_node_id: Dict[str, List[str]], node_id: str, msg: str) -> None:
    errors_by_node_id.setdefault(node_id, []).append(msg)


def _to_int(v: Any) -> int | None:
    try:
        return int(v)
    except Exception:
        return None


def compile_graph_to_ir(graph: Dict[str, Any]) -> CompileResult:
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []

    errors: List[str] = []
    errors_by_node_id: Dict[str, List[str]] = {}

    by_type: Dict[str, List[Dict[str, Any]]] = {}
    for n in nodes:
        t = n.get("type")
        if not t:
            continue
        by_type.setdefault(t, []).append(n)

    target_nodes = by_type.get("target") or []
    if len(target_nodes) == 0:
        errors.append("Target 블록이 필요합니다.")
        device_ids: List[int] = []
    else:
        data = (target_nodes[0].get("data") or {})
        ids = data.get("device_ids")
        if not isinstance(ids, list) or len(ids) == 0:
            _push_err(errors_by_node_id, target_nodes[0].get("id") or "target", "대상 장비를 1대 이상 선택해야 합니다.")
            device_ids = []
        else:
            device_ids = []
            for x in ids:
                xi = _to_int(x)
                if xi is not None:
                    device_ids.append(xi)
            if len(device_ids) == 0:
                _push_err(errors_by_node_id, target_nodes[0].get("id") or "target", "대상 장비 ID가 올바르지 않습니다.")

    for e in edges:
        if e.get("source") and e.get("target") and e.get("source") == e.get("target"):
            errors.append("자기 자신으로 연결된 엣지가 있습니다.")
            break

    def validate_vlan(node: Dict[str, Any]) -> Dict[str, Any] | None:
        nid = node.get("id") or "vlan"
        d = node.get("data") or {}
        vid = _to_int(d.get("vlan_id"))
        if vid is None or vid < 1 or vid > 4094:
            _push_err(errors_by_node_id, nid, "VLAN ID는 1~4094 정수여야 합니다.")
        name = str(d.get("name") or "").strip()
        if not name:
            _push_err(errors_by_node_id, nid, "VLAN Name이 필요합니다.")
        return {"type": "vlan", "vlan_id": vid, "name": name, "svi_ip": d.get("svi_ip") or "", "vrf": d.get("vrf") or "", "dhcp_relay": d.get("dhcp_relay") or ""}

    def validate_interface(node: Dict[str, Any]) -> Dict[str, Any] | None:
        nid = node.get("id") or "interface"
        d = node.get("data") or {}
        ports = str(d.get("ports") or "").strip()
        if not ports:
            _push_err(errors_by_node_id, nid, "Ports가 필요합니다.")
        admin_state = str(d.get("admin_state") or "up").strip()
        if admin_state not in ("up", "down"):
            _push_err(errors_by_node_id, nid, "Admin state는 up/down이어야 합니다.")
        mode = str(d.get("mode") or "access").strip()
        if mode not in ("access", "trunk"):
            _push_err(errors_by_node_id, nid, "Mode는 access/trunk이어야 합니다.")
        access_vlan = _to_int(d.get("access_vlan"))
        native_vlan = _to_int(d.get("native_vlan"))
        allowed_vlans = str(d.get("allowed_vlans") or "").strip()
        if mode == "access":
            if access_vlan is None or access_vlan < 1 or access_vlan > 4094:
                _push_err(errors_by_node_id, nid, "Access VLAN은 1~4094 정수여야 합니다.")
        if mode == "trunk":
            if native_vlan is None or native_vlan < 1 or native_vlan > 4094:
                _push_err(errors_by_node_id, nid, "Native VLAN은 1~4094 정수여야 합니다.")
            if not allowed_vlans:
                _push_err(errors_by_node_id, nid, "Allowed VLANs가 필요합니다.")
        return {
            "type": "interface",
            "ports": ports,
            "description": str(d.get("description") or "").strip(),
            "admin_state": admin_state,
            "mode": mode,
            "access_vlan": access_vlan,
            "native_vlan": native_vlan,
            "allowed_vlans": allowed_vlans,
        }

    def validate_l2_safety(node: Dict[str, Any]) -> Dict[str, Any] | None:
        nid = node.get("id") or "l2_safety"
        d = node.get("data") or {}
        ports = str(d.get("ports") or "").strip()
        if not ports:
            _push_err(errors_by_node_id, nid, "Ports가 필요합니다.")
        return {
            "type": "l2_safety",
            "ports": ports,
            "portfast": bool(d.get("portfast")),
            "bpduguard": bool(d.get("bpduguard")),
            "storm_control": str(d.get("storm_control") or "").strip(),
        }

    def validate_acl(node: Dict[str, Any]) -> Dict[str, Any] | None:
        nid = node.get("id") or "acl"
        d = node.get("data") or {}
        name = str(d.get("name") or "").strip()
        if not name:
            _push_err(errors_by_node_id, nid, "ACL Name이 필요합니다.")
        entries = d.get("entries")
        if not isinstance(entries, list) or len(entries) == 0:
            _push_err(errors_by_node_id, nid, "ACL entries가 필요합니다.")
            entries = []
        normalized = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            normalized.append(
                {
                    "action": str(e.get("action") or "permit").strip(),
                    "proto": str(e.get("proto") or "ip").strip(),
                    "src": str(e.get("src") or "any").strip(),
                    "dst": str(e.get("dst") or "any").strip(),
                    "dport": str(e.get("dport") or "").strip(),
                }
            )
        return {"type": "acl", "name": name, "entries": normalized}

    def validate_global(node: Dict[str, Any]) -> Dict[str, Any] | None:
        nid = node.get("id") or "global"
        d = node.get("data") or {}
        
        # Helper to ensure list of dicts or strings
        def _list(k, key_in_item=None):
            val = d.get(k)
            if not isinstance(val, dict): return [] # expect wrapper obj usually
            items = val.get(key_in_item + "s") if key_in_item else val.get("servers")
            return items if isinstance(items, list) else []

        # SNMP
        snmp = d.get("snmp") or {}
        snmp_comms = []
        if isinstance(snmp.get("communities"), list):
            for c in snmp["communities"]:
                if isinstance(c, dict) and c.get("name"):
                    snmp_comms.append({"name": str(c["name"]), "mode": str(c.get("mode") or "ro")})
        
        # NTP
        ntp_servers = []
        ntp = d.get("ntp") or {}
        if isinstance(ntp.get("servers"), list):
            ntp_servers = [str(s) for s in ntp["servers"] if s]

        # Logging
        log_servers = []
        logging = d.get("logging") or {}
        if isinstance(logging.get("servers"), list):
            log_servers = [str(s) for s in logging["servers"] if s]
        
        # AAA
        aaa_servers = []
        aaa = d.get("aaa") or {}
        if isinstance(aaa.get("tacacs_servers"), list):
            for s in aaa["tacacs_servers"]:
                if isinstance(s, dict) and s.get("ip"):
                    aaa_servers.append({"name": str(s.get("name") or "TACACS"), "ip": str(s["ip"]), "key": str(s.get("key") or "")})

        # Users
        users = []
        raw_users = d.get("users")
        if isinstance(raw_users, list):
            for u in raw_users:
                if isinstance(u, dict) and u.get("username"):
                    users.append({"username": str(u["username"]), "privilege": _to_int(u.get("privilege")) or 15, "secret": str(u.get("secret") or "")})

        return {
            "type": "global",
            "hostname": str(d.get("hostname") or "").strip(),
            "domain_name": str(d.get("domain_name") or "").strip(),
            "banner": str(d.get("banner") or "").strip(),
            "snmp": {"communities": snmp_comms, "trap_server": str(snmp.get("trap_server") or "").strip()},
            "ntp": {"servers": ntp_servers},
            "logging": {"servers": log_servers, "level": str(logging.get("level") or "informational")},
            "aaa": {"tacacs_servers": aaa_servers},
            "users": users,
        }

    def validate_ospf(node: Dict[str, Any]) -> Dict[str, Any] | None:
        nid = node.get("id") or "ospf"
        d = node.get("data") or {}
        process_id = _to_int(d.get("process_id"))
        if process_id is None or process_id < 1:
            _push_err(errors_by_node_id, nid, "OSPF Process ID가 필요합니다 (1 이상).")
        networks = d.get("networks")
        if not isinstance(networks, list) or len(networks) == 0:
            _push_err(errors_by_node_id, nid, "OSPF network가 1개 이상 필요합니다.")
            networks = []
        normalized_nets = []
        for net in networks:
            if not isinstance(net, dict):
                continue
            normalized_nets.append({
                "ip": str(net.get("ip") or "").strip(),
                "wildcard": str(net.get("wildcard") or "").strip(),
                "area": str(net.get("area") or "0").strip(),
            })
        return {"type": "ospf", "process_id": process_id, "networks": normalized_nets}

    def validate_route(node: Dict[str, Any]) -> Dict[str, Any] | None:
        nid = node.get("id") or "route"
        d = node.get("data") or {}
        destination = str(d.get("destination") or "").strip()
        mask = str(d.get("mask") or "").strip()
        next_hop = str(d.get("next_hop") or "").strip()
        if not destination:
            _push_err(errors_by_node_id, nid, "Destination이 필요합니다.")
        if not next_hop:
            _push_err(errors_by_node_id, nid, "Next Hop이 필요합니다.")
        return {"type": "route", "destination": destination, "mask": mask, "next_hop": next_hop}

    order: List[Tuple[str, Any]] = [
        ("vlan", validate_vlan),
        ("interface", validate_interface),
        ("l2_safety", validate_l2_safety),
        ("acl", validate_acl),
        ("ospf", validate_ospf),
        ("route", validate_route),
        ("global", validate_global),
    ]

    ir: List[Dict[str, Any]] = []
    for t, fn in order:
        for node in by_type.get(t) or []:
            ir.append(fn(node))

    if errors_by_node_id:
        errors.append("그래프에 오류가 있습니다.")

    return CompileResult(ir=ir, device_ids=device_ids, errors=errors, errors_by_node_id=errors_by_node_id)

