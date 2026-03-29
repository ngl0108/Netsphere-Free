import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.db.session import get_db, SessionLocal
from app.models.approval import ApprovalRequest
from app.models.cloud import CloudAccount, CloudResource
from app.models.device import EventLog
from app.models.user import User
from app.schemas.cloud import (
    CloudAccountCreate,
    CloudAccountLedgerOperationResponse,
    CloudAccountLedgerResponse,
    CloudAccountResponse,
    CloudBootstrapRunRequest,
    CloudBootstrapRunResponse,
    CloudKpiSummaryResponse,
    CloudNormalizedResourceResponse,
    CloudPipelineRunRequest,
    CloudPipelineRunResponse,
    CloudPreflightRequest,
    CloudPreflightResponse,
    CloudProviderPresetResponse,
    CloudAccountUpdate,
    CloudResourceResponse,
    CloudScanResponse,
    mask_credentials,
    normalize_and_validate_credentials,
)
from app.services.cloud_credentials_service import (
    decrypt_credentials_for_runtime,
    encrypt_credentials_for_storage,
)
from app.services.cloud_bootstrap_service import CloudBootstrapService
from app.services.cloud_account_readiness_service import CloudAccountReadinessService
from app.services.cloud_normalization_service import CloudNormalizationService
from app.services.cloud_pipeline_service import CloudPipelineService
from app.services.cloud_preset_service import CloudPresetService
from app.services.cloud_service import CloudScanner
from app.services.change_policy_service import ChangePolicyService
from app.services.cloud_intent_execution_service import CloudIntentExecutionService
from app.services.hybrid_topology_service import HybridTopologyService
from app.services.license_policy_service import LicensePolicyViolation
from app.services.audit_service import AuditService
from app.services.source_of_truth_service import SourceOfTruthService

router = APIRouter()

CLOUD_ACCOUNT_PREFLIGHT_EVENT_ID = "CLOUD_ACCOUNT_PREFLIGHT"
CLOUD_ACCOUNT_SCAN_EVENT_ID = "CLOUD_ACCOUNT_SCAN"

LEDGER_FAILURE_REASON_LABELS = {
    "permission_issue": "Permission issue",
    "credential_issue": "Credential issue",
    "connectivity_issue": "Connectivity issue",
    "policy_blocked": "Policy blocked",
    "scope_issue": "Scope issue",
    "operation_failed": "Operation failed",
}


def _safe_int(value: object, default: int | None = None) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return default


def _parse_event_message_payload(row: EventLog) -> dict:
    if not isinstance(getattr(row, "message", None), str) or (not str(row.message).strip()):
        return {}
    try:
        parsed = json.loads(str(row.message))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _emit_cloud_account_event(
    db: Session,
    *,
    event_id: str,
    source: str,
    status: str,
    payload: dict,
) -> None:
    try:
        db.add(
            EventLog(
                device_id=None,
                severity="info" if str(status or "").strip().lower() in {"ok", "success", "queued"} else "warning",
                event_id=str(event_id or ""),
                message=json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
                source=str(source or "CloudAccounts"),
                timestamp=datetime.utcnow(),
            )
        )
        db.commit()
    except Exception:
        db.rollback()


def _classify_cloud_failure_reason(entry: CloudAccountLedgerOperationResponse) -> tuple[str | None, str | None]:
    status = str(entry.status or "").strip().lower()
    if status in {"ok", "success", "queued", "running", "syncing"}:
        return None, None

    text = " ".join(
        [
            str(entry.event_type or ""),
            str(entry.label or ""),
            str(entry.summary or ""),
        ]
    ).strip().lower()

    if any(token in text for token in ["accessdenied", "forbidden", "unauthorized", "permission", "not authorized"]):
        code = "permission_issue"
    elif any(
        token in text
        for token in [
            "credential",
            "secret",
            "token",
            "signaturedoesnotmatch",
            "invalidclienttokenid",
            "auth",
        ]
    ):
        code = "credential_issue"
    elif any(
        token in text
        for token in [
            "timeout",
            "timed out",
            "connection",
            "connreset",
            "unreachable",
            "refused",
            "temporary failure",
            "dns",
            "network",
        ]
    ):
        code = "connectivity_issue"
    elif any(token in text for token in ["blocker", "pre-check", "precheck", "approval required", "rollback-on-failure"]):
        code = "policy_blocked"
    elif any(token in text for token in ["no targets", "empty scope", "account_ids", "resource", "region", "scope"]):
        code = "scope_issue"
    else:
        code = "operation_failed"

    return code, LEDGER_FAILURE_REASON_LABELS.get(code)


