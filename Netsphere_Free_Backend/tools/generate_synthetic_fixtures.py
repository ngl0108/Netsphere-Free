from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "test-data" / "synthetic"
SCENARIO_DIRNAME = "scenarios"
TWIN_DIRNAME = "digital-twin"

@dataclass(frozen=True)
class VendorProfile:
    key: str
    device_type: str
    prefix: str
    sys_object_id: str
    platform: str
    os_family: str


VENDORS = [
    VendorProfile("cisco", "cisco_ios_xe", "C9K", "1.3.6.1.4.1.9.1.2504", "campus_switch", "ios_xe"),
    VendorProfile("arista", "arista_eos", "VEOS", "1.3.6.1.4.1.30065.1.3011", "datacenter_switch", "eos"),
    VendorProfile("juniper", "juniper_junos", "QFX", "1.3.6.1.4.1.2636.1.1.1.2.144", "datacenter_switch", "junos"),
    VendorProfile("fortinet", "fortinet", "FGT", "1.3.6.1.4.1.12356.101.1", "security", "fortios"),
    VendorProfile("paloalto", "paloalto_panos", "PA", "1.3.6.1.4.1.25461.2.3.30", "security", "panos"),
    VendorProfile("f5", "f5_ltm", "BIGIP", "1.3.6.1.4.1.3375.2.1.3.4.1", "adc", "tmos"),
    VendorProfile("nokia", "nokia_sros", "SR", "1.3.6.1.4.1.6527.1.3.4.1", "routing", "sros"),
    VendorProfile("vyos", "linux", "VYOS", "1.3.6.1.4.1.8072.3.2.10", "routing", "linux"),
    VendorProfile("mikrotik", "linux", "CHR", "1.3.6.1.4.1.14988.1", "routing", "routeros"),
]

SITES = ["hq-core", "branch-a", "branch-b", "dc-west", "dc-east"]


@dataclass(frozen=True)
class ScenarioPlan:
    name: str
    title: str
    device_count: int
    extra_link_ratio: float
    focus_areas: tuple[str, ...]
    link_protocols: tuple[str, ...]
    failure_ratio: float = 0.0
    security_ratio: float = 0.0


SCENARIO_PLANS = [
    ScenarioPlan(
        name="normal",
        title="Normal Operation",
        device_count=24,
        extra_link_ratio=1.4,
        focus_areas=("baseline", "inventory", "topology"),
        link_protocols=("lldp", "cdp", "fdb"),
    ),
    ScenarioPlan(
        name="large_scale",
        title="Large Scale",
        device_count=260,
        extra_link_ratio=1.8,
        focus_areas=("scale", "throughput", "topology"),
        link_protocols=("lldp", "fdb", "bgp"),
    ),
    ScenarioPlan(
        name="failure",
        title="Failure Spike",
        device_count=64,
        extra_link_ratio=1.5,
        focus_areas=("failure", "retry", "recovery"),
        link_protocols=("lldp", "cdp", "bgp"),
        failure_ratio=0.22,
    ),
    ScenarioPlan(
        name="security_incident",
        title="Security Incident",
        device_count=72,
        extra_link_ratio=1.4,
        focus_areas=("security", "policy", "isolation"),
        link_protocols=("lldp", "fdb", "vxlan"),
        security_ratio=0.18,
    ),
    ScenarioPlan(
        name="rollback_wave",
        title="Rollback Wave",
        device_count=48,
        extra_link_ratio=1.5,
        focus_areas=("change", "rollback", "approval"),
        link_protocols=("lldp", "lacp", "bgp"),
        failure_ratio=0.18,
    ),
    ScenarioPlan(
        name="hybrid_cloud",
        title="Hybrid Cloud Edge",
        device_count=54,
        extra_link_ratio=1.45,
        focus_areas=("hybrid", "cloud", "bgp"),
        link_protocols=("lldp", "bgp", "cloud"),
        failure_ratio=0.08,
    ),
    ScenarioPlan(
        name="wireless_edge",
        title="Wireless Edge",
        device_count=36,
        extra_link_ratio=1.3,
        focus_areas=("wireless", "edge", "telemetry"),
        link_protocols=("lldp", "capwap", "fdb"),
    ),
]


