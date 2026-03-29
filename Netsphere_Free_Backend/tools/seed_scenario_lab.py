from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from sqlalchemy.orm import Session

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.core.security import get_password_hash
from app.db.session import SessionLocal
from app.models.approval import ApprovalRequest
from app.models.audit import AuditLog
from app.models.asset_change_event import AssetChangeEvent
from app.models.cloud import CloudAccount, CloudResource
from app.models.credentials import SnmpCredentialProfile  # noqa: F401
from app.models.device import Device, EventLog, Interface, Issue, Link, Site, SystemMetric
from app.models.known_error import KnownErrorEntry
from app.models.monitoring_profile import MonitoringProfileAssignment
from app.models.operation_action import OperationAction
from app.models.service_group import ServiceGroup, ServiceGroupMember
from app.models.tenant import Tenant
from app.models.topology import TopologySnapshot
from app.models.user import User
from app.models.user_session import UserSession
from app.services.monitoring_profile_service import MonitoringProfileService
from app.services.preview_edition_service import PreviewEditionService
from app.services.state_history_service import StateHistoryService
from app.services.intent_service import IntentService


ROLE_DEVICE_POOL: Dict[str, List[Dict[str, str]]] = {
    "core": [
        {"device_type": "cisco_ios", "model": "Catalyst 9500", "vendor": "Cisco"},
        {"device_type": "juniper_junos", "model": "EX4650", "vendor": "Juniper"},
    ],
    "distribution": [
        {"device_type": "arista_eos", "model": "7050SX3", "vendor": "Arista"},
        {"device_type": "cisco_ios", "model": "Catalyst 9300", "vendor": "Cisco"},
    ],
    "access": [
        {"device_type": "dasan_nos", "model": "V5124XG", "vendor": "Dasan"},
        {"device_type": "ubiquoss_l2", "model": "UB-L2-48", "vendor": "Ubiquoss"},
        {"device_type": "handream_sg", "model": "SG2400", "vendor": "HanDreamnet"},
        {"device_type": "soltech_switch", "model": "SFC-2400", "vendor": "Soltech"},
        {"device_type": "coreedge_switch", "model": "CE4824", "vendor": "CoreEdge"},
        {"device_type": "nst_switch", "model": "NST-4200", "vendor": "NST"},
    ],
    "branch_router": [
        {"device_type": "cisco_ios", "model": "ISR 4331", "vendor": "Cisco"},
        {"device_type": "juniper_junos", "model": "SRX345", "vendor": "Juniper"},
    ],
    "security": [
        {"device_type": "fortinet", "model": "FortiGate 100F", "vendor": "Fortinet"},
        {"device_type": "paloalto_panos", "model": "PA-3220", "vendor": "Palo Alto"},
    ],
    "wireless_controller": [
        {"device_type": "cisco_ios", "model": "Catalyst 9800-L", "vendor": "Cisco"},
    ],
    "wireless_ap": [
        {"device_type": "cisco_ios", "model": "Catalyst 9120", "vendor": "Cisco"},
        {"device_type": "linux", "model": "Campus AP", "vendor": "Generic"},
    ],
    "spine": [
        {"device_type": "arista_eos", "model": "7280R3", "vendor": "Arista"},
        {"device_type": "juniper_junos", "model": "QFX10002", "vendor": "Juniper"},
    ],
    "leaf": [
        {"device_type": "arista_eos", "model": "7050X4", "vendor": "Arista"},
        {"device_type": "cisco_ios", "model": "Nexus 93180", "vendor": "Cisco"},
    ],
    "border_leaf": [
        {"device_type": "arista_eos", "model": "7280R", "vendor": "Arista"},
        {"device_type": "cisco_ios", "model": "Nexus 9364C", "vendor": "Cisco"},
    ],
    "adc": [
        {"device_type": "f5_ltm", "model": "BIG-IP i5800", "vendor": "F5"},
    ],
    "cloud_gateway": [
        {"device_type": "linux", "model": "Hybrid Gateway", "vendor": "NetSphere"},
    ],
}

ROLE_PRIORITY: Dict[str, int] = {
    "core": 100,
    "spine": 98,
    "border_leaf": 96,
    "distribution": 92,
    "security": 88,
    "cloud_gateway": 85,
    "branch_router": 82,
    "leaf": 78,
    "adc": 74,
    "wireless_controller": 68,
    "access": 60,
    "wireless_ap": 42,
}

ROLE_SHORT: Dict[str, str] = {
    "core": "CORE",
    "distribution": "DIST",
    "access": "ACC",
    "branch_router": "RTR",
    "security": "SEC",
    "wireless_controller": "WLC",
    "wireless_ap": "AP",
    "spine": "SPN",
    "leaf": "LEF",
    "border_leaf": "BLEF",
    "adc": "ADC",
    "cloud_gateway": "CGW",
}


@dataclass
class SiteBlueprint:
    code: str
    name: str
    site_type: str
    parent_code: str | None
    role_counts: Dict[str, int]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def role_to_user_role(raw_role: str) -> str:
    normalized = str(raw_role or "").strip().lower()
    if normalized == "editor":
        return "operator"
    if normalized in {"admin", "operator", "viewer"}:
        return normalized
    return "viewer"


