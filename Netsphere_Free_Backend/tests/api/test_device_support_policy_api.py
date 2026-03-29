from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from app.core.license import LicenseSchema
from app.models.device import ConfigTemplate, Device, Site
from app.models.discovery import DiscoveredDevice, DiscoveryJob
from app.models.settings import SystemSetting
from app.models.topology_candidate import TopologyNeighborCandidate
from app.models.visual_config import VisualBlueprint, VisualBlueprintVersion, VisualDeployJob
from app.models.ztp_queue import ZtpQueue, ZtpStatus
from app.services.device_support_policy_service import DeviceSupportPolicyService
from app.services.license_service import LicenseService
from app.services.parser_quality_service import ParserQualityService


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _extract_error(res):
    body = res.json()
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return err
        detail = body.get("detail")
        if isinstance(detail, dict):
            return detail
    return {}


def _upsert_setting(db, *, key: str, value: str, category: str = "General"):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = value
        row.category = category
    else:
        db.add(SystemSetting(key=key, value=value, description="", category=category))


def _set_vendor_policy_override(db, *, features: dict, reason: str):
    policy = DeviceSupportPolicyService._clone_default_policy()
    policy["overrides"] = [
        {
            "vendor": "cisco",
            "tier": "limited",
            "reason": reason,
            "features": dict(features or {}),
        }
    ]
    _upsert_setting(
        db,
        key=DeviceSupportPolicyService.SETTING_KEY,
        value=json.dumps(policy, ensure_ascii=False, separators=(",", ":")),
    )
    db.commit()


def _allow_license_features(monkeypatch, features: list[str]):
    lic = LicenseSchema(
        customer="E2E-Policy-Test",
        expiration=datetime.now(timezone.utc) + timedelta(days=30),
        max_devices=1000,
        features=list(features or []),
        is_valid=True,
        status="Active",
    )
    monkeypatch.setattr(
        LicenseService,
        "get_effective_license",
        staticmethod(lambda _db, _lic=lic: _lic),
    )


def test_device_sync_skipped_when_vendor_support_policy_blocks_sync(client, operator_user_token, db):
    policy = DeviceSupportPolicyService._clone_default_policy()
    policy["overrides"] = [
        {
            "device_type": "cisco_xe",
            "tier": "limited",
            "reason": "api_sync_block",
            "features": {"sync": False},
        }
    ]
    db.add(
        SystemSetting(
            key=DeviceSupportPolicyService.SETTING_KEY,
            value=json.dumps(policy, ensure_ascii=False, separators=(",", ":")),
            description="",
            category="General",
        )
    )
    device = Device(
        name="policy-api-sync-blocked",
        hostname="policy-api-sync-blocked",
        ip_address="10.50.50.10",
        device_type="cisco_xe",
        model="C9300-48P",
    )
    db.add(device)
    db.commit()
    db.refresh(device)

    res = client.post(
        f"/api/v1/devices/{int(device.id)}/sync",
        headers=operator_user_token,
    )
    assert res.status_code == 200
    payload = _unwrap(res.json())
    assert str(payload.get("status")) == "skipped"
    assert str(payload.get("message")) == "vendor_support_policy_blocked"


