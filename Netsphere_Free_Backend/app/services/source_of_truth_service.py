from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session, joinedload

from app.models.asset_change_event import AssetChangeEvent
from app.models.cloud import CloudAccount, CloudResource
from app.models.device import Device
from app.models.monitoring_profile import MonitoringProfileAssignment
from app.models.service_group import ServiceGroup, ServiceGroupMember
from app.schemas.source_of_truth import (
    SourceOfTruthChangeEventResponse,
    SourceOfTruthCoverageBlock,
    SourceOfTruthDistributionBlock,
    SourceOfTruthDistributionItem,
    SourceOfTruthMetricBlock,
    SourceOfTruthSummaryResponse,
)


class SourceOfTruthService:
    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    @classmethod
    def record_event(
        cls,
        db: Session,
        *,
        asset_kind: str,
        asset_key: str,
        action: str,
        summary: str,
        asset_name: Optional[str] = None,
        actor_name: Optional[str] = None,
        actor_role: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        commit: bool = True,
    ) -> AssetChangeEvent:
        row = AssetChangeEvent(
            asset_kind=str(asset_kind or "").strip() or "asset",
            asset_key=str(asset_key or "").strip() or "unknown",
            asset_name=str(asset_name or "").strip() or None,
            action=str(action or "").strip() or "updated",
            summary=str(summary or "").strip() or "Asset updated",
            actor_name=str(actor_name or "").strip() or None,
            actor_role=str(actor_role or "").strip() or None,
            details=dict(details or {}),
        )
        db.add(row)
        if commit:
            db.commit()
            db.refresh(row)
        return row

    @classmethod
    def list_recent_changes(cls, db: Session, *, limit: int = 12) -> list[SourceOfTruthChangeEventResponse]:
        rows = (
            db.query(AssetChangeEvent)
            .order_by(AssetChangeEvent.created_at.desc(), AssetChangeEvent.id.desc())
            .limit(max(1, int(limit)))
            .all()
        )
        return [
            SourceOfTruthChangeEventResponse(
                id=int(row.id),
                asset_kind=str(row.asset_kind or ""),
                asset_key=str(row.asset_key or ""),
                asset_name=str(row.asset_name or "").strip() or None,
                action=str(row.action or ""),
                summary=str(row.summary or ""),
                actor_name=str(row.actor_name or "").strip() or None,
                actor_role=str(row.actor_role or "").strip() or None,
                details=dict(row.details or {}),
                created_at=row.created_at,
            )
            for row in rows
        ]

    @classmethod
    def _serialize_distribution(cls, counter: Counter[str], *, limit: int = 6) -> list[SourceOfTruthDistributionItem]:
        rows = [
            SourceOfTruthDistributionItem(key=str(key), count=int(count))
            for key, count in counter.most_common(max(1, int(limit)))
            if str(key).strip()
        ]
        return rows

    @classmethod
    def build_summary(cls, db: Session) -> SourceOfTruthSummaryResponse:
        devices = db.query(Device).order_by(Device.id.asc()).all()
        accounts = db.query(CloudAccount).order_by(CloudAccount.id.asc()).all()
        resources = (
            db.query(CloudResource)
            .options(joinedload(CloudResource.account))
            .order_by(CloudResource.id.asc())
            .all()
        )
        groups = (
            db.query(ServiceGroup)
            .options(joinedload(ServiceGroup.members).joinedload(ServiceGroupMember.cloud_resource))
            .options(joinedload(ServiceGroup.members).joinedload(ServiceGroupMember.device))
            .order_by(ServiceGroup.id.asc())
            .all()
        )
        assigned_device_ids = {
            int(row.device_id)
            for row in db.query(MonitoringProfileAssignment.device_id).all()
            if getattr(row, "device_id", None) is not None
        }

        role_counter: Counter[str] = Counter()
        type_counter: Counter[str] = Counter()
        provider_counter: Counter[str] = Counter()

        managed_devices = 0
        discovered_only_devices = 0
        online_devices = 0
        offline_devices = 0
        devices_with_site = 0
        devices_with_hostname = 0
        devices_with_serial = 0

        for device in devices:
            management_state = str(getattr(device, "management_state", "managed") or "managed").strip().lower()
            status = str(getattr(device, "status", "offline") or "offline").strip().lower()
            role = str(getattr(device, "role", "") or "").strip().lower() or "unspecified"
            device_type = str(getattr(device, "device_type", "") or "").strip().lower() or "unspecified"

            role_counter[role] += 1
            type_counter[device_type] += 1

            if management_state == "managed":
                managed_devices += 1
            else:
                discovered_only_devices += 1

            if status == "online":
                online_devices += 1
            else:
                offline_devices += 1

            if getattr(device, "site_id", None):
                devices_with_site += 1
            if str(getattr(device, "hostname", "") or "").strip():
                devices_with_hostname += 1
            if str(getattr(device, "serial_number", "") or "").strip():
                devices_with_serial += 1

        mapped_cloud_ids: set[int] = set()
        service_groups_with_owner = 0
        service_groups_with_devices = 0
        service_groups_with_cloud_resources = 0
        service_group_members_total = 0

        for group in groups:
            members = list(group.members or [])
            service_group_members_total += len(members)
            if str(getattr(group, "owner_team", "") or "").strip():
                service_groups_with_owner += 1
            has_device = False
            has_cloud = False
            for member in members:
                member_type = str(getattr(member, "member_type", "") or "").strip().lower()
                if member_type == "device":
                    has_device = True
                if member_type == "cloud_resource" and getattr(member, "cloud_resource_id", None):
                    has_cloud = True
                    mapped_cloud_ids.add(int(member.cloud_resource_id))
            if has_device:
                service_groups_with_devices += 1
            if has_cloud:
                service_groups_with_cloud_resources += 1

        for account in accounts:
            provider = str(getattr(account, "provider", "") or "").strip().lower() or "unknown"
            provider_counter[provider] += 1

        metrics = SourceOfTruthMetricBlock(
            devices_total=int(len(devices)),
            managed_devices=int(managed_devices),
            discovered_only_devices=int(discovered_only_devices),
            online_devices=int(online_devices),
            offline_devices=int(offline_devices),
            cloud_accounts_total=int(len(accounts)),
            cloud_resources_total=int(len(resources)),
            service_groups_total=int(len(groups)),
            service_group_members_total=int(service_group_members_total),
        )
        coverage = SourceOfTruthCoverageBlock(
            devices_with_site=int(devices_with_site),
            devices_with_hostname=int(devices_with_hostname),
            devices_with_serial=int(devices_with_serial),
            devices_with_monitoring_profile=int(len(assigned_device_ids)),
            service_groups_with_owner=int(service_groups_with_owner),
            service_groups_with_devices=int(service_groups_with_devices),
            service_groups_with_cloud_resources=int(service_groups_with_cloud_resources),
            cloud_resources_mapped_to_services=int(len(mapped_cloud_ids)),
        )
        distributions = SourceOfTruthDistributionBlock(
            device_roles=cls._serialize_distribution(role_counter),
            device_types=cls._serialize_distribution(type_counter),
            cloud_providers=cls._serialize_distribution(provider_counter),
        )
        recent_changes = cls.list_recent_changes(db)
        return SourceOfTruthSummaryResponse(
            generated_at=cls._utcnow(),
            metrics=metrics,
            coverage=coverage,
            distributions=distributions,
            recent_changes=recent_changes,
        )
