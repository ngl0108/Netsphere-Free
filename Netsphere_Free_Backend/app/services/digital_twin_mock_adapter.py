from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FIXTURE_ROOT = REPO_ROOT / "test-data" / "synthetic" / "digital-twin"


class DigitalTwinMockError(RuntimeError):
    """Base error for digital twin fixture access."""


class DigitalTwinTimeoutError(DigitalTwinMockError):
    """Raised when fixture case models a timeout."""


class DigitalTwinMalformedPayloadError(DigitalTwinMockError):
    """Raised when fixture case intentionally models malformed payload."""


class DigitalTwinProtocolError(DigitalTwinMockError):
    """Raised when protocol/vendor/case does not exist."""


class DigitalTwinMockAdapter:
    """Fixture-backed mock adapter for SNMP/SSH/gNMI deterministic tests."""

    _PROTOCOLS = ("snmp", "ssh", "gnmi")

    def __init__(self, fixture_root: Path | str | None = None):
        root = Path(fixture_root).resolve() if fixture_root else DEFAULT_FIXTURE_ROOT.resolve()
        self.fixture_root = root
        self._data = {protocol: self._load_protocol(protocol) for protocol in self._PROTOCOLS}

    def _load_protocol(self, protocol: str) -> dict[str, Any]:
        path = self.fixture_root / f"{protocol}.json"
        if not path.exists():
            raise DigitalTwinProtocolError(f"Missing digital twin fixture: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive
            raise DigitalTwinProtocolError(f"Failed to parse fixture {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise DigitalTwinProtocolError(f"Invalid fixture root shape: {path}")
        vendors = payload.get("vendors")
        if not isinstance(vendors, dict):
            raise DigitalTwinProtocolError(f"Missing `vendors` map in fixture: {path}")
        return payload

    def available_vendors(self, protocol: str) -> list[str]:
        data = self._data.get(str(protocol or "").lower())
        if not data:
            return []
        return sorted(str(k) for k in data.get("vendors", {}).keys())

    def _resolve_case(self, protocol: str, vendor: str, case: str = "normal") -> dict[str, Any]:
        protocol_k = str(protocol or "").strip().lower()
        vendor_k = str(vendor or "").strip().lower()
        case_k = str(case or "normal").strip().lower()
        if protocol_k not in self._data:
            raise DigitalTwinProtocolError(f"Unsupported protocol: {protocol}")

        vendor_map = self._data[protocol_k].get("vendors", {})
        case_map = vendor_map.get(vendor_k)
        if not isinstance(case_map, dict):
            raise DigitalTwinProtocolError(f"Unknown vendor `{vendor}` for protocol `{protocol}`")

        payload = case_map.get(case_k)
        if not isinstance(payload, dict):
            raise DigitalTwinProtocolError(
                f"Unknown case `{case}` for vendor `{vendor}` protocol `{protocol}`"
            )

        status = str(payload.get("status") or "ok").strip().lower()
        if status == "timeout":
            raise DigitalTwinTimeoutError(str(payload.get("error") or f"{protocol.upper()} timeout"))
        if status == "malformed":
            raise DigitalTwinMalformedPayloadError(
                str(payload.get("error") or f"{protocol.upper()} malformed payload")
            )
        if status not in {"ok", "partial"}:
            raise DigitalTwinProtocolError(f"Unexpected fixture status `{status}` in {protocol}/{vendor}/{case}")
        return payload

    def get_snmp_system_info(self, vendor: str, case: str = "normal") -> dict[str, Any]:
        payload = self._resolve_case("snmp", vendor, case)
        sysinfo = payload.get("sysinfo", {})
        if not isinstance(sysinfo, dict):
            raise DigitalTwinMalformedPayloadError("SNMP sysinfo payload must be object")
        return sysinfo

    def get_snmp_oids(self, vendor: str, case: str = "normal") -> dict[str, Any]:
        payload = self._resolve_case("snmp", vendor, case)
        oids = payload.get("oids", {})
        if not isinstance(oids, dict):
            raise DigitalTwinMalformedPayloadError("SNMP oids payload must be object")
        return oids

    def get_ssh_inventory(self, vendor: str, case: str = "normal") -> list[dict[str, Any]]:
        payload = self._resolve_case("ssh", vendor, case)
        inventory = payload.get("inventory", [])
        if not isinstance(inventory, list):
            raise DigitalTwinMalformedPayloadError("SSH inventory payload must be list")
        return [x for x in inventory if isinstance(x, dict)]

    def get_ssh_neighbors(self, vendor: str, case: str = "normal") -> list[dict[str, Any]]:
        payload = self._resolve_case("ssh", vendor, case)
        neighbors = payload.get("neighbors", [])
        if not isinstance(neighbors, list):
            raise DigitalTwinMalformedPayloadError("SSH neighbors payload must be list")
        return [x for x in neighbors if isinstance(x, dict)]

    def get_gnmi_telemetry(self, vendor: str, case: str = "normal") -> dict[str, Any]:
        payload = self._resolve_case("gnmi", vendor, case)
        telemetry = payload.get("telemetry", {})
        if not isinstance(telemetry, dict):
            raise DigitalTwinMalformedPayloadError("gNMI telemetry payload must be object")
        return telemetry
