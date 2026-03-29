from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.cloud import CloudAccount, CloudResource
from app.models.device import Device
from app.models.device import Issue
from app.models.service_group import ServiceGroup, ServiceGroupMember


class ServiceGroupService:
    CRITICALITY_RANK = {
        "high": 3,
        "elevated": 2,
        "standard": 1,
    }

    @classmethod
    def list_groups(cls, db: Session) -> List[ServiceGroup]:
        return (
            db.query(ServiceGroup)
            .options(
                joinedload(ServiceGroup.members).joinedload(ServiceGroupMember.device),
                joinedload(ServiceGroup.members).joinedload(ServiceGroupMember.cloud_resource).joinedload(CloudResource.account),
            )
            .order_by(ServiceGroup.name.asc())
            .all()
        )

    @classmethod
    def get_group(cls, db: Session, group_id: int) -> Optional[ServiceGroup]:
        return (
            db.query(ServiceGroup)
            .options(
                joinedload(ServiceGroup.members).joinedload(ServiceGroupMember.device),
                joinedload(ServiceGroup.members).joinedload(ServiceGroupMember.cloud_resource).joinedload(CloudResource.account),
            )
            .filter(ServiceGroup.id == group_id)
            .first()
        )

    @classmethod
    def create_group(cls, db: Session, payload: Dict[str, Any]) -> ServiceGroup:
        group = ServiceGroup(**payload)
        db.add(group)
        db.commit()
        db.refresh(group)
        return cls.get_group(db, int(group.id)) or group

    @classmethod
    def update_group(cls, db: Session, group: ServiceGroup, payload: Dict[str, Any]) -> ServiceGroup:
        for key, value in payload.items():
            setattr(group, key, value)
        db.add(group)
        db.commit()
        db.refresh(group)
        return cls.get_group(db, int(group.id)) or group

    @classmethod
    def delete_group(cls, db: Session, group: ServiceGroup) -> None:
        db.delete(group)
        db.commit()

    @classmethod
    def add_device_member(
        cls,
        db: Session,
        *,
        group: ServiceGroup,
        device: Device,
        role_label: Optional[str] = None,
    ) -> ServiceGroup:
        existing = (
            db.query(ServiceGroupMember)
            .filter(
                ServiceGroupMember.service_group_id == group.id,
                ServiceGroupMember.member_type == "device",
                ServiceGroupMember.device_id == device.id,
            )
            .first()
        )
        if existing:
            return cls.get_group(db, int(group.id)) or group
        member = ServiceGroupMember(
            service_group_id=int(group.id),
            member_type="device",
            device_id=int(device.id),
            role_label=str(role_label or "").strip() or None,
        )
        db.add(member)
        db.commit()
        return cls.get_group(db, int(group.id)) or group

    @classmethod
    def add_cloud_resource_member(
        cls,
        db: Session,
        *,
        group: ServiceGroup,
        cloud_resource: CloudResource,
        role_label: Optional[str] = None,
    ) -> ServiceGroup:
        existing = (
            db.query(ServiceGroupMember)
            .filter(
                ServiceGroupMember.service_group_id == group.id,
                ServiceGroupMember.member_type == "cloud_resource",
                ServiceGroupMember.cloud_resource_id == cloud_resource.id,
            )
            .first()
        )
        if existing:
            return cls.get_group(db, int(group.id)) or group
        member = ServiceGroupMember(
            service_group_id=int(group.id),
            member_type="cloud_resource",
            cloud_resource_id=int(cloud_resource.id),
            role_label=str(role_label or "").strip() or None,
        )
        db.add(member)
        db.commit()
        return cls.get_group(db, int(group.id)) or group

    @classmethod
    def remove_member(cls, db: Session, *, group: ServiceGroup, member_id: int) -> ServiceGroup:
        member = (
            db.query(ServiceGroupMember)
            .filter(
                ServiceGroupMember.service_group_id == group.id,
                ServiceGroupMember.id == member_id,
            )
            .first()
        )
        if member is None:
            raise ValueError("member not found")
        db.delete(member)
        db.commit()
        return cls.get_group(db, int(group.id)) or group

    @classmethod
    def build_catalog(cls, db: Session) -> Dict[str, Any]:
        devices = (
            db.query(Device)
            .order_by(Device.name.asc())
            .all()
        )
        cloud_rows = (
            db.query(CloudResource, CloudAccount)
            .join(CloudAccount, CloudAccount.id == CloudResource.account_id)
            .order_by(CloudAccount.provider.asc(), CloudAccount.name.asc(), CloudResource.resource_type.asc(), CloudResource.name.asc(), CloudResource.resource_id.asc())
            .all()
        )
        return {
            "devices": [
                {
                    "id": int(device.id),
                    "name": str(device.name or ""),
                    "ip_address": str(device.ip_address or ""),
                    "role": str(device.role or "") or None,
                    "status": str(device.status or "") or None,
                    "management_state": str(device.management_state or "") or None,
                }
                for device in devices
            ],
            "cloud_resources": [
                {
                    "id": int(resource.id),
                    "account_id": int(account.id),
                    "account_name": str(account.name or ""),
                    "provider": str(account.provider or ""),
                    "resource_id": str(resource.resource_id or ""),
                    "resource_type": str(resource.resource_type or ""),
                    "name": str(resource.name or "") or None,
                    "region": str(resource.region or "") or None,
                    "state": str(resource.state or "") or None,
                }
                for resource, account in cloud_rows
            ],
        }

    @classmethod
    def build_group_health_map(cls, db: Session, groups: list[ServiceGroup]) -> Dict[int, Dict[str, Any]]:
        rows = list(groups or [])
        if not rows:
            return {}

        group_device_ids: Dict[int, set[int]] = {}
        group_device_counts: Dict[int, int] = {}
        group_cloud_counts: Dict[int, int] = {}
        all_device_ids: set[int] = set()

        for group in rows:
            device_ids: set[int] = set()
            device_count = 0
            cloud_count = 0
            for member in list(group.members or []):
                member_type = str(member.member_type or "").strip().lower()
                if member_type == "device" and getattr(member, "device_id", None) is not None:
                    device_id = int(member.device_id)
                    device_ids.add(device_id)
                    all_device_ids.add(device_id)
                    device_count += 1
                elif member_type == "cloud_resource":
                    cloud_count += 1
            group_device_ids[int(group.id)] = device_ids
            group_device_counts[int(group.id)] = device_count
            group_cloud_counts[int(group.id)] = cloud_count

        issue_counts: dict[int, int] = defaultdict(int)
        critical_issue_counts: dict[int, int] = defaultdict(int)
        if all_device_ids:
            active_issues = (
                db.query(Issue)
                .filter(Issue.device_id.in_(list(all_device_ids)), Issue.status == "active")
                .all()
            )
            for issue in active_issues:
                device_id = int(getattr(issue, "device_id", 0) or 0)
                if device_id <= 0:
                    continue
                issue_counts[device_id] += 1
                severity = str(getattr(issue, "severity", "") or "").strip().lower()
                if severity == "critical":
                    critical_issue_counts[device_id] += 1

        out: Dict[int, Dict[str, Any]] = {}
        for group in rows:
            group_id = int(group.id)
            offline_device_count = 0
            managed_device_count = 0
            discovered_only_device_count = 0
            active_issue_count = 0
            critical_issue_count = 0

            for member in list(group.members or []):
                if str(member.member_type or "").strip().lower() != "device" or member.device is None:
                    continue
                device = member.device
                management_state = str(getattr(device, "management_state", "") or "").strip().lower()
                status = str(getattr(device, "status", "") or "").strip().lower()
                reachability = str(getattr(device, "reachability_status", "") or "").strip().lower()
                device_id = int(getattr(device, "id", 0) or 0)

                if management_state == "managed":
                    managed_device_count += 1
                elif management_state == "discovered_only":
                    discovered_only_device_count += 1

                is_online = status in {"online", "up", "available"} or reachability in {"reachable", "online", "up"}
                if not is_online:
                    offline_device_count += 1

                active_issue_count += int(issue_counts.get(device_id, 0))
                critical_issue_count += int(critical_issue_counts.get(device_id, 0))

            member_device_count = int(group_device_counts.get(group_id, 0))
            member_cloud_count = int(group_cloud_counts.get(group_id, 0))

            if member_device_count == 0 and member_cloud_count == 0:
                health_score = 50
                health_status = "review"
            else:
                score = 100
                score -= min(50, critical_issue_count * 20)
                noncritical_issue_count = max(0, active_issue_count - critical_issue_count)
                score -= min(24, noncritical_issue_count * 8)
                score -= min(45, offline_device_count * 15)
                score -= min(20, discovered_only_device_count * 5)
                health_score = max(0, min(100, int(score)))

                if critical_issue_count > 0 or health_score < 45:
                    health_status = "critical"
                elif active_issue_count > 0 or offline_device_count > 0 or discovered_only_device_count > 0 or health_score < 80:
                    health_status = "degraded"
                else:
                    health_status = "healthy"

            out[group_id] = {
                "health_score": health_score,
                "health_status": health_status,
                "active_issue_count": int(active_issue_count),
                "critical_issue_count": int(critical_issue_count),
                "offline_device_count": int(offline_device_count),
                "managed_device_count": int(managed_device_count),
                "discovered_only_device_count": int(discovered_only_device_count),
                "member_device_count": int(member_device_count),
                "member_cloud_count": int(member_cloud_count),
            }

        return out

    @classmethod
    def serialize_group_summary(cls, group: ServiceGroup, *, health: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        members = list(group.members or [])
        device_count = sum(1 for member in members if str(member.member_type or "") == "device")
        cloud_resource_count = sum(1 for member in members if str(member.member_type or "") == "cloud_resource")
        return {
            "id": int(group.id),
            "name": str(group.name or ""),
            "description": group.description,
            "criticality": str(group.criticality or "standard"),
            "owner_team": group.owner_team,
            "color": str(group.color or "#0ea5e9"),
            "is_active": bool(group.is_active),
            "device_count": int(device_count),
            "cloud_resource_count": int(cloud_resource_count),
            "member_count": int(len(members)),
            "health": dict(health or {}),
            "created_at": group.created_at,
            "updated_at": group.updated_at,
        }

    @classmethod
    def serialize_member(cls, member: ServiceGroupMember) -> Dict[str, Any]:
        if str(member.member_type or "") == "device" and member.device is not None:
            device = member.device
            subtitle_parts = [str(device.ip_address or "").strip(), str(device.role or "").strip()]
            return {
                "id": int(member.id),
                "member_type": "device",
                "role_label": member.role_label,
                "display_name": str(device.name or ""),
                "subtitle": " | ".join([part for part in subtitle_parts if part]) or None,
                "status": str(device.management_state or "managed"),
                "provider": None,
                "region": None,
                "resource_type": "device",
                "state": str(device.status or "") or None,
                "device_id": int(device.id),
                "cloud_resource_id": None,
                "resource_id": None,
                "created_at": member.created_at,
            }
        resource = member.cloud_resource
        account = getattr(resource, "account", None)
        resource_name = str((resource.name if resource is not None else None) or (resource.resource_id if resource is not None else "") or "").strip()
        subtitle_parts = [
            str((account.provider if account is not None else "") or "").strip().upper(),
            str((resource.resource_type if resource is not None else "") or "").strip(),
            str((resource.region if resource is not None else "") or "").strip(),
        ]
        return {
            "id": int(member.id),
            "member_type": "cloud_resource",
            "role_label": member.role_label,
            "display_name": resource_name or "Cloud Resource",
            "subtitle": " | ".join([part for part in subtitle_parts if part]) or None,
            "status": str((resource.state if resource is not None else "") or "") or None,
            "provider": str((account.provider if account is not None else "") or "") or None,
            "region": str((resource.region if resource is not None else "") or "") or None,
            "resource_type": str((resource.resource_type if resource is not None else "") or "") or None,
            "state": str((resource.state if resource is not None else "") or "") or None,
            "device_id": None,
            "cloud_resource_id": int(resource.id) if resource is not None else None,
            "resource_id": str((resource.resource_id if resource is not None else "") or "") or None,
            "created_at": member.created_at,
        }

    @classmethod
    def serialize_group_detail(cls, group: ServiceGroup, *, health: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        summary = cls.serialize_group_summary(group, health=health)
        summary["members"] = [cls.serialize_member(member) for member in sorted(list(group.members or []), key=lambda row: int(row.id))]
        return summary

    @classmethod
    def _issue_cloud_resource_ids(cls, issue: Issue) -> set[str]:
        device = getattr(issue, "device", None)
        variables = getattr(device, "variables", None)
        if not isinstance(variables, dict):
            return set()
        cloud = variables.get("cloud")
        if not isinstance(cloud, dict):
            return set()
        refs = [row for row in list(cloud.get("refs") or []) if isinstance(row, dict)]
        out: set[str] = set()
        for ref in refs:
            resource_id = str(ref.get("resource_id") or "").strip()
            if resource_id:
                out.add(resource_id)
        return out

    @classmethod
    def build_issue_service_impacts(cls, db: Session, issue: Issue) -> list[Dict[str, Any]]:
        device_id = int(getattr(issue, "device_id", 0) or 0)
        cloud_resource_ids = cls._issue_cloud_resource_ids(issue)
        groups = cls.list_groups(db)
        impacts: list[Dict[str, Any]] = []
        matched_groups: list[ServiceGroup] = []

        for group in groups:
            matched_members: list[Dict[str, Any]] = []
            for member in list(group.members or []):
                member_type = str(member.member_type or "")
                if member_type == "device" and device_id > 0 and int(getattr(member, "device_id", 0) or 0) == device_id:
                    matched_members.append(
                        {
                            "member_type": "device",
                            "member_id": int(member.id),
                            "display_name": str(getattr(getattr(member, "device", None), "name", "") or ""),
                            "role_label": str(member.role_label or "").strip() or None,
                        }
                    )
                elif member_type == "cloud_resource" and member.cloud_resource is not None:
                    resource_id = str(getattr(member.cloud_resource, "resource_id", "") or "").strip()
                    if resource_id and resource_id in cloud_resource_ids:
                        matched_members.append(
                            {
                                "member_type": "cloud_resource",
                                "member_id": int(member.id),
                                "display_name": str(getattr(member.cloud_resource, "name", None) or resource_id),
                                "role_label": str(member.role_label or "").strip() or None,
                            }
                        )
            if not matched_members:
                continue
            matched_groups.append(group)
            impacts.append(
                {
                    "id": int(group.id),
                    "name": str(group.name or ""),
                    "criticality": str(group.criticality or "standard"),
                    "owner_team": str(group.owner_team or "").strip() or None,
                    "color": str(group.color or "#0ea5e9"),
                    "matched_member_count": len(matched_members),
                    "matched_members": matched_members,
                }
            )

        health_map = cls.build_group_health_map(db, matched_groups)
        for row in impacts:
            health = dict(health_map.get(int(row.get("id") or 0)) or {})
            row["health_score"] = int(health.get("health_score") or 0)
            row["health_status"] = str(health.get("health_status") or "review")
            row["active_issue_count"] = int(health.get("active_issue_count") or 0)
            row["offline_device_count"] = int(health.get("offline_device_count") or 0)
            row["discovered_only_device_count"] = int(health.get("discovered_only_device_count") or 0)

        impacts.sort(
            key=lambda row: (
                -int(cls.CRITICALITY_RANK.get(str(row.get("criticality") or "standard"), 1)),
                str(row.get("name") or "").lower(),
            )
        )
        return impacts

    @classmethod
    def build_issue_service_impact_summary_map(cls, db: Session, issues: list[Issue]) -> Dict[int, Dict[str, Any]]:
        out: Dict[int, Dict[str, Any]] = {}
        for issue in list(issues or []):
            issue_id = int(getattr(issue, "id", 0) or 0)
            if issue_id <= 0:
                continue
            impacts = cls.build_issue_service_impacts(db, issue)
            top = impacts[0] if impacts else {}
            review_group_count = sum(
                1
                for row in impacts
                if str(row.get("health_status") or "").strip().lower() in {"degraded", "critical", "review"}
            )
            critical_group_count = sum(
                1 for row in impacts if str(row.get("health_status") or "").strip().lower() == "critical"
            )
            out[issue_id] = {
                "count": len(impacts),
                "primary_group_id": int(top.get("id") or 0) if top else None,
                "primary_name": str(top.get("name") or "") or None,
                "highest_criticality": str(top.get("criticality") or "") or None,
                "matched_member_count": int(top.get("matched_member_count") or 0),
                "primary_health_score": int(top.get("health_score") or 0) if top else None,
                "primary_health_status": str(top.get("health_status") or "") or None,
                "review_group_count": int(review_group_count),
                "critical_group_count": int(critical_group_count),
            }
        return out

    @classmethod
    def summarize_service_impacts(cls, impacts: list[Dict[str, Any]]) -> Dict[str, Any]:
        top = impacts[0] if impacts else {}
        return {
            "count": int(len(list(impacts or []))),
            "primary_group_id": int(top.get("id") or 0) if top else None,
            "primary_name": str(top.get("name") or "") or None,
            "highest_criticality": str(top.get("criticality") or "") or None,
            "matched_member_count": int(top.get("matched_member_count") or 0),
        }

    @classmethod
    def build_approval_service_impacts(cls, db: Session, approval_request: Any) -> list[Dict[str, Any]]:
        from app.services.issue_approval_context_service import IssueApprovalContextService

        payload = dict(getattr(approval_request, "payload", None) or {})
        device_ids = IssueApprovalContextService._payload_device_ids(payload)
        account_ids = IssueApprovalContextService._payload_account_ids(payload)
        resource_ids = IssueApprovalContextService._payload_resource_ids(payload)
        regions = {str(row).strip().lower() for row in IssueApprovalContextService._payload_regions(payload) if str(row).strip()}
        providers = {str(row).strip().lower() for row in IssueApprovalContextService._payload_providers(payload) if str(row).strip()}

        groups = cls.list_groups(db)
        impacts: list[Dict[str, Any]] = []

        for group in groups:
            matched_members: list[Dict[str, Any]] = []
            seen_member_ids: set[int] = set()
            for member in list(group.members or []):
                member_id = int(getattr(member, "id", 0) or 0)
                member_type = str(member.member_type or "").strip().lower()
                match_reason: str | None = None

                if member_type == "device":
                    device_id = int(getattr(member, "device_id", 0) or 0)
                    if device_id > 0 and device_id in device_ids:
                        match_reason = "device_scope"
                elif member_type == "cloud_resource" and member.cloud_resource is not None:
                    resource = member.cloud_resource
                    account = getattr(resource, "account", None)
                    resource_id = str(getattr(resource, "resource_id", "") or "").strip()
                    account_id = int(getattr(resource, "account_id", 0) or 0)
                    provider = str(getattr(account, "provider", "") or "").strip().lower()
                    region = str(getattr(resource, "region", "") or "").strip().lower()

                    if resource_id and resource_id in resource_ids:
                        match_reason = "resource_scope"
                    elif account_id > 0 and account_id in account_ids:
                        match_reason = "account_scope"
                    elif region and region in regions and (not providers or provider in providers):
                        match_reason = "region_scope"
                    elif provider and provider in providers and not regions and not account_ids and not resource_ids:
                        match_reason = "provider_scope"

                if not match_reason or member_id <= 0 or member_id in seen_member_ids:
                    continue

                seen_member_ids.add(member_id)
                serialized = cls.serialize_member(member)
                matched_members.append(
                    {
                        "member_type": str(serialized.get("member_type") or member_type),
                        "member_id": member_id,
                        "display_name": str(serialized.get("display_name") or "").strip() or f"member-{member_id}",
                        "role_label": str(serialized.get("role_label") or "").strip() or None,
                        "match_reason": match_reason,
                    }
                )

            if not matched_members:
                continue

            impacts.append(
                {
                    "id": int(group.id),
                    "name": str(group.name or ""),
                    "criticality": str(group.criticality or "standard"),
                    "owner_team": str(group.owner_team or "").strip() or None,
                    "color": str(group.color or "#0ea5e9"),
                    "matched_member_count": len(matched_members),
                    "matched_members": matched_members,
                }
            )

        impacts.sort(
            key=lambda row: (
                -int(cls.CRITICALITY_RANK.get(str(row.get("criticality") or "standard"), 1)),
                str(row.get("name") or "").lower(),
            )
        )
        return impacts
