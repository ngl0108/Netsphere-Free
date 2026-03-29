from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CloudAccountCreate(BaseModel):
    name: str
    provider: str = Field(..., description="aws|azure|gcp|naver")
    credentials: Dict[str, Any]
    is_active: bool = True


class CloudAccountUpdate(BaseModel):
    name: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class CloudAccountResponse(BaseModel):
    id: int
    name: str
    provider: str
    is_active: bool
    last_synced_at: Optional[datetime]
    sync_status: Optional[str]
    sync_message: Optional[str]
    execution_readiness: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class CloudAccountLedgerOperationResponse(BaseModel):
    event_type: str
    label: str
    status: str
    timestamp: Optional[datetime] = None
    summary: Optional[str] = None
    failure_reason_code: Optional[str] = None
    failure_reason_label: Optional[str] = None
    blocker_count: int = 0
    warning_count: int = 0
    retryable: bool = False
    approval_id: Optional[int] = None


class CloudAccountLedgerResponse(BaseModel):
    account_id: int
    account_name: str
    provider: str
    operations_posture: str = "unknown"
    pending_approvals: int = 0
    latest_approval_id: Optional[int] = None
    last_operation_type: Optional[str] = None
    last_operation_status: Optional[str] = None
    last_operation_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    last_failure_message: Optional[str] = None
    last_failure_reason_code: Optional[str] = None
    last_failure_reason_label: Optional[str] = None
    blocker_events: int = 0
    retry_recommended: bool = False
    recent_operations: List[CloudAccountLedgerOperationResponse] = Field(default_factory=list)


class CloudResourceResponse(BaseModel):
    id: int
    account_id: int
    resource_id: str
    resource_type: str
    name: Optional[str]
    region: Optional[str]
    cidr_block: Optional[str]
    state: Optional[str]
    resource_metadata: Optional[Dict[str, Any]]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class CloudScanResponse(BaseModel):
    status: str
    account_id: int


class CloudCredentialField(BaseModel):
    key: str
    label: str
    required: bool = False
    secret: bool = False
    description: Optional[str] = None


class CloudProviderPresetResponse(BaseModel):
    provider: str
    display_name: str
    read_only_policy: Optional[str] = None
    trust_policy: Optional[str] = None
    credential_fields: List[CloudCredentialField] = Field(default_factory=list)
    preflight_checks: List[str] = Field(default_factory=list)


class CloudPreflightRequest(BaseModel):
    provider: str = Field(..., description="aws|azure|gcp|naver")
    credentials: Dict[str, Any] = Field(default_factory=dict)


class CloudPreflightCheckResponse(BaseModel):
    key: str
    ok: bool
    message: str


class CloudPreflightResponse(BaseModel):
    provider: str
    status: str
    checks: List[CloudPreflightCheckResponse] = Field(default_factory=list)
    summary: Optional[str] = None


class CloudNormalizedResourceResponse(BaseModel):
    account_id: int
    account_name: Optional[str] = None
    provider: str
    provider_group: str
    resource_uid: str
    resource_id: str
    resource_type: str
    name: Optional[str] = None
    region: Optional[str] = None
    cidr_block: Optional[str] = None
    state: Optional[str] = None
    peer_ips: List[str] = Field(default_factory=list)
    peer_confidence: str = "none"
    labels: Dict[str, str] = Field(default_factory=dict)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class CloudPipelineRunRequest(BaseModel):
    account_ids: Optional[List[int]] = None
    preflight: bool = True
    include_hybrid_build: bool = True
    include_hybrid_infer: bool = True
    enrich_inferred: bool = True
    continue_on_error: bool = True
    idempotency_key: Optional[str] = None
    force: bool = False


class CloudPipelineAccountResult(BaseModel):
    account_id: int
    provider: str
    preflight_status: str = "skipped"
    preflight_message: Optional[str] = None
    scan_status: str = "skipped"
    scan_count: int = 0
    message: Optional[str] = None


class CloudPipelineRunResponse(BaseModel):
    status: str
    idempotency_key: Optional[str] = None
    total_accounts: int = 0
    scanned_resources: int = 0
    failed_accounts: int = 0
    accounts: List[CloudPipelineAccountResult] = Field(default_factory=list)
    normalized_by_provider: Dict[str, int] = Field(default_factory=dict)
    hybrid_build: Optional[Dict[str, int]] = None
    hybrid_infer: Optional[Dict[str, int]] = None
    message: Optional[str] = None


