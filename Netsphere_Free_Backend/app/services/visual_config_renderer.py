from __future__ import annotations

import ipaddress
from typing import Any, Dict, List


def _cidr_to_mask(ip: str) -> str | None:
    try:
        iface = ipaddress.ip_interface(ip)
        return f"{iface.ip} {iface.network.netmask}"
    except Exception:
        return None


def _normalize_device_type(device_type: str) -> str:
    s = (device_type or "").lower()
    if "junos" in s or "juniper" in s:
        return "junos"
    if "dasan" in s or "dasan_nos" in s:
        return "dasan_nos"
    if "ubiquoss" in s or "ubiquoss_l2" in s:
        return "ubiquoss_l2"
    if "handream" in s or "handream_sg" in s:
        return "handream_sg"
    if "soltech" in s or "soltech_switch" in s:
        return "cisco_like"
    if "coreedge" in s or "coreedge_switch" in s:
        return "cisco_like"
    if "nst" in s or "nst_switch" in s:
        return "cisco_like"
    if "huawei" in s or "vrp" in s:
        return "cisco_like"
    if "extreme" in s or "exos" in s:
        return "cisco_like"
    if "hp" in s or "procurve" in s or "aruba" in s:
        return "cisco_like"
    if "dell" in s or "os10" in s or "force10" in s:
        return "cisco_like"
    if "nxos" in s:
        return "cisco_like"
    if "eos" in s or "arista" in s:
        return "cisco_like"
    if "ios" in s or "cisco" in s:
        return "cisco_like"
    return "cisco_like"


def render_ir_to_commands(ir: List[Dict[str, Any]], device_type: str) -> List[str]:
    kind = _normalize_device_type(device_type)
    if kind == "junos":
        return _render_junos(ir)
    if kind == "dasan_nos":
        return _render_dasan_nos(ir)
    if kind == "ubiquoss_l2":
        return _render_ubiquoss_l2(ir)
    if kind == "handream_sg":
        return _render_handream_sg(ir)
    return _render_cisco_like(ir)


def render_ir_to_rollback_commands(ir: List[Dict[str, Any]], device_type: str) -> List[str]:
    kind = _normalize_device_type(device_type)
    if kind == "junos":
        return _render_junos_rollback(ir)
    if kind == "dasan_nos":
        return _render_dasan_nos_rollback(ir)
    if kind == "ubiquoss_l2":
        return _render_ubiquoss_l2_rollback(ir)
    if kind == "handream_sg":
        return _render_handream_sg_rollback(ir)
    return _render_cisco_like_rollback(ir)


# ── Cisco-like variant (shared by Cisco/Dasan/Ubiquoss/Handream) ──

