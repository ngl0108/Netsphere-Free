from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db
from app.models.user import User
from app.services.discovery_hint_benchmark_service import DiscoveryHintBenchmarkService
from app.services.discovery_hint_rule_service import DiscoveryHintRuleService
from app.services.discovery_hint_seed_rule_service import DiscoveryHintSeedRuleService
from app.services.discovery_hint_sync_service import DiscoveryHintSyncService
from app.services.discovery_hint_telemetry_service import DiscoveryHintTelemetryService
from app.services.oui_service import OUIService


router = APIRouter()


class DiscoveryHintRuleInput(BaseModel):
    rule_key: str
    vendor_family: Optional[str] = None
    match_conditions: Dict[str, Any] = Field(default_factory=dict)
    driver_overrides: List[str] = Field(default_factory=list)
    score_bonus: float = 0.0
    evidence_count: int = 0
    source: str = "manual"
    is_active: bool = True
    expires_at: Optional[datetime] = None

    model_config = ConfigDict(extra="ignore")


class DiscoveryHintRuleBatchUpsertRequest(BaseModel):
    rules: List[DiscoveryHintRuleInput] = Field(default_factory=list)


class DiscoveryHintScoreAdjustmentApplyRequest(BaseModel):
    rule_keys: List[str] = Field(default_factory=list)


class DiscoveryHintAliasCandidateApplyRequest(BaseModel):
    raw_vendors: List[str] = Field(default_factory=list)


class DiscoveryHintSeedRuleDraftApplyRequest(BaseModel):
    rule_keys: List[str] = Field(default_factory=list)


class DiscoveryHintTelemetryEventInput(BaseModel):
    event_type: str = "unknown"
    target_ip: Optional[str] = None
    mac: Optional[str] = None
    oui_prefix: Optional[str] = None
    raw_vendor: Optional[str] = None
    normalized_vendor: Optional[str] = None
    seed_device_id: Optional[int] = None
    seed_ip: Optional[str] = None
    seed_vendor: Optional[str] = None
    local_interface: Optional[str] = None
    neighbor_name: Optional[str] = None
    neighbor_mgmt_ip: Optional[str] = None
    chosen_driver: Optional[str] = None
    final_driver: Optional[str] = None
    success: bool = False
    failure_reason: Optional[str] = None
    candidates: List[Dict[str, Any]] = Field(default_factory=list)

    model_config = ConfigDict(extra="allow")


class DiscoveryHintTelemetryIngestRequest(BaseModel):
    events: List[DiscoveryHintTelemetryEventInput] = Field(default_factory=list)


@router.get("/rules")
def list_discovery_hint_rules(
    include_inactive: bool = Query(False),
    current_user: User = Depends(deps.require_admin),
):
    items = DiscoveryHintRuleService.list_rules_detailed(include_inactive=include_inactive)
    active_items = [item for item in items if bool(item.get("is_active"))]
    return {
        "count": len(items),
        "active_count": len(active_items),
        "version": DiscoveryHintRuleService._compute_version(active_items),
        "items": items,
    }


@router.get("/summary")
def get_discovery_hint_summary(
    benchmark_limit: int = Query(500, ge=50, le=5000),
    current_user: User = Depends(deps.require_operator),
    db: Session = Depends(get_db),
):
    return DiscoveryHintSyncService.build_status_summary(db, benchmark_limit=benchmark_limit)


@router.get("/rules/ota")
def get_discovery_hint_rule_snapshot(
    since_version: Optional[str] = Query(None),
    current_user: User = Depends(deps.require_viewer),
):
    return DiscoveryHintRuleService.build_ota_snapshot(since_version=since_version)


@router.post("/rules")
def upsert_discovery_hint_rules(
    request: DiscoveryHintRuleBatchUpsertRequest,
    current_user: User = Depends(deps.require_admin),
):
    ids: List[int] = []
    for rule in request.rules or []:
        row_id = DiscoveryHintRuleService.upsert_rule(rule.model_dump())
        if isinstance(row_id, int):
            ids.append(row_id)
    snapshot = DiscoveryHintRuleService.build_ota_snapshot()
    return {
        "accepted": len(request.rules or []),
        "upserted": len(ids),
        "ids": ids,
        "version": snapshot.get("version"),
    }


@router.post("/rules/score-adjustments/apply")
def apply_discovery_hint_score_adjustments(
    request: DiscoveryHintScoreAdjustmentApplyRequest,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(get_db),
):
    status_summary = DiscoveryHintSyncService.build_status_summary(db, benchmark_limit=500)
    adjustments = list(status_summary.get("score_adjustments") or [])
    if request.rule_keys:
        allowed_keys = {str(value or "").strip() for value in request.rule_keys if str(value or "").strip()}
        adjustments = [item for item in adjustments if str(item.get("rule_key") or "").strip() in allowed_keys]

    rules = DiscoveryHintRuleService.list_rules_detailed(include_inactive=False)
    rules_by_key = {
        str(item.get("rule_key") or "").strip(): item
        for item in rules
        if str(item.get("rule_key") or "").strip()
    }

    applied_rule_keys: List[str] = []
    ids: List[int] = []
    for adjustment in adjustments:
        rule_key = str(adjustment.get("rule_key") or "").strip()
        current_rule = rules_by_key.get(rule_key)
        if not current_rule:
            continue
        payload = {
            "rule_key": rule_key,
            "vendor_family": current_rule.get("vendor_family"),
            "match_conditions": dict(current_rule.get("match_conditions") or {}),
            "driver_overrides": list(current_rule.get("driver_overrides") or []),
            "score_bonus": float(adjustment.get("suggested_score_bonus") or 0.0),
            "evidence_count": int(current_rule.get("evidence_count") or 0),
            "source": str(current_rule.get("source") or "telemetry").strip() or "telemetry",
            "is_active": bool(current_rule.get("is_active", True)),
            "expires_at": current_rule.get("expires_at"),
        }
        row_id = DiscoveryHintRuleService.upsert_rule(payload)
        if isinstance(row_id, int):
            ids.append(row_id)
            applied_rule_keys.append(rule_key)

    snapshot = DiscoveryHintRuleService.build_ota_snapshot()
    return {
        "accepted": len(adjustments),
        "applied": len(applied_rule_keys),
        "ids": ids,
        "rule_keys": applied_rule_keys,
        "version": snapshot.get("version"),
    }


