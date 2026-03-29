import re
from typing import Any, Dict, Optional, Tuple

# ============================================================================
# 1. SNMP Enterprise OID Database (PEN: Private Enterprise Number)
# ============================================================================
VENDOR_OIDS = {
    # Global Vendors
    "1.3.6.1.4.1.9": "Cisco",
    "1.3.6.1.4.1.29671": "Cisco Meraki",
    "1.3.6.1.4.1.2636": "Juniper",
    "1.3.6.1.4.1.30065": "Arista",
    "1.3.6.1.4.1.2011": "Huawei",
    "1.3.6.1.4.1.47196": "Aruba",
    "1.3.6.1.4.1.11": "HP",
    "1.3.6.1.4.1.25506": "H3C",
    "1.3.6.1.4.1.14823": "Aruba",
    "1.3.6.1.4.1.1916": "Extreme",
    "1.3.6.1.4.1.1588": "Extreme",
    "1.3.6.1.4.1.45": "Nortel",
    "1.3.6.1.4.1.2272": "Passport",
    "1.3.6.1.4.1.1872": "Alteon",
    "1.3.6.1.4.1.89": "Allied Telesis",
    "1.3.6.1.4.1.171": "D-Link",
    "1.3.6.1.4.1.6486": "Alcatel-Lucent",
    "1.3.6.1.4.1.6527": "Nokia",
    "1.3.6.1.4.1.12356": "Fortinet",
    "1.3.6.1.4.1.25461": "PaloAlto",
    "1.3.6.1.4.1.3375": "F5",
    "1.3.6.1.4.1.2620": "CheckPoint",
    "1.3.6.1.4.1.5951": "NetScaler",
    "1.3.6.1.4.1.3076": "Ruckus",
    "1.3.6.1.4.1.119": "NEC",
    "1.3.6.1.4.1.6027": "Dell",
    "1.3.6.1.4.1.2": "IBM",
    "1.3.6.1.4.1.674": "Dell",

    # Korean Vendors
    "1.3.6.1.4.1.6296": "Dasan",
    "1.3.6.1.4.1.36243": "Dasan",
    "1.3.6.1.4.1.6728": "Dasan",
    "1.3.6.1.4.1.7331": "Ubiquoss",
    "1.3.6.1.4.1.7800": "Ubiquoss",
    "1.3.6.1.4.1.7803": "Ubiquoss",
    "1.3.6.1.4.1.7784": "Ubiquoss",
    "1.3.6.1.4.1.10226": "Ubiquoss",
    "1.3.6.1.4.1.20935": "Handream",
    "1.3.6.1.4.1.25053": "HanDreamnet",
    "1.3.6.1.4.1.23237": "HanDreamnet",
    "1.3.6.1.4.1.14781": "HanDreamnet",
    "1.3.6.1.4.1.17804": "Piolink",
    "1.3.6.1.4.1.8842": "Piolink",
    "1.3.6.1.4.1.13530": "Piolink",
    "1.3.6.1.4.1.11798": "Piolink",
    "1.3.6.1.4.1.29336": "NST IC",
    "1.3.6.1.4.1.13626": "HFR",
    "1.3.6.1.4.1.10166": "Coweaver",
    "1.3.6.1.4.1.10931": "WooriNet",
    "1.3.6.1.4.1.14838": "Telefield",
    "1.3.6.1.4.1.19865": "EFMNetworks",
    "1.3.6.1.4.1.17792": "EFMNetworks",
    "1.3.6.1.4.1.16668": "Mercury",
    "1.3.6.1.4.1.13974": "Davolink",

    # Security / NAC (Korea)
    "1.3.6.1.4.1.35020": "Genians",
    "1.3.6.1.4.1.5491": "NetMan",
    "1.3.6.1.4.1.26163": "AirCuve",
    "1.3.6.1.4.1.19746": "MLSoft",
    "1.3.6.1.4.1.26154": "SGA",
    "1.3.6.1.4.1.20038": "Nixtech",
    "1.3.6.1.4.1.26464": "AhnLab",
    "1.3.6.1.4.1.2608": "AhnLab",
    "1.3.6.1.4.1.33152": "AhnLab",
    "1.3.6.1.4.1.2603": "SECUI",
    "1.3.6.1.4.1.4867": "SECUI",
    "1.3.6.1.4.1.14922": "SECUI",
    "1.3.6.1.4.1.2439": "WINS",
    "1.3.6.1.4.1.3996": "WINS",
    "1.3.6.1.4.1.14441": "WINS",
    "1.3.6.1.4.1.26472": "MonitorApp",
    "1.3.6.1.4.1.20237": "MonitorApp",
    "1.3.6.1.4.1.37259": "AXGATE",
    "1.3.6.1.4.1.10641": "NexG",
    "1.3.6.1.4.1.30058": "TrinitySoft",

    # OS / Servers
    "1.3.6.1.4.1.8072": "Linux",
    "1.3.6.1.4.1.311": "Windows",
    "1.3.6.1.4.1.6876": "VMware",
    "1.3.6.1.4.1.231": "Compaq",
    "1.3.6.1.4.1.343": "Intel",
    "1.3.6.1.4.1.236": "Samsung",
}