def _render_cisco_like_variant(
    ir: List[Dict[str, Any]],
    svi_interface_format: str = "Vlan{vid}",
    trunk_allowed_mode: str = "set",
    portfast_cmd: str = "spanning-tree portfast",
    bpduguard_cmd: str = "spanning-tree bpduguard enable",
    logging_prefix: str = "logging host",
    banner_format: str = "banner motd ^{msg}^",
) -> List[str]:
    cmds: List[str] = []

    for x in ir:
        t = x.get("type")

        if t == "global":
            hn = x.get("hostname")
            dn = x.get("domain_name")
            if hn: cmds.append(f"hostname {hn}")
            if dn: cmds.append(f"ip domain-name {dn}")
            
            ban = x.get("banner")
            if ban: cmds.append(banner_format.format(msg=ban))

            snmp = x.get("snmp") or {}
            for c in (snmp.get("communities") or []):
                cmds.append(f"snmp-server community {c['name']} {c['mode']}")
            if snmp.get("trap_server"):
                cmds.append(f"snmp-server host {snmp['trap_server']}")

            ntp = x.get("ntp") or {}
            for s in (ntp.get("servers") or []):
                cmds.append(f"ntp server {s}")

            logging = x.get("logging") or {}
            for s in (logging.get("servers") or []):
                cmds.append(f"{logging_prefix} {s}")
            if logging.get("level"):
                cmds.append(f"logging trap {logging['level']}")

            aaa = x.get("aaa") or {}
            ts_list = aaa.get("tacacs_servers") or []
            if ts_list:
                for ts in ts_list:
                    cmds.append(f"tacacs server {ts['name']}")
                    cmds.append(f" address ipv4 {ts['ip']}")
                    if ts.get("key"): cmds.append(f" key {ts['key']}")
                    cmds.append(" exit")
                cmds.append("aaa new-model")
                cmds.append("aaa authentication login default group tacacs+ local")
                cmds.append("aaa authorization exec default group tacacs+ local")

            users = x.get("users") or []
            for u in users:
                line = f"username {u['username']} privilege {u['privilege']}"
                if u.get("secret"): line += f" secret {u['secret']}"
                cmds.append(line)

        elif t == "vlan":
            vid = x.get("vlan_id")
            name = (x.get("name") or "").strip()
            if not vid:
                continue
            cmds.append(f"vlan {vid}")
            if name:
                cmds.append(f" name {name}")
            cmds.append("exit")
            svi_ip = (x.get("svi_ip") or "").strip()
            vrf = (x.get("vrf") or "").strip()
            dhcp = (x.get("dhcp_relay") or "").strip()
            if svi_ip or vrf or dhcp:
                cmds.append(f"interface {svi_interface_format.format(vid=vid)}")
                if vrf:
                    cmds.append(f" vrf forwarding {vrf}")
                if svi_ip:
                    mask = _cidr_to_mask(svi_ip)
                    cmds.append(f" ip address {mask or svi_ip}")
                if dhcp:
                    cmds.append(f" ip helper-address {dhcp}")
                cmds.append("exit")

        elif t == "interface":
            ports = (x.get("ports") or "").strip()
            if not ports:
                continue
            desc = (x.get("description") or "").strip()
            admin_state = (x.get("admin_state") or "up").strip()
            mode = (x.get("mode") or "access").strip()
            access_vlan = x.get("access_vlan")
            native_vlan = x.get("native_vlan")
            allowed_vlans = (x.get("allowed_vlans") or "").strip()
            for p in [pp.strip() for pp in ports.split(",") if pp.strip()]:
                cmds.append(f"interface {p}")
                if desc:
                    cmds.append(f" description {desc}")
                cmds.append(" shutdown" if admin_state == "down" else " no shutdown")
                if mode == "access":
                    cmds.append(" switchport")
                    cmds.append(" switchport mode access")
                    if access_vlan:
                        cmds.append(f" switchport access vlan {access_vlan}")
                elif mode == "trunk":
                    cmds.append(" switchport")
                    cmds.append(" switchport mode trunk")
                    if native_vlan:
                        cmds.append(f" switchport trunk native vlan {native_vlan}")
                    if allowed_vlans:
                        if trunk_allowed_mode == "add":
                            cmds.append(f" switchport trunk allowed vlan add {allowed_vlans}")
                        else:
                            cmds.append(f" switchport trunk allowed vlan {allowed_vlans}")
                cmds.append("exit")

        elif t == "l2_safety":
            ports = (x.get("ports") or "").strip()
            if not ports:
                continue
            for p in [pp.strip() for pp in ports.split(",") if pp.strip()]:
                cmds.append(f"interface {p}")
                if x.get("portfast"):
                    cmds.append(f" {portfast_cmd}")
                if x.get("bpduguard"):
                    cmds.append(f" {bpduguard_cmd}")
                storm = (x.get("storm_control") or "").strip()
                if storm:
                    cmds.append(f" storm-control {storm}")
                cmds.append("exit")

        elif t == "acl":
            name = (x.get("name") or "").strip()
            entries = x.get("entries") or []
            if not name:
                continue
            cmds.append(f"ip access-list extended {name}")
            for e in entries:
                action = (e.get("action") or "permit").strip()
                proto = (e.get("proto") or "ip").strip()
                src = (e.get("src") or "any").strip()
                dst = (e.get("dst") or "any").strip()
                dport = (e.get("dport") or "").strip()
                line = f" {action} {proto} {src} {dst}"
                if dport:
                    line = f"{line} eq {dport}"
                cmds.append(line)
            cmds.append("exit")

        elif t == "ospf":
            pid = x.get("process_id") or 1
            networks = x.get("networks") or []
            cmds.append(f"router ospf {pid}")
            for net in networks:
                ip = (net.get("ip") or "").strip()
                wc = (net.get("wildcard") or "").strip()
                area = (net.get("area") or "0").strip()
                if ip and wc:
                    cmds.append(f" network {ip} {wc} area {area}")
            cmds.append("exit")

        elif t == "route":
            dest = (x.get("destination") or "").strip()
            mask = (x.get("mask") or "").strip()
            nh = (x.get("next_hop") or "").strip()
            if dest and nh:
                cmds.append(f"ip route {dest} {mask} {nh}")

    return cmds


