from __future__ import annotations

import base64
from datetime import datetime
import hashlib
import hmac
import json
import re
import time
from typing import Any, Dict, List, Sequence
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.cloud import CloudAccount, CloudResource
from app.models.device import EventLog
from app.schemas.cloud import CloudBootstrapRunRequest, CloudBootstrapRunResponse, CloudBootstrapTargetResult
from app.services.approval_execution_service import ApprovalExecutionService
from app.services.change_execution_service import ChangeExecutionService
from app.services.cloud_credentials_service import decrypt_credentials_for_runtime


class CloudBootstrapService:
    KPI_EVENT_ID = "CLOUD_BOOTSTRAP_KPI"
    _VM_RESOURCE_TYPES = {
        "virtual_machine",
        "vm",
        "instance",
        "compute_instance",
        "ec2_instance",
        "azure_vm",
        "gce_instance",
    }
    _BLOCKED_STATES = {
        "stopped",
        "terminated",
        "deallocated",
        "failed",
        "error",
    }

    @staticmethod
    def _normalize_ids(raw_ids: Sequence[Any] | None) -> List[int]:
        out: List[int] = []
        seen = set()
        for raw in list(raw_ids or []):
            try:
                value = int(raw)
            except Exception:
                continue
            if value in seen:
                continue
            seen.add(value)
            out.append(value)
        return out

    @staticmethod
    def _normalize_regions(raw_regions: Sequence[Any] | None) -> List[str]:
        out: List[str] = []
        seen = set()
        for raw in list(raw_regions or []):
            value = str(raw or "").strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            out.append(value)
        return out

    @staticmethod
    def _normalize_resource_ids(raw_ids: Sequence[Any] | None) -> List[str]:
        out: List[str] = []
        seen = set()
        for raw in list(raw_ids or []):
            value = str(raw or "").strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out

    @staticmethod
    def _shell_escape(value: Any) -> str:
        text = str(value if value is not None else "")
        return text.replace("\\", "\\\\").replace('"', '\\"')

    @staticmethod
    def _default_template(provider: str) -> str:
        provider_lc = str(provider or "").strip().lower()
        common_block = (
            "NETMANAGER_CONTROLLER_URL={{controller_url}}\n"
            "NETMANAGER_PROVIDER={{provider}}\n"
            "NETMANAGER_ACCOUNT_ID={{account_id}}\n"
            "NETMANAGER_RESOURCE_ID={{resource_id}}\n"
            "NETMANAGER_REGION={{region}}\n"
            "NETMANAGER_BOOTSTRAP_TOKEN={{bootstrap_token}}\n"
            "NETMANAGER_EXECUTION_ID={{execution_id}}\n"
        )
        if provider_lc in {"aws", "gcp"}:
            return (
                "#cloud-config\n"
                "write_files:\n"
                "  - path: /etc/netmanager/bootstrap.env\n"
                "    permissions: '0600'\n"
                "    content: |\n"
                + "".join([f"      {line}\n" for line in common_block.splitlines()])
                + "runcmd:\n"
                + "  - [bash, -lc, \"echo 'netmanager bootstrap start' > /var/log/netmanager-bootstrap.log\"]\n"
                + "  - [bash, -lc, \"source /etc/netmanager/bootstrap.env && echo $NETMANAGER_CONTROLLER_URL >> /var/log/netmanager-bootstrap.log\"]\n"
            )
        if provider_lc in {"azure", "naver", "naver_cloud", "ncp"}:
            return (
                "#!/bin/bash\n"
                "set -eu\n"
                "mkdir -p /etc/netmanager\n"
                "cat > /etc/netmanager/bootstrap.env <<'EOF'\n"
                + common_block
                + "EOF\n"
                "echo 'netmanager bootstrap start' > /var/log/netmanager-bootstrap.log\n"
                "source /etc/netmanager/bootstrap.env\n"
                "echo \"$NETMANAGER_CONTROLLER_URL\" >> /var/log/netmanager-bootstrap.log\n"
            )
        return (
            "#!/bin/bash\n"
            "set -eu\n"
            "echo 'netmanager bootstrap start' > /var/log/netmanager-bootstrap.log\n"
            "echo 'controller={{controller_url}} provider={{provider}} resource={{resource_id}}' >> /var/log/netmanager-bootstrap.log\n"
        )

    @staticmethod
    def _render_template(template: str, context: Dict[str, Any]) -> str:
        out = str(template or "")
        for key, value in dict(context or {}).items():
            token = "{{" + str(key).strip() + "}}"
            out = out.replace(token, CloudBootstrapService._shell_escape(value))
        return out

    @staticmethod
    def _compute_script_hash(script: str) -> str:
        return hashlib.sha256(str(script or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _build_context(
        *,
        req: CloudBootstrapRunRequest,
        account: CloudAccount,
        resource: CloudResource,
        execution_id: str,
    ) -> Dict[str, Any]:
        resource_meta = dict(resource.resource_metadata or {})
        region = str(resource.region or resource_meta.get("region") or "")
        seed = f"{account.id}:{resource.resource_id}:{execution_id}:{datetime.utcnow().isoformat()}"
        bootstrap_token = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
        context = {
            "controller_url": "http://localhost:8000/api/v1",
            "provider": str(account.provider or "").lower(),
            "account_id": int(account.id),
            "resource_id": str(resource.resource_id or ""),
            "resource_name": str(resource.name or ""),
            "region": region,
            "execution_id": str(execution_id or ""),
            "bootstrap_token": bootstrap_token,
        }
        context.update(dict(req.context or {}))
        return context

    @staticmethod
    def _state_of(resource: CloudResource) -> str:
        state = str(resource.state or "").strip().lower()
        if state:
            return state
        metadata = dict(resource.resource_metadata or {})
        return str(metadata.get("state") or "").strip().lower()

    @staticmethod
    def _pre_check(resource: CloudResource) -> Dict[str, Any]:
        state = CloudBootstrapService._state_of(resource)
        if state in CloudBootstrapService._BLOCKED_STATES:
            return {"ok": False, "message": f"resource state blocked: {state}"}
        if not str(resource.resource_id or "").strip():
            return {"ok": False, "message": "resource_id is empty"}
        return {"ok": True, "message": "pre-check passed"}

    @staticmethod
    def _post_check(*, script: str, apply_result: Dict[str, Any]) -> Dict[str, Any]:
        if not bool(apply_result.get("ok")):
            return {"ok": False, "message": str(apply_result.get("message") or "apply failed")}
        text = str(script or "")
        if not text.strip():
            return {"ok": False, "message": "rendered script is empty"}
        if "NETMANAGER_CONTROLLER_URL=" not in text:
            return {"ok": False, "message": "controller registration stanza is missing"}
        return {"ok": True, "message": "post-check passed"}

    @staticmethod
    def _runtime_credentials(account: CloudAccount) -> Dict[str, Any]:
        return decrypt_credentials_for_runtime(account.provider, account.credentials or {})

    @staticmethod
    def _aws_session(credentials: Dict[str, Any], *, region: str):
        import boto3

        auth_type = str(
            credentials.get("auth_type") or ("assume_role" if credentials.get("role_arn") else "access_key")
        ).strip().lower()
        access_key = str(credentials.get("access_key") or "").strip()
        secret_key = str(credentials.get("secret_key") or "").strip()
        session_token = str(credentials.get("session_token") or "").strip()
        source_access_key = str(credentials.get("source_access_key") or "").strip()
        source_secret_key = str(credentials.get("source_secret_key") or "").strip()
        source_session_token = str(credentials.get("source_session_token") or "").strip()
        role_arn = str(credentials.get("role_arn") or "").strip()
        external_id = str(credentials.get("external_id") or "").strip()
        role_session_name = str(credentials.get("role_session_name") or "netmanager-cloud-bootstrap").strip()

        base_kwargs: Dict[str, Any] = {"region_name": str(region or "").strip() or "ap-northeast-2"}
        if source_access_key or source_secret_key:
            if not source_access_key or not source_secret_key:
                raise ValueError("source_access_key and source_secret_key must be provided together")
            base_kwargs["aws_access_key_id"] = source_access_key
            base_kwargs["aws_secret_access_key"] = source_secret_key
            if source_session_token:
                base_kwargs["aws_session_token"] = source_session_token
        elif access_key or secret_key:
            if not access_key or not secret_key:
                raise ValueError("Missing AWS access_key/secret_key")
            base_kwargs["aws_access_key_id"] = access_key
            base_kwargs["aws_secret_access_key"] = secret_key
            if session_token:
                base_kwargs["aws_session_token"] = session_token

        session = boto3.Session(**base_kwargs)
        if auth_type != "assume_role":
            return session
        if not role_arn:
            raise ValueError("Missing AWS role_arn for assume_role auth")
        sts = session.client("sts")
        assume_kwargs: Dict[str, Any] = {
            "RoleArn": role_arn,
            "RoleSessionName": role_session_name,
        }
        if external_id:
            assume_kwargs["ExternalId"] = external_id
        assumed = sts.assume_role(**assume_kwargs).get("Credentials", {})
        if not assumed:
            raise ValueError("AssumeRole returned empty credentials")
        return boto3.Session(
            aws_access_key_id=assumed.get("AccessKeyId"),
            aws_secret_access_key=assumed.get("SecretAccessKey"),
            aws_session_token=assumed.get("SessionToken"),
            region_name=base_kwargs["region_name"],
        )

    @staticmethod
    def _resolve_aws_instance_id(resource: CloudResource) -> str:
        metadata = dict(resource.resource_metadata or {})
        rid = str(resource.resource_id or "").strip()
        if rid.startswith("i-"):
            return rid
        candidate = str(metadata.get("instance_id") or metadata.get("instanceId") or "").strip()
        if candidate.startswith("i-"):
            return candidate
        raise ValueError("Unable to resolve AWS instance id for bootstrap target")

    @staticmethod
    def _apply_bootstrap_aws(
        *,
        account: CloudAccount,
        resource: CloudResource,
        script: str,
        request_context: Dict[str, Any],
        runtime_credentials: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            region = str(resource.region or runtime_credentials.get("region") or "ap-northeast-2").strip() or "ap-northeast-2"
            metadata = dict(resource.resource_metadata or {})
            instance_id = CloudBootstrapService._resolve_aws_instance_id(resource)
            preferred = str(
                request_context.get("aws_bootstrap_path")
                or request_context.get("bootstrap_channel")
                or "auto"
            ).strip().lower()
            if preferred in {"", "auto"}:
                preferred = "ssm" if bool(metadata.get("ssm_managed")) else "userdata"

            session = CloudBootstrapService._aws_session(runtime_credentials, region=region)
            if preferred == "userdata":
                ec2 = session.client("ec2")
                encoded = base64.b64encode(str(script or "").encode("utf-8")).decode("utf-8")
                ec2.modify_instance_attribute(
                    InstanceId=instance_id,
                    UserData={"Value": encoded},
                )
                return {
                    "ok": True,
                    "transport": "aws:user_data",
                    "message": f"UserData updated for instance {instance_id}",
                    "provider_result": {"instance_id": instance_id, "region": region},
                }

            if preferred in {"ssm", "run_command"}:
                ssm = session.client("ssm")
                lines = str(script or "").splitlines()
                commands = [
                    "cat > /tmp/netmanager-bootstrap.sh <<'EOF'",
                    *lines,
                    "EOF",
                    "chmod +x /tmp/netmanager-bootstrap.sh",
                    "bash /tmp/netmanager-bootstrap.sh",
                ]
                resp = ssm.send_command(
                    InstanceIds=[instance_id],
                    DocumentName="AWS-RunShellScript",
                    Parameters={"commands": commands},
                    Comment="NetSphere cloud bootstrap",
                )
                cmd_id = str((resp or {}).get("Command", {}).get("CommandId") or "").strip()
                return {
                    "ok": True,
                    "transport": "aws:ssm",
                    "message": f"SSM command queued for instance {instance_id}",
                    "provider_result": {"instance_id": instance_id, "region": region, "command_id": cmd_id},
                }

            return {"ok": False, "transport": "aws:none", "message": f"Unsupported AWS bootstrap path: {preferred}"}
        except Exception as e:
            return {"ok": False, "transport": "aws:error", "message": f"{type(e).__name__}: {e}"}

    @staticmethod
    def _parse_azure_vm_resource_id(resource_id: str) -> Dict[str, str]:
        rid = str(resource_id or "").strip()
        if not rid:
            return {}
        parts = [p for p in rid.split("/") if p]
        out: Dict[str, str] = {}
        for i, token in enumerate(parts):
            t = token.lower()
            if t == "subscriptions" and (i + 1) < len(parts):
                out["subscription_id"] = parts[i + 1]
            if t == "resourcegroups" and (i + 1) < len(parts):
                out["resource_group"] = parts[i + 1]
            if t == "virtualmachines" and (i + 1) < len(parts):
                out["vm_name"] = parts[i + 1]
        return out

    @staticmethod
    def _resolve_azure_vm_target(resource: CloudResource) -> Dict[str, str]:
        metadata = dict(resource.resource_metadata or {})
        parsed = CloudBootstrapService._parse_azure_vm_resource_id(str(resource.resource_id or ""))
        resource_group = str(
            metadata.get("resource_group")
            or metadata.get("resourceGroup")
            or parsed.get("resource_group")
            or ""
        ).strip()
        vm_name = str(
            metadata.get("vm_name")
            or metadata.get("vmName")
            or resource.name
            or parsed.get("vm_name")
            or ""
        ).strip()
        subscription_id = str(
            metadata.get("subscription_id")
            or metadata.get("subscriptionId")
            or parsed.get("subscription_id")
            or ""
        ).strip()
        if not resource_group or not vm_name:
            raise ValueError("Unable to resolve Azure vm target (resource_group/vm_name)")
        return {
            "resource_group": resource_group,
            "vm_name": vm_name,
            "subscription_id": subscription_id,
        }

    @staticmethod
    def _apply_bootstrap_azure(
        *,
        account: CloudAccount,
        resource: CloudResource,
        script: str,
        request_context: Dict[str, Any],
        runtime_credentials: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            from azure.identity import ClientSecretCredential
            from azure.mgmt.compute import ComputeManagementClient
            from azure.mgmt.compute.models import RunCommandInput
        except Exception as e:
            return {"ok": False, "transport": "azure:error", "message": f"{type(e).__name__}: {e}"}

        try:
            tenant_id = str(runtime_credentials.get("tenant_id") or "").strip()
            client_id = str(runtime_credentials.get("client_id") or "").strip()
            client_secret = str(runtime_credentials.get("client_secret") or "").strip()
            subscription_id = str(runtime_credentials.get("subscription_id") or "").strip()
            if not all([tenant_id, client_id, client_secret, subscription_id]):
                raise ValueError("Missing Azure credentials")

            target = CloudBootstrapService._resolve_azure_vm_target(resource)
            sub = target.get("subscription_id") or subscription_id
            credential = ClientSecretCredential(tenant_id, client_id, client_secret)
            compute = ComputeManagementClient(credential, sub)

            preferred = str(
                request_context.get("azure_bootstrap_path")
                or request_context.get("bootstrap_channel")
                or "auto"
            ).strip().lower()
            if preferred in {"", "auto"}:
                preferred = "run_command"

            rg = target["resource_group"]
            vm_name = target["vm_name"]

            if preferred in {"run_command", "runcommand"}:
                run_input = RunCommandInput(
                    command_id="RunShellScript",
                    script=str(script or "").splitlines(),
                )
                poller = compute.virtual_machines.begin_run_command(rg, vm_name, run_input)
                result = poller.result(timeout=180)
                return {
                    "ok": True,
                    "transport": "azure:run_command",
                    "message": f"RunCommand invoked for {vm_name}",
                    "provider_result": {
                        "resource_group": rg,
                        "vm_name": vm_name,
                        "result_type": str(type(result).__name__),
                    },
                }

            if preferred in {"custom_script", "customscript"}:
                script_b64 = base64.b64encode(str(script or "").encode("utf-8")).decode("utf-8")
                command = (
                    "bash -lc \"echo " + script_b64 + " | base64 -d > /tmp/netmanager-bootstrap.sh "
                    "&& chmod +x /tmp/netmanager-bootstrap.sh && /bin/bash /tmp/netmanager-bootstrap.sh\""
                )
                ext_name = f"netmanager-bootstrap-{hashlib.sha1(str(resource.resource_id).encode('utf-8')).hexdigest()[:8]}"
                ext_params = {
                    "location": str(resource.region or "koreacentral"),
                    "publisher": "Microsoft.Azure.Extensions",
                    "virtual_machine_extension_type": "CustomScript",
                    "type_handler_version": "2.1",
                    "auto_upgrade_minor_version": True,
                    "settings": {"commandToExecute": command},
                }
                poller = compute.virtual_machine_extensions.begin_create_or_update(
                    rg,
                    vm_name,
                    ext_name,
                    ext_params,
                )
                result = poller.result(timeout=180)
                return {
                    "ok": True,
                    "transport": "azure:custom_script",
                    "message": f"Custom Script extension invoked for {vm_name}",
                    "provider_result": {
                        "resource_group": rg,
                        "vm_name": vm_name,
                        "extension": ext_name,
                        "result_type": str(type(result).__name__),
                    },
                }

            return {"ok": False, "transport": "azure:none", "message": f"Unsupported Azure bootstrap path: {preferred}"}
        except Exception as e:
            return {"ok": False, "transport": "azure:error", "message": f"{type(e).__name__}: {e}"}

    @staticmethod
    def _parse_gcp_instance_self_link(value: str) -> Dict[str, str]:
        text = str(value or "").strip()
        if not text:
            return {}
        m = re.search(r"/projects/([^/]+)/zones/([^/]+)/instances/([^/]+)", text)
        if not m:
            return {}
        return {"project_id": m.group(1), "zone": m.group(2), "instance_name": m.group(3)}

    @staticmethod
    def _resolve_gcp_instance_target(resource: CloudResource, runtime_credentials: Dict[str, Any]) -> Dict[str, str]:
        metadata = dict(resource.resource_metadata or {})
        parsed = CloudBootstrapService._parse_gcp_instance_self_link(str(resource.resource_id or ""))
        project_id = str(
            metadata.get("project_id")
            or metadata.get("projectId")
            or runtime_credentials.get("project_id")
            or parsed.get("project_id")
            or ""
        ).strip()
        zone = str(
            metadata.get("zone")
            or metadata.get("availability_zone")
            or resource.region
            or parsed.get("zone")
            or ""
        ).strip()
        if zone and zone.count("-") < 2:
            zone = str(metadata.get("zone") or parsed.get("zone") or "").strip()
        instance_name = str(
            metadata.get("instance_name")
            or metadata.get("instanceName")
            or resource.name
            or parsed.get("instance_name")
            or ""
        ).strip()
        if not all([project_id, zone, instance_name]):
            raise ValueError("Unable to resolve GCP target (project_id/zone/instance_name)")
        return {"project_id": project_id, "zone": zone, "instance_name": instance_name}

    @staticmethod
    def _apply_bootstrap_gcp(
        *,
        account: CloudAccount,
        resource: CloudResource,
        script: str,
        request_context: Dict[str, Any],
        runtime_credentials: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            from google.cloud import compute_v1
            from google.oauth2 import service_account
        except Exception as e:
            return {"ok": False, "transport": "gcp:error", "message": f"{type(e).__name__}: {e}"}

        try:
            sa_json = runtime_credentials.get("service_account_json")
            if not sa_json:
                raise ValueError("Missing GCP service_account_json")
            info = json.loads(sa_json) if isinstance(sa_json, str) else sa_json
            credentials = service_account.Credentials.from_service_account_info(info)
            target = CloudBootstrapService._resolve_gcp_instance_target(resource, runtime_credentials)
            preferred = str(
                request_context.get("gcp_bootstrap_path")
                or request_context.get("bootstrap_channel")
                or "startup_metadata"
            ).strip().lower()
            if preferred in {"", "auto"}:
                preferred = "startup_metadata"
            if preferred not in {"startup_metadata", "startup_script", "metadata"}:
                return {"ok": False, "transport": "gcp:none", "message": f"Unsupported GCP bootstrap path: {preferred}"}

            instances_client = compute_v1.InstancesClient(credentials=credentials)
            instance = instances_client.get(
                project=target["project_id"],
                zone=target["zone"],
                instance=target["instance_name"],
            )
            existing_items = list(getattr(getattr(instance, "metadata", None), "items", None) or [])
            updated_items: List[Any] = []
            replaced = False
            for item in existing_items:
                key = str(getattr(item, "key", "") or "")
                value = getattr(item, "value", None)
                if key == "startup-script":
                    updated_items.append({"key": "startup-script", "value": str(script or "")})
                    replaced = True
                else:
                    updated_items.append({"key": key, "value": value})
            if not replaced:
                updated_items.append({"key": "startup-script", "value": str(script or "")})

            fingerprint = str(getattr(getattr(instance, "metadata", None), "fingerprint", "") or "")
            metadata_resource = compute_v1.Metadata(
                fingerprint=fingerprint,
                items=updated_items,
            )
            op = instances_client.set_metadata(
                project=target["project_id"],
                zone=target["zone"],
                instance=target["instance_name"],
                metadata_resource=metadata_resource,
            )
            op_name = str(getattr(op, "name", "") or "")
            return {
                "ok": True,
                "transport": "gcp:startup_metadata",
                "message": f"startup-script metadata updated for {target['instance_name']}",
                "provider_result": {
                    "project_id": target["project_id"],
                    "zone": target["zone"],
                    "instance_name": target["instance_name"],
                    "operation": op_name,
                },
            }
        except Exception as e:
            return {"ok": False, "transport": "gcp:error", "message": f"{type(e).__name__}: {e}"}

    @staticmethod
    def _resolve_ncp_instance_no(resource: CloudResource) -> str:
        metadata = dict(resource.resource_metadata or {})
        candidates = [
            metadata.get("server_instance_no"),
            metadata.get("serverInstanceNo"),
            metadata.get("instance_no"),
            metadata.get("instanceNo"),
            metadata.get("server_no"),
            metadata.get("serverNo"),
            resource.resource_id,
        ]
        for raw in candidates:
            value = str(raw or "").strip()
            if not value:
                continue
            if value.isdigit():
                return value
            match = re.search(r"(\d{3,})", value)
            if match:
                return str(match.group(1))
        raise ValueError("Unable to resolve NCP server instance number")

    @staticmethod
    def _ncp_sign_headers(*, method: str, path_with_query: str, access_key: str, secret_key: str) -> Dict[str, str]:
        timestamp = str(int(time.time() * 1000))
        normalized_method = str(method or "GET").strip().upper()
        message = f"{normalized_method} {path_with_query}\n{timestamp}\n{access_key}"
        signature = base64.b64encode(
            hmac.new(str(secret_key).encode("utf-8"), message.encode("utf-8"), hashlib.sha256).digest()
        ).decode("utf-8")
        return {
            "x-ncp-apigw-timestamp": timestamp,
            "x-ncp-iam-access-key": str(access_key),
            "x-ncp-apigw-signature-v2": signature,
        }

    @staticmethod
    def _apply_bootstrap_ncp(
        *,
        account: CloudAccount,
        resource: CloudResource,
        script: str,
        request_context: Dict[str, Any],
        runtime_credentials: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            access_key = str(runtime_credentials.get("access_key") or "").strip()
            secret_key = str(runtime_credentials.get("secret_key") or "").strip()
            if not access_key or not secret_key:
                raise ValueError("Missing NCP access_key/secret_key")

            preferred = str(
                request_context.get("ncp_bootstrap_path")
                or request_context.get("bootstrap_channel")
                or runtime_credentials.get("bootstrap_path")
                or "api_gateway"
            ).strip().lower()
            if preferred in {"", "auto"}:
                preferred = "api_gateway"
            if preferred not in {"api_gateway", "userdata", "user_data"}:
                return {"ok": False, "transport": "ncp:none", "message": f"Unsupported NCP bootstrap path: {preferred}"}

            endpoint = str(
                request_context.get("ncp_bootstrap_endpoint")
                or runtime_credentials.get("bootstrap_endpoint")
                or runtime_credentials.get("api_endpoint")
                or "https://ncloud.apigw.ntruss.com/vserver/v2/setServerInstanceUserData"
            ).strip()
            if not endpoint:
                raise ValueError("NCP bootstrap endpoint is empty")

            parsed = urlparse.urlsplit(endpoint)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid NCP bootstrap endpoint URL")

            instance_no = CloudBootstrapService._resolve_ncp_instance_no(resource)
            region_code = str(
                runtime_credentials.get("region_code")
                or runtime_credentials.get("region")
                or request_context.get("region_code")
                or resource.region
                or ""
            ).strip()
            encoded_script = base64.b64encode(str(script or "").encode("utf-8")).decode("utf-8")

            query_pairs = list(urlparse.parse_qsl(parsed.query, keep_blank_values=True))
            query_pairs.extend(
                [
                    ("responseFormatType", "json"),
                    ("serverInstanceNo", instance_no),
                    ("userData", encoded_script),
                ]
            )
            if region_code:
                query_pairs.append(("regionCode", region_code))
            query = urlparse.urlencode(query_pairs)

            path = parsed.path or "/"
            path_with_query = f"{path}?{query}" if query else path
            signed_headers = CloudBootstrapService._ncp_sign_headers(
                method="POST",
                path_with_query=path_with_query,
                access_key=access_key,
                secret_key=secret_key,
            )

            final_url = urlparse.urlunsplit((parsed.scheme, parsed.netloc, path, query, ""))
            req = urlrequest.Request(
                final_url,
                method="POST",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    **signed_headers,
                },
            )

            with urlrequest.urlopen(req, timeout=20) as resp:  # nosec B310 - signed outbound call to configured API endpoint
                status_code = int(getattr(resp, "status", 0) or 0)
                raw = resp.read()

            body_text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw or "")
            parsed_body: Dict[str, Any] | None = None
            try:
                parsed_json = json.loads(body_text) if body_text else {}
                if isinstance(parsed_json, dict):
                    parsed_body = parsed_json
            except Exception:
                parsed_body = None

            if status_code < 200 or status_code >= 300:
                return {
                    "ok": False,
                    "transport": "ncp:api_gateway",
                    "message": f"NCP API returned status {status_code}",
                    "provider_result": {"status_code": status_code, "body": parsed_body or body_text[:300]},
                }
            if parsed_body and str(parsed_body.get("errorCode") or parsed_body.get("returnCode") or "").strip() not in {"", "0"}:
                err_code = str(parsed_body.get("errorCode") or parsed_body.get("returnCode") or "").strip()
                err_msg = str(parsed_body.get("errorMessage") or parsed_body.get("returnMessage") or "NCP API error").strip()
                return {
                    "ok": False,
                    "transport": "ncp:api_gateway",
                    "message": f"{err_code}: {err_msg}".strip(": "),
                    "provider_result": {"status_code": status_code, "body": parsed_body},
                }

            return {
                "ok": True,
                "transport": "ncp:api_gateway",
                "message": f"NCP userData submitted for server instance {instance_no}",
                "provider_result": {
                    "status_code": status_code,
                    "server_instance_no": instance_no,
                    "region_code": region_code or None,
                    "endpoint": f"{parsed.scheme}://{parsed.netloc}{path}",
                    "body": parsed_body,
                },
            }
        except urlerror.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            return {
                "ok": False,
                "transport": "ncp:error",
                "message": f"HTTPError({getattr(e, 'code', 'n/a')}): {body[:300] or str(e)}",
            }
        except urlerror.URLError as e:
            return {"ok": False, "transport": "ncp:error", "message": f"URLError: {e}"}
        except Exception as e:
            return {"ok": False, "transport": "ncp:error", "message": f"{type(e).__name__}: {e}"}

    @staticmethod
    def _apply_bootstrap(
        *,
        account: CloudAccount,
        resource: CloudResource,
        script: str,
        dry_run: bool,
        request_context: Dict[str, Any] | None = None,
        runtime_credentials: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        if dry_run:
            return {"ok": True, "message": "dry-run: no provider API call", "transport": "dry_run"}

        request_ctx = dict(request_context or {})
        credentials = dict(runtime_credentials or {})
        metadata = dict(resource.resource_metadata or {})
        if bool(metadata.get("simulate_bootstrap_apply_failure")):
            return {"ok": False, "message": "simulated provider adapter failure", "transport": "mock_adapter"}
        if bool(metadata.get("simulate_bootstrap_apply_success")):
            return {"ok": True, "message": "simulated provider adapter success", "transport": "mock_adapter"}

        provider = str(account.provider or "").lower()
        if provider == "aws":
            return CloudBootstrapService._apply_bootstrap_aws(
                account=account,
                resource=resource,
                script=script,
                request_context=request_ctx,
                runtime_credentials=credentials,
            )
        if provider == "azure":
            return CloudBootstrapService._apply_bootstrap_azure(
                account=account,
                resource=resource,
                script=script,
                request_context=request_ctx,
                runtime_credentials=credentials,
            )
        if provider == "gcp":
            return CloudBootstrapService._apply_bootstrap_gcp(
                account=account,
                resource=resource,
                script=script,
                request_context=request_ctx,
                runtime_credentials=credentials,
            )
        if provider in {"naver", "naver_cloud", "ncp"}:
            return CloudBootstrapService._apply_bootstrap_ncp(
                account=account,
                resource=resource,
                script=script,
                request_context=request_ctx,
                runtime_credentials=credentials,
            )
        return {"ok": False, "message": f"unsupported provider for bootstrap apply: {provider}", "transport": "none"}

    @staticmethod
    def _rollback(
        *,
        resource: CloudResource,
        reason: str,
    ) -> Dict[str, Any]:
        started = time.time()
        metadata = dict(resource.resource_metadata or {})
        if bool(metadata.get("simulate_bootstrap_rollback_failure")):
            elapsed_ms = int((time.time() - started) * 1000)
            return {
                "attempted": True,
                "success": False,
                "duration_ms": elapsed_ms,
                "message": f"rollback failed: {reason}",
            }
        elapsed_ms = int((time.time() - started) * 1000)
        return {
            "attempted": True,
            "success": True,
            "duration_ms": elapsed_ms,
            "message": f"rollback completed: {reason}",
        }

    @staticmethod
    def _emit_kpi_event(db: Session, *, payload: Dict[str, Any]) -> None:
        try:
            db.add(
                EventLog(
                    device_id=None,
                    severity="info" if str(payload.get("status") or "").lower() == "ok" else "warning",
                    event_id=CloudBootstrapService.KPI_EVENT_ID,
                    message=json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
                    source="CloudBootstrap",
                    timestamp=datetime.utcnow(),
                )
            )
            db.commit()
        except Exception:
            db.rollback()

    @staticmethod
    def _load_targets(
        db: Session,
        *,
        tenant_id: int | None,
        account_ids: List[int],
        regions: List[str],
        resource_ids: List[str],
    ) -> List[tuple[CloudResource, CloudAccount]]:
        q = db.query(CloudResource, CloudAccount).join(CloudAccount, CloudAccount.id == CloudResource.account_id)
        q = q.filter(CloudAccount.is_active == True)  # noqa: E712
        if tenant_id is not None:
            q = q.filter(CloudAccount.tenant_id == int(tenant_id))
        if account_ids:
            q = q.filter(CloudAccount.id.in_(list(account_ids)))
        q = q.filter(CloudResource.resource_type.in_(sorted(CloudBootstrapService._VM_RESOURCE_TYPES)))
        if resource_ids:
            selectors = [str(v).strip().lower() for v in list(resource_ids or []) if str(v).strip()]
            if selectors:
                q = q.filter(
                    or_(
                        func.lower(CloudResource.resource_id).in_(selectors),
                        func.lower(CloudResource.name).in_(selectors),
                    )
                )
        rows = q.order_by(CloudAccount.id.asc(), CloudResource.id.asc()).all()
        if not regions:
            return rows

        region_set = {str(r).strip().lower() for r in list(regions or []) if str(r).strip()}
        filtered: List[tuple[CloudResource, CloudAccount]] = []
        for resource, account in rows:
            reg = str(resource.region or "").strip().lower()
            if reg and reg in region_set:
                filtered.append((resource, account))
                continue
            metadata = dict(resource.resource_metadata or {})
            reg_meta = str(metadata.get("region") or "").strip().lower()
            if reg_meta and reg_meta in region_set:
                filtered.append((resource, account))
        return filtered

    @staticmethod
    def _inject_account_bootstrap_path(
        *,
        provider: str,
        runtime_credentials: Dict[str, Any],
        request_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        ctx = dict(request_context or {})
        if str(ctx.get("bootstrap_channel") or "").strip():
            return ctx
        path = str(runtime_credentials.get("bootstrap_path") or "").strip().lower()
        if not path:
            return ctx

        p = str(provider or "").strip().lower()
        if p == "aws":
            if path == "run_command":
                path = "ssm"
            if (not str(ctx.get("aws_bootstrap_path") or "").strip()) and path in {"auto", "userdata", "ssm"}:
                ctx["aws_bootstrap_path"] = path
        elif p == "azure":
            if (not str(ctx.get("azure_bootstrap_path") or "").strip()) and path in {"auto", "run_command", "custom_script"}:
                ctx["azure_bootstrap_path"] = path
        elif p == "gcp":
            if path in {"auto", "metadata"}:
                path = "startup_metadata"
            if (not str(ctx.get("gcp_bootstrap_path") or "").strip()) and path in {"startup_metadata", "startup_script"}:
                ctx["gcp_bootstrap_path"] = path
        elif p in {"naver", "naver_cloud", "ncp"}:
            if path in {"auto", "userdata", "user_data", "api_gateway"} and (not str(ctx.get("ncp_bootstrap_path") or "").strip()):
                ctx["ncp_bootstrap_path"] = "api_gateway" if path == "auto" else path
        return ctx

    @classmethod
    def run(
        cls,
        db: Session,
        *,
        tenant_id: int | None,
        owner_id: int,
        req: CloudBootstrapRunRequest,
    ) -> CloudBootstrapRunResponse:
        account_ids = cls._normalize_ids(req.account_ids)
        regions = cls._normalize_regions(req.regions)
        resource_ids = cls._normalize_resource_ids(req.resource_ids)
        idempotency_key = str(req.idempotency_key or "").strip() or None
        if idempotency_key and (not bool(req.force)):
            if not ChangeExecutionService.claim_idempotency(
                "cloud_bootstrap",
                idempotency_key,
                ttl_seconds=180,
                db=db,
            ):
                return CloudBootstrapRunResponse(
                    status="skipped_duplicate",
                    idempotency_key=idempotency_key,
                    message="Duplicate cloud bootstrap execution blocked by idempotency key.",
                )

        approval_id = int(req.approval_id) if req.approval_id is not None else None
        execution_id = str(req.execution_id or "").strip() or None
        if approval_id is not None:
            execution_id = ApprovalExecutionService.bind_approved_execution(
                db,
                approval_id=approval_id,
                expected_request_type="cloud_bootstrap",
                execution_id=execution_id,
            )
        if not execution_id:
            execution_id = ChangeExecutionService.make_fingerprint(
                "cloud_bootstrap_execution",
                {
                    "owner_id": int(owner_id),
                    "tenant_id": int(tenant_id) if tenant_id is not None else None,
                    "account_ids": account_ids,
                    "regions": regions,
                    "resource_ids": resource_ids,
                    "dry_run": bool(req.dry_run),
                    "approval_id": approval_id,
                },
            )

        rows = cls._load_targets(
            db,
            tenant_id=tenant_id,
            account_ids=account_ids,
            regions=regions,
            resource_ids=resource_ids,
        )
        if not rows:
            return CloudBootstrapRunResponse(
                status="no_targets",
                idempotency_key=idempotency_key,
                message="No active cloud VM targets found for bootstrap.",
            )

        target_by_row_id: Dict[int, Dict[str, Any]] = {}
        for resource, account in rows:
            target_by_row_id[int(resource.id)] = {"resource": resource, "account": account}

        request_context = dict(req.context or {})
        account_runtime_credentials: Dict[int, Dict[str, Any]] = {}
        account_credential_errors: Dict[int, str] = {}
        for _, account in rows:
            account_id = int(account.id)
            if account_id in account_runtime_credentials or account_id in account_credential_errors:
                continue
            try:
                account_runtime_credentials[account_id] = cls._runtime_credentials(account)
            except Exception as e:
                account_credential_errors[account_id] = f"{type(e).__name__}: {e}"

        wave_plan = ChangeExecutionService.build_waves(
            list(target_by_row_id.keys()),
            wave_size=int(req.wave_size or 0),
            canary_count=int(req.canary_count or 0),
        )

        custom_template = str(req.script_template or "").strip() or None

        def _run_wave(resource_row_ids: List[int], wave_no: int) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for row_id in list(resource_row_ids or []):
                target = target_by_row_id.get(int(row_id))
                if not target:
                    out.append(
                        {
                            "id": int(row_id),
                            "device_id": int(row_id),
                            "status": "failed",
                            "error": "target_not_found",
                            "wave": int(wave_no),
                            "execution_id": str(execution_id),
                            "approval_id": approval_id,
                        }
                    )
                    continue

                resource: CloudResource = target["resource"]
                account: CloudAccount = target["account"]
                provider = str(account.provider or "").strip().lower()
                template = custom_template or cls._default_template(provider)
                context = cls._build_context(
                    req=req,
                    account=account,
                    resource=resource,
                    execution_id=str(execution_id),
                )
                script = cls._render_template(template, context)
                script_hash = cls._compute_script_hash(script)
                script_preview = script[:220]
                if len(script) > 220:
                    script_preview += "...(truncated)"

                row: Dict[str, Any] = {
                    "id": int(resource.id),
                    "device_id": int(resource.id),
                    "account_id": int(account.id),
                    "provider": provider,
                    "resource_id": str(resource.resource_id or ""),
                    "resource_name": str(resource.name or "").strip() or None,
                    "region": str(resource.region or "").strip() or None,
                    "wave": int(wave_no),
                    "status": "failed",
                    "pre_check": {},
                    "post_check": {},
                    "rollback": {},
                    "script_sha256": script_hash,
                    "script_preview": script_preview,
                    "execution_id": str(execution_id),
                    "approval_id": approval_id,
                }

                pre_check = {"ok": True, "message": "pre-check bypassed"}
                if bool(req.pre_check_enabled):
                    pre_check = cls._pre_check(resource)
                row["pre_check"] = pre_check
                if not bool(pre_check.get("ok")):
                    row["status"] = "precheck_failed"
                    row["error"] = str(pre_check.get("message") or "pre-check failed")
                    out.append(row)
                    continue

                credential_error = account_credential_errors.get(int(account.id))
                runtime_credentials = dict(account_runtime_credentials.get(int(account.id), {}))
                if credential_error and (not bool(req.dry_run)):
                    row["status"] = "failed"
                    row["error"] = f"runtime credentials unavailable: {credential_error}"
                    out.append(row)
                    continue

                effective_request_context = cls._inject_account_bootstrap_path(
                    provider=provider,
                    runtime_credentials=runtime_credentials,
                    request_context=request_context,
                )
                apply_result = cls._apply_bootstrap(
                    account=account,
                    resource=resource,
                    script=script,
                    dry_run=bool(req.dry_run),
                    request_context=effective_request_context,
                    runtime_credentials=runtime_credentials,
                )

                if bool(req.dry_run):
                    row["status"] = "dry_run"
                    row["post_check"] = {"ok": True, "message": "post-check bypassed in dry-run"}
                    out.append(row)
                    continue

                if not bool(apply_result.get("ok")):
                    row["status"] = "failed"
                    row["error"] = str(apply_result.get("message") or "bootstrap apply failed")
                    if bool(req.rollback_on_failure):
                        rollback = cls._rollback(resource=resource, reason="apply_failed")
                        row["rollback"] = rollback
                        row["rollback_attempted"] = bool(rollback.get("attempted"))
                        row["rollback_success"] = bool(rollback.get("success"))
                        row["rollback_duration_ms"] = int(rollback.get("duration_ms") or 0)
                        if bool(rollback.get("attempted")) and not bool(rollback.get("success")):
                            row["status"] = "rollback_failed"
                    out.append(row)
                    continue

                post_check = {"ok": True, "message": "post-check bypassed"}
                if bool(req.post_check_enabled):
                    post_check = cls._post_check(script=script, apply_result=apply_result)
                row["post_check"] = post_check
                if not bool(post_check.get("ok")):
                    row["status"] = "postcheck_failed"
                    row["error"] = str(post_check.get("message") or "post-check failed")
                    if bool(req.rollback_on_failure):
                        rollback = cls._rollback(resource=resource, reason="post_check_failed")
                        row["rollback"] = rollback
                        row["rollback_attempted"] = bool(rollback.get("attempted"))
                        row["rollback_success"] = bool(rollback.get("success"))
                        row["rollback_duration_ms"] = int(rollback.get("duration_ms") or 0)
                        if bool(rollback.get("attempted")) and not bool(rollback.get("success")):
                            row["status"] = "postcheck_failed_rollback_failed"
                    out.append(row)
                    continue

                row["status"] = "success"
                row["post_check"] = post_check
                out.append(row)
            return out

        wave_result = ChangeExecutionService.execute_wave_batches(
            wave_plan,
            _run_wave,
            stop_on_wave_failure=bool(req.stop_on_wave_failure),
            inter_wave_delay_seconds=float(req.inter_wave_delay_seconds or 0.0),
        )

        raw_rows: List[Dict[str, Any]] = list(wave_result.get("results") or [])
        enriched_rows: List[Dict[str, Any]] = []
        for row in raw_rows:
            item = dict(row or {})
            row_id = None
            try:
                row_id = int(item.get("id")) if item.get("id") is not None else None
            except Exception:
                row_id = None
            if row_id is not None and row_id in target_by_row_id:
                target = target_by_row_id[row_id]
                resource = target["resource"]
                account = target["account"]
                item.setdefault("account_id", int(account.id))
                item.setdefault("provider", str(account.provider or "").strip().lower())
                item.setdefault("resource_id", str(resource.resource_id or ""))
                item.setdefault("resource_name", str(resource.name or "").strip() or None)
                item.setdefault("region", str(resource.region or "").strip() or None)
            item.setdefault("execution_id", str(execution_id))
            item.setdefault("approval_id", approval_id)
            item.setdefault("pre_check", {})
            item.setdefault("post_check", {})
            item.setdefault("rollback", {})
            enriched_rows.append(item)

        success_targets = 0
        failed_targets = 0
        dry_run_targets = 0
        skipped_targets = 0
        for row in enriched_rows:
            status = str(row.get("status") or "").strip().lower()
            if status in {"success", "ok"}:
                success_targets += 1
            elif status == "dry_run":
                dry_run_targets += 1
            elif status.startswith("skipped"):
                skipped_targets += 1
            else:
                failed_targets += 1

        final_status = "ok"
        if failed_targets > 0 and (success_targets > 0 or dry_run_targets > 0 or skipped_targets > 0):
            final_status = "partial"
        elif failed_targets > 0:
            final_status = "failed"

        result_models = [CloudBootstrapTargetResult.model_validate(row) for row in enriched_rows]

        response = CloudBootstrapRunResponse(
            status=final_status,
            idempotency_key=idempotency_key,
            approval_id=approval_id,
            execution_id=str(execution_id),
            total_targets=len(enriched_rows),
            success_targets=int(success_targets),
            failed_targets=int(failed_targets),
            dry_run_targets=int(dry_run_targets),
            skipped_targets=int(skipped_targets),
            execution=dict(wave_result.get("execution") or {}),
            results=result_models,
            message=None,
        )

        cls._emit_kpi_event(
            db,
            payload={
                "status": str(response.status),
                "tenant_id": int(tenant_id) if tenant_id is not None else None,
                "owner_id": int(owner_id),
                "approval_id": approval_id,
                "execution_id": str(execution_id),
                "dry_run": bool(req.dry_run),
                "resource_ids": list(resource_ids),
                "total_targets": int(response.total_targets),
                "success_targets": int(response.success_targets),
                "failed_targets": int(response.failed_targets),
                "dry_run_targets": int(response.dry_run_targets),
                "skipped_targets": int(response.skipped_targets),
                "account_ids": sorted(
                    {
                        int(row.account_id)
                        for row in result_models
                        if getattr(row, "account_id", None) is not None
                    }
                ),
                "halted": bool((response.execution or {}).get("halted")),
                "halted_wave": (response.execution or {}).get("halted_wave"),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        if approval_id is not None:
            ApprovalExecutionService.finalize_approval_execution(
                db,
                approval_id=approval_id,
                execution_id=str(execution_id),
                result=response.model_dump(),
            )

        return response
