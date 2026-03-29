import re
from datetime import datetime, timedelta
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.device import Device, Interface, ConfigBackup, Link, EventLog
from app.models.settings import SystemSetting
from app.models.endpoint import Endpoint, EndpointAttachment
from app.services.oui_service import OUIService
from app.services.ssh_service import DeviceConnection, DeviceInfo
from app.services.topology_link_service import TopologyLinkService
from app.services.entity_mib_service import EntityMibService
from app.services.inventory_ssh_service import InventorySshService
from app.services.snmp_l2_service import SnmpL2Service
from app.services.snmp_service import SnmpManager
from app.services.capability_profile_service import CapabilityProfileService
from app.services.device_support_policy_service import DeviceSupportPolicyService
from app.services.discovery_hint_cache_service import DiscoveryHintCacheService


def parse_uptime_seconds(uptime_value) -> str:
    if not uptime_value:
        return "0d 0h 0m"

    if isinstance(uptime_value, str) and ("day" in uptime_value or "hour" in uptime_value):
        return uptime_value

    try:
        val = float(uptime_value)
        if val > 10000000:
            val = val / 100
        td = timedelta(seconds=val)
        return f"{td.days}d {td.seconds // 3600}h {(td.seconds % 3600) // 60}m"
    except (ValueError, TypeError):
        return str(uptime_value)