def test_vendor_support_block_is_consistent_across_manual_discovery_ztp_and_api_paths(
    client,
    admin_user_token,
    db,
    monkeypatch,
):
    _allow_license_features(monkeypatch, ["ztp"])
    _set_vendor_policy_override(
        db,
        features={
            "discovery": False,
            "ztp": False,
            "config": False,
            "sync": False,
        },
        reason="e2e_path_block",
    )

    site = Site(name="policy-path-site")
    template = ConfigTemplate(name="policy-path-template", category="ops", content="hostname TEST", tags="v1")
    api_device = Device(
        name="policy-path-api-device",
        hostname="policy-path-api-device",
        ip_address="10.61.0.10",
        device_type="cisco_ios",
        model="C9300",
        status="online",
        site_obj=site,
    )
    db.add_all([site, template, api_device])
    db.flush()
    db.add(
        DiscoveryJob(
            cidr="10.61.0.0/24",
            status="completed",
            site_id=int(site.id),
            logs="",
        )
    )
    db.flush()
    discovered = DiscoveredDevice(
        job_id=int(db.query(DiscoveryJob).order_by(DiscoveryJob.id.desc()).first().id),
        ip_address="10.61.0.20",
        hostname="policy-discovered",
        vendor="Cisco",
        model="C9300",
        os_version="17.9",
        device_type="cisco_ios",
        snmp_status="reachable",
        status="new",
        vendor_confidence=0.95,
    )
    db.add(discovered)
    ztp_item = ZtpQueue(
        serial_number="ZTP-POLICY-BLOCK-001",
        status=ZtpStatus.NEW.value,
        platform="C9300",
        software_version="17.9",
        device_type="cisco_ios",
    )
    db.add(ztp_item)
    db.commit()
    db.refresh(site)
    db.refresh(template)
    db.refresh(api_device)
    db.refresh(discovered)
    db.refresh(ztp_item)

    # 1) Manual onboarding path should block with DEVICE_SUPPORT_BLOCKED.
    manual_res = client.post(
        "/api/v1/devices/",
        json={
            "name": "policy-manual-blocked",
            "ip_address": "10.61.0.11",
            "device_type": "cisco_ios",
            "site_id": int(site.id),
        },
        headers=admin_user_token,
    )
    assert manual_res.status_code == 409
    manual_error = _extract_error(manual_res)
    assert str(manual_error.get("code")) == "DEVICE_SUPPORT_BLOCKED"
    assert str((manual_error.get("details") or {}).get("feature")) == "discovery"

    # 2) Discovery approval path should block with DEVICE_SUPPORT_BLOCKED.
    discovery_res = client.post(
        f"/api/v1/discovery/approve/{int(discovered.id)}",
        headers=admin_user_token,
    )
    assert discovery_res.status_code == 409
    discovery_error = _extract_error(discovery_res)
    assert str(discovery_error.get("code")) == "DEVICE_SUPPORT_BLOCKED"
    assert str((discovery_error.get("details") or {}).get("feature")) == "discovery"

    # 3) ZTP approval path should block with DEVICE_SUPPORT_BLOCKED.
    ztp_res = client.post(
        f"/api/v1/ztp/queue/{int(ztp_item.id)}/approve",
        json={
            "site_id": int(site.id),
            "template_id": int(template.id),
            "target_hostname": "ztp-blocked-host",
        },
        headers=admin_user_token,
    )
    assert ztp_res.status_code == 409
    ztp_error = _extract_error(ztp_res)
    assert str(ztp_error.get("code")) == "DEVICE_SUPPORT_BLOCKED"

    # 4) API config execution path should block with DEVICE_SUPPORT_BLOCKED.
    api_res = client.post(
        "/api/v1/devices/Netsphere_Free_Deploy/vlan",
        json={"device_ids": [int(api_device.id)], "vlan_id": 120, "vlan_name": "BLOCKED"},
        headers=admin_user_token,
    )
    assert api_res.status_code == 409
    api_error = _extract_error(api_res)
    assert str(api_error.get("code")) == "DEVICE_SUPPORT_BLOCKED"
    assert str((api_error.get("details") or {}).get("feature")) == "config"


def test_rollback_unsupported_vendor_block_is_consistent_for_template_fabric_compliance_and_visual(
    client,
    admin_user_token,
    db,
    monkeypatch,
):
    _allow_license_features(monkeypatch, ["fabric", "compliance", "visual_config"])
    _set_vendor_policy_override(
        db,
        features={
            "discovery": True,
            "ztp": True,
            "config": True,
            "rollback": False,
        },
        reason="e2e_rollback_block",
    )

    d1 = Device(
        name="rollback-block-1",
        hostname="rollback-block-1",
        ip_address="10.62.0.1",
        device_type="cisco_ios",
        model="C9300",
        status="online",
    )
    d2 = Device(
        name="rollback-block-2",
        hostname="rollback-block-2",
        ip_address="10.62.0.2",
        device_type="cisco_ios",
        model="C9300",
        status="online",
    )
    template = ConfigTemplate(name="rollback-block-template", category="ops", content="hostname X", tags="v1")
    db.add_all([d1, d2, template])
    db.flush()

    graph = {
        "nodes": [
            {
                "id": "target-1",
                "type": "target",
                "position": {"x": 100, "y": 120},
                "data": {"target_type": "devices", "device_ids": [int(d1.id)]},
            }
        ],
        "edges": [],
        "viewport": None,
    }
    blueprint = VisualBlueprint(name="rollback-blueprint", description="rollback test", owner_id=None)
    db.add(blueprint)
    db.flush()
    version = VisualBlueprintVersion(blueprint_id=int(blueprint.id), version=1, graph_json=graph)
    db.add(version)
    db.flush()
    blueprint.current_version_id = int(version.id)
    job = VisualDeployJob(
        blueprint_id=int(blueprint.id),
        blueprint_version_id=int(version.id),
        requested_by=None,
        status="success",
        target_device_ids=[int(d1.id)],
        summary={"type": "deploy"},
    )
    db.add(job)
    db.commit()
    db.refresh(d1)
    db.refresh(d2)
    db.refresh(template)
    db.refresh(job)

    template_res = client.post(
        f"/api/v1/templates/{int(template.id)}/deploy",
        json={"device_ids": [int(d1.id)], "rollback_on_failure": True},
        headers=admin_user_token,
    )
    assert template_res.status_code == 409
    template_err = _extract_error(template_res)
    assert str(template_err.get("code")) == "ROLLBACK_STRATEGY_UNSUPPORTED"

    fabric_res = client.post(
        "/api/v1/fabric/deploy",
        json={
            "spine_ids": [int(d1.id)],
            "leaf_ids": [int(d2.id)],
            "dry_run": True,
            "rollback_on_error": True,
        },
        headers=admin_user_token,
    )
    assert fabric_res.status_code == 409
    fabric_err = _extract_error(fabric_res)
    assert str(fabric_err.get("code")) == "ROLLBACK_STRATEGY_UNSUPPORTED"

    compliance_res = client.post(
        "/api/v1/compliance/drift/remediate-batch",
        json={"device_ids": [int(d1.id)], "rollback_on_failure": True},
        headers=admin_user_token,
    )
    assert compliance_res.status_code == 409
    compliance_err = _extract_error(compliance_res)
    assert str(compliance_err.get("code")) == "ROLLBACK_STRATEGY_UNSUPPORTED"

    visual_res = client.post(
        f"/api/v1/visual/deploy-jobs/{int(job.id)}/rollback",
        json={"save_backup": False},
        headers=admin_user_token,
    )
    assert visual_res.status_code == 409
    visual_err = _extract_error(visual_res)
    assert str(visual_err.get("code")) == "ROLLBACK_STRATEGY_UNSUPPORTED"


