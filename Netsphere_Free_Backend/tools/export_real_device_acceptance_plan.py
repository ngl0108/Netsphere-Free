#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_MATRIX_PATH = REPO_ROOT / "docs" / "reports" / "vendor-support-matrix.latest.json"
DEFAULT_JSON_OUT = REPO_ROOT / "docs" / "reports" / "real-device-acceptance.latest.json"
DEFAULT_MD_OUT = REPO_ROOT / "docs" / "reports" / "real-device-acceptance.latest.md"
DEFAULT_CSV_OUT = REPO_ROOT / "docs" / "reports" / "real-device-acceptance-checklist.latest.csv"


SCENARIO_SETS: dict[str, list[str]] = {
    "routing_switching": [
        "inventory_facts",
        "discovery_import",
        "l2_topology_reflection",
        "l3_topology_reflection",
        "path_trace",
        "config_backup",
        "template_dry_run",
        "approval_trace",
        "rollback",
        "diagnosis",
    ],
    "overlay_fabric": [
        "inventory_facts",
        "discovery_import",
        "l2_topology_reflection",
        "l3_topology_reflection",
        "vxlan_overlay_visibility",
        "bgp_evpn_visibility",
        "path_trace",
        "config_backup",
        "template_dry_run",
        "approval_trace",
        "rollback",
        "diagnosis",
    ],
    "security": [
        "inventory_facts",
        "discovery_import",
        "route_visibility",
        "path_trace",
        "config_backup",
        "template_dry_run",
        "approval_trace",
        "rollback",
        "diagnosis",
        "northbound_event_delivery",
    ],
    "wireless": [
        "inventory_facts",
        "discovery_import",
        "wireless_summary",
        "config_backup",
        "approval_trace",
        "diagnosis",
    ],
    "load_balancer": [
        "inventory_facts",
        "discovery_import",
        "route_visibility",
        "config_backup",
        "template_dry_run",
        "approval_trace",
        "rollback",
        "diagnosis",
    ],
    "generic": [
        "inventory_facts",
        "discovery_import",
        "config_backup",
        "approval_trace",
        "diagnosis",
    ],
}


ARTIFACT_REQUIREMENTS = [
    "raw_cli_text",
    "version_and_model",
    "interface_summary",
    "neighbor_detail",
    "running_or_current_config",
    "feature_on_capture",
    "feature_off_capture",
]


