from __future__ import annotations

from typing import Any, Dict, List


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


class ParserQualityService:
    """
    Validation + confidence score for discovery parser outputs.
    """

    DEFAULT_LOW_CONF_THRESHOLD = 0.45

    @staticmethod
    def _normalize_issues(raw: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not isinstance(raw, list):
            return out
        for item in raw:
            if isinstance(item, dict):
                out.append(dict(item))
        return out

    @staticmethod
    def _normalize_evidence(raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return dict(raw)
        return {}

    @staticmethod
    def _schema_errors(payload: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        ip = str(payload.get("ip_address") or "").strip()
        if not ip:
            errors.append("missing_ip_address")
        host = str(payload.get("hostname") or "").strip()
        if not host:
            errors.append("missing_hostname")
        snmp_status = str(payload.get("snmp_status") or "").strip().lower()
        if snmp_status not in {"reachable", "unreachable", "unknown"}:
            errors.append("invalid_snmp_status")
        device_type = str(payload.get("device_type") or "").strip().lower()
        if not device_type:
            errors.append("missing_device_type")
        vendor_conf = payload.get("vendor_confidence")
        if vendor_conf is None:
            errors.append("missing_vendor_confidence")
        else:
            try:
                float(vendor_conf)
            except Exception:
                errors.append("invalid_vendor_confidence")
        return errors

    @staticmethod
    def _compute_parser_confidence(payload: Dict[str, Any], schema_errors: List[str]) -> float:
        conf = _clamp(_as_float(payload.get("vendor_confidence"), 0.0))
        snmp_status = str(payload.get("snmp_status") or "").strip().lower()
        device_type = str(payload.get("device_type") or "").strip().lower()
        model = str(payload.get("model") or "").strip()
        os_version = str(payload.get("os_version") or "").strip()
        sys_object_id = str(payload.get("sys_object_id") or "").strip()

        if snmp_status == "reachable":
            conf += 0.15
        elif snmp_status == "unreachable":
            conf -= 0.12

        if device_type and device_type not in {"unknown", "manageable_device", "web_device"}:
            conf += 0.14
        elif device_type:
            conf -= 0.08

        if model:
            conf += 0.08
        if os_version:
            conf += 0.06
        if sys_object_id:
            conf += 0.08

        if schema_errors:
            conf -= 0.25

        issues = payload.get("issues")
        if isinstance(issues, list):
            has_error = False
            has_warn = False
            for item in issues:
                if not isinstance(item, dict):
                    continue
                sev = str(item.get("severity") or "").strip().lower()
                if sev == "error":
                    has_error = True
                elif sev in {"warn", "warning"}:
                    has_warn = True
            if has_error:
                conf -= 0.15
            elif has_warn:
                conf -= 0.07

        return round(_clamp(conf), 3)

    @staticmethod
    def normalize_discovery_result(
        raw_result: Dict[str, Any] | None,
        *,
        ip_address: str | None = None,
        low_conf_threshold: float | None = None,
    ) -> Dict[str, Any]:
        payload = dict(raw_result or {})
        if ip_address and not payload.get("ip_address"):
            payload["ip_address"] = str(ip_address)

        payload["issues"] = ParserQualityService._normalize_issues(payload.get("issues"))
        payload["evidence"] = ParserQualityService._normalize_evidence(payload.get("evidence"))

        payload["hostname"] = str(payload.get("hostname") or payload.get("ip_address") or "").strip()
        payload["vendor"] = str(payload.get("vendor") or "Unknown").strip() or "Unknown"
        payload["model"] = str(payload.get("model") or "").strip()
        payload["os_version"] = str(payload.get("os_version") or "").strip()
        payload["device_type"] = str(payload.get("device_type") or "unknown").strip() or "unknown"
        payload["snmp_status"] = str(payload.get("snmp_status") or "unknown").strip().lower() or "unknown"
        payload["vendor_confidence"] = round(_clamp(_as_float(payload.get("vendor_confidence"), 0.0)), 3)

        schema_errors = ParserQualityService._schema_errors(payload)
        parser_conf = ParserQualityService._compute_parser_confidence(payload, schema_errors)
        threshold = _clamp(_as_float(low_conf_threshold, ParserQualityService.DEFAULT_LOW_CONF_THRESHOLD))

        if schema_errors:
            payload["issues"].append(
                {
                    "code": "parser_schema_violation",
                    "severity": "error",
                    "message": "Discovery parser output schema validation failed.",
                    "details": {"errors": schema_errors},
                }
            )
            payload["vendor_confidence"] = round(min(float(payload.get("vendor_confidence") or 0.0), 0.35), 3)

        if parser_conf < threshold:
            payload["issues"].append(
                {
                    "code": "parser_low_confidence",
                    "severity": "warn",
                    "message": "Parser confidence is below threshold and requires manual review.",
                    "details": {"confidence": parser_conf, "threshold": threshold},
                }
            )

        payload["vendor_confidence"] = round(min(float(payload.get("vendor_confidence") or 0.0), parser_conf), 3)
        payload["evidence"]["parser_confidence"] = parser_conf
        payload["evidence"]["parser_schema_valid"] = not bool(schema_errors)
        payload["evidence"]["parser_low_conf_threshold"] = threshold
        payload["parser_confidence"] = parser_conf
        payload["low_confidence"] = bool(parser_conf < threshold)
        return payload