def test_parser_low_confidence_issue_is_excluded_from_auto_approve_and_remains_in_candidate_queue(
    client,
    operator_user_token,
    normal_user_token,
    db,
):
    site = Site(name="parser-chain-site")
    source = Device(
        name="parser-chain-src",
        hostname="parser-chain-src",
        ip_address="10.63.0.1",
        device_type="cisco_ios",
        status="online",
        site_obj=site,
    )
    db.add_all([site, source])
    db.flush()

    _upsert_setting(db, key="auto_approve_enabled", value="true")
    _upsert_setting(db, key="auto_approve_min_vendor_confidence", value="0")
    _upsert_setting(db, key="auto_approve_require_snmp_reachable", value="true")
    _upsert_setting(db, key="auto_approve_block_severities", value="warn,error")
    _upsert_setting(db, key="topology_candidate_low_confidence_threshold", value="0.7")

    job = DiscoveryJob(cidr="10.63.0.0/24", status="completed", site_id=int(site.id), logs="")
    db.add(job)
    db.flush()

    parsed = ParserQualityService.normalize_discovery_result(
        {
            "ip_address": "10.63.0.20",
            "hostname": "parser-low-device",
            "vendor": "Cisco",
            "model": "",
            "os_version": "",
            "device_type": "unknown",
            "snmp_status": "reachable",
            "vendor_confidence": 0.2,
        },
        low_conf_threshold=0.9,
    )
    issues = list(parsed.get("issues") or [])
    assert any(str(i.get("code") or "") == "parser_low_confidence" for i in issues)

    discovered = DiscoveredDevice(
        job_id=int(job.id),
        ip_address=str(parsed.get("ip_address")),
        hostname=str(parsed.get("hostname")),
        vendor=str(parsed.get("vendor")),
        model=str(parsed.get("model") or ""),
        os_version=str(parsed.get("os_version") or ""),
        device_type=str(parsed.get("device_type") or "unknown"),
        snmp_status=str(parsed.get("snmp_status") or "unknown"),
        status="new",
        vendor_confidence=float(parsed.get("vendor_confidence") or 0.0),
        issues=issues,
        evidence=dict(parsed.get("evidence") or {}),
    )
    db.add(discovered)
    db.add(
        TopologyNeighborCandidate(
            discovery_job_id=int(job.id),
            source_device_id=int(source.id),
            neighbor_name="parser-low-neighbor",
            mgmt_ip=str(parsed.get("ip_address")),
            status="low_confidence",
            confidence=0.2,
            reason="parser_low_confidence",
        )
    )
    db.commit()
    db.refresh(discovered)

    approve_res = client.post(
        f"/api/v1/discovery/jobs/{int(job.id)}/approve-all",
        params={"policy": True},
        headers=operator_user_token,
    )
    assert approve_res.status_code == 200
    approve_payload = _unwrap(approve_res.json())
    assert int(approve_payload.get("approved_count") or 0) == 0
    assert int(approve_payload.get("skipped_count") or 0) == 1
    skip_breakdown = dict(approve_payload.get("skip_breakdown") or {})
    assert int(skip_breakdown.get("low_confidence_link") or 0) + int(skip_breakdown.get("blocked_issue_severity") or 0) >= 1

    discovered_row = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == int(discovered.id)).first()
    assert discovered_row is not None
    assert str(discovered_row.status or "") == "new"
    current_issues = list(getattr(discovered_row, "issues", None) or [])
    assert any(str(i.get("code") or "") == "parser_low_confidence" for i in current_issues)

    queue_res = client.get(
        "/api/v1/topology/candidates/summary",
        params={"site_id": int(site.id)},
        headers=normal_user_token,
    )
    assert queue_res.status_code == 200
    queue_payload = _unwrap(queue_res.json())
    totals = dict(queue_payload.get("totals") or {})
    assert int(totals.get("backlog_low_confidence") or 0) >= 1
