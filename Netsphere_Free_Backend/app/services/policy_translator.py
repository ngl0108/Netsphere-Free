from typing import Any, Callable, Dict, List
import ipaddress

from app.models.device import Policy


class PolicyTranslator:
    """
    Policy translator plugin registry + compatibility wrapper.
    """

    _plugins: List[Dict[str, Any]] = []

    @staticmethod
    def register_plugin(
        plugin_id: str,
        label: str,
        match: Callable[[str], bool],
        renderer: Callable[[Policy], List[str]],
    ) -> None:
        PolicyTranslator._plugins.append(
            {
                "id": str(plugin_id),
                "label": str(label),
                "match": match,
                "renderer": renderer,
            }
        )

    @staticmethod
    def support_matrix() -> List[Dict[str, str]]:
        return [
            {"plugin": p["id"], "label": p["label"]}
            for p in PolicyTranslator._plugins
        ]

    @staticmethod
    def _find_plugin(device_type: str) -> Dict[str, Any] | None:
        dtype = str(device_type or "").strip().lower()
        for p in PolicyTranslator._plugins:
            try:
                if p["match"](dtype):
                    return p
            except Exception:
                continue
        return None

    @staticmethod
    def translate_or_fallback(policy: Policy, device_type: str) -> Dict[str, Any]:
        plugin = PolicyTranslator._find_plugin(device_type)
        if not plugin:
            return {
                "supported": False,
                "mode": "read_only_manual_approval",
                "plugin": None,
                "commands": [],
                "message": f"Translation not supported for {device_type}",
            }
        try:
            commands = plugin["renderer"](policy) or []
            if not commands:
                return {
                    "supported": False,
                    "mode": "read_only_manual_approval",
                    "plugin": plugin["id"],
                    "commands": [],
                    "message": f"Translator returned no commands for {device_type}",
                }
            return {
                "supported": True,
                "mode": "auto_push",
                "plugin": plugin["id"],
                "commands": commands,
                "message": "ok",
            }
        except Exception as e:
            return {
                "supported": False,
                "mode": "read_only_manual_approval",
                "plugin": plugin["id"],
                "commands": [],
                "message": f"Translator error for {device_type}: {e}",
            }

    @staticmethod
    def translate(policy: Policy, device_type: str) -> List[str]:
        """
        Backward compatibility: endpoints expecting list[str].
        """
        result = PolicyTranslator.translate_or_fallback(policy, device_type)
        if result["supported"]:
            return result["commands"]
        return []

    @staticmethod
    def to_cisco_ios(policy: Policy) -> List[str]:
        commands = []
        acl_name = policy.name.replace(" ", "_").upper()
        commands.append(f"ip access-list extended {acl_name}")
        sorted_rules = sorted(policy.rules, key=lambda r: r.priority)
        for rule in sorted_rules:
            action = rule.action.lower() if rule.action else "permit"
            conditions = rule.match_conditions or {}
            protocol = conditions.get("protocol", "ip")
            src = PolicyTranslator._parse_address_cisco(conditions.get("source", "any"))
            dst = PolicyTranslator._parse_address_cisco(conditions.get("destination", "any"))
            port_str = ""
            if protocol in ["tcp", "udp"]:
                port = conditions.get("port")
                if port and str(port).lower() != "any":
                    port_str = f" eq {port}"
            commands.append(f" {action} {protocol} {src} {dst}{port_str}")
        return commands

    @staticmethod
    def to_juniper_junos(policy: Policy) -> List[str]:
        commands = []
        filter_name = policy.name.replace(" ", "-").upper()
        sorted_rules = sorted(policy.rules, key=lambda r: r.priority)
        for idx, rule in enumerate(sorted_rules, start=1):
            term_name = f"TERM-{idx}"
            action = "accept" if rule.action.lower() == "permit" else "reject"
            conditions = rule.match_conditions or {}
            protocol = conditions.get("protocol", "ip")
            src = conditions.get("source", "any")
            dst = conditions.get("destination", "any")
            port = conditions.get("port")
            if src and str(src).lower() != "any":
                commands.append(f"set firewall filter {filter_name} term {term_name} from source-address {src}")
            if dst and str(dst).lower() != "any":
                commands.append(f"set firewall filter {filter_name} term {term_name} from destination-address {dst}")
            if protocol and str(protocol).lower() != "ip":
                commands.append(f"set firewall filter {filter_name} term {term_name} from protocol {protocol}")
            if port and protocol in ["tcp", "udp"]:
                commands.append(f"set firewall filter {filter_name} term {term_name} from destination-port {port}")
            commands.append(f"set firewall filter {filter_name} term {term_name} then {action}")
        return commands

    @staticmethod
    def to_arista_eos(policy: Policy) -> List[str]:
        commands = []
        acl_name = policy.name.replace(" ", "_").upper()
        commands.append(f"ip access-list {acl_name}")
        sorted_rules = sorted(policy.rules, key=lambda r: r.priority)
        for idx, rule in enumerate(sorted_rules, start=10):
            action = rule.action.lower() if rule.action else "permit"
            conditions = rule.match_conditions or {}
            protocol = conditions.get("protocol", "ip")
            src = PolicyTranslator._parse_address_arista(conditions.get("source", "any"))
            dst = PolicyTranslator._parse_address_arista(conditions.get("destination", "any"))
            port_str = ""
            if protocol in ["tcp", "udp"]:
                port = conditions.get("port")
                if port and str(port).lower() != "any":
                    port_str = f" eq {port}"
            commands.append(f"   {idx} {action} {protocol} {src} {dst}{port_str}")
        return commands

    @staticmethod
    def to_linux_iptables(policy: Policy) -> List[str]:
        commands: List[str] = []
        sorted_rules = sorted(policy.rules, key=lambda r: r.priority)
        for rule in sorted_rules:
            action = (rule.action or "permit").strip().lower()
            target = "ACCEPT" if action in {"permit", "allow", "accept"} else "DROP"
            conditions = rule.match_conditions or {}
            protocol = str(conditions.get("protocol", "") or "").strip().lower()
            parts: List[str] = ["iptables", "-A", "FORWARD"]
            if protocol and protocol not in {"ip", "any", "all"}:
                parts += ["-p", protocol]
            src = str(conditions.get("source", "any") or "any").strip()
            dst = str(conditions.get("destination", "any") or "any").strip()
            if src.lower() != "any":
                parts += ["-s", PolicyTranslator._normalize_cidr(src)]
            if dst.lower() != "any":
                parts += ["-d", PolicyTranslator._normalize_cidr(dst)]
            port = conditions.get("port")
            if port and str(port).lower() != "any" and protocol in {"tcp", "udp"}:
                parts += ["--dport", str(port)]
            parts += ["-j", target]
            commands.append(" ".join(parts))
        return commands

    @staticmethod
    def _parse_address_cisco(addr: str) -> str:
        if not addr or str(addr).lower() == "any":
            return "any"
        if "/" in addr:
            try:
                network = ipaddress.ip_network(addr, strict=False)
                return f"{network.network_address} {network.hostmask}"
            except ValueError:
                return f"! INVALID_IP({addr})"
        if " " not in addr and addr.count(".") == 3:
            return f"host {addr}"
        return addr

    @staticmethod
    def _parse_address_arista(addr: str) -> str:
        if not addr or str(addr).lower() == "any":
            return "any"
        if "/" in addr:
            return addr
        if " " not in addr and addr.count(".") == 3:
            return f"host {addr}"
        return addr

    @staticmethod
    def _normalize_cidr(addr: str) -> str:
        a = str(addr or "").strip()
        if not a:
            return "0.0.0.0/0"
        if "/" in a:
            try:
                return str(ipaddress.ip_network(a, strict=False))
            except ValueError:
                return a
        if a.count(".") == 3 and " " not in a:
            return f"{a}/32"
        return a