def _append_ledger_entry(summary: dict, entry: CloudAccountLedgerOperationResponse) -> None:
    reason_code, reason_label = _classify_cloud_failure_reason(entry)
    if reason_code:
        entry.failure_reason_code = reason_code
        entry.failure_reason_label = reason_label

    ops = list(summary.get("recent_operations") or [])
    ops.append(entry)
    ops.sort(key=lambda item: item.timestamp or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    summary["recent_operations"] = ops[:5]

    if entry.timestamp and (
        summary.get("last_operation_at") is None or entry.timestamp > summary["last_operation_at"]
    ):
        summary["last_operation_at"] = entry.timestamp
        summary["last_operation_type"] = str(entry.event_type or "")
        summary["last_operation_status"] = str(entry.status or "")

    if str(entry.status or "").strip().lower() in {"ok", "success"}:
        if entry.timestamp and (
            summary.get("last_success_at") is None or entry.timestamp > summary["last_success_at"]
        ):
            summary["last_success_at"] = entry.timestamp
    else:
        if entry.timestamp and (
            summary.get("last_failure_at") is None or entry.timestamp > summary["last_failure_at"]
        ):
            summary["last_failure_at"] = entry.timestamp
            summary["last_failure_message"] = str(entry.summary or "").strip() or None
            summary["last_failure_reason_code"] = reason_code
            summary["last_failure_reason_label"] = reason_label

    summary["blocker_events"] = int(summary.get("blocker_events") or 0) + int(entry.blocker_count or 0)


def _finalize_ledger_summary(summary: dict) -> dict:
    pending_approvals = int(summary.get("pending_approvals") or 0)
    sync_status = str(summary.get("sync_status") or "").strip().lower()
    last_failure_at = summary.get("last_failure_at")
    last_success_at = summary.get("last_success_at")
    blocker_events = int(summary.get("blocker_events") or 0)

    posture = "unknown"
    if pending_approvals > 0:
        posture = "approval_pending"
    elif sync_status in {"running", "queued", "syncing"}:
        posture = "syncing"
    elif sync_status in {"failed", "error"} or blocker_events > 0:
        posture = "attention"
    elif sync_status in {"success", "ok"}:
        posture = "stable"

    retry_recommended = False
    if posture in {"attention", "approval_pending"}:
        retry_recommended = posture == "attention"
    if last_failure_at and (last_success_at is None or last_failure_at >= last_success_at):
        retry_recommended = True
    if sync_status in {"failed", "error"} or blocker_events > 0:
        retry_recommended = True

    out = dict(summary)
    out["operations_posture"] = posture
    out["retry_recommended"] = bool(retry_recommended)
    out.pop("sync_status", None)
    return out

def _percentile(values: List[float], pct: float) -> Optional[float]:
    data = sorted([float(v) for v in values if v is not None])
    if not data:
        return None
    if len(data) == 1:
        return round(float(data[0]), 3)
    p = max(0.0, min(100.0, float(pct)))
    idx = (len(data) - 1) * (p / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(data) - 1)
    frac = idx - lo
    value = data[lo] * (1.0 - frac) + data[hi] * frac
    return round(float(value), 3)


def _filter_by_tenant(query, current_user: User):
    if getattr(current_user, "tenant_id", None):
        return query.filter(CloudAccount.tenant_id == current_user.tenant_id)
    if current_user.role == "admin":
        return query
    raise HTTPException(status_code=403, detail="tenant required")


def _preflight_failed(provider: str, message: str) -> CloudPreflightResponse:
    return CloudPreflightResponse(
        provider=str(provider or ""),
        status="failed",
        checks=[{"key": "preflight", "ok": False, "message": str(message)}],
        summary="Cloud preflight failed",
    )


@router.get("/accounts", response_model=List[CloudAccountResponse])
def list_cloud_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q = _filter_by_tenant(db.query(CloudAccount), current_user)
    rows = q.order_by(CloudAccount.id.asc()).all()
    global_execution_readiness = CloudIntentExecutionService.execution_readiness()
    enriched: List[dict] = []
    for acc in rows:
        runtime_credentials = decrypt_credentials_for_runtime(acc.provider, acc.credentials or {})
        readiness = CloudAccountReadinessService.build(
            acc.provider,
            runtime_credentials,
            global_execution_readiness=global_execution_readiness,
        )
        enriched.append(
            {
                "id": int(acc.id),
                "name": str(acc.name or ""),
                "provider": str(acc.provider or ""),
                "is_active": bool(acc.is_active),
                "last_synced_at": acc.last_synced_at,
                "sync_status": acc.sync_status,
                "sync_message": acc.sync_message,
                "execution_readiness": readiness,
                "created_at": acc.created_at,
                "updated_at": acc.updated_at,
            }
        )
    return enriched


@router.get("/accounts/operations-ledger", response_model=List[CloudAccountLedgerResponse])
def list_cloud_account_operations_ledger(
    limit: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    row_limit = max(1, min(int(limit or 5), 12))
    accounts = _filter_by_tenant(db.query(CloudAccount), current_user).order_by(CloudAccount.id.asc()).all()
    if not accounts:
        return []

    account_map = {int(acc.id): acc for acc in accounts}
    summaries: dict[int, dict] = {}
    for acc in accounts:
        summaries[int(acc.id)] = {
            "account_id": int(acc.id),
            "account_name": str(acc.name or ""),
            "provider": str(acc.provider or ""),
            "sync_status": str(acc.sync_status or ""),
            "pending_approvals": 0,
            "latest_approval_id": None,
            "last_operation_type": None,
            "last_operation_status": None,
            "last_operation_at": None,
            "last_success_at": None,
            "last_failure_at": None,
            "last_failure_message": None,
            "last_failure_reason_code": None,
            "last_failure_reason_label": None,
            "blocker_events": 0,
            "retry_recommended": False,
            "recent_operations": [],
        }

    approval_rows = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.status == "pending")
        .filter(ApprovalRequest.request_type.in_(["cloud_bootstrap", "intent_apply"]))
        .order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc())
        .limit(500)
        .all()
    )
    for req in approval_rows:
        payload = req.payload if isinstance(req.payload, dict) else {}
        raw_account_ids = payload.get("account_ids") if isinstance(payload.get("account_ids"), list) else []
        for account_id in [_safe_int(v) for v in raw_account_ids]:
            if account_id is None or account_id not in summaries:
                continue
            summaries[account_id]["pending_approvals"] = int(summaries[account_id]["pending_approvals"] or 0) + 1
            if summaries[account_id].get("latest_approval_id") is None:
                summaries[account_id]["latest_approval_id"] = int(req.id)

    event_rows = (
        db.query(EventLog)
        .filter(
            EventLog.event_id.in_(
                [
                    CLOUD_ACCOUNT_PREFLIGHT_EVENT_ID,
                    CLOUD_ACCOUNT_SCAN_EVENT_ID,
                    CloudPipelineService.KPI_EVENT_ID,
                    CloudBootstrapService.KPI_EVENT_ID,
                ]
            )
        )
        .order_by(EventLog.timestamp.desc(), EventLog.id.desc())
        .limit(2000)
        .all()
    )

    for row in event_rows:
        payload = _parse_event_message_payload(row)
        timestamp = row.timestamp
        if timestamp is not None and timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        if row.event_id in {CLOUD_ACCOUNT_PREFLIGHT_EVENT_ID, CLOUD_ACCOUNT_SCAN_EVENT_ID}:
            account_id = _safe_int(payload.get("account_id"))
            if account_id is None or account_id not in summaries:
                continue
            summary = summaries[account_id]
            blocker_count = int(payload.get("blocker_count") or 0)
            warning_count = int(payload.get("warning_count") or 0)
            label = "Validate" if row.event_id == CLOUD_ACCOUNT_PREFLIGHT_EVENT_ID else "Scan"
            _append_ledger_entry(
                summary,
                CloudAccountLedgerOperationResponse(
                    event_type="preflight" if row.event_id == CLOUD_ACCOUNT_PREFLIGHT_EVENT_ID else "scan",
                    label=label,
                    status=str(payload.get("status") or "unknown"),
                    timestamp=timestamp,
                    summary=str(payload.get("summary") or payload.get("message") or "").strip() or None,
                    blocker_count=blocker_count,
                    warning_count=warning_count,
                    retryable=bool(payload.get("retryable")),
                    approval_id=_safe_int(payload.get("approval_id")),
                ),
            )
            continue

        if row.event_id == CloudPipelineService.KPI_EVENT_ID:
            account_results = payload.get("accounts")
            if not isinstance(account_results, list):
                continue
            for item in account_results:
                if not isinstance(item, dict):
                    continue
                account_id = _safe_int(item.get("account_id"))
                if account_id is None or account_id not in summaries:
                    continue
                preflight_status = str(item.get("preflight_status") or "").strip().lower()
                scan_status = str(item.get("scan_status") or "").strip().lower()
                status = "ok"
                blocker_count = 0
                if preflight_status not in {"ok", "skipped"}:
                    status = "failed"
                    blocker_count += 1
                if scan_status not in {"ok", "skipped"}:
                    status = "failed"
                    blocker_count += 1
                message = (
                    str(item.get("message") or "").strip()
                    or str(item.get("preflight_message") or "").strip()
                    or f"scan_count={int(item.get('scan_count') or 0)}"
                )
                _append_ledger_entry(
                    summaries[account_id],
                    CloudAccountLedgerOperationResponse(
                        event_type="pipeline",
                        label="Pipeline",
                        status=status,
                        timestamp=timestamp,
                        summary=message or None,
                        blocker_count=blocker_count,
                        warning_count=0,
                        retryable=(status != "ok"),
                    ),
                )
            continue

        if row.event_id == CloudBootstrapService.KPI_EVENT_ID:
            account_ids = payload.get("account_ids") if isinstance(payload.get("account_ids"), list) else []
            for account_id in [_safe_int(v) for v in account_ids]:
                if account_id is None or account_id not in summaries:
                    continue
                status = str(payload.get("status") or "unknown")
                blocker_count = int(payload.get("failed_targets") or 0)
                summary_text = (
                    f"targets={int(payload.get('total_targets') or 0)} "
                    f"success={int(payload.get('success_targets') or 0)} "
                    f"failed={int(payload.get('failed_targets') or 0)}"
                )
                _append_ledger_entry(
                    summaries[account_id],
                    CloudAccountLedgerOperationResponse(
                        event_type="bootstrap",
                        label="Bootstrap",
                        status=status,
                        timestamp=timestamp,
                        summary=summary_text,
                        blocker_count=blocker_count,
                        warning_count=0,
                        retryable=(str(status).strip().lower() not in {"ok", "success"}),
                        approval_id=_safe_int(payload.get("approval_id")),
                    ),
                )

    finalized = []
    for account_id in sorted(summaries.keys()):
        summary = _finalize_ledger_summary(summaries[account_id])
        recent_ops = list(summary.get("recent_operations") or [])[:row_limit]
        summary["recent_operations"] = recent_ops
        finalized.append(CloudAccountLedgerResponse.model_validate(summary))
    return finalized


