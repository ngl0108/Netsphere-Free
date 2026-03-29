from __future__ import annotations

import random
from typing import Any

from app.services.capability_profile_service import CapabilityProfileService


def _rand_scalar(rng: random.Random) -> Any:
    bucket = rng.randint(0, 7)
    if bucket == 0:
        return None
    if bucket == 1:
        return rng.choice([True, False, "true", "false", "yes", "no", "1", "0"])
    if bucket == 2:
        return rng.randint(-9999, 9999)
    if bucket == 3:
        return rng.random() * rng.randint(-10, 10)
    if bucket == 4:
        return "".join(rng.choice("abcdefghijklmnopqrstuvwxyz_-0123456789") for _ in range(rng.randint(0, 14)))
    if bucket == 5:
        return {"unexpected": "object"}
    if bucket == 6:
        return [rng.choice(["snmp", "ssh", "gnmi", "telnet", 123, None]) for _ in range(rng.randint(0, 6))]
    return "???garbled???"


def _rand_object(rng: random.Random, depth: int = 0) -> Any:
    if depth > 2:
        return _rand_scalar(rng)
    kind = rng.randint(0, 4)
    if kind == 0:
        return _rand_scalar(rng)
    if kind == 1:
        return [_rand_object(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    obj: dict[str, Any] = {}
    for i in range(rng.randint(0, 6)):
        key = f"k_{depth}_{i}_{rng.randint(1, 999)}"
        obj[key] = _rand_object(rng, depth + 1)
    return obj


def _build_random_profile(rng: random.Random) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "default": {
            "allowed_protocols": _rand_object(rng, 1),
            "auto_reflection": _rand_object(rng, 1),
            "read_only": _rand_object(rng, 1),
        },
        "sites": _rand_object(rng, 1),
        "device_types": _rand_object(rng, 1),
    }
    if rng.random() < 0.35:
        profile["default"] = _rand_object(rng, 1)
    if rng.random() < 0.35:
        profile["sites"] = _rand_object(rng, 1)
    if rng.random() < 0.35:
        profile["device_types"] = _rand_object(rng, 1)
    return profile


def test_capability_profile_fuzz_stability():
    rng = random.Random(20260219)
    for _ in range(400):
        src = _build_random_profile(rng)
        normalized = CapabilityProfileService.normalize_profile(src)
        assert isinstance(normalized, dict)
        assert isinstance(normalized.get("default"), dict)
        assert isinstance(normalized.get("sites"), dict)
        assert isinstance(normalized.get("device_types"), dict)

        default = normalized["default"]
        assert isinstance(default.get("allowed_protocols"), list)
        assert default["allowed_protocols"], "allowed_protocols must not be empty"
        assert set(default["allowed_protocols"]).issubset({"snmp", "ssh", "gnmi"})
        assert isinstance(default.get("auto_reflection"), dict)
        assert isinstance(default.get("read_only"), bool)
