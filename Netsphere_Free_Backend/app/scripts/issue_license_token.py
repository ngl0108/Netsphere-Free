from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import jwt


def _parse_feature_list(raw_values: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for raw in raw_values:
        for item in str(raw or "").split(","):
            val = item.strip()
            if not val:
                continue
            key = val.lower().replace("-", "_").replace(" ", "_")
            if key in seen:
                continue
            seen.add(key)
            out.append(key)
    return out


def _build_payload(args: argparse.Namespace) -> dict:
    now = datetime.now(timezone.utc)
    if args.expires_at:
        exp = datetime.fromisoformat(args.expires_at)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        else:
            exp = exp.astimezone(timezone.utc)
    else:
        exp = now + timedelta(days=max(1, int(args.days or 365)))

    features = _parse_feature_list(args.feature or [])
    if not features:
        features = ["all"]

    payload = {
        "sub": str(args.customer).strip(),
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(args.jti).strip() if str(args.jti or "").strip() else str(uuid4()),
        "limits": {"devices": max(0, int(args.max_devices or 0))},
        "features": features,
    }
    if args.issuer:
        payload["iss"] = str(args.issuer).strip()
    if args.audience:
        payload["aud"] = str(args.audience).strip()
    if args.sku:
        payload["sku"] = str(args.sku).strip()
    if args.extra_json:
        extra = json.loads(args.extra_json)
        if isinstance(extra, dict):
            payload.update(extra)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Issue signed NetSphere license JWT (RS256).")
    parser.add_argument("--private-key", required=True, help="PEM private key path used to sign token")
    parser.add_argument("--customer", required=True, help="Customer name (JWT sub)")
    parser.add_argument("--max-devices", type=int, default=100, help="Maximum number of devices")
    parser.add_argument("--days", type=int, default=365, help="Validity period in days")
    parser.add_argument("--expires-at", help="Absolute expiration time (ISO-8601, UTC if tz omitted)")
    parser.add_argument("--feature", action="append", default=[], help="Feature name (repeatable or comma-separated)")
    parser.add_argument("--issuer", default="", help="JWT issuer (iss)")
    parser.add_argument("--audience", default="", help="JWT audience (aud)")
    parser.add_argument("--sku", default="", help="Optional SKU label")
    parser.add_argument("--jti", default="", help="Optional custom JTI (token id). If empty, UUIDv4 is generated.")
    parser.add_argument("--extra-json", default="", help="Optional JSON object merged into payload")
    parser.add_argument("--algorithm", default="RS256", help="JWT signing algorithm")
    parser.add_argument("--out", default="", help="Output file path for token")
    parser.add_argument("--print-payload", action="store_true", help="Print payload JSON")
    args = parser.parse_args()

    private_key_path = Path(args.private_key)
    private_key = private_key_path.read_text(encoding="utf-8")
    payload = _build_payload(args)
    token = jwt.encode(payload, private_key, algorithm=str(args.algorithm or "RS256"))

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(token, encoding="utf-8")
        print(f"Wrote token to {out_path}")

    if args.print_payload:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