def _render_cisco_like_rollback_variant(
    ir: List[Dict[str, Any]],
    svi_interface_format: str = "Vlan{vid}",
    portfast_cmd: str = "spanning-tree portfast",
    bpduguard_cmd: str = "spanning-tree bpduguard enable",
) -> List[str]:
    cmds: List[str] = []
    for x in ir:
        t = x.get("type")
        if t == "l2_safety":
            ports = (x.get("ports") or "").strip()
            if not ports:
                continue
            for p in [pp.strip() for pp in ports.split(",") if pp.strip()]:
                cmds.append(f"interface {p}")
                cmds.append(f" no {portfast_cmd}")
                cmds.append(f" no {bpduguard_cmd}")
                cmds.append(" no storm-control")
                cmds.append("exit")
        elif t == "interface":
            ports = (x.get("ports") or "").strip()
            if not ports:
                continue
            for p in [pp.strip() for pp in ports.split(",") if pp.strip()]:
                cmds.append(f"interface {p}")
                cmds.append(" no description")
                cmds.append(" no switchport access vlan")
                cmds.append(" no switchport trunk native vlan")
                cmds.append(" no switchport trunk allowed vlan")
                cmds.append(" no switchport mode")
                cmds.append("exit")
        elif t == "acl":
            name = (x.get("name") or "").strip()
            if name:
                cmds.append(f"no ip access-list extended {name}")
        elif t == "vlan":
            vid = x.get("vlan_id")
            if vid:
                cmds.append(f"no interface {svi_interface_format.format(vid=vid)}")
                cmds.append(f"no vlan {vid}")
        elif t == "ospf":
            pid = x.get("process_id") or 1
            cmds.append(f"no router ospf {pid}")
        elif t == "route":
            dest = (x.get("destination") or "").strip()
            mask = (x.get("mask") or "").strip()
            nh = (x.get("next_hop") or "").strip()
            if dest and nh:
                cmds.append(f"no ip route {dest} {mask} {nh}")
    return cmds


# ── Vendor wrappers ──

def _render_cisco_like(ir): return _render_cisco_like_variant(ir)
def _render_cisco_like_rollback(ir): return _render_cisco_like_rollback_variant(ir)

def _render_dasan_nos(ir):
    return _render_cisco_like_variant(ir, svi_interface_format="vlan {vid}", trunk_allowed_mode="set",
                                     portfast_cmd="spanning-tree portfast", bpduguard_cmd="spanning-tree bpduguard enable",
                                     logging_prefix="syslog host", banner_format="banner login \"{msg}\"")

def _render_dasan_nos_rollback(ir):
    return _render_cisco_like_rollback_variant(ir, svi_interface_format="vlan {vid}",
                                              portfast_cmd="spanning-tree portfast", bpduguard_cmd="spanning-tree bpduguard enable")

def _render_ubiquoss_l2(ir):
    return _render_cisco_like_variant(ir, svi_interface_format="vlan {vid}", trunk_allowed_mode="add",
                                     portfast_cmd="spanning-tree portfast edge", bpduguard_cmd="spanning-tree bpduguard",
                                     logging_prefix="logging host", banner_format="banner motd \"{msg}\"")

def _render_ubiquoss_l2_rollback(ir):
    return _render_cisco_like_rollback_variant(ir, svi_interface_format="vlan {vid}",
                                              portfast_cmd="spanning-tree portfast edge", bpduguard_cmd="spanning-tree bpduguard")

def _render_handream_sg(ir):
    return _render_cisco_like_variant(ir, svi_interface_format="vlan {vid}", trunk_allowed_mode="set",
                                     portfast_cmd="spanning-tree portfast edge", bpduguard_cmd="spanning-tree bpduguard enable",
                                     logging_prefix="logging host", banner_format="banner motd \"{msg}\"")

def _render_handream_sg_rollback(ir):
    return _render_cisco_like_rollback_variant(ir, svi_interface_format="vlan {vid}",
                                              portfast_cmd="spanning-tree portfast edge", bpduguard_cmd="spanning-tree bpduguard enable")


# ── Juniper JunOS ──