COMMAND_PROFILES: dict[str, dict[str, Any]] = {
    "cisco_ios_xe": {
        "platform_family": "Cisco IOS / IOS XE",
        "feature_class": "routing_switching",
        "commands": [
            "show version",
            "show inventory",
            "show ip interface brief",
            "show vlan brief",
            "show mac address-table",
            "show lldp neighbors detail",
            "show cdp neighbors detail",
            "show ip route",
            "show ip ospf neighbor",
            "show ip bgp summary",
            "show running-config",
        ],
    },
    "cisco_nxos": {
        "platform_family": "Cisco NX-OS",
        "feature_class": "overlay_fabric",
        "commands": [
            "show version",
            "show inventory",
            "show interface status",
            "show vlan brief",
            "show mac address-table",
            "show lldp neighbors detail",
            "show bgp all summary",
            "show nve peers",
            "show bgp l2vpn evpn summary",
            "show vxlan vni",
            "show running-config",
        ],
    },
    "cisco_wlc": {
        "platform_family": "Cisco Wireless Controller",
        "feature_class": "wireless",
        "commands": [
            "show sysinfo",
            "show interface summary",
            "show wlan summary",
            "show ap summary",
            "show cdp neighbors",
            "show lldp neighbors",
        ],
    },
    "junos": {
        "platform_family": "Juniper Junos",
        "feature_class": "overlay_fabric",
        "commands": [
            "show version",
            "show chassis hardware",
            "show interfaces terse",
            "show vlans",
            "show ethernet-switching table",
            "show lldp neighbors detail",
            "show route",
            "show ospf neighbor",
            "show bgp summary",
            "show evpn instance",
            "show configuration | display set",
        ],
    },
    "arista_eos": {
        "platform_family": "Arista EOS",
        "feature_class": "overlay_fabric",
        "commands": [
            "show version",
            "show inventory",
            "show interfaces status",
            "show vlan",
            "show mac address-table",
            "show lldp neighbors detail",
            "show ip route",
            "show ip bgp summary",
            "show bgp evpn summary",
            "show vxlan vni",
            "show running-config",
        ],
    },
    "huawei_vrp": {
        "platform_family": "Huawei VRP / CloudEngine",
        "feature_class": "overlay_fabric",
        "commands": [
            "display version",
            "display device",
            "display interface brief",
            "display vlan",
            "display mac-address",
            "display lldp neighbor-information verbose",
            "display ip routing-table",
            "display ospf peer",
            "display bgp peer",
            "display vxlan tunnel",
            "display current-configuration",
        ],
    },
    "aruba_switch": {
        "platform_family": "Aruba AOS-Switch",
        "feature_class": "routing_switching",
        "commands": [
            "show version",
            "show interfaces brief",
            "show vlan",
            "show mac-address",
            "show lldp info remote-device",
            "show trunks",
            "show running-config",
        ],
    },
    "aruba_cx": {
        "platform_family": "Aruba AOS-CX",
        "feature_class": "routing_switching",
        "commands": [
            "show version",
            "show interface brief",
            "show vlan",
            "show mac-address-table",
            "show lldp neighbor-info detail",
            "show ip route",
            "show bgp summary",
            "show running-config",
        ],
    },
    "h3c_comware": {
        "platform_family": "H3C Comware",
        "feature_class": "routing_switching",
        "commands": [
            "display version",
            "display device",
            "display interface brief",
            "display vlan",
            "display mac-address",
            "display lldp neighbor-information verbose",
            "display ip routing-table",
            "display current-configuration",
        ],
    },
    "dell_os10": {
        "platform_family": "Dell OS10 / Force10",
        "feature_class": "overlay_fabric",
        "commands": [
            "show version",
            "show inventory",
            "show interfaces status",
            "show vlan",
            "show mac address-table",
            "show lldp neighbors detail",
            "show ip route",
            "show bgp summary",
            "show virtual-network",
            "show running-configuration",
        ],
    },
    "extreme": {
        "platform_family": "Extreme EXOS / NetIron",
        "feature_class": "routing_switching",
        "commands": [
            "show version",
            "show ports",
            "show vlan",
            "show fdb",
            "show lldp neighbors detail",
            "show iproute",
            "show configuration",
        ],
    },
    "nokia_sros": {
        "platform_family": "Nokia SR OS",
        "feature_class": "routing_switching",
        "commands": [
            "show version",
            "show chassis",
            "show router interface",
            "show service id",
            "show router route-table",
            "show router bgp summary",
            "show router ospf neighbor",
            "admin display-config",
        ],
    },
    "alcatel_aos": {
        "platform_family": "Alcatel OmniSwitch AOS",
        "feature_class": "routing_switching",
        "commands": [
            "show chassis",
            "show interfaces",
            "show vlan",
            "show mac-learning",
            "show lldp remote-system",
            "show configuration snapshot",
        ],
    },
    "fortigate": {
        "platform_family": "Fortinet FortiGate",
        "feature_class": "security",
        "commands": [
            "get system status",
            "show system interface",
            "get system arp",
            "get router info routing-table all",
            "get router info ospf neighbor",
            "get router info bgp summary",
            "show full-configuration",
        ],
    },
    "paloalto": {
        "platform_family": "Palo Alto PAN-OS",
        "feature_class": "security",
        "commands": [
            "show system info",
            "show interface all",
            "show routing route",
            "show routing protocol bgp summary",
            "show routing protocol ospf neighbor",
            "show config running",
        ],
    },
    "checkpoint": {
        "platform_family": "Check Point Gaia",
        "feature_class": "security",
        "commands": [
            "show version all",
            "show interfaces all",
            "show route all",
            "show configuration",
        ],
    },
    "f5_bigip": {
        "platform_family": "F5 BIG-IP / TMOS",
        "feature_class": "load_balancer",
        "commands": [
            "tmsh show sys hardware",
            "tmsh show net interface",
            "tmsh show net arp",
            "tmsh show net route",
            "tmsh list net vlan all",
            "tmsh list net self all",
            "tmsh list sys config",
        ],
    },
    "domestic_switch": {
        "platform_family": "Domestic Switch NOS",
        "feature_class": "routing_switching",
        "commands": [
            "show version or equivalent",
            "show interface summary",
            "show vlan",
            "show mac-address",
            "show lldp neighbors detail",
            "show ip route",
            "show running-config or current-config",
        ],
    },
    "domestic_security": {
        "platform_family": "Domestic Security / UTM",
        "feature_class": "security",
        "commands": [
            "show version or equivalent",
            "show interface summary",
            "show arp",
            "show route",
            "show policy summary",
            "show running-config or current-config",
        ],
    },
    "linux_like": {
        "platform_family": "Linux-like Network OS",
        "feature_class": "generic",
        "commands": [
            "hostnamectl",
            "ip link show",
            "ip addr show",
            "ip route show",
            "bridge link show",
            "cat running config equivalent",
        ],
    },
    "generic_network": {
        "platform_family": "Generic Network Device",
        "feature_class": "generic",
        "commands": [
            "show version",
            "show interface summary",
            "show neighbors detail",
            "show route",
            "show running-config",
        ],
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return payload


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().lower()


def _command_profile_for_device_type(device_type: str) -> str:
    dt = _normalize_token(device_type)
    if dt in {"cisco_nxos"}:
        return "cisco_nxos"
    if dt in {"cisco_ios", "cisco_ios_xe"}:
        return "cisco_ios_xe"
    if dt in {"cisco_wlc"}:
        return "cisco_wlc"
    if dt.startswith("juniper") or dt.startswith("junos"):
        return "junos"
    if dt in {"arista", "arista_eos"}:
        return "arista_eos"
    if dt in {"huawei_vrp", "huawei_cloudengine", "huawei"}:
        return "huawei_vrp"
    if dt in {"aruba_os", "hp_procurve"}:
        return "aruba_switch"
    if dt in {"aruba_cx"}:
        return "aruba_cx"
    if dt in {"hp_comware", "h3c_comware"}:
        return "h3c_comware"
    if dt in {"dell_os10", "dell_force10"}:
        return "dell_os10"
    if dt in {"extreme_exos", "extreme_netiron"}:
        return "extreme"
    if dt in {"nokia_sros"}:
        return "nokia_sros"
    if dt in {"alcatel_aos"}:
        return "alcatel_aos"
    if dt in {"fortinet", "fortigate"}:
        return "fortigate"
    if dt in {"paloalto_panos", "paloalto"}:
        return "paloalto"
    if dt in {"checkpoint_gaia"}:
        return "checkpoint"
    if dt in {"f5_ltm", "f5_bigip"}:
        return "f5_bigip"
    if dt.startswith(("ubiquoss", "dasan", "handream", "piolink", "soltech", "coreedge", "nst", "sga")):
        return "domestic_switch"
    if dt.startswith(("ahnlab", "secui", "wins", "axgate", "nexg", "genians", "monitorapp", "aircuve", "netman", "mlsoft", "trinitysoft")):
        return "domestic_security"
    if dt.startswith(("linux", "vyos", "mikrotik")):
        return "linux_like"
    return "generic_network"


def _acceptance_wave(readiness: str, profile_id: str) -> int:
    rd = _normalize_token(readiness)
    if profile_id in {"cisco_ios_xe", "cisco_nxos", "junos", "arista_eos", "fortigate", "paloalto", "dell_os10", "huawei_vrp"}:
        return 1 if rd in {"full", "extended", "basic"} else 2
    if rd in {"full", "extended"}:
        return 1
    if rd == "basic":
        return 2
    return 3


def _required_artifacts_for_feature_class(feature_class: str) -> list[str]:
    artifacts = list(ARTIFACT_REQUIREMENTS)
    if feature_class in {"routing_switching", "overlay_fabric", "security", "load_balancer"}:
        artifacts.extend(["routing_table_capture", "arp_or_mac_table_capture"])
    if feature_class == "overlay_fabric":
        artifacts.extend(["bgp_capture", "vxlan_or_evpn_capture"])
    if feature_class == "wireless":
        artifacts.extend(["wlan_summary_capture", "ap_summary_capture"])
    if feature_class == "security":
        artifacts.extend(["policy_summary_capture", "nat_or_session_capture"])
    return artifacts


def build_real_device_acceptance_plan(matrix_payload: dict[str, Any]) -> dict[str, Any]:
    rows_in = list(matrix_payload.get("rows") or [])
    readiness_counts = dict((((matrix_payload.get("summary") or {}).get("readiness") or {})))
    plan_rows: list[dict[str, Any]] = []
    wave_counts = {"wave_1": 0, "wave_2": 0, "wave_3": 0}

    for raw in rows_in:
        if not isinstance(raw, dict):
            continue
        device_type = str(raw.get("device_type") or "").strip()
        if not device_type:
            continue
        profile_id = _command_profile_for_device_type(device_type)
        profile = COMMAND_PROFILES[profile_id]
        feature_class = str(profile["feature_class"])
        scenarios = list(SCENARIO_SETS.get(feature_class) or SCENARIO_SETS["generic"])
        wave = _acceptance_wave(str(raw.get("readiness") or ""), profile_id)
        wave_counts[f"wave_{wave}"] = int(wave_counts.get(f"wave_{wave}") or 0) + 1
        commands = list(profile.get("commands") or [])
        plan_rows.append(
            {
                "device_type": device_type,
                "readiness": str(raw.get("readiness") or "unknown"),
                "readiness_score": int(raw.get("readiness_score") or 0),
                "covered": bool(raw.get("covered")),
                "suggested_wave": int(wave),
                "command_profile": profile_id,
                "platform_family": str(profile.get("platform_family") or profile_id),
                "feature_class": feature_class,
                "driver_modes": list(raw.get("driver_modes") or []),
                "fixture_groups": list(raw.get("fixture_groups") or []),
                "mandatory_scenarios": scenarios,
                "required_artifacts": _required_artifacts_for_feature_class(feature_class),
                "required_commands": commands,
                "capture_requirements": {
                    "raw_cli_text": True,
                    "feature_on_capture": True,
                    "feature_off_capture": True,
                    "config_section_capture": True,
                },
            }
        )

    plan_rows.sort(key=lambda row: (int(row.get("suggested_wave") or 9), -int(row.get("readiness_score") or 0), str(row.get("device_type") or "")))

    return {
        "generated_at": _now_iso(),
        "source_matrix_generated_at": matrix_payload.get("generated_at"),
        "summary": {
            "total_device_types": len(plan_rows),
            "wave_counts": wave_counts,
            "readiness_counts": readiness_counts,
            "command_profile_count": len({str(row["command_profile"]) for row in plan_rows}),
            "feature_classes": sorted({str(row["feature_class"]) for row in plan_rows}),
        },
        "scenario_catalog": {
            key: list(value)
            for key, value in sorted(SCENARIO_SETS.items(), key=lambda item: item[0])
        },
        "rows": plan_rows,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "wave",
                "device_type",
                "platform_family",
                "readiness",
                "feature_class",
                "command_profile",
                "mandatory_scenarios",
                "required_commands",
                "required_artifacts",
                "device_ready",
                "capture_complete",
                "import_complete",
                "discovery_pass",
                "topology_pass",
                "config_pass",
                "acceptance_pass",
                "notes",
            ],
        )
        writer.writeheader()
        for row in list(payload.get("rows") or []):
            writer.writerow(
                {
                    "wave": int(row.get("suggested_wave") or 0),
                    "device_type": row.get("device_type"),
                    "platform_family": row.get("platform_family"),
                    "readiness": row.get("readiness"),
                    "feature_class": row.get("feature_class"),
                    "command_profile": row.get("command_profile"),
                    "mandatory_scenarios": " | ".join(list(row.get("mandatory_scenarios") or [])),
                    "required_commands": " | ".join(list(row.get("required_commands") or [])),
                    "required_artifacts": " | ".join(list(row.get("required_artifacts") or [])),
                    "device_ready": "",
                    "capture_complete": "",
                    "import_complete": "",
                    "discovery_pass": "",
                    "topology_pass": "",
                    "config_pass": "",
                    "acceptance_pass": "",
                    "notes": "",
                }
            )


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    lines = [
        "# Real Device Acceptance Plan",
        "",
        f"- Generated at: {payload.get('generated_at')}",
        f"- Source vendor matrix: {payload.get('source_matrix_generated_at')}",
        f"- Total device types: {summary.get('total_device_types', 0)}",
        f"- Wave 1 / 2 / 3: {((summary.get('wave_counts') or {}).get('wave_1', 0))} / {((summary.get('wave_counts') or {}).get('wave_2', 0))} / {((summary.get('wave_counts') or {}).get('wave_3', 0))}",
        "",
        "## Usage",
        "",
        "1. Reserve one representative device per `platform_family`.",
        "2. Capture all commands in raw text for both populated and empty feature states.",
        "3. Import device into NetSphere and execute the mandatory scenarios.",
        "4. Mark the CSV checklist and archive raw outputs alongside the run report.",
        "",
        "## Acceptance rows",
        "",
        "| Wave | Device Type | Platform Family | Readiness | Scenarios |",
        "|---|---|---|---|---|",
    ]
    for row in list(payload.get("rows") or []):
        lines.append(
            f"| {row.get('suggested_wave')} | `{row.get('device_type')}` | {row.get('platform_family')} | {row.get('readiness')} | {', '.join(list(row.get('mandatory_scenarios') or [])[:4])}... |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a real-device acceptance plan and checklist from vendor support matrix.")
    parser.add_argument("--matrix-json", default=str(DEFAULT_MATRIX_PATH), help="Path to vendor-support-matrix JSON.")
    parser.add_argument("--latest-json-path", default=str(DEFAULT_JSON_OUT), help="Output JSON path.")
    parser.add_argument("--latest-md-path", default=str(DEFAULT_MD_OUT), help="Output Markdown path.")
    parser.add_argument("--latest-csv-path", default=str(DEFAULT_CSV_OUT), help="Output CSV checklist path.")
    args = parser.parse_args()

    matrix_payload = _load_json(Path(args.matrix_json).resolve())
    payload = build_real_device_acceptance_plan(matrix_payload)
    json_path = Path(args.latest_json_path).resolve()
    md_path = Path(args.latest_md_path).resolve()
    csv_path = Path(args.latest_csv_path).resolve()

    _write_json(json_path, payload)
    _write_markdown(md_path, payload)
    _write_csv(csv_path, payload)

    print(f"Acceptance plan JSON: {json_path}")
    print(f"Acceptance plan Markdown: {md_path}")
    print(f"Acceptance checklist CSV: {csv_path}")
    print(
        "Acceptance plan summary: "
        f"rows={((payload.get('summary') or {}).get('total_device_types') or 0)} "
        f"wave1={(((payload.get('summary') or {}).get('wave_counts') or {}).get('wave_1') or 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
