import json
import sys
from pathlib import Path

from app.models.cloud import CloudAccount, CloudResource
from app.models.settings import SystemSetting
from app.services import intent_service as intent_service_mod


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def _set_setting(db, key: str, value: str, category: str = "system"):
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        row = SystemSetting(key=key, value=str(value), description=key, category=category)
    else:
        row.value = str(value)
        row.category = category
    db.add(row)
    db.commit()
    return row


def test_intent_validate_blocked_when_feature_disabled(client, operator_user_token):
    res = client.post(
        "/api/v1/intent/validate",
        json={
            "intent_type": "segment",
            "name": "seg-a",
            "spec": {"segments": [{"name": "corp", "cidrs": ["10.0.0.0/24"]}]},
        },
        headers=operator_user_token,
    )
    assert res.status_code == 403


def test_intent_validate_segment_success_when_enabled(client, operator_user_token, db):
    _set_setting(db, "intent_engine_enabled", "true")
    res = client.post(
        "/api/v1/intent/validate",
        json={
            "intent_type": "segment",
            "name": "corp-seg",
            "spec": {"segments": [{"name": "corp", "cidrs": ["10.0.0.0/24"]}]},
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["valid"] is True
    assert body["normalized_intent"]["intent_type"] == "segment"
    assert body["normalized_intent"]["spec"]["segments"][0]["cidrs"][0] == "10.0.0.0/24"


def test_intent_simulate_access_policy_detects_conflict(client, operator_user_token, db):
    _set_setting(db, "intent_engine_enabled", "true")
    res = client.post(
        "/api/v1/intent/simulate",
        json={
            "intent_type": "access_policy",
            "name": "acl-main",
            "spec": {
                "rules": [
                    {
                        "name": "allow-web",
                        "action": "permit",
                        "sources": ["segA"],
                        "destinations": ["segB"],
                        "protocols": ["tcp"],
                        "ports": [443],
                    },
                    {
                        "name": "deny-web",
                        "action": "deny",
                        "sources": ["segA"],
                        "destinations": ["segB"],
                        "protocols": ["tcp"],
                        "ports": [443],
                    },
                ]
            },
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    validation = body["validation"]
    assert validation["valid"] is True
    assert len(validation["conflicts"]) >= 1
    assert int(body["risk_score"]) >= 60
    assert body["apply_eligible"] is False


def test_intent_validate_cloud_policy_success_when_enabled(client, operator_user_token, db):
    _set_setting(db, "intent_engine_enabled", "true")
    res = client.post(
        "/api/v1/intent/validate",
        json={
            "intent_type": "cloud_policy",
            "name": "cloud-guardrail-main",
            "spec": {
                "targets": {"providers": ["aws", "ncp"], "regions": ["ap-northeast-2"]},
                "required_tags": [{"key": "owner"}, {"key": "env", "value": "prod"}],
                "blocked_ingress_cidrs": ["0.0.0.0/0"],
                "protected_route_destinations": ["0.0.0.0/0"],
            },
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["valid"] is True
    normalized = body["normalized_intent"]
    assert normalized["intent_type"] == "cloud_policy"
    assert "cloud_policy" in list(body.get("supported_intents") or [])
    assert list(normalized["spec"]["targets"]["providers"]) == ["aws", "ncp"]
    assert list(normalized["spec"]["blocked_ingress_cidrs"]) == ["0.0.0.0/0"]


def test_intent_simulate_cloud_policy_scopes_resources(client, operator_user_token, db):
    _set_setting(db, "intent_engine_enabled", "true")

    aws = CloudAccount(
        name="aws-prod",
        provider="aws",
        credentials={"auth_type": "access_key", "region": "ap-northeast-2"},
        is_active=True,
        tenant_id=None,
    )
    azure = CloudAccount(
        name="azure-ignored",
        provider="azure",
        credentials={"tenant_id": "t", "client_id": "c", "client_secret": "s"},
        is_active=True,
        tenant_id=None,
    )
    db.add(aws)
    db.add(azure)
    db.flush()

    db.add(
        CloudResource(
            account_id=int(aws.id),
            resource_id="i-001",
            resource_type="instance",
            name="vm-a",
            region="ap-northeast-2",
            cidr_block=None,
            resource_metadata={"tags": {"env": "prod", "owner": "netops"}},
            state="running",
        )
    )
    db.add(
        CloudResource(
            account_id=int(aws.id),
            resource_id="sg-001",
            resource_type="security_group",
            name="sg-a",
            region="ap-northeast-2",
            cidr_block=None,
            resource_metadata={"tags": {"env": "prod"}},
            state="active",
        )
    )
    db.add(
        CloudResource(
            account_id=int(aws.id),
            resource_id="rtb-001",
            resource_type="route_table",
            name="rtb-a",
            region="ap-northeast-2",
            cidr_block=None,
            resource_metadata={"tags": {"env": "dev"}},
            state="active",
        )
    )
    db.add(
        CloudResource(
            account_id=int(azure.id),
            resource_id="vm-ignored",
            resource_type="vm",
            name="vm-ignored",
            region="koreacentral",
            cidr_block=None,
            resource_metadata={"tags": {"env": "prod", "owner": "secops"}},
            state="running",
        )
    )
    db.commit()

    res = client.post(
        "/api/v1/intent/simulate",
        json={
            "intent_type": "cloud_policy",
            "name": "cloud-guardrail-sim",
            "spec": {
                "targets": {
                    "providers": ["aws"],
                    "account_ids": [int(aws.id)],
                    "regions": ["ap-northeast-2"],
                },
                "required_tags": [{"key": "owner"}],
                "blocked_ingress_cidrs": ["0.0.0.0/0"],
                "protected_route_destinations": ["0.0.0.0/0"],
            },
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    validation = body["validation"]
    assert validation["valid"] is True
    assert body["blast_radius"]["estimated_devices"] == 1
    assert body["blast_radius"]["estimated_rules"] == 3
    cloud_scope = body.get("cloud_scope") or {}
    assert int(cloud_scope.get("scoped_resources") or 0) == 3
    assert int(cloud_scope.get("missing_required_tags") or 0) == 2
    tf_preview = body.get("terraform_plan_preview") or {}
    assert tf_preview.get("engine") == "terraform"
    assert str(tf_preview.get("workspace_prefix") or "").startswith("netsphere-")
    assert int((tf_preview.get("summary") or {}).get("providers") or 0) == 1
    assert (tf_preview.get("summary") or {}).get("narrow_scope_ready") is True
    assert len(list(tf_preview.get("plan_lines") or [])) >= 1
    blocks = list(tf_preview.get("change_blocks") or [])
    assert len(blocks) == 1
    assert blocks[0].get("provider") == "aws"
    assert "verification_checks" in blocks[0]
    assert "evidence_artifacts" in blocks[0]
    assert len(list((tf_preview.get("post_check_plan") or {}).get("steps") or [])) >= 2
    assert "runner-result.json" in list((tf_preview.get("evidence_plan") or {}).get("artifacts") or [])
    guardrails = body.get("operational_guardrails") or {}
    assert int((guardrails.get("summary") or {}).get("scoped_accounts") or 0) == 1
    assert int((guardrails.get("summary") or {}).get("warning_findings") or 0) >= 1
    assert any(str(item.get("key") or "") == "public_ingress" for item in list(guardrails.get("findings") or []))
    assert len(list(guardrails.get("account_modes") or [])) == 1
    pre_check = body.get("pre_check") or {}
    assert (pre_check.get("rule_pack") or {}).get("name") == "Digital Twin Lite"
    assert int((pre_check.get("summary") or {}).get("checks_run") or 0) >= 5
    assert int((pre_check.get("summary") or {}).get("blockers") or 0) >= 1
    assert any(str(item.get("key") or "") == "default_route" for item in list(pre_check.get("findings") or []))
    compare = body.get("before_after_compare") or {}
    compare_summary = compare.get("summary") or {}
    compare_cards = list(compare.get("cards") or [])
    assert compare_summary.get("result") in {"blocked", "review", "ready"}
    assert int(compare_summary.get("cards") or 0) >= 4
    assert any(str(item.get("key") or "") == "scope_discipline" for item in compare_cards)
    summary = " | ".join(list(body.get("change_summary") or []))
    assert "cloud_scope resources=3" in summary


def test_intent_simulate_cloud_policy_marks_empty_scope_as_precheck_blocker(client, operator_user_token, db):
    _set_setting(db, "intent_engine_enabled", "true")

    aws = CloudAccount(
        name="aws-empty",
        provider="aws",
        credentials={"auth_type": "access_key", "region": "ap-northeast-2"},
        is_active=True,
        tenant_id=None,
    )
    db.add(aws)
    db.commit()

    res = client.post(
        "/api/v1/intent/simulate",
        json={
            "intent_type": "cloud_policy",
            "name": "cloud-empty-scope",
            "spec": {
                "targets": {
                    "providers": ["aws"],
                    "account_ids": [int(aws.id)],
                    "regions": ["ap-northeast-2"],
                    "resource_types": ["security_group"],
                },
                "required_tags": [{"key": "owner"}],
            },
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    pre_check = body.get("pre_check") or {}
    summary = pre_check.get("summary") or {}
    findings = list(pre_check.get("findings") or [])
    compare = body.get("before_after_compare") or {}
    compare_cards = list(compare.get("cards") or [])

    assert summary.get("result") == "block"
    assert summary.get("blocking") is True
    assert int(summary.get("blockers") or 0) >= 1
    assert any(str(item.get("key") or "") == "empty_scope" for item in findings)
    assert any(
        str(item.get("key") or "") == "scope_discipline" and str(item.get("status") or "") == "blocked"
        for item in compare_cards
    )
    assert body.get("apply_eligible") is False


def test_intent_apply_requires_approval_for_live_mode(client, operator_user_token, db):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "intent_apply_requires_approval", "true")
    res = client.post(
        "/api/v1/intent/apply",
        json={
            "intent_type": "segment",
            "name": "seg-live",
            "dry_run": False,
            "idempotency_key": "intent-live-need-approval",
            "spec": {"segments": [{"name": "live", "cidrs": ["10.10.0.0/24"]}]},
        },
        headers=operator_user_token,
    )
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["status"] == "approval_required"
    assert body["required"] is True


def test_intent_apply_with_approval_persists_and_dedupes(client, operator_user_token, db):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "intent_apply_requires_approval", "true")
    payload = {
        "intent_type": "segment",
        "name": "seg-prod",
        "dry_run": False,
        "approval_id": 7001,
        "idempotency_key": "intent-apply-7001",
        "spec": {"segments": [{"name": "prod", "cidrs": ["10.20.0.0/24"]}]},
    }

    first = client.post("/api/v1/intent/apply", json=payload, headers=operator_user_token)
    assert first.status_code == 200
    first_body = _unwrap(first.json())
    assert first_body["status"] == "applied"
    execution_id = str(first_body.get("execution_id") or "").strip()
    assert execution_id != ""

    key = f"intent_v1_execution:{execution_id}"
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    assert row is not None
    saved = json.loads(str(row.value))
    assert int(saved.get("approval_id")) == 7001
    assert str(saved.get("intent_type")) == "segment"

    second = client.post("/api/v1/intent/apply", json=payload, headers=operator_user_token)
    assert second.status_code == 200
    second_body = _unwrap(second.json())
    assert second_body["status"] == "skipped_idempotent"
    assert str(second_body.get("execution_id") or "").strip() == execution_id


def test_intent_status_exposes_apply_execute_actions_flag(client, normal_user_token):
    res = client.get("/api/v1/intent/status", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body.get("apply_execute_actions_enabled") is False
    assert body.get("northbound_policy_enabled") is False
    assert int(body.get("northbound_max_auto_publish_risk_score") or 0) == 30


def test_intent_status_reports_cloud_execution_readiness(client, normal_user_token, monkeypatch):
    monkeypatch.setenv("NETSPHERE_CLOUD_INTENT_LIVE_APPLY_ENABLED", "true")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_EXECUTION_MODE", "real_apply")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_STATE_BACKEND", "s3")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_STATE_S3_BUCKET", "")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_STATE_S3_REGION", "ap-northeast-2")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_BIN", sys.executable)

    res = client.get("/api/v1/intent/status", headers=normal_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    readiness = body.get("cloud_execution_readiness") or {}

    assert readiness.get("mode") == "real_apply"
    assert readiness.get("live_apply_enabled") is True
    assert readiness.get("ready_for_real_apply") is False
    assert (readiness.get("backend_validation") or {}).get("backend") == "s3"
    assert (readiness.get("backend_validation") or {}).get("valid") is False
    assert any("s3 backend requires bucket" in str(item) for item in list(readiness.get("errors") or []))
    assert (readiness.get("terraform_runtime") or {}).get("available") is True


def test_intent_apply_northbound_policy_requires_approval_when_risky(client, operator_user_token, db):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "intent_apply_requires_approval", "false")
    _set_setting(db, "intent_northbound_policy_enabled", "true")
    _set_setting(db, "intent_northbound_max_auto_publish_risk_score", "20")

    payload = {
        "intent_type": "access_policy",
        "name": "acl-risky",
        "dry_run": False,
        "idempotency_key": "intent-nb-risky-approval",
        "spec": {
            "rules": [
                {
                    "name": "allow-web",
                    "action": "permit",
                    "sources": ["segA"],
                    "destinations": ["segB"],
                    "protocols": ["tcp"],
                    "ports": [443],
                },
                {
                    "name": "deny-web",
                    "action": "deny",
                    "sources": ["segA"],
                    "destinations": ["segB"],
                    "protocols": ["tcp"],
                    "ports": [443],
                },
            ]
        },
        "metadata": {
            "execution_actions": [
                {"type": "webhook", "payload": {"title": "intent risky publish"}},
            ]
        },
    }

    res = client.post("/api/v1/intent/apply", json=payload, headers=operator_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["status"] == "approval_required"
    assert body.get("required_for") == "northbound_publish"
    nb = body.get("northbound_publish") or {}
    assert nb.get("enabled") is True
    assert nb.get("decision") == "approval_gated"
    assert nb.get("requires_approval") is True


def test_intent_apply_northbound_policy_allows_with_approval_id(client, operator_user_token, db):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "intent_apply_requires_approval", "false")
    _set_setting(db, "intent_northbound_policy_enabled", "true")
    _set_setting(db, "intent_northbound_max_auto_publish_risk_score", "20")
    _set_setting(db, "intent_apply_execute_actions", "false")

    payload = {
        "intent_type": "access_policy",
        "name": "acl-risky-approved",
        "dry_run": False,
        "approval_id": 9001,
        "idempotency_key": "intent-nb-risky-approved",
        "spec": {
            "rules": [
                {
                    "name": "allow-web",
                    "action": "permit",
                    "sources": ["segA"],
                    "destinations": ["segB"],
                    "protocols": ["tcp"],
                    "ports": [443],
                },
                {
                    "name": "deny-web",
                    "action": "deny",
                    "sources": ["segA"],
                    "destinations": ["segB"],
                    "protocols": ["tcp"],
                    "ports": [443],
                },
            ]
        },
        "metadata": {
            "execution_actions": [
                {"type": "webhook", "payload": {"title": "intent risky publish approved"}},
            ]
        },
    }

    res = client.post("/api/v1/intent/apply", json=payload, headers=operator_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["status"] == "applied"
    nb = body.get("northbound_publish") or {}
    assert nb.get("enabled") is True
    assert nb.get("decision") == "approval_gated"
    assert nb.get("approval_provided") is True


def test_intent_apply_skips_execution_actions_when_disabled(client, operator_user_token, db):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "intent_apply_requires_approval", "false")
    _set_setting(db, "intent_apply_execute_actions", "false")

    payload = {
        "intent_type": "segment",
        "name": "seg-exec-disabled",
        "dry_run": False,
        "idempotency_key": "intent-exec-disabled-1",
        "spec": {"segments": [{"name": "prod", "cidrs": ["10.30.0.0/24"]}]},
        "metadata": {
            "execution_actions": [
                {"type": "run_scan", "payload": {"cidr": "10.30.0.0/24"}},
            ]
        },
    }

    res = client.post("/api/v1/intent/apply", json=payload, headers=operator_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["status"] == "applied"
    actions = body.get("execution_actions") or {}
    assert actions.get("enabled") is False
    assert int(actions.get("requested") or 0) == 1
    assert int(actions.get("executed") or 0) == 0
    rows = list(actions.get("results") or [])
    assert len(rows) == 1
    assert rows[0].get("status") == "skipped_execution_disabled"


def test_intent_apply_executes_action_plan_when_enabled(client, operator_user_token, db, monkeypatch):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "intent_apply_requires_approval", "false")
    _set_setting(db, "intent_apply_execute_actions", "true")

    payload = {
        "intent_type": "segment",
        "name": "seg-exec-enabled",
        "dry_run": False,
        "idempotency_key": "intent-exec-enabled-1",
        "spec": {"segments": [{"name": "prod", "cidrs": ["10.31.0.0/24"]}]},
        "metadata": {
            "execution_actions": [
                {"type": "run_scan", "payload": {"cidr": "10.31.0.0/24"}},
                {"type": "webhook", "payload": {"title": "intent test"}},
            ]
        },
    }

    monkeypatch.setattr(
        intent_service_mod.IntentService,
        "_execute_action_plan",
        staticmethod(
            lambda *_a, **_k: {
                "enabled": True,
                "requested": 2,
                "executed": 2,
                "errors": 0,
                "results": [
                    {"index": 1, "type": "run_scan", "status": "dispatched", "job_id": 901},
                    {"index": 2, "type": "webhook", "status": "sent", "delivery_id": "d-901"},
                ],
            }
        ),
    )

    res = client.post("/api/v1/intent/apply", json=payload, headers=operator_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["status"] == "applied"
    actions = body.get("execution_actions") or {}
    assert actions.get("enabled") is True
    assert int(actions.get("requested") or 0) == 2
    assert int(actions.get("executed") or 0) == 2
    assert int(actions.get("errors") or 0) == 0


def test_intent_apply_executes_cloud_bootstrap_action_when_enabled(client, operator_user_token, db, monkeypatch):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "intent_apply_requires_approval", "false")
    _set_setting(db, "intent_apply_execute_actions", "true")

    payload = {
        "intent_type": "segment",
        "name": "seg-cloud-bootstrap-action",
        "dry_run": False,
        "idempotency_key": "intent-exec-cloud-bootstrap-1",
        "spec": {"segments": [{"name": "prod", "cidrs": ["10.32.0.0/24"]}]},
        "metadata": {
            "execution_actions": [
                {"type": "cloud_bootstrap", "payload": {"account_ids": [11], "dry_run": True}},
            ]
        },
    }

    monkeypatch.setattr(
        intent_service_mod.IntentService,
        "_execute_cloud_bootstrap_action",
        staticmethod(
            lambda *_a, **_k: {
                "index": 1,
                "type": "cloud_bootstrap",
                "status": "dispatched",
                "run_status": "ok",
                "total_targets": 3,
                "success_targets": 3,
                "failed_targets": 0,
                "dry_run_targets": 3,
            }
        ),
    )

    res = client.post("/api/v1/intent/apply", json=payload, headers=operator_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["status"] == "applied"
    actions = body.get("execution_actions") or {}
    assert actions.get("enabled") is True
    assert int(actions.get("requested") or 0) == 1
    assert int(actions.get("executed") or 0) == 1
    rows = list(actions.get("results") or [])
    assert len(rows) == 1
    assert rows[0].get("type") == "cloud_bootstrap"
    assert rows[0].get("status") == "dispatched"


def test_intent_apply_cloud_policy_prepares_execution_bundle(client, operator_user_token, db, monkeypatch, tmp_path):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "intent_apply_requires_approval", "false")
    _set_setting(db, "intent_apply_execute_actions", "true")
    monkeypatch.setenv("NETSPHERE_CLOUD_INTENT_LIVE_APPLY_ENABLED", "true")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_EXECUTION_MODE", "prepare_only")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_WORK_ROOT", str(tmp_path))

    aws = CloudAccount(
        name="aws-live-apply",
        provider="aws",
        credentials={
            "auth_type": "access_key",
            "region": "ap-northeast-2",
            "access_key": "AKIATESTVALUE",
            "secret_key": "SECRETTESTVALUE",
        },
        is_active=True,
        tenant_id=None,
    )
    db.add(aws)
    db.flush()
    db.add(
        CloudResource(
            account_id=int(aws.id),
            resource_id="sg-001",
            resource_type="security_group",
            name="sg-a",
            region="ap-northeast-2",
            resource_metadata={"tags": {"owner": "netops", "env": "prod"}},
            state="active",
        )
    )
    db.commit()

    payload = {
        "intent_type": "cloud_policy",
        "name": "corp-guardrails",
        "dry_run": False,
        "approval_id": 5001,
        "idempotency_key": "intent-cloud-policy-prepare",
        "spec": {
            "targets": {
                "providers": ["aws"],
                "account_ids": [int(aws.id)],
                "regions": ["ap-northeast-2"],
                "resource_types": ["security_group"],
            },
            "required_tags": [{"key": "owner"}],
            "blocked_ingress_cidrs": ["0.0.0.0/0"],
        },
    }

    res = client.post("/api/v1/intent/apply", json=payload, headers=operator_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["status"] == "applied"
    actions = body.get("execution_actions") or {}
    assert actions.get("enabled") is True
    rows = list(actions.get("results") or [])
    assert len(rows) == 1
    row = rows[0]
    assert row.get("type") == "cloud_intent_apply"
    assert row.get("status") == "prepared_only"
    bundle_dir = Path(str(row.get("bundle_dir") or ""))
    assert bundle_dir.exists()
    request_payload = json.loads((bundle_dir / "execution-request.json").read_text(encoding="utf-8"))
    target_accounts = list(request_payload.get("target_accounts") or [])
    assert len(target_accounts) == 1
    assert target_accounts[0]["credentials"]["secret_key"] == "********"
    contract = dict(target_accounts[0].get("credential_contract") or {})
    assert "AWS_ACCESS_KEY_ID" in list(contract.get("required_env_keys") or [])
    assert "AWS_SECRET_ACCESS_KEY" in list(contract.get("required_env_keys") or [])
    render_payload = json.loads((bundle_dir / "terraform-render.json").read_text(encoding="utf-8"))
    assert "aws" in list(render_payload.get("rendered_providers") or [])
    post_check_payload = json.loads((bundle_dir / "post-check-plan.json").read_text(encoding="utf-8"))
    assert bool(post_check_payload.get("required")) is True
    assert len(list(post_check_payload.get("steps") or [])) >= 2
    evidence_payload = json.loads((bundle_dir / "evidence-plan.json").read_text(encoding="utf-8"))
    assert "terraform-plan-preview.json" in list(evidence_payload.get("artifacts") or [])
    rollback_plan_payload = json.loads((bundle_dir / "rollback-plan.json").read_text(encoding="utf-8"))
    assert str(rollback_plan_payload.get("strategy") or "") == "terraform_state_reconcile"
    post_check_result_payload = json.loads((bundle_dir / "post-check-result.json").read_text(encoding="utf-8"))
    assert str(post_check_result_payload.get("status") or "") == "skipped_prepare_only"
    rollback_result_payload = json.loads((bundle_dir / "rollback-result.json").read_text(encoding="utf-8"))
    assert str(rollback_result_payload.get("status") or "") == "not_needed"
    assert (bundle_dir / "terraform" / "backend.tf.json").exists()
    assert (bundle_dir / "terraform" / "backend.local.auto.tfbackend.json").exists()
    assert (bundle_dir / "terraform" / "modules" / "aws" / "cloud_policy" / "main.tf.json").exists()


def test_intent_apply_cloud_policy_mock_apply_mode(client, operator_user_token, db, monkeypatch, tmp_path):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "intent_apply_requires_approval", "false")
    _set_setting(db, "intent_apply_execute_actions", "true")
    monkeypatch.setenv("NETSPHERE_CLOUD_INTENT_LIVE_APPLY_ENABLED", "true")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_EXECUTION_MODE", "mock_apply")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_WORK_ROOT", str(tmp_path))
    from app.services import cloud_pipeline_service as cps
    monkeypatch.setattr(
        cps.CloudPipelineService,
        "run",
        staticmethod(
            lambda *_a, **_k: {
                "status": "ok",
                "scanned_resources": 4,
                "failed_accounts": 0,
                "normalized_by_provider": {"aws": 4},
                "accounts": [
                    {
                        "account_id": 1,
                        "provider": "aws",
                        "preflight_status": "ok",
                        "scan_status": "ok",
                        "scan_count": 4,
                    }
                ],
            }
        ),
    )

    aws = CloudAccount(
        name="aws-mock-apply",
        provider="aws",
        credentials={
            "auth_type": "access_key",
            "region": "ap-northeast-2",
            "access_key": "AKIAMOCKVALUE",
            "secret_key": "SECRETMOCKVALUE",
        },
        is_active=True,
        tenant_id=None,
    )
    db.add(aws)
    db.flush()
    db.add(
        CloudResource(
            account_id=int(aws.id),
            resource_id="rtb-001",
            resource_type="route_table",
            name="rtb-a",
            region="ap-northeast-2",
            resource_metadata={"tags": {"owner": "netops", "env": "prod"}},
            state="active",
        )
    )
    db.commit()

    payload = {
        "intent_type": "cloud_policy",
        "name": "corp-routes",
        "dry_run": False,
        "approval_id": 5002,
        "idempotency_key": "intent-cloud-policy-mock",
        "spec": {
            "targets": {
                "providers": ["aws"],
                "account_ids": [int(aws.id)],
                "regions": ["ap-northeast-2"],
                "resource_types": ["route_table"],
            },
            "protected_route_destinations": ["0.0.0.0/0"],
            "allowed_default_route_targets": ["nat-gateway"],
        },
    }

    res = client.post("/api/v1/intent/apply", json=payload, headers=operator_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["status"] == "applied"
    actions = body.get("execution_actions") or {}
    rows = list(actions.get("results") or [])
    assert len(rows) == 1
    row = rows[0]
    assert row.get("type") == "cloud_intent_apply"
    assert row.get("status") == "applied_mock"
    assert bool(row.get("post_check_failed")) is False
    assert bool(row.get("rollback_attempted")) is False
    provider_runs = list(row.get("provider_runs") or [])
    assert len(provider_runs) == 1
    assert provider_runs[0].get("provider") == "aws"
    assert provider_runs[0].get("status") == "mock_applied"
    assert str((row.get("post_check_result") or {}).get("status") or "") == "passed"
    assert str((row.get("rollback_plan") or {}).get("status") or "") == "not_needed"


def test_intent_apply_cloud_policy_marks_post_check_failure_and_prepares_rollback(client, operator_user_token, db, monkeypatch, tmp_path):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "intent_apply_requires_approval", "false")
    _set_setting(db, "intent_apply_execute_actions", "true")
    monkeypatch.setenv("NETSPHERE_CLOUD_INTENT_LIVE_APPLY_ENABLED", "true")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_EXECUTION_MODE", "mock_apply")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_WORK_ROOT", str(tmp_path))

    from app.services import cloud_pipeline_service as cps
    monkeypatch.setattr(
        cps.CloudPipelineService,
        "run",
        staticmethod(
            lambda *_a, **_k: {
                "status": "partial",
                "scanned_resources": 1,
                "failed_accounts": 1,
                "normalized_by_provider": {"aws": 1},
                "accounts": [
                    {
                        "account_id": 1,
                        "provider": "aws",
                        "preflight_status": "ok",
                        "scan_status": "failed",
                        "scan_count": 0,
                        "message": "scan timed out",
                    }
                ],
            }
        ),
    )

    aws = CloudAccount(
        name="aws-postcheck-fail",
        provider="aws",
        credentials={
            "auth_type": "access_key",
            "region": "ap-northeast-2",
            "access_key": "AKIAPOSTCHECK",
            "secret_key": "SECRETPOSTCHECK",
        },
        is_active=True,
        tenant_id=None,
    )
    db.add(aws)
    db.flush()
    db.add(
        CloudResource(
            account_id=int(aws.id),
            resource_id="sg-postcheck-001",
            resource_type="security_group",
            name="sg-postcheck",
            region="ap-northeast-2",
            resource_metadata={"tags": {"owner": "netops"}},
            state="active",
        )
    )
    db.commit()

    payload = {
        "intent_type": "cloud_policy",
        "name": "corp-postcheck-fail",
        "dry_run": False,
        "approval_id": 5004,
        "idempotency_key": "intent-cloud-policy-postcheck-fail",
        "spec": {
            "targets": {
                "providers": ["aws"],
                "account_ids": [int(aws.id)],
                "regions": ["ap-northeast-2"],
                "resource_types": ["security_group"],
            },
            "blocked_ingress_cidrs": ["0.0.0.0/0"],
        },
    }

    res = client.post("/api/v1/intent/apply", json=payload, headers=operator_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    rows = list((body.get("execution_actions") or {}).get("results") or [])
    assert len(rows) == 1
    row = rows[0]
    assert row.get("status") == "post_check_failed"
    assert bool(row.get("post_check_failed")) is True
    assert str(row.get("failure_cause") or "") == "post_check_failed"
    assert str((row.get("post_check_result") or {}).get("status") or "") == "failed"
    assert str((row.get("rollback_plan") or {}).get("status") or "") == "approval_required"
    assert str((row.get("rollback_result") or {}).get("status") or "") == "approval_required"


def test_intent_apply_cloud_policy_real_apply_mode_runs_fake_terraform(
    client,
    operator_user_token,
    db,
    monkeypatch,
    tmp_path,
):
    _set_setting(db, "intent_engine_enabled", "true")
    _set_setting(db, "intent_apply_requires_approval", "false")
    _set_setting(db, "intent_apply_execute_actions", "true")
    monkeypatch.setenv("NETSPHERE_CLOUD_INTENT_LIVE_APPLY_ENABLED", "true")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_EXECUTION_MODE", "real_apply")
    monkeypatch.setenv("NETSPHERE_TERRAFORM_WORK_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("NETSPHERE_TERRAFORM_STATE_ROOT", str(tmp_path / "state"))
    monkeypatch.setenv("NETSPHERE_TERRAFORM_STATE_BACKEND", "local")

    fake_runner = tmp_path / "fake_terraform.py"
    fake_runner.write_text(
        "\n".join(
            [
                "import json, os, sys",
                "cmd = sys.argv[1:]",
                "log = os.environ.get('TF_FAKE_LOG')",
                "if log:",
                "    with open(log, 'a', encoding='utf-8') as fp:",
                "        fp.write(json.dumps(cmd) + '\\n')",
                "for item in cmd:",
                "    if item.startswith('-out='):",
                "        path = item.split('=', 1)[1]",
                "        with open(path, 'w', encoding='utf-8') as fp:",
                "            fp.write('fake-plan')",
                "if cmd[:2] == ['output', '-json']:",
                "    sys.stdout.write(json.dumps({'render_summary': {'value': {'provider': 'aws'}}}))",
                "sys.exit(0)",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(
        "NETSPHERE_TERRAFORM_BIN",
        f'\"{sys.executable}\" \"{fake_runner}\"',
    )
    monkeypatch.setenv("TF_FAKE_LOG", str(tmp_path / "terraform-calls.log"))
    from app.services import cloud_pipeline_service as cps
    monkeypatch.setattr(
        cps.CloudPipelineService,
        "run",
        staticmethod(
            lambda *_a, **_k: {
                "status": "ok",
                "scanned_resources": 2,
                "failed_accounts": 0,
                "normalized_by_provider": {"aws": 2},
                "accounts": [
                    {
                        "account_id": 1,
                        "provider": "aws",
                        "preflight_status": "ok",
                        "scan_status": "ok",
                        "scan_count": 2,
                    }
                ],
            }
        ),
    )

    aws = CloudAccount(
        name="aws-real-apply",
        provider="aws",
        credentials={
            "auth_type": "access_key",
            "region": "ap-northeast-2",
            "access_key": "AKIAREALVALUE",
            "secret_key": "SECRETREALVALUE",
        },
        is_active=True,
        tenant_id=None,
    )
    db.add(aws)
    db.flush()
    db.add(
        CloudResource(
            account_id=int(aws.id),
            resource_id="subnet-001",
            resource_type="subnet",
            name="subnet-a",
            region="ap-northeast-2",
            resource_metadata={"tags": {"owner": "netops"}},
            state="active",
        )
    )
    db.commit()

    payload = {
        "intent_type": "cloud_policy",
        "name": "corp-subnet-guardrail",
        "dry_run": False,
        "approval_id": 5003,
        "idempotency_key": "intent-cloud-policy-real",
        "spec": {
            "targets": {
                "providers": ["aws"],
                "account_ids": [int(aws.id)],
                "regions": ["ap-northeast-2"],
                "resource_types": ["subnet"],
            },
            "required_tags": [{"key": "owner"}],
        },
    }

    res = client.post("/api/v1/intent/apply", json=payload, headers=operator_user_token)
    assert res.status_code == 200
    body = _unwrap(res.json())
    assert body["status"] == "applied"
    actions = body.get("execution_actions") or {}
    rows = list(actions.get("results") or [])
    assert len(rows) == 1
    row = rows[0]
    assert row.get("type") == "cloud_intent_apply"
    assert row.get("status") == "applied_real"
    bundle_dir = Path(str(row.get("bundle_dir") or ""))
    runner_result = json.loads((bundle_dir / "runner-result.json").read_text(encoding="utf-8"))
    assert str(runner_result.get("status") or "") == "applied_real"
    steps = list(runner_result.get("steps") or [])
    assert [step.get("step") for step in steps[:5]] == ["version", "init", "validate", "plan", "apply"]
    assert str((runner_result.get("post_check_result") or {}).get("status") or "") == "passed"
    assert str((runner_result.get("rollback_plan") or {}).get("status") or "") == "not_needed"
    assert str((runner_result.get("rollback_result") or {}).get("status") or "") == "not_needed"
    assert (bundle_dir / "terraform" / "netsphere.tfplan").exists()
