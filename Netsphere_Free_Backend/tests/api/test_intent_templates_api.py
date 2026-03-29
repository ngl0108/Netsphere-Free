def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_intent_template_catalog_exposes_seed_templates(client, operator_user_token):
    res = client.get("/api/v1/intent/templates/catalog", headers=operator_user_token)
    assert res.status_code == 200
    payload = _unwrap(res.json())

    keys = {str(row.get("key") or "") for row in payload["templates"]}
    assert "network-segmentation-baseline" in keys
    assert "public-ingress-lockdown" in keys
    assert "default-route-control" in keys
    assert "required-tags-compliance" in keys
    assert payload["coverage"]["template_count"] >= 4
    assert "aws" in payload["coverage"]["providers"]
    assert "guardrail" in payload["coverage"]["categories"]


def test_intent_template_detail_returns_parameter_schema_and_starter_payload(client, operator_user_token):
    res = client.get("/api/v1/intent/templates/default-route-control", headers=operator_user_token)
    assert res.status_code == 200
    payload = _unwrap(res.json())

    assert payload["key"] == "default-route-control"
    assert payload["intent_type"] == "cloud_policy"
    assert payload["risk_level"] == "high"
    assert "approval_required" in list(payload.get("risk_notes") or [])
    assert any(str(row.get("field_key")) == "protected_route_destinations" for row in payload["parameter_schema"])
    starter = payload["starter_payload"]
    assert starter["resource_types"] == ["route_table"]
    assert starter["enforce_private_only_next_hop"] is True