class CloudBootstrapRunRequest(BaseModel):
    account_ids: Optional[List[int]] = None
    regions: Optional[List[str]] = None
    resource_ids: Optional[List[str]] = None
    dry_run: bool = True
    pre_check_enabled: bool = True
    post_check_enabled: bool = True
    rollback_on_failure: bool = True
    canary_count: int = 0
    wave_size: int = 0
    stop_on_wave_failure: bool = True
    inter_wave_delay_seconds: float = 0.0
    idempotency_key: Optional[str] = None
    force: bool = False
    approval_id: Optional[int] = None
    execution_id: Optional[str] = None
    script_template: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class CloudBootstrapTargetResult(BaseModel):
    account_id: int
    provider: str
    resource_id: str
    resource_name: Optional[str] = None
    region: Optional[str] = None
    status: str
    wave: Optional[int] = None
    pre_check: Dict[str, Any] = Field(default_factory=dict)
    post_check: Dict[str, Any] = Field(default_factory=dict)
    rollback: Dict[str, Any] = Field(default_factory=dict)
    script_sha256: Optional[str] = None
    script_preview: Optional[str] = None
    error: Optional[str] = None
    approval_id: Optional[int] = None
    execution_id: Optional[str] = None


class CloudBootstrapRunResponse(BaseModel):
    status: str
    idempotency_key: Optional[str] = None
    approval_id: Optional[int] = None
    execution_id: Optional[str] = None
    total_targets: int = 0
    success_targets: int = 0
    failed_targets: int = 0
    dry_run_targets: int = 0
    skipped_targets: int = 0
    execution: Dict[str, Any] = Field(default_factory=dict)
    results: List[CloudBootstrapTargetResult] = Field(default_factory=list)
    message: Optional[str] = None


class CloudKpiTrendPoint(BaseModel):
    date: str
    runs: int = 0
    reflected_links: int = 0
    low_confidence_queued: int = 0


class CloudKpiSummaryResponse(BaseModel):
    days: int = 30
    runs: int = 0
    first_map_seconds_p50: Optional[float] = None
    first_map_seconds_p95: Optional[float] = None
    auto_reflection_rate_pct: float = 0.0
    false_positive_rate_pct: float = 0.0
    reflected_links: int = 0
    low_confidence_queued: int = 0
    ok_runs: int = 0
    partial_runs: int = 0
    failed_runs: int = 0
    last_run_at: Optional[datetime] = None
    trend: List[CloudKpiTrendPoint] = Field(default_factory=list)


def normalize_and_validate_credentials(provider: str, creds: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(creds, dict):
        raise ValueError("credentials must be an object")

    p = (provider or "").strip().lower()
    out = dict(creds)

    if p == "aws":
        out["region"] = str(out.get("region") or "ap-northeast-2").strip()
        auth_type = str(out.get("auth_type") or ("assume_role" if out.get("role_arn") else "access_key")).strip().lower()
        if auth_type not in {"access_key", "assume_role"}:
            raise ValueError("aws auth_type must be access_key or assume_role")
        out["auth_type"] = auth_type

        if auth_type == "access_key":
            if not str(out.get("access_key") or "").strip() or not str(out.get("secret_key") or "").strip():
                raise ValueError("AWS Access Key/Secret Key is required for access_key auth")
        else:
            if not str(out.get("role_arn") or "").strip():
                raise ValueError("AWS role_arn is required for assume_role auth")
            has_source_ak = bool(str(out.get("source_access_key") or "").strip())
            has_source_sk = bool(str(out.get("source_secret_key") or "").strip())
            if has_source_ak != has_source_sk:
                raise ValueError("source_access_key and source_secret_key must be provided together")

    return out


def mask_credentials(provider: str, creds: Dict[str, Any]) -> Dict[str, Any]:
    p = (provider or "").strip().lower()
    sensitive_keys = {
        "secret_key",
        "client_secret",
        "service_account_json",
        "shared_secret",
        "access_key",
        "private_key",
        "source_access_key",
        "source_secret_key",
        "session_token",
        "source_session_token",
        "external_id",
    }
    if p == "aws":
        sensitive_keys |= {"secret_key"}
    if p == "azure":
        sensitive_keys |= {"client_secret"}
    if p == "gcp":
        sensitive_keys |= {"service_account_json"}
    if p in {"naver", "naver_cloud", "ncp"}:
        sensitive_keys |= {"secret_key"}

    out: Dict[str, Any] = {}
    for k, v in (creds or {}).items():
        is_encrypted_token = isinstance(v, str) and v.startswith("enc:")
        if k in sensitive_keys and (v not in (None, "") or is_encrypted_token):
            out[k] = "********"
        else:
            out[k] = v
    return out