@router.post("/rules/alias-candidates/apply")
def apply_discovery_hint_alias_candidates(
    request: DiscoveryHintAliasCandidateApplyRequest,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(get_db),
):
    status_summary = DiscoveryHintSyncService.build_status_summary(db, benchmark_limit=500)
    candidates = list(status_summary.get("alias_candidates") or [])
    if request.raw_vendors:
        allowed = {str(value or "").strip().lower() for value in request.raw_vendors if str(value or "").strip()}
        candidates = [item for item in candidates if str(item.get("raw_vendor") or "").strip().lower() in allowed]

    ids: List[int] = []
    applied_raw_vendors: List[str] = []
    for candidate in candidates:
        raw_vendor = str(candidate.get("raw_vendor") or "").strip()
        vendor_family = str(candidate.get("suggested_vendor_family") or "").strip()
        if not raw_vendor or not vendor_family:
            continue
        row_id = OUIService.upsert_vendor_alias(raw_alias=raw_vendor, vendor_family=vendor_family, source="telemetry")
        if isinstance(row_id, int):
            ids.append(row_id)
            applied_raw_vendors.append(raw_vendor)

    return {
        "accepted": len(candidates),
        "applied": len(applied_raw_vendors),
        "ids": ids,
        "raw_vendors": applied_raw_vendors,
        "aliases": OUIService.list_vendor_aliases(),
    }


@router.post("/rules/seed-rule-drafts/apply")
def apply_discovery_hint_seed_rule_drafts(
    request: DiscoveryHintSeedRuleDraftApplyRequest,
    current_user: User = Depends(deps.require_admin),
    db: Session = Depends(get_db),
):
    status_summary = DiscoveryHintSyncService.build_status_summary(db, benchmark_limit=500)
    drafts = list(status_summary.get("seed_rule_drafts") or [])
    if request.rule_keys:
        allowed_keys = {str(value or "").strip() for value in request.rule_keys if str(value or "").strip()}
        drafts = [item for item in drafts if str(item.get("rule_key") or "").strip() in allowed_keys]

    ids: List[int] = []
    applied_rule_keys: List[str] = []
    for draft in drafts:
        payload = {
            "rule_key": str(draft.get("rule_key") or "").strip(),
            "vendor_family": str(draft.get("vendor_family") or "").strip() or None,
            "match_conditions": dict(draft.get("match_conditions") or {}),
            "driver_overrides": list(draft.get("driver_overrides") or []),
            "score_bonus": float(draft.get("score_bonus") or 0.0),
            "evidence_count": int(draft.get("sample_count") or 0),
            "source": "telemetry_draft",
            "is_active": True,
        }
        if not payload["rule_key"] or not payload["driver_overrides"]:
            continue
        row_id = DiscoveryHintRuleService.upsert_rule(payload)
        if isinstance(row_id, int):
            ids.append(row_id)
            applied_rule_keys.append(payload["rule_key"])

    snapshot = DiscoveryHintRuleService.build_ota_snapshot()
    return {
        "accepted": len(drafts),
        "applied": len(applied_rule_keys),
        "ids": ids,
        "rule_keys": applied_rule_keys,
        "version": snapshot.get("version"),
    }


@router.post("/rules/seed-defaults")
def install_seed_discovery_hint_rules(
    current_user: User = Depends(deps.require_admin),
):
    result = DiscoveryHintSeedRuleService.install_defaults()
    snapshot = DiscoveryHintRuleService.build_ota_snapshot()
    return {
        **result,
        "version": snapshot.get("version"),
    }


@router.get("/telemetry")
def list_discovery_hint_telemetry(
    limit: int = Query(50, ge=1, le=500),
    include_payload: bool = Query(False),
    current_user: User = Depends(deps.require_admin),
):
    items = DiscoveryHintTelemetryService.list_recent(limit=limit, include_payload=include_payload)
    return {
        "count": len(items),
        "items": items,
    }


@router.get("/telemetry/summary")
def get_discovery_hint_telemetry_summary(
    limit: int = Query(500, ge=1, le=5000),
    current_user: User = Depends(deps.require_admin),
):
    return DiscoveryHintBenchmarkService.summarize_recent(limit=limit)


@router.post("/telemetry")
def ingest_discovery_hint_telemetry(
    request: DiscoveryHintTelemetryIngestRequest,
    current_user: User = Depends(deps.require_operator),
):
    result = DiscoveryHintTelemetryService.record_events([event.model_dump() for event in (request.events or [])])
    return result