def _deterministic_timestamp(seed: int) -> str:
    base = datetime(2026, 2, 19, 0, 0, 0, tzinfo=timezone.utc)
    offset = timedelta(seconds=int(seed) % 86400)
    return (base + offset).isoformat()


def _scenario_seed(base_seed: int, label: str) -> int:
    digest = hashlib.sha256(f"{base_seed}:{label}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _vendor_tuple(rng: random.Random) -> VendorProfile:
    return rng.choice(VENDORS)


def _ip_for_index(idx: int, block: int) -> str:
    return f"10.{block}.{idx // 250}.{(idx % 250) + 1}"


def _device_name(vendor: VendorProfile, idx: int) -> str:
    return f"{vendor.prefix}-{idx:04d}"


def _build_devices(plan: ScenarioPlan, rng: random.Random) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for idx in range(plan.device_count):
        vendor = _vendor_tuple(rng)
        site = SITES[idx % len(SITES)]
        ip = _ip_for_index(idx, block=(11 + (idx % 6)))
        status = "online"
        tags: list[str] = []
        cloud_provider = None

        if plan.failure_ratio > 0 and rng.random() < plan.failure_ratio:
            status = rng.choice(["degraded", "offline"])
            tags.append("failure_candidate")
        if plan.security_ratio > 0 and rng.random() < plan.security_ratio:
            status = rng.choice(["online", "degraded"])
            tags.append("security_candidate")
        if "rollback" in plan.focus_areas and rng.random() < 0.25:
            tags.append("change_candidate")
        if "hybrid" in plan.focus_areas and rng.random() < 0.22:
            tags.append("cloud_gateway")
            cloud_provider = rng.choice(["aws", "azure", "gcp", "ncp"])
        if "wireless" in plan.focus_areas:
            if idx % 6 == 0:
                tags.append("wireless_controller")
            elif idx % 6 in {1, 2, 3}:
                tags.append("wireless_ap")
            else:
                tags.append("wireless_access")

        devices.append(
            {
                "id": idx + 1,
                "name": _device_name(vendor, idx + 1),
                "ip_address": ip,
                "vendor": vendor.key,
                "device_type": vendor.device_type,
                "site": site,
                "status": status,
                "confidence": round(0.72 + rng.random() * 0.28, 3),
                "platform": vendor.platform,
                "os_family": vendor.os_family,
                "cloud_provider": cloud_provider,
                "tags": tags,
            }
        )
    return devices


def _build_links(plan: ScenarioPlan, devices: list[dict[str, Any]], rng: random.Random, ratio: float) -> list[dict[str, Any]]:
    links: set[tuple[int, int]] = set()
    device_ids = [int(d["id"]) for d in devices]
    if len(device_ids) < 2:
        return []

    # Backbone ring
    for i in range(len(device_ids)):
        a = device_ids[i]
        b = device_ids[(i + 1) % len(device_ids)]
        links.add((min(a, b), max(a, b)))

    # Additional random edges
    target_count = int(len(device_ids) * ratio)
    while len(links) < target_count:
        a, b = rng.sample(device_ids, 2)
        links.add((min(a, b), max(a, b)))

    out: list[dict[str, Any]] = []
    device_by_id = {int(device["id"]): device for device in devices}
    for idx, (a, b) in enumerate(sorted(links), start=1):
        source = device_by_id.get(a, {})
        target = device_by_id.get(b, {})
        protocol = rng.choice(list(plan.link_protocols))
        if "hybrid" in plan.focus_areas and (
            "cloud_gateway" in list(source.get("tags") or []) or "cloud_gateway" in list(target.get("tags") or [])
        ):
            protocol = rng.choice(["cloud", "bgp"])
        out.append(
            {
                "id": idx,
                "source_id": a,
                "target_id": b,
                "protocol": protocol,
                "confidence": round(0.62 + rng.random() * 0.38, 3),
            }
        )
    return out


def _build_events(plan: ScenarioPlan, devices: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).replace(microsecond=0)

    if plan.name == "normal":
        categories = ["discovery_completed", "topology_refreshed", "sync_completed"]
        for i in range(20):
            events.append(
                {
                    "timestamp": now.isoformat(),
                    "type": categories[i % len(categories)],
                    "device_id": devices[i % len(devices)]["id"],
                    "severity": "info",
                }
            )

    if plan.name == "large_scale":
        for i in range(60):
            events.append(
                {
                    "timestamp": now.isoformat(),
                    "type": "discovery_batch_chunk",
                    "chunk_id": i + 1,
                    "processed": 80 + (i % 40),
                    "severity": "info",
                }
            )

    if plan.name == "failure":
        troubled = [d for d in devices if d["status"] != "online"] or devices[:8]
        for dev in troubled:
            events.append(
                {
                    "timestamp": now.isoformat(),
                    "type": rng.choice(["snmp_timeout", "ssh_auth_failed", "topology_link_flap"]),
                    "device_id": dev["id"],
                    "severity": "warning",
                }
            )
        events.append(
            {
                "timestamp": now.isoformat(),
                "type": "auto_rollback_executed",
                "device_count": max(1, len(troubled) // 2),
                "severity": "critical",
            }
        )

    if plan.name == "security_incident":
        suspects = [d for d in devices if "security_candidate" in d.get("tags", [])] or devices[:10]
        for dev in suspects:
            events.append(
                {
                    "timestamp": now.isoformat(),
                    "type": rng.choice(["rogue_mac_detected", "policy_violation", "unexpected_config_change"]),
                    "device_id": dev["id"],
                    "severity": "critical",
                }
            )
        events.append(
            {
                "timestamp": now.isoformat(),
                "type": "isolation_workflow_triggered",
                "device_count": len(suspects),
                "severity": "critical",
            }
        )

    if plan.name == "rollback_wave":
        candidates = [d for d in devices if "change_candidate" in d.get("tags", [])] or devices[:8]
        for dev in candidates[:10]:
            events.extend(
                [
                    {
                        "timestamp": now.isoformat(),
                        "type": "precheck_passed",
                        "device_id": dev["id"],
                        "severity": "info",
                    },
                    {
                        "timestamp": now.isoformat(),
                        "type": "approval_granted",
                        "device_id": dev["id"],
                        "severity": "info",
                    },
                    {
                        "timestamp": now.isoformat(),
                        "type": "wave_deploy_started",
                        "device_id": dev["id"],
                        "severity": "warning" if dev["status"] != "online" else "info",
                    },
                ]
            )
        events.append(
            {
                "timestamp": now.isoformat(),
                "type": "post_check_failed",
                "device_count": max(1, len(candidates) // 3),
                "severity": "warning",
            }
        )
        events.append(
            {
                "timestamp": now.isoformat(),
                "type": "auto_rollback_executed",
                "device_count": max(1, len(candidates) // 2),
                "severity": "critical",
            }
        )

    if plan.name == "hybrid_cloud":
        gateways = [d for d in devices if "cloud_gateway" in d.get("tags", [])] or devices[:6]
        for dev in gateways[:10]:
            events.extend(
                [
                    {
                        "timestamp": now.isoformat(),
                        "type": "cloud_inventory_sync_completed",
                        "device_id": dev["id"],
                        "severity": "info",
                    },
                    {
                        "timestamp": now.isoformat(),
                        "type": "hybrid_bgp_peer_up",
                        "device_id": dev["id"],
                        "severity": "info",
                    },
                ]
            )
        events.extend(
            [
                {
                    "timestamp": now.isoformat(),
                    "type": "hybrid_path_recomputed",
                    "device_count": len(gateways),
                    "severity": "info",
                },
                {
                    "timestamp": now.isoformat(),
                    "type": "cloud_link_latency_warning",
                    "device_count": max(1, len(gateways) // 2),
                    "severity": "warning",
                },
            ]
        )

    if plan.name == "wireless_edge":
        wireless_nodes = [d for d in devices if any(tag.startswith("wireless_") for tag in list(d.get("tags") or []))] or devices[:10]
        for dev in wireless_nodes[:12]:
            events.append(
                {
                    "timestamp": now.isoformat(),
                    "type": rng.choice(["wireless_ap_joined", "wireless_client_roam", "wlan_policy_sync"]),
                    "device_id": dev["id"],
                    "severity": "info",
                }
            )
        events.append(
            {
                "timestamp": now.isoformat(),
                "type": "wireless_client_auth_warning",
                "device_count": max(1, len(wireless_nodes) // 4),
                "severity": "warning",
            }
        )

    return events


def _scenario_kpi(plan: ScenarioPlan) -> dict[str, Any]:
    if plan.name == "normal":
        return {"first_map_seconds_p50": 168, "auto_reflection_rate_pct": 87.4, "false_positive_rate_pct": 3.9}
    if plan.name == "large_scale":
        return {"first_map_seconds_p50": 284, "auto_reflection_rate_pct": 82.2, "false_positive_rate_pct": 4.7}
    if plan.name == "failure":
        return {"first_map_seconds_p50": 233, "auto_reflection_rate_pct": 70.1, "false_positive_rate_pct": 8.8}
    if plan.name == "rollback_wave":
        return {"first_map_seconds_p50": 214, "auto_reflection_rate_pct": 76.9, "false_positive_rate_pct": 4.4}
    if plan.name == "hybrid_cloud":
        return {"first_map_seconds_p50": 226, "auto_reflection_rate_pct": 79.8, "false_positive_rate_pct": 5.1}
    if plan.name == "wireless_edge":
        return {"first_map_seconds_p50": 198, "auto_reflection_rate_pct": 84.3, "false_positive_rate_pct": 4.2}
    return {"first_map_seconds_p50": 241, "auto_reflection_rate_pct": 74.5, "false_positive_rate_pct": 6.1}


def _build_scenario(plan: ScenarioPlan, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    devices = _build_devices(plan, rng)
    links = _build_links(plan, devices, rng, ratio=plan.extra_link_ratio)
    events = _build_events(plan, devices, rng)
    vendor_mix = Counter(str(device.get("vendor") or "").strip() for device in devices)
    tag_mix = Counter(tag for device in devices for tag in list(device.get("tags") or []))
    return {
        "scenario": plan.name,
        "title": plan.title,
        "seed": seed,
        "generated_at": _deterministic_timestamp(seed),
        "focus_areas": list(plan.focus_areas),
        "protocols": sorted({str(link.get("protocol") or "").strip().lower() for link in links if str(link.get("protocol") or "").strip()}),
        "vendor_mix": {key: int(vendor_mix[key]) for key in sorted(vendor_mix.keys())},
        "tag_mix": {key: int(tag_mix[key]) for key in sorted(tag_mix.keys())},
        "counts": {
            "devices": len(devices),
            "links": len(links),
            "events": len(events),
        },
        "kpi_snapshot": _scenario_kpi(plan),
        "devices": devices,
        "links": links,
        "events": events,
    }


def _digital_twin_payload(seed: int) -> dict[str, Any]:
    rng = random.Random(seed)

    def vendor_profile(vendor: str) -> VendorProfile:
        return next((row for row in VENDORS if row.key == vendor), VendorProfile(vendor, "linux", "SW", "1.3.6.1.4.1.8072.3.2.10", "generic", "linux"))

    def snmp_sys(vendor: str) -> dict[str, Any]:
        profile = vendor_profile(vendor)
        return {
            "sysName": f"{profile.prefix}-{rng.randint(1, 999):03d}",
            "sysDescr": f"{vendor} synthetic {profile.platform}",
            "sysObjectID": profile.sys_object_id,
        }

    snmp = {"vendors": {}}
    ssh = {"vendors": {}}
    gnmi = {"vendors": {}}

    for profile in VENDORS:
        vendor = profile.key
        snmp["vendors"][vendor] = {
            "normal": {
                "status": "ok",
                "sysinfo": snmp_sys(vendor),
                "oids": {
                    "1.0.8802.1.1.2.1.3.2.0": "lldpEnabled",
                    "1.3.6.1.2.1.17.1.2.0": "bridgeEnabled",
                    "1.3.6.1.2.1.15.2.0": "bgpEnabled",
                },
            },
            "timeout": {"status": "timeout", "error": "SNMP request timed out"},
            "partial": {"status": "ok", "sysinfo": {"sysName": f"{vendor}-partial"}, "oids": {}},
            "malformed": {"status": "malformed", "sysinfo": "!!invalid!!"},
        }

        ssh["vendors"][vendor] = {
            "normal": {
                "status": "ok",
                "inventory": [
                    {"name": "chassis", "class_name": "chassis", "model_name": f"{profile.prefix}-core", "serial_number": f"{vendor[:2].upper()}-{rng.randint(100000, 999999)}"},
                    {"name": "linecard-1", "class_name": "module", "model_name": f"{profile.prefix}-lc", "serial_number": f"{vendor[:2].upper()}-{rng.randint(100000, 999999)}"},
                ],
                "neighbors": [
                    {"local_port": "Ethernet1", "neighbor_ip": f"10.{rng.randint(1, 200)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"},
                ],
            },
            "timeout": {"status": "timeout", "error": "SSH command timeout"},
            "partial": {"status": "ok", "inventory": [{"name": "chassis", "class_name": "chassis"}], "neighbors": []},
            "malformed": {"status": "malformed", "inventory": "bad-format"},
        }

        gnmi["vendors"][vendor] = {
            "normal": {
                "status": "ok",
                "telemetry": {
                    "interfaces_up": rng.randint(6, 48),
                    "interfaces_total": rng.randint(24, 96),
                    "cpu_pct": round(rng.uniform(8, 56), 2),
                    "mem_pct": round(rng.uniform(15, 72), 2),
                },
            },
            "timeout": {"status": "timeout", "error": "gNMI stream timeout"},
            "partial": {"status": "ok", "telemetry": {"interfaces_up": rng.randint(1, 12)}},
            "malformed": {"status": "malformed", "telemetry": ["unexpected", "list"]},
        }

    return {
        "meta": {
            "seed": seed,
            "generated_at": _deterministic_timestamp(seed),
            "cases": ["normal", "timeout", "partial", "malformed"],
            "vendors": [profile.key for profile in VENDORS],
        },
        "snmp": snmp,
        "ssh": ssh,
        "gnmi": gnmi,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _build_manifest(base_seed: int, written_files: list[Path]) -> dict[str, Any]:
    return {
        "base_seed": base_seed,
        "generated_at": _deterministic_timestamp(base_seed),
        "files": [
            {"path": str(path.relative_to(REPO_ROOT)).replace("\\", "/"), "sha256": _sha256(path)}
            for path in sorted(written_files)
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic synthetic fixtures for NetSphere test pipelines.")
    parser.add_argument("--seed", type=int, default=20260219, help="Deterministic base seed.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT_DIR), help="Output directory.")
    args = parser.parse_args()

    out_root = Path(args.output_dir).resolve()
    scenario_root = out_root / SCENARIO_DIRNAME
    twin_root = out_root / TWIN_DIRNAME
    written: list[Path] = []

    for plan in SCENARIO_PLANS:
        seed = _scenario_seed(args.seed, f"scenario:{plan.name}")
        payload = _build_scenario(plan, seed=seed)
        path = scenario_root / f"{plan.name}.json"
        _write_json(path, payload)
        written.append(path)

    twin_payload = _digital_twin_payload(_scenario_seed(args.seed, "digital-twin"))
    for protocol in ("snmp", "ssh", "gnmi"):
        path = twin_root / f"{protocol}.json"
        _write_json(path, {"meta": twin_payload["meta"], **twin_payload[protocol]})
        written.append(path)

    manifest_path = out_root / "manifest.json"
    _write_json(manifest_path, _build_manifest(args.seed, written))
    written.append(manifest_path)

    print(f"Synthetic fixtures generated: {len(written)} files")
    for file_path in sorted(written):
        print(f"- {file_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
