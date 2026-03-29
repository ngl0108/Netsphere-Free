from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt


def _load_revocation_map(path_value: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    path = Path(str(path_value or "").strip())
    if not path.exists():
        return out
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    if isinstance(parsed, list):
        for raw in parsed:
            jti = str(raw or "").strip()
            if jti:
                out[jti] = {"reason": "revoked_by_file", "source": str(path)}
        return out
    if not isinstance(parsed, dict):
        return out
    rows = parsed.get("revoked")
    if not isinstance(rows, list):
        return out
    for row in rows:
        if isinstance(row, str):
            jti = row.strip()
            if jti:
                out[jti] = {"reason": "revoked_by_file", "source": str(path)}
            continue
        if not isinstance(row, dict):
            continue
        jti = str(row.get("jti") or "").strip()
        if not jti:
            continue
        out[jti] = {
            "reason": str(row.get("reason") or "revoked_by_file").strip() or "revoked_by_file",
            "source": str(path),
            "revoked_at": row.get("revoked_at"),
            "revoked_by": row.get("revoked_by"),
        }
    return out


def _extract_features(payload: dict[str, Any]) -> list[str]:
    raw = payload.get("features")
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        return [x.strip() for x in raw.split(",") if x.strip()]
    return []


def _extract_max_devices(payload: dict[str, Any]) -> int:
    limits = payload.get("limits") if isinstance(payload.get("limits"), dict) else {}
    value = limits.get("devices", payload.get("max_devices", 0))
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify signed NetSphere license JWT.")
    parser.add_argument("--public-key", required=True, help="PEM public key path")
    parser.add_argument("--token", default="", help="JWT token string (optional if --token-file used)")
    parser.add_argument("--token-file", default="", help="Path to file containing JWT token")
    parser.add_argument("--algorithm", default="RS256", help="JWT verification algorithm")
    parser.add_argument("--issuer", default="", help="Optional expected issuer")
    parser.add_argument("--audience", default="", help="Optional expected audience")
    parser.add_argument(
        "--revocation-list",
        default="",
        help="Optional revocation JSON file path (same format as LICENSE_REVOCATION_LIST_PATH)",
    )
    parser.add_argument("--grace-days", type=int, default=0, help="Expiration grace days (default: 0)")
    parser.add_argument("--warning-days", type=int, default=30, help="Expiring soon threshold in days")
    args = parser.parse_args()

    token = str(args.token or "").strip()
    if not token and args.token_file:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
    if not token:
        raise ValueError("token is required (--token or --token-file)")

    public_key = Path(args.public_key).read_text(encoding="utf-8")
    options = {"verify_aud": bool(args.audience)}
    kwargs = {"algorithms": [str(args.algorithm or "RS256")], "options": options}
    if args.issuer:
        kwargs["issuer"] = str(args.issuer).strip()
    if args.audience:
        kwargs["audience"] = str(args.audience).strip()

    payload = jwt.decode(token, public_key, **kwargs)
    now = datetime.now(timezone.utc)
    exp_raw = payload.get("exp")
    if exp_raw is None:
        raise ValueError("Missing exp claim")
    exp = datetime.fromtimestamp(float(exp_raw), tz=timezone.utc)
    jti = str(payload.get("jti") or "").strip() or None

    revoked = None
    revocation_map = {}
    if args.revocation_list:
        revocation_map = _load_revocation_map(args.revocation_list)
        if jti:
            revoked = revocation_map.get(jti)

    grace_days = max(0, int(args.grace_days or 0))
    warning_days = max(0, int(args.warning_days or 0))

    is_valid = True
    status = "Active"
    in_grace_period = False
    grace_until = None

    if revoked:
        is_valid = False
        status = "Revoked"
    elif exp < now:
        if grace_days > 0:
            grace_until_dt = exp + timedelta(days=grace_days)
            if now <= grace_until_dt:
                in_grace_period = True
                grace_until = grace_until_dt.isoformat()
                status = f"Grace Period ({grace_days}d)"
            else:
                is_valid = False
                status = "Expired"
        else:
            is_valid = False
            status = "Expired"
    else:
        days_to_expiration = int((exp - now).total_seconds() // 86400)
        if days_to_expiration <= warning_days:
            status = "Expiring Soon"

    days_to_expiration = int((exp - now).total_seconds() // 86400)
    result = {
        "is_valid": bool(is_valid),
        "status": status,
        "customer": str(payload.get("sub") or payload.get("customer") or "Unknown"),
        "sku": str(payload.get("sku") or "").strip() or None,
        "jti": jti,
        "expires_at": exp.isoformat(),
        "days_to_expiration": days_to_expiration,
        "in_grace_period": bool(in_grace_period),
        "grace_until": grace_until,
        "max_devices": _extract_max_devices(payload),
        "features": _extract_features(payload),
        "revoked": bool(revoked),
        "revocation": revoked,
        "payload": payload,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