@router.post("/pipeline/run", response_model=CloudPipelineRunResponse)
def run_cloud_pipeline(
    req: CloudPipelineRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    try:
        return CloudPipelineService.run(
            db,
            tenant_id=getattr(current_user, "tenant_id", None),
            owner_id=int(current_user.id),
            req=req,
        )
    except LicensePolicyViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/bootstrap/run", response_model=CloudBootstrapRunResponse)
def run_cloud_bootstrap(
    req: CloudBootstrapRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    approval_id = int(req.approval_id) if req.approval_id is not None else None
    if ChangePolicyService.requires_cloud_bootstrap_live_approval(
        db,
        dry_run=bool(req.dry_run),
        approval_id=approval_id,
    ):
        raise HTTPException(
            status_code=409,
            detail="Approval required for live cloud bootstrap. Use dry_run or submit an approval request first.",
        )
    try:
        return CloudBootstrapService.run(
            db,
            tenant_id=getattr(current_user, "tenant_id", None),
            owner_id=int(current_user.id),
            req=req,
        )
    except LicensePolicyViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/providers/presets", response_model=List[CloudProviderPresetResponse])
def list_cloud_provider_presets(
    current_user: User = Depends(deps.require_operator),
):
    _ = current_user
    return CloudPresetService.list_presets()


@router.get("/providers/{provider}/preset", response_model=CloudProviderPresetResponse)
def get_cloud_provider_preset(
    provider: str,
    current_user: User = Depends(deps.require_operator),
):
    _ = current_user
    preset = CloudPresetService.get_preset(provider)
    if not preset:
        raise HTTPException(status_code=404, detail="provider preset not found")
    return preset


@router.post("/preflight", response_model=CloudPreflightResponse)
def preflight_cloud_credentials(
    req: CloudPreflightRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    provider = (req.provider or "").strip().lower()
    if provider not in {"aws", "azure", "gcp", "naver", "naver_cloud", "ncp"}:
        raise HTTPException(status_code=400, detail="unsupported provider")

    try:
        normalized_credentials = normalize_and_validate_credentials(provider, req.credentials)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    scanner = CloudScanner(
        db=db,
        account=CloudAccount(
            name="preflight",
            provider=provider,
            credentials=normalized_credentials,
            is_active=True,
            tenant_id=getattr(current_user, "tenant_id", None),
        ),
    )
    try:
        result = asyncio.run(scanner.preflight())
    except Exception as e:
        return _preflight_failed(provider=provider, message=f"{type(e).__name__}: {e}")
    return CloudPreflightResponse.model_validate(result)


@router.post("/accounts", response_model=CloudAccountResponse)
def create_cloud_account(
    req: CloudAccountCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    provider = (req.provider or "").strip().lower()
    if provider not in {"aws", "azure", "gcp", "naver", "naver_cloud", "ncp"}:
        raise HTTPException(status_code=400, detail="unsupported provider")

    try:
        normalized_credentials = normalize_and_validate_credentials(provider, req.credentials)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    encrypted_credentials = encrypt_credentials_for_storage(provider, normalized_credentials)

    acc = CloudAccount(
        name=req.name,
        provider=provider,
        credentials=encrypted_credentials,
        is_active=req.is_active,
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    SourceOfTruthService.record_event(
        db,
        asset_kind="cloud_account",
        asset_key=f"cloud-account:{int(acc.id)}",
        asset_name=str(acc.name or ""),
        action="created",
        summary=f"Cloud account '{acc.name}' was created.",
        actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
        actor_role=str(current_user.role or "").strip() or None,
        details={"account_id": int(acc.id), "provider": str(acc.provider or "")},
    )
    return acc


@router.put("/accounts/{account_id}", response_model=CloudAccountResponse)
def update_cloud_account(
    account_id: int,
    req: CloudAccountUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q = _filter_by_tenant(db.query(CloudAccount).filter(CloudAccount.id == account_id), current_user)
    acc = q.first()
    if not acc:
        raise HTTPException(status_code=404, detail="cloud account not found")

    bootstrap_path_before = None
    bootstrap_path_after = None
    bootstrap_path_changed = False

    if req.name is not None:
        acc.name = req.name
    if req.credentials is not None:
        existing_plain = decrypt_credentials_for_runtime(acc.provider, acc.credentials or {})
        bootstrap_path_before = str(existing_plain.get("bootstrap_path") or "").strip().lower() or None
        incoming = dict(req.credentials or {})
        for k, v in incoming.items():
            if isinstance(v, str) and v == "********":
                incoming[k] = existing_plain.get(k)
        merged = {**existing_plain, **incoming}
        try:
            normalized = normalize_and_validate_credentials(acc.provider, merged)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        bootstrap_path_after = str(normalized.get("bootstrap_path") or "").strip().lower() or None
        bootstrap_path_changed = bootstrap_path_before != bootstrap_path_after
        acc.credentials = encrypt_credentials_for_storage(acc.provider, normalized)
    if req.is_active is not None:
        acc.is_active = req.is_active
    db.add(acc)
    db.commit()
    db.refresh(acc)
    changed_fields = []
    if req.name is not None:
        changed_fields.append("name")
    if req.credentials is not None:
        changed_fields.append("credentials")
    if req.is_active is not None:
        changed_fields.append("is_active")
    if changed_fields:
        SourceOfTruthService.record_event(
            db,
            asset_kind="cloud_account",
            asset_key=f"cloud-account:{int(acc.id)}",
            asset_name=str(acc.name or ""),
            action="updated",
            summary=f"Cloud account '{acc.name}' was updated.",
            actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
            actor_role=str(current_user.role or "").strip() or None,
            details={"account_id": int(acc.id), "provider": str(acc.provider or ""), "changed_fields": changed_fields},
        )
    if bootstrap_path_changed:
        AuditService.log(
            db=db,
            user=current_user,
            action="UPDATE",
            resource_type="cloud_account",
            resource_name=f"/api/v1/cloud/accounts/{int(acc.id)}",
            details={
                "event": "cloud_bootstrap_path_update",
                "account_id": int(acc.id),
                "provider": str(acc.provider or ""),
                "name": str(acc.name or ""),
                "bootstrap_path_before": bootstrap_path_before or "auto",
                "bootstrap_path_after": bootstrap_path_after or "auto",
                "changed_fields": ["credentials.bootstrap_path"],
            },
            status="success",
        )
    return acc


@router.delete("/accounts/{account_id}")
def delete_cloud_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q = _filter_by_tenant(db.query(CloudAccount).filter(CloudAccount.id == account_id), current_user)
    acc = q.first()
    if not acc:
        raise HTTPException(status_code=404, detail="cloud account not found")
    account_name = str(acc.name or "")
    provider = str(acc.provider or "")
    db.delete(acc)
    db.commit()
    SourceOfTruthService.record_event(
        db,
        asset_kind="cloud_account",
        asset_key=f"cloud-account:{int(account_id)}",
        asset_name=account_name,
        action="deleted",
        summary=f"Cloud account '{account_name}' was deleted.",
        actor_name=str(current_user.full_name or current_user.username or "").strip() or None,
        actor_role=str(current_user.role or "").strip() or None,
        details={"account_id": int(account_id), "provider": provider},
    )
    return {"status": "ok"}


@router.post("/accounts/{account_id}/preflight", response_model=CloudPreflightResponse)
def preflight_cloud_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q = _filter_by_tenant(db.query(CloudAccount).filter(CloudAccount.id == account_id), current_user)
    acc = q.first()
    if not acc:
        raise HTTPException(status_code=404, detail="cloud account not found")
    scanner = CloudScanner(db, acc)
    try:
        result = asyncio.run(scanner.preflight())
    except Exception as e:
        failed = _preflight_failed(provider=acc.provider, message=f"{type(e).__name__}: {e}")
        _emit_cloud_account_event(
            db,
            event_id=CLOUD_ACCOUNT_PREFLIGHT_EVENT_ID,
            source="CloudPreflight",
            status="failed",
            payload={
                "event_type": "preflight",
                "account_id": int(acc.id),
                "provider": str(acc.provider or ""),
                "status": "failed",
                "summary": str(failed.summary or ""),
                "message": str(f"{type(e).__name__}: {e}"),
                "blocker_count": 1,
                "warning_count": 0,
                "retryable": True,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
        return failed
    normalized = CloudPreflightResponse.model_validate(result)
    status_value = str(normalized.status or "").strip().lower() or "unknown"
    blocker_count = len([item for item in list(normalized.checks or []) if not bool(item.ok)])
    _emit_cloud_account_event(
        db,
        event_id=CLOUD_ACCOUNT_PREFLIGHT_EVENT_ID,
        source="CloudPreflight",
        status=status_value,
        payload={
            "event_type": "preflight",
            "account_id": int(acc.id),
            "provider": str(acc.provider or ""),
            "status": status_value,
            "summary": str(normalized.summary or ""),
            "message": str(normalized.summary or ""),
            "blocker_count": int(blocker_count),
            "warning_count": 0,
            "retryable": status_value != "ok",
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
    return normalized


def _run_scan_sync(account_id: int):
    db = SessionLocal()
    try:
        acc = db.query(CloudAccount).filter(CloudAccount.id == account_id).first()
        if not acc:
            return
        scanner = CloudScanner(db, acc)
        try:
            results = asyncio.run(scanner.scan())
            _emit_cloud_account_event(
                db,
                event_id=CLOUD_ACCOUNT_SCAN_EVENT_ID,
                source="CloudScan",
                status="success",
                payload={
                    "event_type": "scan",
                    "account_id": int(acc.id),
                    "provider": str(acc.provider or ""),
                    "status": "success",
                    "summary": f"Scanned {len(results or [])} resources",
                    "message": str(getattr(acc, "sync_message", "") or ""),
                    "resource_count": int(len(results or [])),
                    "blocker_count": 0,
                    "warning_count": 0,
                    "retryable": False,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            _emit_cloud_account_event(
                db,
                event_id=CLOUD_ACCOUNT_SCAN_EVENT_ID,
                source="CloudScan",
                status="failed",
                payload={
                    "event_type": "scan",
                    "account_id": int(acc.id),
                    "provider": str(acc.provider or ""),
                    "status": "failed",
                    "summary": str(getattr(acc, "sync_message", "") or f"{type(e).__name__}: {e}"),
                    "message": f"{type(e).__name__}: {e}",
                    "resource_count": 0,
                    "blocker_count": 1,
                    "warning_count": 0,
                    "retryable": True,
                    "timestamp": datetime.utcnow().isoformat(),
                },
            )
    finally:
        db.close()


@router.post("/accounts/{account_id}/scan", response_model=CloudScanResponse)
def scan_cloud_account(
    account_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q = _filter_by_tenant(db.query(CloudAccount).filter(CloudAccount.id == account_id), current_user)
    acc = q.first()
    if not acc:
        raise HTTPException(status_code=404, detail="cloud account not found")
    if not acc.is_active:
        raise HTTPException(status_code=400, detail="cloud account is inactive")

    background_tasks.add_task(_run_scan_sync, acc.id)
    return {"status": "queued", "account_id": acc.id}


@router.post("/accounts/{account_id}/pipeline/run", response_model=CloudPipelineRunResponse)
def run_cloud_account_pipeline(
    account_id: int,
    req: CloudPipelineRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q = _filter_by_tenant(db.query(CloudAccount).filter(CloudAccount.id == account_id), current_user)
    acc = q.first()
    if not acc:
        raise HTTPException(status_code=404, detail="cloud account not found")

    request_payload = req.model_copy(
        update={"account_ids": [int(account_id)]},
        deep=True,
    )
    try:
        return CloudPipelineService.run(
            db,
            tenant_id=getattr(current_user, "tenant_id", None),
            owner_id=int(current_user.id),
            req=request_payload,
        )
    except LicensePolicyViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/accounts/{account_id}/bootstrap/run", response_model=CloudBootstrapRunResponse)
def run_cloud_account_bootstrap(
    account_id: int,
    req: CloudBootstrapRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q = _filter_by_tenant(db.query(CloudAccount).filter(CloudAccount.id == account_id), current_user)
    acc = q.first()
    if not acc:
        raise HTTPException(status_code=404, detail="cloud account not found")

    request_payload = req.model_copy(
        update={"account_ids": [int(account_id)]},
        deep=True,
    )
    approval_id = int(request_payload.approval_id) if request_payload.approval_id is not None else None
    if ChangePolicyService.requires_cloud_bootstrap_live_approval(
        db,
        dry_run=bool(request_payload.dry_run),
        approval_id=approval_id,
    ):
        raise HTTPException(
            status_code=409,
            detail="Approval required for live cloud bootstrap. Use dry_run or submit an approval request first.",
        )
    try:
        return CloudBootstrapService.run(
            db,
            tenant_id=getattr(current_user, "tenant_id", None),
            owner_id=int(current_user.id),
            req=request_payload,
        )
    except LicensePolicyViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.get("/kpi/summary", response_model=CloudKpiSummaryResponse)
def get_cloud_pipeline_kpi_summary(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    span_days = max(1, min(int(days or 30), 90))
    since = datetime.now(timezone.utc) - timedelta(days=span_days)

    rows = (
        db.query(EventLog)
        .filter(EventLog.event_id == CloudPipelineService.KPI_EVENT_ID)
        .filter(EventLog.timestamp >= since)
        .order_by(EventLog.timestamp.desc())
        .limit(5000)
        .all()
    )

    tenant_scope = getattr(current_user, "tenant_id", None)
    entries = []
    for row in rows:
        payload = {}
        if isinstance(row.message, str) and row.message.strip():
            try:
                parsed = json.loads(row.message)
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}

        if tenant_scope is not None:
            tenant_value = payload.get("tenant_id")
            if tenant_value is None:
                continue
            try:
                if int(tenant_value) != int(tenant_scope):
                    continue
            except Exception:
                if str(tenant_value) != str(tenant_scope):
                    continue

        ts = row.timestamp
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        entries.append((ts, payload))

    durations: List[float] = []
    reflected_links = 0
    low_confidence_queued = 0
    ok_runs = 0
    partial_runs = 0
    failed_runs = 0
    last_run_at: Optional[datetime] = None

    trend_days = min(span_days, 7)
    trend = {}
    for i in range(trend_days):
        day = (datetime.now(timezone.utc) - timedelta(days=(trend_days - 1 - i))).date().isoformat()
        trend[day] = {
            "date": day,
            "runs": 0,
            "reflected_links": 0,
            "low_confidence_queued": 0,
        }

    for ts, payload in entries:
        if last_run_at is None or ts > last_run_at:
            last_run_at = ts

        status = str(payload.get("status") or "").strip().lower()
        if status == "ok":
            ok_runs += 1
        elif status == "partial":
            partial_runs += 1
        else:
            failed_runs += 1

        try:
            d = float(payload.get("first_map_seconds"))
            if d >= 0:
                durations.append(d)
        except Exception:
            pass

        try:
            reflected = max(0, int(payload.get("reflected_links") or 0))
        except Exception:
            reflected = 0
        try:
            low_conf = max(0, int(payload.get("low_confidence_queued") or 0))
        except Exception:
            low_conf = 0

        reflected_links += reflected
        low_confidence_queued += low_conf

        day_key = ts.astimezone(timezone.utc).date().isoformat()
        if day_key in trend:
            trend[day_key]["runs"] += 1
            trend[day_key]["reflected_links"] += reflected
            trend[day_key]["low_confidence_queued"] += low_conf

    denom = reflected_links + low_confidence_queued
    auto_reflection_rate_pct = round((reflected_links / denom) * 100.0, 2) if denom > 0 else 0.0
    false_positive_rate_pct = round((low_confidence_queued / denom) * 100.0, 2) if denom > 0 else 0.0

    return CloudKpiSummaryResponse(
        days=span_days,
        runs=len(entries),
        first_map_seconds_p50=_percentile(durations, 50.0),
        first_map_seconds_p95=_percentile(durations, 95.0),
        auto_reflection_rate_pct=auto_reflection_rate_pct,
        false_positive_rate_pct=false_positive_rate_pct,
        reflected_links=int(reflected_links),
        low_confidence_queued=int(low_confidence_queued),
        ok_runs=int(ok_runs),
        partial_runs=int(partial_runs),
        failed_runs=int(failed_runs),
        last_run_at=last_run_at,
        trend=[trend[k] for k in sorted(trend.keys())],
    )


@router.get("/resources", response_model=List[CloudResourceResponse])
def list_cloud_resources(
    account_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q = db.query(CloudResource)
    if account_id is not None:
        acc_q = _filter_by_tenant(db.query(CloudAccount).filter(CloudAccount.id == account_id), current_user)
        if not acc_q.first():
            raise HTTPException(status_code=404, detail="cloud account not found")
        q = q.filter(CloudResource.account_id == account_id)
    else:
        acc_ids = [a.id for a in _filter_by_tenant(db.query(CloudAccount), current_user).all()]
        q = q.filter(CloudResource.account_id.in_(acc_ids))

    return q.order_by(CloudResource.id.asc()).all()


@router.get("/resources/normalized", response_model=List[CloudNormalizedResourceResponse])
def list_normalized_cloud_resources(
    account_id: Optional[int] = None,
    provider: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q = db.query(CloudResource, CloudAccount).join(CloudAccount, CloudAccount.id == CloudResource.account_id)
    if account_id is not None:
        acc_q = _filter_by_tenant(db.query(CloudAccount).filter(CloudAccount.id == account_id), current_user)
        if not acc_q.first():
            raise HTTPException(status_code=404, detail="cloud account not found")
        q = q.filter(CloudResource.account_id == account_id)
    else:
        acc_ids = [a.id for a in _filter_by_tenant(db.query(CloudAccount), current_user).all()]
        q = q.filter(CloudResource.account_id.in_(acc_ids))

    if provider:
        normalized_provider = CloudPresetService.normalize_provider(provider)
        aliases = {normalized_provider}
        if normalized_provider == "naver":
            aliases.update({"ncp", "naver_cloud", "naver"})
        q = q.filter(CloudAccount.provider.in_(sorted(aliases)))

    rows = q.order_by(CloudResource.id.asc()).all()
    return [CloudNormalizationService.normalize_resource(acc, res) for res, acc in rows]


@router.get("/accounts/{account_id}/credentials")
def get_cloud_account_credentials_masked(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    q = _filter_by_tenant(db.query(CloudAccount).filter(CloudAccount.id == account_id), current_user)
    acc = q.first()
    if not acc:
        raise HTTPException(status_code=404, detail="cloud account not found")
    raw_credentials = decrypt_credentials_for_runtime(acc.provider, acc.credentials or {})
    return {
        "account_id": acc.id,
        "provider": acc.provider,
        "credentials": mask_credentials(acc.provider, raw_credentials),
    }


@router.post("/hybrid/build")
def build_hybrid_cloud_links(
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    try:
        stats = HybridTopologyService.build_cloud_peer_links(
            db,
            tenant_id=getattr(current_user, "tenant_id", None),
            owner_id=int(current_user.id),
        )
    except LicensePolicyViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"status": "ok", "result": stats}


@router.post("/hybrid/infer")
def infer_hybrid_cloud_links_from_bgp(
    enrich: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(deps.require_operator),
):
    try:
        stats = HybridTopologyService.build_inferred_cloud_links(
            db,
            tenant_id=getattr(current_user, "tenant_id", None),
            owner_id=int(current_user.id),
            enrich=bool(enrich),
        )
    except LicensePolicyViolation as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return {"status": "ok", "result": stats}
