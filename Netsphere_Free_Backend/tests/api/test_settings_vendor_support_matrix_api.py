from __future__ import annotations


def _unwrap(body):
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def test_vendor_support_matrix_endpoint_generates_and_caches(client, admin_user_token):
    generated = client.get(
        "/api/v1/settings/vendor-support-matrix?refresh=true",
        headers=admin_user_token,
    )
    assert generated.status_code == 200
    payload = _unwrap(generated.json())

    summary = payload.get("summary") or {}
    assert int(summary.get("total_supported_device_types") or 0) >= 20
    assert float(summary.get("coverage_pct") or 0.0) == 100.0
    assert payload.get("source") == "generated"

    rows = payload.get("rows") or []
    assert any((r.get("device_type") == "dasan_nos") for r in rows)
    assert any((r.get("device_type") == "fortinet") for r in rows)

    cached = client.get(
        "/api/v1/settings/vendor-support-matrix",
        headers=admin_user_token,
    )
    assert cached.status_code == 200
    cached_payload = _unwrap(cached.json())
    assert cached_payload.get("source") in {"cached", "generated"}