def _register_builtin_plugins() -> None:
    if PolicyTranslator._plugins:
        return
    PolicyTranslator.register_plugin(
        plugin_id="cisco_acl",
        label="Cisco IOS/NXOS + domestic Cisco-like",
        match=lambda d: (
            "cisco" in d
            or "ios" in d
            or "nxos" in d
            or "dasan" in d
            or "ubiquoss" in d
            or "soltech" in d
            or "coreedge" in d
            or "nst" in d
        ),
        renderer=PolicyTranslator.to_cisco_ios,
    )
    PolicyTranslator.register_plugin(
        plugin_id="juniper_filter",
        label="Juniper JunOS firewall filter",
        match=lambda d: ("juniper" in d or "junos" in d),
        renderer=PolicyTranslator.to_juniper_junos,
    )
    PolicyTranslator.register_plugin(
        plugin_id="arista_acl",
        label="Arista EOS ACL",
        match=lambda d: ("arista" in d or "eos" in d),
        renderer=PolicyTranslator.to_arista_eos,
    )
    PolicyTranslator.register_plugin(
        plugin_id="linux_iptables",
        label="Linux iptables (domestic security vendors)",
        match=lambda d: d.startswith("linux_") and any(
            k in d for k in (
                "ahnlab",
                "secui",
                "wins",
                "axgate",
                "nexg",
                "genians",
                "monitorapp",
                "aircuve",
                "netman",
                "mlsoft",
                "sga",
                "nixtech",
                "trinitysoft",
            )
        ),
        renderer=PolicyTranslator.to_linux_iptables,
    )


_register_builtin_plugins()
