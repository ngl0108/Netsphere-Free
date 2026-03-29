import os

import pytest
import requests


_base_url = os.getenv("NETSPHERE_BASE_URL") or os.getenv("NETMANAGER_BASE_URL")
if not _base_url:
    pytest.skip("NETSPHERE_BASE_URL or NETMANAGER_BASE_URL is not set", allow_module_level=True)

BASE_URL = _base_url.rstrip("/")


def _unwrap_payload(payload):
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        return payload.get("data") or {}
    return payload if isinstance(payload, dict) else {}


def test_root_endpoint_responds():
    res = requests.get(f"{BASE_URL}/", timeout=5)
    assert res.status_code == 200
    payload = _unwrap_payload(res.json())
    assert isinstance(payload, dict)
    assert payload.get("message")


def test_openapi_responds():
    res = requests.get(f"{BASE_URL}/openapi.json", timeout=5)
    assert res.status_code == 200
    payload = _unwrap_payload(res.json())
    assert isinstance(payload, dict)
    assert payload.get("openapi")
