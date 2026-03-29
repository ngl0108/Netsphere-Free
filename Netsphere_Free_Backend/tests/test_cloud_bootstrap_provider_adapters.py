import base64
import sys
import types

from app.models.cloud import CloudAccount, CloudResource
from app.services import cloud_bootstrap_service as bootstrap_module
from app.services.cloud_bootstrap_service import CloudBootstrapService


class _FakeEC2Client:
    def __init__(self):
        self.calls = []

    def modify_instance_attribute(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


class _FakeSSMClient:
    def __init__(self):
        self.calls = []

    def send_command(self, **kwargs):
        self.calls.append(dict(kwargs))
        return {"Command": {"CommandId": "cmd-12345"}}


class _FakeAWSSession:
    def __init__(self, ec2_client, ssm_client):
        self._ec2_client = ec2_client
        self._ssm_client = ssm_client

    def client(self, name):
        if name == "ec2":
            return self._ec2_client
        if name == "ssm":
            return self._ssm_client
        raise AssertionError(f"unexpected aws client requested: {name}")


def test_apply_bootstrap_aws_userdata_path(monkeypatch):
    ec2 = _FakeEC2Client()
    ssm = _FakeSSMClient()
    fake_session = _FakeAWSSession(ec2, ssm)
    monkeypatch.setattr(CloudBootstrapService, "_aws_session", staticmethod(lambda *_args, **_kwargs: fake_session))

    account = CloudAccount(id=11, provider="aws", credentials={})
    resource = CloudResource(
        account_id=11,
        resource_id="i-abc123456789",
        resource_type="virtual_machine",
        name="vm-userdata",
        region="ap-northeast-2",
        state="running",
        resource_metadata={"ssm_managed": False},
    )
    script = "#!/bin/bash\necho userdata"

    result = CloudBootstrapService._apply_bootstrap_aws(
        account=account,
        resource=resource,
        script=script,
        request_context={"aws_bootstrap_path": "userdata"},
        runtime_credentials={"access_key": "AK", "secret_key": "SK", "region": "ap-northeast-2"},
    )

    assert bool(result.get("ok")) is True
    assert str(result.get("transport")) == "aws:user_data"
    assert len(ec2.calls) == 1
    sent = ec2.calls[0]
    assert str(sent.get("InstanceId")) == "i-abc123456789"
    encoded = str((sent.get("UserData") or {}).get("Value") or "")
    decoded = base64.b64decode(encoded.encode("utf-8")).decode("utf-8")
    assert decoded == script
    assert len(ssm.calls) == 0


def test_apply_bootstrap_aws_ssm_path_auto(monkeypatch):
    ec2 = _FakeEC2Client()
    ssm = _FakeSSMClient()
    fake_session = _FakeAWSSession(ec2, ssm)
    monkeypatch.setattr(CloudBootstrapService, "_aws_session", staticmethod(lambda *_args, **_kwargs: fake_session))

    account = CloudAccount(id=12, provider="aws", credentials={})
    resource = CloudResource(
        account_id=12,
        resource_id="i-def987654321",
        resource_type="virtual_machine",
        name="vm-ssm",
        region="ap-northeast-2",
        state="running",
        resource_metadata={"ssm_managed": True},
    )
    script = "#!/bin/bash\necho ssm"

    result = CloudBootstrapService._apply_bootstrap_aws(
        account=account,
        resource=resource,
        script=script,
        request_context={"bootstrap_channel": "auto"},
        runtime_credentials={"access_key": "AK", "secret_key": "SK", "region": "ap-northeast-2"},
    )

    assert bool(result.get("ok")) is True
    assert str(result.get("transport")) == "aws:ssm"
    assert len(ssm.calls) == 1
    sent = ssm.calls[0]
    assert str(sent.get("DocumentName")) == "AWS-RunShellScript"
    params = dict(sent.get("Parameters") or {})
    commands = list(params.get("commands") or [])
    assert "cat > /tmp/netmanager-bootstrap.sh <<'EOF'" in commands
    assert "bash /tmp/netmanager-bootstrap.sh" in commands
    assert "#!/bin/bash" in commands
    assert "echo ssm" in commands
    assert str(((result.get("provider_result") or {}).get("command_id") or "")) == "cmd-12345"
    assert len(ec2.calls) == 0


def test_apply_bootstrap_azure_run_command_path(monkeypatch):
    calls = {}

    class _FakeCredential:
        def __init__(self, tenant_id, client_id, client_secret):
            calls["credential"] = {
                "tenant_id": tenant_id,
                "client_id": client_id,
                "client_secret": client_secret,
            }

    class _FakeRunCommandInput:
        def __init__(self, command_id=None, script=None):
            self.command_id = command_id
            self.script = script or []

    class _FakePoller:
        def __init__(self, payload):
            self._payload = payload

        def result(self, timeout=None):
            calls["timeout"] = timeout
            return self._payload

    class _FakeVirtualMachines:
        def begin_run_command(self, resource_group, vm_name, run_input):
            calls["run_command"] = {
                "resource_group": resource_group,
                "vm_name": vm_name,
                "command_id": run_input.command_id,
                "script": list(run_input.script or []),
            }
            return _FakePoller({"status": "ok"})

    class _FakeVirtualMachineExtensions:
        def begin_create_or_update(self, *_args, **_kwargs):
            raise AssertionError("custom_script path should not be used in this test")

    class _FakeComputeClient:
        def __init__(self, _credential, subscription_id):
            calls["subscription_id"] = subscription_id
            self.virtual_machines = _FakeVirtualMachines()
            self.virtual_machine_extensions = _FakeVirtualMachineExtensions()

    azure_mod = types.ModuleType("azure")
    azure_identity = types.ModuleType("azure.identity")
    azure_identity.ClientSecretCredential = _FakeCredential
    azure_mgmt = types.ModuleType("azure.mgmt")
    azure_compute = types.ModuleType("azure.mgmt.compute")
    azure_compute.ComputeManagementClient = _FakeComputeClient
    azure_compute_models = types.ModuleType("azure.mgmt.compute.models")
    azure_compute_models.RunCommandInput = _FakeRunCommandInput
    azure_compute.models = azure_compute_models
    azure_mgmt.compute = azure_compute
    azure_mod.identity = azure_identity
    azure_mod.mgmt = azure_mgmt

    monkeypatch.setitem(sys.modules, "azure", azure_mod)
    monkeypatch.setitem(sys.modules, "azure.identity", azure_identity)
    monkeypatch.setitem(sys.modules, "azure.mgmt", azure_mgmt)
    monkeypatch.setitem(sys.modules, "azure.mgmt.compute", azure_compute)
    monkeypatch.setitem(sys.modules, "azure.mgmt.compute.models", azure_compute_models)

    account = CloudAccount(id=21, provider="azure", credentials={})
    resource = CloudResource(
        account_id=21,
        resource_id="/subscriptions/sub-123/resourceGroups/rg-a/providers/Microsoft.Compute/virtualMachines/vm-a",
        resource_type="virtual_machine",
        name="vm-a",
        region="koreacentral",
        state="running",
        resource_metadata={},
    )
    script = "#!/bin/bash\necho azure"

    result = CloudBootstrapService._apply_bootstrap_azure(
        account=account,
        resource=resource,
        script=script,
        request_context={"azure_bootstrap_path": "run_command"},
        runtime_credentials={
            "tenant_id": "tenant-1",
            "client_id": "client-1",
            "client_secret": "secret-1",
            "subscription_id": "sub-123",
        },
    )

    assert bool(result.get("ok")) is True
    assert str(result.get("transport")) == "azure:run_command"
    assert str(calls.get("subscription_id")) == "sub-123"
    run = dict(calls.get("run_command") or {})
    assert str(run.get("resource_group")) == "rg-a"
    assert str(run.get("vm_name")) == "vm-a"
    assert str(run.get("command_id")) == "RunShellScript"
    assert "#!/bin/bash" in list(run.get("script") or [])
    assert "echo azure" in list(run.get("script") or [])


def test_apply_bootstrap_azure_custom_script_path(monkeypatch):
    calls = {}

    class _FakeCredential:
        def __init__(self, *_args, **_kwargs):
            pass

    class _FakeRunCommandInput:
        def __init__(self, *_args, **_kwargs):
            pass

    class _FakePoller:
        def __init__(self, payload):
            self._payload = payload

        def result(self, timeout=None):
            calls["timeout"] = timeout
            return self._payload

    class _FakeVirtualMachines:
        def begin_run_command(self, *_args, **_kwargs):
            raise AssertionError("run_command path should not be used in this test")

    class _FakeVirtualMachineExtensions:
        def begin_create_or_update(self, resource_group, vm_name, extension_name, ext_params):
            calls["custom_script"] = {
                "resource_group": resource_group,
                "vm_name": vm_name,
                "extension_name": extension_name,
                "ext_params": dict(ext_params or {}),
            }
            return _FakePoller({"status": "ok"})

    class _FakeComputeClient:
        def __init__(self, _credential, _subscription_id):
            self.virtual_machines = _FakeVirtualMachines()
            self.virtual_machine_extensions = _FakeVirtualMachineExtensions()

    azure_mod = types.ModuleType("azure")
    azure_identity = types.ModuleType("azure.identity")
    azure_identity.ClientSecretCredential = _FakeCredential
    azure_mgmt = types.ModuleType("azure.mgmt")
    azure_compute = types.ModuleType("azure.mgmt.compute")
    azure_compute.ComputeManagementClient = _FakeComputeClient
    azure_compute_models = types.ModuleType("azure.mgmt.compute.models")
    azure_compute_models.RunCommandInput = _FakeRunCommandInput
    azure_compute.models = azure_compute_models
    azure_mgmt.compute = azure_compute
    azure_mod.identity = azure_identity
    azure_mod.mgmt = azure_mgmt

    monkeypatch.setitem(sys.modules, "azure", azure_mod)
    monkeypatch.setitem(sys.modules, "azure.identity", azure_identity)
    monkeypatch.setitem(sys.modules, "azure.mgmt", azure_mgmt)
    monkeypatch.setitem(sys.modules, "azure.mgmt.compute", azure_compute)
    monkeypatch.setitem(sys.modules, "azure.mgmt.compute.models", azure_compute_models)

    account = CloudAccount(id=22, provider="azure", credentials={})
    resource = CloudResource(
        account_id=22,
        resource_id="/subscriptions/sub-123/resourceGroups/rg-b/providers/Microsoft.Compute/virtualMachines/vm-b",
        resource_type="virtual_machine",
        name="vm-b",
        region="koreacentral",
        state="running",
        resource_metadata={},
    )

    result = CloudBootstrapService._apply_bootstrap_azure(
        account=account,
        resource=resource,
        script="#!/bin/bash\necho custom-script",
        request_context={"azure_bootstrap_path": "custom_script"},
        runtime_credentials={
            "tenant_id": "tenant-1",
            "client_id": "client-1",
            "client_secret": "secret-1",
            "subscription_id": "sub-123",
        },
    )

    assert bool(result.get("ok")) is True
    assert str(result.get("transport")) == "azure:custom_script"
    custom = dict(calls.get("custom_script") or {})
    assert str(custom.get("resource_group")) == "rg-b"
    assert str(custom.get("vm_name")) == "vm-b"
    params = dict(custom.get("ext_params") or {})
    assert str(params.get("virtual_machine_extension_type")) == "CustomScript"
    command = str(dict(params.get("settings") or {}).get("commandToExecute") or "")
    assert "/tmp/netmanager-bootstrap.sh" in command


def test_apply_bootstrap_gcp_startup_metadata_path(monkeypatch):
    calls = {}

    class _FakeCredentialsBuilder:
        @staticmethod
        def from_service_account_info(info):
            calls["service_account_info"] = dict(info or {})
            return {"cred": "ok"}

    class _FakeMetadataItem:
        def __init__(self, key="", value=""):
            self.key = key
            self.value = value

    class _FakeInstanceMetadata:
        def __init__(self):
            self.fingerprint = "fp-001"
            self.items = [_FakeMetadataItem(key="env", value="test"), _FakeMetadataItem(key="startup-script", value="old")]

    class _FakeInstance:
        def __init__(self):
            self.metadata = _FakeInstanceMetadata()

    class _FakeOperation:
        def __init__(self):
            self.name = "op-123"

    class _FakeInstancesClient:
        def __init__(self, credentials=None):
            calls["client_credentials"] = credentials

        def get(self, *, project, zone, instance):
            calls["get"] = {"project": project, "zone": zone, "instance": instance}
            return _FakeInstance()

        def set_metadata(self, *, project, zone, instance, metadata_resource):
            calls["set"] = {
                "project": project,
                "zone": zone,
                "instance": instance,
                "items": list(getattr(metadata_resource, "items", []) or []),
                "fingerprint": str(getattr(metadata_resource, "fingerprint", "") or ""),
            }
            return _FakeOperation()

    class _FakeMetadata:
        def __init__(self, fingerprint="", items=None):
            self.fingerprint = fingerprint
            self.items = list(items or [])

    google_mod = types.ModuleType("google")
    google_cloud = types.ModuleType("google.cloud")
    google_compute_v1 = types.ModuleType("google.cloud.compute_v1")
    google_compute_v1.InstancesClient = _FakeInstancesClient
    google_compute_v1.Metadata = _FakeMetadata
    google_oauth2 = types.ModuleType("google.oauth2")
    google_service_account = types.ModuleType("google.oauth2.service_account")
    google_service_account.Credentials = _FakeCredentialsBuilder
    google_cloud.compute_v1 = google_compute_v1
    google_oauth2.service_account = google_service_account
    google_mod.cloud = google_cloud
    google_mod.oauth2 = google_oauth2

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.cloud", google_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.compute_v1", google_compute_v1)
    monkeypatch.setitem(sys.modules, "google.oauth2", google_oauth2)
    monkeypatch.setitem(sys.modules, "google.oauth2.service_account", google_service_account)

    account = CloudAccount(id=31, provider="gcp", credentials={})
    resource = CloudResource(
        account_id=31,
        resource_id="projects/proj-a/zones/asia-northeast3-a/instances/vm-gcp",
        resource_type="virtual_machine",
        name="vm-gcp",
        region="asia-northeast3-a",
        state="running",
        resource_metadata={},
    )
    script = "#!/bin/bash\necho gcp"

    result = CloudBootstrapService._apply_bootstrap_gcp(
        account=account,
        resource=resource,
        script=script,
        request_context={"gcp_bootstrap_path": "auto"},
        runtime_credentials={
            "project_id": "proj-a",
            "service_account_json": {"type": "service_account", "project_id": "proj-a"},
        },
    )

    assert bool(result.get("ok")) is True
    assert str(result.get("transport")) == "gcp:startup_metadata"
    set_call = dict(calls.get("set") or {})
    assert str(set_call.get("project")) == "proj-a"
    assert str(set_call.get("zone")) == "asia-northeast3-a"
    assert str(set_call.get("instance")) == "vm-gcp"
    items = list(set_call.get("items") or [])
    startup = [it for it in items if str(it.get("key")) == "startup-script"]
    assert startup
    assert str(startup[0].get("value")) == script