def _render_junos(ir: List[Dict[str, Any]]) -> List[str]:
    cmds: List[str] = []
    for x in ir:
        t = x.get("type")
        if t == "global":
            hn = x.get("hostname")
            if hn: cmds.append(f"set system host-name {hn}")
            dn = x.get("domain_name")
            if dn: cmds.append(f"set system domain-name {dn}")
            ban = x.get("banner")
            if ban: cmds.append(f"set system login message \"{ban}\"")

            snmp = x.get("snmp") or {}
            for c in (snmp.get("communities") or []):
                mode = "authorization read-only" if c['mode'] == 'ro' else "authorization read-write"
                cmds.append(f"set snmp community {c['name']} {mode}")
            if snmp.get("trap_server"):
                cmds.append(f"set snmp trap-group generic targets {snmp['trap_server']}")

            ntp = x.get("ntp") or {}
            for s in (ntp.get("servers") or []):
                cmds.append(f"set system ntp server {s}")
            
            logging = x.get("logging") or {}
            for s in (logging.get("servers") or []):
                cmds.append(f"set system syslog host {s} any any")
            
            aaa = x.get("aaa") or {}
            ts_list = aaa.get("tacacs_servers") or []
            if ts_list:
                for ts in ts_list:
                    cmds.append(f"set system tacplus-server {ts['ip']} secret {ts['key']}")
                cmds.append("set system authentication-order [ tacplus password ]")

            users = x.get("users") or []
            for u in users:
                cls = "super-user" if u['privilege'] >= 15 else "operator"
                cmds.append(f"set system login user {u['username']} class {cls} authentication plain-text-password-value {u.get('secret')}")

        elif t == "vlan":
            vid = x.get("vlan_id")
            name = (x.get("name") or "").strip() or f"vlan-{vid}"
            if not vid:
                continue
            cmds.append(f"set vlans {name} vlan-id {vid}")
            svi_ip = (x.get("svi_ip") or "").strip()
            if svi_ip:
                cmds.append(f"set interfaces irb unit {vid} family inet address {svi_ip}")
                cmds.append(f"set vlans {name} l3-interface irb.{vid}")
        elif t == "interface":
            ports = (x.get("ports") or "").strip()
            if not ports:
                continue
            mode = (x.get("mode") or "access").strip()
            access_vlan = x.get("access_vlan")
            native_vlan = x.get("native_vlan")
            allowed_vlans = (x.get("allowed_vlans") or "").strip()
            desc = (x.get("description") or "").strip()
            admin_state = (x.get("admin_state") or "up").strip()
            for p in [pp.strip() for pp in ports.split(",") if pp.strip()]:
                if desc:
                    cmds.append(f"set interfaces {p} description \"{desc}\"")
                if admin_state == "down":
                    cmds.append(f"set interfaces {p} disable")
                else:
                    cmds.append(f"delete interfaces {p} disable")
                if mode == "access" and access_vlan:
                    cmds.append(f"set interfaces {p} unit 0 family ethernet-switching interface-mode access")
                    cmds.append(f"set interfaces {p} unit 0 family ethernet-switching vlan members {access_vlan}")
                elif mode == "trunk":
                    cmds.append(f"set interfaces {p} unit 0 family ethernet-switching interface-mode trunk")
                    if allowed_vlans:
                        cmds.append(f"set interfaces {p} unit 0 family ethernet-switching vlan members [{allowed_vlans}]")
                    if native_vlan:
                        cmds.append(f"set interfaces {p} unit 0 family ethernet-switching native-vlan-id {native_vlan}")
        elif t == "ospf":
            pid = x.get("process_id") or 1
            networks = x.get("networks") or []
            for net in networks:
                ip = (net.get("ip") or "").strip()
                area = (net.get("area") or "0").strip()
                if ip:
                    cmds.append(f"set protocols ospf area {area} interface {ip}")
        elif t == "route":
            dest = (x.get("destination") or "").strip()
            mask = (x.get("mask") or "").strip()
            nh = (x.get("next_hop") or "").strip()
            if dest and nh:
                cmds.append(f"set routing-options static route {dest}/{mask} next-hop {nh}")
    return cmds


def _render_junos_rollback(ir: List[Dict[str, Any]]) -> List[str]:
    cmds: List[str] = []
    for x in ir:
        t = x.get("type")
        if t == "interface":
            ports = (x.get("ports") or "").strip()
            if not ports:
                continue
            for p in [pp.strip() for pp in ports.split(",") if pp.strip()]:
                cmds.append(f"delete interfaces {p} description")
                cmds.append(f"delete interfaces {p} unit 0 family ethernet-switching")
                cmds.append(f"delete interfaces {p} disable")
        elif t == "vlan":
            vid = x.get("vlan_id")
            name = (x.get("name") or "").strip()
            if not vid:
                continue
            if name:
                cmds.append(f"delete vlans {name}")
            cmds.append(f"delete interfaces irb unit {vid}")
        elif t == "ospf":
            networks = x.get("networks") or []
            for net in networks:
                ip = (net.get("ip") or "").strip()
                area = (net.get("area") or "0").strip()
                if ip:
                    cmds.append(f"delete protocols ospf area {area} interface {ip}")
        elif t == "route":
            dest = (x.get("destination") or "").strip()
            mask = (x.get("mask") or "").strip()
            if dest:
                cmds.append(f"delete routing-options static route {dest}/{mask}")
    return cmds