class ScenarioSeeder:
    def __init__(self, db: Session, manifest: Dict[str, Any], user_password: str) -> None:
        self.db = db
        self.manifest = manifest
        self.slug = str(manifest.get("slug") or "scenario-lab").strip()
        if not self.slug:
            raise ValueError("Scenario slug is required.")
        self.user_password = user_password
        self.random = random.Random(self.slug)
        self.now = utcnow()
        self.lab_prefix = f"[LAB {self.slug}]"
        self.lab_asset_prefix = f"lab:{self.slug}:"
        self.device_prefix = "LAB-" + self.slug.replace("-", "_").upper()
        self.users: List[User] = []
        self.sites: Dict[str, Site] = {}
        self.devices: List[Device] = []
        self.cloud_accounts: List[CloudAccount] = []
        self.cloud_resources: List[CloudResource] = []
        self.service_groups: List[ServiceGroup] = []
        self.issues: List[Issue] = []
        self.approvals: List[ApprovalRequest] = []
        self.known_errors: List[KnownErrorEntry] = []
        self.topology_snapshots: List[TopologySnapshot] = []
        self.state_snapshots: List[Dict[str, Any]] = []
        self.tenant: Tenant | None = None
        self.interfaces: Dict[tuple[int, str], Interface] = {}

    def seed(self, wipe_existing: bool = True) -> Dict[str, Any]:
        if wipe_existing:
            self.cleanup()
        MonitoringProfileService.install_defaults(self.db)
        self.tenant = self._create_tenant()
        self.users = self._create_users(self.tenant)
        self._ensure_preview_policy_for_free()
        blueprints = self._build_site_blueprints()
        self.sites = self._create_sites(blueprints)
        self.devices = self._create_devices(blueprints, self.sites, self.users, self.tenant)
        self._assign_management_states(self.devices)
        self.db.commit()
        self._install_profile_assignments(self.devices)
        self._create_links(blueprints)
        self.cloud_accounts, self.cloud_resources = self._create_cloud_inventory(self.tenant)
        self.service_groups = self._create_service_groups(self.devices, self.cloud_resources)
        self.issues = self._create_issues_and_actions(self.devices, self.users)
        self.approvals = self._create_approvals(self.users)
        self.known_errors = self._create_known_errors()
        self._create_asset_change_events()
        self.topology_snapshots = self._create_topology_snapshots()
        self.state_snapshots = self._create_state_history_snapshots()
        self.db.commit()
        return self._build_summary()

    def cleanup(self) -> None:
        label_prefix = self.lab_prefix
        asset_prefix = self.lab_asset_prefix
        username_prefix = f"lab_{self.slug.replace('-', '_')}_"
        lab_devices = self.db.query(Device).filter(Device.name.like(f"{self.device_prefix}%")).all()
        lab_device_ids = [int(row.id) for row in lab_devices if row.id is not None]

        for row in (
            self.db.query(EventLog)
            .filter(EventLog.event_id == StateHistoryService.SNAPSHOT_EVENT_ID)
            .all()
        ):
            try:
                payload = json.loads(str(row.message or "{}"))
            except Exception:
                payload = {}
            if str(payload.get("label") or "").startswith(label_prefix):
                self.db.delete(row)

        for row in self.db.query(TopologySnapshot).filter(TopologySnapshot.label.like(f"{label_prefix}%")).all():
            self.db.delete(row)
        for row in self.db.query(AssetChangeEvent).filter(AssetChangeEvent.asset_key.like(f"{asset_prefix}%")).all():
            self.db.delete(row)
        for row in self.db.query(ApprovalRequest).filter(ApprovalRequest.title.like(f"{label_prefix}%")).all():
            self.db.delete(row)
        for row in self.db.query(OperationAction).filter(OperationAction.title.like(f"{label_prefix}%")).all():
            self.db.delete(row)
        for row in self.db.query(Issue).filter(Issue.title.like(f"{label_prefix}%")).all():
            self.db.delete(row)
        for row in self.db.query(KnownErrorEntry).filter(KnownErrorEntry.title.like(f"{label_prefix}%")).all():
            self.db.delete(row)
        for row in self.db.query(ServiceGroup).filter(ServiceGroup.name.like(f"{label_prefix}%")).all():
            self.db.delete(row)
        for row in self.db.query(CloudAccount).filter(CloudAccount.name.like(f"{label_prefix}%")).all():
            self.db.delete(row)
        if lab_device_ids:
            for row in (
                self.db.query(MonitoringProfileAssignment)
                .filter(MonitoringProfileAssignment.device_id.in_(lab_device_ids))
                .all()
            ):
                self.db.delete(row)
        for row in lab_devices:
            self.db.delete(row)
        for row in self.db.query(Site).filter(Site.name.like(f"{label_prefix}%")).all():
            self.db.delete(row)
        lab_users = self.db.query(User).filter(User.username.like(f"{username_prefix}%")).all()
        lab_user_ids = [int(row.id) for row in lab_users if row.id is not None]
        if lab_user_ids:
            for row in self.db.query(AuditLog).filter(AuditLog.user_id.in_(lab_user_ids)).all():
                self.db.delete(row)
            for row in self.db.query(UserSession).filter(UserSession.user_id.in_(lab_user_ids)).all():
                self.db.delete(row)
        for row in lab_users:
            self.db.delete(row)
        tenant_name = f"{label_prefix} Tenant"
        tenant = self.db.query(Tenant).filter(Tenant.name == tenant_name).first()
        if tenant is not None:
            self.db.delete(tenant)
        self.db.commit()

    def _create_tenant(self) -> Tenant:
        name = f"{self.lab_prefix} Tenant"
        tenant = self.db.query(Tenant).filter(Tenant.name == name).first()
        if tenant is None:
            tenant = Tenant(
                name=name,
                description=f"Scenario Lab tenant for {self.slug}",
                plan_type=str(self.manifest.get("edition") or "free"),
                max_devices=10000,
                is_active=True,
            )
            self.db.add(tenant)
            self.db.flush()
        return tenant

    def _create_users(self, tenant: Tenant) -> List[User]:
        created: List[User] = []
        counts = dict(self.manifest.get("user_counts") or {})
        for raw_role, total in counts.items():
            role = role_to_user_role(raw_role)
            for index in range(1, int(total or 0) + 1):
                username = f"lab_{self.slug.replace('-', '_')}_{role}_{index:02d}"
                user = self.db.query(User).filter(User.username == username).first()
                if user is None:
                    user = User(
                        username=username,
                        email=f"{username}@lab.example.com",
                        hashed_password=get_password_hash(self.user_password),
                        full_name=f"LAB {self.slug} {role.title()} {index:02d}",
                        role=role,
                        is_active=True,
                        eula_accepted=True,
                        must_change_password=False,
                        tenant_id=tenant.id,
                    )
                    self.db.add(user)
                    self.db.flush()
                created.append(user)
        return created

    def _ensure_preview_policy_for_free(self) -> None:
        edition = str(self.manifest.get("edition") or "").strip().lower()
        if edition != "free":
            return
        admin_user = next((row for row in self.users if str(row.role or "").strip().lower() == "admin"), None)
        policy = PreviewEditionService.get_policy(self.db)
        if bool(policy.get("upload_decision_recorded")) and bool(policy.get("upload_locked")):
            return
        try:
            PreviewEditionService.set_upload_participation(
                self.db,
                user=admin_user,
                enabled=True,
                source="first_run_wizard",
            )
        except PermissionError:
            self.db.rollback()

    def _build_site_blueprints(self) -> List[SiteBlueprint]:
        scale = dict(self.manifest.get("scale") or {})
        top = str(self.manifest.get("topology_kind") or "").strip().lower()
        blueprints: List[SiteBlueprint] = [
            SiteBlueprint(
                code="ROOT",
                name=f"{self.lab_prefix} Root",
                site_type="region",
                parent_code=None,
                role_counts={},
            )
        ]

        if top in {"enterprise", "hybrid"}:
            blueprints.append(
                SiteBlueprint(
                    code="HQ",
                    name=f"{self.lab_prefix} HQ",
                    site_type="campus",
                    parent_code="ROOT",
                    role_counts={
                        "core": int(scale.get("hq_core", 0)),
                        "distribution": int(scale.get("hq_distribution", 0)),
                        "access": int(scale.get("hq_access", 0)),
                        "security": int(scale.get("hq_security", 0)),
                        "wireless_controller": int(scale.get("wireless_controllers", 0)),
                        "wireless_ap": int(scale.get("wireless_aps_hq", 0)),
                        "cloud_gateway": int(scale.get("cloud_gateways", 0)),
                    },
                )
            )
        branch_count = int(scale.get("branches", 1 if top == "branch" else 0))
        for branch_idx in range(1, branch_count + 1):
            blueprints.append(
                SiteBlueprint(
                    code=f"BR{branch_idx:02d}",
                    name=f"{self.lab_prefix} Branch {branch_idx:02d}",
                    site_type="branch",
                    parent_code="ROOT" if top == "branch" else "HQ" if any(item.code == "HQ" for item in blueprints) else "ROOT",
                    role_counts={
                        "branch_router": int(scale.get("branch_router_per_site", 0)),
                        "access": int(scale.get("branch_access_per_site", 0)),
                        "security": int(scale.get("branch_security_per_site", 0)),
                        "wireless_ap": int(scale.get("wireless_aps_per_site", 0)),
                    },
                )
            )
        dc_count = int(scale.get("datacenters", 0))
        for dc_idx in range(1, dc_count + 1):
            blueprints.append(
                SiteBlueprint(
                    code=f"DC{dc_idx:02d}",
                    name=f"{self.lab_prefix} Datacenter {dc_idx:02d}",
                    site_type="datacenter",
                    parent_code="ROOT",
                    role_counts={
                        "spine": int(scale.get("spines_per_dc", 0)),
                        "leaf": int(scale.get("leafs_per_dc", 0)),
                        "border_leaf": int(scale.get("border_leafs_per_dc", 0)),
                        "security": int(scale.get("security_per_dc", 0)),
                        "adc": int(scale.get("adc_per_dc", 0)),
                    },
                )
            )
        if top == "datacenter" and dc_count == 0:
            blueprints.append(
                SiteBlueprint(
                    code="DC01",
                    name=f"{self.lab_prefix} Datacenter 01",
                    site_type="datacenter",
                    parent_code="ROOT",
                    role_counts={
                        "spine": int(scale.get("spines_per_dc", 2)),
                        "leaf": int(scale.get("leafs_per_dc", 4)),
                        "border_leaf": int(scale.get("border_leafs_per_dc", 1)),
                        "security": int(scale.get("security_per_dc", 1)),
                        "adc": int(scale.get("adc_per_dc", 1)),
                    },
                )
            )
        return blueprints

    def _create_sites(self, blueprints: Iterable[SiteBlueprint]) -> Dict[str, Site]:
        out: Dict[str, Site] = {}
        for blueprint in blueprints:
            parent_id = out[blueprint.parent_code].id if blueprint.parent_code and blueprint.parent_code in out else None
            row = Site(
                name=blueprint.name,
                type=blueprint.site_type,
                parent_id=parent_id,
                address=f"LAB Address {blueprint.code}",
                timezone="Asia/Seoul",
            )
            self.db.add(row)
            self.db.flush()
            out[blueprint.code] = row
        return out

    def _pick_device_pool(self, role: str, index: int) -> Dict[str, str]:
        pool = ROLE_DEVICE_POOL.get(role) or ROLE_DEVICE_POOL["access"]
        return dict(pool[index % len(pool)])

    def _pick_owner(self, role: str, users: List[User]) -> User:
        admins = [item for item in users if item.role == "admin"]
        operators = [item for item in users if item.role == "operator"]
        viewers = [item for item in users if item.role == "viewer"]
        if role in {"core", "distribution", "spine", "border_leaf", "security"} and admins:
            return admins[len(self.devices) % len(admins)]
        if operators:
            return operators[len(self.devices) % len(operators)]
        if admins:
            return admins[0]
        return viewers[0]

    def _build_device_ip(self, site_seq: int, host_seq: int) -> str:
        third = ((site_seq // 200) + 1) % 200
        fourth = ((host_seq % 240) + 10)
        second = (site_seq % 200) + 10
        return f"10.{second}.{third}.{fourth}"

    def _build_device_mac(self, site_seq: int, host_seq: int) -> str:
        values = [0x02, 0xAB, site_seq % 256, (host_seq // 256) % 256, host_seq % 256, (site_seq + host_seq) % 256]
        return ":".join(f"{value:02X}" for value in values)

    def _create_devices(
        self,
        blueprints: Iterable[SiteBlueprint],
        sites: Dict[str, Site],
        users: List[User],
        tenant: Tenant,
    ) -> List[Device]:
        created: List[Device] = []
        host_seq = 0
        for site_seq, blueprint in enumerate(blueprints, start=1):
            if blueprint.code == "ROOT":
                continue
            site = sites[blueprint.code]
            for role, total in blueprint.role_counts.items():
                for idx in range(1, int(total or 0) + 1):
                    host_seq += 1
                    pool = self._pick_device_pool(role, idx)
                    name = f"{self.device_prefix}-{blueprint.code}-{ROLE_SHORT.get(role, role.upper())}-{idx:02d}"
                    hostname = name.lower()
                    is_online = self.random.random() > 0.12
                    owner = self._pick_owner(role, users)
                    device = Device(
                        name=name,
                        hostname=hostname,
                        ip_address=self._build_device_ip(site_seq, host_seq),
                        mac_address=self._build_device_mac(site_seq, host_seq),
                        snmp_community="public",
                        snmp_version="v2c",
                        ssh_username="admin",
                        ssh_password="Password1!!@",
                        polling_interval=60 if str(self.manifest.get("edition") or "") == "pro" else 120,
                        status_interval=60 if str(self.manifest.get("edition") or "") == "pro" else 180,
                        model=pool["model"],
                        os_version="2026.03-lab",
                        serial_number=f"LAB-{self.slug[:6].upper()}-{host_seq:06d}",
                        site_id=site.id,
                        location=site.name,
                        device_type=pool["device_type"],
                        telemetry_mode="hybrid",
                        role=role,
                        status="online" if is_online else "offline",
                        reachability_status="reachable" if is_online else "unreachable",
                        uptime=f"{self.random.randint(4, 180)}d {self.random.randint(0, 23)}h {self.random.randint(0, 59)}m",
                        last_seen=self.now - timedelta(minutes=self.random.randint(1, 120)) if is_online else self.now - timedelta(hours=self.random.randint(4, 96)),
                        variables={
                            "support_policy": {
                                "tier": "gold" if role in {"core", "spine", "security", "border_leaf"} else "standard",
                                "vendor": pool["vendor"],
                            },
                            "scenario_lab": {
                                "slug": self.slug,
                                "site_code": blueprint.code,
                            },
                        },
                        owner_id=owner.id,
                        tenant_id=tenant.id,
                    )
                    self.db.add(device)
                    self.db.flush()
                    created.append(device)
        return created

    def _assign_management_states(self, devices: List[Device]) -> None:
        edition = str(self.manifest.get("edition") or "free").strip().lower()
        managed_limit = int(self.manifest.get("managed_limit") or 0)
        ranked = sorted(
            devices,
            key=lambda item: (
                ROLE_PRIORITY.get(str(item.role or ""), 10),
                1 if str(item.status or "").lower() == "online" else 0,
                int(item.id or 0),
            ),
            reverse=True,
        )
        allowed = len(ranked) if edition == "pro" or managed_limit <= 0 else min(managed_limit, len(ranked))
        allowed_ids = {int(item.id) for item in ranked[:allowed]}
        for device in devices:
            priority = float(ROLE_PRIORITY.get(str(device.role or ""), 10))
            if str(device.status or "").lower() == "online":
                priority += 5.0
            device.management_priority_score = priority
            if int(device.id or 0) in allowed_ids:
                device.management_state = "managed"
                device.management_reason = "auto_selected"
                device.managed_since = self.now
            else:
                device.management_state = "discovered_only"
                device.management_reason = "edition_limit"
                device.managed_since = None
            self.db.add(device)

    def _install_profile_assignments(self, devices: Iterable[Device]) -> None:
        for device in devices:
            MonitoringProfileService.ensure_assignment(self.db, device, commit=False)
        self.db.commit()

    def _interface_for(self, device: Device, name: str, vlan: int = 1, mode: str = "trunk") -> Interface:
        key = (int(device.id or 0), name)
        existing = self.interfaces.get(key)
        if existing is not None:
            return existing
        row = Interface(
            device_id=device.id,
            name=name,
            description=f"{self.lab_prefix} {name}",
            status="up",
            admin_status="up",
            vlan=vlan,
            mode=mode,
        )
        self.db.add(row)
        self.db.flush()
        self.interfaces[key] = row
        return row

    def _site_devices(self, site_code: str, role: str | None = None) -> List[Device]:
        site = self.sites.get(site_code)
        if site is None:
            return []
        rows = [item for item in self.devices if int(item.site_id or 0) == int(site.id or 0)]
        if role:
            rows = [item for item in rows if str(item.role or "") == role]
        return rows

    def _link(self, source: Device, target: Device, source_name: str, target_name: str, protocol: str = "LAB") -> None:
        row = Link(
            source_device_id=source.id,
            target_device_id=target.id,
            source_interface_name=self._interface_for(source, source_name).name,
            target_interface_name=self._interface_for(target, target_name).name,
            status="active",
            link_speed="10G",
            protocol=protocol,
            confidence=0.96,
            discovery_source="scenario_lab",
            first_seen=self.now,
            last_seen=self.now,
        )
        self.db.add(row)
        self.db.flush()

    def _create_links(self, blueprints: Iterable[SiteBlueprint]) -> None:
        for blueprint in blueprints:
            if blueprint.code == "ROOT":
                continue
            routers = self._site_devices(blueprint.code, "branch_router")
            access = self._site_devices(blueprint.code, "access")
            security = self._site_devices(blueprint.code, "security")
            aps = self._site_devices(blueprint.code, "wireless_ap")
            wlc = self._site_devices(blueprint.code, "wireless_controller")
            core = self._site_devices(blueprint.code, "core")
            dist = self._site_devices(blueprint.code, "distribution")
            spines = self._site_devices(blueprint.code, "spine")
            leafs = self._site_devices(blueprint.code, "leaf")
            border_leafs = self._site_devices(blueprint.code, "border_leaf")
            adcs = self._site_devices(blueprint.code, "adc")
            gateways = self._site_devices(blueprint.code, "cloud_gateway")

            for router in routers:
                for sec_idx, sec in enumerate(security, start=1):
                    self._link(router, sec, f"Gi0/{sec_idx}", f"Gi0/{sec_idx}", "LAB_BRANCH")
                for acc_idx, edge in enumerate(access, start=1):
                    self._link(router, edge, f"Gi1/{acc_idx}", "Gi0/1", "LAB_BRANCH")

            for index, edge in enumerate(access, start=1):
                divisor = max(len(access), 1)
                assigned_aps = [ap for ap_idx, ap in enumerate(aps) if (ap_idx % divisor) == (index - 1) % divisor]
                for ap_offset, ap in enumerate(assigned_aps, start=1):
                    self._link(edge, ap, f"Gi0/{24 + ap_offset}", "Eth0", "LAB_WIFI")

            for core_idx, core_device in enumerate(core, start=1):
                for dist_idx, dist_device in enumerate(dist, start=1):
                    self._link(core_device, dist_device, f"Eth1/{dist_idx}", f"Eth1/{core_idx}", "LAB_CAMPUS")

            for dist_idx, dist_device in enumerate(dist, start=1):
                for acc_idx, edge in enumerate(access, start=1):
                    self._link(dist_device, edge, f"Eth2/{acc_idx}", "Gi0/48", "LAB_CAMPUS")
                for sec_idx, sec in enumerate(security, start=1):
                    self._link(dist_device, sec, f"Eth3/{sec_idx}", f"Eth1/{dist_idx}", "LAB_CAMPUS")
                for wlc_idx, controller in enumerate(wlc, start=1):
                    self._link(dist_device, controller, f"Eth4/{wlc_idx}", f"Gi0/{dist_idx}", "LAB_WIFI")

            for spine_idx, spine in enumerate(spines, start=1):
                for leaf_idx, leaf in enumerate(leafs, start=1):
                    self._link(spine, leaf, f"Eth1/{leaf_idx}", f"Eth1/{spine_idx}", "LAB_DC")
                for border_idx, border in enumerate(border_leafs, start=1):
                    self._link(spine, border, f"Eth2/{border_idx}", f"Eth1/{spine_idx}", "LAB_DC")

            for border_idx, border in enumerate(border_leafs, start=1):
                for sec_idx, sec in enumerate(security, start=1):
                    self._link(border, sec, f"Eth3/{sec_idx}", f"Eth1/{border_idx}", "LAB_DC")
                for adc_idx, adc in enumerate(adcs, start=1):
                    self._link(border, adc, f"Eth4/{adc_idx}", f"Eth1/{border_idx}", "LAB_DC")

            uplink_candidates = core or border_leafs or routers
            for gateway_idx, gateway in enumerate(gateways, start=1):
                if not uplink_candidates:
                    continue
                target = uplink_candidates[(gateway_idx - 1) % len(uplink_candidates)]
                self._link(gateway, target, "Eth0", f"Eth9/{gateway_idx}", "LAB_HYBRID")
        self.db.commit()

    def _create_cloud_inventory(self, tenant: Tenant) -> tuple[List[CloudAccount], List[CloudResource]]:
        cloud_cfg = dict(self.manifest.get("cloud") or {})
        if not cloud_cfg.get("enabled"):
            return [], []
        providers = list(cloud_cfg.get("providers") or ["aws", "azure", "gcp"])
        account_total = int(cloud_cfg.get("accounts") or 0)
        resources_per = int(cloud_cfg.get("resources_per_account") or 0)
        accounts: List[CloudAccount] = []
        resources: List[CloudResource] = []
        default_types = ["vpc", "subnet", "vm", "security_group", "route_table", "load_balancer", "gateway"]
        for account_idx in range(1, account_total + 1):
            provider = providers[(account_idx - 1) % len(providers)]
            account = CloudAccount(
                name=f"{self.lab_prefix} {provider.upper()} Account {account_idx:02d}",
                provider=provider,
                credentials={"mode": "scenario_lab", "provider": provider, "slug": self.slug},
                tenant_id=tenant.id,
                is_active=True,
                last_synced_at=self.now,
                sync_status="ok",
                sync_message="Scenario lab seeded",
            )
            self.db.add(account)
            self.db.flush()
            accounts.append(account)
            for resource_idx in range(1, resources_per + 1):
                resource_type = default_types[(resource_idx - 1) % len(default_types)]
                state = "RUNNING" if resource_type == "vm" else "AVAILABLE"
                resource = CloudResource(
                    account_id=account.id,
                    resource_id=f"{provider}-{self.slug}-{account_idx:02d}-{resource_type}-{resource_idx:03d}",
                    resource_type=resource_type,
                    name=f"{self.lab_prefix} {provider.upper()} {resource_type.replace('_', ' ').title()} {resource_idx:02d}",
                    region=f"{provider}-kr-{1 + ((resource_idx - 1) % 2)}",
                    cidr_block=f"172.{20 + account_idx}.{resource_idx}.0/24" if resource_type in {"vpc", "subnet"} else None,
                    resource_metadata={
                        "provider_state": state,
                        "scenario_lab": {"slug": self.slug, "account_index": account_idx},
                    },
                    state=state,
                )
                self.db.add(resource)
                self.db.flush()
                resources.append(resource)
        self.db.commit()
        return accounts, resources

    def _create_service_groups(self, devices: List[Device], cloud_resources: List[CloudResource]) -> List[ServiceGroup]:
        created: List[ServiceGroup] = []
        manifests = list(self.manifest.get("service_groups") or [])
        for group_idx, payload in enumerate(manifests, start=1):
            row = ServiceGroup(
                name=f"{self.lab_prefix} {str(payload.get('name') or f'Service Group {group_idx}').strip()}",
                description=f"Scenario lab service group for {self.slug}",
                criticality=str(payload.get("criticality") or "standard"),
                owner_team=str(payload.get("owner_team") or "Operations"),
                color="#0ea5e9",
                is_active=True,
            )
            self.db.add(row)
            self.db.flush()
            role_allow = {str(item or "").strip() for item in list(payload.get("device_roles") or []) if str(item or "").strip()}
            max_devices = int(payload.get("max_devices") or 0)
            matched_devices = [device for device in devices if not role_allow or str(device.role or "") in role_allow]
            for device in matched_devices[: max_devices or len(matched_devices)]:
                self.db.add(
                    ServiceGroupMember(
                        service_group_id=row.id,
                        member_type="device",
                        device_id=device.id,
                        role_label=str(device.role or ""),
                    )
                )
            cloud_types = {str(item or "").strip() for item in list(payload.get("cloud_types") or []) if str(item or "").strip()}
            if cloud_types:
                cloud_matches = [resource for resource in cloud_resources if str(resource.resource_type or "") in cloud_types]
                limit = min(len(cloud_matches), max(3, max_devices // 2 if max_devices else len(cloud_matches)))
                for resource in cloud_matches[:limit]:
                    self.db.add(
                        ServiceGroupMember(
                            service_group_id=row.id,
                            member_type="cloud_resource",
                            cloud_resource_id=resource.id,
                            role_label=str(resource.resource_type or ""),
                        )
                    )
            created.append(row)
        self.db.commit()
        return created

    def _create_metrics_for_device(self, device: Device, sample_count: int) -> None:
        base_cpu = 24 + (ROLE_PRIORITY.get(str(device.role or ""), 20) // 6)
        for sample_idx in range(sample_count):
            minute_offset = sample_count - sample_idx
            self.db.add(
                SystemMetric(
                    device_id=device.id,
                    cpu_usage=min(95.0, float(base_cpu + self.random.randint(-8, 18))),
                    memory_usage=min(92.0, float(36 + self.random.randint(-10, 20))),
                    traffic_in=float(120 + self.random.randint(10, 600)),
                    traffic_out=float(100 + self.random.randint(10, 550)),
                    timestamp=self.now - timedelta(minutes=minute_offset * 10),
                )
            )

    def _pick_issue_devices(self, severity: str) -> List[Device]:
        preferred = [device for device in self.devices if device.management_state == "managed"]
        if severity == "critical":
            preferred = [device for device in preferred if device.role in {"core", "security", "border_leaf", "cloud_gateway", "spine"}] or preferred
        elif severity == "warning":
            preferred = [device for device in preferred if device.role not in {"wireless_ap"}] or preferred
        return preferred or list(self.devices)

    def _create_issues_and_actions(self, devices: List[Device], users: List[User]) -> List[Issue]:
        issue_cfg = dict(self.manifest.get("issues") or {})
        sample_count = int(self.manifest.get("metrics_samples_per_managed_device") or 0)
        created: List[Issue] = []
        operators = [user for user in users if user.role == "operator"] or [user for user in users if user.role == "admin"]
        admin_actor = next((user for user in users if user.role == "admin"), None)
        issue_patterns = {
            "critical": [
                "Core uplink saturation",
                "Firewall session exhaustion",
                "East-west packet loss",
                "Cloud gateway route drift",
            ],
            "warning": [
                "Interface error growth",
                "BGP neighbor flap",
                "VPN jitter increase",
                "Topology mismatch detected",
            ],
            "info": [
                "Preventive check reminder",
                "Config drift observed",
                "State snapshot captured",
                "Monitoring profile adjusted",
            ],
        }
        issue_index = 0
        for severity in ("critical", "warning", "info"):
            candidates = self._pick_issue_devices(severity)
            for count in range(1, int(issue_cfg.get(severity) or 0) + 1):
                issue_index += 1
                device = candidates[(count - 1) % len(candidates)]
                status = "active" if severity != "info" or count % 3 != 0 else "resolved"
                issue = Issue(
                    device_id=device.id,
                    title=f"{self.lab_prefix} {issue_patterns[severity][(count - 1) % len(issue_patterns[severity])]} #{count:02d}",
                    description=f"Scenario lab generated {severity} issue for {device.name}.",
                    severity=severity,
                    status=status,
                    category="network" if severity != "info" else "operations",
                    is_read=False,
                    created_at=self.now - timedelta(minutes=issue_index * 7),
                    resolved_at=(self.now - timedelta(minutes=issue_index * 2)) if status == "resolved" else None,
                )
                self.db.add(issue)
                self.db.flush()
                created.append(issue)
                self.db.add(
                    EventLog(
                        device_id=device.id,
                        severity=severity,
                        event_id=f"LAB_ISSUE_{severity.upper()}",
                        message=f"{issue.title} raised for scenario {self.slug}",
                        source=f"LAB:{self.slug}",
                        timestamp=issue.created_at,
                    )
                )
                if status == "active" and severity in {"critical", "warning"}:
                    assignee = operators[(count - 1) % len(operators)]
                    action_status = ["open", "investigating", "mitigated", "resolved"][(count - 1) % 4]
                    self.db.add(
                        OperationAction(
                            issue_id=issue.id,
                            device_id=device.id,
                            source_type="issue",
                            title=f"{self.lab_prefix} Action for {device.name}",
                            summary=f"Follow up on {severity} issue for {device.name}",
                            severity=severity,
                            status=action_status,
                            assignee_name=str(assignee.full_name or assignee.username),
                            created_by=str(admin_actor.username if admin_actor else "lab"),
                            updated_by=str(assignee.username),
                            latest_note=f"Scenario lab action update {count}",
                            timeline=[
                                {"status": "open", "at": (self.now - timedelta(minutes=issue_index * 7)).isoformat()},
                                {"status": action_status, "at": (self.now - timedelta(minutes=issue_index * 3)).isoformat()},
                            ],
                            created_at=self.now - timedelta(minutes=issue_index * 6),
                            updated_at=self.now - timedelta(minutes=issue_index * 2),
                            resolved_at=(self.now - timedelta(minutes=issue_index)) if action_status == "resolved" else None,
                        )
                    )
            if sample_count > 0:
                for device in [item for item in devices if item.management_state == "managed"]:
                    self._create_metrics_for_device(device, sample_count)
        self.db.commit()
        return created

    def _create_approvals(self, users: List[User]) -> List[ApprovalRequest]:
        created: List[ApprovalRequest] = []
        admins = [user for user in users if user.role == "admin"]
        operators = [user for user in users if user.role == "operator"] or admins
        critical_issues = [issue for issue in self.issues if str(issue.severity or "") == "critical"][: max(1, min(4, len(self.issues)))]
        for idx, issue in enumerate(critical_issues, start=1):
            device = next((item for item in self.devices if int(item.id or 0) == int(issue.device_id or 0)), None)
            status = ["pending", "approved", "approved", "rejected"][(idx - 1) % 4]
            requester = operators[(idx - 1) % len(operators)]
            approver = admins[(idx - 1) % len(admins)] if admins else requester
            request_type = "config_deploy"
            payload: Dict[str, Any]

            if idx == 1 and self.cloud_accounts and str(self.manifest.get("edition") or "").strip().lower() == "pro":
                account = self.cloud_accounts[0]
                payload = self._build_cloud_intent_approval_payload(
                    issue=issue,
                    device=device,
                    account=account,
                    approval_status=status,
                )
                request_type = "intent_apply"
            else:
                payload = {
                    "device_ids": [int(issue.device_id or 0)] if issue.device_id else [],
                    "scope": {
                        "device_ids": [int(issue.device_id or 0)] if issue.device_id else [],
                        "site_ids": [int(device.site_id or 0)] if device is not None and device.site_id else [],
                    },
                    "pre_check": {
                        "result": "PASS" if status != "rejected" else "WARN",
                        "blockers": 0,
                        "warnings": 1 if status == "rejected" else 0,
                        "checks": 5,
                    },
                    "execution_result": {"status": "completed", "bundle": f"lab-{self.slug}-approval-{idx}.zip"} if status == "approved" else None,
                    "rollback_trace": {"status": "ready"} if idx % 2 == 0 else None,
                }
                if self.cloud_accounts:
                    account = self.cloud_accounts[(idx - 1) % len(self.cloud_accounts)]
                    payload["scope"]["provider"] = account.provider
                    payload["scope"]["account_name"] = account.name
            row = ApprovalRequest(
                requester_id=requester.id,
                approver_id=approver.id if approver else None,
                title=f"{self.lab_prefix} Approval for {device.name if device else 'Shared Scope'}",
                description=f"Scenario lab approval context for issue {issue.title}",
                request_type=request_type,
                payload=payload,
                status=status,
                requester_comment="Scenario lab requested change review",
                approver_comment="Scenario lab decision recorded",
                created_at=self.now - timedelta(hours=idx * 3),
                updated_at=self.now - timedelta(hours=idx * 2),
                decided_at=(self.now - timedelta(hours=idx)) if status in {"approved", "rejected"} else None,
            )
            self.db.add(row)
            self.db.flush()
            created.append(row)
        self.db.commit()
        return created

    def _build_cloud_intent_approval_payload(
        self,
        *,
        issue: Issue,
        device: Device | None,
        account: CloudAccount,
        approval_status: str,
    ) -> Dict[str, Any]:
        provider = str(account.provider or "aws").strip().lower() or "aws"
        account_id = int(account.id or 0)
        account_name = str(account.name or f"{provider}-account").strip() or f"{provider}-account"
        scoped_resources = [row for row in self.cloud_resources if int(row.account_id or 0) == account_id]
        region = str(
            next(
                (
                    str(row.region or "").strip()
                    for row in scoped_resources
                    if str(row.region or "").strip()
                ),
                "",
            )
            or "ap-northeast-2"
        )
        resource_types = sorted({str(row.resource_type or "").strip() for row in scoped_resources if str(row.resource_type or "").strip()})
        spec: Dict[str, Any] = {
            "targets": {
                "providers": [provider],
                "account_ids": [account_id],
                "regions": [region],
            },
            "required_tags": [{"key": "owner"}],
        }
        if resource_types:
            spec["targets"]["resource_types"] = resource_types[:3]
        if provider in {"aws", "ncp", "azure", "gcp"}:
            spec["blocked_ingress_cidrs"] = ["0.0.0.0/0"]
            spec["protected_route_destinations"] = ["0.0.0.0/0"]

        intent_name = f"{self.lab_prefix} cloud policy {provider}-{account_id}"
        simulate_payload: Dict[str, Any] = {
            "intent_type": "cloud_policy",
            "name": intent_name,
            "spec": spec,
            "metadata": {
                "source": "scenario_lab",
                "engine": "terraform",
                "submission_channel": "scenario_lab_seed",
            },
            "dry_run": True,
            "idempotency_key": f"scenario-lab:{self.slug}:intent:{account_id}",
        }
        simulation = IntentService.simulate_intent(self.db, simulate_payload)
        terraform_preview = simulation.get("terraform_plan_preview") if isinstance(simulation.get("terraform_plan_preview"), dict) else {}
        change_preview_summary = {
            "risk_score": simulation.get("risk_score"),
            "blast_radius": simulation.get("blast_radius"),
            "change_summary": simulation.get("change_summary"),
            "cloud_scope": simulation.get("cloud_scope"),
        }

        payload: Dict[str, Any] = {
            **simulate_payload,
            "dry_run": False,
            "device_ids": [int(issue.device_id or 0)] if issue.device_id else [],
            "scope": {
                "device_ids": [int(issue.device_id or 0)] if issue.device_id else [],
                "site_ids": [int(device.site_id or 0)] if device is not None and device.site_id else [],
                "provider": provider,
                "account_ids": [account_id],
                "account_name": account_name,
                "regions": [region],
            },
            "simulation_snapshot": simulation,
            "terraform_plan_preview": terraform_preview,
            "change_preview_summary": change_preview_summary,
            "pre_check": simulation.get("pre_check") if isinstance(simulation.get("pre_check"), dict) else {},
            "execution_result": {
                "status": "completed",
                "bundle": f"lab-{self.slug}-intent-approval-{account_id}.zip",
            } if approval_status == "approved" else None,
            "rollback_trace": {"status": "ready"} if approval_status == "approved" else None,
        }
        return payload

    def _create_known_errors(self) -> List[KnownErrorEntry]:
        created: List[KnownErrorEntry] = []
        count = int(self.manifest.get("known_errors") or 0)
        vendors = sorted({str(device.device_type or "") for device in self.devices})
        categories = ["routing", "interface", "security", "wireless", "hybrid"]
        for idx in range(1, count + 1):
            vendor_scope = vendors[(idx - 1) % len(vendors)] if vendors else None
            row = KnownErrorEntry(
                title=f"{self.lab_prefix} Known Error {idx:02d}",
                symptom_pattern=f"lab symptom pattern {idx}",
                category=categories[(idx - 1) % len(categories)],
                severity_hint=["warning", "critical", "info"][(idx - 1) % 3],
                device_type_scope=vendor_scope,
                vendor_scope=vendor_scope,
                root_cause=f"Scenario lab root cause {idx}",
                workaround=f"Scenario lab workaround {idx}",
                sop_summary=f"Scenario lab SOP summary {idx}",
                tags=["scenario_lab", self.slug],
                is_enabled=True,
                created_by="scenario_lab",
                updated_by="scenario_lab",
                times_matched=idx * 2,
                last_matched_at=self.now - timedelta(days=idx),
            )
            self.db.add(row)
            self.db.flush()
            created.append(row)
        self.db.commit()
        return created

    def _create_asset_change_events(self) -> None:
        for site in list(self.sites.values())[:4]:
            self.db.add(
                AssetChangeEvent(
                    asset_kind="site",
                    asset_key=f"{self.lab_asset_prefix}site:{site.id}",
                    asset_name=site.name,
                    action="seeded",
                    summary=f"Scenario lab site seeded: {site.name}",
                    actor_name="scenario_lab",
                    actor_role="system",
                    details={"slug": self.slug, "site_type": site.type},
                    created_at=self.now - timedelta(days=2),
                )
            )
        for device in self.devices[: min(len(self.devices), 12)]:
            self.db.add(
                AssetChangeEvent(
                    asset_kind="device",
                    asset_key=f"{self.lab_asset_prefix}device:{device.id}",
                    asset_name=device.name,
                    action="seeded",
                    summary=f"Scenario lab device seeded: {device.name}",
                    actor_name="scenario_lab",
                    actor_role="system",
                    details={
                        "slug": self.slug,
                        "management_state": device.management_state,
                        "site_id": device.site_id,
                    },
                    created_at=self.now - timedelta(hours=12),
                )
            )
        for account in self.cloud_accounts[:4]:
            self.db.add(
                AssetChangeEvent(
                    asset_kind="cloud_account",
                    asset_key=f"{self.lab_asset_prefix}cloud-account:{account.id}",
                    asset_name=account.name,
                    action="synced",
                    summary=f"Scenario lab cloud account synced: {account.name}",
                    actor_name="scenario_lab",
                    actor_role="system",
                    details={"provider": account.provider, "slug": self.slug},
                    created_at=self.now - timedelta(hours=6),
                )
            )
        self.db.commit()

    def _create_topology_snapshots(self) -> List[TopologySnapshot]:
        created: List[TopologySnapshot] = []
        snapshot_total = int(self.manifest.get("topology_snapshots") or 0)
        links = self.db.query(Link).filter(Link.discovery_source == "scenario_lab").all()
        nodes_json = json.dumps(
            [
                {
                    "id": int(device.id or 0),
                    "label": device.name,
                    "role": device.role,
                    "site_id": device.site_id,
                    "status": device.status,
                    "management_state": device.management_state,
                }
                for device in self.devices
            ],
            ensure_ascii=False,
        )
        links_json = json.dumps(
            [
                {
                    "id": int(link.id or 0),
                    "source": int(link.source_device_id or 0),
                    "target": int(link.target_device_id or 0),
                    "protocol": link.protocol,
                }
                for link in links
            ],
            ensure_ascii=False,
        )
        metadata = json.dumps(
            {
                "slug": self.slug,
                "edition": self.manifest.get("edition"),
                "topology_kind": self.manifest.get("topology_kind"),
            },
            ensure_ascii=False,
        )
        for idx in range(1, snapshot_total + 1):
            row = TopologySnapshot(
                site_id=None,
                job_id=None,
                label=f"{self.lab_prefix} Topology Snapshot {idx:02d}",
                node_count=len(self.devices),
                link_count=len(links),
                nodes_json=nodes_json,
                links_json=links_json,
                metadata_json=metadata,
                created_at=self.now - timedelta(hours=snapshot_total - idx),
            )
            self.db.add(row)
            self.db.flush()
            created.append(row)
        self.db.commit()
        return created

    def _create_state_history_snapshots(self) -> List[Dict[str, Any]]:
        created: List[Dict[str, Any]] = []
        count = max(1, min(3, int(self.manifest.get("topology_snapshots") or 1)))
        for idx in range(1, count + 1):
            snapshot = StateHistoryService.create_snapshot(
                self.db,
                label=f"{self.lab_prefix} State Review {idx:02d}",
                note=f"Scenario lab snapshot {idx} for {self.slug}",
                actor_name="scenario_lab",
                actor_role="system",
                commit=True,
            )
            created.append(snapshot.model_dump())
        return created

    def _build_summary(self) -> Dict[str, Any]:
        managed = sum(1 for device in self.devices if str(device.management_state or "") == "managed")
        discovered_only = sum(1 for device in self.devices if str(device.management_state or "") == "discovered_only")
        links = self.db.query(Link).filter(Link.discovery_source == "scenario_lab").count()
        assignments = (
            self.db.query(MonitoringProfileAssignment)
            .join(Device, MonitoringProfileAssignment.device_id == Device.id)
            .filter(Device.name.like(f"{self.device_prefix}%"))
            .count()
        )
        return {
            "slug": self.slug,
            "title": self.manifest.get("title"),
            "edition": self.manifest.get("edition"),
            "topology_kind": self.manifest.get("topology_kind"),
            "seeded_at": self.now.isoformat(),
            "credentials": {
                "password": self.user_password,
                "accounts": [
                    {
                        "username": user.username,
                        "role": user.role,
                        "email": user.email,
                    }
                    for user in self.users
                ],
            },
            "counts": {
                "users": len(self.users),
                "sites": len(self.sites),
                "devices": len(self.devices),
                "managed_devices": managed,
                "discovered_only_devices": discovered_only,
                "links": int(links),
                "cloud_accounts": len(self.cloud_accounts),
                "cloud_resources": len(self.cloud_resources),
                "service_groups": len(self.service_groups),
                "issues": len(self.issues),
                "approvals": len(self.approvals),
                "known_errors": len(self.known_errors),
                "monitoring_assignments": int(assignments),
                "topology_snapshots": len(self.topology_snapshots),
                "state_history_snapshots": len(self.state_snapshots),
            },
            "highlights": {
                "first_admin": next((user.username for user in self.users if user.role == "admin"), None),
                "first_operator": next((user.username for user in self.users if user.role == "operator"), None),
                "sample_device": self.devices[0].name if self.devices else None,
                "sample_service_group": self.service_groups[0].name if self.service_groups else None,
            },
        }


def load_manifest(path: str) -> Dict[str, Any]:
    manifest_path = Path(path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"Scenario manifest not found: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Scenario manifest must be a JSON object.")
    required = {"slug", "edition", "topology_kind", "scale"}
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Scenario manifest missing required keys: {', '.join(missing)}")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed repeatable FREE/PRO scenario-lab data.")
    parser.add_argument("--scenario-file", required=True, help="Path to scenario JSON manifest.")
    parser.add_argument("--user-password", default="Password1!!@", help="Password to apply to seeded lab users.")
    parser.add_argument("--wipe-existing", action="store_true", help="Delete prior LAB data for the same scenario before reseeding.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = load_manifest(args.scenario_file)
    db = SessionLocal()
    try:
        seeder = ScenarioSeeder(db, manifest, args.user_password)
        summary = seeder.seed(wipe_existing=bool(args.wipe_existing))
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
