from __future__ import annotations

from app.services.parser_quality_service import ParserQualityService


def _issue_codes(payload):
    return [str(x.get("code")) for x in list(payload.get("issues") or []) if isinstance(x, dict)]


def test_parser_quality_adds_schema_violation_and_low_confidence():
    raw = {
        "ip_address": "",
        "hostname": "",
        "device_type": "cisco_xe",
        "snmp_status": "BROKEN_STATE",
        "vendor_confidence": 0.22,
        "issues": [],
    }
    normalized = ParserQualityService.normalize_discovery_result(
        raw,
        low_conf_threshold=0.8,
    )

    codes = _issue_codes(normalized)
    assert "parser_schema_violation" in codes
    assert "parser_low_confidence" in codes
    assert bool(normalized.get("low_confidence")) is True

    evidence = normalized.get("evidence") or {}
    assert bool(evidence.get("parser_schema_valid")) is False
    assert float(evidence.get("parser_confidence") or 0.0) < 0.8
    assert float(normalized.get("vendor_confidence") or 0.0) <= 0.35


def test_parser_quality_passes_valid_payload_without_schema_violation():
    raw = {
        "ip_address": "10.20.30.40",
        "hostname": "edge-1",
        "device_type": "cisco_xe",
        "snmp_status": "reachable",
        "vendor_confidence": 0.86,
        "model": "C9300-48P",
        "os_version": "17.9.4",
        "sys_object_id": "1.3.6.1.4.1.9.1.2695",
        "issues": [],
        "evidence": {},
    }
    normalized = ParserQualityService.normalize_discovery_result(
        raw,
        low_conf_threshold=0.45,
    )

    codes = _issue_codes(normalized)
    assert "parser_schema_violation" not in codes
    assert bool(normalized.get("low_confidence")) is False
    assert float(normalized.get("parser_confidence") or 0.0) >= 0.45
    assert float(normalized.get("vendor_confidence") or 0.0) >= 0.45