PLATFORM_OID_HINTS = {
    "1.3.6.1.4.1.9.1.1745": {
        "device_type": "cisco_ios",
        "platform": "ios",
        "family": "enterprise",
        "os_family": "ios",
        "rule_id": "cisco:ios:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.9.1.2170": {
        "device_type": "cisco_wlc",
        "platform": "wireless_controller",
        "family": "wireless",
        "os_family": "aireos",
        "rule_id": "cisco:wlc:aireos:oid",
        "confidence_bonus": 0.05,
    },
    "1.3.6.1.4.1.9.1.2263": {
        "device_type": "cisco_nxos",
        "platform": "nexus",
        "family": "datacenter",
        "os_family": "nxos",
        "rule_id": "cisco:nxos:oid",
        "confidence_bonus": 0.05,
    },
    "1.3.6.1.4.1.9.1.2504": {
        "device_type": "cisco_ios_xe",
        "platform": "ios_xe",
        "family": "enterprise",
        "os_family": "ios_xe",
        "rule_id": "cisco:ios_xe:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.9.1.2530": {
        "device_type": "cisco_wlc",
        "platform": "wireless_controller",
        "family": "wireless",
        "os_family": "ios_xe",
        "rule_id": "cisco:wlc:ios_xe:oid",
        "confidence_bonus": 0.05,
    },
    "1.3.6.1.4.1.2636.1.1.1.2.22": {
        "device_type": "juniper_junos",
        "platform": "router",
        "family": "routing",
        "os_family": "junos",
        "rule_id": "juniper:router:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.2636.1.1.1.2.100": {
        "device_type": "juniper_junos",
        "platform": "srx",
        "family": "security",
        "os_family": "junos",
        "rule_id": "juniper:srx:oid",
        "confidence_bonus": 0.05,
    },
    "1.3.6.1.4.1.2636.1.1.1.2.144": {
        "device_type": "juniper_junos",
        "platform": "switch",
        "family": "switching",
        "os_family": "junos",
        "rule_id": "juniper:switch:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.30065.1.3011.7050.332": {
        "device_type": "arista_eos",
        "platform": "eos",
        "family": "switching",
        "os_family": "eos",
        "rule_id": "arista:eos:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.2011.2.239.11": {
        "device_type": "huawei_vrp",
        "platform": "cloudengine",
        "family": "datacenter",
        "os_family": "vrp",
        "rule_id": "huawei:cloudengine:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.25506.1": {
        "device_type": "hp_comware",
        "platform": "comware",
        "family": "networking",
        "os_family": "comware",
        "rule_id": "h3c:comware:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.11.2.3.7.11.160": {
        "device_type": "hp_procurve",
        "platform": "aos_switch",
        "family": "switching",
        "os_family": "aos_switch",
        "rule_id": "hp:aos_switch:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.47196.4.1.25.1.1": {
        "device_type": "aruba_os",
        "platform": "aos_cx",
        "family": "switching",
        "os_family": "aos_cx",
        "rule_id": "aruba:aos_cx:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.6027.1.3.17": {
        "device_type": "dell_force10",
        "platform": "force10",
        "family": "switching",
        "os_family": "ftos",
        "rule_id": "dell:force10:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.674.10895.3082": {
        "device_type": "dell_os10",
        "platform": "os10",
        "family": "switching",
        "os_family": "os10",
        "rule_id": "dell:os10:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.1916.2.193": {
        "device_type": "extreme_exos",
        "platform": "exos",
        "family": "switching",
        "os_family": "exos",
        "rule_id": "extreme:exos:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.1588.2.1.1": {
        "device_type": "extreme_netiron",
        "platform": "netiron",
        "family": "datacenter",
        "os_family": "netiron",
        "rule_id": "extreme:netiron:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.6527.1.3.4": {
        "device_type": "nokia_sros",
        "platform": "sr_os",
        "family": "routing",
        "os_family": "sros",
        "rule_id": "nokia:sros:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.6486.801.1.1.2.1.11.1.2": {
        "device_type": "alcatel_aos",
        "platform": "aos",
        "family": "switching",
        "os_family": "aos",
        "rule_id": "alcatel:aos:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.12356.101.1": {
        "device_type": "fortinet",
        "platform": "fortigate",
        "family": "security",
        "os_family": "fortios",
        "rule_id": "fortinet:fortigate:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.25461.2.3": {
        "device_type": "paloalto_panos",
        "platform": "firewall",
        "family": "security",
        "os_family": "panos",
        "rule_id": "paloalto:panos:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.2620.1.6": {
        "device_type": "checkpoint_gaia",
        "platform": "gaia",
        "family": "security",
        "os_family": "gaia",
        "rule_id": "checkpoint:gaia:oid",
        "confidence_bonus": 0.04,
    },
    "1.3.6.1.4.1.3375.2.1.3": {
        "device_type": "f5_ltm",
        "platform": "bigip",
        "family": "adc",
        "os_family": "tmos",
        "rule_id": "f5:tmos:oid",
        "confidence_bonus": 0.04,
    },
}

# ============================================================================
# 2. Netmiko Driver Mapping
# ============================================================================
VENDOR_TO_DRIVER = {
    "Cisco": "cisco_ios",
    "Cisco Meraki": "cisco_meraki",
    "Juniper": "juniper_junos",
    "Arista": "arista_eos",
    "Huawei": "huawei",
    "HP": "hp_procurve",
    "Aruba": "aruba_os",
    "H3C": "hp_comware",
    "Extreme": "extreme_exos",
    "Dell": "dell_os10",
    "Nokia": "nokia_sros",
    "Alcatel-Lucent": "alcatel_aos",
    "Fortinet": "fortinet",
    "PaloAlto": "paloalto_panos",
    "F5": "f5_ltm",
    "CheckPoint": "checkpoint_gaia",
    "Linux": "linux",
    "Windows": "windows_cmd",
    "Dasan": "dasan_nos",
    "Ubiquoss": "ubiquoss_l2",
    "Handream": "handream_sg",
    "HanDreamnet": "handream_sg",
    "Piolink": "piolink_pas",
    "NST IC": "nst_switch",
    "NST": "nst_switch",
    "Soltech": "soltech_switch",
    "CoreEdge": "coreedge_switch",
    "Core Edge": "coreedge_switch",
    "HFR": "cisco_ios",
    "Coweaver": "cisco_ios",
    "WooriNet": "cisco_ios",
    "Telefield": "cisco_ios",
    # Security / NAC
    "Genians": "linux_genians",
    "NetMan": "linux_netman",
    "AirCuve": "linux_aircuve",
    "MLSoft": "linux_mlsoft",
    "SGA": "linux_sga",
    "Nixtech": "linux_nixtech",
    "AhnLab": "linux_ahnlab",
    "SECUI": "linux_secui",
    "WINS": "linux_wins",
    "MonitorApp": "linux_monitorapp",
    "AXGATE": "linux_axgate",
    "NexG": "linux_nexg",
    "TrinitySoft": "linux_trinitysoft",
    "EFMNetworks": "linux",
    "Mercury": "linux",
    "Davolink": "linux",
    "Samsung": "linux",
}

# ============================================================================
# 3. Model Extraction Regex Patterns
# ============================================================================
MODEL_PATTERNS = {
    "Cisco": [
        r"\b(N\dK-[A-Z0-9-]+)\b",
        r"\b((?:C)?9800(?:-[A-Z0-9-]+)?)\b",
        r"\b(AIR-CT\d+[A-Z0-9-]*)\b",
        r"\b(CSR1000V)\b",
        r"\b((?:ISR|ASR)\d+[A-Z0-9-]*)\b",
        r"\b((?:WS-|CBS|C)\d{3,4}[A-Z0-9-]*)\b",
        r"Cisco\s+Nexus\s+([0-9]+[A-Z0-9]*)",
        r"Cisco\s+IOS\s+Software.*?\(([^)]+)\)",
        r"Cisco\s+Adaptive\s+Security\s+Appliance\s+Version\s+([0-9\.]+)",
    ],
    "Juniper": [
        r"\b(MX\d+[A-Z0-9-]*)\b",
        r"\b(SRX\d+[A-Z0-9-]*)\b",
        r"\b(QFX\d+[A-Z0-9-]*)\b",
        r"\b(EX\d+[A-Z0-9-]*)\b",
        r"\b(PTX\d+[A-Z0-9-]*)\b",
        r"Juniper\s+Networks,\s+Inc\.\s+([a-zA-Z0-9-]+)\s+(?:Edge|Router|Switch|Services)",
        r"Model:\s+([a-zA-Z0-9-]+)",
    ],
    "Arista": [
        r"\b(DCS-\d+[A-Z0-9-]*)\b",
        r"Arista\s+([a-zA-Z0-9-]+)",
    ],
    "Huawei": [
        r"\b(CE\d{3,5}[A-Z0-9-]*)\b",
        r"\b(S\d{3,5}[A-Z0-9-]*)\b",
        r"\b(NE\d{2,4}[A-Z0-9-]*)\b",
        r"HUAWEI\s+([A-Z0-9-]+)\s+Switch",
    ],
    "HP": [
        r"\b(JL\d{3}[A-Z])\b",
        r"\b(54\d{2}R?[A-Z0-9-]*)\b",
        r"(29\d{2}[A-Z0-9+\-]*\+?)",
    ],
    "Aruba": [
        r"\b(83\d{2}[A-Z0-9-]*)\b",
        r"\b(84\d{2}[A-Z0-9-]*)\b",
        r"\b(63\d{2}[A-Z0-9-]*)\b",
        r"\b(29\d{2}[A-Z0-9-]*)\b",
    ],
    "H3C": [
        r"\b(S\d{4}[A-Z0-9-]*)\b",
        r"\b(MSR\d+[A-Z0-9-]*)\b",
    ],
    "Dell": [
        r"\b([SZN]\d{4}[A-Z0-9-]*)\b",
        r"\b(PowerConnect\s+[A-Z0-9-]+)\b",
    ],
    "Extreme": [
        r"\b(SLX-\d+[A-Z0-9-]*)\b",
        r"\b(VDX\d+[A-Z0-9-]*)\b",
        r"\b(X\d{4}[A-Z0-9-]*)\b",
    ],
    "Nokia": [
        r"\b(7750\s+SR-\d+[A-Z0-9-]*)\b",
        r"\b(7210\s+SAS-[A-Z0-9-]+)\b",
    ],
    "Alcatel-Lucent": [
        r"\b(OS\d{4,5}(?:-[A-Z0-9-]+)*)\b",
        r"\b(OmniSwitch\s+\d+[A-Z0-9-]*)\b",
    ],
    "Fortinet": [
        r"\b(FortiGate(?:-[A-Z0-9]+)+)\b",
    ],
    "PaloAlto": [
        r"\b(PA-\d{3,4}[A-Z0-9-]*)\b",
    ],
    "CheckPoint": [
        r"\b(Quantum\s+\d{4})\b",
        r"\b(\d{4})\b",
    ],
    "F5": [
        r"\b(BIG-IP\s+[A-Za-z0-9-]+)\b",
        r"\b(i\d{4})\b",
    ],
    "Dasan": [
        r"Dasan\s+Networks\s+([A-Z0-9-]+)",
        r"\b(V\d{4}[A-Z0-9-]*)\b",
    ],
    "Ubiquoss": [
        r"\b([A-Z]{1,5}-?\d{3,5}[A-Z0-9-]*)\b",
        r"Ubiquoss\s+(?:L[23]\s+)?(?:Switch\s+)?([A-Z0-9-\/]+)",
        r"uNOS\s+System\s+([A-Z0-9-]+)",
    ],
    "Handream": [
        r"\b(SG\d{3,5}[A-Z0-9-]*)\b",
        r"\b(Subgate|SubGate)\b",
    ],
    "HanDreamnet": [
        r"\b(SG\d{3,5}[A-Z0-9-]*)\b",
        r"\b(Subgate|SubGate)\b",
    ],
    "Piolink": [
        r"\b(PAS-[A-Z0-9-]+)\b",
        r"\b(TiFRONT)\b",
    ],
    "Soltech": [
        r"\b(SFC[0-9A-Z-]+)\b",
        r"\b(ESR[0-9A-Z-]+)\b",
    ],
    "CoreEdge": [
        r"\b(C[0-9]{4}[A-Z0-9-]*)\b",
        r"\b(CSW[0-9A-Z-]+)\b",
    ],
    "NST": [
        r"\b(NST[0-9A-Z-]+)\b",
        r"\b(NS[0-9A-Z-]+)\b",
    ],
    "AhnLab": [
        r"\b(TrusGuard\s*[A-Z0-9-]+)\b",
        r"\b(TrusGuard)\b",
    ],
    "SECUI": [
        r"\b(MF\d+[A-Z0-9-]*)\b",
        r"\b(BLUEMAX)\b",
    ],
    "WINS": [
        r"\b(DDX-[A-Z0-9-]+)\b",
        r"\b(Sniper\s+[A-Z0-9-]+)\b",
    ],
    "MonitorApp": [
        r"\b(AIWAF[A-Z0-9-]*)\b",
    ],
    "EFMNetworks": [
        r"\b(A\d{3,4}[A-Z0-9-]*)\b",
        r"\biptime\s+([a-z0-9-]+)\b",
    ],
    "Samsung": [
        r"\b([A-Z]{2,6}-\d{3,6}[A-Z0-9-]*)\b",
        r"Samsung\s+([A-Z0-9-]+)",
    ],
}


def _normalize_text(*values: object) -> str:
    parts = []
    for value in values:
        text = str(value or "").strip().lower()
        if text:
            parts.append(text)
    return " ".join(parts)


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _match_platform_oid_profile(sys_oid: str, model: str = "") -> Optional[Dict[str, Any]]:
    oid = str(sys_oid or "").strip()
    if not oid:
        return None
    for prefix, profile in sorted(PLATFORM_OID_HINTS.items(), key=lambda item: len(item[0]), reverse=True):
        if oid.startswith(prefix):
            matched = dict(profile)
            if model and not matched.get("model_hint"):
                matched["model_hint"] = model
            return matched
    return None


def _identify_vendor_internal(sys_oid: str, sys_descr: str = "") -> Tuple[str, float, str, str]:
    sys_oid = str(sys_oid or "").strip()
    sys_descr_l = _normalize_text(sys_descr)

    sorted_oids = sorted(VENDOR_OIDS.items(), key=lambda x: len(x[0]), reverse=True)
    for oid, vendor in sorted_oids:
        if sys_oid.startswith(oid):
            if oid == "1.3.6.1.4.1.23237":
                if "somansa" in sys_descr_l:
                    return "Somansa", 0.9, "oid", f"oid:{oid}:somansa"
                if "handream" in sys_descr_l or "subgate" in sys_descr_l:
                    return "HanDreamnet", 0.9, "oid", f"oid:{oid}:handream"
            return vendor, 0.95, "oid", f"oid:{oid}"

    if _contains_any(sys_descr_l, ("cisco", "ios xe", "ios-xe", "nx-os", "nexus", "aireos", "catalyst 9800")):
        return "Cisco", 0.8, "sys_descr", "sys_descr:cisco"
    if _contains_any(sys_descr_l, ("juniper", "junos", "junos os evolved")):
        return "Juniper", 0.8, "sys_descr", "sys_descr:juniper"
    if _contains_any(sys_descr_l, ("arista", "eos")):
        return "Arista", 0.8, "sys_descr", "sys_descr:arista"
    if _contains_any(sys_descr_l, ("huawei", "vrp")):
        return "Huawei", 0.8, "sys_descr", "sys_descr:huawei"
    if _contains_any(sys_descr_l, ("h3c", "comware")):
        return "H3C", 0.8, "sys_descr", "sys_descr:h3c"
    if _contains_any(sys_descr_l, ("aruba", "aos-cx", "arubaos-cx")):
        return "Aruba", 0.8, "sys_descr", "sys_descr:aruba"
    if _contains_any(sys_descr_l, ("hp", "procurve", "provision", "arubaos-switch", "aos-switch")):
        return "HP", 0.7, "sys_descr", "sys_descr:hp"
    if _contains_any(sys_descr_l, ("extreme", "xos", "exos", "netiron", "slx")):
        return "Extreme", 0.8, "sys_descr", "sys_descr:extreme"
    if _contains_any(sys_descr_l, ("dell", "powerconnect", "force10", "ftos", "os10", "smartfabric os10")):
        return "Dell", 0.8, "sys_descr", "sys_descr:dell"
    if _contains_any(sys_descr_l, ("fortinet", "fortigate", "fortios")):
        return "Fortinet", 0.8, "sys_descr", "sys_descr:fortinet"
    if _contains_any(sys_descr_l, ("paloalto", "panos", "pan-os", "pa-")):
        return "PaloAlto", 0.8, "sys_descr", "sys_descr:paloalto"
    if _contains_any(sys_descr_l, ("checkpoint", "gaia")):
        return "CheckPoint", 0.8, "sys_descr", "sys_descr:checkpoint"
    if _contains_any(sys_descr_l, ("f5", "big-ip", "tmos")):
        return "F5", 0.8, "sys_descr", "sys_descr:f5"
    if _contains_any(sys_descr_l, ("nokia", "sr os", "sros", "7750 sr", "7210 sas")):
        return "Nokia", 0.8, "sys_descr", "sys_descr:nokia"
    if _contains_any(sys_descr_l, ("alcatel", "omniswitch", "aos")):
        return "Alcatel-Lucent", 0.75, "sys_descr", "sys_descr:alcatel"
    if "iptime" in sys_descr_l:
        return "EFMNetworks", 0.8, "sys_descr", "sys_descr:iptime"
    if "samsung" in sys_descr_l:
        return "Samsung", 0.8, "sys_descr", "sys_descr:samsung"
    if "linux" in sys_descr_l:
        return "Linux", 0.6, "sys_descr", "sys_descr:linux"
    if "windows" in sys_descr_l:
        return "Windows", 0.6, "sys_descr", "sys_descr:windows"

    if "dasan" in sys_descr_l:
        return "Dasan", 0.8, "sys_descr", "sys_descr:dasan"
    if "ubiquoss" in sys_descr_l:
        return "Ubiquoss", 0.8, "sys_descr", "sys_descr:ubiquoss"
    if "handream" in sys_descr_l or "subgate" in sys_descr_l:
        return "HanDreamnet", 0.8, "sys_descr", "sys_descr:handream"
    if "piolink" in sys_descr_l or "tifront" in sys_descr_l:
        return "Piolink", 0.8, "sys_descr", "sys_descr:piolink"
    if "soltech" in sys_descr_l:
        return "Soltech", 0.8, "sys_descr", "sys_descr:soltech"
    if "coreedge" in sys_descr_l or "core edge" in sys_descr_l:
        return "CoreEdge", 0.8, "sys_descr", "sys_descr:coreedge"
    if re.search(r"\bnst\b", sys_descr_l):
        return "NST", 0.8, "sys_descr", "sys_descr:nst"
    if "wins" in sys_descr_l or "sniper" in sys_descr_l:
        return "WINS", 0.8, "sys_descr", "sys_descr:wins"
    if "secui" in sys_descr_l or "bluemax" in sys_descr_l:
        return "SECUI", 0.8, "sys_descr", "sys_descr:secui"
    if "ahnlab" in sys_descr_l or "trusguard" in sys_descr_l:
        return "AhnLab", 0.8, "sys_descr", "sys_descr:ahnlab"
    if "genians" in sys_descr_l:
        return "Genians", 0.8, "sys_descr", "sys_descr:genians"

    return "Unknown", 0.0, "none", "none"


def _platform_profile(
    vendor: str,
    sys_oid: str = "",
    sys_descr: str = "",
    sys_name: str = "",
    model: str = "",
) -> Dict[str, Any]:
    text = _normalize_text(sys_descr, sys_name, model)
    profile: Dict[str, Any] = {
        "device_type": VENDOR_TO_DRIVER.get(vendor, "unknown"),
        "platform": "",
        "family": "",
        "os_family": "",
        "rule_id": "",
        "confidence_bonus": 0.0,
        "model_hint": None,
    }

    oid_profile = _match_platform_oid_profile(sys_oid, model=model)
    if oid_profile:
        profile.update(oid_profile)
        return profile

    if vendor == "Cisco":
        if _matches_any(text, (r"\baireos\b", r"wireless lan controller", r"\bc9800\b", r"catalyst 9800", r"9800-?cl", r"\bewlc\b")):
            profile.update(
                device_type="cisco_wlc",
                platform="wireless_controller",
                family="wireless",
                os_family="aireos" if "aireos" in text else "ios_xe",
                rule_id="cisco:wlc",
                confidence_bonus=0.03,
            )
        elif _matches_any(text, (r"\bnx-?os\b", r"\bnexus\b", r"\bn[3579]k\b", r"\bmds\d", r"\baci\b")):
            profile.update(
                device_type="cisco_nxos",
                platform="nexus",
                family="datacenter",
                os_family="nxos",
                rule_id="cisco:nxos",
                confidence_bonus=0.04,
            )
        elif _matches_any(text, (r"\bios[- ]xe\b", r"\bcsr1000v\b", r"\basr1000\b", r"\bisr4\d{3}\b", r"\bc8\d{3}\b", r"\bc9[234569]00\b", r"\bcat9k\b")):
            profile.update(
                device_type="cisco_ios_xe",
                platform="ios_xe",
                family="enterprise",
                os_family="ios_xe",
                rule_id="cisco:ios_xe",
                confidence_bonus=0.03,
            )
        else:
            profile.update(
                device_type="cisco_ios",
                platform="ios",
                family="enterprise",
                os_family="ios",
                rule_id="cisco:ios",
            )
        return profile

    if vendor == "Cisco Meraki":
        profile.update(platform="meraki", family="cloud_managed", os_family="meraki", rule_id="cisco:meraki")
        return profile

    if vendor == "Juniper":
        profile.update(device_type="juniper_junos", os_family="junos")
        if _matches_any(text, (r"\bsrx\d", r"\bv?srx\b")):
            profile.update(platform="srx", family="security", rule_id="juniper:srx", confidence_bonus=0.03)
        elif _matches_any(text, (r"\b(qfx|ex)\d",)):
            profile.update(platform="switch", family="switching", rule_id="juniper:switch", confidence_bonus=0.02)
        elif _matches_any(text, (r"\b(mx|ptx)\d",)):
            profile.update(platform="router", family="routing", rule_id="juniper:router", confidence_bonus=0.02)
        else:
            profile.update(platform="junos", family="networking", rule_id="juniper:junos")
        return profile

    if vendor == "Arista":
        profile.update(device_type="arista_eos", platform="eos", family="switching", os_family="eos", rule_id="arista:eos")
        return profile

    if vendor == "Huawei":
        profile.update(device_type="huawei", platform="vrp", family="networking", os_family="vrp", rule_id="huawei:vrp")
        return profile

    if vendor == "H3C":
        profile.update(device_type="hp_comware", platform="comware", family="networking", os_family="comware", rule_id="h3c:comware")
        return profile

    if vendor in {"HP", "Aruba"}:
        if _matches_any(text, (r"\barubaos-cx\b", r"\baos-cx\b")):
            profile.update(device_type="aruba_os", platform="aos_cx", family="switching", os_family="aos_cx", rule_id=f"{vendor.lower()}:aos_cx", confidence_bonus=0.03)
        elif _matches_any(text, (r"\bcomware\b", r"\bh3c\b")):
            profile.update(device_type="hp_comware", platform="comware", family="networking", os_family="comware", rule_id=f"{vendor.lower()}:comware", confidence_bonus=0.02)
        elif _matches_any(text, (r"\bprocurve\b", r"\bprovision\b", r"\barubaos-switch\b", r"\baos-switch\b")):
            profile.update(
                device_type="aruba_os" if vendor == "Aruba" else "hp_procurve",
                platform="aos_switch",
                family="switching",
                os_family="aos_switch",
                rule_id=f"{vendor.lower()}:aos_switch",
                confidence_bonus=0.02,
            )
        else:
            profile.update(
                device_type="aruba_os" if vendor == "Aruba" else "hp_procurve",
                platform="procurve" if vendor == "HP" else "aruba_switch",
                family="switching",
                os_family="aos",
                rule_id=f"{vendor.lower()}:default",
            )
        return profile

    if vendor == "Dell":
        if _matches_any(text, (r"\bos10\b", r"smartfabric os10")):
            profile.update(device_type="dell_os10", platform="os10", family="switching", os_family="os10", rule_id="dell:os10", confidence_bonus=0.03)
        elif _matches_any(text, (r"force10", r"\bftos\b", r"powerconnect")):
            profile.update(device_type="dell_force10", platform="force10", family="switching", os_family="ftos", rule_id="dell:force10", confidence_bonus=0.03)
        else:
            profile.update(device_type="dell_os10", platform="os10", family="switching", os_family="os10", rule_id="dell:default")
        return profile

    if vendor == "Extreme":
        if _matches_any(text, (r"netiron", r"\bslx\b", r"\bvdx\b")):
            profile.update(device_type="extreme_netiron", platform="netiron", family="datacenter", os_family="netiron", rule_id="extreme:netiron", confidence_bonus=0.03)
        else:
            profile.update(device_type="extreme_exos", platform="exos", family="switching", os_family="exos", rule_id="extreme:exos")
        return profile

    if vendor == "Nokia":
        profile.update(device_type="nokia_sros", platform="sr_os", family="routing", os_family="sros", rule_id="nokia:sros")
        return profile

    if vendor == "Alcatel-Lucent":
        profile.update(device_type="alcatel_aos", platform="aos", family="switching", os_family="aos", rule_id="alcatel:aos")
        return profile

    if vendor == "Fortinet":
        profile.update(device_type="fortinet", platform="fortigate", family="security", os_family="fortios", rule_id="fortinet:fortios")
        return profile

    if vendor == "PaloAlto":
        profile.update(device_type="paloalto_panos", platform="firewall", family="security", os_family="panos", rule_id="paloalto:panos")
        return profile

    if vendor == "F5":
        profile.update(device_type="f5_ltm", platform="bigip", family="adc", os_family="tmos", rule_id="f5:tmos")
        return profile

    if vendor == "CheckPoint":
        profile.update(device_type="checkpoint_gaia", platform="gaia", family="security", os_family="gaia", rule_id="checkpoint:gaia")
        return profile

    if vendor == "Dasan":
        profile.update(device_type="dasan_nos", platform="nos", family="switching", os_family="nos", rule_id="dasan:nos")
        return profile

    if vendor == "Ubiquoss":
        is_l3 = _matches_any(text, (r"\bl3\b", r"\brouter\b", r"\brouting\b", r"\bunos\b"))
        profile.update(
            device_type="ubiquoss_l3" if is_l3 else "ubiquoss_l2",
            platform="l3" if is_l3 else "l2",
            family="networking",
            os_family="unos",
            rule_id="ubiquoss:l3" if is_l3 else "ubiquoss:l2",
            confidence_bonus=0.02 if is_l3 else 0.0,
        )
        return profile

    if vendor in {"HanDreamnet", "Handream"}:
        profile.update(device_type="handream_sg", platform="sg", family="switching", os_family="subgate", rule_id="handream:sg")
        return profile

    if vendor == "Piolink":
        profile.update(device_type="piolink_pas", platform="pas", family="security", os_family="pas", rule_id="piolink:pas")
        return profile

    if vendor in {"NST IC", "NST"}:
        profile.update(device_type="nst_switch", platform="switch", family="switching", os_family="domestic_cli", rule_id="nst:switch")
        return profile

    if vendor == "Soltech":
        profile.update(device_type="soltech_switch", platform="switch", family="switching", os_family="domestic_cli", rule_id="soltech:switch")
        return profile

    if vendor in {"CoreEdge", "Core Edge"}:
        profile.update(device_type="coreedge_switch", platform="switch", family="switching", os_family="domestic_cli", rule_id="coreedge:switch")
        return profile

    if vendor in {"Linux", "Windows"}:
        profile.update(platform=vendor.lower(), family="server", os_family=vendor.lower(), rule_id=f"{vendor.lower()}:default")
        return profile

    if vendor in {"AhnLab", "SECUI", "WINS", "AXGATE", "NexG", "Genians", "MonitorApp", "AirCuve", "NetMan", "MLSoft", "SGA", "Nixtech", "TrinitySoft"}:
        profile.update(platform="security_appliance", family="security", os_family="linux", rule_id=f"{vendor.lower()}:linux")
        return profile

    if vendor in {"EFMNetworks", "Mercury", "Davolink", "Samsung"}:
        profile.update(platform="embedded", family="networking", os_family="linux", rule_id=f"{vendor.lower()}:embedded")
        return profile

    if vendor in {"HFR", "Coweaver", "WooriNet", "Telefield"}:
        profile.update(device_type="cisco_ios", platform="cisco_like", family="switching", os_family="ios_like", rule_id=f"{vendor.lower()}:cisco_like")
        return profile

    return profile


def identify_vendor_by_oid(sys_oid: str, sys_descr: str = "") -> Tuple[str, float]:
    """
    Identifies vendor from sys_oid (primary) or sys_descr (fallback).
    Returns (VendorName, ConfidenceScore).
    """
    vendor, confidence, _, _ = _identify_vendor_internal(sys_oid, sys_descr)
    return vendor, confidence


def extract_model_from_descr(vendor: str, sys_descr: str) -> Optional[str]:
    """
    Attempts to extract the model number from sys_descr using regex patterns.
    """
    if not sys_descr or not vendor or vendor == "Unknown":
        return None

    patterns = MODEL_PATTERNS.get(vendor, [])
    for pattern in patterns:
        match = re.search(pattern, sys_descr, re.IGNORECASE)
        if match:
            if match.lastindex:
                return str(match.group(1) or "").strip()
            return str(match.group(0) or "").strip()
    return None


def fingerprint_device(
    sys_oid: str = "",
    sys_descr: str = "",
    sys_name: str = "",
    model: str = "",
) -> Dict[str, Any]:
    vendor, confidence, match_source, vendor_rule = _identify_vendor_internal(sys_oid, sys_descr)
    model_from_descr = extract_model_from_descr(vendor, sys_descr)
    platform = _platform_profile(vendor, sys_oid=sys_oid, sys_descr=sys_descr, sys_name=sys_name, model=model_from_descr or model)

    final_confidence = float(confidence or 0.0)
    if vendor != "Unknown":
        final_confidence = min(0.99, final_confidence + float(platform.get("confidence_bonus") or 0.0))

    return {
        "vendor": vendor,
        "confidence": round(final_confidence, 3),
        "device_type": str(platform.get("device_type") or VENDOR_TO_DRIVER.get(vendor, "unknown")),
        "platform": str(platform.get("platform") or ""),
        "family": str(platform.get("family") or ""),
        "os_family": str(platform.get("os_family") or ""),
        "match_source": match_source,
        "rule_id": str(platform.get("rule_id") or vendor_rule),
        "model_hint": model_from_descr or platform.get("model_hint"),
    }


def get_driver_for_vendor(
    vendor: str,
    sys_descr: str = "",
    model: str = "",
    sys_oid: str = "",
    sys_name: str = "",
) -> str:
    """
    Returns the best driver name for a vendor, optionally refined by fingerprint hints.
    """
    vendor_s = str(vendor or "").strip()
    if not vendor_s or vendor_s == "Unknown":
        if any((sys_descr, model, sys_oid, sys_name)):
            return str(fingerprint_device(sys_oid=sys_oid, sys_descr=sys_descr, sys_name=sys_name, model=model).get("device_type") or "unknown")
        return "unknown"

    profile = _platform_profile(vendor_s, sys_oid=sys_oid, sys_descr=sys_descr, sys_name=sys_name, model=model)
    driver = str(profile.get("device_type") or VENDOR_TO_DRIVER.get(vendor_s, "unknown"))
    return driver or "unknown"
