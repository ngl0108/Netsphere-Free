from __future__ import annotations

from typing import Any, Dict, List


class CloudAccountReadinessService:
    REAL_APPLY_PROVIDERS = {"aws", "azure", "gcp", "ncp"}

    @staticmethod
    def normalize_provider(provider: str | None) -> str:
        value = str(provider or "").strip().lower()
        if value in {"naver", "naver_cloud"}:
            return "ncp"
        return value

    @classmethod
    def build(
        cls,
        provider: str | None,
        runtime_credentials: Dict[str, Any] | None,
        *,
        global_execution_readiness: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        p = cls.normalize_provider(provider)
        creds = dict(runtime_credentials or {})
        warnings: List[str] = []
        missing_fields: List[str] = []
        required_fields: List[str] = []
        supports_real_apply = p in cls.REAL_APPLY_PROVIDERS
        stage = "unknown"

        if p == "aws":
            auth_type = str(creds.get("auth_type") or ("assume_role" if creds.get("role_arn") else "access_key")).strip().lower()
            region = str(creds.get("region") or "").strip()
            if auth_type == "assume_role":
                required_fields = ["region", "role_arn"]
                if not region:
                    missing_fields.append("region")
                if not str(creds.get("role_arn") or "").strip():
                    missing_fields.append("role_arn")
                has_source_ak = bool(str(creds.get("source_access_key") or "").strip())
                has_source_sk = bool(str(creds.get("source_secret_key") or "").strip())
                if has_source_ak != has_source_sk:
                    missing_fields.extend(
                        [field for field in ("source_access_key", "source_secret_key") if field not in missing_fields]
                    )
                if not has_source_ak and not has_source_sk:
                    warnings.append("assume_role requires ambient AWS auth or source access keys on the runner.")
            else:
                required_fields = ["region", "access_key", "secret_key"]
                if not region:
                    missing_fields.append("region")
                if not str(creds.get("access_key") or "").strip():
                    missing_fields.append("access_key")
                if not str(creds.get("secret_key") or "").strip():
                    missing_fields.append("secret_key")
        elif p == "azure":
            required_fields = ["tenant_id", "subscription_id", "client_id", "client_secret"]
            missing_fields = [field for field in required_fields if not str(creds.get(field) or "").strip()]
        elif p == "gcp":
            required_fields = ["project_id", "service_account_json"]
            missing_fields = [field for field in required_fields if not creds.get(field)]
        elif p == "ncp":
            required_fields = ["access_key", "secret_key"]
            missing_fields = [field for field in required_fields if not str(creds.get(field) or "").strip()]
        else:
            warnings.append("Unsupported provider for Cloud Intent execution readiness.")

        if missing_fields:
            stage = "credentials_missing"
        elif supports_real_apply:
            stage = "real_apply_ready"
        else:
            stage = "unknown"

        global_ready = bool((global_execution_readiness or {}).get("ready_for_real_apply"))
        ready_for_intent_preview = len(missing_fields) == 0
        ready_for_real_apply = supports_real_apply and len(missing_fields) == 0
        change_enabled = ready_for_real_apply and global_ready
        change_mode = "change_enabled" if change_enabled else "read_only"
        read_only_recommended = not change_enabled

        if missing_fields:
            change_mode_reason = "Required provider credentials are incomplete, so this account stays read-only."
        elif not supports_real_apply:
            change_mode_reason = "This provider is available for discovery and preview, but live apply is not enabled yet."
        elif not global_ready:
            change_mode_reason = "Global execution guardrails keep this account in read-only mode until runtime, backend, and live apply policy are ready."
            warnings.append("Global execution policy currently keeps this account in read-only mode.")
        else:
            change_mode_reason = "Credentials, runtime, backend, and live apply policy are ready for approval-gated changes."

        return {
            "provider": p,
            "auth_type": str(creds.get("auth_type") or "").strip().lower() or None,
            "required_fields": required_fields,
            "missing_fields": missing_fields,
            "warnings": warnings,
            "supports_real_apply": supports_real_apply,
            "ready_for_intent_preview": ready_for_intent_preview,
            "ready_for_real_apply": ready_for_real_apply,
            "stage": stage,
            "change_mode": change_mode,
            "change_enabled": change_enabled,
            "read_only_recommended": read_only_recommended,
            "change_mode_reason": change_mode_reason,
        }
