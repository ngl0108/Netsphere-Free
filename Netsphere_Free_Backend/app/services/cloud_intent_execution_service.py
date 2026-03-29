from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from app.models.cloud import CloudAccount
from app.services.cloud_credentials_service import decrypt_credentials_for_runtime


class CloudIntentExecutionService:
    EXECUTION_MODES = {"disabled", "prepare_only", "mock_apply", "real_apply"}
    STATE_BACKENDS = {"local", "s3", "azurerm", "gcs"}
    SUPPORTED_RENDER_PROVIDERS = {"aws", "azure", "gcp", "ncp"}

    @staticmethod
    def _truthy(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}

    @staticmethod
    def live_apply_enabled() -> bool:
        return CloudIntentExecutionService._truthy(
            os.getenv("NETSPHERE_CLOUD_INTENT_LIVE_APPLY_ENABLED", "false")
        )

    @staticmethod
    def auto_rollback_enabled() -> bool:
        return CloudIntentExecutionService._truthy(
            os.getenv("NETSPHERE_CLOUD_INTENT_AUTO_ROLLBACK_ENABLED", "false")
        )

    @staticmethod
    def execution_mode() -> str:
        mode = str(os.getenv("NETSPHERE_TERRAFORM_EXECUTION_MODE", "prepare_only") or "").strip().lower()
        if mode not in CloudIntentExecutionService.EXECUTION_MODES:
            return "prepare_only"
        return mode

    @staticmethod
    def terraform_binary() -> str:
        return str(os.getenv("NETSPHERE_TERRAFORM_BIN", "terraform") or "").strip() or "terraform"

    @staticmethod
    def work_root() -> Path:
        raw = str(
            os.getenv(
                "NETSPHERE_TERRAFORM_WORK_ROOT",
                "Netsphere_Free_Backend/reports_cache/cloud_intent_runs",
            )
            or ""
        ).strip()
        path = Path(raw)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def state_root() -> Path:
        raw = str(
            os.getenv(
                "NETSPHERE_TERRAFORM_STATE_ROOT",
                "Netsphere_Free_Backend/reports_cache/cloud_intent_state",
            )
            or ""
        ).strip()
        path = Path(raw)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def keep_runtime_files() -> bool:
        return CloudIntentExecutionService._truthy(
            os.getenv("NETSPHERE_TERRAFORM_KEEP_RUNTIME_FILES", "false")
        )

    @staticmethod
    def parallelism() -> int:
        try:
            return max(1, int(float(os.getenv("NETSPHERE_TERRAFORM_PARALLELISM", "4"))))
        except Exception:
            return 4

    @staticmethod
    def lock_timeout() -> str:
        value = str(os.getenv("NETSPHERE_TERRAFORM_LOCK_TIMEOUT", "60s") or "").strip()
        return value or "60s"

    @staticmethod
    def apply_timeout_seconds() -> int:
        try:
            return max(60, int(float(os.getenv("NETSPHERE_TERRAFORM_APPLY_TIMEOUT_SECONDS", "1800"))))
        except Exception:
            return 1800

    @staticmethod
    def state_backend() -> str:
        backend = str(os.getenv("NETSPHERE_TERRAFORM_STATE_BACKEND", "local") or "").strip().lower()
        if backend not in CloudIntentExecutionService.STATE_BACKENDS:
            return "local"
        return backend

    @staticmethod
    def state_prefix() -> str:
        return str(os.getenv("NETSPHERE_TERRAFORM_STATE_PREFIX", "netsphere/cloud-intents") or "").strip().strip("/\\")

    @staticmethod
    def _fs_safe(value: Any) -> str:
        text = str(value or "").strip() or "execution"
        out = []
        for ch in text:
            if ch.isalnum() or ch in {"-", "_", "."}:
                out.append(ch)
            else:
                out.append("_")
        return "".join(out).strip("._") or "execution"

    @staticmethod
    def _normalize_provider(value: Any) -> str:
        provider = str(value or "").strip().lower()
        if provider in {"naver", "naver_cloud"}:
            return "ncp"
        return provider

    @staticmethod
    def _terraform_command_prefix() -> List[str]:
        raw = CloudIntentExecutionService.terraform_binary()
        if any(ch.isspace() for ch in raw) or raw.startswith('"'):
            parts = [str(p).strip().strip('"') for p in shlex.split(raw, posix=False) if str(p).strip()]
            return parts or ["terraform"]
        return [raw]

    @staticmethod
    def _bundle_dir(execution_id: str) -> Path:
        path = CloudIntentExecutionService.work_root() / CloudIntentExecutionService._fs_safe(execution_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    @staticmethod
    def _write_text(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(text), encoding="utf-8")

    @staticmethod
    def _credential_contract(provider: str, runtime_credentials: Dict[str, Any]) -> Dict[str, Any]:
        provider_key = CloudIntentExecutionService._normalize_provider(provider)
        required_env_keys: List[str] = []
        notes: List[str] = []

        if provider_key == "aws":
            auth_type = str(
                runtime_credentials.get("auth_type")
                or ("assume_role" if runtime_credentials.get("role_arn") else "access_key")
            ).strip().lower()
            if auth_type == "assume_role":
                if runtime_credentials.get("source_access_key") and runtime_credentials.get("source_secret_key"):
                    required_env_keys.extend(["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
                notes.append("AWS assume-role execution expects role_arn and optional external_id/session inputs.")
            else:
                required_env_keys.extend(["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"])
            if runtime_credentials.get("session_token"):
                required_env_keys.append("AWS_SESSION_TOKEN")
            required_env_keys.append("AWS_DEFAULT_REGION")
        elif provider_key == "azure":
            required_env_keys.extend(
                [
                    "ARM_TENANT_ID",
                    "ARM_SUBSCRIPTION_ID",
                    "ARM_CLIENT_ID",
                    "ARM_CLIENT_SECRET",
                ]
            )
        elif provider_key == "gcp":
            required_env_keys.extend(["GOOGLE_CLOUD_PROJECT", "GOOGLE_APPLICATION_CREDENTIALS"])
        elif provider_key == "ncp":
            required_env_keys.extend(["NCLOUD_ACCESS_KEY", "NCLOUD_SECRET_KEY"])

        return {
            "provider": provider_key,
            "required_env_keys": required_env_keys,
            "notes": notes,
        }

    @staticmethod
    def _masked_account_payload(account: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "account_id": int(account.get("account_id") or 0),
            "name": str(account.get("name") or ""),
            "provider": str(account.get("provider") or ""),
            "credentials": dict(account.get("masked_credentials") or {}),
            "credential_contract": dict(account.get("credential_contract") or {}),
            "default_region": account.get("default_region"),
        }

    @staticmethod
    def _target_accounts_for_intent(
        db: Session,
        normalized_intent: Dict[str, Any],
        simulation: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        spec = normalized_intent.get("spec") if isinstance(normalized_intent.get("spec"), dict) else {}
        targets = spec.get("targets") if isinstance(spec.get("targets"), dict) else {}
        cloud_scope = simulation.get("cloud_scope") if isinstance(simulation.get("cloud_scope"), dict) else {}

        target_providers = {
            CloudIntentExecutionService._normalize_provider(v)
            for v in list(targets.get("providers") or cloud_scope.get("target_providers") or [])
            if str(v or "").strip()
        }
        target_account_ids = {
            int(v)
            for v in list(targets.get("account_ids") or cloud_scope.get("target_accounts") or [])
            if str(v or "").strip()
        }

        accounts = list(db.query(CloudAccount).filter(CloudAccount.is_active == True).all())  # noqa: E712
        out: List[Dict[str, Any]] = []

        for account in accounts:
            provider = CloudIntentExecutionService._normalize_provider(account.provider)
            if target_providers and provider not in target_providers:
                continue
            if target_account_ids and int(account.id) not in target_account_ids:
                continue

            runtime_credentials = decrypt_credentials_for_runtime(provider, account.credentials or {})
            masked_credentials = dict(runtime_credentials)
            for key in {
                "secret_key",
                "client_secret",
                "service_account_json",
                "access_key",
                "source_access_key",
                "source_secret_key",
                "session_token",
                "source_session_token",
            }:
                if key in masked_credentials and masked_credentials.get(key) not in (None, ""):
                    masked_credentials[key] = "********"

            default_region = None
            if provider == "aws":
                default_region = str(runtime_credentials.get("region") or "ap-northeast-2").strip() or "ap-northeast-2"
            elif provider == "ncp":
                default_region = str(runtime_credentials.get("region_code") or runtime_credentials.get("region") or "KR").strip() or "KR"
            else:
                default_region = str(runtime_credentials.get("region") or "").strip() or None

            out.append(
                {
                    "account_id": int(account.id),
                    "name": str(account.name or ""),
                    "provider": provider,
                    "runtime_credentials": runtime_credentials,
                    "masked_credentials": masked_credentials,
                    "credential_contract": CloudIntentExecutionService._credential_contract(provider, runtime_credentials),
                    "default_region": default_region,
                }
            )

        out.sort(key=lambda row: (str(row.get("provider") or ""), int(row.get("account_id") or 0)))
        return out

    @staticmethod
    def _build_backend_config(execution_id: str) -> Tuple[str, Dict[str, Any]]:
        backend = CloudIntentExecutionService.state_backend()
        state_key = CloudIntentExecutionService._fs_safe(execution_id) + ".tfstate"
        prefix = CloudIntentExecutionService.state_prefix()
        key_with_prefix = f"{prefix}/{state_key}" if prefix else state_key

        if backend == "local":
            return backend, {"path": str(CloudIntentExecutionService.state_root() / state_key)}
        if backend == "s3":
            config = {
                "bucket": str(os.getenv("NETSPHERE_TERRAFORM_STATE_S3_BUCKET", "")).strip(),
                "key": key_with_prefix,
                "region": str(os.getenv("NETSPHERE_TERRAFORM_STATE_S3_REGION", "")).strip(),
            }
            table = str(os.getenv("NETSPHERE_TERRAFORM_STATE_S3_DYNAMODB_TABLE", "")).strip()
            if table:
                config["dynamodb_table"] = table
            return backend, config
        if backend == "azurerm":
            return backend, {
                "resource_group_name": str(os.getenv("NETSPHERE_TERRAFORM_STATE_AZURERM_RESOURCE_GROUP", "")).strip(),
                "storage_account_name": str(os.getenv("NETSPHERE_TERRAFORM_STATE_AZURERM_STORAGE_ACCOUNT", "")).strip(),
                "container_name": str(os.getenv("NETSPHERE_TERRAFORM_STATE_AZURERM_CONTAINER", "")).strip(),
                "key": key_with_prefix,
            }
        return backend, {
            "bucket": str(os.getenv("NETSPHERE_TERRAFORM_STATE_GCS_BUCKET", "")).strip(),
            "prefix": key_with_prefix.rsplit("/", 1)[0] if "/" in key_with_prefix else key_with_prefix,
        }

    @staticmethod
    def _backend_validation(backend: str, config: Dict[str, Any]) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []

        required_by_backend = {
            "local": ["path"],
            "s3": ["bucket", "key", "region"],
            "azurerm": ["resource_group_name", "storage_account_name", "container_name", "key"],
            "gcs": ["bucket", "prefix"],
        }
        for key in required_by_backend.get(backend, []):
            if not str(config.get(key) or "").strip():
                errors.append(f"{backend} backend requires {key}")
        if backend not in required_by_backend:
            errors.append(f"unsupported state backend: {backend}")
        if backend != "local":
            warnings.append("Remote backend selected; verify backend credentials and locking before enabling real_apply.")

        return {"backend": backend, "valid": len(errors) == 0, "errors": errors, "warnings": warnings}

    @staticmethod
    def terraform_runtime_status() -> Dict[str, Any]:
        configured = CloudIntentExecutionService.terraform_binary()
        command = CloudIntentExecutionService._terraform_command_prefix()
        executable = str(command[0]).strip() if command else configured
        resolved = None
        available = False

        if executable:
            as_path = Path(executable)
            if as_path.exists():
                resolved = str(as_path.resolve())
                available = True
            else:
                found = shutil.which(executable)
                if found:
                    resolved = str(found)
                    available = True

        return {
            "configured": configured,
            "command": command,
            "primary": executable,
            "available": available,
            "resolved": resolved,
        }

    @staticmethod
    def execution_readiness() -> Dict[str, Any]:
        backend = CloudIntentExecutionService.state_backend()
        _, backend_config = CloudIntentExecutionService._build_backend_config("status-probe")
        backend_validation = CloudIntentExecutionService._backend_validation(backend, backend_config)
        runtime = CloudIntentExecutionService.terraform_runtime_status()
        mode = CloudIntentExecutionService.execution_mode()
        live_apply = CloudIntentExecutionService.live_apply_enabled()

        errors: List[str] = list(backend_validation.get("errors") or [])
        warnings: List[str] = list(backend_validation.get("warnings") or [])

        if not bool(runtime.get("available")):
            errors.append(f"terraform binary not found: {runtime.get('configured')}")

        if mode in {"prepare_only", "mock_apply"}:
            warnings.append("Current execution mode is safe-mode. Provider writes remain blocked until real_apply.")
        elif mode == "disabled":
            warnings.append("Terraform execution mode is disabled.")

        if not live_apply:
            warnings.append("Live apply policy is disabled. Approval can still generate preview and evidence bundles.")

        ready_for_real_apply = bool(live_apply) and bool(runtime.get("available")) and bool(backend_validation.get("valid"))

        return {
            "mode": mode,
            "live_apply_enabled": live_apply,
            "state_backend": backend,
            "state_prefix": CloudIntentExecutionService.state_prefix(),
            "backend_validation": backend_validation,
            "terraform_runtime": runtime,
            "ready_for_real_apply": ready_for_real_apply,
            "errors": errors,
            "warnings": warnings,
        }

    @staticmethod
    def _execution_request(
        db: Session,
        *,
        normalized_intent: Dict[str, Any],
        simulation: Dict[str, Any],
        execution_id: str,
        approval_id: int | None,
    ) -> Dict[str, Any]:
        target_accounts = CloudIntentExecutionService._target_accounts_for_intent(db, normalized_intent, simulation)
        backend, backend_config = CloudIntentExecutionService._build_backend_config(execution_id)
        backend_validation = CloudIntentExecutionService._backend_validation(backend, backend_config)
        terraform_preview = simulation.get("terraform_plan_preview") if isinstance(
            simulation.get("terraform_plan_preview"), dict
        ) else {}
        post_check_plan = terraform_preview.get("post_check_plan") if isinstance(
            terraform_preview.get("post_check_plan"), dict
        ) else {}
        evidence_plan = terraform_preview.get("evidence_plan") if isinstance(
            terraform_preview.get("evidence_plan"), dict
        ) else {}

        return {
            "execution_id": execution_id,
            "approval_id": approval_id,
            "intent": {
                "intent_type": normalized_intent.get("intent_type"),
                "name": normalized_intent.get("name"),
                "spec": normalized_intent.get("spec"),
                "metadata": normalized_intent.get("metadata"),
            },
            "terraform": {
                "mode": CloudIntentExecutionService.execution_mode(),
                "binary": CloudIntentExecutionService.terraform_binary(),
                "parallelism": CloudIntentExecutionService.parallelism(),
                "lock_timeout": CloudIntentExecutionService.lock_timeout(),
                "apply_timeout_seconds": CloudIntentExecutionService.apply_timeout_seconds(),
            },
            "state_backend": {
                "backend": backend,
                "config": backend_config,
                "validation": backend_validation,
            },
            "post_check_plan": post_check_plan,
            "evidence_plan": evidence_plan,
            "target_accounts": [
                CloudIntentExecutionService._masked_account_payload(account)
                for account in target_accounts
            ],
            "terraform_plan_preview": terraform_preview,
            "simulation_summary": {
                "risk_score": int(simulation.get("risk_score") or 0),
                "change_summary": list(simulation.get("change_summary") or []),
                "blast_radius": dict(simulation.get("blast_radius") or {}),
                "cloud_scope": dict(simulation.get("cloud_scope") or {}),
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _render_provider_module(module_dir: Path, provider: str) -> None:
        payload = {
            "terraform": {"required_version": ">= 1.5.0"},
            "variable": {
                "provider_name": {},
                "account_id": {},
                "account_name": {},
                "intent_name": {},
                "regions": {},
                "resource_types": {},
                "required_tags": {},
                "blocked_ingress_cidrs": {},
                "protected_route_destinations": {},
                "allowed_default_route_targets": {},
                "enforce_private_only_next_hop": {},
            },
            "output": {
                "execution_summary": {
                    "value": {
                        "provider": "${var.provider_name}",
                        "account_id": "${var.account_id}",
                        "account_name": "${var.account_name}",
                        "intent_name": "${var.intent_name}",
                        "regions": "${var.regions}",
                        "resource_types": "${var.resource_types}",
                        "required_tags": "${var.required_tags}",
                        "blocked_ingress_cidrs": "${var.blocked_ingress_cidrs}",
                        "protected_route_destinations": "${var.protected_route_destinations}",
                        "allowed_default_route_targets": "${var.allowed_default_route_targets}",
                        "enforce_private_only_next_hop": "${var.enforce_private_only_next_hop}",
                    }
                }
            },
        }
        CloudIntentExecutionService._write_json(module_dir / "main.tf.json", payload)
        CloudIntentExecutionService._write_text(
            module_dir / "README.txt",
            (
                f"NetSphere cloud intent execution module for {provider}.\n"
                "This module is generated from the common cloud intent contract and is ready for preview/apply workflows.\n"
                "Provider-specific resources can be expanded over time without changing the approval/evidence pipeline.\n"
            ),
        )

    @staticmethod
    def _render_module_tree(bundle_dir: Path, execution_request: Dict[str, Any]) -> Dict[str, Any]:
        terraform_dir = bundle_dir / "terraform"
        modules_dir = terraform_dir / "modules"
        terraform_dir.mkdir(parents=True, exist_ok=True)
        modules_dir.mkdir(parents=True, exist_ok=True)

        intent = execution_request.get("intent") if isinstance(execution_request.get("intent"), dict) else {}
        spec = intent.get("spec") if isinstance(intent.get("spec"), dict) else {}
        targets = spec.get("targets") if isinstance(spec.get("targets"), dict) else {}
        explicit_regions = [str(v).strip() for v in list(targets.get("regions") or []) if str(v or "").strip()]
        resource_types = [str(v).strip().lower() for v in list(targets.get("resource_types") or []) if str(v or "").strip()]
        required_tags = list(spec.get("required_tags") or [])
        blocked_ingress_cidrs = list(spec.get("blocked_ingress_cidrs") or [])
        protected_route_destinations = list(spec.get("protected_route_destinations") or [])
        allowed_default_route_targets = list(spec.get("allowed_default_route_targets") or [])
        enforce_private_only_next_hop = bool(spec.get("enforce_private_only_next_hop", False))

        rendered_providers: List[str] = []
        skipped_providers: List[str] = []
        module_calls: Dict[str, Any] = {}
        module_refs: Dict[str, str] = {}
        account_ids: List[int] = []

        for account in list(execution_request.get("target_accounts") or []):
            provider = CloudIntentExecutionService._normalize_provider(account.get("provider"))
            if provider not in CloudIntentExecutionService.SUPPORTED_RENDER_PROVIDERS:
                if provider not in skipped_providers:
                    skipped_providers.append(provider)
                continue

            provider_module_dir = modules_dir / provider / "cloud_policy"
            if provider not in rendered_providers:
                CloudIntentExecutionService._render_provider_module(provider_module_dir, provider)
                rendered_providers.append(provider)

            account_id = int(account.get("account_id") or 0)
            account_ids.append(account_id)
            module_name = f"{provider}_account_{account_id}"
            module_refs[module_name] = f"${{module.{module_name}.execution_summary}}"
            regions = explicit_regions or ([account.get("default_region")] if account.get("default_region") else [])
            module_calls[module_name] = {
                "source": f"./modules/{provider}/cloud_policy",
                "provider_name": provider,
                "account_id": account_id,
                "account_name": str(account.get("name") or ""),
                "intent_name": str(intent.get("name") or "cloud-intent"),
                "regions": regions,
                "resource_types": resource_types,
                "required_tags": required_tags,
                "blocked_ingress_cidrs": blocked_ingress_cidrs,
                "protected_route_destinations": protected_route_destinations,
                "allowed_default_route_targets": allowed_default_route_targets,
                "enforce_private_only_next_hop": enforce_private_only_next_hop,
            }

        backend = execution_request.get("state_backend") if isinstance(execution_request.get("state_backend"), dict) else {}
        backend_name = str(backend.get("backend") or "local")
        backend_block = {
            "terraform": {
                "required_version": ">= 1.5.0",
                "backend": {backend_name: {}},
            }
        }
        CloudIntentExecutionService._write_json(terraform_dir / "backend.tf.json", backend_block)
        CloudIntentExecutionService._write_json(
            terraform_dir / f"backend.{backend_name}.auto.tfbackend.json",
            dict(backend.get("config") or {}),
        )

        root_payload = {
            "module": module_calls,
            "output": {
                "execution_id": {"value": str(execution_request.get("execution_id") or "")},
                "rendered_modules": {"value": module_refs},
                "render_summary": {
                    "value": {
                        "accounts": account_ids,
                        "providers": rendered_providers,
                        "regions": explicit_regions,
                        "resource_types": resource_types,
                    }
                },
            },
        }
        CloudIntentExecutionService._write_json(terraform_dir / "main.tf.json", root_payload)
        CloudIntentExecutionService._write_text(
            terraform_dir / "README.txt",
            (
                "This directory is generated by NetSphere Cloud Pro.\n"
                "It contains provider modules generated from the common cloud intent contract.\n"
                "Preview, approval, apply, and evidence flows all use the same rendered execution bundle.\n"
            ),
        )

        return {
            "terraform_dir": str(terraform_dir),
            "rendered_providers": rendered_providers,
            "skipped_providers": skipped_providers,
            "module_count": len(module_calls),
            "backend_file": str(terraform_dir / f"backend.{backend_name}.auto.tfbackend.json"),
        }

    @staticmethod
    def _build_runner_env(
        bundle_dir: Path,
        target_accounts_runtime: List[Dict[str, Any]],
    ) -> Tuple[Dict[str, str], List[str]]:
        env = {k: str(v) for k, v in os.environ.items()}
        env["TF_IN_AUTOMATION"] = "1"
        env["TF_INPUT"] = "0"
        env["TF_CLI_ARGS_plan"] = (
            f"-lock-timeout={CloudIntentExecutionService.lock_timeout()} "
            f"-parallelism={CloudIntentExecutionService.parallelism()}"
        )
        env["TF_CLI_ARGS_apply"] = f"-lock-timeout={CloudIntentExecutionService.lock_timeout()}"

        runtime_artifacts: List[str] = []
        if len(target_accounts_runtime) != 1:
            return env, runtime_artifacts

        account = target_accounts_runtime[0]
        provider = CloudIntentExecutionService._normalize_provider(account.get("provider"))
        creds = dict(account.get("runtime_credentials") or {})

        if provider == "aws":
            if creds.get("access_key"):
                env["AWS_ACCESS_KEY_ID"] = str(creds.get("access_key"))
            if creds.get("secret_key"):
                env["AWS_SECRET_ACCESS_KEY"] = str(creds.get("secret_key"))
            if creds.get("session_token"):
                env["AWS_SESSION_TOKEN"] = str(creds.get("session_token"))
            if creds.get("region"):
                env["AWS_DEFAULT_REGION"] = str(creds.get("region"))
            if creds.get("role_arn"):
                env["NETSPHERE_AWS_ROLE_ARN"] = str(creds.get("role_arn"))
            if creds.get("external_id"):
                env["NETSPHERE_AWS_EXTERNAL_ID"] = str(creds.get("external_id"))
        elif provider == "azure":
            for key, env_key in {
                "tenant_id": "ARM_TENANT_ID",
                "subscription_id": "ARM_SUBSCRIPTION_ID",
                "client_id": "ARM_CLIENT_ID",
                "client_secret": "ARM_CLIENT_SECRET",
            }.items():
                if creds.get(key):
                    env[env_key] = str(creds.get(key))
        elif provider == "gcp":
            if creds.get("project_id"):
                env["GOOGLE_CLOUD_PROJECT"] = str(creds.get("project_id"))
            if isinstance(creds.get("service_account_json"), dict):
                cred_path = bundle_dir / "runtime" / "gcp-service-account.json"
                CloudIntentExecutionService._write_json(cred_path, dict(creds.get("service_account_json") or {}))
                env["GOOGLE_APPLICATION_CREDENTIALS"] = str(cred_path)
                runtime_artifacts.append(str(cred_path))
        elif provider == "ncp":
            if creds.get("access_key"):
                env["NCLOUD_ACCESS_KEY"] = str(creds.get("access_key"))
            if creds.get("secret_key"):
                env["NCLOUD_SECRET_KEY"] = str(creds.get("secret_key"))
            if creds.get("region_code") or creds.get("region"):
                env["NCLOUD_REGION"] = str(creds.get("region_code") or creds.get("region"))

        return env, runtime_artifacts

    @staticmethod
    def _run_terraform_command(
        *,
        terraform_dir: Path,
        args: List[str],
        env: Dict[str, str],
        log_path: Path,
    ) -> Dict[str, Any]:
        command = CloudIntentExecutionService._terraform_command_prefix() + args
        completed = subprocess.run(
            command,
            cwd=str(terraform_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=CloudIntentExecutionService.apply_timeout_seconds(),
            check=False,
        )
        combined = []
        if completed.stdout:
            combined.append(completed.stdout)
        if completed.stderr:
            combined.append(completed.stderr)
        CloudIntentExecutionService._write_text(log_path, "\n".join(combined))
        return {
            "command": command,
            "returncode": int(completed.returncode),
            "ok": int(completed.returncode) == 0,
            "log_path": str(log_path),
        }

    @staticmethod
    def _execute_real_apply(
        *,
        bundle_dir: Path,
        execution_request: Dict[str, Any],
        target_accounts_runtime: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        state_backend = execution_request.get("state_backend") if isinstance(execution_request.get("state_backend"), dict) else {}
        validation = state_backend.get("validation") if isinstance(state_backend.get("validation"), dict) else {}
        if not bool(validation.get("valid")):
            return {
                "mode": "real_apply",
                "status": "configuration_error",
                "errors": list(validation.get("errors") or []),
                "warnings": list(validation.get("warnings") or []),
            }

        terraform_dir = bundle_dir / "terraform"
        logs_dir = bundle_dir / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        env, runtime_artifacts = CloudIntentExecutionService._build_runner_env(bundle_dir, target_accounts_runtime)
        steps: List[Dict[str, Any]] = []
        plan_path = terraform_dir / "netsphere.tfplan"

        for name, args in [
            ("version", ["version"]),
            ("init", ["init", "-input=false"]),
            ("validate", ["validate", "-no-color"]),
            ("plan", ["plan", "-input=false", "-no-color", f"-out={plan_path.name}"]),
            ("apply", ["apply", "-input=false", "-auto-approve", plan_path.name]),
        ]:
            result = CloudIntentExecutionService._run_terraform_command(
                terraform_dir=terraform_dir,
                args=args,
                env=env,
                log_path=logs_dir / f"{name}.log",
            )
            result["step"] = name
            steps.append(result)
            if not bool(result.get("ok")):
                return {
                    "mode": "real_apply",
                    "status": f"{name}_failed",
                    "steps": steps,
                    "runtime_artifacts": runtime_artifacts,
                }

        outputs_result = CloudIntentExecutionService._run_terraform_command(
            terraform_dir=terraform_dir,
            args=["output", "-json"],
            env=env,
            log_path=logs_dir / "output.log",
        )
        outputs_result["step"] = "output"
        steps.append(outputs_result)

        outputs_payload: Dict[str, Any] = {}
        if outputs_result.get("ok"):
            try:
                outputs_payload = json.loads((logs_dir / "output.log").read_text(encoding="utf-8") or "{}")
            except Exception:
                outputs_payload = {}

        if not CloudIntentExecutionService.keep_runtime_files():
            for artifact in runtime_artifacts:
                try:
                    Path(artifact).unlink(missing_ok=True)
                except Exception:
                    pass

        return {
            "mode": "real_apply",
            "status": "applied_real",
            "steps": steps,
            "outputs": outputs_payload,
            "runtime_artifacts": runtime_artifacts,
            "plan_path": str(plan_path),
        }

    @staticmethod
    def _write_bundle_files(
        *,
        bundle_dir: Path,
        normalized_intent: Dict[str, Any],
        simulation: Dict[str, Any],
        execution_request: Dict[str, Any],
        terraform_render: Dict[str, Any],
        runner_result: Dict[str, Any],
    ) -> None:
        CloudIntentExecutionService._write_json(bundle_dir / "intent.json", normalized_intent)
        CloudIntentExecutionService._write_json(bundle_dir / "simulation.json", simulation)
        CloudIntentExecutionService._write_json(
            bundle_dir / "terraform-plan-preview.json",
            dict(simulation.get("terraform_plan_preview") or {}),
        )
        preview = simulation.get("terraform_plan_preview") if isinstance(simulation.get("terraform_plan_preview"), dict) else {}
        CloudIntentExecutionService._write_json(
            bundle_dir / "post-check-plan.json",
            dict(preview.get("post_check_plan") or {}),
        )
        CloudIntentExecutionService._write_json(
            bundle_dir / "evidence-plan.json",
            dict(preview.get("evidence_plan") or {}),
        )
        CloudIntentExecutionService._write_json(
            bundle_dir / "rollback-plan.json",
            dict(preview.get("rollback_plan") or {}),
        )
        CloudIntentExecutionService._write_json(bundle_dir / "execution-request.json", execution_request)
        CloudIntentExecutionService._write_json(bundle_dir / "terraform-render.json", terraform_render)
        CloudIntentExecutionService._write_json(bundle_dir / "runner-result.json", runner_result)
        CloudIntentExecutionService._write_json(
            bundle_dir / "post-check-result.json",
            dict(runner_result.get("post_check_result") or {}),
        )
        CloudIntentExecutionService._write_json(
            bundle_dir / "rollback-result.json",
            dict(runner_result.get("rollback_result") or {}),
        )
        CloudIntentExecutionService._write_text(
            bundle_dir / "README.txt",
            (
                "NetSphere Cloud Pro execution bundle.\n"
                "This bundle contains normalized intent, simulation, Terraform rendering, and execution results.\n"
                "Provider credentials are masked in persisted bundle files.\n"
            ),
        )

    @staticmethod
    def _run_post_check(
        db: Session,
        *,
        execution_request: Dict[str, Any],
        target_accounts_runtime: List[Dict[str, Any]],
        actor_user: Any,
        mode: str,
    ) -> Dict[str, Any]:
        post_check_plan = execution_request.get("post_check_plan") if isinstance(
            execution_request.get("post_check_plan"), dict
        ) else {}
        required = bool(post_check_plan.get("required", True))
        account_ids = [
            int(account.get("account_id") or 0)
            for account in list(target_accounts_runtime or [])
            if int(account.get("account_id") or 0) > 0
        ]
        execution_id = str(execution_request.get("execution_id") or "").strip()

        if not required:
            return {
                "required": False,
                "status": "disabled",
                "message": "Post-check is disabled for this cloud intent.",
                "steps": list(post_check_plan.get("steps") or []),
            }

        if mode in {"prepare_only", "disabled"}:
            return {
                "required": True,
                "status": "skipped_prepare_only",
                "message": "Prepare-only mode does not run live post-check verification.",
                "steps": list(post_check_plan.get("steps") or []),
            }

        if not account_ids:
            return {
                "required": True,
                "status": "skipped_no_accounts",
                "message": "No target cloud accounts were resolved for post-check verification.",
                "steps": list(post_check_plan.get("steps") or []),
            }

        from app.schemas.cloud import CloudPipelineRunRequest
        from app.services.cloud_pipeline_service import CloudPipelineService

        req = CloudPipelineRunRequest(
            account_ids=account_ids,
            preflight=True,
            include_hybrid_build=True,
            include_hybrid_infer=True,
            enrich_inferred=True,
            continue_on_error=True,
            idempotency_key=f"cloud_intent_post_check:{execution_id}",
            force=True,
        )
        out = CloudPipelineService.run(
            db,
            tenant_id=getattr(actor_user, "tenant_id", None),
            owner_id=int(getattr(actor_user, "id", 0) or 0),
            req=req,
        )
        payload = out.model_dump() if hasattr(out, "model_dump") else dict(out)
        account_results = list(payload.get("accounts") or [])
        blocking_failures: List[Dict[str, Any]] = []
        for row in account_results:
            preflight_status = str(row.get("preflight_status") or "").strip().lower()
            scan_status = str(row.get("scan_status") or "").strip().lower()
            if preflight_status not in {"ok", "skipped"} or scan_status not in {"ok", "skipped"}:
                blocking_failures.append(
                    {
                        "account_id": int(row.get("account_id") or 0),
                        "provider": str(row.get("provider") or ""),
                        "preflight_status": preflight_status or "unknown",
                        "scan_status": scan_status or "unknown",
                        "message": row.get("message") or row.get("preflight_message"),
                    }
                )

        status = "passed"
        if bool(blocking_failures) or str(payload.get("status") or "").strip().lower() in {"failed", "partial"}:
            status = "failed"

        return {
            "required": True,
            "status": status,
            "pipeline_status": str(payload.get("status") or "unknown"),
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "steps": list(post_check_plan.get("steps") or []),
            "scanned_resources": int(payload.get("scanned_resources") or 0),
            "failed_accounts": int(payload.get("failed_accounts") or 0),
            "normalized_by_provider": dict(payload.get("normalized_by_provider") or {}),
            "account_results": account_results,
            "blocking_failures": blocking_failures,
            "message": payload.get("message"),
        }

    @staticmethod
    def _build_rollback_plan(
        *,
        execution_request: Dict[str, Any],
        target_accounts_runtime: List[Dict[str, Any]],
        post_check_result: Dict[str, Any],
        mode: str,
    ) -> Dict[str, Any]:
        preview = execution_request.get("terraform_plan_preview") if isinstance(
            execution_request.get("terraform_plan_preview"), dict
        ) else {}
        summary = preview.get("summary") if isinstance(preview.get("summary"), dict) else {}
        failure = str(post_check_result.get("status") or "").strip().lower() == "failed"
        auto_enabled = CloudIntentExecutionService.auto_rollback_enabled()
        automatic_eligible = bool(failure) and bool(auto_enabled) and mode == "mock_apply"
        provider_set = sorted(
            {
                CloudIntentExecutionService._normalize_provider(account.get("provider"))
                for account in list(target_accounts_runtime or [])
                if str(account.get("provider") or "").strip()
            }
        )

        operator_steps = [
            "Review post-check failures and impacted accounts before any rollback approval.",
            "Open the generated evidence bundle and confirm the rendered modules and provider scope.",
            "Re-run the intended Cloud Intent in prepare-only mode before approving rollback execution.",
        ]
        if mode == "real_apply":
            operator_steps.append("Use the captured Terraform bundle and backend state to execute the approved rollback workflow.")
        elif mode == "mock_apply":
            operator_steps.append("Mock mode can simulate rollback success without provider writes.")

        return {
            "required": bool(failure),
            "status": "not_needed" if not failure else ("mock_ready" if automatic_eligible else "approval_required"),
            "strategy": "terraform_state_reconcile",
            "trigger": "post_check_failed" if failure else "post_check_passed",
            "automatic_enabled": auto_enabled,
            "automatic_eligible": automatic_eligible,
            "providers": provider_set,
            "accounts": int(summary.get("accounts") or len(target_accounts_runtime)),
            "regions": int(summary.get("regions") or 0),
            "operator_steps": operator_steps,
            "evidence_artifacts": [
                "terraform-plan-preview.json",
                "post-check-result.json",
                "runner-result.json",
                "rollback-plan.json",
            ],
        }

    @staticmethod
    def _build_rollback_result(
        *,
        rollback_plan: Dict[str, Any],
        post_check_result: Dict[str, Any],
        mode: str,
    ) -> Dict[str, Any]:
        failure = str(post_check_result.get("status") or "").strip().lower() == "failed"
        if not failure:
            return {
                "attempted": False,
                "success": False,
                "status": "not_needed",
                "message": "Rollback was not needed because post-check passed.",
            }

        if bool(rollback_plan.get("automatic_eligible")) and mode == "mock_apply":
            return {
                "attempted": True,
                "success": True,
                "status": "mock_rollback_completed",
                "message": "Mock mode simulated rollback after post-check failure.",
            }

        return {
            "attempted": False,
            "success": False,
            "status": "approval_required",
            "message": "Rollback plan is prepared and awaits explicit approval.",
        }

    @staticmethod
    def run(
        db: Session,
        *,
        normalized_intent: Dict[str, Any],
        simulation: Dict[str, Any],
        execution_id: str,
        approval_id: int | None,
        actor_user: Any,
    ) -> Dict[str, Any]:
        if not CloudIntentExecutionService.live_apply_enabled():
            return {
                "status": "skipped_execution_disabled",
                "message": "Cloud intent execution is disabled by policy.",
            }

        execution_request = CloudIntentExecutionService._execution_request(
            db,
            normalized_intent=normalized_intent,
            simulation=simulation,
            execution_id=execution_id,
            approval_id=approval_id,
        )
        target_accounts_runtime = CloudIntentExecutionService._target_accounts_for_intent(
            db,
            normalized_intent,
            simulation,
        )
        bundle_dir = CloudIntentExecutionService._bundle_dir(execution_id)
        terraform_render = CloudIntentExecutionService._render_module_tree(bundle_dir, execution_request)

        mode = CloudIntentExecutionService.execution_mode()
        if mode == "disabled":
            runner_result = {"mode": mode, "status": "skipped_execution_disabled"}
            status = "skipped_execution_disabled"
        elif mode == "prepare_only":
            runner_result = {
                "mode": mode,
                "status": "prepared_only",
                "target_accounts": len(target_accounts_runtime),
                "rendered_providers": list(terraform_render.get("rendered_providers") or []),
            }
            status = "prepared_only"
        elif mode == "mock_apply":
            provider_runs = [
                {
                    "account_id": int(account.get("account_id") or 0),
                    "provider": str(account.get("provider") or ""),
                    "status": "mock_applied",
                }
                for account in target_accounts_runtime
            ]
            runner_result = {
                "mode": mode,
                "status": "applied_mock",
                "provider_runs": provider_runs,
                "rendered_providers": list(terraform_render.get("rendered_providers") or []),
            }
            status = "applied_mock"
        else:
            runner_result = CloudIntentExecutionService._execute_real_apply(
                bundle_dir=bundle_dir,
                execution_request=execution_request,
                target_accounts_runtime=target_accounts_runtime,
            )
            status = str(runner_result.get("status") or "real_apply_failed")

        post_check_result = CloudIntentExecutionService._run_post_check(
            db,
            execution_request=execution_request,
            target_accounts_runtime=target_accounts_runtime,
            actor_user=actor_user,
            mode=mode,
        )
        rollback_plan = CloudIntentExecutionService._build_rollback_plan(
            execution_request=execution_request,
            target_accounts_runtime=target_accounts_runtime,
            post_check_result=post_check_result,
            mode=mode,
        )
        rollback_result = CloudIntentExecutionService._build_rollback_result(
            rollback_plan=rollback_plan,
            post_check_result=post_check_result,
            mode=mode,
        )
        runner_result["post_check_result"] = post_check_result
        runner_result["rollback_plan"] = rollback_plan
        runner_result["rollback_result"] = rollback_result
        if str(post_check_result.get("status") or "").strip().lower() == "failed":
            runner_result["post_check_failed"] = True
            runner_result["failure_cause"] = "post_check_failed"
            status = "post_check_failed"
        runner_result["rollback_attempted"] = bool(rollback_result.get("attempted"))
        runner_result["rollback_success"] = bool(rollback_result.get("success"))

        CloudIntentExecutionService._write_bundle_files(
            bundle_dir=bundle_dir,
            normalized_intent=normalized_intent,
            simulation=simulation,
            execution_request=execution_request,
            terraform_render=terraform_render,
            runner_result=runner_result,
        )

        return {
            "status": status,
            "bundle_dir": str(bundle_dir),
            "provider_runs": list(runner_result.get("provider_runs") or []),
            "rendered_providers": list(terraform_render.get("rendered_providers") or []),
            "state_backend": dict(execution_request.get("state_backend") or {}),
            "runner_result": runner_result,
            "post_check_result": post_check_result,
            "rollback_plan": rollback_plan,
            "rollback_result": rollback_result,
            "post_check_failed": bool(runner_result.get("post_check_failed")),
            "failure_cause": runner_result.get("failure_cause"),
            "rollback_attempted": bool(runner_result.get("rollback_attempted")),
            "rollback_success": bool(runner_result.get("rollback_success")),
        }