def test_apply_bootstrap_ncp_api_gateway_path(monkeypatch):
    captured = {}

    class _FakeResponse:
        def __init__(self, status=200, payload=None):
            self.status = status
            self._payload = payload or {"returnCode": "0", "returnMessage": "success"}

        def read(self):
            import json

            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.headers or {})
        captured["method"] = req.get_method()
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(bootstrap_module.urlrequest, "urlopen", _fake_urlopen)

    account = CloudAccount(id=41, provider="naver", credentials={})
    resource = CloudResource(
        account_id=41,
        resource_id="server-1234567",
        resource_type="virtual_machine",
        name="ncp-vm-a",
        region="KR",
        state="running",
        resource_metadata={"server_instance_no": "1234567"},
    )

    result = CloudBootstrapService._apply_bootstrap_ncp(
        account=account,
        resource=resource,
        script="#!/bin/bash\necho ncp",
        request_context={},
        runtime_credentials={"access_key": "NCP_AK", "secret_key": "NCP_SK", "region_code": "KR"},
    )

    assert bool(result.get("ok")) is True
    assert str(result.get("transport")) == "ncp:api_gateway"
    assert str(captured.get("method")) == "POST"
    assert "serverInstanceNo=1234567" in str(captured.get("url"))
    assert "userData=" in str(captured.get("url"))
    hdr = {str(k).lower(): str(v) for k, v in dict(captured.get("headers") or {}).items()}
    assert "x-ncp-apigw-timestamp" in hdr
    assert "x-ncp-iam-access-key" in hdr
    assert "x-ncp-apigw-signature-v2" in hdr


def test_apply_bootstrap_ncp_requires_credentials():
    account = CloudAccount(id=42, provider="ncp", credentials={})
    resource = CloudResource(
        account_id=42,
        resource_id="1234567",
        resource_type="virtual_machine",
        name="ncp-vm-b",
        region="KR",
        state="running",
        resource_metadata={},
    )

    result = CloudBootstrapService._apply_bootstrap_ncp(
        account=account,
        resource=resource,
        script="#!/bin/bash\necho ncp",
        request_context={},
        runtime_credentials={},
    )

    assert bool(result.get("ok")) is False
    assert str(result.get("transport")).startswith("ncp:")
    assert "Missing NCP access_key/secret_key" in str(result.get("message"))