class DeviceSyncService:
    @staticmethod
    def _acquire_device_sync_lock(db: Session, device_id: int, ttl_seconds: int = 90) -> bool:
        now = datetime.utcnow()
        lock_until = now + timedelta(seconds=int(ttl_seconds))
        key = f"device_sync_lock:{int(device_id)}"
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting and setting.value:
            try:
                current = datetime.fromisoformat(setting.value)
                if current > now:
                    return False
            except Exception:
                pass
        if not setting:
            setting = SystemSetting(key=key, value=lock_until.isoformat(), description=key, category="system")
        else:
            setting.value = lock_until.isoformat()
        db.add(setting)
        db.commit()
        return True

    @staticmethod
    def sync_device(db: Session, device_id: int) -> Dict[str, Any]:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            return {"status": "not_found", "message": "Device not found"}

        support_policy = DeviceSupportPolicyService.evaluate_device(db, device)
        if not bool((support_policy.get("features") or {}).get("sync", False)):
            return {
                "status": "skipped",
                "message": "vendor_support_policy_blocked:sync",
                "support_policy": support_policy,
            }

        policy = CapabilityProfileService.get_policy_for_device(db, device)
        if bool(policy.get("read_only", False)):
            return {
                "status": "skipped",
                "message": "capability_read_only",
                "policy": policy,
            }
        if not CapabilityProfileService.allows_protocol(db, device, "ssh"):
            return {
                "status": "skipped",
                "message": "capability_protocol_blocked:ssh",
                "policy": policy,
            }

        dev_info = DeviceInfo(
            host=device.ip_address,
            username=device.ssh_username or "admin",
            password=device.ssh_password,
            secret=device.enable_password,
            port=int(device.ssh_port or 22),
            device_type=device.device_type or "cisco_ios",
        )
        conn = DeviceConnection(dev_info)

        if conn.connect():
            device.status = "online"
            device.reachability_status = "reachable"
            device.last_seen = datetime.now()

            try:
                facts = conn.get_facts()
                raw_config = conn.get_running_config()
                neighbors = conn.get_neighbors()
                interfaces = conn.get_detailed_interfaces()
                parsed_data = {"interfaces": interfaces}

                is_wlc_model = "9800" in str(facts.get("model", "")) or "Wireless" in str(facts.get("os_version", ""))
                if is_wlc_model and not hasattr(conn.driver, "get_wireless_summary"):
                    try:
                        ap_parsed = conn.driver.connection.send_command("show ap summary", use_textfsm=True)
                        if isinstance(ap_parsed, list):
                            total_clients = 0
                            client_out = conn.driver.connection.send_command("show wireless client summary")
                            client_match = re.search(r"Number of Clients\s*:\s*(\d+)", client_out, re.IGNORECASE)
                            if client_match:
                                total_clients = int(client_match.group(1))

                            up_aps = 0
                            normalized_aps = []
                            for ap in ap_parsed:
                                ap["name"] = ap.get("name") or ap.get("ap_name") or "Unknown"
                                ap["model"] = ap.get("model") or ap.get("ap_model") or "N/A"
                                ap["status"] = ap.get("status") or ap.get("state") or "Unknown"
                                ap["uptime"] = ap.get("uptime") or ap.get("up_time") or "N/A"
                                ap["serial_number"] = ap.get("serial_number") or ap.get("serial") or "N/A"
                                ap["ip_address"] = ap.get("ip_address") or "N/A"

                                status_lower = str(ap["status"]).lower()
                                if "up" in status_lower or "reg" in status_lower:
                                    up_aps += 1
                                    ap["status"] = "online"
                                else:
                                    ap["status"] = "offline"

                                normalized_aps.append(ap)

                            wlan_out = conn.driver.connection.send_command("show wlan summary")
                            wlans = []
                            for wl in wlan_out.splitlines():
                                m = re.match(r"^\s*(\d+)\s+(\S+)\s+(\S+)\s+(UP|DISABLED|DOWN|ENABLED)", wl, re.IGNORECASE)
                                if m:
                                    wlans.append(
                                        {
                                            "id": m.group(1),
                                            "profile": m.group(2),
                                            "ssid": m.group(3),
                                            "status": "UP"
                                            if "UP" in m.group(4).upper() or "ENABLED" in m.group(4).upper()
                                            else "DOWN",
                                        }
                                    )

                            parsed_data["wireless"] = {
                                "total_aps": len(normalized_aps),
                                "up_aps": up_aps,
                                "down_aps": len(normalized_aps) - up_aps,
                                "total_clients": total_clients,
                                "ap_list": normalized_aps,
                                "wlan_summary": wlans,
                            }
                    except Exception:
                        pass
                elif hasattr(conn.driver, "get_wireless_summary"):
                    parsed_data["wireless"] = conn.driver.get_wireless_summary()

                device.model = facts.get("model", "Unknown")
                device.os_version = facts.get("os_version", "Unknown")
                device.serial_number = facts.get("serial_number", None)
                device.hostname = facts.get("hostname", device.name)
                device.uptime = parse_uptime_seconds(facts.get("uptime", 0))
                device.latest_parsed_data = parsed_data
                try:
                    def _norm_mac(v):
                        if v is None:
                            return None
                        if isinstance(v, (bytes, bytearray)):
                            b = bytes(v)
                            if len(b) < 6:
                                return None
                            s = b[:6].hex()
                            return f"{s[0:4]}.{s[4:8]}.{s[8:12]}".lower()
                        s0 = str(v).strip()
                        if not s0:
                            return None
                        s = s0.lower().replace("0x", "")
                        s = re.sub(r"[^0-9a-f]", "", s)
                        if len(s) < 12:
                            return None
                        s = s[:12]
                        return f"{s[0:4]}.{s[4:8]}.{s[8:12]}".lower()

                    if device.ip_address and device.snmp_community:
                        snmp = SnmpManager(
                            device.ip_address,
                            device.snmp_community,
                            port=int(getattr(device, "snmp_port", None) or 161),
                            version=str(getattr(device, "snmp_version", None) or "v2c"),
                            v3_username=getattr(device, "snmp_v3_username", None),
                            v3_security_level=getattr(device, "snmp_v3_security_level", None),
                            v3_auth_proto=getattr(device, "snmp_v3_auth_proto", None),
                            v3_auth_key=getattr(device, "snmp_v3_auth_key", None),
                            v3_priv_proto=getattr(device, "snmp_v3_priv_proto", None),
                            v3_priv_key=getattr(device, "snmp_v3_priv_key", None),
                        )
                        mac_probe = snmp.get_oids(["1.3.6.1.2.1.17.1.1.0"]) or {}
                        mac = _norm_mac(mac_probe.get("1.3.6.1.2.1.17.1.1.0"))
                        if mac:
                            device.mac_address = mac
                except Exception:
                    pass
                try:
                    mac_aliases = set()
                    if getattr(device, "mac_address", None):
                        mac_aliases.add(str(device.mac_address).strip().lower())
                    for iface in parsed_data.get("interfaces", []) or []:
                        if not isinstance(iface, dict):
                            continue
                        m = _norm_mac(iface.get("mac_address") or iface.get("hardware_address"))
                        if m:
                            mac_aliases.add(m)
                    if device.ip_address and device.snmp_community:
                        snmp2 = SnmpManager(
                            device.ip_address,
                            device.snmp_community,
                            port=int(getattr(device, "snmp_port", None) or 161),
                            version=str(getattr(device, "snmp_version", None) or "v2c"),
                            v3_username=getattr(device, "snmp_v3_username", None),
                            v3_security_level=getattr(device, "snmp_v3_security_level", None),
                            v3_auth_proto=getattr(device, "snmp_v3_auth_proto", None),
                            v3_auth_key=getattr(device, "snmp_v3_auth_key", None),
                            v3_priv_proto=getattr(device, "snmp_v3_priv_proto", None),
                            v3_priv_key=getattr(device, "snmp_v3_priv_key", None),
                        )
                        for m in snmp2.get_mac_aliases() or []:
                            mm = _norm_mac(m)
                            if mm:
                                mac_aliases.add(mm)
                    if mac_aliases:
                        parsed_data["mac_aliases"] = sorted(m for m in mac_aliases if m)
                        device.latest_parsed_data = parsed_data
                except Exception:
                    pass

                db.query(Interface).filter(Interface.device_id == device.id).delete()
                for iface in parsed_data.get("interfaces", []):
                    link_status = iface.get("link_status", "")
                    is_up = iface.get("is_up", False)
                    is_enabled = iface.get("is_enabled", True)

                    if not is_enabled:
                        status = "admin_down"
                    elif is_up:
                        status = "up"
                    else:
                        status = "down"

                    db.add(
                        Interface(
                            device_id=device.id,
                            name=iface["name"],
                            description=iface.get("description"),
                            status=status,
                            admin_status="up" if is_enabled else "down",
                            mode=iface.get("mode", "access"),
                            vlan=int(iface["vlan"]) if str(iface.get("vlan")).isdigit() else 1,
                            ip_address=iface.get("ip_address"),
                        )
                    )

                if "neighbors" not in parsed_data:
                    parsed_data["neighbors"] = neighbors
                device.latest_parsed_data = parsed_data

                db.add(ConfigBackup(device_id=device.id, raw_config=raw_config))
                TopologyLinkService.refresh_links_for_device(db, device, neighbors)

                try:
                    DeviceSyncService._refresh_endpoints_from_mac_table(db, device, conn)
                except Exception:
                    pass

                try:
                    inv_count = EntityMibService.refresh_device_inventory(db, device)
                except Exception:
                    inv_count = 0

                if inv_count == 0 or (not device.serial_number) or (not device.model or device.model == "Unknown"):
                    try:
                        ssh_inv_count = InventorySshService.refresh_device_inventory_from_ssh(db, device, conn)
                        if int(ssh_inv_count or 0) == 0:
                            db.add(
                                EventLog(
                                    device_id=device.id,
                                    message="Inventory parser fallback: read-only collection only. Manual review/approval required.",
                                    severity="warning",
                                )
                            )
                    except Exception:
                        pass

                # --- L3 Topology: OSPF / BGP neighbor collection ---
                ospf_neighbors = []
                bgp_neighbors = []
                try:
                    if hasattr(conn.driver, 'get_ospf_neighbors'):
                        ospf_neighbors = conn.driver.get_ospf_neighbors()
                except Exception:
                    pass
                try:
                    if hasattr(conn.driver, 'get_bgp_neighbors'):
                        bgp_neighbors = conn.driver.get_bgp_neighbors()
                except Exception:
                    pass

                if ospf_neighbors or bgp_neighbors:
                    try:
                        TopologyLinkService.refresh_l3_links_for_device(
                            db, device, ospf_neighbors, bgp_neighbors
                        )
                    except Exception:
                        pass

                    if "l3_routing" not in parsed_data:
                        parsed_data["l3_routing"] = {}
                    parsed_data["l3_routing"]["ospf_neighbors"] = ospf_neighbors
                    parsed_data["l3_routing"]["bgp_neighbors"] = bgp_neighbors
                    device.latest_parsed_data = parsed_data

                l3_count = len(ospf_neighbors) + len(bgp_neighbors)
                sync_msg = f"Synced. Interfaces: {len(parsed_data.get('interfaces', []))}, L2 Neighbors: {len(neighbors)}, L3 Peers: {l3_count}"
            except Exception as e:
                device.status = "online"
                sync_msg = f"Synced but parsing error: {str(e)}"
                try:
                    db.add(
                        EventLog(
                            device_id=device.id,
                            severity="warning",
                            event_id="DEVICE_SYNC_PARSE_ERROR",
                            message=sync_msg,
                            source="DeviceSync",
                        )
                    )
                except Exception:
                    pass
            finally:
                conn.disconnect()
        else:
            device.status = "offline"
            inv_count = 0
            try:
                inv_count = EntityMibService.refresh_device_inventory(db, device)
            except Exception:
                inv_count = 0
            sync_msg = conn.last_error
            if inv_count:
                sync_msg = f"{sync_msg} (SNMP inventory refreshed: {inv_count})"
            try:
                db.add(
                    EventLog(
                        device_id=device.id,
                        severity="warning",
                        event_id="DEVICE_SYNC_FAIL",
                        message=f"DeviceSync failed: {sync_msg}",
                        source="DeviceSync",
                    )
                )
            except Exception:
                pass

        db.commit()
        return {"status": str(device.status or "offline").lower(), "message": sync_msg}

    @staticmethod
    def _refresh_endpoints_from_mac_table(db: Session, device: Device, conn: DeviceConnection) -> None:
        if not device or not conn:
            return

        def normalize_mac_key(mac: str) -> str:
            s = (mac or "").strip().lower()
            import re

            s = re.sub(r"[^0-9a-f]", "", s)
            return s

        def format_mac(mac_key: str) -> str:
            s = normalize_mac_key(mac_key)
            if len(s) != 12:
                return (mac_key or "").strip().lower()
            return f"{s[0:4]}.{s[4:8]}.{s[8:12]}"

        def infer_endpoint_type_and_vendor(info: dict) -> tuple:
            name = str(info.get("system_name") or "")
            descr = str(info.get("system_description") or "")
            text = f"{name} {descr}".lower()
            vendor = None
            if "cisco" in text:
                vendor = "Cisco"
            elif "aruba" in text or "hewlett" in text or "hp" in text:
                vendor = "Aruba"
            elif "ubiquiti" in text or "unifi" in text:
                vendor = "Ubiquiti"
            elif "juniper" in text:
                vendor = "Juniper"
            elif "arista" in text:
                vendor = "Arista"
            elif "huawei" in text:
                vendor = "Huawei"
            elif "windows" in text:
                vendor = "Microsoft"
            elif "apple" in text or "ios" in text or "mac os" in text:
                vendor = "Apple"

            if any(x in text for x in ("switch", "router", "nx-os", "ios xe", "ios-xe", "junos", "eos", "sr os", "arubaos-switch")):
                return "network", vendor
            if any(x in text for x in ("ip phone", "phone", "voip", "sip", "cisco 79", "cisco 88", "cisco 78")):
                return "phone", vendor
            if any(x in text for x in ("air-", "catalyst ap", "access point", "wireless ap", "unifi ap", "aruba ap", "ap-")):
                return "ap", vendor
            if any(x in text for x in ("windows", "linux", "ubuntu", "debian", "centos", "macbook", "mac os", "android")):
                return "pc", vendor
            return "unknown", vendor

        linked_ports = set()
        links = db.query(Link).filter(
            ((Link.source_device_id == device.id) | (Link.target_device_id == device.id))
            & (Link.status.in_(["active", "up"]))
        ).all()
        for l in links:
            if l.source_device_id == device.id and l.source_interface_name:
                linked_ports.add(l.source_interface_name)
            if l.target_device_id == device.id and l.target_interface_name:
                linked_ports.add(l.target_interface_name)

        arp_entries = {}
        try:
            for a in conn.get_arp_table() or []:
                mac = (a.get("mac") or "").strip().lower()
                ip = (a.get("ip") or "").strip()
                if mac and ip:
                    arp_entries[normalize_mac_key(mac)] = ip
        except Exception:
            arp_entries = {}

        if not arp_entries and device.snmp_community:
            try:
                snmp = SnmpManager(device.ip_address, device.snmp_community)
                for a in SnmpL2Service.get_arp_table(snmp) or []:
                    mac = (a.get("mac") or "").strip().lower()
                    ip = (a.get("ip") or "").strip()
                    if mac and ip:
                        arp_entries[normalize_mac_key(mac)] = ip
            except Exception:
                pass

        dhcp_entries = {}
        try:
            for d in conn.get_dhcp_snooping_bindings() or []:
                mac = d.get("mac")
                ip = d.get("ip")
                if mac and ip:
                    dhcp_entries[normalize_mac_key(mac)] = str(ip).strip()
        except Exception:
            dhcp_entries = {}

        lldp_by_port = {}
        try:
            for n in conn.get_lldp_neighbors_detail() or []:
                li = (n.get("local_interface") or "").strip()
                if li:
                    lldp_by_port[li] = n
        except Exception:
            lldp_by_port = {}

        now = datetime.now()
        retention_days = 30
        mac_table = conn.get_mac_table() or []
        if not mac_table and device.snmp_community:
            try:
                snmp = SnmpManager(device.ip_address, device.snmp_community)
                mac_table = SnmpL2Service.get_qbridge_mac_table(snmp) or SnmpL2Service.get_bridge_mac_table(snmp) or []
            except Exception:
                mac_table = []
        elif mac_table and device.snmp_community:
            try:
                snmp = SnmpManager(device.ip_address, device.snmp_community)
                qrows = SnmpL2Service.get_qbridge_mac_table(snmp) or []
                if qrows:
                    vlan_by_mac_port = {(r.get("mac"), r.get("port")): r.get("vlan") for r in qrows if r.get("mac") and r.get("port") and r.get("vlan")}
                    if vlan_by_mac_port:
                        enriched = []
                        for e in mac_table:
                            if e.get("vlan") is None and e.get("mac") and e.get("port"):
                                v = vlan_by_mac_port.get((e.get("mac"), e.get("port")))
                                if v is not None:
                                    e = {**e, "vlan": v}
                            enriched.append(e)
                        mac_table = enriched
            except Exception:
                pass
        try:
            DiscoveryHintCacheService.record_seed_snapshot(
                seed_device_id=int(device.id) if getattr(device, "id", None) is not None else None,
                seed_ip=str(getattr(device, "ip_address", None) or ""),
                seed_vendor=str(getattr(device, "name", None) or ""),
                arp_rows=[
                    {
                        "ip": ip_value,
                        "mac": mac_key,
                        "interface": None,
                    }
                    for mac_key, ip_value in arp_entries.items()
                    if mac_key and ip_value
                ],
                lldp_rows=list(lldp_by_port.values()),
                fdb_rows=list(mac_table or []),
            )
        except Exception:
            pass
        seen_attachment_ids = set()
        for e in mac_table:
            mac_raw = e.get("mac")
            port = (e.get("port") or "").strip()
            vlan = e.get("vlan")
            entry_type = str(e.get("type") or "").lower()

            if not mac_raw or not port:
                continue
            if entry_type and "dynamic" not in entry_type and entry_type not in ("learn", "learned"):
                continue
            if port in linked_ports:
                continue
            p_low = port.lower()
            if p_low.startswith("po") or p_low.startswith("port-channel") or p_low.startswith("vlan") or p_low in ("cpu", "sup", "router"):
                continue

            mac_key = normalize_mac_key(mac_raw)
            mac_norm = format_mac(mac_key)
            ip = dhcp_entries.get(mac_key) or arp_entries.get(mac_key)

            oui_vendor = None
            try:
                oui_vendor = OUIService.lookup_vendor(mac_norm)
            except Exception:
                oui_vendor = None

            lldp = lldp_by_port.get(port) or lldp_by_port.get(port.replace(" ", ""))
            inferred_type = "unknown"
            inferred_vendor = None
            inferred_hostname = None
            if isinstance(lldp, dict):
                inferred_hostname = lldp.get("system_name") or None
                inferred_type, inferred_vendor = infer_endpoint_type_and_vendor(lldp)
                if inferred_type == "network":
                    continue
            if not inferred_vendor and oui_vendor:
                inferred_vendor = oui_vendor
            if inferred_type in (None, "", "unknown") and inferred_vendor:
                v = inferred_vendor.lower()
                if any(x in v for x in ("apple", "samsung", "xiaomi", "huawei", "lg", "motorola", "google")):
                    inferred_type = "pc"
                if any(x in v for x in ("polycom", "yealink", "grandstream", "cisco")) and inferred_type == "pc":
                    inferred_type = "phone"

            endpoint = db.query(Endpoint).filter(Endpoint.mac_address == mac_norm).first()
            if endpoint:
                endpoint.last_seen = now
                if ip and (not endpoint.ip_address or endpoint.ip_address != ip):
                    endpoint.ip_address = ip
                if inferred_vendor and not endpoint.vendor:
                    endpoint.vendor = inferred_vendor
                if inferred_type and endpoint.endpoint_type in (None, "", "unknown") and inferred_type != "unknown":
                    endpoint.endpoint_type = inferred_type
                if inferred_hostname and not endpoint.hostname:
                    endpoint.hostname = inferred_hostname
            else:
                endpoint = Endpoint(
                    mac_address=mac_norm,
                    ip_address=ip,
                    hostname=inferred_hostname,
                    vendor=inferred_vendor,
                    endpoint_type=inferred_type or "unknown",
                )
                db.add(endpoint)
                db.flush()

            att = db.query(EndpointAttachment).filter(
                EndpointAttachment.endpoint_id == endpoint.id,
                EndpointAttachment.device_id == device.id,
                EndpointAttachment.interface_name == port,
            ).first()
            if att:
                att.last_seen = now
                att.vlan = str(vlan) if vlan is not None else att.vlan
                seen_attachment_ids.add(att.id)
            else:
                new_att = EndpointAttachment(
                    endpoint_id=endpoint.id,
                    device_id=device.id,
                    interface_name=port,
                    vlan=str(vlan) if vlan is not None else None,
                    first_seen=now,
                    last_seen=now,
                )
                db.add(new_att)
                db.flush()
                seen_attachment_ids.add(new_att.id)

        try:
            from datetime import timedelta

            cutoff = now - timedelta(days=retention_days)
            db.query(EndpointAttachment).filter(EndpointAttachment.last_seen < cutoff).delete(synchronize_session=False)
            orphan_ids = (
                db.query(Endpoint.id)
                .outerjoin(EndpointAttachment, EndpointAttachment.endpoint_id == Endpoint.id)
                .filter(EndpointAttachment.id.is_(None))
                .filter(Endpoint.last_seen < cutoff)
                .all()
            )
            if orphan_ids:
                db.query(Endpoint).filter(Endpoint.id.in_([x[0] for x in orphan_ids])).delete(synchronize_session=False)
        except Exception:
            pass

    @staticmethod
    def sync_device_job(device_id: int, idempotency_key: str | None = None) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            if not DeviceSyncService._acquire_device_sync_lock(db, device_id):
                return {"status": "skipped", "message": "sync_locked"}
            result = DeviceSyncService.sync_device(db, device_id)
            if idempotency_key:
                result = {**result, "idempotency_key": str(idempotency_key)}
            return result
        finally:
            db.close()
